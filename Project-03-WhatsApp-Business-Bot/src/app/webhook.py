"""Defensive parsing of incoming Evolution API webhooks.

Evolution API payloads differ between versions and event types, and other
providers may post to the same endpoint, so parsing happens in two stages:

1. A precise reader for the documented Evolution API v2 ``messages.upsert``
   envelope. It also records the fields the HTTP layer needs for routing
   decisions (``event``, ``instance``, ``fromMe``, group JIDs).
2. A generic best-effort walker for anything that is not an Evolution
   envelope, so unknown or future shapes still yield a usable message.

When a payload *is* recognisably an Evolution envelope (it has both ``event``
and ``data``), the event name is treated as authoritative and non-message
events are not re-interpreted by the generic walker. That keeps status events
such as ``connection.update`` from being mistaken for chat messages.

Nothing in this module raises: unparseable input returns ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

WHATSAPP_USER_SUFFIX = "@s.whatsapp.net"
WHATSAPP_GROUP_SUFFIX = "@g.us"

# Evolution event names that carry a chat message. Compared case-insensitively,
# because Evolution emits both ``messages.upsert`` and ``MESSAGES_UPSERT``
# depending on the transport (HTTP webhook vs. RabbitMQ/SQS/Kafka).
MESSAGE_EVENTS: frozenset[str] = frozenset(
    {
        "messages.upsert",
        "messages.set",
        "messages.edited",
        "send.message",
    }
)

# Keys commonly used for the sender identifier, most specific first.
_SENDER_KEYS: tuple[str, ...] = (
    "remoteJid",
    "sender",
    "from",
    "chatId",
    "participant",
    "number",
    "phone",
    "jid",
)

# Keys commonly used for the message body.
_TEXT_KEYS: tuple[str, ...] = (
    "conversation",
    "text",
    "body",
    "content",
    "message",
    "messageText",
)

_MAX_DEPTH = 6
_MAX_CANDIDATES = 30


@dataclass(frozen=True)
class IncomingMessage:
    """A message extracted from a webhook payload."""

    sender: str | None
    text: str
    message_id: str | None = None
    event: str | None = None
    instance: str | None = None
    chat_id: str | None = None
    is_from_me: bool = False
    is_group: bool = False

    @property
    def has_sender(self) -> bool:
        return bool(self.sender)


def _as_text(value: Any) -> str | None:
    """Return ``value`` as a non-empty string, or ``None``."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _as_flag(value: Any) -> bool:
    """Coerce a payload flag to ``bool``, tolerating string representations."""
    if value is True or value is False:
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _sender_from_jid(jid: str) -> str:
    """Strip the device suffix from a JID (``...@s.whatsapp.net``)."""
    return jid.split("@", 1)[0].strip() or jid


def _extract_sender(node: dict[str, Any]) -> str | None:
    """Find a sender identifier in a dictionary, if present.

    ``key.id`` is deliberately excluded: it is the *message* ID, not a phone
    number, and treating it as a sender would make the bot address replies to
    a meaningless identifier.
    """
    key = node.get("key")
    if isinstance(key, dict):
        for candidate in ("remoteJid", "participant"):
            value = _as_text(key.get(candidate))
            if value:
                return _sender_from_jid(value)

    for name in _SENDER_KEYS:
        value = _as_text(node.get(name))
        if value:
            return _sender_from_jid(value)

    sender_node = node.get("sender")
    if isinstance(sender_node, dict):
        for name in ("id", "number", "jid", "phone"):
            value = _as_text(sender_node.get(name))
            if value:
                return _sender_from_jid(value)

    return None


def _extract_text(node: dict[str, Any]) -> str | None:
    """Find the message body in a dictionary, if present."""
    body = node.get("message")
    if isinstance(body, dict):
        inner = _extract_text(body)
        if inner:
            return inner

    for name in _TEXT_KEYS:
        value = _as_text(node.get(name))
        if value:
            return value

    # Extended and wrapped messages carry the body one level deeper.
    for wrapper in (
        "extendedTextMessage",
        "ephemeralMessage",
        "viewOnceMessage",
        "viewOnceMessageV2",
        "documentWithCaptionMessage",
    ):
        nested = node.get(wrapper)
        if isinstance(nested, dict):
            inner = _extract_text(nested)
            if inner:
                return inner
        elif isinstance(nested, str) and nested.strip():
            return nested.strip()

    return None


def _is_message_event(event: str | None) -> bool:
    """Match an Evolution event name across transport spellings.

    Evolution emits ``messages.upsert`` over HTTP webhooks but
    ``MESSAGES_UPSERT`` over RabbitMQ/SQS/Kafka, so both separators and case
    are normalised away before comparison.
    """
    if not event:
        return False
    normalised = event.strip().lower().replace("-", ".").replace("_", ".")
    return normalised in MESSAGE_EVENTS


def _find_data(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Evolution ``data`` object, unwrapping a single-item list."""
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
    return None


def _parse_evolution_v2(payload: dict[str, Any]) -> IncomingMessage | None:
    """Parse the documented Evolution API v2 message envelope.

    Returns ``None`` for non-message events, absent payload data, or when no
    text body can be found.
    """
    event = _as_text(payload.get("event"))
    if not _is_message_event(event):
        return None

    data = _find_data(payload)
    if data is None:
        return None

    key = data.get("key")
    key_node = key if isinstance(key, dict) else {}

    text = _extract_text(data)
    if not text:
        return None

    remote_jid = _as_text(key_node.get("remoteJid")) or _as_text(
        data.get("remoteJid")
    )
    is_group = bool(remote_jid and remote_jid.endswith(WHATSAPP_GROUP_SUFFIX))

    # In a group, ``remoteJid`` identifies the room while ``participant``
    # identifies the person who wrote. Prefer the person; fall back to the room.
    if is_group:
        sender_source = _as_text(key_node.get("participant")) or remote_jid
    else:
        sender_source = remote_jid or _extract_sender(data)

    sender = _sender_from_jid(sender_source) if sender_source else None

    return IncomingMessage(
        sender=sender,
        text=text,
        message_id=_as_text(key_node.get("id")) or _as_text(data.get("id")),
        event=event,
        instance=_as_text(payload.get("instance")),
        chat_id=remote_jid,
        is_from_me=_as_flag(key_node.get("fromMe")),
        is_group=is_group,
    )


def _iter_candidates(payload: Any) -> list[dict[str, Any]]:
    """Breadth-first collection of dict nodes, bounded in depth and size."""

    def walk(node: Any, depth: int, found: list[dict[str, Any]]) -> None:
        if depth > _MAX_DEPTH or len(found) >= _MAX_CANDIDATES:
            return
        if isinstance(node, dict):
            found.append(node)
            if depth == _MAX_DEPTH:
                return
            for value in node.values():
                walk(value, depth + 1, found)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1, found)

    found: list[dict[str, Any]] = []
    walk(payload, 0, found)
    return found


def _parse_generic(payload: Any) -> IncomingMessage | None:
    """Best-effort reader for payloads that are not Evolution envelopes."""
    if not isinstance(payload, (dict, list)):
        return None

    nodes = _iter_candidates(payload)
    if not nodes:
        return None

    best: IncomingMessage | None = None
    for node in nodes:
        text = _extract_text(node)
        if not text:
            continue
        sender = _extract_sender(node)
        key = node.get("key")
        key_node = key if isinstance(key, dict) else {}
        candidate = IncomingMessage(
            sender=sender,
            text=text,
            message_id=_as_text(node.get("id")),
            is_from_me=_as_flag(key_node.get("fromMe")),
        )
        if candidate.has_sender:
            return candidate
        if best is None:
            best = candidate

    return best


def parse_webhook(payload: Any) -> IncomingMessage | None:
    """Best-effort extraction of an incoming message from a webhook payload.

    Returns ``None`` when the payload has an unrecognised event, an unknown
    structure, or holds no readable text message. Never raises.
    """
    try:
        if isinstance(payload, dict) and "event" in payload and "data" in payload:
            return _parse_evolution_v2(payload)
        return _parse_generic(payload)
    except Exception:  # pragma: no cover - defensive: malformed payloads
        return None

"""Tests for webhook parsing and the /webhook endpoint.

Payload shapes come from ``tests/fixtures/evolution_messages_upsert.json``,
which mirrors the documented Evolution API v2 envelope. No real WhatsApp
number, account or credential is involved.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.config import WEBHOOK_SECRET_HEADER, Settings
from app.main import create_app
from app.webhook import parse_webhook
from tests.fixtures import FIXTURE_FILE, load, names

# Aliases for readability.
A_TEXT = load("A_text_message")
B_NESTED = load("B_nested_message")
C_UNKNOWN_EVENT = load("C_unknown_event")
D_MALFORMED = load("D_malformed")
E_FROM_ME = load("E_from_me")
F_GROUP = load("F_group_message")
G_EMPTY = load("G_empty_message")
H_NO_SENDER = load("H_no_sender")
I_UPPER = load("I_uppercase_event")
J_DATA_LIST = load("J_data_as_list")

FLAT_PAYLOAD = {"from": "555599000001", "text": "help"}


def _settings(**overrides: object) -> Settings:
    """Settings with nothing configured, so no network call is attempted."""
    base = {
        "evolution_api_url": "",
        "evolution_api_key": "",
        "evolution_instance": "",
        "webhook_url": "",
    }
    base.update(overrides)
    return Settings(**base)


def _app(**overrides: object) -> TestClient:
    return TestClient(create_app(_settings(**overrides)))


# --------------------------------------------------------------------------
# Fixture sanity: the JSON must stay valid and free of real credentials.
# --------------------------------------------------------------------------


def test_fixtures_are_wellformed_and_fictional() -> None:
    fixture_names = names()
    assert "A_text_message" in fixture_names
    assert len(fixture_names) >= 7

    raw = FIXTURE_FILE.read_text(encoding="utf-8")
    payloads = json.loads(raw)  # must be valid JSON

    sensitive_keys = {"apikey", "api_key", "token", "secret", "password"}
    for name in fixture_names:
        payload = payloads[name]
        assert isinstance(payload, dict), name
        assert "event" in payload, name
        assert "instance" in payload, name
        assert payload["instance"] == "demo", name
        # Fixtures must not embed credentials, at any nesting level.
        assert not (sensitive_keys & _all_keys(payload)), name


def _all_keys(node: object) -> set[str]:
    """Collect every dictionary key in a nested structure."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key).lower())
            found |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= _all_keys(item)
    return found


# --------------------------------------------------------------------------
# Parser: Evolution v2 envelope
# --------------------------------------------------------------------------


def test_parse_text_message_extracts_sender_text_and_metadata() -> None:
    incoming = parse_webhook(A_TEXT)

    assert incoming is not None
    assert incoming.sender == "555599000001"
    assert incoming.text == "Привет"
    assert incoming.message_id == "3EB0A1B2C3D4E5F6000001"
    assert incoming.event == "messages.upsert"
    assert incoming.instance == "demo"
    assert incoming.chat_id == "555599000001@s.whatsapp.net"
    assert incoming.is_from_me is False
    assert incoming.is_group is False
    assert incoming.has_sender is True


def test_parse_strips_whatsapp_net_suffix() -> None:
    incoming = parse_webhook(A_TEXT)

    assert incoming is not None
    assert incoming.chat_id is not None
    assert incoming.chat_id.endswith("@s.whatsapp.net")
    assert incoming.sender == "555599000001"
    assert "@" not in (incoming.sender or "")


def test_parse_nested_extended_text_message() -> None:
    incoming = parse_webhook(B_NESTED)

    assert incoming is not None
    assert incoming.text == "help"
    assert incoming.sender == "555599000002"


def test_parse_unknown_event_is_ignored() -> None:
    assert parse_webhook(C_UNKNOWN_EVENT) is None


def test_parse_status_event_does_not_leak_into_generic_walker() -> None:
    """An Evolution status event must not be mistaken for a chat message."""
    payload = {
        "event": "connection.update",
        "instance": "demo",
        "data": {"state": "open", "message": "Connected"},
    }

    assert parse_webhook(payload) is None


def test_parse_messages_upsert_without_text_is_none() -> None:
    payload = {
        "event": "messages.upsert",
        "instance": "demo",
        "data": {
            "key": {"remoteJid": "555599000001@s.whatsapp.net", "fromMe": False},
            "message": {"imageMessage": {"url": "https://example.invalid/i.jpg"}},
        },
    }

    assert parse_webhook(payload) is None


def test_parse_empty_message_body_is_none() -> None:
    assert parse_webhook(G_EMPTY) is None


def test_parse_from_me_flag_is_detected() -> None:
    incoming = parse_webhook(E_FROM_ME)

    assert incoming is not None
    assert incoming.is_from_me is True
    assert incoming.text == "Привет"


def test_parse_group_message_uses_participant_as_sender() -> None:
    incoming = parse_webhook(F_GROUP)

    assert incoming is not None
    assert incoming.is_group is True
    assert incoming.chat_id == "555599998888-1600000000@g.us"
    # The person who wrote, not the room.
    assert incoming.sender == "555599000005"
    assert incoming.text == "помощь"


def test_parse_group_without_participant_falls_back_to_room() -> None:
    payload = {
        "event": "messages.upsert",
        "instance": "demo",
        "data": {
            "key": {"remoteJid": "555599998888-1600000000@g.us", "fromMe": False},
            "message": {"conversation": "привет"},
        },
    }

    incoming = parse_webhook(payload)

    assert incoming is not None
    assert incoming.is_group is True
    assert incoming.sender == "555599998888-1600000000"


def test_parse_message_without_sender_yields_missing_sender() -> None:
    incoming = parse_webhook(H_NO_SENDER)

    # Text is readable, but no sender could be determined.
    assert incoming is not None
    assert incoming.text == "привет"
    assert incoming.has_sender is False


def test_parse_uppercase_event_name() -> None:
    incoming = parse_webhook(I_UPPER)

    assert incoming is not None
    assert incoming.text == "hello"


def test_parse_data_as_single_item_list() -> None:
    incoming = parse_webhook(J_DATA_LIST)

    assert incoming is not None
    assert incoming.text == "часы"
    assert incoming.sender == "555599000009"


def test_parse_flat_payload_still_works() -> None:
    incoming = parse_webhook(FLAT_PAYLOAD)

    assert incoming is not None
    assert incoming.sender == "555599000001"
    assert incoming.text == "help"


@pytest.mark.parametrize(
    "payload",
    [None, {}, [], "", 42, {"data": None}, {"a": {"b": {"c": [None, 1]}}}, True],
)
def test_parse_never_raises(payload: object) -> None:
    parse_webhook(payload)  # must not raise


def test_parse_deeply_nested_payload_is_bounded() -> None:
    node: dict = {"conversation": "deep"}
    for _ in range(60):
        node = {"nested": node}

    parse_webhook(node)  # must terminate without raising


# --------------------------------------------------------------------------
# /webhook endpoint behaviour
# --------------------------------------------------------------------------


def test_webhook_handles_messages_upsert() -> None:
    with _app() as client:
        response = client.post("/webhook", json=A_TEXT)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["intent"] == "greeting"
    assert body["sender"] == "555599000001"
    assert body["message_text"] == "Привет"
    assert body["event"] == "messages.upsert"
    assert body["instance"] == "demo"
    assert body["from_me"] is False
    assert body["reply_prepared"] is True
    assert body["reply_sent"] is False
    assert "Здравствуйте" in body["reply"]


def test_webhook_detects_help_intent_from_nested_message() -> None:
    with _app() as client:
        response = client.post("/webhook", json=B_NESTED)

    body = response.json()
    assert body["intent"] == "help"
    assert body["message_text"] == "help"


def test_webhook_ignores_unknown_event() -> None:
    with _app() as client:
        response = client.post("/webhook", json=C_UNKNOWN_EVENT)

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_ignores_malformed_payload() -> None:
    with _app() as client:
        response = client.post("/webhook", json=D_MALFORMED)

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_ignores_empty_message() -> None:
    with _app() as client:
        response = client.post("/webhook", json=G_EMPTY)

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_handles_group_message() -> None:
    with _app() as client:
        response = client.post("/webhook", json=F_GROUP)

    body = response.json()
    assert body["status"] == "ok"
    assert body["is_group"] is True
    assert body["sender"] == "555599000005"
    assert body["intent"] == "help"


def test_webhook_handles_missing_sender_without_crashing() -> None:
    with _app() as client:
        response = client.post("/webhook", json=H_NO_SENDER)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["sender"] is None
    assert body["reply_prepared"] is True
    assert body["reply_sent"] is False


def test_webhook_handles_empty_payload() -> None:
    with _app() as client:
        response = client.post("/webhook", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_handles_list_payload() -> None:
    with _app() as client:
        response = client.post("/webhook", json=[1, 2, 3])

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_handles_invalid_json_body() -> None:
    with _app() as client:
        response = client.post(
            "/webhook",
            content=b"not-json-at-all{{{",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_handles_non_json_content_type() -> None:
    with _app() as client:
        response = client.post("/webhook", content=b"plain text body")

    assert response.status_code == 200


def test_webhook_falls_back_for_unknown_text() -> None:
    payload = {"from": "555599000001", "text": "совершенно непонятный запрос"}

    with _app() as client:
        response = client.post("/webhook", json=payload)

    body = response.json()
    assert body["intent"] == "fallback"
    assert "помощь" in body["reply"]


# --------------------------------------------------------------------------
# Loop prevention: never answer our own outgoing messages
# --------------------------------------------------------------------------


def _recording_client(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Install an Evolution client that records outbound calls."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "body": request.content.decode()})
        return httpx.Response(201, json={"key": {"id": "OUT"}})

    real_cls = main_module.EvolutionAPIClient
    monkeypatch.setattr(
        main_module,
        "EvolutionAPIClient",
        lambda s: real_cls(s, transport=httpx.MockTransport(handler)),
    )
    return calls


def test_webhook_does_not_reply_to_own_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fromMe=true must be ignored, and no outbound message may be sent."""
    settings = Settings(
        evolution_api_url="https://evolution.invalid",
        evolution_api_key="test-key-not-a-real-secret",
        evolution_instance="demo",
    )
    calls = _recording_client(monkeypatch)

    with TestClient(main_module.create_app(settings)) as client:
        response = client.post("/webhook", json=E_FROM_ME)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ignored"
    assert body["from_me"] is True
    assert body["reply_prepared"] is False
    # Decisive: the bot must not have called the Evolution API at all.
    assert calls == []


def test_webhook_replies_to_incoming_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counterpart to the loop test: a genuine incoming message is answered."""
    settings = Settings(
        evolution_api_url="https://evolution.invalid",
        evolution_api_key="test-key-not-a-real-secret",
        evolution_instance="demo",
    )
    calls = _recording_client(monkeypatch)

    with TestClient(main_module.create_app(settings)) as client:
        response = client.post("/webhook", json=A_TEXT)

    body = response.json()
    assert body["status"] == "ok"
    assert body["reply_sent"] is True
    assert len(calls) == 1
    assert "message/sendText/demo" in calls[0]["url"]
    assert "test-key-not-a-real-secret" not in calls[0]["url"]
    assert "test-key-not-a-real-secret" not in calls[0]["body"]


def test_webhook_from_me_inside_generic_payload_is_ignored() -> None:
    """fromMe must also be honoured for non-Evolution payload shapes."""
    payload = {
        "from": "555599000001",
        "text": "Привет",
        "key": {"fromMe": True},
    }

    with _app() as client:
        response = client.post("/webhook", json=payload)

    assert response.json()["status"] == "ignored"


def test_webhook_from_me_string_true_is_ignored() -> None:
    """A stringified 'true' must still count as fromMe."""
    payload = {
        "event": "messages.upsert",
        "instance": "demo",
        "data": {
            "key": {"remoteJid": "555599000001@s.whatsapp.net", "fromMe": "true"},
            "message": {"conversation": "Привет"},
        },
    }

    with _app() as client:
        response = client.post("/webhook", json=payload)

    assert response.json()["status"] == "ignored"


# --------------------------------------------------------------------------
# Webhook authentication (optional, off by default)
# --------------------------------------------------------------------------

SECRET = "test-only-shared-secret-not-real"


def _secured_app() -> TestClient:
    return TestClient(create_app(_settings(webhook_secret=SECRET)))


def test_webhook_auth_disabled_by_default() -> None:
    with _app() as client:
        response = client.post("/webhook", json=A_TEXT)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_auth_accepts_correct_secret() -> None:
    with _secured_app() as client:
        response = client.post(
            "/webhook", json=A_TEXT, headers={WEBHOOK_SECRET_HEADER: SECRET}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_auth_rejects_missing_secret() -> None:
    with _secured_app() as client:
        response = client.post("/webhook", json=A_TEXT)

    assert response.status_code == 401
    body = response.json()
    assert body["status"] == "unauthorized"
    assert WEBHOOK_SECRET_HEADER in body["detail"]
    assert SECRET not in response.text


def test_webhook_auth_rejects_wrong_secret() -> None:
    with _secured_app() as client:
        response = client.post(
            "/webhook", json=A_TEXT, headers={WEBHOOK_SECRET_HEADER: "wrong-secret"}
        )

    assert response.status_code == 401
    assert response.json()["status"] == "unauthorized"


def test_webhook_auth_rejects_empty_secret_header() -> None:
    with _secured_app() as client:
        response = client.post(
            "/webhook", json=A_TEXT, headers={WEBHOOK_SECRET_HEADER: ""}
        )

    assert response.status_code == 401


def test_webhook_auth_secret_never_reaches_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        with _secured_app() as client:
            client.post(
                "/webhook", json=A_TEXT, headers={WEBHOOK_SECRET_HEADER: "wrong-secret"}
            )
            client.post(
                "/webhook", json=A_TEXT, headers={WEBHOOK_SECRET_HEADER: SECRET}
            )

    assert SECRET not in caplog.text
    assert "wrong-secret" not in caplog.text


def test_config_endpoint_masks_webhook_secret() -> None:
    with _secured_app() as client:
        response = client.get("/config")

    body = response.json()
    assert response.status_code == 200
    assert body["webhook_auth_enabled"] is True
    assert body["settings"]["webhook_secret"] == "***"
    assert SECRET not in response.text


def test_config_endpoint_reports_auth_disabled() -> None:
    with _app() as client:
        response = client.get("/config")

    body = response.json()
    assert body["webhook_auth_enabled"] is False
    assert body["settings"]["webhook_secret"] == ""


# --------------------------------------------------------------------------
# Instance allowlist (optional)
# --------------------------------------------------------------------------


def test_instance_allowlist_accepts_configured_instance() -> None:
    with _app(webhook_allowed_instances="demo") as client:
        response = client.post("/webhook", json=A_TEXT)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_instance_allowlist_rejects_other_instance() -> None:
    with _app(webhook_allowed_instances="other-instance") as client:
        response = client.post("/webhook", json=A_TEXT)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ignored"
    assert body["reply_prepared"] is False


def test_instance_allowlist_parses_and_trims() -> None:
    settings = Settings(webhook_allowed_instances=" demo , other ,, ")

    assert settings.allowed_instances == ("demo", "other")


# --------------------------------------------------------------------------
# Outbound delivery failure handling
# --------------------------------------------------------------------------


def test_webhook_survives_evolution_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    settings = Settings(
        evolution_api_url="https://evolution.invalid",
        evolution_api_key="test-key-not-a-real-secret",
        evolution_instance="demo",
    )

    real_cls = main_module.EvolutionAPIClient
    monkeypatch.setattr(
        main_module,
        "EvolutionAPIClient",
        lambda s: real_cls(s, transport=httpx.MockTransport(handler)),
    )

    with TestClient(main_module.create_app(settings)) as client:
        response = client.post("/webhook", json=A_TEXT)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["reply_sent"] is False


def test_evolution_status_endpoint_without_configuration() -> None:
    with _app() as client:
        response = client.get("/evolution/status")

    body = response.json()
    assert response.status_code == 200
    assert body["reachable"] is False
    assert "not configured" in body["detail"]

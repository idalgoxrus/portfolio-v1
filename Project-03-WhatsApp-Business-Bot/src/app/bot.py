"""Bot logic.

Pure text-in / text-out logic. This module knows nothing about FastAPI, HTTP
or the Evolution API, so it can be unit tested in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

GREETING_REPLY = "Здравствуйте! 👋 Это демонстрационный WhatsApp Business Bot."

HELP_REPLY = (
    "Демонстрационный бот понимает несколько простых команд:\n"
    "• *привет* — приветствие\n"
    "• *помощь* — список команд\n"
    "• *часы* — часы работы\n"
    "• *контакты* — как с нами связаться\n"
    "Напишите одно из слов выше, чтобы проверить сценарий."
)

HOURS_REPLY = (
    "Мы работаем по будням с 09:00 до 18:00. "
    "Сообщения, отправленные вне этих часов, обрабатываются автоматически. ⏰"
)

CONTACTS_REPLY = (
    "Связаться с оператором: напишите слово «оператор», "
    "или позвоните по номеру +7 (000) 000-00-00. ☎️"
)

FALLBACK_REPLY = (
    "Извините, я пока не понимаю это сообщение. 🤔\n"
    "Напишите «помощь», чтобы увидеть доступные команды."
)


class Intent(str, Enum):
    """Intents the demo bot recognises."""

    GREETING = "greeting"
    HELP = "help"
    HOURS = "hours"
    CONTACTS = "contacts"
    FALLBACK = "fallback"


_INTENT_KEYWORDS: tuple[tuple[Intent, frozenset[str]], ...] = (
    (
        Intent.GREETING,
        frozenset(
            {
                "привет",
                "приветствую",
                "здравствуйте",
                "здравствуй",
                "добрый день",
                "добрый вечер",
                "доброе утро",
                "hello",
                "hi",
                "hey",
                "start",
            }
        ),
    ),
    (
        Intent.HELP,
        frozenset({"help", "помощь", "помогите", "команды", "меню", "menu"}),
    ),
    (
        Intent.HOURS,
        frozenset({"часы", "график", "время работы", "hours"}),
    ),
    (
        Intent.CONTACTS,
        frozenset({"контакты", "контакт", "связь", "оператор", "contacts"}),
    ),
)

_REPLIES: dict[Intent, str] = {
    Intent.GREETING: GREETING_REPLY,
    Intent.HELP: HELP_REPLY,
    Intent.HOURS: HOURS_REPLY,
    Intent.CONTACTS: CONTACTS_REPLY,
    Intent.FALLBACK: FALLBACK_REPLY,
}

_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize(text: str | None) -> str:
    """Lowercase and strip punctuation, emoji and extra whitespace."""
    if not text:
        return ""
    cleaned = _NON_WORD.sub(" ", str(text).lower())
    return " ".join(cleaned.split())


def detect_intent(text: str | None) -> Intent:
    """Classify an incoming message into one of the demo intents."""
    normalized = normalize(text)
    if not normalized:
        return Intent.FALLBACK

    for intent, keywords in _INTENT_KEYWORDS:
        if normalized in keywords:
            return intent

    tokens = set(normalized.split())
    for intent, keywords in _INTENT_KEYWORDS:
        for keyword in keywords:
            if (" " in keyword and keyword in normalized) or keyword in tokens:
                return intent

    return Intent.FALLBACK


@dataclass(frozen=True)
class BotResponse:
    """A reply prepared by the bot."""

    text: str
    intent: Intent


def build_response(text: str | None) -> BotResponse:
    """Build the reply for an incoming message."""
    intent = detect_intent(text)
    return BotResponse(text=_REPLIES[intent], intent=intent)


def build_reply(text: str | None) -> str:
    """Convenience helper returning only the reply text."""
    return build_response(text).text

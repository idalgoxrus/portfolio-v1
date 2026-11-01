"""Tests for the framework-free bot logic."""

from __future__ import annotations

import pytest

from app.bot import (
    FALLBACK_REPLY,
    GREETING_REPLY,
    HELP_REPLY,
    Intent,
    build_reply,
    build_response,
    detect_intent,
    normalize,
)


@pytest.mark.parametrize(
    "message",
    ["Привет", "привет", "ПРИВЕТ", "  Привет!  ", "Здравствуйте", "hello", "hi"],
)
def test_greeting_is_recognised(message: str) -> None:
    response = build_response(message)

    assert response.intent is Intent.GREETING
    assert response.text == GREETING_REPLY


@pytest.mark.parametrize("message", ["help", "Help", "помощь", "Помощь!", "меню"])
def test_help_is_recognised(message: str) -> None:
    response = build_response(message)

    assert response.intent is Intent.HELP
    assert response.text == HELP_REPLY


@pytest.mark.parametrize("message", ["часы", "график", "время работы"])
def test_hours_is_recognised(message: str) -> None:
    assert detect_intent(message) is Intent.HOURS


@pytest.mark.parametrize("message", ["контакты", "оператор", "связь"])
def test_contacts_is_recognised(message: str) -> None:
    assert detect_intent(message) is Intent.CONTACTS


@pytest.mark.parametrize(
    "message",
    ["какой-то неизвестный текст", "1234567890", "aHR0cHM6Ly8="],
)
def test_unknown_message_falls_back(message: str) -> None:
    response = build_response(message)

    assert response.intent is Intent.FALLBACK
    assert response.text == FALLBACK_REPLY


@pytest.mark.parametrize("message", [None, "", "   ", "!!!", "🙂"])
def test_empty_or_punctuation_only_falls_back(message: str | None) -> None:
    assert detect_intent(message) is Intent.FALLBACK


def test_normalize_strips_punctuation_and_lowercases() -> None:
    assert normalize("  Привет!!!  Мир? ") == "привет мир"
    assert normalize(None) == ""


def test_build_reply_matches_build_response() -> None:
    assert build_reply("Привет") == build_response("Привет").text


def test_bot_logic_has_no_web_framework_imports() -> None:
    """Bot logic must stay decoupled from the HTTP layer."""
    import ast
    from pathlib import Path

    import app.bot as bot_module

    tree = ast.parse(Path(bot_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"fastapi", "httpx", "starlette", "app"})

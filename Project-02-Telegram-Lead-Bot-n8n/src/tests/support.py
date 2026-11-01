"""Общие тестовые двойники и помощники (без обработки логики приложения).

RecordingSession подменяет только транспорт Telegram — это граница системы,
поэтому вся логика aiogram, FSM и наших обработчиков исполняется по-настоящему.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, BinaryIO

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, User

FAKE_TOKEN = "123456789:" + "A" * 35
USER_ID = 777

# Теги, которые Telegram принимает при parse_mode=HTML.
TELEGRAM_TAGS = frozenset(
    {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "blockquote", "span"}
)


class RecordingSession(BaseSession):
    """Session-заглушка: запоминает исходящие сообщения вместо вызовов Bot API."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[SendMessage] = []
        self._message_id = 100

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if isinstance(method, SendMessage):
            self.sent.append(method)
            self._message_id += 1
            return Message(
                message_id=self._message_id,
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if isinstance(method, GetMe):
            return User(id=USER_ID, is_bot=True, first_name="TestBot", username="test_bot")
        raise AssertionError(f"неожиданный вызов Telegram API: {type(method).__name__}")

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncIterator[BinaryIO]:
        raise NotImplementedError("загрузка файлов не используется")
        yield  # pragma: no cover

    async def close(self) -> None:
        return None

    def texts(self) -> list[str]:
        return [m.text for m in self.sent if m.text]

    def last_text(self) -> str:
        assert self.sent, "бот не отправил ни одного сообщения"
        return self.sent[-1].text or ""


class _HtmlChecker(HTMLParser):
    """Проверяет, что текст — корректный HTML, допустимый в Telegram."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in TELEGRAM_TAGS:
            self.errors.append(f"неизвестный тег <{tag}>")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"непарный закрывающий тег </{tag}>")
            return
        self.stack.pop()


def assert_telegram_html(text: str) -> None:
    """Проверить, что сообщение — валидный с точки зрения Telegram HTML без лишних тегов."""
    checker = _HtmlChecker()
    checker.feed(text)
    checker.close()
    assert not checker.errors, f"некорректный HTML: {checker.errors}; текст={text!r}"
    assert not checker.stack, f"незакрытые теги {checker.stack}; текст={text!r}"

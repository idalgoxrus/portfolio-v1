"""Тесты отказоустойчивости обработки исключений в сервисе и обработчике.

Проверяют поведение при ошибках, которые НЕ являются N8nDeliveryError:
неожиданный сбой интеграции или ошибка хранилища не должны оставлять лид
навсегда в статусе new и не должны «проглатываться» без ответа пользователю.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from app.bot.keyboards import BTN_CONFIRM, BTN_SKIP
from app.models.lead import Lead, LeadStatus
from app.services.lead_service import LeadService
from app.storage.repository import LeadRepository

CHAT_ID = 555
USER_ID = 777


class ExplodingN8nClient:
    """Клиент, падающий не-HTTP исключением (имитация неожиданного сбоя)."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def send_lead(self, lead: Lead) -> bool:
        self.calls += 1
        raise self.error


class FailingStatusRepository(LeadRepository):
    """Репозиторий, у которого падает обновление статуса (имитация сбоя SQLite)."""

    def set_status(self, lead_id: int, status: LeadStatus) -> None:
        raise OSError("disk I/O error")


def _lead() -> Lead:
    return Lead(telegram_id=42, full_name="Вадим", phone="+79991234567")


async def test_unexpected_client_error_does_not_leave_lead_in_new(tmp_path: Path) -> None:
    """Любой сбой доставки должен давать терминальный статус, а не «зависший» new."""
    repo = LeadRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    service = LeadService(repository=repo, n8n_client=ExplodingN8nClient(RuntimeError("boom")))  # type: ignore[arg-type]

    await service.register_lead(_lead())

    statuses = [row["status"] for row in repo.list_recent()]
    assert statuses == [LeadStatus.FAILED.value], f"лид завис в статусе: {statuses}"


async def test_storage_error_propagates_but_row_is_traceable(tmp_path: Path) -> None:
    """Сбой записи статуса не должен терять уже сохранённую заявку.

    Даже когда обновление статуса падает, строка лида уже закоммичена на шаге
    add_lead — заявку можно разобрать вручную и не потерять.
    """
    repo = FailingStatusRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    service = LeadService(repository=repo, n8n_client=ExplodingN8nClient(RuntimeError("x")))  # type: ignore[arg-type]

    with pytest.raises(OSError):
        await service.register_lead(_lead())

    assert repo.count() == 1, "заявка должна остаться в БД для ручного разбора"


def _incoming(text: str, *, message_id: int) -> Update:
    return Update(
        update_id=message_id,
        message=Message(
            message_id=message_id,
            date=datetime.now(UTC),
            chat=Chat(id=CHAT_ID, type="private"),
            from_user=User(id=USER_ID, is_bot=False, first_name="Client", username="client"),
            text=text,
        ),
    )


async def _send(dispatcher: Dispatcher, bot: Bot, text: str, *, message_id: int) -> None:
    await dispatcher.feed_update(bot, _incoming(text, message_id=message_id))


async def test_confirm_survives_storage_failure_and_replies(
    dispatcher: Dispatcher, bot: Bot, session, repository: LeadRepository
) -> None:
    """Сбой хранилища при подтверждении: пользователь получает ответ, бот не падает."""
    broken = FailingStatusRepository(repository.db_path)
    broken.init_schema()
    dispatcher.workflow_data["lead_service"] = LeadService(
        repository=broken, n8n_client=ExplodingN8nClient(RuntimeError("boom"))  # type: ignore[arg-type]
    )

    await _send(dispatcher, bot, "/start", message_id=1)
    await _send(dispatcher, bot, "Вадим", message_id=2)
    await _send(dispatcher, bot, "+79991234567", message_id=3)
    await _send(dispatcher, bot, BTN_SKIP, message_id=4)
    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)

    assert session.last_text(), "пользователь остался без ответа"
    assert "заявк" in session.last_text().lower()

"""Тесты надёжности FSM/обработчиков: незаполненные поля, отмена, повторный /start.

Транспорт Telegram подменяется RecordingSession (tests.support). Логика aiogram,
FSM и наших обработчиков исполняется по-настоящему, БД — реальный SQLite.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Contact, Message, Update, User

from app.bot.keyboards import BTN_CANCEL, BTN_CONFIRM, BTN_PHONE, BTN_SKIP
from app.bot.states import LeadForm
from app.models.lead import LeadStatus
from app.services.lead_service import LeadService
from app.services.n8n_client import N8nClient
from app.storage.repository import LeadRepository
from tests.support import RecordingSession, assert_telegram_html

CHAT_ID = 555
USER_ID = 777


@pytest.fixture(autouse=True)
def _bind_state(dispatcher: Dispatcher, repository: LeadRepository) -> None:
    dispatcher.fsm.storage = MemoryStorage()
    dispatcher.workflow_data["lead_service"] = LeadService(
        repository=repository, n8n_client=N8nClient(webhook_url=None)
    )


def _incoming(text: str | None = None, *, message_id: int = 1, contact: Contact | None = None) -> Update:
    return Update(
        update_id=message_id,
        message=Message(
            message_id=message_id,
            date=datetime.now(UTC),
            chat=Chat(id=CHAT_ID, type="private"),
            from_user=User(id=USER_ID, is_bot=False, first_name="Client", username="client"),
            text=text,
            contact=contact,
        ),
    )


async def _send(dispatcher: Dispatcher, bot: Bot, text: str, *, message_id: int = 1) -> None:
    await dispatcher.feed_update(bot, _incoming(text, message_id=message_id))


async def _send_contact(dispatcher: Dispatcher, bot: Bot, phone: str, *, message_id: int = 1) -> None:
    contact = Contact(phone_number=phone, first_name="Client", user_id=USER_ID)
    await dispatcher.feed_update(bot, _incoming(contact=contact, message_id=message_id))


async def _end_form(dispatcher: Dispatcher, bot: Bot, *, name: str = "Вадим") -> None:
    """Довести анкету до шага подтверждения."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, name, message_id=2)
    await _send(dispatcher, bot, "+79991234567", message_id=3)
    await _send(dispatcher, bot, BTN_SKIP, message_id=4)


# --- незаполненные поля ---


async def test_whitespace_name_is_rejected(dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
    """Имя из пробелов не проходит шаг 1 и не попадает в БД."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "   ", message_id=2)

    assert "2" in session.last_text(), "ожидалось сообщение о длине имени (от 2 до 120)"


async def test_blank_phone_is_rejected(dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
    """Пустой телефон не пропускается на шаг комментария."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Вадим", message_id=2)
    await _send(dispatcher, bot, "   ", message_id=3)

    assert "телефон" in session.last_text().lower()
    assert "комментарий" not in session.last_text().lower()


async def test_contact_without_phone_number_is_rejected(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Кнопка «поделиться телефоном» без номера не должна создавать лид."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Вадим", message_id=2)
    await _send_contact(dispatcher, bot, "", message_id=3)

    assert "телефон" in session.last_text().lower()
    assert repository.count() == 0


async def test_oversized_comment_is_rejected_and_flow_continues(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Комментарий >1000 символов отклоняется, но сценарий не ломается."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Вадим", message_id=2)
    await _send(dispatcher, bot, "+79991234567", message_id=3)
    await _send(dispatcher, bot, "я" * 1001, message_id=4)

    assert "1000" in session.last_text()
    assert repository.count() == 0

    # после отказа можно корректно завершить ввод
    await _send(dispatcher, bot, "короткий комментарий", message_id=5)
    assert "отправить" in session.last_text().lower()


# --- отмена ---


async def test_cancel_at_confirm_step_discards_lead(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Отмена на финальном шаге не создаёт лид."""
    await _end_form(dispatcher, bot)
    await _send(dispatcher, bot, BTN_CANCEL, message_id=5)

    assert repository.count() == 0


async def test_cancel_command_mid_form_discards_lead(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """/cancel на шаге телефона сбрасывает анкету."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Вадим", message_id=2)
    await _send(dispatcher, bot, "/cancel", message_id=3)

    assert repository.count() == 0
    await _send(dispatcher, bot, "+79991234567", message_id=4)
    assert repository.count() == 0, "после отмены ввод не должен продолжаться"


async def test_cancel_is_safe_without_active_form(dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
    """Отмена вне анкеты не должна приводить к ошибке."""
    await _send(dispatcher, bot, "/cancel")

    assert "отмен" in session.last_text().lower()


# --- повторный /start ---


async def test_restart_does_not_duplicate_lead(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Повторный /start в середине анкеты перезаписывает данные, а не создаёт лид."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Первый", message_id=2)
    await _send(dispatcher, bot, "/start", message_id=3)
    await _send(dispatcher, bot, "Второй", message_id=4)
    await _send(dispatcher, bot, "+79990000000", message_id=5)
    await _send(dispatcher, bot, BTN_SKIP, message_id=6)
    await _send(dispatcher, bot, BTN_CONFIRM, message_id=7)

    leads = repository.list_recent()
    assert len(leads) == 1
    assert leads[0]["full_name"] == "Второй"


async def test_two_full_leads_create_two_rows(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Две отдельные заявки подряд создают две записи с корректными статусами."""
    await _end_form(dispatcher, bot, name="Первый")
    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)
    await _end_form(dispatcher, bot, name="Второй")
    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)

    assert repository.count() == 2
    assert repository.count(LeadStatus.FAILED) == 2, "webhook не настроен → failed"


async def test_confirm_with_empty_state_does_not_crash(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Подтверждение без начатой анкеты не должно приводить к исключению."""
    await _send(dispatcher, bot, BTN_CONFIRM)

    assert repository.count() == 0
    assert session.last_text(), "бот должен ответить пользователю"


# --- защита HTML ---


async def test_all_preview_fields_are_escaped(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Спецсимволы HTML экранируются в полях предпросмотра (имя, телефон, комментарий)."""
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "<b>Имя</b> & <i>ещё</i>", message_id=2)
    await _send(dispatcher, bot, "+79<script>", message_id=3)

    assert "телефон" in session.last_text().lower(), "некорректный телефон должен быть отклонён"

    await _send(dispatcher, bot, "+79991234567", message_id=4)
    await _send(dispatcher, bot, "комментарий <img src=x onerror=alert(1)>", message_id=5)

    preview = session.last_text()
    assert "<b>Имя</b>" not in preview
    assert "&lt;b&gt;" in preview
    assert "&amp;" in preview
    assert "<img" not in preview
    assert_telegram_html(preview)


async def test_fallback_message_is_plain_text(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession
) -> None:
    await _send(dispatcher, bot, "<script>&")

    assert_telegram_html(session.last_text())


async def test_username_with_html_is_stored_raw_but_not_rendered(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Спецсимволы в имени уходят в БД как есть, а в сообщениях не рендерятся тегами."""
    await _end_form(dispatcher, bot, name="<script>alert(1)</script>")
    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)

    lead = repository.list_recent()[0]
    assert lead["full_name"] == "<script>alert(1)</script>"
    for text in session.texts():
        assert_telegram_html(text)


async def test_confirmation_message_is_escaped(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession
) -> None:
    await _end_form(dispatcher, bot, name="<b>Жертва</b>")
    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)

    for text in session.texts():
        assert_telegram_html(text)


# --- статические инварианты ---


def test_every_injected_handler_dependency_is_bound(dispatcher: Dispatcher) -> None:
    """Каждая зависимость обработчиков реально положена в workflow_data."""
    injected = set(dispatcher.workflow_data)
    handlers = [h.callback for router in dispatcher.sub_routers for h in router.message.handlers]
    needed = {
        name
        for callback in handlers
        for name, param in inspect.signature(callback, eval_str=True).parameters.items()
        if param.annotation in {LeadService, Bot, Dispatcher}
    }

    assert needed <= injected, f"нет в workflow_data: {needed - injected}"


def test_fsm_states_cover_full_form() -> None:
    """Набор состояний FSM покрывает весь сценарий анкеты."""
    assert {s.state for s in LeadForm.__states__} == {
        "LeadForm:full_name",
        "LeadForm:phone",
        "LeadForm:comment",
        "LeadForm:confirm",
    }


def test_buttons_are_distinct_and_non_empty() -> None:
    assert len({BTN_CANCEL, BTN_SKIP, BTN_CONFIRM, BTN_PHONE}) == 4
    assert all(btn.strip() for btn in (BTN_CANCEL, BTN_SKIP, BTN_CONFIRM, BTN_PHONE))

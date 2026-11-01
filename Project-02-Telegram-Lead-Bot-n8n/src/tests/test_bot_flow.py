"""Интеграционный тест FSM-анкеты: реальный Dispatcher + поддельная сессия Bot.

Телеграм не опрашивается: Bot получает RecordingSession (tests.support), которая
перехватывает исходящие методы API и возвращает синтетические ответы. Сеть не
используется, n8n не вызывается (webhook не настроен), реальный токен не нужен.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User

from app.bot.keyboards import BTN_CANCEL, BTN_CONFIRM, BTN_SKIP
from app.models.lead import LeadStatus
from app.services.lead_service import LeadService
from app.services.n8n_client import N8nClient
from app.storage.repository import LeadRepository
from tests.support import RecordingSession, assert_telegram_html

CHAT_ID = 555
USER_ID = 777


@pytest.fixture(autouse=True)
def _bind_state(dispatcher: Dispatcher, repository: LeadRepository) -> None:
    """Свой сервис и своё FSM-хранилище на каждый тест."""
    dispatcher.fsm.storage = MemoryStorage()
    dispatcher.workflow_data["lead_service"] = LeadService(
        repository=repository, n8n_client=N8nClient(webhook_url=None)
    )


def _incoming(text: str, *, message_id: int = 1) -> Update:
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


async def _send(dispatcher: Dispatcher, bot: Bot, text: str, *, message_id: int = 1) -> None:
    await dispatcher.feed_update(bot, _incoming(text, message_id=message_id))


async def test_full_form_flow_escapes_user_input(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    """Полный проход анкеты: шаги, экранирование HTML и сохранение лида."""
    await _send(dispatcher, bot, "/start")
    assert "Как вас зовут" in session.last_text()

    await _send(dispatcher, bot, "Иван", message_id=2)
    assert "телефон" in session.last_text().lower()

    # Символы «<» и «&» приходят от пользователя и не должны ломать HTML.
    await _send(dispatcher, bot, "8 999 123-45-67", message_id=3)
    assert "Комментарий" in session.last_text()

    await _send(dispatcher, bot, "нужен <script>alert(1)</script> & срочно", message_id=4)
    preview = session.last_text()
    assert "Проверьте заявку" in preview
    assert "&lt;script&gt;" in preview
    assert "<script>" not in preview
    assert_telegram_html(preview)

    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)

    leads = repository.list_recent()
    assert len(leads) == 1
    assert leads[0]["phone"] == "+89991234567"
    assert leads[0]["full_name"] == "Иван"
    # webhook не настроен → лид сохранён со статусом failed, но не потерян
    assert leads[0]["status"] == LeadStatus.FAILED.value
    assert f"№{leads[0]['id']}" in session.last_text()

    for text in session.texts():
        assert_telegram_html(text)


async def test_invalid_phone_keeps_phone_step(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Иван", message_id=2)
    await _send(dispatcher, bot, "не телефон", message_id=3)

    assert "Не похоже на телефон" in session.last_text()

    # Шаг не сдвинулся: корректный телефон по-прежнему принимается.
    await _send(dispatcher, bot, "+79991234567", message_id=4)
    assert "Комментарий" in session.last_text()
    assert repository.list_recent() == []


async def test_too_short_name_is_rejected(dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Я", message_id=2)

    assert "от 2 до 120" in session.last_text()


async def test_comment_can_be_skipped(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Иван", message_id=2)
    await _send(dispatcher, bot, "+79991234567", message_id=3)
    await _send(dispatcher, bot, BTN_SKIP, message_id=4)

    await _send(dispatcher, bot, BTN_CONFIRM, message_id=5)

    leads = repository.list_recent()
    assert len(leads) == 1
    assert leads[0]["comment"] is None


async def test_cancel_button_resets_flow(
    dispatcher: Dispatcher, bot: Bot, session: RecordingSession, repository: LeadRepository
) -> None:
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, BTN_CANCEL, message_id=2)

    assert "отменено" in session.last_text().lower()

    # Состояние сброшено: обычный текст идёт в fallback, а не в анкету.
    await _send(dispatcher, bot, "Иван", message_id=3)
    assert "понимаю только шаги анкеты" in session.last_text()
    assert repository.list_recent() == []


async def test_help_and_fallback(dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
    await _send(dispatcher, bot, "/help")
    assert "/start" in session.last_text()

    await _send(dispatcher, bot, "случайный текст", message_id=2)
    assert "понимаю только шаги анкеты" in session.last_text()


async def test_start_twice_restarts_form(dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
    await _send(dispatcher, bot, "/start")
    await _send(dispatcher, bot, "Иван", message_id=2)
    await _send(dispatcher, bot, "/start", message_id=3)

    assert "Как вас зовут" in session.last_text()


def test_confirm_handler_dependency_matches_injected_name(dispatcher: Dispatcher) -> None:
    """Имя зависимости в обработчике должно совпадать с ключом workflow_data.

    aiogram подставляет зависимости по имени аргумента, поэтому переименование
    `lead_service` в обработчике тихо сломает DI на этапе запуска.
    """
    injected = set(dispatcher.workflow_data)
    handlers = [h.callback for router in dispatcher.sub_routers for h in router.message.handlers]

    service_params = {
        name
        # eval_str нужен, потому что в модулях включён `from __future__ import annotations`
        for callback in handlers
        for name, param in inspect.signature(callback, eval_str=True).parameters.items()
        if param.annotation is LeadService
    }

    assert service_params, "ни один обработчик не принимает LeadService"
    assert service_params <= injected, f"нет в workflow_data: {service_params - injected}"

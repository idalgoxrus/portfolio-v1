"""Обработчики Telegram: пошаговый сбор лида через FSM.

Порядок регистрации важен: командные обработчики идут первыми,
финальный fallback — последним.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pydantic import ValidationError

from app.bot.keyboards import (
    BTN_CANCEL,
    BTN_CONFIRM,
    BTN_SKIP,
    confirm_keyboard,
    phone_keyboard,
    remove_keyboard,
    skip_keyboard,
)
from app.bot.states import LeadForm
from app.models.lead import Lead, LeadStatus
from app.services.lead_service import LeadService

logger = logging.getLogger(__name__)

router = Router(name="lead_flow")

HELP_TEXT = (
    "Я собираю заявки и передаю их менеджеру.\n\n"
    "Команды:\n"
    "/start — оставить заявку\n"
    "/cancel — отменить заполнение\n"
    "/help — эта справка"
)

WELCOME_TEXT = "Здравствуйте! Оформим заявку за 3 шага.\n\nШаг 1 из 3. Как вас зовут?"
PHONE_TEXT = (
    "Шаг 2 из 3. Укажите телефон в формате +79991234567 "
    "или нажмите «Поделиться телефоном»."
)
COMMENT_TEXT = "Шаг 3 из 3. Комментарий к заявке (или «Пропустить»)."
FALLBACK_TEXT = "Я понимаю только шаги анкеты. /start — начать заявку, /help — справка."


def _user_id(message: Message) -> int:
    return message.from_user.id if message.from_user else 0


def _username(message: Message) -> str | None:
    return message.from_user.username if message.from_user else None


async def _cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Заполнение отменено. /start — начать заново.", reply_markup=remove_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Начать сбор заявки."""
    await state.clear()
    await state.set_state(LeadForm.full_name)
    await message.answer(WELCOME_TEXT, reply_markup=remove_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Показать справку."""
    await message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отменить заполнение командой."""
    await _cancel(message, state)


@router.message(F.text == BTN_CANCEL)
async def cancel_button(message: Message, state: FSMContext) -> None:
    """Отменить заполнение кнопкой."""
    await _cancel(message, state)


@router.message(LeadForm.full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    """Шаг 1: имя."""
    full_name = (message.text or "").strip()
    if not 2 <= len(full_name) <= 120:
        await message.answer("Имя должно быть от 2 до 120 символов. Попробуйте ещё раз.")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(LeadForm.phone)
    await message.answer(PHONE_TEXT, reply_markup=phone_keyboard())


@router.message(LeadForm.phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext) -> None:
    """Шаг 2: телефон, полученный кнопкой контакта."""
    phone = message.contact.phone_number if message.contact else ""
    await _accept_phone(message, state, phone)


@router.message(LeadForm.phone, F.text)
async def process_phone_text(message: Message, state: FSMContext) -> None:
    """Шаг 2: телефон, введённый вручную."""
    await _accept_phone(message, state, message.text or "")


async def _accept_phone(message: Message, state: FSMContext, raw_phone: str) -> None:
    """Проверить телефон теми же правилами, что и модель лида."""
    data = await state.get_data()
    try:
        Lead(
            telegram_id=_user_id(message),
            full_name=data.get("full_name") or "Клиент",
            phone=raw_phone,
        )
    except ValidationError:
        await message.answer("Не похоже на телефон. Пример: +79991234567", reply_markup=phone_keyboard())
        return

    await state.update_data(phone=raw_phone)
    await state.set_state(LeadForm.comment)
    await message.answer(COMMENT_TEXT, reply_markup=skip_keyboard())


@router.message(LeadForm.comment, F.text == BTN_SKIP)
async def process_comment_skip(message: Message, state: FSMContext) -> None:
    """Шаг 3: комментарий пропущен."""
    await _accept_comment(message, state, None)


@router.message(LeadForm.comment, F.text)
async def process_comment(message: Message, state: FSMContext) -> None:
    """Шаг 3: комментарий введён."""
    await _accept_comment(message, state, message.text or "")


async def _accept_comment(message: Message, state: FSMContext, comment: str | None) -> None:
    if comment and len(comment) > 1000:
        await message.answer("Комментарий слишком длинный (максимум 1000 символов).")
        return

    await state.update_data(comment=comment)
    data = await state.get_data()
    # aiogram шлёт с parse_mode=HTML, поэтому пользовательские значения экранируются:
    # иначе символ «<» ломает разбор сообщения и пользователь не увидит анкету.
    preview = (
        "Проверьте заявку:\n"
        f"Имя: {escape(str(data.get('full_name') or ''))}\n"
        f"Телефон: {escape(str(data.get('phone') or ''))}\n"
        f"Комментарий: {escape(str(data.get('comment') or '—'))}\n\n"
        "Отправить?"
    )
    await state.set_state(LeadForm.confirm)
    await message.answer(preview, reply_markup=confirm_keyboard())


@router.message(LeadForm.confirm, F.text == BTN_CONFIRM)
async def process_confirm(message: Message, state: FSMContext, lead_service: LeadService) -> None:
    """Финал: собрать модель и передать в сервис."""
    data = await state.get_data()
    await state.clear()

    try:
        lead = Lead(
            telegram_id=_user_id(message),
            full_name=data.get("full_name") or "",
            phone=data.get("phone") or "",
            comment=data.get("comment"),
            username=_username(message),
        )
    except ValidationError as exc:
        logger.warning("Некорректные данные заявки: %s", exc)
        await message.answer("Не удалось собрать заявку. Начните заново: /start", reply_markup=remove_keyboard())
        return

    try:
        _, lead_id, status = await lead_service.register_lead(lead)
    except Exception:
        # Сбой хранилища не должен оставлять пользователя без ответа.
        logger.exception("Не удалось сохранить заявку пользователя %s", _user_id(message))
        await message.answer(
            "Не удалось сохранить заявку. Попробуйте, пожалуйста, позже: /start",
            reply_markup=remove_keyboard(),
        )
        return

    if status is LeadStatus.SENT:
        await message.answer(
            f"Спасибо! Заявка №{lead_id} принята, менеджер свяжется с вами.",
            reply_markup=remove_keyboard(),
        )
    else:
        await message.answer(
            f"Заявка №{lead_id} сохранена, но передача менеджеру задержалась. Мы уже разбираемся.",
            reply_markup=remove_keyboard(),
        )


@router.message()
async def fallback(message: Message) -> None:
    """Любое сообщение вне сценария."""
    await message.answer(FALLBACK_TEXT)

"""Клавиатуры бота. Тексты кнопок вынесены в константы, чтобы фильтры и UI не расходились."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

BTN_CANCEL = "Отмена"
BTN_SKIP = "Пропустить"
BTN_CONFIRM = "Подтвердить"
BTN_PHONE = "Поделиться телефоном"


def phone_keyboard() -> ReplyKeyboardMarkup:
    """Шаг с телефоном: кнопка передачи контакта или ручной ввод."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PHONE, request_contact=True)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    """Шаг с комментарием: можно пропустить."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def confirm_keyboard() -> ReplyKeyboardMarkup:
    """Подтверждение отправки заявки."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CONFIRM)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Убрать reply-клавиатуру."""
    return ReplyKeyboardRemove()

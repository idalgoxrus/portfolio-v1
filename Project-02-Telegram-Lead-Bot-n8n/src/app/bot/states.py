"""Состояния анкеты сбора лида."""

from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    """Пошаговое заполнение заявки."""

    full_name = State()
    phone = State()
    comment = State()
    confirm = State()

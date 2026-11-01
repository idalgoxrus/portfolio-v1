"""Базовая настройка logging для всех точек входа приложения.

Модуль намеренно не зависит от настроек и aiogram: его можно вызывать
в боте, в скриптах и в FastAPI-приложении одинаково.
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Библиотеки, которые в DEBUG засоряют лог собственными сообщениями.
NOISY_LOGGERS = ("httpx", "httpcore", "aiogram.event", "uvicorn.access")

DEFAULT_LEVEL = "INFO"


def resolve_level(level: str | int | None) -> int:
    """Преобразовать уровень в числовой, безопасно откатываясь на INFO."""
    if isinstance(level, int):
        return level
    if not level:
        return logging.INFO
    return getattr(logging, str(level).strip().upper(), logging.INFO)


def configure_logging(level: str | int | None = DEFAULT_LEVEL, *, stream: TextIO | None = None) -> None:
    """Настроить корневой логгер и приглушить шумные библиотеки.

    force=True гарантирует идемпотентность: повторный вызов (тесты, перезапуск
    внутри процесса) не оставляет дублирующих хендлеров.
    """
    logging.basicConfig(
        level=resolve_level(level),
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        stream=stream or sys.stdout,
        force=True,
    )
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Получить именованный логгер."""
    return logging.getLogger(name)

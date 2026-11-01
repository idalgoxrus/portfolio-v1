"""Совместимый реэкспорт: канонический модуль логирования — app.core.logging.

Файл оставлен, чтобы старые импорты `from app.logging_setup import ...`
продолжали работать. Новая функциональность добавляется только в app/core/logging.py.
"""

from app.core.logging import (
    DATE_FORMAT,
    DEFAULT_LEVEL,
    LOG_FORMAT,
    NOISY_LOGGERS,
    configure_logging,
    get_logger,
    resolve_level,
)

__all__ = [
    "DATE_FORMAT",
    "DEFAULT_LEVEL",
    "LOG_FORMAT",
    "NOISY_LOGGERS",
    "configure_logging",
    "get_logger",
    "resolve_level",
]

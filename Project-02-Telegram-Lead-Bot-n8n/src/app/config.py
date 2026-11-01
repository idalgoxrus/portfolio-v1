"""Совместимый реэкспорт: канонический модуль настроек — app.core.config.

Файл оставлен, чтобы старые импорты `from app.config import get_settings`
продолжали работать. Новая функциональность добавляется только в app/core/config.py.
"""

from app.core.config import PROJECT_ROOT, Settings, get_settings, load_settings

__all__ = ["PROJECT_ROOT", "Settings", "get_settings", "load_settings"]

"""Инфраструктурный слой: настройки, логирование, базовые исключения."""

from app.core.config import PROJECT_ROOT, Settings, get_settings, load_settings
from app.core.exceptions import (
    ConfigurationError,
    IntegrationError,
    LeadBotError,
    N8nDeliveryError,
)
from app.core.logging import configure_logging, get_logger, resolve_level

__all__ = [
    "PROJECT_ROOT",
    "ConfigurationError",
    "IntegrationError",
    "LeadBotError",
    "N8nDeliveryError",
    "Settings",
    "configure_logging",
    "get_logger",
    "get_settings",
    "load_settings",
    "resolve_level",
]

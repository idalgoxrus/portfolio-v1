"""Базовые исключения проекта.

Иерархия::

    LeadBotError                 — всё, что может поймать точка входа
    ├── ConfigurationError       — некорректные настройки окружения
    └── IntegrationError         — сбой внешней интеграции
        └── N8nDeliveryError     — n8n webhook не принял данные

Правила:
* исключения проекта наследуются от LeadBotError, а не от generic Exception —
  точку входа можно защитить одним `except LeadBotError`;
* ничего не глотаем молча: сбой интеграции логируется и меняет статус лида на failed;
* сообщения — без секретов (никаких токенов и URL с credentials).
"""

from __future__ import annotations


class LeadBotError(Exception):
    """Базовое исключение проекта."""


class ConfigurationError(LeadBotError):
    """Настройки окружения отсутствуют или некорректны."""


class IntegrationError(LeadBotError):
    """Внешняя интеграция недоступна или ответила ошибкой."""


class N8nDeliveryError(IntegrationError):
    """n8n webhook не принял лид после всех попыток."""

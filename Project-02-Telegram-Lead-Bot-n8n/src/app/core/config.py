"""Безопасная загрузка настроек приложения через pydantic-settings.

Принципы:
* отсутствие файла .env не приводит к падению — у всех параметров есть значения по умолчанию;
* лишние переменные окружения игнорируются (extra="ignore");
* пустые значения необязательных параметров трактуются как «не задано»;
* некорректные значения (битый webhook URL, неизвестный LOG_LEVEL, отрицательный таймаут)
  отклоняются сразу на старте с понятным сообщением;
* секреты не попадают в логи — для вывода используется safe_dump().
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})
DEFAULT_DATABASE_PATH = "data/leads.sqlite3"
SECRET_FIELDS = ("bot_token", "n8n_webhook_secret", "admin_api_token")
MASKED = "***"

# Формат токена Telegram: <числовой id>:<секрет>. Проверяется без обращения к API.
TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")
TOKEN_FORMAT_ERROR = (
    "BOT_TOKEN должен иметь формат <id>:<строка> без пробелов "
    "(например, 123456789:AA... — возьмите токен у @BotFather)"
)


class Settings(BaseSettings):
    """Настройки, прочитанные из окружения и/или файла .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    admin_chat_id: int | None = Field(default=None, alias="ADMIN_CHAT_ID")

    # --- n8n ---
    n8n_webhook_url: str | None = Field(default=None, alias="N8N_WEBHOOK_URL")
    n8n_webhook_secret: str | None = Field(default=None, alias="N8N_WEBHOOK_SECRET")

    # --- HTTP ---
    http_timeout: float = Field(default=10.0, alias="HTTP_TIMEOUT", gt=0, le=120)
    http_retries: int = Field(default=2, alias="HTTP_RETRIES", ge=0, le=10)

    # --- Admin API ---
    # Токен для чтения лидов/отчётов через HTTP. Равен None — доступ открыт
    # (локальная разработка); задан — требуется заголовок X-Admin-Token.
    admin_api_token: str | None = Field(default=None, alias="ADMIN_API_TOKEN")

    # --- Storage / Logging ---
    database_path: Path = Field(default=Path(DEFAULT_DATABASE_PATH), alias="DATABASE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Нормализация входных значений ---

    @field_validator("bot_token", mode="before")
    @classmethod
    def _normalize_token(cls, value: object) -> object:
        """None и пробелы → пустая строка.

        Токен необязателен на уровне модуля: импорт настроек не должен падать
        только из-за того, что разработчик ещё не заполнил .env.
        """
        if value is None:
            return ""
        return value.strip() if isinstance(value, str) else value

    @field_validator("bot_token", mode="after")
    @classmethod
    def _check_token_format(cls, value: str) -> str:
        """Проверить формат токена заранее.

        aiogram падает с TokenValidationError уже при создании Bot, то есть после
        старта polling-цикла. Проверка здесь превращает это в понятную ошибку
        конфигурации до обращения к Telegram API.
        """
        if value and not TOKEN_PATTERN.match(value):
            raise ValueError(TOKEN_FORMAT_ERROR)
        return value

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def _blank_int_to_none(cls, value: object) -> object:
        """Пустая переменная ADMIN_CHAT_ID= не должна ломать валидацию."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("n8n_webhook_url", "n8n_webhook_secret", "admin_api_token", mode="before")
    @classmethod
    def _blank_str_to_none(cls, value: object) -> object:
        """Пустая строка → None («интеграция не настроена»)."""
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("database_path", mode="before")
    @classmethod
    def _blank_path_to_default(cls, value: object) -> object:
        """Пустая DATABASE_PATH= → путь по умолчанию."""
        if isinstance(value, str) and not value.strip():
            return DEFAULT_DATABASE_PATH
        return value

    # --- Проверка корректности ---

    @field_validator("n8n_webhook_url")
    @classmethod
    def _check_webhook_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("N8N_WEBHOOK_URL должен быть абсолютным http(s)-адресом")
        return value

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(ALLOWED_LOG_LEVELS))
            raise ValueError(f"LOG_LEVEL должен быть одним из: {allowed}")
        return level

    # --- Удобные производные значения ---

    @property
    def is_bot_configured(self) -> bool:
        """Готов ли бот к запуску (задан ли токен)."""
        return bool(self.bot_token.strip())

    @property
    def is_n8n_configured(self) -> bool:
        """Задан ли webhook n8n."""
        return bool(self.n8n_webhook_url)

    @property
    def is_admin_api_guarded(self) -> bool:
        """Требуется ли токен для чтения админ-эндпоинтов."""
        return bool(self.admin_api_token)

    def resolved_database_path(self) -> Path:
        """Абсолютный путь к файлу БД (относительный путь считается от корня проекта)."""
        path = self.database_path
        return path if path.is_absolute() else PROJECT_ROOT / path

    def safe_dump(self) -> dict[str, object]:
        """Настройки без секретов — можно безопасно писать в лог."""
        data = self.model_dump(mode="json")
        for field_name in SECRET_FIELDS:
            data[field_name] = MASKED if data.get(field_name) else ""
        return data


def load_settings() -> Settings:
    """Прочитать настройки и превратить ошибки валидации в ConfigurationError."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'env'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigurationError(f"Некорректные настройки окружения → {problems}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки с кэшированием: создаются один раз на процесс."""
    return load_settings()

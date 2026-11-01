"""Тесты настроек окружения: валидация, нормализация и маскирование секретов.

Токены здесь синтетические (формат <id>:<строка>), реальных секретов нет.
Проверки идут через load_settings(), чтобы тестировать то же поведение,
которое видит точка входа бота: pydantic ValidationError → ConfigurationError.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings, load_settings
from app.core.exceptions import ConfigurationError

VALID_TOKEN = "123456789:" + "A" * 35


def test_missing_token_is_allowed_but_bot_not_configured() -> None:
    """Отсутствие BOT_TOKEN не ломает импорт настроек."""
    settings = Settings(_env_file=None, BOT_TOKEN="")

    assert settings.is_bot_configured is False


def test_valid_token_is_accepted() -> None:
    settings = Settings(_env_file=None, BOT_TOKEN=VALID_TOKEN)

    assert settings.is_bot_configured is True
    assert settings.bot_token == VALID_TOKEN


def test_token_is_trimmed() -> None:
    settings = Settings(_env_file=None, BOT_TOKEN=f"  {VALID_TOKEN}  ")

    assert settings.bot_token == VALID_TOKEN
    assert settings.is_bot_configured is True


@pytest.mark.parametrize(
    "bad_token",
    ["abc", "123456789", "123456789:", ":shortsecret", "12 34:secretvalue"],
)
def test_malformed_token_fails_startup(monkeypatch: pytest.MonkeyPatch, bad_token: str) -> None:
    """Кривой токен должен падать на старте, а не после запуска polling."""
    monkeypatch.setenv("BOT_TOKEN", bad_token)

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    assert "BOT_TOKEN" in str(excinfo.value)


def test_lowercase_log_level_is_normalized() -> None:
    settings = Settings(_env_file=None, LOG_LEVEL="debug")

    assert settings.log_level == "DEBUG"


def test_unknown_log_level_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    assert "LOG_LEVEL" in str(excinfo.value)


def test_blank_optional_values_become_none() -> None:
    """Пустые необязательные переменные означают «не задано», а не ошибку."""
    settings = Settings(
        _env_file=None,
        N8N_WEBHOOK_URL="",
        N8N_WEBHOOK_SECRET="   ",
        ADMIN_CHAT_ID="",
    )

    assert settings.n8n_webhook_url is None
    assert settings.n8n_webhook_secret is None
    assert settings.admin_chat_id is None
    assert settings.is_n8n_configured is False


def test_relative_webhook_url_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_URL", "localhost:5678/webhook")

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    assert "N8N_WEBHOOK_URL" in str(excinfo.value)


def test_non_positive_http_timeout_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_TIMEOUT", "0")

    with pytest.raises(ConfigurationError):
        load_settings()


def test_blank_database_path_falls_back_to_default() -> None:
    settings = Settings(_env_file=None, DATABASE_PATH="")

    assert settings.resolved_database_path().name == "leads.sqlite3"


def test_safe_dump_masks_secrets() -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN=VALID_TOKEN,
        N8N_WEBHOOK_SECRET="super-secret-value",
        ADMIN_API_TOKEN="another-secret",
    )
    dumped = settings.safe_dump()

    assert dumped["bot_token"] == "***"
    assert dumped["n8n_webhook_secret"] == "***"
    assert dumped["admin_api_token"] == "***"
    assert VALID_TOKEN not in str(dumped)
    assert "super-secret-value" not in str(dumped)
    assert "another-secret" not in str(dumped)


def test_admin_api_token_is_optional_and_blank_means_open() -> None:
    """Пустой ADMIN_API_TOKEN = админ-эндпоинты без токена (локальный запуск)."""
    settings = Settings(_env_file=None, ADMIN_API_TOKEN="  ")

    assert settings.admin_api_token is None
    assert settings.is_admin_api_guarded is False


def test_admin_api_token_guards_endpoints_when_set() -> None:
    settings = Settings(_env_file=None, ADMIN_API_TOKEN="token-value")

    assert settings.admin_api_token == "token-value"
    assert settings.is_admin_api_guarded is True


def test_load_settings_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/telegram-lead")

    settings = load_settings()

    assert settings.is_bot_configured is True
    assert settings.n8n_webhook_url == "http://localhost:5678/webhook/telegram-lead"

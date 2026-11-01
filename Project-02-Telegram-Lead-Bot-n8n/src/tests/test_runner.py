"""Тесты готовности точки входа бота к запуску (без сети и Telegram API).

Проверяем fail-fast: неверная конфигурация должна приводить к понятной ошибке
до первого обращения к Telegram, а корректная — доводить сборку бота до
готового Dispatcher/Bot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bot import runner
from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError

VALID_TOKEN = "123456789:" + "A" * 35


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """get_settings кэширован, поэтому между тестами кэш нужно сбрасывать."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_run_without_token_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без BOT_TOKEN запуск прекращается до создания Bot."""
    monkeypatch.setenv("BOT_TOKEN", "")

    with pytest.raises(ConfigurationError) as excinfo:
        await runner.run()

    assert "BOT_TOKEN" in str(excinfo.value)


async def test_run_with_malformed_token_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "не-токен")

    with pytest.raises(ConfigurationError):
        await runner.run()


def test_build_lead_service_creates_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Сборка сервисного слоя создаёт БД и не требует настроенного n8n."""
    db_path = tmp_path / "nested" / "leads.sqlite3"
    monkeypatch.setattr(
        runner,
        "get_settings",
        lambda: Settings(_env_file=None, DATABASE_PATH=str(db_path)),
    )

    service = runner.build_lead_service()

    assert db_path.exists()
    assert service.n8n_client.is_configured is False

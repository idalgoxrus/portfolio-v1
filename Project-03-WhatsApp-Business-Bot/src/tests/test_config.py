"""Tests for environment-based configuration and secret handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import MASKED_VALUE, Settings, get_settings

SECRET = "super-secret-api-key-do-not-leak"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate tests from the developer's real environment and any .env file."""
    for name in (
        "EVOLUTION_API_URL",
        "EVOLUTION_API_KEY",
        "EVOLUTION_INSTANCE",
        "WEBHOOK_URL",
        "REQUEST_TIMEOUT",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()


def test_defaults_are_empty_and_unconfigured(clean_env: None) -> None:
    settings = Settings()

    assert settings.evolution_api_url == ""
    assert settings.evolution_api_key_value == ""
    assert settings.evolution_instance == ""
    assert settings.webhook_url == ""
    assert settings.evolution_configured is False


def test_settings_load_from_environment(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "https://evolution.example.com")
    monkeypatch.setenv("EVOLUTION_API_KEY", SECRET)
    monkeypatch.setenv("EVOLUTION_INSTANCE", "demo")
    monkeypatch.setenv("WEBHOOK_URL", "https://bot.example.com/webhook")

    settings = Settings()

    assert settings.evolution_api_url == "https://evolution.example.com"
    assert settings.evolution_api_key_value == SECRET
    assert settings.evolution_instance == "demo"
    assert settings.webhook_url == "https://bot.example.com/webhook"
    assert settings.evolution_configured is True


def test_secret_is_masked_in_repr_and_str(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVOLUTION_API_KEY", SECRET)
    settings = Settings()

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert "**********" in repr(settings) or MASKED_VALUE in repr(settings)


def test_safe_dict_masks_secret(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_KEY", SECRET)
    safe = Settings().safe_dict()

    assert SECRET not in str(safe)
    assert safe["evolution_api_key"] == MASKED_VALUE
    assert set(safe) == {
        "evolution_api_url",
        "evolution_api_key",
        "evolution_instance",
        "webhook_url",
        "webhook_auth_enabled",
        "webhook_secret",
        "webhook_allowed_instances",
        "request_timeout",
        "log_level",
    }
    # The webhook secret must never be exposed in cleartext.
    assert safe["webhook_secret"] == ""


def test_config_endpoint_never_exposes_secret(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVOLUTION_API_URL", "https://evolution.example.com")
    monkeypatch.setenv("EVOLUTION_API_KEY", SECRET)
    monkeypatch.setenv("EVOLUTION_INSTANCE", "demo")

    from app.main import create_app

    with TestClient(create_app(Settings())) as client:
        response = client.get("/config")

    body = response.json()
    assert response.status_code == 200
    assert SECRET not in response.text
    assert body["settings"]["evolution_api_key"] == MASKED_VALUE
    assert body["evolution_configured"] is True


def test_request_timeout_must_be_positive(clean_env: None) -> None:
    with pytest.raises(ValueError):
        Settings(request_timeout=0)


def test_get_settings_is_cached(clean_env: None) -> None:
    assert get_settings() is get_settings()


def test_env_example_file_exists_without_real_values() -> None:
    example = PROJECT_ROOT / ".env.example"

    assert example.is_file()
    content = example.read_text(encoding="utf-8")
    for key in (
        "EVOLUTION_API_URL",
        "EVOLUTION_API_KEY",
        "EVOLUTION_INSTANCE",
        "WEBHOOK_URL",
    ):
        assert f"{key}=" in content


def test_no_env_file_is_committed() -> None:
    assert not (PROJECT_ROOT / ".env").exists()

"""Application configuration.

All values come from environment variables (optionally via a local ``.env``
file). No credential is hardcoded, and the API key is wrapped in ``SecretStr``
so it cannot leak through ``repr()``, ``str()`` or logs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MASKED_VALUE = "***"

# Header used to authenticate incoming webhooks. Evolution API sends whatever
# per-instance ``headers`` are configured for the instance, so this is the
# shared secret the bot and the gateway agree on. It is the same header the
# Evolution API itself expects for its own /webhook registration calls.
WEBHOOK_SECRET_HEADER = "x-webhook-token"


class Settings(BaseSettings):
    """Runtime settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    evolution_api_url: str = ""
    evolution_api_key: SecretStr = SecretStr("")
    evolution_instance: str = ""
    webhook_url: str = ""

    # Shared secret expected in the WEBHOOK_SECRET_HEADER header on incoming
    # webhook calls. Empty (the default) disables the check, which keeps local
    # testing frictionless. See ``webhook_auth_enabled``.
    webhook_secret: SecretStr = SecretStr("")

    # Optional comma-separated allowlist of Evolution instance names. When
    # non-empty, events for any other instance are rejected. Empty means no
    # filtering.
    webhook_allowed_instances: str = ""

    request_timeout: float = Field(default=15.0, gt=0)
    log_level: str = "INFO"

    @field_validator("webhook_allowed_instances", mode="after")
    @classmethod
    def _normalise_instances(cls, value: str) -> str:
        return ",".join(part.strip() for part in value.split(",") if part.strip())

    @property
    def evolution_api_key_value(self) -> str:
        """Raw API key, for the outbound HTTP client only."""
        return self.evolution_api_key.get_secret_value()

    @property
    def evolution_configured(self) -> bool:
        """True when all three Evolution API settings are present."""
        return bool(
            self.evolution_api_url
            and self.evolution_api_key_value
            and self.evolution_instance
        )

    @property
    def webhook_secret_value(self) -> str:
        """Raw webhook shared secret. Only compare with, never log."""
        return self.webhook_secret.get_secret_value()

    @property
    def webhook_auth_enabled(self) -> bool:
        """True when incoming webhooks must present the shared secret."""
        return bool(self.webhook_secret_value)

    @property
    def allowed_instances(self) -> tuple[str, ...]:
        """Instance names accepted by the webhook, if an allowlist is set."""
        if not self.webhook_allowed_instances:
            return ()
        return tuple(self.webhook_allowed_instances.split(","))

    def safe_dict(self) -> dict[str, Any]:
        """Settings dump safe to log or expose over HTTP."""
        return {
            "evolution_api_url": self.evolution_api_url,
            "evolution_api_key": MASKED_VALUE if self.evolution_api_key_value else "",
            "evolution_instance": self.evolution_instance,
            "webhook_url": self.webhook_url,
            "webhook_auth_enabled": self.webhook_auth_enabled,
            "webhook_secret": MASKED_VALUE if self.webhook_secret_value else "",
            "webhook_allowed_instances": list(self.allowed_instances),
            "request_timeout": self.request_timeout,
            "log_level": self.log_level,
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for the running process."""
    return Settings()

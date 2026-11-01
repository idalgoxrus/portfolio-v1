"""Доменная модель лида — единый контракт между ботом, БД и n8n."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-()]{6,19}$")
_NON_DIGITS = re.compile(r"\D")


class LeadStatus(StrEnum):
    """Жизненный цикл лида."""

    NEW = "new"
    SENT = "sent"
    FAILED = "failed"


def normalize_phone(raw: str) -> str:
    """Привести телефон к виду +<цифры>, отбросив пробелы, скобки и дефисы."""
    digits = _NON_DIGITS.sub("", raw or "")
    return f"+{digits}" if digits else (raw or "").strip()


class Lead(BaseModel):
    """Заявка, собранная ботом."""

    telegram_id: int
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=7, max_length=20)
    username: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)
    source: str = Field(default="telegram_bot", max_length=64)
    status: LeadStatus = LeadStatus.NEW
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("full_name", "phone")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("значение не может быть пустым")
        return value

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if not PHONE_PATTERN.match(normalized):
            raise ValueError("телефон должен содержать 7-20 символов, допустимы цифры и +-()")
        return normalized

    @field_validator("comment", "username")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def to_n8n_payload(self) -> dict[str, object]:
        """JSON-совместимое представление лида для отправки в webhook."""
        return self.model_dump(mode="json")

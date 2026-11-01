"""Тесты доменной модели лида."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.lead import Lead, LeadStatus, normalize_phone


def test_normalize_phone_strips_formatting() -> None:
    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"


def test_lead_normalizes_fields_and_defaults() -> None:
    lead = Lead(telegram_id=1, full_name="  Иван  ", phone="8 999 123 45 67")

    assert lead.full_name == "Иван"
    assert lead.phone == "+89991234567"
    assert lead.status is LeadStatus.NEW
    assert lead.source == "telegram_bot"
    assert lead.comment is None


def test_lead_rejects_invalid_phone() -> None:
    with pytest.raises(ValidationError):
        Lead(telegram_id=1, full_name="Иван", phone="не телефон")


def test_lead_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        Lead(telegram_id=1, full_name="   ", phone="+79991234567")


def test_lead_comment_is_trimmed_to_none() -> None:
    lead = Lead(telegram_id=1, full_name="Иван", phone="+79991234567", comment="   ")

    assert lead.comment is None


def test_payload_is_json_serializable() -> None:
    lead = Lead(telegram_id=1, full_name="Иван", phone="+79991234567", comment="Нужна консультация")
    payload = lead.to_n8n_payload()

    assert payload["status"] == "new"
    assert payload["phone"] == "+79991234567"
    assert isinstance(payload["created_at"], str)

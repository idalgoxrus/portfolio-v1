"""Тесты простого правила маршрутизации (без AI-классификации)."""

from __future__ import annotations

import pytest

from app.models.lead import Lead
from app.services.routing import (
    DEFAULT_QUEUE,
    HIGH_PRIORITY_QUEUE,
    SUPPORT_QUEUE,
    LeadPriority,
    route_lead,
)


def test_plain_lead_without_comment_goes_to_default_queue() -> None:
    decision = route_lead({"source": "telegram_bot", "comment": None})

    assert decision.queue == DEFAULT_QUEUE
    assert decision.priority is LeadPriority.NORMAL
    assert decision.reason == "default"
    assert decision.tags == ()


def test_comment_moves_lead_to_sales_queue() -> None:
    decision = route_lead({"source": "telegram_bot", "comment": "просто интересуюсь"})

    assert decision.queue == "sales"
    assert decision.reason == "comment_present"
    assert decision.tags == ("with_comment",)


@pytest.mark.parametrize("keyword", ["срочно", "ASAP", "Сегодня", "завтра", "консультация"])
def test_urgency_keyword_raises_priority(keyword: str) -> None:
    """Ключевое слово ловится независимо от регистра (в т.ч. внутри фразы)."""
    decision = route_lead({"source": "telegram_bot", "comment": f"Мне {keyword} нужно"})

    assert decision.queue == HIGH_PRIORITY_QUEUE
    assert decision.priority is LeadPriority.HIGH
    assert decision.reason.startswith("keyword:")
    assert "hot" in decision.tags


def test_keyword_wins_over_plain_comment() -> None:
    """При конфликте правил приоритет у ключевого слова."""
    decision = route_lead({"source": "telegram_bot", "comment": "срочно, обычный вопрос"})

    assert decision.priority is LeadPriority.HIGH


def test_non_bot_source_goes_to_support() -> None:
    decision = route_lead({"source": "website_form", "comment": "срочно"})

    assert decision.queue == SUPPORT_QUEUE
    assert decision.priority is LeadPriority.NORMAL
    assert decision.reason == "source=website_form"


def test_source_rule_wins_over_keyword() -> None:
    """Лид не из бота уходит в поддержку, даже если в комментарии есть ключевое слово."""
    decision = route_lead({"source": "landing", "comment": "asap"})

    assert decision.queue == SUPPORT_QUEUE


def test_blank_comment_is_treated_as_absent() -> None:
    decision = route_lead({"source": "telegram_bot", "comment": "   "})

    assert decision.queue == DEFAULT_QUEUE


def test_lead_model_is_supported_directly() -> None:
    """Функция принимает и доменную модель, и словарь — единый контракт."""
    lead = Lead(telegram_id=1, full_name="Иван", phone="+79991234567", comment="консультация")

    decision = route_lead(lead)

    assert decision.queue == HIGH_PRIORITY_QUEUE
    assert decision.priority is LeadPriority.HIGH


def test_lead_model_without_comment_uses_default() -> None:
    lead = Lead(telegram_id=1, full_name="Иван", phone="+79991234567")

    assert route_lead(lead).queue == DEFAULT_QUEUE


def test_custom_keywords_are_respected() -> None:
    decision = route_lead(
        {"source": "telegram_bot", "comment": "нужен аудит"},
        high_value_keywords=("аудит",),
    )

    assert decision.priority is LeadPriority.HIGH
    assert decision.reason == "keyword:аудит"


def test_payload_is_json_ready() -> None:
    payload = route_lead({"source": "telegram_bot", "comment": "срочно"}).to_payload()

    assert payload["route"] == HIGH_PRIORITY_QUEUE
    assert payload["priority"] == "high"
    assert payload["tags"] == ["hot", "срочно"]

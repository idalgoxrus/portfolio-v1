"""Маршрутизация лида по простому правилу — без AI-классификации.

Правило намеренно детерминированное и объяснимое: менеджер должен понимать,
почему лид попал в ту или иную очередь. Результат (`RoutingDecision`) — это
готовый к передаче в n8n/Telegram контракт уведомления.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Значения по умолчанию; переопределяются аргументами route_lead().
DEFAULT_HIGH_VALUE_KEYWORDS = ("срочно", "asap", "сегодня", "завтра", "консультация")
BY_REGION_QUEUE = "sales"
SUPPORT_QUEUE = "support"
HIGH_PRIORITY_QUEUE = "priority"
DEFAULT_QUEUE = "general"


class LeadPriority(StrEnum):
    """Приоритет обработки лида."""

    HIGH = "high"
    NORMAL = "normal"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Результат маршрутизации: кому и с каким приоритетом уходит лид."""

    queue: str
    priority: LeadPriority
    reason: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        """JSON-совместимый вид для n8n/уведомления."""
        return {
            "route": self.queue,
            "priority": self.priority.value,
            "reason": self.reason,
            "tags": list(self.tags),
        }


def route_lead(
    lead: Mapping[str, Any] | Any,
    *,
    high_value_keywords: tuple[str, ...] = DEFAULT_HIGH_VALUE_KEYWORDS,
) -> RoutingDecision:
    """Определить очередь и приоритет лида по простым правилам.

    Порядок проверок (первое сработавшее правило выигрывает):
    1. источник не `telegram_bot` → отдельный контур поддержки;
    2. ключевое слово в комментарии → высокий приоритет;
    3. комментарий заполнен → обычная продажа с тегом «with_comment»;
    4. иначе → общая очередь.
    """

    def field_value(name: str) -> str:
        if isinstance(lead, Mapping):
            raw = lead.get(name)
        else:
            raw = getattr(lead, name, None)
        return str(raw).strip() if raw is not None else ""

    source = field_value("source") or "telegram_bot"
    comment = field_value("comment")

    if source and source != "telegram_bot":
        return RoutingDecision(
            queue=SUPPORT_QUEUE,
            priority=LeadPriority.NORMAL,
            reason=f"source={source}",
            tags=(source,),
        )

    lowered = comment.lower()
    matched = next((word for word in high_value_keywords if word.lower() in lowered), None)
    if matched:
        return RoutingDecision(
            queue=HIGH_PRIORITY_QUEUE,
            priority=LeadPriority.HIGH,
            reason=f"keyword:{matched}",
            tags=("hot", matched),
        )

    if comment:
        return RoutingDecision(
            queue=BY_REGION_QUEUE,
            priority=LeadPriority.NORMAL,
            reason="comment_present",
            tags=("with_comment",),
        )

    return RoutingDecision(
        queue=DEFAULT_QUEUE,
        priority=LeadPriority.NORMAL,
        reason="default",
        tags=(),
    )

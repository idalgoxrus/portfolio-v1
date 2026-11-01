"""Follow-up / напоминания по лидам на основе уже существующих данных.

Сложная очередь не нужна: n8n вызывает воркфлоу по расписанию, забирает
`list_leads()` и классифицирует возраст каждой заявки по `created_at`.
Классификация вынесена в чистые функции — её легко тестировать без БД и сети.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from app.models.lead import LeadStatus

SENT_REMINDER_AFTER_HOURS = 24
STALE_AFTER_HOURS = 72


class FollowUpBucket(StrEnum):
    """Во что превратился лид по прошествии времени."""

    FRESH = "fresh"  # только что пришёл, напоминать рано
    REMIND = "remind"  # давно ждёт ответа менеджера — пора напомнить
    STALE = "stale"  # критично просрочен
    UNRESOLVED = "unresolved"  # не передан в n8n (failed) — нужен ручной разбор


@dataclass(frozen=True, slots=True)
class FollowUpItem:
    """Один лид, требующий внимания."""

    lead_id: int
    bucket: FollowUpBucket
    age_hours: float
    phone: str
    full_name: str
    status: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "bucket": self.bucket.value,
            "age_hours": round(self.age_hours, 1),
            "phone": self.phone,
            "full_name": self.full_name,
            "status": self.status,
        }


def _parse_created_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def age_hours(created_at: object, *, now: datetime | None = None) -> float | None:
    """Возраст лида в часах или None, если дата нечитаема."""
    parsed = _parse_created_at(created_at)
    if parsed is None:
        return None
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return (reference - parsed).total_seconds() / 3600


def reminder_cutoff_iso(
    *,
    now: datetime | None = None,
    sent_after_hours: float = SENT_REMINDER_AFTER_HOURS,
) -> str:
    """ISO-строка границы «лид достаточно старый для напоминания».

    Нужна, чтобы репозиторий отсекал свежие лиды прямо в SQL (и они не вытесняли
    проблемные из LIMIT). Формат совпадает с `Lead.created_at.isoformat()`, поэтому
    сравнение строк в SQLite лексикографически корректно.
    """
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return (reference - timedelta(hours=sent_after_hours)).isoformat()


def classify_lead(
    lead: Mapping[str, Any],
    *,
    now: datetime | None = None,
    sent_after_hours: float = SENT_REMINDER_AFTER_HOURS,
    stale_after_hours: float = STALE_AFTER_HOURS,
) -> FollowUpBucket:
    """Определить, нужно ли напоминание по лиду."""
    status = str(lead.get("status") or "")
    if status == LeadStatus.FAILED.value:
        return FollowUpBucket.UNRESOLVED

    age = age_hours(lead.get("created_at"), now=now)
    if age is None or age < sent_after_hours:
        return FollowUpBucket.FRESH
    if age >= stale_after_hours:
        return FollowUpBucket.STALE
    return FollowUpBucket.REMIND


def select_follow_ups(
    leads: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    sent_after_hours: float = SENT_REMINDER_AFTER_HOURS,
    stale_after_hours: float = STALE_AFTER_HOURS,
) -> list[FollowUpItem]:
    """Оставить только лиды, требующие действия, отсортированные по возрасту."""
    items: list[FollowUpItem] = []
    for lead in leads:
        bucket = classify_lead(
            lead,
            now=now,
            sent_after_hours=sent_after_hours,
            stale_after_hours=stale_after_hours,
        )
        if bucket is FollowUpBucket.FRESH:
            continue
        age = age_hours(lead.get("created_at"), now=now) or 0.0
        items.append(
            FollowUpItem(
                lead_id=int(lead.get("id") or 0),
                bucket=bucket,
                age_hours=age,
                phone=str(lead.get("phone") or ""),
                full_name=str(lead.get("full_name") or ""),
                status=str(lead.get("status") or ""),
            )
        )

    items.sort(key=lambda item: item.age_hours, reverse=True)
    return items


def build_follow_up_payload(
    leads: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    sent_after_hours: float = SENT_REMINDER_AFTER_HOURS,
    stale_after_hours: float = STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Контракт ответа для n8n: сколько и какие лиды требуют внимания."""
    items = select_follow_ups(
        leads,
        now=now,
        sent_after_hours=sent_after_hours,
        stale_after_hours=stale_after_hours,
    )
    return {
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "count": len(items),
        "items": [item.to_payload() for item in items],
    }

"""Тесты классификации лидов для follow-up / напоминаний."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.lead import LeadStatus
from app.services.followup import (
    STALE_AFTER_HOURS,
    FollowUpBucket,
    age_hours,
    build_follow_up_payload,
    classify_lead,
    select_follow_ups,
)

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _lead(
    *,
    lead_id: int = 1,
    hours_ago: float = 0,
    status: LeadStatus = LeadStatus.SENT,
) -> dict[str, object]:
    return {
        "id": lead_id,
        "status": status.value,
        "phone": "+79991234567",
        "full_name": "Иван",
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }


def test_fresh_lead_is_not_flagged() -> None:
    assert classify_lead(_lead(hours_ago=1), now=NOW) is FollowUpBucket.FRESH


def test_lead_between_thresholds_needs_reminder() -> None:
    assert classify_lead(_lead(hours_ago=30), now=NOW) is FollowUpBucket.REMIND


def test_lead_older_than_stale_threshold_is_stale() -> None:
    assert classify_lead(_lead(hours_ago=STALE_AFTER_HOURS + 1), now=NOW) is FollowUpBucket.STALE


def test_failed_lead_is_unresolved_regardless_of_age() -> None:
    """Не переданный в n8n лид требует ручного разбора сразу, а не через сутки."""
    bucket = classify_lead(_lead(hours_ago=0.1, status=LeadStatus.FAILED), now=NOW)

    assert bucket is FollowUpBucket.UNRESOLVED


def test_boundary_at_reminder_threshold_is_inclusive() -> None:
    assert classify_lead(_lead(hours_ago=24), now=NOW) is FollowUpBucket.REMIND


def test_boundary_just_below_reminder_threshold() -> None:
    assert classify_lead(_lead(hours_ago=23.9), now=NOW) is FollowUpBucket.FRESH


def test_broken_created_at_is_treated_as_fresh() -> None:
    """Некорректная дата не должна превращаться в «срочное напоминание»."""
    lead = _lead(status=LeadStatus.SENT)
    lead["created_at"] = "не-дата"

    assert classify_lead(lead, now=NOW) is FollowUpBucket.FRESH


def test_age_hours_accepts_naive_and_aware_datetimes() -> None:
    assert age_hours(NOW.replace(tzinfo=None), now=NOW) == pytest.approx(0.0)
    assert age_hours((NOW - timedelta(hours=5)).isoformat(), now=NOW) == pytest.approx(5.0)


def test_age_hours_returns_none_for_unparsable_value() -> None:
    assert age_hours("2026-13-45T99:99:99", now=NOW) is None


def test_select_follow_ups_filters_fresh_and_sorts_by_age() -> None:
    leads = [
        _lead(lead_id=1, hours_ago=1),
        _lead(lead_id=2, hours_ago=30),
        _lead(lead_id=3, hours_ago=100),
    ]

    items = select_follow_ups(leads, now=NOW)

    assert [item.lead_id for item in items] == [3, 2]


def test_select_follow_ups_includes_unresolved() -> None:
    leads = [_lead(lead_id=9, hours_ago=0.5, status=LeadStatus.FAILED)]

    items = select_follow_ups(leads, now=NOW)

    assert [item.bucket for item in items] == [FollowUpBucket.UNRESOLVED]


def test_thresholds_are_configurable() -> None:
    leads = [_lead(hours_ago=5)]

    items = select_follow_ups(leads, now=NOW, sent_after_hours=1, stale_after_hours=6)

    assert [item.bucket for item in items] == [FollowUpBucket.REMIND]
    assert not select_follow_ups(leads, now=NOW, sent_after_hours=10, stale_after_hours=100)


def test_payload_contract_for_n8n() -> None:
    payload = build_follow_up_payload(
        [_lead(lead_id=7, hours_ago=48), _lead(lead_id=8, hours_ago=1)],
        now=NOW,
    )

    assert payload["count"] == 1
    assert payload["generated_at"] == NOW.isoformat()
    item = payload["items"][0]
    assert item["lead_id"] == 7
    assert item["bucket"] == FollowUpBucket.REMIND.value
    assert item["age_hours"] == 48.0
    assert item["phone"] == "+79991234567"


def test_empty_input_yields_empty_payload() -> None:
    payload = build_follow_up_payload([], now=NOW)

    assert payload["count"] == 0
    assert payload["items"] == []

"""Тесты ежедневной статистики по лидам."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.models.lead import LeadStatus
from app.services.reporting import build_daily_report, day_bounds


def _lead(status: LeadStatus) -> dict[str, object]:
    return {"status": status.value}


def test_empty_day_yields_zeroes() -> None:
    report = build_daily_report([], day=date(2026, 1, 1))

    assert report.total == 0
    assert report.new == report.sent == report.failed == 0
    assert report.success_rate == 0.0


def test_counts_are_split_by_status() -> None:
    leads = [
        _lead(LeadStatus.NEW),
        _lead(LeadStatus.SENT),
        _lead(LeadStatus.SENT),
        _lead(LeadStatus.FAILED),
    ]

    report = build_daily_report(leads, day=date(2026, 1, 1))

    assert (report.total, report.new, report.sent, report.failed) == (4, 1, 2, 1)
    assert report.success_rate == 0.5


def test_unknown_status_lands_in_other_and_keeps_total_consistent() -> None:
    """Неизвестный статус не должен ломать счётчики или «исчезать» из total."""
    leads = [_lead(LeadStatus.SENT), {"status": "archived"}, {"status": None}]

    report = build_daily_report(leads, day=date(2026, 1, 1))

    assert report.total == 3
    assert report.sent == 1
    assert report.other == 2


def test_success_rate_covers_all_delivered() -> None:
    report = build_daily_report([_lead(LeadStatus.SENT)] * 3, day=date(2026, 1, 1))

    assert report.success_rate == 1.0


def test_payload_fields() -> None:
    payload = build_daily_report([_lead(LeadStatus.FAILED)], day=date(2026, 1, 5)).to_payload()

    assert payload == {
        "day": "2026-01-05",
        "total": 1,
        "new": 0,
        "sent": 0,
        "failed": 1,
        "other": 0,
        "success_rate": 0.0,
    }


def test_text_report_contains_required_metrics() -> None:
    report = build_daily_report(
        [_lead(LeadStatus.NEW), _lead(LeadStatus.SENT), _lead(LeadStatus.FAILED)],
        day=date(2026, 1, 5),
    )

    text = report.to_text()

    assert "2026-01-05" in text
    assert "Всего лидов: 3" in text
    assert "Отправлено: 1" in text
    assert "Не передано (failed): 1" in text


def test_day_bounds_cover_exactly_one_utc_day() -> None:
    since, until = day_bounds(date(2026, 3, 1))

    assert since == datetime(2026, 3, 1, tzinfo=UTC).isoformat()
    assert until == datetime(2026, 3, 2, tzinfo=UTC).isoformat()


def test_default_day_is_today_utc() -> None:
    report = build_daily_report([])

    assert report.day == datetime.now(UTC).date()

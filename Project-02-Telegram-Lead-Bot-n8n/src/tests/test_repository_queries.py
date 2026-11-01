"""Тесты новых выборок репозитория: фильтры, границы, группировка по статусам."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.models.lead import Lead, LeadStatus
from app.storage.repository import LeadRepository

NOW = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)


@pytest.fixture()
def repository(tmp_path: Path) -> LeadRepository:
    repo = LeadRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    return repo


def _add(
    repository: LeadRepository,
    *,
    status: LeadStatus = LeadStatus.NEW,
    hours_ago: float = 0,
    full_name: str = "Иван",
) -> int:
    lead = Lead(telegram_id=1, full_name=full_name, phone="+79991234567").model_copy(
        update={"status": status, "created_at": NOW - timedelta(hours=hours_ago)}
    )
    return repository.add_lead(lead)


def test_list_leads_without_filters_returns_all_newest_first(repository: LeadRepository) -> None:
    first = _add(repository, full_name="Первый", hours_ago=10)
    second = _add(repository, full_name="Второй", hours_ago=1)

    rows = repository.list_leads()

    assert [row["id"] for row in rows] == [second, first]


def test_list_leads_filters_by_status(repository: LeadRepository) -> None:
    _add(repository, status=LeadStatus.SENT)
    _add(repository, status=LeadStatus.FAILED)

    rows = repository.list_leads(status=LeadStatus.FAILED)

    assert len(rows) == 1
    assert rows[0]["status"] == LeadStatus.FAILED.value


def test_list_leads_since_is_inclusive(repository: LeadRepository) -> None:
    _add(repository, hours_ago=24)
    _add(repository, hours_ago=1)

    rows = repository.list_leads(since=(NOW - timedelta(hours=24)).isoformat())

    assert len(rows) == 2


def test_list_leads_until_is_exclusive(repository: LeadRepository) -> None:
    _add(repository, hours_ago=1)

    rows = repository.list_leads(until=(NOW - timedelta(hours=1)).isoformat())

    assert rows == []


def test_list_leads_combines_filters(repository: LeadRepository) -> None:
    _add(repository, status=LeadStatus.SENT, hours_ago=1)
    _add(repository, status=LeadStatus.SENT, hours_ago=50)
    _add(repository, status=LeadStatus.FAILED, hours_ago=1)

    rows = repository.list_leads(
        status=LeadStatus.SENT,
        since=(NOW - timedelta(hours=10)).isoformat(),
    )

    assert len(rows) == 1


def test_list_leads_respects_limit(repository: LeadRepository) -> None:
    for index in range(5):
        _add(repository, hours_ago=index)

    assert len(repository.list_leads(limit=2)) == 2


def test_list_leads_zero_limit_returns_nothing(repository: LeadRepository) -> None:
    _add(repository)

    assert repository.list_leads(limit=0) == []


def test_list_leads_is_empty_for_fresh_database(repository: LeadRepository) -> None:
    assert repository.list_leads() == []


def test_list_follow_up_candidates_keeps_old_failed_lead_under_limit(
    repository: LeadRepository,
) -> None:
    """failed-лид старше границы попадает в кандидатов, даже если он не в «последних N»."""
    old_failed = _add(repository, status=LeadStatus.FAILED, hours_ago=500)
    for index in range(10):
        _add(repository, status=LeadStatus.SENT, hours_ago=index)

    rows = repository.list_follow_up_candidates(
        older_than=(NOW - timedelta(hours=24)).isoformat(),
        limit=3,
    )

    assert old_failed in [row["id"] for row in rows]


def test_list_follow_up_candidates_excludes_fresh_sent_leads(repository: LeadRepository) -> None:
    """Свежие `sent`/`new` не являются кандидатами: фильтр работает в SQL."""
    _add(repository, status=LeadStatus.SENT, hours_ago=1)
    _add(repository, status=LeadStatus.NEW, hours_ago=2)

    rows = repository.list_follow_up_candidates(older_than=(NOW - timedelta(hours=24)).isoformat())

    assert rows == []


def test_list_follow_up_candidates_boundary_is_inclusive(repository: LeadRepository) -> None:
    """Ровно на границе 24 ч лид уже кандидат (согласовано с classify_lead)."""
    at_boundary = _add(repository, status=LeadStatus.SENT, hours_ago=24)

    rows = repository.list_follow_up_candidates(older_than=(NOW - timedelta(hours=24)).isoformat())

    assert [row["id"] for row in rows] == [at_boundary]


def test_list_follow_up_candidates_returns_newest_first(repository: LeadRepository) -> None:
    first = _add(repository, status=LeadStatus.SENT, hours_ago=100)
    second = _add(repository, status=LeadStatus.SENT, hours_ago=50)

    rows = repository.list_follow_up_candidates(older_than=(NOW - timedelta(hours=24)).isoformat())

    assert [row["id"] for row in rows] == [second, first]


def test_count_by_status_returns_zeroes_for_missing_statuses(repository: LeadRepository) -> None:
    _add(repository, status=LeadStatus.SENT)

    counts = repository.count_by_status()

    assert counts == {"new": 0, "sent": 1, "failed": 0}


def test_count_by_status_counts_every_status(repository: LeadRepository) -> None:
    _add(repository, status=LeadStatus.NEW)
    _add(repository, status=LeadStatus.SENT)
    _add(repository, status=LeadStatus.SENT)
    _add(repository, status=LeadStatus.FAILED)

    assert repository.count_by_status() == {"new": 1, "sent": 2, "failed": 1}


def test_existing_count_helper_still_works(repository: LeadRepository) -> None:
    """Старый метод count() не сломан новыми выборками."""
    _add(repository, status=LeadStatus.SENT)

    assert repository.count() == 1
    assert repository.count(LeadStatus.SENT) == 1
    assert repository.count(LeadStatus.FAILED) == 0

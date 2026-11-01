"""Тесты новых HTTP-эндпоинтов: чтение лидов, карточка, сводка, follow-up.

Работают через ASGI-приложение (TestClient) и реальный SQLite во временном
каталоге — сеть и n8n не используются. База подменяется через dependency_overrides,
поэтому тесты не зависят от содержимого рабочей БД.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app, get_repository
from app.models.lead import Lead, LeadStatus
from app.storage.repository import LeadRepository

TOKEN = "secret-admin-token"


@pytest.fixture()
def repository(tmp_path: Path) -> LeadRepository:
    repo = LeadRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    return repo


@pytest.fixture()
def client(repository: LeadRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ADMIN_API_TOKEN="")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed(repository: LeadRepository, *, status: LeadStatus, hours_ago: float = 0, comment: str | None = None) -> int:
    lead = Lead(telegram_id=1, full_name="Иван", phone="+79991234567", comment=comment)
    lead = lead.model_copy(
        update={
            "status": status,
            "created_at": datetime.now(UTC) - timedelta(hours=hours_ago),
        }
    )
    return repository.add_lead(lead)


def test_health_still_ok(client: TestClient) -> None:
    """Существующий health-эндпоинт не сломан расширением API."""
    assert client.get("/health").json() == {"status": "ok"}


def test_list_leads_returns_items_and_count(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.SENT)
    _seed(repository, status=LeadStatus.FAILED)

    body = client.get("/leads").json()

    assert body["count"] == 2
    assert len(body["items"]) == 2


def test_list_leads_filters_by_status(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.SENT)
    _seed(repository, status=LeadStatus.FAILED)

    body = client.get("/leads", params={"status": LeadStatus.FAILED.value}).json()

    assert body["count"] == 1
    assert body["items"][0]["status"] == LeadStatus.FAILED.value


def test_list_leads_rejects_unknown_status(client: TestClient) -> None:
    assert client.get("/leads", params={"status": "не-статус"}).status_code == 422


def test_list_leads_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/leads", params={"limit": 0}).status_code == 422
    assert client.get("/leads", params={"limit": 5000}).status_code == 422


def test_list_leads_filters_by_day_bounds(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.SENT, hours_ago=30)
    _seed(repository, status=LeadStatus.SENT, hours_ago=1)

    since = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    body = client.get("/leads", params={"since": since}).json()

    assert body["count"] == 1


def test_get_lead_returns_card(client: TestClient, repository: LeadRepository) -> None:
    lead_id = _seed(repository, status=LeadStatus.SENT)

    body = client.get(f"/leads/{lead_id}").json()

    assert body["id"] == lead_id
    assert body["phone"] == "+79991234567"


def test_get_missing_lead_returns_404(client: TestClient) -> None:
    assert client.get("/leads/424242").status_code == 404


def test_daily_stats_matches_repository(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.SENT)
    _seed(repository, status=LeadStatus.FAILED)
    _seed(repository, status=LeadStatus.FAILED)

    body = client.get("/stats/daily").json()

    assert body["total"] == 3
    assert body["sent"] == 1
    assert body["failed"] == 2
    assert body["new"] == 0


def test_daily_stats_accepts_explicit_day(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.SENT, hours_ago=48)

    body = client.get("/stats/daily", params={"day": "2020-01-01"}).json()

    assert body["day"] == "2020-01-01"
    assert body["total"] == 0


def test_daily_stats_rejects_broken_day(client: TestClient) -> None:
    assert client.get("/stats/daily", params={"day": "01-01-2026"}).status_code == 422


def test_follow_ups_returns_stale_leads(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.SENT, hours_ago=100)
    _seed(repository, status=LeadStatus.SENT, hours_ago=1)

    body = client.get("/follow-ups").json()

    assert body["count"] == 1
    assert body["items"][0]["bucket"] == "stale"


def test_follow_ups_includes_failed_lead(client: TestClient, repository: LeadRepository) -> None:
    _seed(repository, status=LeadStatus.FAILED)

    body = client.get("/follow-ups").json()

    assert body["items"][0]["bucket"] == "unresolved"


def test_follow_ups_keeps_old_failed_lead_behind_many_fresh_ones(
    client: TestClient, repository: LeadRepository
) -> None:
    """Регрессия: старый failed не должен выпадать из-за лимита на «последние N» лидов.

    Раньше выборка брала последние 200 записей и только потом классифицировала их,
    поэтому 250 свежих заявок полностью вытесняли старый failed-лид из напоминаний.
    """
    old_failed_id = _seed(repository, status=LeadStatus.FAILED, hours_ago=500)
    for _ in range(250):
        _seed(repository, status=LeadStatus.SENT, hours_ago=0)

    body = client.get("/follow-ups").json()

    lead_ids = [item["lead_id"] for item in body["items"]]
    assert old_failed_id in lead_ids
    assert body["count"] == 1


def test_follow_ups_keeps_old_stale_lead_behind_many_fresh_ones(
    client: TestClient, repository: LeadRepository
) -> None:
    """Та же регрессия для просроченного (`stale`) лида, а не только `failed`."""
    old_stale_id = _seed(repository, status=LeadStatus.SENT, hours_ago=200)
    for _ in range(250):
        _seed(repository, status=LeadStatus.SENT, hours_ago=0)

    body = client.get("/follow-ups").json()

    lead_ids = [item["lead_id"] for item in body["items"]]
    assert old_stale_id in lead_ids


def test_follow_ups_excludes_fresh_leads(client: TestClient, repository: LeadRepository) -> None:
    """Свежие заявки в напоминания не попадают — фильтр работает в SQL, до лимита."""
    _seed(repository, status=LeadStatus.SENT, hours_ago=1)
    _seed(repository, status=LeadStatus.NEW, hours_ago=2)

    body = client.get("/follow-ups").json()

    assert body["count"] == 0
    assert body["items"] == []


def test_follow_ups_limit_is_optional_and_caps_items(
    client: TestClient, repository: LeadRepository
) -> None:
    """Явный limit остаётся поддерживаемым, но по умолчанию ограничения нет."""
    for _ in range(5):
        _seed(repository, status=LeadStatus.FAILED)

    assert client.get("/follow-ups").json()["count"] == 5
    assert client.get("/follow-ups", params={"limit": 2}).json()["count"] == 2
    assert client.get("/follow-ups", params={"limit": 0}).status_code == 422


def test_follow_ups_rejects_absurd_limit(client: TestClient) -> None:
    assert client.get("/follow-ups", params={"limit": 100000}).status_code == 422


# --- защита токеном ---


@pytest.fixture()
def guarded_client(repository: LeadRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ADMIN_API_TOKEN=TOKEN)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["/leads", "/leads/1", "/stats/daily", "/follow-ups"])
def test_guarded_endpoints_reject_missing_token(guarded_client: TestClient, path: str) -> None:
    """Если ADMIN_API_TOKEN задан, персональные данные без токена не отдаются."""
    assert guarded_client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/leads", "/leads/1", "/stats/daily", "/follow-ups"])
def test_guarded_endpoints_reject_wrong_token(guarded_client: TestClient, path: str) -> None:
    response = guarded_client.get(path, headers={"X-Admin-Token": "wrong"})

    assert response.status_code == 401


def test_guarded_endpoint_accepts_correct_token(
    guarded_client: TestClient, repository: LeadRepository
) -> None:
    _seed(repository, status=LeadStatus.SENT)

    response = guarded_client.get("/leads", headers={"X-Admin-Token": TOKEN})

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_health_is_never_guarded(guarded_client: TestClient) -> None:
    """Liveness-проверка должна оставаться открытой для мониторинга."""
    assert guarded_client.get("/health").status_code == 200

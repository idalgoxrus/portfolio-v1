"""Тесты надёжности статусов и хранилища: new/sent/failed, отсутствие потери лида.

Здесь проверяется реальный LeadRepository (SQLite во временной папке) и настоящая
логика LeadService. Подменяется только внешний n8n-клиент — это граница системы.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.lead import Lead, LeadStatus
from app.services.lead_service import LeadService
from app.services.n8n_client import N8nDeliveryError
from app.storage.repository import LeadRepository


class RecordingN8nClient:
    """Фиксирует отправленные лиды и отдаёт заданный исход."""

    def __init__(self, *, success: bool = True, error: Exception | None = None) -> None:
        self.success = success
        self.error = error
        self.sent: list[Lead] = []

    async def send_lead(self, lead: Lead) -> bool:
        self.sent.append(lead)
        if self.error is not None:
            raise self.error
        return self.success


@pytest.fixture()
def repository(tmp_path: Path) -> LeadRepository:
    repo = LeadRepository(tmp_path / "nested" / "leads.sqlite3")
    repo.init_schema()
    return repo


def _lead(telegram_id: int = 42) -> Lead:
    return Lead(telegram_id=telegram_id, full_name="Вадим", phone="+79991234567")


async def test_status_transitions_new_then_sent(repository: LeadRepository) -> None:
    """Итоговый статус sent, а не new: new — только промежуточное состояние записи."""
    service = LeadService(repository=repository, n8n_client=RecordingN8nClient(success=True))

    _, lead_id, status = await service.register_lead(_lead())

    assert status is LeadStatus.SENT
    assert repository.get(lead_id)["status"] == LeadStatus.SENT.value
    assert repository.count(LeadStatus.NEW) == 0


async def test_failed_lead_is_persisted_not_lost(repository: LeadRepository) -> None:
    """Сбой интеграции не теряет заявку: строка остаётся в БД со статусом failed."""
    client = RecordingN8nClient(error=N8nDeliveryError("n8n недоступен"))
    service = LeadService(repository=repository, n8n_client=client)

    _, lead_id, status = await service.register_lead(_lead())

    assert status is LeadStatus.FAILED
    row = repository.get(lead_id)
    assert row is not None
    assert row["status"] == LeadStatus.FAILED.value
    assert row["phone"] == "+79991234567"


async def test_lead_saved_once_even_when_delivery_fails(repository: LeadRepository) -> None:
    """Даже при полном провале доставки создаётся ровно одна запись (нет потери/дублей)."""
    service = LeadService(
        repository=repository, n8n_client=RecordingN8nClient(error=N8nDeliveryError("boom"))
    )

    await service.register_lead(_lead())

    assert repository.count() == 1


async def test_unconfigured_webhook_marks_failed_and_keeps_row(repository: LeadRepository) -> None:
    """webhook_url=None → send_lead вернёт False → статус failed, заявка сохранена."""
    service = LeadService(repository=repository, n8n_client=RecordingN8nClient(success=False))

    _, lead_id, status = await service.register_lead(_lead())

    assert status is LeadStatus.FAILED
    assert repository.get(lead_id)["status"] == LeadStatus.FAILED.value


async def test_each_register_call_creates_distinct_row(repository: LeadRepository) -> None:
    """Повторный вызов сервиса создаёт новую запись (идемпотентность реализуется выше).

    Это фиксирует текущую семантику at-least-once: дедупликация не входит в задачу
    сервиса, поэтому двойной вызов даёт две строки — важно, чтобы это было осознанно.
    """
    client = RecordingN8nClient(success=True)
    service = LeadService(repository=repository, n8n_client=client)

    _, first_id, _ = await service.register_lead(_lead())
    _, second_id, _ = await service.register_lead(_lead())

    assert first_id != second_id
    assert repository.count() == 2
    assert len(client.sent) == 2


async def test_status_index_supports_filtering(repository: LeadRepository) -> None:
    service = LeadService(repository=repository, n8n_client=RecordingN8nClient(success=True))
    await service.register_lead(_lead())

    assert repository.count(LeadStatus.SENT) == 1
    assert repository.count(LeadStatus.FAILED) == 0


def test_init_schema_is_idempotent(tmp_path: Path) -> None:
    """Повторный init_schema на той же БД не должен падать или терять данные."""
    repo = LeadRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    repo.add_lead(_lead())
    repo.init_schema()

    assert repo.count() == 1


def test_set_status_on_missing_lead_is_silent_noop(repository: LeadRepository) -> None:
    """Обновление статуса несуществующего id не создаёт запись и не бросает."""
    repository.set_status(999_999, LeadStatus.FAILED)

    assert repository.get(999_999) is None
    assert repository.count() == 0


def test_get_and_list_recent_are_read_only(repository: LeadRepository) -> None:
    lead_id = repository.add_lead(_lead())

    assert repository.get(lead_id)["telegram_id"] == 42
    assert repository.list_recent(limit=5)[0]["id"] == lead_id
    assert repository.get(lead_id + 1) is None


def test_add_lead_returns_usable_id_and_persists_created_at(repository: LeadRepository) -> None:
    lead = _lead()
    lead_id = repository.add_lead(lead)

    assert lead_id > 0
    row = repository.get(lead_id)
    assert row["created_at"] == lead.created_at.isoformat()
    assert row["source"] == "telegram_bot"


def test_repository_survives_new_connection(repository: LeadRepository) -> None:
    """Данные коммитятся: новое соединение видит запись (нет незакрытой транзакции)."""
    lead_id = repository.add_lead(_lead())

    fresh = sqlite3.connect(repository.db_path)
    try:
        row = fresh.execute("SELECT phone FROM leads WHERE id = ?", (lead_id,)).fetchone()
    finally:
        fresh.close()

    assert row == ("+79991234567",)

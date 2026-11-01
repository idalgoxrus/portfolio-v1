"""Тесты связки репозиторий + сервис (без сети)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.lead import Lead, LeadStatus
from app.services.lead_service import LeadService
from app.services.n8n_client import N8nDeliveryError
from app.storage.repository import LeadRepository


class FakeN8nClient:
    """Подмена n8n-клиента для тестов."""

    def __init__(self, success: bool = True, error: Exception | None = None) -> None:
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
    repo = LeadRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    return repo


def _lead() -> Lead:
    return Lead(telegram_id=42, full_name="Иван", phone="+79991234567")


async def test_register_lead_marks_sent(repository: LeadRepository) -> None:
    service = LeadService(repository=repository, n8n_client=FakeN8nClient(success=True))  # type: ignore[arg-type]

    _, lead_id, status = await service.register_lead(_lead())

    assert lead_id > 0
    assert status is LeadStatus.SENT
    assert repository.count(LeadStatus.SENT) == 1
    assert repository.get(lead_id)["phone"] == "+79991234567"


async def test_register_lead_marks_failed_on_error(repository: LeadRepository) -> None:
    client = FakeN8nClient(error=N8nDeliveryError("n8n недоступен"))
    service = LeadService(repository=repository, n8n_client=client)  # type: ignore[arg-type]

    _, lead_id, status = await service.register_lead(_lead())

    assert status is LeadStatus.FAILED
    assert repository.count(LeadStatus.FAILED) == 1
    # заявка не теряется, даже если интеграция упала
    assert repository.get(lead_id) is not None


async def test_register_lead_marks_failed_when_webhook_missing(repository: LeadRepository) -> None:
    service = LeadService(repository=repository, n8n_client=FakeN8nClient(success=False))  # type: ignore[arg-type]

    _, _, status = await service.register_lead(_lead())

    assert status is LeadStatus.FAILED
    assert repository.count() == 1

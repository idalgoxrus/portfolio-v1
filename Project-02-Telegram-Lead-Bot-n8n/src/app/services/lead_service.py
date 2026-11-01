"""Бизнес-логика обработки лида: сохранить → передать в n8n → обновить статус."""

from __future__ import annotations

import logging

from app.models.lead import Lead, LeadStatus
from app.services.n8n_client import N8nClient, N8nDeliveryError
from app.storage.repository import LeadRepository

logger = logging.getLogger(__name__)


class LeadService:
    """Оркестратор обработки заявки."""

    def __init__(self, repository: LeadRepository, n8n_client: N8nClient) -> None:
        self.repository = repository
        self.n8n_client = n8n_client

    async def register_lead(self, lead: Lead) -> tuple[Lead, int, LeadStatus]:
        """Сохранить лид локально и попытаться передать его в n8n.

        Возвращает кортеж (лид, id в БД, итоговый статус).
        Ошибка интеграции не теряет заявку: она остаётся в БД со статусом failed.
        """
        lead_id = self.repository.add_lead(lead)
        logger.info("Лид #%s сохранён (телефон %s)", lead_id, lead.phone)

        status = LeadStatus.NEW
        try:
            delivered = await self.n8n_client.send_lead(lead)
            status = LeadStatus.SENT if delivered else LeadStatus.FAILED
        except N8nDeliveryError as exc:
            logger.error("Лид #%s не передан в n8n: %s", lead_id, exc)
            status = LeadStatus.FAILED
        except Exception as exc:  # noqa: BLE001
            # Любой непредвиденный сбой интеграции обязан дать терминальный статус:
            # иначе заявка навсегда останется в new и выпадет из обработки.
            logger.exception("Непредвиденный сбой передачи лида #%s: %s", lead_id, exc)
            status = LeadStatus.FAILED

        self.repository.set_status(lead_id, status)
        return lead, lead_id, status

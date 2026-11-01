"""HTTP-клиент для передачи лидов в n8n webhook."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.exceptions import N8nDeliveryError
from app.models.lead import Lead

__all__ = ["RETRYABLE_STATUS", "SOURCE_HEADER", "TOKEN_HEADER", "N8nClient", "N8nDeliveryError"]

logger = logging.getLogger(__name__)

SOURCE_HEADER = "X-Webhook-Source"
TOKEN_HEADER = "X-Webhook-Token"


# Коды 4xx, которые означают временную проблему и имеют смысл при повторе.
# Остальные 4xx — постоянные (неверный запрос, нет прав): повтор только тянет время.
RETRYABLE_STATUS = frozenset({408, 429})


class N8nClient:
    """Отправка лида в n8n с повторами и экспоненциальной задержкой."""

    def __init__(
        self,
        webhook_url: str | None,
        secret: str | None = None,
        timeout: float = 10.0,
        retries: int = 2,
    ) -> None:
        self.webhook_url = webhook_url
        self.secret = secret
        self.timeout = timeout
        self.retries = max(0, retries)

    @property
    def is_configured(self) -> bool:
        """Задан ли URL webhook."""
        return bool(self.webhook_url)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", SOURCE_HEADER: "telegram-lead-bot"}
        if self.secret:
            headers[TOKEN_HEADER] = self.secret
        return headers

    async def send_lead(self, lead: Lead) -> bool:
        """Отправить лид в n8n.

        Возвращает True при успехе, False если webhook не настроен.
        Бросает N8nDeliveryError, если все попытки исчерпаны.
        """
        if not self.is_configured or not self.webhook_url:
            logger.warning("N8N_WEBHOOK_URL не задан — лид не передан в n8n")
            return False

        payload = lead.to_n8n_payload()
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(self.webhook_url, json=payload, headers=self._headers())
                if response.is_success:
                    logger.info("Лид передан в n8n (попытка %s, код %s)", attempt, response.status_code)
                    return True

                last_error = N8nDeliveryError(
                    f"n8n ответил {response.status_code}: {response.text[:200]}"
                )
                # 4xx (кроме 408/429) — постоянная ошибка: повтор не изменит результат,
                # а редирект 3xx означает, что webhook не обработан и повтор тоже бесполезен.
                if response.status_code < 500 and response.status_code not in RETRYABLE_STATUS:
                    logger.warning("Лид отклонён n8n без повторов (код %s)", response.status_code)
                    raise last_error
            except httpx.HTTPError as exc:
                last_error = exc

            logger.warning("Попытка %s/%s передачи лида не удалась: %s", attempt, self.retries + 1, last_error)
            if attempt <= self.retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 5))

        raise N8nDeliveryError(str(last_error))

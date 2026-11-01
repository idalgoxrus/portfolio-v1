"""Тесты надёжности HTTP-клиента n8n: таймауты, повторы, коды ответа, сетевые сбои.

Транспорт подменяется httpx.MockTransport, поэтому реальных сетевых вызовов нет,
но код ответа обрабатывает настоящий httpx.Response и наш код N8nClient.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.models.lead import Lead
from app.services.n8n_client import (
    SOURCE_HEADER,
    TOKEN_HEADER,
    N8nClient,
    N8nDeliveryError,
)

REAL_ASYNC_CLIENT = httpx.AsyncClient
WEBHOOK = "http://n8n.test/webhook/telegram-lead"


class Harness:
    """Подменяет httpx.AsyncClient транспортом-заглушкой и записывает вызовы."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, handler) -> None:
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.client_kwargs: list[dict] = []

        def wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request, len(self.requests))

        transport = httpx.MockTransport(wrapped)

        def factory(*args, **kwargs):
            self.client_kwargs.append(dict(kwargs))
            kwargs.pop("timeout", None)
            return REAL_ASYNC_CLIENT(transport=transport, follow_redirects=False)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

        async def fake_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    @property
    def attempts(self) -> int:
        return len(self.requests)


@pytest.fixture()
def make_client(monkeypatch: pytest.MonkeyPatch):
    """Вернуть фабрику (handler, **client_kwargs) -> (client, harness)."""

    def build(handler, retries: int = 2, secret: str | None = None, **kwargs):
        harness = Harness(monkeypatch, handler)
        client = N8nClient(webhook_url=WEBHOOK, secret=secret, retries=retries, **kwargs)
        return client, harness

    return build


def _status(code: int, text: str = ""):
    def handler(_request: httpx.Request, _n: int) -> httpx.Response:
        return httpx.Response(code, text=text)

    return handler


def _lead() -> Lead:
    return Lead(telegram_id=42, full_name="Вадим", phone="+79991234567")


async def test_2xx_is_reported_as_success_without_retry(make_client) -> None:
    client, harness = make_client(_status(200))

    assert await client.send_lead(_lead()) is True
    assert harness.attempts == 1
    assert harness.sleeps == []


@pytest.mark.parametrize("code", [200, 201, 202, 204])
async def test_all_2xx_codes_are_success(make_client, code: int) -> None:
    client, harness = make_client(_status(code))

    assert await client.send_lead(_lead()) is True
    assert harness.attempts == 1


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
async def test_redirects_are_not_treated_as_delivered(make_client, code: int) -> None:
    """3xx означает, что webhook не обработан: лид нельзя помечать sent."""
    client, harness = make_client(_status(code))

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 1, "редирект — постоянная ошибка, повтор не нужен"


async def test_5xx_is_retried_up_to_retries_plus_one(make_client) -> None:
    client, harness = make_client(_status(500, "boom"))

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 3


async def test_backoff_schedule_is_exponential_and_capped(make_client) -> None:
    client, harness = make_client(_status(503), retries=3)

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())

    # 2**0=1, 2**1=2, 2**2=4 (кап 5 ещё не достигнут), между 4 попытками 3 паузы
    assert harness.sleeps == [1, 2, 4]


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
async def test_permanent_4xx_is_not_retried(make_client, code: int) -> None:
    """400/401/404/422 — постоянные ошибки: повтор только задерживает пользователя."""
    client, harness = make_client(_status(code, "bad request"))

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 1


async def test_429_is_retried(make_client) -> None:
    """429 Too Many Requests — временная ошибка, повтор оправдан."""
    client, harness = make_client(_status(429, "slow down"))

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 3


async def test_connection_error_is_retried_then_raises(make_client) -> None:
    def handler(_request: httpx.Request, _n: int) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client, harness = make_client(handler)

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 3


async def test_timeout_is_retried_then_raises(make_client) -> None:
    def handler(_request: httpx.Request, _n: int) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    client, harness = make_client(handler)

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 3


async def test_zero_retries_makes_single_attempt(make_client) -> None:
    client, harness = make_client(_status(500), retries=0)

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())
    assert harness.attempts == 1
    assert harness.sleeps == []


async def test_unconfigured_webhook_returns_false_without_http(make_client) -> None:
    client, harness = make_client(_status(200))
    client.webhook_url = None

    assert await client.send_lead(_lead()) is False
    assert harness.attempts == 0


async def test_configured_timeout_is_passed_to_http_client(make_client) -> None:
    client, harness = make_client(_status(200), timeout=7.5)

    await client.send_lead(_lead())

    assert harness.client_kwargs[0]["timeout"] == 7.5


async def test_headers_carry_source_and_optional_secret(make_client) -> None:
    client, harness = make_client(_status(200), secret="s3cret-token")

    await client.send_lead(_lead())

    headers = harness.requests[0].headers
    assert headers[SOURCE_HEADER] == "telegram-lead-bot"
    assert headers[TOKEN_HEADER] == "s3cret-token"


async def test_token_header_absent_without_secret(make_client) -> None:
    client, harness = make_client(_status(200))

    await client.send_lead(_lead())

    assert TOKEN_HEADER not in harness.requests[0].headers


async def test_payload_is_normalized_and_json_serializable(make_client) -> None:
    client, harness = make_client(_status(200))
    lead = Lead(telegram_id=7, full_name="  Вадим  ", phone="8 999 123 45 67")

    await client.send_lead(lead)

    body = json.loads(harness.requests[0].content)
    assert body["full_name"] == "Вадим"
    assert body["phone"] == "+89991234567"
    assert body["status"] == "new"
    assert isinstance(body["created_at"], str)


async def test_error_message_does_not_include_token(make_client) -> None:
    """Сообщение об ошибке не должно утекать секретом webhook."""
    secret = "super-secret-webhook-token"
    client, _ = make_client(_status(500, "down"), secret=secret)

    with pytest.raises(N8nDeliveryError) as excinfo:
        await client.send_lead(_lead())

    assert secret not in str(excinfo.value)


async def test_malformed_url_raises_delivery_error_not_value_error() -> None:
    """Битый URL, прошедший проверку настроек, должен стать N8nDeliveryError, а не голым исключением.

    urllib.parse принимает `http://:80/x` как валидный (netloc=':80'), но на реальном
    транспорте httpx он не доходит до сети. Важно, чтобы клиент обернул это в
    N8nDeliveryError: иначе LeadService не пометит лид как failed.

    Используется настоящий httpx-транспорт (заведомо неверный адрес), поэтому
    запрос мгновенно падает локально — реального сетевого вызова нет.
    """
    client = N8nClient(webhook_url="http://:80/x", retries=0)

    with pytest.raises(N8nDeliveryError):
        await client.send_lead(_lead())


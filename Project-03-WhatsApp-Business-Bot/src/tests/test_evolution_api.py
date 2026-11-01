"""Tests for the Evolution API client.

These tests cover the HTTP contract verified against a real local Evolution
API v2.3.7 container (see docker-compose.yml and README). Only the transport
layer is stubbed, via ``httpx.MockTransport``, so the real client code - URL
construction, headers, status handling and error mapping - is exercised.

No WhatsApp number and no live Evolution API are required.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx

from app.config import Settings
from app.evolution_api import EvolutionAPIClient

TEST_KEY = "test-key-not-a-real-secret"

# Verbatim response bodies captured from Evolution API v2.3.7.
ROOT_BODY = {
    "status": 200,
    "message": "Welcome to the Evolution API, it is working!",
    "version": "2.3.7",
    "clientName": "evolution_local",
}
INSTANCE_MISSING_BODY = {
    "status": 404,
    "error": "Not Found",
    "response": {"message": ['The "demo" instance does not exist']},
}

Handler = Callable[[httpx.Request], httpx.Response]


def configured_settings(instance: str = "demo") -> Settings:
    return Settings(
        evolution_api_url="http://127.0.0.1:8080",
        evolution_api_key=TEST_KEY,
        evolution_instance=instance,
        request_timeout=5.0,
    )


def unconfigured_settings() -> Settings:
    return Settings(
        evolution_api_url="",
        evolution_api_key="",
        evolution_instance="",
    )


def make_client(handler: Handler, settings: Settings | None = None) -> EvolutionAPIClient:
    return EvolutionAPIClient(
        settings or configured_settings(),
        transport=httpx.MockTransport(handler),
    )


def evolution_stub(
    instance_state: httpx.Response | None = None,
) -> Handler:
    """Transport mimicking a healthy Evolution API with no instances."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/":
            return httpx.Response(200, json=ROOT_BODY)
        if path.startswith("/instance/connectionState/"):
            if instance_state is not None:
                return instance_state
            return httpx.Response(404, json=INSTANCE_MISSING_BODY)
        if path.startswith("/message/sendText/"):
            return httpx.Response(404, json=INSTANCE_MISSING_BODY)
        return httpx.Response(404, json={"status": 404, "error": "Not Found"})

    return handler


def never_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError("network must not be touched when unconfigured")


# --------------------------------------------------------------------------
# check_api
# --------------------------------------------------------------------------


def test_check_api_reachable_without_any_instance() -> None:
    """A live API with no connected instance must report reachable=True."""
    client = make_client(evolution_stub())

    status = asyncio.run(client.check_api())

    assert status.reachable is True
    assert status.version == "2.3.7"
    assert status.instance_exists is False
    assert "does not exist yet" in status.detail
    assert "No WhatsApp number is connected" in status.detail


def test_check_api_reports_existing_instance() -> None:
    connected = httpx.Response(
        200, json={"instance": {"instanceName": "demo", "state": "close"}}
    )
    client = make_client(evolution_stub(instance_state=connected))

    status = asyncio.run(client.check_api())

    assert status.reachable is True
    assert status.instance_exists is True
    assert status.status_code == 200
    assert status.version == "2.3.7"


def test_check_api_unconfigured_does_not_touch_network() -> None:
    client = EvolutionAPIClient(
        unconfigured_settings(), transport=httpx.MockTransport(never_called)
    )

    status = asyncio.run(client.check_api())

    assert status.reachable is False
    assert "not configured" in status.detail
    assert status.version is None


def test_check_api_reports_unreachable_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    status = asyncio.run(make_client(handler).check_api())

    assert status.reachable is False
    assert "Connection error" in status.detail


def test_check_api_reports_unreachable_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    status = asyncio.run(make_client(handler).check_api())

    assert status.reachable is False
    assert status.detail == "Request timed out."


def test_check_api_reports_unreachable_on_server_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    status = asyncio.run(make_client(handler).check_api())

    assert status.reachable is False
    assert status.status_code == 500


def test_check_api_tolerates_non_json_root_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text="<html>not json</html>")
        return httpx.Response(404, json=INSTANCE_MISSING_BODY)

    status = asyncio.run(make_client(handler).check_api())

    assert status.reachable is True
    assert status.version is None
    assert status.instance_exists is False


def test_check_api_instance_state_unavailable_is_still_reachable() -> None:
    """A non-404 error on connectionState must not mask a live API."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, json=ROOT_BODY)
        return httpx.Response(500, text="state backend down")

    status = asyncio.run(make_client(handler).check_api())

    assert status.reachable is True
    assert status.instance_exists is None
    assert "Instance state unavailable" in status.detail


# --------------------------------------------------------------------------
# send_text_message
# --------------------------------------------------------------------------


def test_send_text_message_missing_instance_is_explicit() -> None:
    """404 'instance does not exist' must be reported clearly, not as a crash."""
    client = make_client(evolution_stub())

    result = asyncio.run(
        client.send_text_message(number="15550000000", text="Привет")
    )

    assert result.success is False
    assert result.status_code == 404
    assert "does not exist" in result.detail
    assert TEST_KEY not in result.detail


def test_send_text_message_success() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201, json={"key": {"id": "3EB0ABC"}, "status": "PENDING"}
        )

    result = asyncio.run(
        make_client(handler).send_text_message(number="15550000000", text="Привет")
    )

    assert result.success is True
    assert result.status_code == 201
    assert isinstance(result.response, dict)
    assert len(seen) == 1
    assert seen[0].url.path == "/message/sendText/demo"
    assert seen[0].headers["apikey"] == TEST_KEY
    assert "Привет".encode() in seen[0].content


def test_send_text_message_rejects_empty_inputs() -> None:
    client = make_client(evolution_stub())

    assert asyncio.run(client.send_text_message("", "hi")).success is False
    assert asyncio.run(client.send_text_message("15550000000", "")).success is False


def test_send_text_message_handles_non_json_success_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    result = asyncio.run(
        make_client(handler).send_text_message(number="15550000000", text="hi")
    )

    assert result.success is False
    assert "not valid JSON" in result.detail


def test_send_text_message_handles_json_array_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    result = asyncio.run(
        make_client(handler).send_text_message(number="15550000000", text="hi")
    )

    assert result.success is False
    assert "not an object" in result.detail


def test_send_text_message_handles_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = asyncio.run(
        make_client(handler).send_text_message(number="15550000000", text="hi")
    )

    assert result.success is False
    assert "Connection error" in result.detail


def test_send_text_message_handles_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.WriteTimeout("slow", request=request)

    result = asyncio.run(
        make_client(handler).send_text_message(number="15550000000", text="hi")
    )

    assert result.success is False
    assert result.detail == "Request timed out."


def test_send_text_message_unconfigured_does_not_touch_network() -> None:
    client = EvolutionAPIClient(
        unconfigured_settings(), transport=httpx.MockTransport(never_called)
    )

    result = asyncio.run(client.send_text_message(number="15550000000", text="hi"))

    assert result.success is False
    assert "not configured" in result.detail


# --------------------------------------------------------------------------
# URL / instance handling
# --------------------------------------------------------------------------


def test_base_url_and_instance_properties() -> None:
    client = make_client(evolution_stub(), configured_settings(instance="my-inst"))

    assert client.base_url == "http://127.0.0.1:8080"
    assert client.instance == "my-inst"


def test_base_url_trailing_slash_is_normalised() -> None:
    settings = Settings(
        evolution_api_url="http://127.0.0.1:8080/",
        evolution_api_key=TEST_KEY,
        evolution_instance="demo",
    )

    assert EvolutionAPIClient(settings).base_url == "http://127.0.0.1:8080"


def test_send_uses_exact_evolution_v2_path_and_payload_shape() -> None:
    """Guard the v2 route and body shape against silent regressions."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content
        return httpx.Response(201, json={"status": "PENDING"})

    asyncio.run(
        make_client(handler).send_text_message(number="15551234567", text="Привет")
    )

    assert captured["path"] == "/message/sendText/demo"
    assert b"15551234567" in captured["body"]
    assert "Привет".encode() in captured["body"]

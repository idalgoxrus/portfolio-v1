"""Minimal Evolution API client.

Wraps the HTTP calls the bot needs:

* ``check_api`` — probe the Evolution API and report its reachability.
* ``send_text_message`` — send a plain text WhatsApp message.

Every failure mode (timeout, connection error, HTTP error status, malformed
response body) is converted into a well defined result object, so callers
never have to deal with raw ``httpx`` exceptions.

Contract notes validated against Evolution API **v2.3.7**:

* ``GET /`` returns ``{"status":200,"message":"...","version":"2.3.7"}`` and
  is the reliable reachability probe. It does not depend on any instance
  existing.
* ``GET /instance/connectionState/{instance}`` returns ``404`` with
  ``{"response":{"message":["The \\"x\\" instance does not exist"]}}`` when the
  instance is absent. That is a normal state for this project - no WhatsApp
  number is connected - and must NOT be reported as "API unreachable".
* ``POST /message/sendText/{instance}`` returns ``404`` with the same
  instance-not-found body when the instance is missing.
* There is no ``/docs`` or ``/openapi.json`` route in this build; the browser
  UI is served at ``/manager``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendResult:
    """Outcome of an attempt to send a WhatsApp message."""

    success: bool
    status_code: int | None = None
    detail: str = ""
    response: dict[str, Any] | None = None


@dataclass(frozen=True)
class ApiStatus:
    """Outcome of an Evolution API availability probe."""

    reachable: bool
    status_code: int | None = None
    detail: str = ""
    version: str | None = None
    instance_exists: bool | None = None


def _summarize(response: httpx.Response) -> str:
    """Short, secret-free description of an HTTP response."""
    body = response.text or ""
    if len(body) > 300:
        body = body[:300] + "...(truncated)"
    return f"HTTP {response.status_code}: {body}"


def _is_instance_missing(response: httpx.Response) -> bool:
    """True when the API answered 'this instance does not exist'."""
    if response.status_code != 404:
        return False
    return "does not exist" in (response.text or "").lower()


def _as_str(value: Any) -> str | None:
    """Return ``value`` as a non-empty stripped string, else ``None``."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


class EvolutionAPIClient:
    """Thin async client for the Evolution API."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def base_url(self) -> str:
        return self._settings.evolution_api_url.rstrip("/")

    @property
    def instance(self) -> str:
        return self._settings.evolution_instance

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._settings.evolution_api_key_value,
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._settings.request_timeout,
            headers=self._headers(),
            transport=self._transport,
        )

    def _unconfigured(self) -> str:
        return (
            "Evolution API is not configured: set EVOLUTION_API_URL, "
            "EVOLUTION_API_KEY and EVOLUTION_INSTANCE."
        )

    async def check_api(self) -> ApiStatus:
        """Check whether the Evolution API answers.

        Reachability is established from ``GET /``, which succeeds whether or
        not any WhatsApp instance exists. The instance state is then probed as
        optional extra detail, so a missing instance never masquerades as an
        unreachable API.
        """
        if not self._settings.evolution_configured:
            return ApiStatus(reachable=False, detail=self._unconfigured())

        try:
            async with self._client() as client:
                root = await client.get("/")
                if root.status_code >= 400:
                    return ApiStatus(
                        reachable=False,
                        status_code=root.status_code,
                        detail=_summarize(root),
                    )

                version: str | None = None
                try:
                    payload = root.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict):
                    version = _as_str(payload.get("version"))

                state = await client.get(
                    f"instance/connectionState/{self.instance}"
                )
        except httpx.TimeoutException:
            logger.warning("Evolution API check timed out")
            return ApiStatus(reachable=False, detail="Request timed out.")
        except httpx.HTTPError as exc:
            logger.warning("Evolution API check failed: %s", type(exc).__name__)
            return ApiStatus(
                reachable=False,
                detail=f"Connection error: {type(exc).__name__}",
            )

        if _is_instance_missing(state):
            return ApiStatus(
                reachable=True,
                status_code=root.status_code,
                version=version,
                instance_exists=False,
                detail=(
                    f"Evolution API is reachable, but instance "
                    f"'{self.instance}' does not exist yet. "
                    "No WhatsApp number is connected (expected for this project)."
                ),
            )

        if state.status_code >= 400:
            return ApiStatus(
                reachable=True,
                status_code=state.status_code,
                version=version,
                instance_exists=None,
                detail=f"Instance state unavailable: {_summarize(state)}",
            )

        return ApiStatus(
            reachable=True,
            status_code=state.status_code,
            version=version,
            instance_exists=True,
            detail="Evolution API responded.",
        )

    async def send_text_message(self, number: str, text: str) -> SendResult:
        """Send a plain text WhatsApp message to ``number``."""
        if not number:
            return SendResult(success=False, detail="Recipient number is empty.")
        if not text:
            return SendResult(success=False, detail="Message text is empty.")
        if not self._settings.evolution_configured:
            return SendResult(success=False, detail=self._unconfigured())

        url = f"message/sendText/{self.instance}"
        payload = {"number": number, "text": text}

        try:
            async with self._client() as client:
                response = await client.post(url, json=payload)
        except httpx.TimeoutException:
            logger.warning("Sending message timed out")
            return SendResult(success=False, detail="Request timed out.")
        except httpx.HTTPError as exc:
            logger.warning("Sending message failed: %s", type(exc).__name__)
            return SendResult(
                success=False,
                detail=f"Connection error: {type(exc).__name__}",
            )

        if response.status_code >= 400:
            if _is_instance_missing(response):
                return SendResult(
                    success=False,
                    status_code=response.status_code,
                    detail=(
                        f"Cannot send: instance '{self.instance}' does not exist "
                        "in Evolution API. No WhatsApp number is connected."
                    ),
                )
            return SendResult(
                success=False,
                status_code=response.status_code,
                detail=_summarize(response),
            )

        try:
            body = response.json()
        except ValueError:
            logger.warning("Evolution API returned a non-JSON body")
            return SendResult(
                success=False,
                status_code=response.status_code,
                detail="Unexpected response: body is not valid JSON.",
            )

        if not isinstance(body, dict):
            return SendResult(
                success=False,
                status_code=response.status_code,
                detail="Unexpected response: JSON root is not an object.",
            )

        return SendResult(
            success=True,
            status_code=response.status_code,
            detail="Message queued for delivery.",
            response=body,
        )

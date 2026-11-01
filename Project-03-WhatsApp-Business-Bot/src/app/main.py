"""FastAPI application: HTTP layer only.

Routing, validation and error mapping live here. Message interpretation lives
in :mod:`app.bot` and :mod:`app.webhook`; WhatsApp transport lives in
:mod:`app.evolution_api`.

The webhook endpoint deliberately logs only routing metadata (event name,
instance, intent, whether a sender was detected). Evolution API includes an
``apikey`` field *in the webhook body*, so raw payloads must never be logged.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .bot import build_response
from .config import WEBHOOK_SECRET_HEADER, Settings, get_settings
from .evolution_api import EvolutionAPIClient
from .webhook import parse_webhook


logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _ignored(reason: str, **extra: Any) -> JSONResponse:
    """Standard 'nothing to do' webhook response."""
    content: dict[str, Any] = {
        "status": "ignored",
        "reason": reason,
        "reply_prepared": False,
    }
    content.update(extra)
    return JSONResponse(status_code=200, content=content)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    ``settings`` can be injected by tests; otherwise cached environment
    settings are used.
    """
    app = FastAPI(
        title="WhatsApp Business Bot + Evolution API",
        description="Portfolio Project #3 - demo WhatsApp Business Bot.",
        version="0.1.0",
    )

    active_settings = settings or get_settings()
    client = EvolutionAPIClient(active_settings)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/config", tags=["system"])
    async def config_status() -> dict[str, Any]:
        """Non-secret view of the active configuration."""
        return {
            "settings": active_settings.safe_dict(),
            "evolution_configured": active_settings.evolution_configured,
            "webhook_auth_enabled": active_settings.webhook_auth_enabled,
        }

    @app.get("/evolution/status", tags=["evolution"])
    async def evolution_status() -> dict[str, Any]:
        """Probe whether the configured Evolution API is reachable."""
        status = await client.check_api()
        return {
            "reachable": status.reachable,
            "status_code": status.status_code,
            "version": status.version,
            "instance_exists": status.instance_exists,
            "instance": active_settings.evolution_instance or None,
            "detail": status.detail,
        }

    @app.post("/webhook", tags=["webhook"])
    async def webhook(request: Request) -> JSONResponse:
        """Receive Evolution API / WhatsApp events without crashing."""
        # 1. Authentication. Disabled unless a shared secret is configured.
        if active_settings.webhook_auth_enabled:
            provided = request.headers.get(WEBHOOK_SECRET_HEADER, "")
            expected = active_settings.webhook_secret_value
            if not hmac.compare_digest(provided, expected):
                # Never log the presented or expected value.
                logger.warning("Webhook rejected: invalid or missing shared secret")
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": "unauthorized",
                        "detail": f"Missing or invalid {WEBHOOK_SECRET_HEADER} header.",
                    },
                )

        # 2. Body parsing. A malformed body is not an error condition here.
        try:
            payload = await request.json()
        except Exception:
            payload = None

        incoming = parse_webhook(payload)
        if incoming is None:
            logger.info("Webhook event ignored: no message detected")
            return _ignored("No incoming message detected in payload.")

        # 3. Instance allowlist, when configured.
        allowed = active_settings.allowed_instances
        if allowed and incoming.instance not in allowed:
            logger.warning("Webhook rejected: instance not allowed")
            return _ignored("Event received from an instance that is not allowed.")

        # 4. Loop prevention. ``fromMe`` marks a message the linked WhatsApp
        #    account itself sent. Replying to those would make the bot answer
        #    its own outgoing messages forever.
        if incoming.is_from_me:
            logger.info("Webhook event ignored: message originated from this account")
            return _ignored(
                "Message was sent by this account (fromMe=true); not replying.",
                from_me=True,
            )

        response = build_response(incoming.text)
        logger.info(
            "Webhook message handled: intent=%s sender=%s group=%s",
            response.intent.value,
            "present" if incoming.has_sender else "unknown",
            incoming.is_group,
        )

        reply_sent = False
        if incoming.has_sender and active_settings.evolution_configured:
            result = await client.send_text_message(
                number=incoming.sender or "",
                text=response.text,
            )
            reply_sent = result.success
            if not result.success:
                logger.warning("Reply delivery failed: %s", result.detail)

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "intent": response.intent.value,
                "sender": incoming.sender,
                "message_text": incoming.text,
                "event": incoming.event,
                "instance": incoming.instance,
                "from_me": incoming.is_from_me,
                "is_group": incoming.is_group,
                "reply_prepared": True,
                "reply_sent": reply_sent,
                "reply": response.text,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": "Internal server error."},
        )

    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    import uvicorn

    _configure_logging(get_settings().log_level)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

"""Точка входа Telegram-бота: инициализация хранилища, сервисов, роутеров, long polling.

Запуск из корня проекта:
    python -m app.bot.runner
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import router as lead_router
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, LeadBotError
from app.core.logging import configure_logging
from app.services.lead_service import LeadService
from app.services.n8n_client import N8nClient
from app.storage.repository import LeadRepository

logger = logging.getLogger(__name__)


def build_dispatcher(lead_service: LeadService) -> Dispatcher:
    """Собрать диспетчер и внедрить зависимости в обработчики."""
    dispatcher = Dispatcher(lead_service=lead_service)
    dispatcher.include_router(lead_router)
    return dispatcher


def build_lead_service() -> LeadService:
    """Собрать сервисный слой из настроек окружения."""
    settings = get_settings()

    repository = LeadRepository(settings.resolved_database_path())
    repository.init_schema()

    n8n_client = N8nClient(
        webhook_url=settings.n8n_webhook_url,
        secret=settings.n8n_webhook_secret,
        timeout=settings.http_timeout,
        retries=settings.http_retries,
    )
    return LeadService(repository=repository, n8n_client=n8n_client)


async def run() -> None:
    """Запустить бота в режиме long polling."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.is_bot_configured:
        raise ConfigurationError(
            "BOT_TOKEN не задан: скопируйте .env.example в .env и заполните значения."
        )

    lead_service = build_lead_service()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = build_dispatcher(lead_service)

    logger.info("Бот запускается. n8n webhook: %s", settings.n8n_webhook_url or "не настроен")
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Бот остановлен")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Остановлено пользователем")
    except LeadBotError as exc:
        print(f"Ошибка запуска: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

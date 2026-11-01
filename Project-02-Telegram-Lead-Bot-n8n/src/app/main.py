"""FastAPI-приложение: служебный HTTP-слой проекта.

Здесь живут health-check и read-only админ-эндпоинты, которые использует n8n:
списки лидов (routing/reminders), карточка лида и суточная сводка.

Логика бота лежит отдельно: точка входа — app/bot/runner.py.

Запуск:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from app import __version__
from app.core.config import Settings, get_settings
from app.core.exceptions import LeadBotError
from app.core.logging import configure_logging
from app.models.lead import LeadStatus
from app.services.followup import build_follow_up_payload, reminder_cutoff_iso
from app.services.reporting import build_daily_report, day_bounds
from app.storage.repository import LeadRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Настроить логирование при старте приложения."""
    try:
        configure_logging(get_settings().log_level)
    except LeadBotError as exc:
        configure_logging()
        logger.warning("Не удалось прочитать LOG_LEVEL (%s), используется INFO", exc)
    logger.info("HTTP-слой запущен (версия %s)", __version__)
    yield
    logger.info("HTTP-слой остановлен")


app = FastAPI(
    title="Telegram Lead Bot + n8n",
    description="Служебный HTTP-слой проекта #02: health-check, чтение лидов и отчёты для n8n.",
    version=__version__,
    lifespan=lifespan,
)


def get_repository() -> LeadRepository:
    """Репозиторий лидов на процесс (зависимость FastAPI)."""
    return LeadRepository(get_settings().resolved_database_path())


def require_admin_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    """Защитить эндпоинты с персональными данными заголовком X-Admin-Token.

    Если `ADMIN_API_TOKEN` в окружении не задан, доступ открыт: проект рассчитан
    на локальный запуск. В публичном деплое токен обязателен.
    """
    expected = settings.admin_api_token
    if not expected:
        return
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="invalid admin token")


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка живости сервиса."""
    return {"status": "ok"}


@app.get("/leads", dependencies=[Depends(require_admin_token)])
async def list_leads(
    repository: Annotated[LeadRepository, Depends(get_repository)],
    status: Annotated[LeadStatus | None, Query()] = None,
    since: Annotated[str | None, Query(description="ISO-8601 UTC, включительно")] = None,
    until: Annotated[str | None, Query(description="ISO-8601 UTC, не включительно")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, object]:
    """Список лидов по фильтрам — вход для маршрутизации и напоминаний в n8n."""
    leads = repository.list_leads(status=status, since=since, until=until, limit=limit)
    return {"count": len(leads), "items": leads}


@app.get("/leads/{lead_id}", dependencies=[Depends(require_admin_token)])
async def get_lead(
    lead_id: int,
    repository: Annotated[LeadRepository, Depends(get_repository)],
) -> dict[str, object]:
    """Карточка одного лида."""
    lead = repository.get(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@app.get("/stats/daily", dependencies=[Depends(require_admin_token)])
async def daily_stats(
    repository: Annotated[LeadRepository, Depends(get_repository)],
    day: Annotated[date | None, Query(description="Дата в UTC; по умолчанию — сегодня")] = None,
) -> dict[str, object]:
    """Суточная сводка по лидам (new / sent / failed) для отчёта в n8n."""
    target = day or datetime.now(UTC).date()
    since, until = day_bounds(target)
    leads = repository.list_leads(since=since, until=until, limit=1000)
    return build_daily_report(leads, day=target).to_payload()


@app.get("/follow-ups", dependencies=[Depends(require_admin_token)])
async def follow_ups(
    repository: Annotated[LeadRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=5000)] | None = None,
) -> dict[str, object]:
    """Лиды, требующие внимания менеджера (напоминания/follow-up).

    Кандидаты отбираются в SQL (`failed` + достаточно старые), а не «последние N
    записей»: иначе поток свежих заявок вытеснял бы старый `failed`-лид из окна
    выборки, и он не попал бы в напоминание никогда. По умолчанию ограничения нет —
    ни один проблемный лид не теряется.
    """
    candidates = repository.list_follow_up_candidates(
        older_than=reminder_cutoff_iso(),
        limit=limit,
    )
    return build_follow_up_payload(candidates)

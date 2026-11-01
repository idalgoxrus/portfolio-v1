"""Общие fixture тестов.

`handlers.router` — модульный синглтон, и aiogram запрещает подключать его к
двум разным Dispatcher. Поэтому Dispatcher собирается один раз на сессию, а
тесты изолируют состояние через MemoryStorage и workflow_data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.runner import build_dispatcher
from app.services.lead_service import LeadService
from app.services.n8n_client import N8nClient
from app.storage.repository import LeadRepository
from tests.support import FAKE_TOKEN, RecordingSession


@pytest.fixture(scope="session")
def dispatcher(tmp_path_factory: pytest.TempPathFactory) -> Dispatcher:
    repo = LeadRepository(tmp_path_factory.mktemp("dispatcher") / "boot.sqlite3")
    repo.init_schema()
    return build_dispatcher(LeadService(repository=repo, n8n_client=N8nClient(webhook_url=None)))


@pytest.fixture()
def repository(tmp_path: Path) -> LeadRepository:
    repo = LeadRepository(tmp_path / "leads.sqlite3")
    repo.init_schema()
    return repo


@pytest.fixture()
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture()
def bot(session: RecordingSession) -> Bot:
    return Bot(token=FAKE_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

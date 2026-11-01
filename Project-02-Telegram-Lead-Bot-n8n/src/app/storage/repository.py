"""Хранилище лидов на SQLite (только стандартная библиотека).

Этап 0 сознательно не тянет ORM: нужна нулевая зависимость от внешних сервисов.
При росте нагрузки репозиторий меняется на PostgreSQL без правок сервисного слоя.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from app.models.lead import Lead, LeadStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username    TEXT,
    full_name   TEXT NOT NULL,
    phone       TEXT NOT NULL,
    comment     TEXT,
    source      TEXT NOT NULL DEFAULT 'telegram_bot',
    status      TEXT NOT NULL DEFAULT 'new',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_telegram_id ON leads (telegram_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
"""


class LeadRepository:
    """Простой репозиторий лидов."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        """Создать таблицы и индексы, если их ещё нет."""
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def add_lead(self, lead: Lead) -> int:
        """Сохранить лид и вернуть его id."""
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO leads
                    (telegram_id, username, full_name, phone, comment, source, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead.telegram_id,
                    lead.username,
                    lead.full_name,
                    lead.phone,
                    lead.comment,
                    lead.source,
                    lead.status.value,
                    lead.created_at.isoformat(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid or 0)

    def set_status(self, lead_id: int, status: LeadStatus) -> None:
        """Обновить статус лида."""
        with closing(self._connect()) as connection:
            connection.execute("UPDATE leads SET status = ? WHERE id = ?", (status.value, lead_id))
            connection.commit()

    def get(self, lead_id: int) -> dict[str, object] | None:
        """Вернуть лид по id."""
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None

    def list_recent(self, limit: int = 20) -> list[dict[str, object]]:
        """Вернуть последние лиды (для админ-функций следующего этапа)."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_leads(
        self,
        *,
        status: LeadStatus | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        """Выборка лидов по фильтрам — входной контракт отчётов и напоминаний.

        `since`/`until` сравниваются со строкой `created_at` лексикографически, что
        корректно для ISO-8601 в UTC (так лид и сохраняется моделью `Lead`).
        """
        query = "SELECT * FROM leads"
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if until is not None:
            clauses.append("created_at < ?")
            params.append(until)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(0, limit))

        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_follow_up_candidates(
        self,
        *,
        older_than: str,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Выборка лидов, которые в принципе могут требовать внимания менеджера.

        Отбор идёт в SQL: `failed` (нужен ручной разбор независимо от возраста)
        либо лиды старше `older_than`. Это ключевое отличие от `list_leads(limit=...)`:
        там LIMIT накладывался на *все* записи, поэтому поток свежих заявок вытеснял
        старый `failed`-лид из окна выборки и он никогда не попадал в follow-up.
        Здесь статус и возраст отсекаются до LIMIT, так что проблемные лиды не теряются.
        """
        query = "SELECT * FROM leads WHERE status = ? OR created_at <= ? ORDER BY id DESC"
        params: list[object] = [LeadStatus.FAILED.value, older_than]
        if limit is not None:
            query += " LIMIT ?"
            params.append(max(0, limit))

        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def count_by_status(self) -> dict[str, int]:
        """Количество лидов по каждому статусу (включая отсутствующие — ноль)."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM leads GROUP BY status"
            ).fetchall()
        counts = {status.value: 0 for status in LeadStatus}
        for row in rows:
            counts[str(row["status"])] = int(row["total"])
        return counts

    def count(self, status: LeadStatus | None = None) -> int:
        """Количество лидов (всего или с указанным статусом)."""
        with closing(self._connect()) as connection:
            if status is None:
                row = connection.execute("SELECT COUNT(*) AS total FROM leads").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS total FROM leads WHERE status = ?", (status.value,)
                ).fetchone()
        return int(row["total"]) if row else 0

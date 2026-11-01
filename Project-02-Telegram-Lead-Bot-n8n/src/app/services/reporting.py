"""Ежедневная статистика по лидам.

Минимум MVP: сколько лидов создано за сутки и как они распределены по статусам
(`new` / `sent` / `failed`). Результат — готовый текст для Telegram и JSON для
других каналов уведомления.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.models.lead import LeadStatus


def day_bounds(day: date) -> tuple[str, str]:
    """Начало и конец суток в UTC как ISO-8601 — границы для `since`/`until`."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


@dataclass(frozen=True, slots=True)
class DailyReport:
    """Сводка по лидам за одни сутки."""

    day: date
    total: int
    new: int
    sent: int
    failed: int
    other: int

    @property
    def success_rate(self) -> float:
        """Доля успешно переданных лидов, 0.0 если заявок не было."""
        if self.total == 0:
            return 0.0
        return self.sent / self.total

    def to_payload(self) -> dict[str, Any]:
        """JSON-совместимый контракт для n8n/API."""
        return {
            "day": self.day.isoformat(),
            "total": self.total,
            "new": self.new,
            "sent": self.sent,
            "failed": self.failed,
            "other": self.other,
            "success_rate": round(self.success_rate, 4),
        }

    def to_text(self) -> str:
        """Текст для Telegram-канала/менеджера."""
        return (
            f"Отчёт за {self.day.isoformat()}\n"
            f"Всего лидов: {self.total}\n"
            f"Отправлено: {self.sent}\n"
            f"Не передано (failed): {self.failed}\n"
            f"В обработке (new): {self.new}\n"
            f"Прочие статусы: {self.other}\n"
            f"Доля успешных: {self.success_rate:.0%}"
        )


def build_daily_report(
    leads: Sequence[Mapping[str, Any]],
    *,
    day: date | None = None,
) -> DailyReport:
    """Посчитать сводку по заранее выбранным лидам.

    `leads` — результат `LeadRepository.list_leads(since=..., until=...)`, то есть
    функция не ходит в БД и не знает про n8n.
    """
    report_day = day or datetime.now(UTC).date()
    counts = {status.value: 0 for status in LeadStatus}
    for lead in leads:
        status = str(lead.get("status") or "")
        if status in counts:
            counts[status] += 1

    known = sum(counts.values())
    return DailyReport(
        day=report_day,
        total=len(leads),
        new=counts[LeadStatus.NEW.value],
        sent=counts[LeadStatus.SENT.value],
        failed=counts[LeadStatus.FAILED.value],
        other=len(leads) - known,
    )

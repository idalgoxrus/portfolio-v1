"""Диагностика окружения без сетевых вызовов.

Запуск из корня проекта:
    python scripts/check_env.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.exceptions import LeadBotError  # noqa: E402


def main() -> int:
    print(f"Корень проекта : {PROJECT_ROOT}")

    env_file = PROJECT_ROOT / ".env"
    print(f".env           : {'найден' if env_file.exists() else 'НЕ найден (скопируйте .env.example)'}")

    try:
        settings = get_settings()
    except LeadBotError as exc:
        print(f"Настройки      : ОШИБКА — {exc}")
        return 1

    print(f"BOT_TOKEN      : {'задан' if settings.is_bot_configured else 'НЕ задан'}")
    print(f"ADMIN_CHAT_ID  : {settings.admin_chat_id if settings.admin_chat_id else 'не задан'}")
    print(f"n8n webhook    : {settings.n8n_webhook_url or 'НЕ задан (лиды будут в статусе failed)'}")
    print(f"LOG_LEVEL      : {settings.log_level}")

    db_path = settings.resolved_database_path()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"База данных    : каталог недоступен ({exc})")
        return 1
    print(f"База данных    : {db_path}")

    ok = settings.is_bot_configured
    print("\nИтог:", "окружение готово к запуску" if ok else "не хватает BOT_TOKEN в .env")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

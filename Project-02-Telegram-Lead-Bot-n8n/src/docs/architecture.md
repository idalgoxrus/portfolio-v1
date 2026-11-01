# Архитектура Project #02 — Telegram Lead Bot + n8n

## 1. Задача

Telegram-бот собирает заявки (имя → телефон → комментарий → подтверждение), надёжно
сохраняет их и передаёт в n8n. n8n уведомляет менеджера, пишет данные в CRM/таблицу и
возвращает ответ боту. Потеря заявки при недоступности n8n недопустима.

## 2. Слои

| Слой | Модуль | Ответственность |
| --- | --- | --- |
| Telegram | `app/bot` | приём сообщений, FSM-анкета, клавиатуры, ответы пользователю |
| Точка входа бота | `app/bot/runner.py` | long polling, DI сервиса в диспетчер |
| Логика | `app/services` | оркестрация обработки лида, обращение к n8n |
| Интеграция | `app/services/n8n_client.py` | HTTP POST в webhook, retry/backoff, секрет |
| Домен | `app/models` | модель `Lead`, валидация, JSON-payload |
| Хранение | `app/storage` | SQLite: схема, вставка, статусы, выборки |
| Инфраструктура | `app/core` | настройки (`config.py`), логирование (`logging.py`), исключения (`exceptions.py`) |
| Правила/сервисы | `app/services/routing.py`, `followup.py`, `reporting.py` | маршрутизация, follow-up, суточная статистика (чистые функции) |
| HTTP-слой | `app/main.py` | FastAPI: `GET /health` + read-only админ-эндпоинты для n8n |
| Автоматизация | `n8n/workflows` | приём лида, CRM-синк, маршрутизация, напоминания, отчёт |

Правило зависимостей: `bot → services → storage / n8n_client`, все слои зависят от
`app/core`. Сервисный слой ничего не знает про aiogram и FastAPI, репозиторий — про HTTP.
Модель `Lead` — единственный контракт между ботом, БД и n8n.

`app/config.py` и `app/logging_setup.py` — совместимые реэкспорты `app/core/*`;
новая функциональность добавляется только в `app/core`.

## 3. Поток данных

```
Пользователь ──/start──► LeadForm.full_name
                          │ текст (валидация 2..120)
                          ▼
                        LeadForm.phone ── контакт или текст ── валидация через Lead
                          ▼
                        LeadForm.comment ── текст или «Пропустить»
                          ▼
                        LeadForm.confirm ── «Подтвердить»
                          ▼
        LeadService.register_lead()
             ├─ repository.add_lead()          → SQLite, статус new
             ├─ N8nClient.send_lead()          → POST webhook (retry/backoff)
             └─ repository.set_status()        → sent | failed
                          ▼
        Ответ пользователю с номером заявки
```

Статусы: `new` → `sent` (webhook ответил 2xx) | `failed` (нет URL или ошибка после
всех попыток). 3xx-редирект не считается успехом, постоянные 4xx не повторяются.
Заявка сохраняется **до** отправки, поэтому сбой интеграции не теряет лид.

## 4. Внешние контракты

- **Env** (валидируются в `app/core/config.py`): `BOT_TOKEN` — единственная обязательная
  переменная; её формат `<id>:<строка>` проверяется на старте (fail-fast до создания `Bot`).
  `N8N_WEBHOOK_URL`, `LOG_LEVEL`, `ADMIN_CHAT_ID`, `N8N_WEBHOOK_SECRET`, `ADMIN_API_TOKEN`,
  `HTTP_TIMEOUT`, `HTTP_RETRIES`, `DATABASE_PATH` — опциональные, со значениями по умолчанию.
  `.env.example` содержит полный список.
- **HTTP**: `GET /health` → `{"status": "ok"}` (открыт всегда). Read-only эндпоинты для n8n:
  `GET /leads` (фильтры `status`, `since`, `until`, `limit`), `GET /leads/{id}` (404, если нет),
  `GET /stats/daily` (суточная сводка), `GET /follow-ups` (лиды на follow-up). Все они
  защищены заголовком `X-Admin-Token`, если задан `ADMIN_API_TOKEN` (иначе открыты — для
  локального запуска).
- **Webhook наружу**: `POST` JSON с полями `telegram_id, full_name, phone, username,
  comment, source, status, created_at`; заголовки `X-Webhook-Source`, `X-Webhook-Token`.
- **Ответ webhook**: `2xx` = успех, `4xx/5xx` = повтор и затем статус `failed`.
- **БД**: таблица `leads` + индексы `telegram_id`, `status`.
- **Ошибки**: иерархия от `LeadBotError` (`app/core/exceptions.py`) — единая точка
  перехвата для точек входа; сбой интеграции не пробрасывается в обработчики aiogram.

## 5. Этапы разработки

| Этап | Содержание | Результат |
| --- | --- | --- |
| **0. Каркас** | конфиг, логи, исключения, модель, репозиторий, сервис, роутер бота, FastAPI + `/health`, n8n-заготовка, тесты, docs | запускаются и бот, и HTTP-слой |
| 1. Рабочий сбор лидов | реальный токен, прогон FSM, приём событий от n8n в FastAPI, уведомление админа | стабильный приём заявок |
| 2. Надёжность | outbox-повтор `failed`, идемпотентность, rate-limit/анти-спам | лиды не теряются и не дублируются |
| **3. n8n-автоматизация (MVP)** | воркфлоу CRM/Sheets, маршрутизация, follow-up + read-only API | лид доходит до менеджера и попадает в CRM по контракту |
| **4. Аналитика (MVP)** | `/stats/daily`, `/follow-ups`, ежедневный отчёт | управляемость по цифрам |
| 5. Эксплуатация | Docker, CI (ruff + pytest), миграции, Postgres, алерты | предсказуемый деплой |
| 6. Продукт | мультиязычность, вложения, оплата, реферальные ссылки | рост конверсии |

## 6. Карта файлов

| Путь | Назначение |
| --- | --- |
| `pyproject.toml` | метаданные и зависимости (runtime + dev), конфиг pytest/ruff |
| `requirements.txt` | зеркало зависимостей для быстрой установки |
| `.env.example` | базовые переменные окружения |
| `app/main.py` | FastAPI-приложение, `GET /health` (`uvicorn app.main:app`) |
| `app/bot/runner.py` | точка входа бота: long polling (`python -m app.bot.runner`) |
| `app/core/config.py` | безопасная загрузка настроек, валидация, `safe_dump()` |
| `app/core/logging.py` | базовая настройка logging |
| `app/core/exceptions.py` | `LeadBotError`, `ConfigurationError`, `IntegrationError`, `N8nDeliveryError` |
| `app/config.py`, `app/logging_setup.py` | совместимые реэкспорты (для старых импортов) |
| `app/models/lead.py` | `Lead`, `LeadStatus`, `normalize_phone` |
| `app/storage/repository.py` | схема SQLite и доступ к лидам |
| `app/services/lead_service.py` | сценарий обработки лида |
| `app/services/routing.py` | простое правило маршрутизации лида (queue/priority/tags) |
| `app/services/followup.py` | классификация «зависших» лидов для напоминаний |
| `app/services/reporting.py` | суточная статистика (`new`/`sent`/`failed`) и текст отчёта |
| `app/services/n8n_client.py` | webhook-клиент с повторами (реэкспорт `N8nDeliveryError`) |
| `app/bot/states.py` | состояния FSM |
| `app/bot/keyboards.py` | reply-клавиатуры |
| `app/bot/handlers.py` | обработчики и валидация шагов |
| `scripts/check_env.py` | диагностика окружения |
| `tests/test_config.py` | настройки: валидация, нормализация, маскирование секретов |
| `tests/test_lead_model.py` | валидация модели `Lead` |
| `tests/test_lead_service.py` | сценарий «сохранить → отправить → статус» (без сети) |
| `tests/test_bot_flow.py` | сквозной прогон FSM-анкеты на поддельной сессии `Bot` (без сети) |
| `tests/test_runner.py` | готовность точки входа бота: fail-fast без токена, сборка сервиса |
| `tests/test_smoke.py` | smoke-тест `GET /health` через `TestClient` |
| `n8n/workflows/lead_intake.json` | воркфлоу приёма лида |
| `n8n/workflows/crm_sync.json` | запись лида в CRM / Google Sheets (узел-заглушка до credentials) |
| `n8n/workflows/lead_routing.json` | маршрутизация лида по простому правилу |
| `n8n/workflows/lead_reminders.json` | cron-напоминания по «зависшим» лидам |
| `n8n/workflows/daily_report.json` | cron-отчёт по лидам за сутки |
| `tests/test_n8n_workflows.py` | статическая проверка n8n-воркфлоу (JSON, связи, секреты) |
| `tests/test_routing.py`, `tests/test_followup.py`, `tests/test_reporting.py` | unit-тесты правил и статистики |
| `tests/test_api_endpoints.py`, `tests/test_repository_queries.py` | тесты HTTP-эндпоинтов и выборок БД |
| `n8n/README.md` | инструкция по импорту и доработке воркфлоу |
| `data/`, `logs/` | рантайм-каталоги (содержимое игнорируется git) |
| `hello.py` | служебный файл ранних прогонов агента, не изменяется |

## 7. Ограничения каркаса (осознанные)

- Одна БД на процесс, без миграций — для этапа 0 достаточно.
- `failed`-лиды пока не переотправляются автоматически (этап 2).
- Приём событий от n8n в HTTP-слой не реализован; эндпоинты — только чтение.
- CRM/Google Sheets: воркфлоу и контракт готовы, узел записи — заглушка (нужны credentials).
- Маршрутизация — детерминированное правило, без AI-классификации (осознанно).
- Нет проверки `X-Webhook-Token` на стороне n8n (описано в `n8n/README.md`).
- Read-only эндпоинты открыты, если `ADMIN_API_TOKEN` не задан (локальный запуск).
- Нет Docker/CI (этап 5).

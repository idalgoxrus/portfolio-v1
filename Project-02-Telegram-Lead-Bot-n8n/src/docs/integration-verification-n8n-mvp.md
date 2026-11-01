# Integration Verification — MVP n8n workflows

Дата: 2026-09-26
Проверяемая ревизия: `bdb5b83` (Expand Project #02 MVP functionality)
Цель: доказать, что `lead_routing`, `lead_reminders`, `daily_report`, `crm_sync`
работают в реальном n8n, а не только в статических тестах.

## Как проверялось

- Отдельный **временный** n8n-контейнер (`n8n-verify`, порт 5679, собственный volume).
  Рабочий контейнер `n8n-local` не изменялся.
- Workflow импортировались файлами как есть (`n8n/workflows/*.json`), без правок.
- Тестовый HTTP-слой — то же FastAPI-приложение (`app.main`), порт 8010,
  отдельная SQLite с детерминированным набором лидов (вне репозитория).
- Реальные executions: production/test webhook и ручные запуски schedule-триггеров.
- Данные executions читались из API n8n и разворачивались из плоского формата n8n.

## Итог

| Workflow | Реальный прогон | Результат |
|---|---|---|
| CRM Sync | execution `success` (mode=webhook) | **PASS** |
| Lead Routing | цепочка узлов пройдена, mode=manual | **PASS** (логика) |
| Lead Reminders | цепочка узлов пройдена, mode=manual | **PASS** (логика) |
| Daily Report | цепочка узлов пройдена, mode=manual | **PASS** (логика) |

Общий вывод: **интеграция подтверждена**. Единственный незавершённый шаг во всех
workflow — доставка в Telegram.

> **Статус Telegram delivery:** в чистом тестовом n8n доставка **НЕ завершена**
> из-за отсутствия credential `telegramApi`. Это **конфигурационное ограничение
> окружения**, а **не подтверждённый дефект workflow**: логика узлов до шага
> отправки проверена на реальных executions. Реальный Telegram credential /
> API token в репозиторий **не добавлялся** и в файлах workflow отсутствует.

## Детали по workflow

### CRM Sync — PASS
Production webhook (`POST /webhook/crm-sync`) вернул:
`{"ok": true, "crm_target": "google_sheets", "external_id": "tg-777002-..."}`.
Узлы: Webhook → Code (Map Lead → CRM Record) → CRM (noOp-заглушка) → Respond.
`respondToWebhook` вернул смапленную запись. Workflow **активируется** в n8n.

### Lead Routing — PASS (логика)
Вход `POST /webhook/lead-routing`, лид с комментарием «срочно нужна консультация»:
Code-узел вернул
`{"route": "priority", "priority": "high", "reason": "keyword:срочно", "tags": ["hot", "срочно"]}`.
Цепочка соединений: Webhook → Code → Telegram → Respond.

### Lead Reminders — PASS (логика)
Ручной запуск schedule-триггера (`0 10 * * *`):
- `HTTP: получить лиды для follow-up` → `count=5`, бакеты `stale` (1), `remind` (2), `unresolved` (2);
- `IF: есть лиды на напоминание` → true;
- `Code: собрать сообщение` → готовый текст, например:
  `Follow-up: 5 лидов требуют внимания` + строки `#5 stale 100.3 ч`, `#4 remind 30.3 ч`,
  `#3 unresolved 3.3 ч, статус: failed`.

`/follow-ups` корректно исключает свежие лиды (в выборке нет лида возрастом 1–2 ч).
Правило бакетов совпало с ожидаемым.

### Daily Report — PASS (логика)
Ручной запуск schedule-триггера (`0 20 * * *`):
- `HTTP: получить статистику за сутки` → `{"day":"2026-09-26","total":4,"new":1,"sent":1,"failed":2,"success_rate":0.25}`;
- `Code: собрать отчёт` → текст:
  `Отчёт за 2026-09-26 / Всего лидов: 4 / Отправлено: 1 / Не передано (failed): 2 / В обработке (new): 1 / Доля успешных: 25%`.

## Найденное ограничение: Telegram credential блокирует активацию

В чистом n8n-инстансе (без credential) активация трёх workflow возвращает **400**:

```
Cannot publish workflow: 1 node have configuration issues:
Node "Telegram: ...": Missing required credential: telegramApi
```

Затронуты: Lead Routing, Lead Reminders, Daily Report. CRM Sync активируется (у него нет Telegram-узла).

Практические следствия:

1. **Секретов в файлах workflow нет** — это корректно (`README.md`: только `$env.*`).
   Telegram-узел ожидает credential `telegramApi`, который настраивается руками в n8n.
2. **Порядок настройки на новом инстансе обязателен: сначала credential, потом активация.**
   Пока credential нет, production-webhook `lead-routing` не регистрируется (404).
   Это же касается и вновь импортируемого `lead_intake.json` (у него та же модель Telegram-узла),
   т.е. поведение согласовано с уже существующим workflow.
3. `$env.TELEGRAM_ADMIN_CHAT_ID` в Telegram-узлах читается из окружения n8n и должен быть
   задан в контейнере (как в рабочем `n8n-local`).

## Соответствие контрактов API ↔ workflow

| Endpoint | Используется в | Ответ в проверке |
|---|---|---|
| `GET /stats/daily` | daily_report.json | `day,total,new,sent,failed,other,success_rate` |
| `GET /follow-ups` | lead_reminders.json | `generated_at,count,items[{lead_id,bucket,age_hours,phone,full_name,status}]` |
| `GET /leads` | — (доступен) | `count,items[...]` |
| `X-Admin-Token` | guard | без/с неверным токеном → **401** |

## Побочные наблюдения для n8n 2.40.7

- Логин принимает `emailOrLdapLoginId` (поле `email` устарело).
- Активация/деактивация/удаление workflow требуют `versionId`; ручной запуск —
  `triggerToStartFrom` (иначе `startNodes`/`destinationNode`).
- `n8n execute --id` в CLI не умеет стартовать с Schedule Trigger
  («Missing node to start execution»), поэтому schedule-воркфлоу проверялись
  ручным запуском через API.

## Что не проверялось

- Фактическая доставка сообщений в Telegram (нет credential/чата в тестовом инстансе).
- Реальная запись в Google Sheets/CRM: узел CRM — noOp-заглушка по проекту.

## Рекомендации

1. Перед активацией workflow на новом инстансе создавать Telegram credential.
2. При желании сделать проверку полностью автономной — добавить в тестовый контур
   фиктивный credential или переключаемый noOp-режим Telegram-узла
   (изменение кода, вне рамок текущей задачи).

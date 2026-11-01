# Project #02 — Telegram Lead Bot + n8n

**Telegram lead capture · Workflow automation · Google Sheets CRM**

## 🇷🇺 Русская версия

### О проекте
Telegram-бот для автоматизированного сбора заявок от клиентов. Бот последовательно запрашивает имя, телефон и комментарий, показывает данные для подтверждения и сохраняет заявку локально. Затем отправляет её в n8n для дальнейшей обработки.

### Возможности
- Пошаговая форма сбора заявок в Telegram.
- Подтверждение введённых данных перед отправкой.
- Локальное хранение заявок в SQLite.
- Передача заявок в n8n через webhook.
- Маршрутизация заявок по содержанию комментария и источнику.
- Уведомление менеджера в Telegram с очередью и приоритетом.
- Запись заявок в Google Sheets CRM.
- Обработка ошибок при передаче заявок.
- Автоматизированные тесты основных сценариев.

### Технологии
Python · aiogram 3 · SQLite · n8n · Google Sheets API · Telegram Bot API · pytest

### Архитектура
`Клиент в Telegram → Python-бот → SQLite → n8n Telegram Lead Intake → Lead Routing → уведомление менеджера и Google Sheets CRM`

### Результаты проверки
- Telegram-бот запущен и проверен вручную.
- Полный сценарий создания и подтверждения заявки пройден.
- n8n успешно обработал тестовую заявку.
- Уведомление менеджеру получено в Telegram.
- Тестовая заявка записана в Google Sheets CRM.
- Оба workflow — `Telegram Lead Intake` и `Lead Routing` — успешно выполнились в реальном E2E-тесте.
- Маршрутизация проверена: тестовая заявка с комментарием «Нужна консультация по вашим услугам» получила `route: priority` и `priority: high`.
- Бот подтвердил приём заявки №8.
- В предыдущем аудите проекта: **98 тестов пройдены**, Ruff без замечаний, проверка компиляции Python завершилась успешно.

### Текущий статус
**Рабочий портфолио-проект.** Приём заявок, передача в n8n, маршрутизация, уведомление менеджера и запись в Google Sheets CRM проверены на практике.

Ранее в одном из тестов маршрутизация возвращала `route: unknown` и `reason: routing_unavailable`. После публикации workflow `Lead Routing` проведён повторный полный тест через Telegram-бота: маршрутизация успешно вернула `priority/high`, оба workflow завершились успешно. Предыдущая проблема устранена.

### Безопасность
- Не публиковать Telegram-токены, секреты и содержимое `.env`.
- Не включать базу данных с реальными заявками в публичный архив.
- Использовать отдельную тестовую CRM для демонстрации.
- Перед публикацией проверить файлы проекта и историю Git на наличие секретов.

### Скриншоты
См. папку `screenshots/` в этом пакете.

---

## 🇬🇧 English Version

### About the Project
A Telegram bot that automates customer lead collection. It asks for the customer's name, phone number, and comment, displays the collected information for confirmation, and stores the lead locally. The lead is then sent to n8n for further processing.

### Features
- Step-by-step lead collection through Telegram.
- Confirmation before submission.
- Local lead storage in SQLite.
- Webhook integration with n8n.
- Lead routing based on the comment and source.
- Telegram manager notifications with routing queue and priority.
- Google Sheets CRM integration.
- Error handling during lead delivery.
- Automated tests for core scenarios.

### Tech Stack
Python · aiogram 3 · SQLite · n8n · Google Sheets API · Telegram Bot API · pytest

### Architecture
`Telegram user → Python bot → SQLite → n8n Telegram Lead Intake → Lead Routing → manager notification and Google Sheets CRM`

### Verification Results
- The Telegram bot was launched and tested manually.
- The complete lead submission and confirmation flow was tested.
- n8n successfully processed a test lead.
- The manager received a Telegram notification.
- The test lead was recorded in Google Sheets CRM.
- Both workflows, `Telegram Lead Intake` and `Lead Routing`, completed successfully in a real end-to-end test.
- Lead routing was verified: a test lead with the comment “I need a consultation about your services” received `route: priority` and `priority: high`.
- The bot confirmed that lead #8 had been accepted.
- Previous project audit: **98 tests passed**, Ruff reported no issues, and Python compilation checks completed successfully.

### Project Status
**Working portfolio project.** Lead collection, n8n delivery, routing, manager notification, and Google Sheets CRM recording have been tested in practice.

An earlier test returned `route: unknown` and `reason: routing_unavailable`. After publishing the `Lead Routing` workflow, a new full test through the Telegram bot confirmed successful routing with `priority/high`; both workflows completed successfully. The earlier issue is resolved.

### Security
- Never publish Telegram bot tokens, credentials, or `.env` contents.
- Do not include databases containing real customer information in public archives.
- Use a separate test CRM for demonstrations.
- Check project files and Git history for secrets before publication.

### Screenshots
See the `screenshots/` folder in this package.

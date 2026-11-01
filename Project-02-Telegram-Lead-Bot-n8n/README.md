# Project #2 — Telegram Lead Bot + n8n

**Telegram lead capture · Workflow automation · Google Sheets CRM**

## 🇷🇺 Русская версия

### О проекте

Telegram-бот для автоматизированного сбора и обработки заявок клиентов. Бот последовательно запрашивает имя, телефон и комментарий, показывает собранные данные для подтверждения и передаёт заявку в n8n для дальнейшей обработки.

### Возможности

- Пошаговая форма сбора заявок в Telegram.
- Подтверждение введённых данных перед отправкой.
- Локальное хранение заявок в SQLite.
- Передача заявок в n8n через webhook.
- Маршрутизация заявки по заданным правилам.
- Уведомление менеджера в Telegram.
- Запись заявок в Google Sheets CRM.
- Обработка ошибок при передаче заявок.
- Автоматизированные тесты основных сценариев.

### Технологии

Python · aiogram 3 · SQLite · n8n · Google Sheets API · Telegram Bot API · pytest

### Архитектура

`Клиент в Telegram → Python-бот → SQLite → n8n webhook → обработка и маршрутизация → уведомление менеджера и Google Sheets CRM`

### Результаты проверки

- Telegram-бот запущен и проверен вручную.
- Полный сценарий создания и подтверждения заявки пройден.
- n8n успешно обработал тестовую заявку.
- Проверена маршрутизация тестовой заявки с высоким приоритетом.
- Уведомление менеджеру получено в Telegram.
- Тестовая заявка появилась в Google Sheets CRM.
- Последний зафиксированный результат автоматизированного набора: **249 тестов пройдены**.

Результаты относятся к проверенным тестовым сценариям и не являются гарантией поведения при любых внешних сбоях или конфигурациях.

### Статус проекта

**Рабочий завершённый портфолио-проект.** Основной сценарий сбора заявки, передачи в n8n, обработки, маршрутизации, уведомления и записи в CRM проверен.

### Скриншоты

- [Форма сбора заявки](screenshots/01_Telegram_Lead_Form.jpg)
- [Подтверждение заявки](screenshots/02_Telegram_Lead_Confirmation.jpg)
- [Запись в Google Sheets CRM](screenshots/03_Google_Sheets_CRM.jpg)
- [Исполнение n8n workflow](screenshots/04_n8n_Workflow_Execution.jpg)
- [Итоговая запись CRM](screenshots/05_Google_Sheets_CRM_Final.jpg)
- [Общая схема workflow](Project02_Telegram_Lead_Intake_Workflow.jpg)

### Технические материалы

- [`src/`](src/) — исходный код приложения и тесты.
- [`src/docs/architecture.md`](src/docs/architecture.md) — описание архитектуры.
- [`src/docs/integration-verification-n8n-mvp.md`](src/docs/integration-verification-n8n-mvp.md) — отчёт проверки интеграции.
- [`src/n8n/workflows/`](src/n8n/workflows/) — демонстрационные экспорты n8n.

### Безопасность

- Не публиковать Telegram-токены, секреты и содержимое `.env`.
- Не включать базы данных с реальными заявками.
- Использовать отдельную тестовую CRM для демонстрации.
- Перед публикацией проверять исходники и историю Git на наличие секретов.

---

## 🇬🇧 English Version

### About the Project

A Telegram bot that automates customer lead collection and processing. It asks for the customer's name, phone number, and comment, displays the collected information for confirmation, and sends the lead to n8n for further processing.

### Features

- Step-by-step lead collection through Telegram.
- Confirmation before submission.
- Local lead storage in SQLite.
- Webhook integration with n8n.
- Rule-based lead routing.
- Telegram notifications for the manager.
- Google Sheets CRM integration.
- Error handling during lead delivery.
- Automated tests for core scenarios.

### Tech Stack

Python · aiogram 3 · SQLite · n8n · Google Sheets API · Telegram Bot API · pytest

### Architecture

`Telegram user → Python bot → SQLite → n8n webhook → processing and routing → manager notification and Google Sheets CRM`

### Verification Results

- The Telegram bot was launched and tested manually.
- The complete lead submission and confirmation flow was tested.
- n8n successfully processed a test lead.
- High-priority routing was verified with a test lead.
- The manager received a Telegram notification.
- The test lead was recorded in Google Sheets CRM.
- The latest recorded automated test-suite result: **249 tests passed**.

These results apply to the tested scenarios and do not guarantee behavior under every possible external failure or configuration.

### Project Status

**Completed working portfolio project.** The main flow covering lead capture, n8n delivery, processing, routing, manager notification, and CRM logging has been verified.

### Screenshots

- [Telegram lead form](screenshots/01_Telegram_Lead_Form.jpg)
- [Lead confirmation](screenshots/02_Telegram_Lead_Confirmation.jpg)
- [Google Sheets CRM record](screenshots/03_Google_Sheets_CRM.jpg)
- [n8n workflow execution](screenshots/04_n8n_Workflow_Execution.jpg)
- [Final CRM record](screenshots/05_Google_Sheets_CRM_Final.jpg)
- [Workflow overview](Project02_Telegram_Lead_Intake_Workflow.jpg)

### Technical Materials

- [`src/`](src/) — application source code and tests.
- [`src/docs/architecture.md`](src/docs/architecture.md) — architecture description.
- [`src/docs/integration-verification-n8n-mvp.md`](src/docs/integration-verification-n8n-mvp.md) — integration verification report.
- [`src/n8n/workflows/`](src/n8n/workflows/) — n8n demonstration exports.

### Security

- Never publish Telegram bot tokens, credentials, or `.env` contents.
- Do not include databases containing real customer information.
- Use a separate test CRM for demonstrations.
- Check project files and Git history for secrets before publication.

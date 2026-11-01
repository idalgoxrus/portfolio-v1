# AI & Automation Developer Portfolio

**Python · Telegram Bots · WhatsApp Automation · n8n · AI Integrations**

Практическое портфолио проектов по автоматизации клиентской поддержки, сбору заявок, интеграции мессенджеров и AI-обработке обращений.

A practical portfolio of projects covering customer support automation, lead capture, messaging integrations, and AI-assisted customer conversations.

---

## 🇷🇺 Русская версия

### Проекты

| № | Проект | Что демонстрирует | Технологии |
|---|---|---|---|
| 01 | [Telegram Customer Support Bot](Project-01-Telegram-Customer-Support-Bot/README.md) | Меню услуг и цен, FAQ, приём заявок | Python, Telegram Bot API, SQLite |
| 02 | [Telegram Lead Bot + n8n](Project-02-Telegram-Lead-Bot-n8n/README.md) | Сбор заявок, маршрутизация, CRM и автоматизация | Python, aiogram, n8n, Google Sheets |
| 03 | [WhatsApp Business Bot](Project-03-WhatsApp-Business-Bot/README.md) | Реальная обработка сообщений WhatsApp и автоматические ответы | Python, FastAPI, Evolution API |
| 04 | [AI Sales Assistant](Project-04-AI-Sales-Assistant/README.md) | AI-обработка обращений WhatsApp, CRM, уведомления менеджеру | n8n, DeepSeek, Evolution API, Google Sheets, Telegram |

### Что находится в репозитории

- `src/` — выбранные исходные файлы приложений и безопасные примеры конфигурации.
- `tests/` — автоматические тесты там, где они включены в пакет проекта.
- `docs/` — архитектурные описания и отчёты о проверках.
- `workflows/` или `workflow/` — демонстрационные экспорты n8n, очищенные от credentials.
- `screenshots/` — скриншоты реальной работы и интерфейсов.

Состав папок зависит от конкретного проекта; подробности указаны в README соответствующего проекта.

### Проверка и результаты

В документации отдельно указаны автоматические тесты и реальные end-to-end проверки. Результаты относятся только к описанным сценариям и не означают, что все возможные условия эксплуатации проверены.

### Безопасность

Публичная версия не должна содержать действующие токены, API-ключи, пароли, `.env` с реальными значениями, личные базы данных, приватные журналы или данные клиентов. Примеры конфигурации используют placeholders. Экспорты workflow предназначены для ознакомления и требуют настройки в отдельном тестовом окружении.

---

## 🇬🇧 English Version

### Projects

| # | Project | What it demonstrates | Technology |
|---|---|---|---|
| 01 | [Telegram Customer Support Bot](Project-01-Telegram-Customer-Support-Bot/README.md) | Service and price menus, FAQ, lead intake | Python, Telegram Bot API, SQLite |
| 02 | [Telegram Lead Bot + n8n](Project-02-Telegram-Lead-Bot-n8n/README.md) | Lead capture, routing, CRM, and automation | Python, aiogram, n8n, Google Sheets |
| 03 | [WhatsApp Business Bot](Project-03-WhatsApp-Business-Bot/README.md) | Real WhatsApp message handling and automated replies | Python, FastAPI, Evolution API |
| 04 | [AI Sales Assistant](Project-04-AI-Sales-Assistant/README.md) | AI-assisted WhatsApp inquiries, CRM, and manager alerts | n8n, DeepSeek, Evolution API, Google Sheets, Telegram |

### Repository contents

- `src/` — selected application source files and safe configuration examples.
- `tests/` — automated tests where included in the project package.
- `docs/` — architecture notes and verification reports.
- `workflows/` or `workflow/` — n8n demonstration exports with credential bindings removed.
- `screenshots/` — screenshots of application behavior and interfaces.

Folder contents vary by project; see each project's README for details.

### Verification and results

The documentation distinguishes automated tests from real end-to-end checks. Results apply only to the scenarios explicitly described and do not imply that every possible production condition has been tested.

### Security

The public version must not contain live tokens, API keys, passwords, real `.env` values, private databases, internal logs, or customer data. Configuration examples use placeholders. Workflow exports are provided for review and require configuration in a separate test environment.

---

*Project documentation is available in Russian and English.*

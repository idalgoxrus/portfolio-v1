# Project #4 — AI Sales Assistant
## AI Sales Assistant for WhatsApp & Telegram

**Статус / Status:** Portfolio project — real end-to-end test passed  
**Языки / Languages:** Русский / English

---

# 🇷🇺 Русская версия

## 1. О проекте

**AI Sales Assistant** — AI-ассистент для автоматизации общения с клиентами через WhatsApp и Telegram. Проект использует n8n для управления процессами, DeepSeek для обработки сообщений и Google Sheets в качестве CRM.

Ассистент помогает обрабатывать входящие обращения, формировать ответы, сохранять данные о клиентах и передавать ситуации, требующие внимания, менеджеру.

## 2. Основные возможности

- Приём входящих сообщений через интеграцию с WhatsApp.
- Обработка событий и определение типа сообщения.
- Использование AI для анализа обращений и подготовки ответов.
- Хранение информации о клиентах в Google Sheets.
- Ведение журнала диалогов.
- Уведомление менеджера через Telegram, когда требуется вмешательство.
- Проверка статуса отправки ответа и обработка результата API.
- Защита от повторной обработки сообщений с помощью SQLite и TTL-механизма.

## 3. Архитектура

Основной поток обработки:

1. Клиент отправляет сообщение в WhatsApp.
2. Evolution API передаёт событие в webhook n8n.
3. Workflow проверяет событие и тип сообщения.
4. AI-компоненты анализируют обращение и формируют ответ.
5. Google Sheets используется для работы с CRM и журналом сообщений.
6. Ответ отправляется клиенту через Evolution API.
7. При необходимости менеджер получает уведомление в Telegram.

### Компоненты проекта

- **n8n** — автоматизация workflow.
- **Evolution API** — интеграция с WhatsApp.
- **DeepSeek** — AI-обработка сообщений.
- **Google Sheets** — CRM и журнал диалогов.
- **SQLite** — хранение данных для дедупликации.
- **Telegram Bot API** — уведомления менеджеру.

## 4. Используемые технологии

| Технология | Назначение |
|---|---|
| n8n | Автоматизация и маршрутизация |
| Evolution API | WhatsApp-интеграция |
| DeepSeek | Обработка сообщений с помощью AI |
| Google Sheets | CRM и журнал сообщений |
| SQLite | Дедупликация сообщений |
| Telegram Bot API | Уведомления менеджеру |
| Docker | Контейнерное окружение |

## 5. Проверенные результаты

В ходе реального end-to-end теста:

- Сообщение «Привет» было отправлено с другого WhatsApp-аккаунта.
- Входящее событие было получено и обработано workflow.
- Бот подготовил ответ.
- Evolution API принял запрос на отправку.
- Автоматический ответ был реально получен на втором WhatsApp-аккаунте.
- В Google Sheets появилась запись о лиде.

Также проверялись CRM, журнал сообщений, дедупликация и уведомления менеджеру в Telegram.

**Важно:** принятие сообщения API и подтверждение доставки — разные состояния. Статус `PENDING` сам по себе не означает подтверждённую доставку. Факт получения автоматического ответа во время end-to-end теста подтверждён отдельно.

## 6. Структура CRM

Google Sheets CRM содержит разделы для бизнес-информации, продуктов, FAQ, журнала диалогов и лидов.

В таблице лидов используются поля для контактных данных, статуса, языка, источника, намерения клиента, последнего сообщения и времени последнего контакта.

## 7. Безопасность и конфигурация

Для запуска интеграций необходимы собственные учётные данные и настроенное окружение.

- Не храните API-ключи, токены и пароли в публичном репозитории.
- Используйте собственные credentials в n8n.
- Не публикуйте реальные контактные данные клиентов.
- Перед использованием в production проверьте настройки доступа и политику хранения данных.

Файл экспорта workflow предназначен для ознакомления с архитектурой. Для реального запуска могут потребоваться настройка credentials, webhook-адресов и интеграций.

## 8. Возможное применение

Проект может служить основой для:

- автоматизации первичных ответов клиентам;
- сбора и регистрации лидов;
- поддержки продаж через мессенджеры;
- передачи обращений менеджеру;
- ведения централизованного журнала коммуникаций.

---

# 🇬🇧 English Version

## 1. About the Project

**AI Sales Assistant** is an AI-powered assistant designed to handle incoming customer inquiries through WhatsApp. Telegram is used for manager notifications. The project uses n8n for workflow automation, DeepSeek for AI-powered message processing, and Google Sheets as a lightweight CRM.

The assistant helps process incoming inquiries, generate responses, maintain customer records, and notify a manager when a conversation requires human attention.

## 2. Key Features

- Receives incoming WhatsApp messages through an integration.
- Processes incoming events and identifies message types.
- Uses AI to analyze customer inquiries and prepare responses.
- Stores lead information in Google Sheets.
- Maintains a conversation log.
- Sends Telegram notifications when human intervention is required.
- Tracks API response and message-acceptance status.
- Uses SQLite and a TTL mechanism to prevent duplicate message processing.

## 3. Architecture

The main processing flow:

1. A customer sends a WhatsApp message.
2. Evolution API forwards the event to an n8n webhook.
3. The workflow validates the event and identifies the message type.
4. AI components analyze the inquiry and generate a response.
5. Google Sheets stores CRM data and conversation records.
6. The response is sent through Evolution API.
7. A manager receives a Telegram notification when necessary.

### Core Components

- **n8n** — workflow automation.
- **Evolution API** — WhatsApp integration.
- **DeepSeek** — AI-powered message processing.
- **Google Sheets** — CRM and conversation log.
- **SQLite** — duplicate-message prevention.
- **Telegram Bot API** — manager notifications.

## 4. Technology Stack

| Technology | Purpose |
|---|---|
| n8n | Workflow automation and routing |
| Evolution API | WhatsApp integration |
| DeepSeek | AI message processing |
| Google Sheets | CRM and conversation logging |
| SQLite | Message deduplication |
| Telegram Bot API | Manager notifications |
| Docker | Containerized environment |

## 5. Verified Results

During a real end-to-end test:

- A second WhatsApp account sent the message “Привет”.
- The incoming event reached and was processed by the workflow.
- The bot generated a response.
- Evolution API accepted the outgoing request.
- The automated reply was actually received by the second WhatsApp account.
- A lead record appeared in Google Sheets.

CRM operations, conversation logging, deduplication, and Telegram manager notifications were also tested.

**Important:** API acceptance and confirmed delivery are different states. A `PENDING` status alone does not confirm delivery. Receipt of the automated reply during the end-to-end test was verified separately.

## 6. CRM Structure

The Google Sheets CRM includes sections for business information, products, FAQs, conversation logs, and leads.

The leads table tracks contact information, status, language, source, customer intent, last message, and last-contact time.

## 7. Security and Configuration

Running the integrations requires your own credentials and a configured environment.

- Never commit API keys, tokens, or passwords to a public repository.
- Configure your own credentials in n8n.
- Do not publish real customer contact details.
- Review access controls and data-retention settings before production use.

The exported workflow is provided to demonstrate the project architecture. Running it may require configuring credentials, webhook URLs, and integrations.

## 8. Potential Use Cases

The project can serve as a foundation for:

- automating initial customer responses;
- capturing and registering leads;
- supporting sales through messaging platforms;
- routing inquiries to a human manager;
- maintaining a centralized communication log.

---

**Project #4 — AI Sales Assistant**  
*Portfolio project demonstrating workflow automation, AI integration, CRM operations, messaging integrations, and end-to-end testing.*

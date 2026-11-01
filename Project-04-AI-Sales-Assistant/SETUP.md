# Project #4 — AI Sales Assistant
# SETUP / ИНСТРУКЦИЯ ПО НАСТРОЙКЕ

Этот документ описывает общую последовательность подготовки проекта к запуску. Конкретные адреса, credentials и параметры зависят от вашего окружения.

---

# 🇷🇺 Русская версия

## 1. Что потребуется

- Установленный и доступный n8n.
- Evolution API с настроенной интеграцией WhatsApp.
- Аккаунт Google с доступом к Google Sheets.
- Telegram-бот для уведомлений менеджеру.
- API-доступ к используемой AI-модели DeepSeek.
- Доступ к Docker, если окружение разворачивается в контейнерах.

## 2. Перед импортом

1. Используйте тестовый экземпляр n8n или резервную копию, а не рабочий production workflow.
2. Сохраните JSON-файл workflow локально.
3. Убедитесь, что в вашем окружении настроены необходимые сервисы и есть доступ к ним.
4. Не публикуйте реальные токены, пароли, номера клиентов и другие приватные данные.

## 3. Импорт workflow в n8n

1. Откройте свой экземпляр n8n.
2. Используйте функцию импорта workflow из JSON-файла.
3. Импортируйте workflow в тестовое окружение.
4. До активации проверьте все узлы, webhook-пути, соединения и настройки интеграций.
5. Не включайте workflow, пока не настроены credentials и не завершены тесты.

> Важно: импортируемый workflow может потребовать ручной настройки. Наличие JSON-файла не гарантирует готовность к запуску в другом окружении.

## 4. Настройка подключений

### DeepSeek
- Создайте или используйте собственный API-ключ.
- Добавьте credentials в n8n.
- Выберите их в соответствующем AI-узле.
- Проверьте доступность модели тестовым запросом.

### Google Sheets
- Подключите Google account через поддерживаемый механизм авторизации n8n.
- Укажите собственные таблицы и листы CRM.
- Проверьте названия колонок и права доступа.
- Убедитесь, что тестовые данные записываются только в тестовую таблицу.

### Evolution API / WhatsApp
- Настройте Evolution API и подключите отдельный тестовый WhatsApp-аккаунт.
- Укажите URL вашего сервиса и необходимые credentials в n8n.
- Настройте webhook для нужного события и проверьте входящее сообщение.
- Сначала используйте тестовый номер, не клиентскую переписку.

### Telegram
- Создайте Telegram-бота и настройте credentials в n8n.
- Укажите целевой чат менеджера.
- Проверьте отправку тестового уведомления.

## 5. Webhook и URL

Webhook-адреса и внутренние URL зависят от окружения. После импорта проверьте их в каждом соответствующем узле. Не копируйте адреса локальной или тестовой среды в production без проверки.

## 6. Проверка перед активацией

- [ ] Все необходимые credentials подключены.
- [ ] Google Sheets указывает на тестовую CRM.
- [ ] Входящий webhook получает тестовое сообщение.
- [ ] AI-узел успешно обрабатывает тестовый запрос.
- [ ] Отправка ответа проверена на тестовом аккаунте.
- [ ] Telegram-уведомление проверено.
- [ ] Дедупликация и обработка повторных событий проверены.
- [ ] В логах нет токенов и других секретов.
- [ ] Настроены доступы и правила хранения персональных данных.

Активируйте workflow только после успешного завершения проверок.

## 7. Безопасность

- Не помещайте реальные credentials в README, SETUP или публичный JSON.
- Не загружайте в публичный репозиторий клиентские данные, рабочие логи или базы данных.
- Используйте минимально необходимые права доступа.
- Храните резервную копию конфигурации в безопасном месте.
- Проверяйте соответствие обработки персональных данных применимым требованиям.

## 8. Ограничения

Эта инструкция является общей. Точные названия узлов, webhook-пути, поля Google Sheets и параметры API могут различаться между версиями workflow и окружениями. Для настройки конкретного экземпляра используйте его актуальную конфигурацию и документацию используемых сервисов.

---

# 🇬🇧 English Version

## 1. Requirements

- An installed and accessible n8n instance.
- Evolution API configured for WhatsApp integration.
- A Google account with access to Google Sheets.
- A Telegram bot for manager notifications.
- API access to the selected DeepSeek model.
- Docker access if the environment is containerized.

## 2. Before Importing

1. Use a test n8n instance or a backup, not a live production workflow.
2. Save the workflow JSON file locally.
3. Ensure the required services are configured and reachable.
4. Never publish real tokens, passwords, customer phone numbers, or other private data.

## 3. Importing the Workflow into n8n

1. Open your n8n instance.
2. Use the workflow import function to import the JSON file.
3. Import the workflow into a test environment.
4. Before activation, review all nodes, webhook paths, connections, and integration settings.
5. Do not activate the workflow until credentials are configured and tests are complete.

> Important: the imported workflow may require manual configuration. Having a JSON file does not guarantee that it will run in another environment without changes.

## 4. Configure Integrations

### DeepSeek
- Create or use your own API key.
- Add the credentials in n8n.
- Select them in the relevant AI node.
- Test model access with a sample request.

### Google Sheets
- Connect your Google account using a supported n8n authorization method.
- Select your own CRM spreadsheet and sheets.
- Verify column names and access permissions.
- Ensure test data is written only to a test spreadsheet.

### Evolution API / WhatsApp
- Configure Evolution API and connect a separate test WhatsApp account.
- Enter your service URL and required credentials in n8n.
- Configure the webhook for the required event and test an incoming message.
- Use a test number first, not customer conversations.

### Telegram
- Create a Telegram bot and configure its credentials in n8n.
- Set the manager's target chat.
- Verify that a test notification can be sent.

## 5. Webhooks and URLs

Webhook addresses and internal URLs depend on the environment. Review them in every relevant node after import. Do not copy URLs from a local or test environment into production without verifying them.

## 6. Pre-activation Checklist

- [ ] All required credentials are configured.
- [ ] Google Sheets points to a test CRM.
- [ ] The incoming webhook receives a test message.
- [ ] The AI node processes a test request successfully.
- [ ] Outgoing replies are tested with a test account.
- [ ] Telegram notifications are tested.
- [ ] Deduplication and repeated-event handling are tested.
- [ ] Logs do not expose tokens or other secrets.
- [ ] Access permissions and personal-data retention rules are configured.

Activate the workflow only after all checks pass.

## 7. Security

- Do not place real credentials in README, SETUP, or public workflow JSON files.
- Do not upload customer data, production logs, or databases to a public repository.
- Use the minimum permissions required.
- Keep configuration backups in a secure location.
- Ensure personal-data processing complies with applicable requirements.

## 8. Limitations

This is a general setup guide. Exact node names, webhook paths, Google Sheets fields, and API parameters may vary across workflow versions and environments. Use the current configuration of your instance and the documentation for the services you use.

---

**Project #4 — AI Sales Assistant**  
*Setup guide for a portfolio workflow. Test in an isolated environment before any production use.*

import logging
import os
import re
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "bot.db")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

NAME, CONTACT, QUESTION = range(3)

# Пункты главного меню — единый источник подписей кнопок.
# Используются и в клавиатуре, и в фильтрах сообщений,
# чтобы текст кнопок и правила их обработки не расходились.
BTN_SERVICES = "🛠 Услуги"
BTN_PRICES = "💰 Цены"
BTN_FAQ = "❓ FAQ"
BTN_REQUEST = "📝 Оставить заявку"
BTN_CONTACTS = "📞 Контакты"

MENU_BUTTONS = (BTN_SERVICES, BTN_PRICES, BTN_FAQ, BTN_REQUEST, BTN_CONTACTS)

MAIN_MENU = [
    [BTN_SERVICES, BTN_PRICES],
    [BTN_FAQ, BTN_REQUEST],
    [BTN_CONTACTS],
]


def menu_button_regex(label):
    """Regex для точного совпадения текста кнопки меню."""
    return rf"^{re.escape(label)}$"


def not_menu_button_regex():
    """Regex текста, который не является пунктом меню.

    Сохраняет прежнее поведение: отклоняет точные подписи кнопок
    (как с эмодзи, так и без них) и требует хотя бы один символ.
    """
    alternatives = []
    for label in MENU_BUTTONS:
        emoji, _, text = label.partition(" ")
        alternatives.append(rf"{re.escape(emoji)}\s*{re.escape(text)}$")
    for label in MENU_BUTTONS:
        alternatives.append(rf"{re.escape(label.partition(' ')[2])}$")
    return rf"^(?!{'|'.join(alternatives)}).+"


NOT_MENU_REGEX = not_menu_button_regex()


def admin_chat_id():
    try:
        return int(ADMIN_CHAT_ID_RAW) if ADMIN_CHAT_ID_RAW else None
    except ValueError:
        return None


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER,
                username TEXT,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                question TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_request(user_id, username, name, contact, question):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO requests
            (telegram_user_id, username, name, contact, question, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                name,
                contact,
                question,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cur.lastrowid


def menu_markup():
    return ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Здравствуйте! 👋\n\nЯ бот-помощник. Выберите нужный раздел:",
        reply_markup=menu_markup(),
    )
    return ConversationHandler.END


async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 Наши услуги:\n\n"
        "• Создание Telegram-ботов\n"
        "• Автоматизация через n8n\n"
        "• Интеграция API\n"
        "• WhatsApp-автоматизация\n"
        "• AI-ассистенты\n"
        "• Интеграции с таблицами и CRM",
        reply_markup=menu_markup(),
    )


async def prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 Примерные пакеты:\n\n"
        "Starter — от 50 €\n"
        "Automation — от 100 €\n"
        "AI / API integration — от 200 €\n\n"
        "Точная стоимость зависит от задачи.",
        reply_markup=menu_markup(),
    )


async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ FAQ\n\n"
        "Можно ли подключить бота к Google Sheets? — Да.\n\n"
        "Можно ли использовать n8n? — Да.\n\n"
        "Можно ли подключить AI? — Да.\n\n"
        "Можно ли передать диалог оператору? — Да, это можно добавить в workflow.",
        reply_markup=menu_markup(),
    )


async def contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 Контакты\n\nДля связи оставьте заявку через кнопку «📝 Оставить заявку».",
        reply_markup=menu_markup(),
    )


async def request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📝 Отлично. Оставим заявку.\n\nКак вас зовут?",
        reply_markup=menu_markup(),
    )
    return NAME


async def request_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Укажите Telegram, телефон или другой удобный контакт:")
    return CONTACT


async def request_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["contact"] = update.message.text.strip()
    await update.message.reply_text("Коротко опишите вашу задачу:")
    return QUESTION


async def request_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()
    user = update.effective_user
    name = context.user_data.get("name", "")
    contact = context.user_data.get("contact", "")

    request_id = save_request(
        user.id if user else None,
        user.username if user else None,
        name,
        contact,
        question,
    )

    admin_id = admin_chat_id()
    if admin_id:
        username = f"@{user.username}" if user and user.username else "не указан"
        admin_text = (
            f"🔔 Новая заявка #{request_id}\n\n"
            f"Имя: {name}\n"
            f"Контакт: {contact}\n"
            f"Telegram: {username}\n"
            f"Задача: {question}"
        )
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception:
            logger.exception("Не удалось отправить уведомление админу")

    context.user_data.clear()
    await update.message.reply_text(
        f"✅ Заявка #{request_id} принята!\n\nМы свяжемся с вами по указанному контакту.",
        reply_markup=menu_markup(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Заявка отменена.", reply_markup=menu_markup())
    return ConversationHandler.END


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите пункт меню или нажмите /start.", reply_markup=menu_markup()
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Необработанная ошибка при обработке обновления", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Произошла ошибка. Попробуйте ещё раз или нажмите /start."
            )
        except Exception:
            logger.exception("Не удалось отправить сообщение об ошибке")


def build_app():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    app = Application.builder().token(BOT_TOKEN).build()

    request_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(menu_button_regex(BTN_REQUEST)), request_start),
        ],
        states={
            NAME: [MessageHandler(filters.Regex(NOT_MENU_REGEX) & ~filters.COMMAND, request_name)],
            CONTACT: [MessageHandler(filters.Regex(NOT_MENU_REGEX) & ~filters.COMMAND, request_contact)],
            QUESTION: [MessageHandler(filters.Regex(NOT_MENU_REGEX) & ~filters.COMMAND, request_question)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(menu_button_regex(BTN_SERVICES)), services),
            MessageHandler(filters.Regex(menu_button_regex(BTN_PRICES)), prices),
            MessageHandler(filters.Regex(menu_button_regex(BTN_FAQ)), faq),
            MessageHandler(filters.Regex(menu_button_regex(BTN_CONTACTS)), contacts),
            MessageHandler(filters.Regex(menu_button_regex(BTN_REQUEST)), request_start),
        ],
    )

    app.add_handler(request_handler)
    app.add_handler(MessageHandler(filters.Regex(menu_button_regex(BTN_SERVICES)), services))
    app.add_handler(MessageHandler(filters.Regex(menu_button_regex(BTN_PRICES)), prices))
    app.add_handler(MessageHandler(filters.Regex(menu_button_regex(BTN_FAQ)), faq))
    app.add_handler(MessageHandler(filters.Regex(menu_button_regex(BTN_CONTACTS)), contacts))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))
    app.add_error_handler(on_error)
    return app


if __name__ == "__main__":
    application = build_app()
    init_db()
    logger.info("Telegram Support Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

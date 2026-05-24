import logging

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import APPS_SCRIPT_URL, BUSINESS_NAME, CLOSING_MESSAGE, TELEGRAM_BOT_TOKEN
from bot.sheets_client import save_lead

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_NAME, ASK_EVENT, ASK_DATE = range(3)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        f"Hi! Welcome to {BUSINESS_NAME}.\n\n"
        "I'll collect a few details and our team will follow up shortly.\n\n"
        "What is your name?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Thanks! What type of event are you planning?")
    return ASK_EVENT


async def ask_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_type"] = update.message.text.strip()
    await update.message.reply_text("Great. What date are you looking for?")
    return ASK_DATE


async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_date"] = update.message.text.strip()

    contact = ""
    if update.effective_user:
        parts = []
        if update.effective_user.username:
            parts.append(f"@{update.effective_user.username}")
        if update.effective_user.id:
            parts.append(f"id:{update.effective_user.id}")
        contact = " ".join(parts)

    saved = await save_lead(
        source="telegram",
        contact=contact,
        name=context.user_data.get("name", ""),
        event_type=context.user_data.get("event_type", ""),
        event_date=context.user_data.get("event_date", ""),
    )

    if not saved:
        await update.message.reply_text(
            "I saved your answers, but had trouble writing to the spreadsheet. "
            "Our team will still reach out soon."
        )
    else:
        await update.message.reply_text(CLOSING_MESSAGE)

    await update.message.reply_text(
        "Need to submit another inquiry? Tap /start",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled. Tap /start anytime to try again.")
    return ConversationHandler.END


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (free from @BotFather on Telegram)")
    if not APPS_SCRIPT_URL:
        raise SystemExit("Set APPS_SCRIPT_URL in .env (free Google Apps Script web app URL)")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_EVENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_event)],
            ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conversation)
    logger.info("Telegram bot running (100%% free — polling mode, no hosting bill)")
    app.run_polling()


if __name__ == "__main__":
    main()

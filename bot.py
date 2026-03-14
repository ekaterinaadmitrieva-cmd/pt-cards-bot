import json
import os
import datetime as dt
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, Defaults

TOKEN = os.environ["BOT_TOKEN"]
TZ = ZoneInfo("Europe/Lisbon")

CARDS_FILE = "cards.json"
STATE_FILE = os.environ.get("STATE_FILE", "state.json")


def load_cards():
    with open(CARDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"chat_id": None, "day_index": 0}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    if "/" in STATE_FILE:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def format_card(card):
    pt_lines = "\n".join(f"🇵🇹 {line}" for line in card["pt"])
    ru_lines = "\n".join(f"🇷🇺 {line}" for line in card["ru"])
    return f"📅 Dia {card['day']}\n\n{pt_lines}\n\n{ru_lines}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["chat_id"] = update.effective_chat.id
    save_state(state)
    await update.message.reply_text(
        "Готово ✅ Я буду присылать карточку каждый день в 09:30 (Лиссабон).\n"
        "Команды: /today (карточка сейчас), /reset (сбросить на день 1)."
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cards = load_cards()
    state = load_state()
    idx = max(0, min(state.get("day_index", 0), len(cards) - 1))
    await update.message.reply_text(format_card(cards[idx]))


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["day_index"] = 0
    save_state(state)
    await update.message.reply_text("Сбросила на день 1 ✅")


async def send_daily_card(context: ContextTypes.DEFAULT_TYPE):
    cards = load_cards()
    state = load_state()

    chat_id = state.get("chat_id")
    if not chat_id:
        return

    idx = state.get("day_index", 0)
    if idx >= len(cards):
        idx = len(cards) - 1

    await context.bot.send_message(chat_id=chat_id, text=format_card(cards[idx]))

    state["day_index"] = min(idx + 1, len(cards))
    save_state(state)


def main():
    defaults = Defaults(tzinfo=TZ)
    app = Application.builder().token(TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("reset", reset))

    app.job_queue.run_daily(send_daily_card, time=dt.time(9, 30, tzinfo=TZ))

    app.run_polling()


if __name__ == "__main__":
    main()

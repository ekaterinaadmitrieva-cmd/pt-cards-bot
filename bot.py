import json
import os
import datetime as dt
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import edge_tts
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    Defaults,
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

TZ = ZoneInfo("Europe/Lisbon")

CARDS_FILE = "cards.json"
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
TTS_VOICE = "pt-PT-RaquelNeural"  # европейский португальский


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


def clamp_index(idx: int, total: int) -> int:
    return max(0, min(idx, total - 1))


def build_card_text(card: dict, total_cards: int) -> str:
    pt_lines = "\n".join(f"• {line}" for line in card["pt"])
    ru_lines = "\n".join(f"• {line}" for line in card["ru"])

    return (
        f"📘 <b>Карточка дня</b>\n"
        f"📅 <b>День {card['day']} из {total_cards}</b>\n\n"
        f"🇵🇹 <b>Português</b>\n{pt_lines}\n\n"
        f"🇷🇺 <b>Русский</b>\n{ru_lines}"
    )


def build_keyboard(card_day: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔊 Произношение", callback_data=f"say:{card_day}"),
            ],
            [
                InlineKeyboardButton("➡️ Next", callback_data="next"),
                InlineKeyboardButton("🔁 Reset", callback_data="reset"),
            ],
        ]
    )


def get_card_by_day(cards: list, day_number: int) -> dict | None:
    for card in cards:
        if card["day"] == day_number:
            return card
    return None


async def send_card(chat_id: int, context: ContextTypes.DEFAULT_TYPE, idx: int):
    cards = load_cards()
    idx = clamp_index(idx, len(cards))
    card = cards[idx]

    await context.bot.send_message(
        chat_id=chat_id,
        text=build_card_text(card, len(cards)),
        reply_markup=build_keyboard(card["day"]),
        parse_mode="HTML",
    )


async def synthesize_pronunciation(text: str) -> Path:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    temp_path = Path(temp_file.name)
    temp_file.close()

    communicate = edge_tts.Communicate(text=text, voice=TTS_VOICE)
    await communicate.save(str(temp_path))
    return temp_path


def pronunciation_text(card: dict) -> str:
    # озвучиваем только португальские строки
    return " ... ".join(card["pt"])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["chat_id"] = update.effective_chat.id
    save_state(state)

    await update.message.reply_text(
        "Готово ✅ Бот подключён.\n"
        "Команды:\n"
        "/today — текущая карточка\n"
        "/next — следующая карточка\n"
        "/reset — начать снова с дня 1"
    )

    cards = load_cards()
    idx = clamp_index(state.get("day_index", 0), len(cards))
    await send_card(update.effective_chat.id, context, idx)


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cards = load_cards()
    state = load_state()
    idx = clamp_index(state.get("day_index", 0), len(cards))
    await send_card(update.effective_chat.id, context, idx)


async def next_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cards = load_cards()
    state = load_state()
    current_idx = clamp_index(state.get("day_index", 0), len(cards))
    next_idx = clamp_index(current_idx + 1, len(cards))

    state["day_index"] = next_idx
    save_state(state)

    await send_card(update.effective_chat.id, context, next_idx)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["day_index"] = 0
    save_state(state)

    await update.message.reply_text("Сбросила прогресс на День 1 ✅")
    await send_card(update.effective_chat.id, context, 0)


async def send_daily_card(context: ContextTypes.DEFAULT_TYPE):
    cards = load_cards()
    state = load_state()

    chat_id = state.get("chat_id")
    if not chat_id:
        return

    idx = clamp_index(state.get("day_index", 0), len(cards))
    await send_card(chat_id, context, idx)

    # после ежедневной отправки двигаемся на следующий день
    state["day_index"] = clamp_index(idx + 1, len(cards))
    save_state(state)


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cards = load_cards()
    state = load_state()

    if query.data == "next":
        current_idx = clamp_index(state.get("day_index", 0), len(cards))
        next_idx = clamp_index(current_idx + 1, len(cards))
        state["day_index"] = next_idx
        save_state(state)
        await send_card(query.message.chat_id, context, next_idx)
        return

    if query.data == "reset":
        state["day_index"] = 0
        save_state(state)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Сбросила прогресс на День 1 ✅",
        )
        await send_card(query.message.chat_id, context, 0)
        return

    if query.data.startswith("say:"):
        day_number = int(query.data.split(":")[1])
        card = get_card_by_day(cards, day_number)
        if not card:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Не нашла карточку для озвучивания 😕",
            )
            return

        text_for_tts = pronunciation_text(card)
        audio_path = await synthesize_pronunciation(text_for_tts)

        try:
            with open(audio_path, "rb") as audio_file:
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=audio_file,
                    title=f"Pronúncia — Dia {day_number}",
                    caption="🇵🇹 Европейский португальский",
                )
        finally:
            if audio_path.exists():
                audio_path.unlink()


def main():
    defaults = Defaults(tzinfo=TZ)
    app = Application.builder().token(TOKEN).defaults(defaults).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("next", next_card))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(handle_button))

    app.job_queue.run_daily(send_daily_card, time=dt.time(9, 30, tzinfo=TZ))

    app.run_polling()


if __name__ == "__main__":
    main()
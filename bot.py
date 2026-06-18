import logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from config import TOKEN, ADMIN_ID, QUESTIONS, RESULTS, INTRO_TEXT, WARMUP_TEXT, WELCOME_PHOTO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище: user_id -> {answers: [], question_index: int}
user_sessions = {}
# Статистика: {type_name: count}
stats = {"Шизоидный": 0, "Оральный": 0, "Психопатический": 0, "Мазохистский": 0, "Ригидный": 0}


def calculate_result(answers: list) -> str:
    """
    Каждый вопрос имеет 5 вариантов:
    1 → Шизоидный, 2 → Оральный, 3 → Психопатический, 4 → Мазохистский, 5 → Ригидный
    Считаем, какой тип встречается чаще всего.
    """
    type_map = {1: "Шизоидный", 2: "Оральный", 3: "Психопатический", 4: "Мазохистский", 5: "Ригидный"}
    counts = {t: 0 for t in type_map.values()}
    for a in answers:
        counts[type_map[a]] += 1
    return max(counts, key=counts.get)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = {"answers": [], "question_index": 0}

    keyboard = [[InlineKeyboardButton("▶️ Начать тест", callback_data="start_test")]]

    photo_path = Path(WELCOME_PHOTO)
    if photo_path.exists():
        with open(photo_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=INTRO_TEXT,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text(
            INTRO_TEXT,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = user_sessions[user_id]
    q_index = session["question_index"]
    question = QUESTIONS[q_index]

    keyboard = [
        [InlineKeyboardButton(opt["text"], callback_data=f"answer_{q_index}_{opt['value']}")]
        for opt in question["options"]
    ]

    text = f"<b>Вопрос {q_index + 1} из {len(QUESTIONS)}</b>\n\n{question['text']}"

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data == "start_test":
        user_sessions[user_id] = {"answers": [], "question_index": 0}
        await send_question(update, context, user_id)
        return

    if data.startswith("answer_"):
        _, q_index, value = data.split("_")
        q_index = int(q_index)
        value = int(value)

        if user_id not in user_sessions:
            await query.edit_message_text("Напиши /start чтобы начать заново.")
            return

        session = user_sessions[user_id]

        # Защита от повторного нажатия
        if session["question_index"] != q_index:
            return

        session["answers"].append(value)
        session["question_index"] += 1

        if session["question_index"] < len(QUESTIONS):
            await send_question(update, context, user_id)
        else:
            # Тест завершён
            result_type = calculate_result(session["answers"])
            stats[result_type] += 1

            result_text = RESULTS[result_type]
            warmup = WARMUP_TEXT.get(result_type, WARMUP_TEXT["default"])

            full_text = (
                f"<b>Ваш телесный тип — {result_type.upper()}</b>\n\n"
                f"{result_text}\n\n"
                f"———\n\n"
                f"{warmup}"
            )

            keyboard = [[InlineKeyboardButton("🔄 Пройти ещё раз", callback_data="start_test")]]
            await query.edit_message_text(
                full_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )

            # Уведомление админу
            user = update.effective_user
            name = user.full_name
            username = f"@{user.username}" if user.username else "нет username"
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 Новый результат\n👤 {name} ({username})\n📊 Тип: <b>{result_type}</b>",
                parse_mode="HTML"
            )

    if data == "admin_stats":
        if user_id != ADMIN_ID:
            await query.answer("Нет доступа", show_alert=True)
            return
        await show_stats(update, context)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total = sum(stats.values())
    lines = [f"📊 <b>Статистика бота</b>\n", f"Всего прошли тест: <b>{total}</b>\n"]
    for type_name, count in stats.items():
        pct = round(count / total * 100) if total else 0
        lines.append(f"• {type_name}: {count} ({pct}%)")

    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats")]]
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = sum(stats.values())
    lines = [f"📊 <b>Статистика бота</b>\n", f"Всего прошли тест: <b>{total}</b>\n"]
    for type_name, count in stats.items():
        pct = round(count / total * 100) if total else 0
        lines.append(f"• {type_name}: {count} ({pct}%)")

    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats")]]
    await update.callback_query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши /start чтобы начать тест 👇")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()

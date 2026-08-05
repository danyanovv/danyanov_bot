import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_NAME = "bot.db"


# ---------- База данных ----------

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            question TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def add_question(user_id, username, question):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.execute(
        "INSERT INTO questions (user_id, username, question, created_at) "
        "VALUES (?, ?, ?, datetime('now', 'localtime'))",
        (user_id, username, question),
    )
    question_id = cur.lastrowid
    conn.commit()
    conn.close()
    return question_id


# ---------- Клавиатуры ----------

def card_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Мой сайт", callback_data="site_soon")],
            [InlineKeyboardButton(text="📢 Телеграм канал", url="https://t.me/danyanovv")],
            [InlineKeyboardButton(text="💙 ВК сообщество", url="https://vk.ru/danyanovmedia")],
            [InlineKeyboardButton(text="📸 Инстаграм", url="https://www.instagram.com/danyanovv")],
            [InlineKeyboardButton(text="📌 Пинтерест", url="https://pin.it/6mzkwtuR7")],
            [InlineKeyboardButton(text="▶️ Ютуб", url="https://youtube.com/@danyanov")],
            [InlineKeyboardButton(text="✉️ Задать вопрос", callback_data="ask_question")],
        ]
    )


def admin_keyboard(question_id, user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ответить", callback_data=f"answer:{question_id}:{user_id}")],

        ]
    )


# ---------- Состояния (FSM) ----------

class AskQuestion(StatesGroup):
    waiting = State()


class AnswerQuestion(StatesGroup):
    waiting = State()


answer_targets = {}


# ---------- 1. Визитка ----------

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привет! Это бот-визитка.\n\n"
        "Здесь мои ссылки и возможность задать вопрос.\n"
        "Выбери действие ниже:",
        reply_markup=card_keyboard(),
    )


# ---------- 2. Анонимный вопрос ----------

@dp.callback_query(F.data == "ask_question")
async def ask_question(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AskQuestion.waiting)
    await callback.message.answer("✍️ Напиши свой вопрос одним сообщением.")
    await callback.answer()


@dp.message(AskQuestion.waiting)
async def receive_question(message: Message, state: FSMContext):
    await state.clear()

    question_id = add_question(
        message.from_user.id,
        message.from_user.username,
        message.text,
    )

    await message.answer("✅ Вопрос отправлен.")

    if message.from_user.username:
        user_info = "@" + message.from_user.username
    else:
        user_info = "без username"

    await bot.send_message(
        ADMIN_ID,
        f"❓ Новый вопрос #{question_id}\n\n"
        f"От: {user_info}\n"
        f"ID: {message.from_user.id}\n\n"
        f"Текст:\n{message.text}",
        reply_markup=admin_keyboard(question_id, message.from_user.id),
    )


# ---------- Ответ на вопрос ----------

@dp.callback_query(F.data.startswith("answer:"))
async def answer_question(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Недоступно.")
        return

    _, question_id, user_id = callback.data.split(":")

    answer_targets[callback.from_user.id] = int(user_id)

    await state.set_state(AnswerQuestion.waiting)
    await callback.message.answer(f"✍️ Напиши ответ на вопрос #{question_id}.")
    await callback.answer()


@dp.message(AnswerQuestion.waiting)
async def send_answer(message: Message, state: FSMContext):
    await state.clear()

    user_id = answer_targets.pop(message.from_user.id, None)
    if not user_id:
        await message.answer("❌ Не удалось найти, кому отвечать.")
        return

    try:
        await bot.send_message(
            user_id,
            f"💬 Ответ на твой вопрос:\n\n{message.text}",
        )
        await message.answer("✅ Ответ отправлен.")
    except Exception:
        await message.answer("❌ Не удалось отправить. Возможно, пользователь заблокировал бота.")


# ---------- Жалоба ----------

@dp.callback_query(F.data.startswith("report:"))
async def report_user(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Недоступно.")
        return

    user_id = callback.data.split(":")[1]
    await callback.message.answer(f"⚠️ Жалоба на пользователя {user_id} сохранена.")
    await callback.answer()


# ---------- Запуск ----------

async def main():
    init_db()

    # мини-сервер, чтобы Render не усыплял бота
    app = web.Application()
    app.add_routes([web.get("/", lambda request: web.Response(text="ok"))])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
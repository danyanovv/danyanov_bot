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
from aiogram.types import ReplyParameters
from aiogram.types import WebAppInfo


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
            [InlineKeyboardButton(text="📖 Википедия", web_app=WebAppInfo(url=WIKI_URL))],
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
        "👋 Привет! Это бот-визитка. \n\n"
        "Здесь мои ссылки и возможность задать вопрос.\n"
        "Выбери действие ниже:\n\n"
        "👨‍💻 Разработчик: By Danya Nov",
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

# ---------- Автокомментарий под постами ----------

AUTO_COMMENT_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Перейти в бота", url="https://t.me/danyanov_bot")],
    ]
)


@dp.message(F.is_automatic_forward)
async def auto_comment(message: Message):
    await bot.send_message(
        chat_id=message.chat.id,
        text="👇 Вся инфа здесь — ссылки, вопросы, ответы:",
        reply_markup=AUTO_COMMENT_KEYBOARD,
        message_thread_id=message.message_thread_id,
        reply_parameters=ReplyParameters(message_id=message.message_id),
    )


# ---------- Мини-апп «Википедия» ----------

WIKI_URL = "https://danyanov-bot.onrender.com/wiki"

PHOTO_URL = ""  # сюда вставь ссылку на своё фото (или оставь пусто — будет заглушка)

photo_html = '<img src="' + PHOTO_URL + '" alt="Danya Nov">' if PHOTO_URL else '<div class="ph">DN</div>'

WIKI_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Новиков, Даниил Русланович — Википедия</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
body{margin:0;background:#fff;color:#202122;font-family:Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6}
.page{max-width:980px;margin:0 auto;padding:14px 16px 40px}
header{display:flex;align-items:baseline;gap:10px;border-bottom:1px solid #c8ccd1;padding-bottom:8px;margin-bottom:10px}
.logo{font-family:Georgia,serif;font-size:20px;letter-spacing:1px}
.sub{color:#54595d;font-size:11px}
h1{font-family:Georgia,'Times New Roman',serif;font-size:26px;font-weight:normal;margin:6px 0 2px;border-bottom:1px solid #a2a9b1;padding-bottom:4px}
.tagline{color:#54595d;font-size:11px;margin:0 0 12px}
h2{font-family:Georgia,'Times New Roman',serif;font-size:20px;font-weight:normal;border-bottom:1px solid #a2a9b1;padding-bottom:3px;margin:22px 0 8px}
h3{font-size:15px;margin:16px 0 6px}
a{color:#0645ad;text-decoration:none}
.infobox{float:right;clear:right;width:260px;background:#f8f9fa;border:1px solid #a2a9b1;padding:6px;font-size:12px;margin:0 0 10px 14px}
.infobox .cap{text-align:center;font-weight:bold;padding:4px 0 6px;font-size:13px}
.infobox .ph{height:240px;background:#eaecf0;display:flex;align-items:center;justify-content:center;color:#a2a9b1;font-family:Georgia,serif;font-size:44px}
.infobox img{width:100%;display:block}
.infobox table{width:100%;border-collapse:collapse;margin-top:6px}
.infobox th{color:#54595d;font-weight:normal;text-align:left;vertical-align:top;padding:3px 6px 3px 0;width:42%}
.infobox td{vertical-align:top;padding:3px 0}
.toc{display:inline-block;background:#f8f9fa;border:1px solid #a2a9b1;padding:8px 18px;margin:4px 0 14px}
.toc .t{text-align:center;font-weight:bold;font-size:13px}
.toc ul{list-style:none;margin:6px 0 0;padding:0}
.toc li{margin:3px 0}
ul.refs{margin:6px 0}
.cat{margin-top:26px;border:1px solid #a2a9b1;background:#f8f9fa;padding:6px 10px;font-size:12px}
@media (max-width:640px){.infobox{float:none;width:100%;margin:0 0 14px}}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logo">📖 <b>ВИКИПЕДИЯ</b></div>
  <div class="sub">Свободная энциклопедия</div>
</header>

<h1>Новиков, Даниил Русланович</h1>
<div class="tagline">Материал из свободной энциклопедии</div>

<div class="infobox">
  <div class="cap">Danya Nov</div>
  <!--PHOTO-->
  <table>
    <tr><th>Дата рождения:</th><td>12 февраля 2007</td></tr>
    <tr><th>Место рождения:</th><td>Нижний Новгород, Россия</td></tr>
    <tr><th>Псевдоним:</th><td>Danya Nov</td></tr>
    <tr><th>Род деятельности:</th><td>видеоблогер, стример, разработчик, предприниматель</td></tr>
    <tr><th>Годы активности:</th><td>2021 — настоящее время</td></tr>
  </table>
</div>

<p><b>Дании́л Русла́нович Но́виков</b> (род. 12 февраля 2007, Нижний Новгород, Россия), более известный под псевдонимом <b>Danya Nov</b> — российский видеоблогер, стример, разработчик и предприниматель. Получил известность благодаря летсплей-контенту по таким играм, как Standoff 2, Arizona RP и CS:GO, а также последующей деятельностью в сфере IT-разработок и сборки компьютерной техники на заказ.</p>

<div class="toc">
  <div class="t">Содержание</div>
  <ul>
    <li><a href="#bio">1 Биография</a></li>
    <li><a href="#work">2 Творческая деятельность</a>
      <ul>
        <li><a href="#yt">2.1 Раннее творчество и YouTube</a></li>
        <li><a href="#it">2.2 IT-деятельность и предпринимательство</a></li>
        <li><a href="#now">2.3 Современная деятельность</a></li>
      </ul>
    </li>
    <li><a href="#links">3 Ссылки</a></li>
  </ul>
</div>

<h2 id="bio">Биография</h2>
<p>Родился 12 февраля 2007 года в Нижнем Новгороде. Активную деятельность в интернете начал в подростковом возрасте, в 2021 году. Изначально фокусировался на создании игрового контента и стриминге, параллельно развивая навыки видеомонтажа и программирования.</p>

<h2 id="work">Творческая деятельность</h2>
<h3 id="yt">Раннее творчество и YouTube</h3>
<p>Свою карьеру Даниил начал на видеохостинге YouTube, создавая классические летсплеи (Let’s Play) и игровые нарезки. Основу его контента составляли прохождения и обзоры популярных в СНГ и мире многопользовательских и мобильных игр:</p>
<ul class="refs">
  <li><b>Standoff 2:</b> один из первых проектов Новикова, принесший ему начальную аудиторию. Даниил выпускал эдиты, дуэли, обзоры обновлений и стримы по мобильному шутеру.</li>
  <li><b>CS:GO (Counter-Strike: Global Offensive):</b> летсплеи, челленджи и выполнение заданий от подписчиков, а также реакции на киберспортивные события.</li>
  <li><b>Arizona RP (GTA SA-MP):</b> ролевые сервера, где Даниил создавал сюжетные ролики, обзоры внутриигровой экономики и стримил взаимодействие с другими игроками.</li>
</ul>
<p>В этот период его контент характеризовался частым использованием трендов, мемов и юмористических вставок, что позволило сформировать ядро молодежной аудитории.</p>

<h3 id="it">IT-деятельность и предпринимательство</h3>
<p>Со временем интересы Новикова сместились от простого создания развлекательного контента к более техническим и коммерческим направлениям.</p>
<p><b>Разработка программного обеспечения.</b> Новиков начал заниматься программированием и созданием собственных цифровых продуктов. Известно, что он разрабатывал и продавал кастомных ботов для мессенджеров (в частности, для Telegram и Discord), автоматизирующих различные задачи для пользователей и сообществ. Параллельно ведет разработку собственных экосистемных проектов, включая авторского Telegram-бота.</p>
<p><b>Сборка ПК.</b> В период активной монетизации своих технических навыков Даниил занимался профессиональной сборкой персональных компьютеров на заказ. Оказывал услуги по подбору комплектующих, оптимизации систем охлаждения и настройке программного обеспечения для геймеров и стримеров из Нижнего Новгорода и других регионов.</p>

<h3 id="now">Современная деятельность</h3>
<p>В настоящее время Даниил Новиков ведет кроссплатформенную деятельность, объединяя свои навыки блогера и разработчика. Его основные ресурсы включают:</p>
<ul class="refs">
  <li>YouTube-канал <b>Danya Nov</b> (более 30 000 подписчиков), где выходят обзоры, автомобильный контент (мото-тематика, шортсы с конфликтами на дорогах) и игровые нарезки.</li>
  <li>Сообщество ВКонтакте и Telegram-канал, где публикуются инсайды, лайфстайл и анонсы IT-проектов.</li>
  <li>TikTok и Instagram, где блогер поддерживает актуальность среди молодой аудитории через короткие вертикальные ролики.</li>
</ul>

<h2 id="links">Ссылки</h2>
<ul class="refs">
  <li><a href="https://www.youtube.com/@DanyaNov">Официальный YouTube-канал Danya Nov</a></li>
  <li><a href="https://vk.com/">Сообщество ВКонтакте</a></li>
  <li><a href="https://t.me/">Telegram-канал</a></li>
</ul>

<div class="cat">Категории: <a href="#bio">Видеоблогеры России</a> | <a href="#bio">Стримеры</a> | <a href="#it">Разработчики</a></div>
</div>
<script>
if (window.Telegram && window.Telegram.WebApp) { Telegram.WebApp.ready(); Telegram.WebApp.expand(); }
</script>
</body>
</html>
""".replace("<!--PHOTO-->", photo_html)


async def wiki_handler(request):
    return web.Response(text=WIKI_HTML, content_type="text/html")


# ---------- Запуск ----------

async def main():
    init_db()

    # мини-сервер, чтобы Render не усыплял бота
    app = web.Application()
    app.add_routes([
        web.get("/", lambda request: web.Response(text="ok")),
        web.get("/wiki", wiki_handler),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
"""Личный секретарь — телеграм-бот (Bot API / aiogram).

Два режима в одном боте:
  • Консьерж — пишешь/говоришь боту напрямую, он ищет места и кидает варианты.
  • Секретарь — подключённый к твоему аккаунту через Telegram Business,
    отвечает в ТВОИХ личных чатах от твоего имени (нужен Premium).

Шаг 1 (этот файл): приём голосовых + распознавание + автопилот вкл/выкл.
Шаг 2 (дальше): поиск по 2ГИС + мозг на GPT, который смотрит фото/меню.
"""

import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BusinessConnection, Message

import brain
import config
from stt import transcribe

# Автопилот: True — бот сам обрабатывает запросы, False — молчит.
autopilot = True

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

VOICES_DIR = Path(__file__).resolve().parent / "voices"
VOICES_DIR.mkdir(exist_ok=True)


def is_owner(msg: Message) -> bool:
    return bool(msg.from_user) and msg.from_user.id == config.OWNER_ID


# --- Управление (только хозяин) ---
@dp.message(Command("on"))
async def turn_on(msg: Message):
    if not is_owner(msg):
        return
    global autopilot
    autopilot = True
    await msg.answer("🟢 Автопилот включён")


@dp.message(Command("off"))
async def turn_off(msg: Message):
    if not is_owner(msg):
        return
    global autopilot
    autopilot = False
    await msg.answer("🔴 Автопилот выключен")


# --- Прямой диалог с ботом (консьерж-режим) ---
@dp.message(F.voice)
async def on_voice(msg: Message):
    if not autopilot:
        return
    note = await msg.answer("🎧 Слушаю голосовое…")
    file = await bot.get_file(msg.voice.file_id)
    path = str(VOICES_DIR / f"{msg.voice.file_unique_id}.ogg")
    await bot.download_file(file.file_path, path)
    try:
        text = transcribe(path)
    except Exception as e:
        await note.edit_text(f"⚠️ Не смог распознать: {e}")
        return
    finally:
        if os.path.exists(path):
            os.remove(path)
    try:
        answer = await asyncio.to_thread(brain.reply, msg.chat.id, text)
    except Exception as e:
        answer = f"⚠️ Мозг не ответил: {e}"
    await note.edit_text(f"🎤 «{text}»\n\n{answer}")


@dp.message(F.text)
async def on_text(msg: Message):
    if not autopilot or msg.text.startswith("/"):
        return
    try:
        answer = await asyncio.to_thread(brain.reply, msg.chat.id, msg.text)
    except Exception as e:
        answer = f"⚠️ Мозг не ответил: {e}"
    await msg.answer(answer)


# --- Telegram Business: ответы в ТВОИХ чатах (нужен Premium + подключение) ---
@dp.business_connection()
async def on_business_connection(conn: BusinessConnection):
    state = "включён" if conn.is_enabled else "выключен"
    print(f"Business-подключение {conn.id}: {state}")


@dp.business_message()
async def on_business_message(msg: Message):
    if not autopilot or not msg.text:
        return
    try:
        answer = await asyncio.to_thread(brain.reply, msg.chat.id, msg.text)
    except Exception as e:
        answer = f"⚠️ {e}"
    await bot.send_message(
        chat_id=msg.chat.id,
        text=answer,
        business_connection_id=msg.business_connection_id,
    )


async def main():
    if not config.BOT_TOKEN:
        raise SystemExit("Заполни TELEGRAM_BOT_TOKEN в .env (см. README)")
    print("Бот запущен. Автопилот:", "вкл" if autopilot else "выкл")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

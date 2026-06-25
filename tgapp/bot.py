"""Телеграм-бот: вход в мини-апп.

/start присылает кнопку, открывающую приложение, и ставит кнопку-меню Web App.
Env: BOT_TOKEN, WEBAPP_URL
Запуск:  python bot.py
"""
import os

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                       MenuButtonWebApp, Update, WebAppInfo)
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]
URL = os.environ["WEBAPP_URL"]


async def start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔪 Открыть Барбер-Лиды", web_app=WebAppInfo(url=URL))]])
    await update.message.reply_text(
        "Барбер-Лиды — гайд по звонку и барбершопы Уфы для обзвона.\n\nЖми кнопку ниже 👇",
        reply_markup=kb,
    )


async def post_init(application: Application):
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=URL))
    )


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

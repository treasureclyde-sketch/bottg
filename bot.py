"""Точка входа: long-polling + планировщик напоминаний."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, Message

import texts
from config import get_settings
from db.engine import init_db
from db.seed import seed_if_empty
from handlers import build_root_router
from handlers.middlewares import SubscriptionMiddleware
from services.reminders import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
# заглушаем слишком болтливые логгеры
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("bot")
settings = get_settings()


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запуск / главное меню"),
            BotCommand(command="menu", description="Главное меню"),
            BotCommand(command="admin", description="Админ-панель"),
        ]
    )


def register_error_handler(dp: Dispatcher) -> None:
    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("Необработанная ошибка: %s", event.exception)
        # пытаемся мягко сообщить пользователю
        update = event.update
        try:
            if update.message:
                await update.message.answer(texts.GENERIC_ERROR)
            elif update.callback_query:
                await update.callback_query.answer(texts.GENERIC_ERROR, show_alert=True)
        except Exception:  # noqa: BLE001
            pass
        return True  # ошибка обработана, бот продолжает работу


def build_fallback_router() -> Router:
    """Роутер-«ловушка» для нераспознанных сообщений. Включается ПОСЛЕДНИМ."""
    router = Router(name="fallback")

    @router.message()
    async def fallback_message(message: Message) -> None:
        await message.answer(texts.UNKNOWN_INPUT)

    return router


async def main() -> None:
    logger.info("Инициализация БД…")
    await init_db()
    await seed_if_empty()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(SubscriptionMiddleware())  # стоп-кран по оплате
    dp.include_router(build_root_router())
    dp.include_router(build_fallback_router())  # последним — ловит всё нераспознанное
    register_error_handler(dp)

    scheduler = setup_scheduler(bot)

    try:
        scheduler.start()
        logger.info("Планировщик напоминаний запущен (интервал %d мин)",
                    settings.reminder_check_interval_min)
        await set_bot_commands(bot)
        me = await bot.get_me()
        logger.info("Бот @%s (%s) запущен. Салон: %s", me.username, me.id, settings.business_name)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        raise SystemExit(
            "Telegram отклонил BOT_TOKEN (Unauthorized). "
            "Проверьте токен в .env — получите его у @BotFather."
        )
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except SystemExit as exc:
        # печатаем понятное текстовое сообщение (например, неверный токен)
        if isinstance(exc.code, str):
            print(exc.code)

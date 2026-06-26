"""Биллинг-бот провайдера: управление подписками всех салонов в одном месте.

Отдельный бот (свой токен). Показывает список клиентов и их статус, позволяет в
один тап продлить/приостановить подписку. Раз в день шлёт дайджест: у кого скоро
истекает или уже просрочено. Источник правды — общая billing.db, которую читают
салонные боты, поэтому продление подхватывается без рестарта (в пределах кэша ≤60с).

Запуск:  python billing_bot.py   (нужны BILLING_BOT_TOKEN, BILLING_ADMIN_IDS в .env)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from billing import store
from billing.config import get_billing_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger("billing")

settings = get_billing_settings()
router = Router(name="billing")


# ---------------------------------------------------------------------------
# Доступ только администраторам биллинга
# ---------------------------------------------------------------------------
class IsBillingAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and settings.is_admin(user.id)


router.message.filter(IsBillingAdmin())
router.callback_query.filter(IsBillingAdmin())


# ---------------------------------------------------------------------------
# Callback-данные
# ---------------------------------------------------------------------------
class BListCB(CallbackData, prefix="blist"):
    pass


class BOpenCB(CallbackData, prefix="bopen"):
    slug: str


class BActCB(CallbackData, prefix="bact"):
    slug: str
    act: str  # ext | susp | del
    days: int = 0


# ---------------------------------------------------------------------------
# Форматирование статуса
# ---------------------------------------------------------------------------
def _today() -> date:
    return datetime.now(settings.tz).date()


def _status(paid_until: date | None, today: date) -> tuple[str, str]:
    """(эмодзи, текст статуса)."""
    if paid_until is None:
        return "♾", "бессрочно"
    delta = (paid_until - today).days
    if delta < 0:
        return "🔴", f"просрочено {abs(delta)} дн. (с {paid_until:%d.%m})"
    if delta == 0:
        return "🟠", "истекает сегодня"
    if delta <= 3:
        return "🟠", f"ещё {delta} дн. (до {paid_until:%d.%m})"
    return "🟢", f"оплачено до {paid_until:%d.%m.%Y}"


# ---------------------------------------------------------------------------
# Рендеры
# ---------------------------------------------------------------------------
async def render_list(message: Message, edit: bool) -> None:
    today = _today()
    subs = await store.list_all(settings.billing_db_path)

    if not subs:
        text = (
            "📋 <b>Подписки</b>\n\nКлиентов пока нет.\n"
            "Добавить: <code>/add &lt;slug&gt; &lt;дней&gt; [название]</code>"
        )
        await _send(message, text, None, edit)
        return

    overdue = sum(1 for s in subs if s.paid_until and s.paid_until < today)
    lines = [f"📋 <b>Подписки</b> — всего {len(subs)}"]
    if overdue:
        lines.append(f"🔴 просрочено: {overdue}")
    lines.append("")

    kb = InlineKeyboardBuilder()
    for s in subs:
        emoji, st = _status(s.paid_until, today)
        title = s.title or s.slug
        lines.append(f"{emoji} <b>{title}</b> (<code>{s.slug}</code>) — {st}")
        kb.button(text=f"{emoji} {title}", callback_data=BOpenCB(slug=s.slug))
    kb.button(text="🔄 Обновить", callback_data=BListCB())
    kb.adjust(1)
    await _send(message, "\n".join(lines), kb.as_markup(), edit)


async def render_detail(message: Message, slug: str, edit: bool) -> None:
    today = _today()
    s = await store.get(settings.billing_db_path, slug)
    if s is None:
        await _send(message, "Клиент не найден.", _back_kb(), edit)
        return
    emoji, st = _status(s.paid_until, today)
    title = s.title or s.slug
    text = (
        f"{emoji} <b>{title}</b>\n"
        f"slug: <code>{s.slug}</code>\n"
        f"Статус: {st}"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ 30 дней", callback_data=BActCB(slug=slug, act="ext", days=30))
    kb.button(text="➕ 7 дней", callback_data=BActCB(slug=slug, act="ext", days=7))
    kb.button(
        text=f"🗓 +1 год ({settings.annual_price} ₽)",
        callback_data=BActCB(slug=slug, act="ext", days=365),
    )
    kb.button(text="⏸ Приостановить", callback_data=BActCB(slug=slug, act="susp"))
    kb.button(text="🗑 Удалить", callback_data=BActCB(slug=slug, act="del"))
    kb.button(text="⬅️ К списку", callback_data=BListCB())
    kb.adjust(2, 1, 1, 1, 1)
    await _send(message, text, kb.as_markup(), edit)


def _back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ К списку", callback_data=BListCB())
    return kb.as_markup()


async def _send(message: Message, text: str, markup, edit: bool) -> None:
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:  # noqa: BLE001
            pass
    await message.answer(text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Хендлеры
# ---------------------------------------------------------------------------
@router.message(CommandStart())
@router.message(Command("clients"))
async def cmd_start(message: Message) -> None:
    await render_list(message, edit=False)


@router.callback_query(BListCB.filter())
async def cb_list(call: CallbackQuery) -> None:
    if isinstance(call.message, Message):
        await render_list(call.message, edit=True)
    await call.answer()


@router.callback_query(BOpenCB.filter())
async def cb_open(call: CallbackQuery, callback_data: BOpenCB) -> None:
    if isinstance(call.message, Message):
        await render_detail(call.message, callback_data.slug, edit=True)
    await call.answer()


@router.callback_query(BActCB.filter())
async def cb_action(call: CallbackQuery, callback_data: BActCB) -> None:
    slug, act = callback_data.slug, callback_data.act
    today = _today()
    db = settings.billing_db_path

    if act == "ext":
        view = await store.extend(db, slug, callback_data.days, today=today)
        msg = f"Продлено на {callback_data.days} дн." if view else "Клиент не найден."
    elif act == "susp":
        view = await store.suspend(db, slug, today=today)
        msg = "Подписка приостановлена." if view else "Клиент не найден."
    elif act == "del":
        ok = await store.remove(db, slug)
        await call.answer("Удалён." if ok else "Не найден.", show_alert=True)
        if isinstance(call.message, Message):
            await render_list(call.message, edit=True)
        return
    else:
        await call.answer("Неизвестное действие.")
        return

    await call.answer(msg, show_alert=True)
    if isinstance(call.message, Message):
        await render_detail(call.message, slug, edit=True)


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject) -> None:
    """/add <slug> <дней> [название] — создать/продлить клиента."""
    args = (command.args or "").split(maxsplit=2)
    if len(args) < 2 or not args[1].lstrip("-").isdigit():
        await message.answer(
            "Формат: <code>/add &lt;slug&gt; &lt;дней&gt; [название]</code>\n"
            "Напр.: <code>/add borodach 30 Барбершоп Бородач</code>"
        )
        return
    slug = args[0].strip()
    days = int(args[1])
    title = args[2].strip() if len(args) > 2 else slug
    today = _today()
    paid_until = today + timedelta(days=days)
    await store.upsert(settings.billing_db_path, slug, title=title, paid_until=paid_until)
    await message.answer(
        f"✅ Клиент <code>{slug}</code> ({title}) — оплачено до {paid_until:%d.%m.%Y}"
    )


# ---------------------------------------------------------------------------
# Ежедневный дайджест провайдеру
# ---------------------------------------------------------------------------
async def send_daily_digest(bot: Bot) -> None:
    today = _today()
    try:
        subs = await store.list_all(settings.billing_db_path)
        attention = [
            s for s in subs
            if s.paid_until is not None and (s.paid_until - today).days <= 3
        ]
        if not attention:
            return
        lines = ["📅 <b>Дайджест подписок</b>", ""]
        for s in sorted(attention, key=lambda x: x.paid_until or today):
            emoji, st = _status(s.paid_until, today)
            lines.append(f"{emoji} {s.title or s.slug} (<code>{s.slug}</code>) — {st}")
        text = "\n".join(lines)
        for admin_id in settings.billing_admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception:  # noqa: BLE001
                logger.warning("Не удалось отправить дайджест %s", admin_id)
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка дайджеста подписок")


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------
async def main() -> None:
    await store.init(settings.billing_db_path)

    bot = Bot(
        token=settings.billing_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=str(settings.tz))
    scheduler.add_job(send_daily_digest, "cron", hour=10, minute=0, args=[bot], id="digest")

    try:
        scheduler.start()
        await bot.set_my_commands([
            BotCommand(command="clients", description="Список подписок"),
            BotCommand(command="add", description="Добавить/продлить клиента"),
        ])
        me = await bot.get_me()
        logger.info("Биллинг-бот @%s запущен. БД: %s", me.username, settings.billing_db_path)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        raise SystemExit(
            "Telegram отклонил BILLING_BOT_TOKEN (Unauthorized). Проверьте токен в .env."
        )
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Биллинг-бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code)

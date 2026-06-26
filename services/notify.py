"""Отправка уведомлений админам и клиентам. Все ошибки доставки логируются."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import texts
from config import get_settings
from services.bookings import BookingView

logger = logging.getLogger(__name__)
settings = get_settings()


async def _safe_send(bot: Bot, chat_id: int, text: str) -> bool:
    """Отправить сообщение, не падая, если чат недоступен (бот заблокирован и т.п.)."""
    try:
        await bot.send_message(chat_id, text)
        return True
    except TelegramAPIError as exc:
        logger.warning("Не удалось отправить сообщение %s: %s", chat_id, exc)
        return False


async def notify_admins_new_booking(bot: Bot, view: BookingView) -> None:
    text = texts.admin_new_booking(
        service_title=view.service_title,
        master_name=view.master_name,
        start_dt=view.start_local,
        client_name=view.client_name,
        client_phone=view.client_phone or "—",
        branch_name=view.branch_name,
    )
    for admin_id in settings.admin_ids:
        await _safe_send(bot, admin_id, text)


async def notify_admins_client_cancelled(bot: Bot, view: BookingView) -> None:
    text = texts.admin_client_cancelled(
        service_title=view.service_title,
        master_name=view.master_name,
        start_dt=view.start_local,
        client_name=view.client_name,
        client_phone=view.client_phone or "—",
    )
    for admin_id in settings.admin_ids:
        await _safe_send(bot, admin_id, text)


async def notify_master_new_booking(bot: Bot, view: BookingView) -> None:
    """Уведомить самого мастера о новой записи к нему (если привязан его TG)."""
    if not view.master_telegram_id:
        return
    text = texts.master_new_booking(
        service_title=view.service_title,
        start_dt=view.start_local,
        client_name=view.client_name,
        client_phone=view.client_phone or "—",
        branch_name=view.branch_name,
    )
    await _safe_send(bot, view.master_telegram_id, text)


async def notify_master_booking_cancelled(bot: Bot, view: BookingView) -> None:
    """Уведомить мастера, что его запись отменили (клиент или владелец)."""
    if not view.master_telegram_id:
        return
    text = texts.master_booking_cancelled(
        service_title=view.service_title,
        start_dt=view.start_local,
        client_name=view.client_name,
    )
    await _safe_send(bot, view.master_telegram_id, text)


async def notify_admins_master_cancelled(bot: Bot, view: BookingView) -> None:
    text = texts.admin_master_cancelled(
        master_name=view.master_name,
        service_title=view.service_title,
        start_dt=view.start_local,
        client_name=view.client_name,
        client_phone=view.client_phone or "—",
    )
    for admin_id in settings.admin_ids:
        await _safe_send(bot, admin_id, text)


async def notify_client_cancelled_by_admin(bot: Bot, view: BookingView) -> None:
    text = texts.client_cancelled_by_admin(
        business_name=settings.business_name,
        service_title=view.service_title,
        master_name=view.master_name,
        start_dt=view.start_local,
    )
    await _safe_send(bot, view.client_telegram_id, text)

"""Напоминания клиентам через APScheduler.

Одна периодическая задача раз в N минут проверяет активные брони и шлёт:
  • напоминание накануне (в заданный час дня перед визитом);
  • напоминание за ~2 часа (если включено в конфиге).

Идемпотентность обеспечивается флагами reminder_day_sent / reminder_2h_sent
в БД — поэтому перезапуск бота не приводит к повторной отправке.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

import texts
from config import get_settings
from db.engine import async_session
from db.models import Booking, BookingStatus, Master
from services.notify import _safe_send

logger = logging.getLogger(__name__)
settings = get_settings()


def _day_before_trigger(start_local: datetime) -> datetime:
    """Момент, когда нужно слать напоминание накануне (день-1 в заданный час)."""
    day_before = (start_local - timedelta(days=1)).date()
    return datetime.combine(day_before, time(settings.reminder_day_before_hour, 0), tzinfo=settings.tz)


async def send_due_reminders(bot: Bot) -> None:
    """Главная периодическая задача напоминаний."""
    now = datetime.now(settings.tz)
    try:
        async with async_session() as session:
            bookings = (
                await session.scalars(
                    select(Booking)
                    .where(
                        Booking.status == BookingStatus.active,
                        Booking.start_dt > now,
                        or_(
                            Booking.reminder_day_sent.is_(False),
                            Booking.reminder_2h_sent.is_(False),
                        ),
                    )
                    .options(
                        selectinload(Booking.client),
                        selectinload(Booking.service),
                        selectinload(Booking.master).selectinload(Master.branch),
                    )
                )
            ).all()

            for b in bookings:
                start_local = b.start_dt.astimezone(settings.tz)
                branch = b.master.branch if (b.master and b.master.branch) else None
                branch_name = branch.name if branch else ""
                branch_address = branch.address if branch else ""
                changed = False

                # --- Напоминание накануне ---
                if not b.reminder_day_sent:
                    trigger = _day_before_trigger(start_local)
                    # шлём, только если уже наступил момент и визит — следующий день
                    if now >= trigger and start_local.date() > now.date():
                        text = texts.booking_reminder_day(
                            business_name=settings.business_name,
                            service_title=b.service.title if b.service else "—",
                            master_name=b.master.name if b.master else "—",
                            start_dt=start_local,
                            address=settings.business_address,
                            branch_name=branch_name,
                            branch_address=branch_address,
                        )
                        if await _safe_send(bot, b.client_telegram_id, text):
                            b.reminder_day_sent = True
                            changed = True
                            logger.info("Напоминание (накануне) отправлено брони #%s", b.id)

                # --- Напоминание за 2 часа ---
                if settings.reminder_2h_enabled and not b.reminder_2h_sent:
                    if start_local - timedelta(hours=2) <= now < start_local:
                        text = texts.booking_reminder_2h(
                            business_name=settings.business_name,
                            service_title=b.service.title if b.service else "—",
                            master_name=b.master.name if b.master else "—",
                            start_dt=start_local,
                            address=settings.business_address,
                            branch_name=branch_name,
                            branch_address=branch_address,
                        )
                        if await _safe_send(bot, b.client_telegram_id, text):
                            b.reminder_2h_sent = True
                            changed = True
                            logger.info("Напоминание (2ч) отправлено брони #%s", b.id)

                if changed:
                    await session.flush()

            await session.commit()
    except Exception:  # noqa: BLE001 - задача не должна ронять планировщик
        logger.exception("Ошибка в задаче напоминаний")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создать и сконфигурировать планировщик с периодической задачей."""
    scheduler = AsyncIOScheduler(timezone=str(settings.tz))
    scheduler.add_job(
        send_due_reminders,
        trigger="interval",
        minutes=settings.reminder_check_interval_min,
        args=[bot],
        id="due_reminders",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(settings.tz) + timedelta(seconds=10),
    )
    return scheduler

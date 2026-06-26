"""Генерация свободных слотов — ключевая логика записи.

Для пары (мастер + услуга) на конкретную дату возвращаем список доступных
времён начала с учётом расписания мастера, существующих активных броней,
блокировок и текущего времени.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.models import BlockedSlot, Booking, BookingStatus, MasterSchedule

settings = get_settings()


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Пересекаются ли полуинтервалы [a_start, a_end) и [b_start, b_end)."""
    return a_start < b_end and b_start < a_end


async def _busy_intervals(
    session: AsyncSession, master_id: int, day_start: datetime, day_end: datetime
) -> list[tuple[datetime, datetime]]:
    """Занятые интервалы мастера на день: активные брони + блокировки.

    Блокировки учитываем как персональные (этого мастера), так и общесалонные
    (master_id IS NULL).
    """
    intervals: list[tuple[datetime, datetime]] = []

    # Активные брони мастера, пересекающие день
    bookings = await session.scalars(
        select(Booking).where(
            Booking.master_id == master_id,
            Booking.status == BookingStatus.active,
            Booking.start_dt < day_end,
            Booking.end_dt > day_start,
        )
    )
    for b in bookings:
        intervals.append((b.start_dt, b.end_dt))

    # Блокировки: персональные мастера или общесалонные
    blocks = await session.scalars(
        select(BlockedSlot).where(
            (BlockedSlot.master_id == master_id) | (BlockedSlot.master_id.is_(None)),
            BlockedSlot.start_dt < day_end,
            BlockedSlot.end_dt > day_start,
        )
    )
    for bl in blocks:
        intervals.append((bl.start_dt, bl.end_dt))

    return intervals


async def get_available_slots(
    session: AsyncSession,
    *,
    master_id: int,
    duration_min: int,
    day: date,
) -> list[datetime]:
    """Список доступных времён начала (aware, в таймзоне конфига) на дату `day`."""
    tz = settings.tz

    # Рабочие интервалы мастера на этот день недели
    weekday = day.weekday()  # 0=Пн .. 6=Вс
    schedules = (
        await session.scalars(
            select(MasterSchedule).where(
                MasterSchedule.master_id == master_id,
                MasterSchedule.weekday == weekday,
            )
        )
    ).all()
    if not schedules:
        return []  # выходной

    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    busy = await _busy_intervals(session, master_id, day_start, day_end)

    now = datetime.now(tz)
    earliest = now + timedelta(minutes=settings.booking_buffer_min)

    step = timedelta(minutes=settings.slot_step_min)
    duration = timedelta(minutes=duration_min)

    slots: list[datetime] = []
    for sched in schedules:
        work_start = datetime.combine(day, _parse_hhmm(sched.start_time), tzinfo=tz)
        work_end = datetime.combine(day, _parse_hhmm(sched.end_time), tzinfo=tz)

        slot = work_start
        while slot + duration <= work_end:
            slot_end = slot + duration
            # не в прошлом (с буфером)
            if slot < earliest:
                slot += step
                continue
            # нет пересечений с занятыми интервалами
            if any(_overlaps(slot, slot_end, b_start, b_end) for b_start, b_end in busy):
                slot += step
                continue
            slots.append(slot)
            slot += step

    slots.sort()
    return slots


async def is_slot_free(
    session: AsyncSession,
    *,
    master_id: int,
    start_dt: datetime,
    duration_min: int,
) -> bool:
    """Проверка перед самим созданием брони (защита от гонок/устаревшего экрана)."""
    end_dt = start_dt + timedelta(minutes=duration_min)
    busy = await _busy_intervals(session, master_id, start_dt, end_dt)
    if any(_overlaps(start_dt, end_dt, b_start, b_end) for b_start, b_end in busy):
        return False
    # также проверим, что слот не в прошлом
    earliest = datetime.now(settings.tz) + timedelta(minutes=settings.booking_buffer_min)
    if start_dt < earliest:
        return False
    return True


async def get_available_dates(
    session: AsyncSession,
    *,
    master_id: int,
    duration_min: int,
) -> list[date]:
    """Ближайшие даты (в пределах горизонта), где есть хотя бы один свободный слот."""
    tz = settings.tz
    today = datetime.now(tz).date()
    result: list[date] = []
    for offset in range(settings.booking_horizon_days):
        day = today + timedelta(days=offset)
        slots = await get_available_slots(
            session, master_id=master_id, duration_min=duration_min, day=day
        )
        if slots:
            result.append(day)
    return result

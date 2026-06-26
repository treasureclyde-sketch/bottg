"""Создание / отмена / получение броней.

Перенос реализован на уровне хендлера как «отмена + новая запись», поэтому
здесь отдельной функции reschedule нет — есть cancel и create.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from db.models import Booking, BookingStatus, Branch, Client, Master, Service
from services.slots import is_slot_free

settings = get_settings()


@dataclass
class BookingView:
    """Плоское представление брони для UI/уведомлений (без ленивых обращений к БД)."""

    id: int
    client_telegram_id: int
    client_name: str
    client_phone: str
    service_title: str
    service_price: int
    service_duration: int
    master_name: str
    start_dt: datetime
    end_dt: datetime
    branch_name: str = ""
    branch_address: str = ""
    master_telegram_id: int | None = None

    @property
    def start_local(self) -> datetime:
        return self.start_dt.astimezone(settings.tz)

    @property
    def end_local(self) -> datetime:
        return self.end_dt.astimezone(settings.tz)


def _to_view(b: Booking) -> BookingView:
    branch = b.master.branch if (b.master and b.master.branch) else None
    return BookingView(
        id=b.id,
        client_telegram_id=b.client_telegram_id,
        client_name=b.client.name if b.client else "",
        client_phone=b.client.phone if b.client else "",
        service_title=b.service.title if b.service else "—",
        service_price=b.service.price if b.service else 0,
        service_duration=b.service.duration_min if b.service else 0,
        master_name=b.master.name if b.master else "—",
        start_dt=b.start_dt,
        end_dt=b.end_dt,
        branch_name=branch.name if branch else "",
        branch_address=branch.address if branch else "",
        master_telegram_id=b.master.telegram_id if b.master else None,
    )


async def get_active_branches(session: AsyncSession) -> list[Branch]:
    return list(
        (
            await session.scalars(
                select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)
            )
        ).all()
    )


async def upsert_client(
    session: AsyncSession, *, telegram_id: int, name: str, phone: str
) -> Client:
    client = await session.get(Client, telegram_id)
    if client is None:
        client = Client(telegram_id=telegram_id, name=name, phone=phone)
        session.add(client)
    else:
        if name:
            client.name = name
        if phone:
            client.phone = phone
    await session.flush()
    return client


class SlotTakenError(Exception):
    """Слот заняли, пока пользователь выбирал."""


async def create_booking(
    session: AsyncSession,
    *,
    telegram_id: int,
    service_id: int,
    master_id: int,
    start_dt: datetime,
    client_name: str,
    client_phone: str,
) -> BookingView:
    """Создать бронь с финальной проверкой занятости (защита от гонок)."""
    service = await session.get(Service, service_id)
    if service is None or not service.is_active:
        raise SlotTakenError("Услуга недоступна")

    if not await is_slot_free(
        session, master_id=master_id, start_dt=start_dt, duration_min=service.duration_min
    ):
        raise SlotTakenError("Слот занят")

    await upsert_client(
        session, telegram_id=telegram_id, name=client_name, phone=client_phone
    )

    end_dt = start_dt + timedelta(minutes=service.duration_min)
    booking = Booking(
        client_telegram_id=telegram_id,
        service_id=service_id,
        master_id=master_id,
        start_dt=start_dt,
        end_dt=end_dt,
        status=BookingStatus.active,
    )
    session.add(booking)
    await session.flush()

    view = await get_booking_view(session, booking.id)
    assert view is not None
    return view


async def get_booking_view(session: AsyncSession, booking_id: int) -> BookingView | None:
    booking = await session.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.client),
            selectinload(Booking.service),
            selectinload(Booking.master).selectinload(Master.branch),
        )
    )
    if booking is None:
        return None
    return _to_view(booking)


async def cancel_booking(
    session: AsyncSession,
    *,
    booking_id: int,
    by_telegram_id: int | None = None,
    by_master_id: int | None = None,
) -> BookingView | None:
    """Отменить бронь. Если указан by_telegram_id/by_master_id — проверяем владельца.

    Возвращает представление отменённой брони (для уведомлений) или None,
    если бронь не найдена / уже не активна / не принадлежит пользователю или мастеру.
    """
    booking = await session.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.client),
            selectinload(Booking.service),
            selectinload(Booking.master).selectinload(Master.branch),
        )
    )
    if booking is None or booking.status != BookingStatus.active:
        return None
    if by_telegram_id is not None and booking.client_telegram_id != by_telegram_id:
        return None
    if by_master_id is not None and booking.master_id != by_master_id:
        return None

    view = _to_view(booking)
    booking.status = BookingStatus.cancelled
    await session.flush()
    return view


async def get_future_bookings_for_client(
    session: AsyncSession, telegram_id: int
) -> list[BookingView]:
    now = datetime.now(settings.tz)
    bookings = (
        await session.scalars(
            select(Booking)
            .where(
                Booking.client_telegram_id == telegram_id,
                Booking.status == BookingStatus.active,
                Booking.start_dt >= now,
            )
            .order_by(Booking.start_dt)
            .options(
                selectinload(Booking.client),
                selectinload(Booking.service),
                selectinload(Booking.master).selectinload(Master.branch),
            )
        )
    ).all()
    return [_to_view(b) for b in bookings]


async def get_master_by_telegram(session: AsyncSession, telegram_id: int) -> Master | None:
    """Активный мастер, привязанный к этому Telegram-аккаунту (или None)."""
    return await session.scalar(
        select(Master).where(
            Master.telegram_id == telegram_id,
            Master.is_active.is_(True),
        )
    )


async def get_future_bookings_for_master(
    session: AsyncSession, master_id: int
) -> list[BookingView]:
    """Предстоящие активные записи конкретного мастера."""
    now = datetime.now(settings.tz)
    bookings = (
        await session.scalars(
            select(Booking)
            .where(
                Booking.master_id == master_id,
                Booking.status == BookingStatus.active,
                Booking.start_dt >= now,
            )
            .order_by(Booking.start_dt)
            .options(
                selectinload(Booking.client),
                selectinload(Booking.service),
                selectinload(Booking.master).selectinload(Master.branch),
            )
        )
    ).all()
    return [_to_view(b) for b in bookings]


async def get_bookings_between(
    session: AsyncSession, *, start: datetime, end: datetime
) -> list[BookingView]:
    """Активные брони в диапазоне [start, end) — для админских отчётов."""
    bookings = (
        await session.scalars(
            select(Booking)
            .where(
                Booking.status == BookingStatus.active,
                Booking.start_dt >= start,
                Booking.start_dt < end,
            )
            .order_by(Booking.start_dt)
            .options(
                selectinload(Booking.client),
                selectinload(Booking.service),
                selectinload(Booking.master).selectinload(Master.branch),
            )
        )
    ).all()
    return [_to_view(b) for b in bookings]

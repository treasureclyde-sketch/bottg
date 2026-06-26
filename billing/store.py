"""Центральное хранилище подписок (общая SQLite-БД для всех ботов).

Одна таблица `subscriptions`: одна строка на клиента (по slug) с датой
`paid_until`. Боты салонов читают её на лету (read-only), биллинг-бот провайдера
пишет (продлевает/приостанавливает). Все функции принимают путь к БД, поэтому
модуль не зависит от конкретного конфига и переиспользуется обеими сторонами.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BillingBase(DeclarativeBase):
    pass


class Subscription(BillingBase):
    __tablename__ = "subscriptions"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    paid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    note: Mapped[str] = mapped_column(String(255), default="")


@dataclass
class SubscriptionView:
    slug: str
    title: str
    paid_until: date | None
    note: str


def _to_view(s: Subscription) -> SubscriptionView:
    return SubscriptionView(slug=s.slug, title=s.title, paid_until=s.paid_until, note=s.note)


# --- кэш движков по пути к БД (один процесс может работать с одной-двумя БД) ---
_engines: dict[str, AsyncEngine] = {}
_initialized: set[str] = set()


def _engine(db_path: str) -> AsyncEngine:
    if db_path not in _engines:
        _engines[db_path] = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    return _engines[db_path]


def _sessionmaker(db_path: str) -> async_sessionmaker:
    return async_sessionmaker(_engine(db_path), expire_on_commit=False)


async def init(db_path: str) -> None:
    """Создать таблицу и включить WAL (лучше для одновременных чтений/записей)."""
    engine = _engine(db_path)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.run_sync(BillingBase.metadata.create_all)
    _initialized.add(db_path)


async def _ensure(db_path: str) -> None:
    if db_path not in _initialized:
        await init(db_path)


async def get(db_path: str, slug: str) -> SubscriptionView | None:
    await _ensure(db_path)
    async with _sessionmaker(db_path)() as s:
        row = await s.get(Subscription, slug)
        return _to_view(row) if row else None


async def list_all(db_path: str) -> list[SubscriptionView]:
    await _ensure(db_path)
    async with _sessionmaker(db_path)() as s:
        rows = (await s.scalars(select(Subscription).order_by(Subscription.slug))).all()
        return [_to_view(r) for r in rows]


async def upsert(
    db_path: str,
    slug: str,
    *,
    title: str | None = None,
    paid_until: date | None = None,
    note: str | None = None,
) -> SubscriptionView:
    await _ensure(db_path)
    async with _sessionmaker(db_path)() as s:
        row = await s.get(Subscription, slug)
        if row is None:
            row = Subscription(slug=slug)
            s.add(row)
        if title is not None:
            row.title = title
        if paid_until is not None:
            row.paid_until = paid_until
        if note is not None:
            row.note = note
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await s.commit()
        return _to_view(row)


async def extend(db_path: str, slug: str, days: int, *, today: date) -> SubscriptionView | None:
    """Продлить подписку на `days` дней. Если истекла — отсчёт от сегодня."""
    await _ensure(db_path)
    async with _sessionmaker(db_path)() as s:
        row = await s.get(Subscription, slug)
        if row is None:
            return None
        base = row.paid_until if (row.paid_until and row.paid_until >= today) else today
        row.paid_until = base + timedelta(days=days)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await s.commit()
        return _to_view(row)


async def suspend(db_path: str, slug: str, *, today: date) -> SubscriptionView | None:
    """Приостановить: ставим дату «вчера», бот сразу встаёт на паузу."""
    await _ensure(db_path)
    async with _sessionmaker(db_path)() as s:
        row = await s.get(Subscription, slug)
        if row is None:
            return None
        row.paid_until = today - timedelta(days=1)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await s.commit()
        return _to_view(row)


async def remove(db_path: str, slug: str) -> bool:
    await _ensure(db_path)
    async with _sessionmaker(db_path)() as s:
        row = await s.get(Subscription, slug)
        if row is None:
            return False
        await s.delete(row)
        await s.commit()
        return True

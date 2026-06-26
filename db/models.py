"""SQLAlchemy 2.0 модели.

Все datetime — timezone-aware. В SQLite они физически хранятся в UTC
(см. TZDateTime), а на чтении возвращаются как aware-UTC. Для отображения
переводим в локальную таймзону из конфига.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class TZDateTime(TypeDecorator):
    """Хранит aware-datetime в UTC, возвращает aware-datetime (UTC).

    SQLite не умеет хранить таймзону, поэтому приводим всё к UTC при записи
    и навешиваем tzinfo=UTC при чтении. Так datetime всегда остаётся aware.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # naive трактуем как UTC, чтобы не терять данные
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class BookingStatus(str, enum.Enum):
    active = "active"
    cancelled = "cancelled"
    done = "done"


class Client(Base):
    __tablename__ = "clients"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="client")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    price: Mapped[int] = mapped_column(Integer, default=0)  # в рублях
    duration_min: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Branch(Base):
    """Филиал салона/сети (адрес, активность). Для одиночного салона можно не заводить."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Telegram ID мастера — чтобы он со своего аккаунта видел свои записи. None = не привязан.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    # Профиль мастера (редактирует сам мастер): специализация и фото-аватар (file_id).
    description: Mapped[str] = mapped_column(String(255), default="")
    photo_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Филиал мастера. None = сеть без филиалов (одиночный салон) или филиал не задан.
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )

    schedule: Mapped[list["MasterSchedule"]] = relationship(
        back_populates="master", cascade="all, delete-orphan"
    )
    branch: Mapped["Branch | None"] = relationship()


class MasterSchedule(Base):
    """Рабочие часы мастера по дню недели. weekday: 0=Пн ... 6=Вс.

    Время хранится строкой 'HH:MM'. Отсутствие записи на день = выходной.
    """

    __tablename__ = "master_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)  # 0..6
    start_time: Mapped[str] = mapped_column(String(5))  # 'HH:MM'
    end_time: Mapped[str] = mapped_column(String(5))  # 'HH:MM'

    master: Mapped["Master"] = relationship(back_populates="schedule")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.telegram_id")
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"))
    start_dt: Mapped[datetime] = mapped_column(TZDateTime)
    end_dt: Mapped[datetime] = mapped_column(TZDateTime)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, native_enum=False, length=16),
        default=BookingStatus.active,
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    reminder_day_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_2h_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    client: Mapped["Client"] = relationship(back_populates="bookings")
    service: Mapped["Service"] = relationship()
    master: Mapped["Master"] = relationship()


class MasterInvite(Base):
    """Одноразовая ссылка-приглашение для привязки аккаунта мастера.

    Владелец генерирует токен, мастер открывает deep-link `?start=join_<token>` —
    и его Telegram-аккаунт привязывается к мастеру. Без логинов и паролей.
    """

    __tablename__ = "master_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    used_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class BlockedSlot(Base):
    """Недоступный интервал. master_id=None → блокировка всего салона."""

    __tablename__ = "blocked_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int | None] = mapped_column(
        ForeignKey("masters.id"), nullable=True
    )
    start_dt: Mapped[datetime] = mapped_column(TZDateTime)
    end_dt: Mapped[datetime] = mapped_column(TZDateTime)
    reason: Mapped[str] = mapped_column(String(255), default="")

    master: Mapped["Master | None"] = relationship()


class Setting(Base):
    """Key-value для настроек, меняемых на лету (опционально)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")

"""Async engine + фабрика сессий + инициализация схемы."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings
from db.models import Base

settings = get_settings()

engine = create_async_engine(settings.db_url, echo=False, future=True)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет, и мягко донакатывает новые колонки."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)


async def _ensure_columns(conn) -> None:
    """Лёгкая «миграция» для уже существующих БД: добавляем недостающие колонки.

    create_all не меняет существующие таблицы, поэтому новые поля на старых БД
    добавляем вручную через ALTER TABLE ADD COLUMN (SQLite это поддерживает).
    """
    result = await conn.exec_driver_sql("PRAGMA table_info(masters)")
    columns = {row[1] for row in result.fetchall()}
    if "telegram_id" not in columns:
        await conn.exec_driver_sql("ALTER TABLE masters ADD COLUMN telegram_id BIGINT")
    if "description" not in columns:
        await conn.exec_driver_sql("ALTER TABLE masters ADD COLUMN description VARCHAR(255) DEFAULT ''")
    if "photo_file_id" not in columns:
        await conn.exec_driver_sql("ALTER TABLE masters ADD COLUMN photo_file_id VARCHAR(255)")
    if "branch_id" not in columns:
        await conn.exec_driver_sql("ALTER TABLE masters ADD COLUMN branch_id INTEGER")

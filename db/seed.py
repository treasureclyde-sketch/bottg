"""Демо-данные при первом запуске: 1 мастер, типовые услуги, расписание.

Сидинг идемпотентен: если услуги/мастера уже есть — ничего не делает.
Для нового клиента достаточно очистить БД (удалить файл) и перезапустить бот.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select

from db.engine import async_session
from db.models import Master, MasterSchedule, Service

logger = logging.getLogger(__name__)

# Демо-услуги: (название, цена ₽, длительность мин)
DEMO_SERVICES = [
    ("Мужская стрижка", 1500, 45),
    ("Стрижка + борода", 2200, 75),
    ("Оформление бороды", 900, 30),
    ("Детская стрижка", 1200, 40),
]

DEMO_MASTER_NAME = "Алексей"

# Демо-расписание: пн–пт 10:00–20:00, сб 11:00–18:00, вс выходной.
DEMO_SCHEDULE = {
    0: ("10:00", "20:00"),
    1: ("10:00", "20:00"),
    2: ("10:00", "20:00"),
    3: ("10:00", "20:00"),
    4: ("10:00", "20:00"),
    5: ("11:00", "18:00"),
    # 6 (вс) — выходной, записи нет
}


async def seed_if_empty() -> None:
    """Засеять демо-данные, если в БД ещё нет услуг и мастеров."""
    async with async_session() as session:
        services_count = await session.scalar(select(func.count()).select_from(Service))
        masters_count = await session.scalar(select(func.count()).select_from(Master))

        if services_count and masters_count:
            return  # уже есть данные — не трогаем

        if not services_count:
            for title, price, duration in DEMO_SERVICES:
                session.add(
                    Service(title=title, price=price, duration_min=duration, is_active=True)
                )
            logger.info("Засеяно демо-услуг: %d", len(DEMO_SERVICES))

        if not masters_count:
            master = Master(name=DEMO_MASTER_NAME, is_active=True)
            session.add(master)
            await session.flush()  # получить master.id
            for weekday, (start, end) in DEMO_SCHEDULE.items():
                session.add(
                    MasterSchedule(
                        master_id=master.id,
                        weekday=weekday,
                        start_time=start,
                        end_time=end,
                    )
                )
            logger.info("Засеян демо-мастер: %s", DEMO_MASTER_NAME)

        await session.commit()

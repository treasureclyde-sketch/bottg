"""Ссылки-приглашения для привязки аккаунта мастера (вместо логинов/паролей).

Владелец создаёт одноразовый токен → deep-link `t.me/<bot>?start=join_<token>`.
Мастер открывает ссылку — его Telegram-аккаунт привязывается к мастеру.
"""
from __future__ import annotations

import secrets

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Master, MasterInvite, utcnow

JOIN_PREFIX = "join_"


def build_deep_link(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start={JOIN_PREFIX}{token}"


async def create_invite(session: AsyncSession, master_id: int) -> str:
    """Создать новый одноразовый токен, погасив прежние неиспользованные."""
    await session.execute(
        delete(MasterInvite).where(
            MasterInvite.master_id == master_id,
            MasterInvite.used_at.is_(None),
        )
    )
    token = secrets.token_urlsafe(9)
    session.add(MasterInvite(master_id=master_id, token=token))
    await session.flush()
    return token


async def redeem_invite(
    session: AsyncSession, token: str, telegram_id: int
) -> Master | None:
    """Применить токен: привязать аккаунт к мастеру. None, если токен невалиден."""
    invite = await session.scalar(
        select(MasterInvite).where(MasterInvite.token == token)
    )
    if invite is None or invite.used_at is not None:
        return None

    master = await session.get(Master, invite.master_id)
    if master is None or not master.is_active:
        return None

    # один аккаунт = один мастер: снимаем эту привязку с других мастеров
    await session.execute(
        update(Master)
        .where(Master.telegram_id == telegram_id, Master.id != master.id)
        .values(telegram_id=None)
    )

    master.telegram_id = telegram_id
    invite.used_at = utcnow()
    invite.used_by = telegram_id
    await session.flush()
    return master

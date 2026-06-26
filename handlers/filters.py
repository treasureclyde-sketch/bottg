"""Общие фильтры."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import get_settings

settings = get_settings()


class IsAdmin(BaseFilter):
    """Пропускает событие, только если отправитель — администратор из конфига."""

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and settings.is_admin(user.id)

"""Middleware подписки: приостанавливает бота при истёкшей оплате.

Стоит outer-middleware перед всеми хендлерами. Пока подписка активна — пропускает
апдейты дальше. Если истекла — вежливо отвечает и НЕ запускает обработчики:
клиенту показывает «запись недоступна», админу (владельцу салона) — что нужно
продлить оплату у поставщика бота.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

import texts
from config import get_settings
from services.billing import is_subscription_active

logger = logging.getLogger(__name__)
settings = get_settings()


def _user_from_update(update: Update) -> User | None:
    """Достаём отправителя из апдейта (outer-middleware может стоять до контекста aiogram)."""
    for attr in ("message", "edited_message", "callback_query", "my_chat_member", "chat_member"):
        obj = getattr(update, attr, None)
        if obj is not None and getattr(obj, "from_user", None):
            return obj.from_user
    return None


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if await is_subscription_active():
            return await handler(event, data)

        # Подписка истекла — мягко тормозим апдейт.
        user: User | None = data.get("event_from_user")
        if user is None and isinstance(event, Update):
            user = _user_from_update(event)
        is_admin = user is not None and settings.is_admin(user.id)

        if is_admin:
            notice = texts.subscription_expired_admin(settings.provider_contact)
        else:
            notice = texts.subscription_expired_client(settings.business_phone)

        try:
            if isinstance(event, Update):
                if event.message:
                    await event.message.answer(notice)
                elif event.callback_query:
                    await event.callback_query.answer(notice, show_alert=True)
        except Exception:  # noqa: BLE001 - не падаем на ответе
            logger.debug("Не удалось отправить уведомление о подписке", exc_info=True)
        return None  # хендлеры не вызываем

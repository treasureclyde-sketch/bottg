"""Сторона салонного бота: проверка подписки через центральный биллинг.

Если центральный биллинг настроен (BILLING_DB_PATH + CLIENT_SLUG) — читаем
`paid_until` из общей БД с коротким кэшем (реакция на оплату ≤ TTL, без рестарта).
Если биллинг не настроен, БД недоступна или строки нет — НЕ глушим бота, а
откатываемся на статичный SUBSCRIPTION_UNTIL (fail-open) и пишем предупреждение.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_CACHE_TTL_SEC = 60
# кэш одной строки (этот процесс знает только про свой slug)
_cache: dict[str, object] = {"ts": 0.0, "paid_until": None, "found": False}


def billing_enabled() -> bool:
    return bool(settings.billing_db_path and settings.client_slug)


def _today() -> date:
    return datetime.now(settings.tz).date()


async def _paid_until_from_store() -> tuple[bool, date | None]:
    """(found, paid_until) из центральной БД, с кэшем. Ошибки → (False, None)."""
    now = time.monotonic()
    if now - float(_cache["ts"]) < _CACHE_TTL_SEC and _cache["ts"]:
        return bool(_cache["found"]), _cache["paid_until"]  # type: ignore[return-value]

    from billing import store  # локальный импорт, чтобы не тянуть биллинг без нужды

    try:
        view = await store.get(settings.billing_db_path, settings.client_slug)
    except Exception:  # noqa: BLE001 - любая проблема с БД → fail-open
        logger.warning("Биллинг недоступен, откат на SUBSCRIPTION_UNTIL", exc_info=True)
        _cache.update(ts=now, found=False, paid_until=None)
        return False, None

    found = view is not None
    paid_until = view.paid_until if view else None
    _cache.update(ts=now, found=found, paid_until=paid_until)
    if not found:
        logger.warning(
            "Клиент '%s' не найден в биллинге — откат на SUBSCRIPTION_UNTIL",
            settings.client_slug,
        )
    return found, paid_until


async def is_subscription_active() -> bool:
    """Активна ли подписка прямо сейчас (учёт центрального биллинга + fallback)."""
    if not billing_enabled():
        return settings.subscription_active()

    found, paid_until = await _paid_until_from_store()
    if not found:
        return settings.subscription_active()  # fail-open на статичный конфиг
    if paid_until is None:
        return True  # запись есть, дата пустая = бессрочно
    return _today() <= paid_until


def invalidate_cache() -> None:
    _cache.update(ts=0.0, found=False, paid_until=None)

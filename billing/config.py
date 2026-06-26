"""Конфиг биллинг-бота провайдера (отдельный бот, отдельный токен)."""
from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BillingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    billing_bot_token: str
    billing_admin_ids: list[int]
    billing_db_path: str = "billing.db"
    timezone: str = "Europe/Moscow"
    default_trial_days: int = 14  # на сколько дней регистрировать нового клиента
    annual_price: int = 5000  # цена годовой подписки (для подписи на кнопке «+1 год»)

    @field_validator("billing_admin_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(p.strip()) for p in value.split(",") if p.strip()]
        if isinstance(value, (list, tuple)):
            return [int(v) for v in value]
        raise ValueError("BILLING_ADMIN_IDS должен быть строкой вида '123,456'")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.billing_admin_ids


@lru_cache
def get_billing_settings() -> BillingSettings:
    try:
        s = BillingSettings()  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "Ошибка конфигурации биллинг-бота. Проверьте .env: нужны "
            "BILLING_BOT_TOKEN и BILLING_ADMIN_IDS.\n"
            f"Подробности: {exc}"
        ) from exc
    if not s.billing_bot_token:
        raise SystemExit("BILLING_BOT_TOKEN не задан в .env")
    if not s.billing_admin_ids:
        raise SystemExit("BILLING_ADMIN_IDS не задан в .env")
    return s

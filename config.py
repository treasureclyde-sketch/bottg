"""Конфигурация бота из переменных окружения (.env).

Используется pydantic-settings. При отсутствии обязательных полей
(BOT_TOKEN, ADMIN_IDS) приложение падает с понятной ошибкой ещё до старта.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки приложения. Читаются из .env (или окружения)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Обязательные ---
    bot_token: str
    admin_ids: list[int]

    # --- Бизнес / тексты ---
    business_name: str = "Барбершоп"
    business_address: str = ""
    business_phone: str = ""

    # --- Время и слоты ---
    timezone: str = "Europe/Moscow"
    slot_step_min: int = 30
    booking_horizon_days: int = 14
    booking_buffer_min: int = 30  # буфер на сегодня: не показывать слоты ближе чем через N минут

    # --- Напоминания ---
    reminder_day_before_hour: int = 20  # час, в который слать напоминание накануне
    reminder_2h_enabled: bool = True
    reminder_check_interval_min: int = 5  # как часто планировщик проверяет брони

    # --- Хранилище ---
    db_path: str = "bot.db"

    # --- Подписка (SaaS) и портфолио ---
    # Дата, до которой (включительно) оплачена подписка. Пусто = бессрочно.
    # Используется как fallback, если центральный биллинг недоступен/не настроен.
    subscription_until: date | None = None
    # Идентификатор этого салона в центральном биллинге (если используется).
    client_slug: str = ""
    # Путь к общей БД биллинга. Пусто = биллинг выключен, берём subscription_until.
    billing_db_path: str = ""
    # Контакт поставщика бота (тебя) — показывается админу при истёкшей подписке.
    provider_contact: str = ""
    # Папка с фото примеров работ для раздела «Наши работы». Пусто/нет папки = раздел скрыт.
    works_dir: str = "works"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> list[int]:
        """Принимаем '123,456' либо уже готовый список."""
        if value is None or value == "":
            return []
        if isinstance(value, int):
            # pydantic-settings JSON-парсит одиночное число в int
            return [value]
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        if isinstance(value, (list, tuple)):
            return [int(v) for v in value]
        raise ValueError("ADMIN_IDS должен быть строкой вида '123,456'")

    @field_validator("subscription_until", mode="before")
    @classmethod
    def _parse_subscription_until(cls, value: object) -> date | None:
        """Пустая строка → None (бессрочно). Строка 'YYYY-MM-DD' → date."""
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value.strip())
        raise ValueError("SUBSCRIPTION_UNTIL должен быть датой 'YYYY-MM-DD'")

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - зависит от системы
            raise ValueError(f"Неизвестная таймзона: {value}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        """Готовый объект таймзоны для timezone-aware дат."""
        return ZoneInfo(self.timezone)

    @property
    def db_url(self) -> str:
        """Async-URL для SQLAlchemy + aiosqlite."""
        return f"sqlite+aiosqlite:///{self.db_path}"

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids

    def subscription_active(self) -> bool:
        """True, если подписка бессрочная или ещё не истекла (по дате в таймзоне салона)."""
        if self.subscription_until is None:
            return True
        today = datetime.now(self.tz).date()
        return today <= self.subscription_until


@lru_cache
def get_settings() -> Settings:
    """Singleton настроек. Бросает понятную ошибку, если конфиг не заполнен."""
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001 - хотим понятное сообщение пользователю
        raise SystemExit(
            "Ошибка конфигурации. Проверьте файл .env "
            "(см. .env.example). Обязательно заполните BOT_TOKEN и ADMIN_IDS.\n"
            f"Подробности: {exc}"
        ) from exc

    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан в .env")
    if not settings.admin_ids:
        raise SystemExit("ADMIN_IDS не задан в .env (укажите хотя бы один Telegram ID)")
    return settings

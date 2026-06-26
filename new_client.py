"""Конвейер развёртывания: создать папку нового клиента из брифа.

По JSON-брифу (см. briefs/example.json) скрипт:
  1. создаёт папку клиента  <base>/<slug>/  (+ пустую works/ для фото);
  2. пишет туда .env с его настройками;
  3. создаёт и засевает bot.db реальными услугами и мастерами клиента.

Дальше остаётся только запустить бота systemd-юнитом:
    sudo systemctl enable --now bot@<slug>

Использование:
    python new_client.py briefs/borodach.json                 # base = ./clients
    python new_client.py briefs/borodach.json /opt/bots        # base = /opt/bots
    python new_client.py briefs/borodach.json /opt/bots --force  # перезаписать .env

Код бота (этот репозиторий) общий для всех клиентов — у клиента в папке только
данные (.env, bot.db, works/). Обновил код → перезапустил ботов, и всё.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import Base, Branch, Master, MasterSchedule, Service

_DEFAULT_TRIAL_DAYS = 14

REQUIRED = ("slug", "bot_token", "admin_ids", "business_name")


def _fail(msg: str) -> None:
    print(f"❌ {msg}")
    raise SystemExit(1)


def _env_lines(brief: dict) -> str:
    def g(key, default=""):
        return brief.get(key, default)

    pairs = [
        ("BOT_TOKEN", g("bot_token")),
        ("ADMIN_IDS", ",".join(str(x) for x in g("admin_ids", []))),
        ("BUSINESS_NAME", g("business_name")),
        ("BUSINESS_ADDRESS", g("business_address")),
        ("BUSINESS_PHONE", g("business_phone")),
        ("TIMEZONE", g("timezone", "Europe/Moscow")),
        ("SLOT_STEP_MIN", g("slot_step_min", 30)),
        ("BOOKING_HORIZON_DAYS", g("booking_horizon_days", 14)),
        ("REMINDER_DAY_BEFORE_HOUR", g("reminder_day_before_hour", 20)),
        ("REMINDER_2H_ENABLED", str(g("reminder_2h_enabled", True)).lower()),
        ("DB_PATH", "bot.db"),
        ("SUBSCRIPTION_UNTIL", g("subscription_until")),
        ("CLIENT_SLUG", g("slug")),
        ("BILLING_DB_PATH", g("billing_db_path")),
        ("PROVIDER_CONTACT", g("provider_contact")),
        ("WORKS_DIR", "works"),
    ]
    return "\n".join(f"{k}={v}" for k, v in pairs) + "\n"


async def _seed_db(db_path: Path, brief: dict) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as s:
            for sv in brief.get("services", []):
                s.add(Service(
                    title=sv["title"], price=int(sv["price"]),
                    duration_min=int(sv["duration_min"]), is_active=True,
                ))
            # филиалы: имя → id (мастера ссылаются по имени филиала)
            branch_ids: dict[str, int] = {}
            for br in brief.get("branches", []):
                branch = Branch(name=br["name"], address=br.get("address", ""), is_active=True)
                s.add(branch)
                await s.flush()
                branch_ids[br["name"]] = branch.id
            for m in brief.get("masters", []):
                master = Master(
                    name=m["name"], is_active=True, telegram_id=m.get("telegram_id"),
                    description=m.get("description", ""),
                    branch_id=branch_ids.get(m.get("branch")) if m.get("branch") else None,
                )
                s.add(master)
                await s.flush()
                for weekday, rng in m.get("schedule", {}).items():
                    s.add(MasterSchedule(
                        master_id=master.id, weekday=int(weekday),
                        start_time=rng[0], end_time=rng[1],
                    ))
            await s.commit()
    finally:
        await engine.dispose()


async def _register_billing(brief: dict) -> date | None:
    """Зарегистрировать клиента в центральном биллинге (если задан billing_db_path)."""
    billing_db = brief.get("billing_db_path")
    if not billing_db:
        return None
    from billing import store

    raw = brief.get("subscription_until")
    if raw:
        paid_until = date.fromisoformat(raw)
    else:
        paid_until = datetime.now().date() + timedelta(days=_DEFAULT_TRIAL_DAYS)
    await store.upsert(
        billing_db, brief["slug"], title=brief["business_name"], paid_until=paid_until
    )
    return paid_until


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if not args:
        _fail("Укажите путь к брифу: python new_client.py briefs/<client>.json [base_dir]")

    brief_path = Path(args[0])
    base_dir = Path(args[1]) if len(args) > 1 else Path("clients")
    if not brief_path.is_file():
        _fail(f"Бриф не найден: {brief_path}")

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    for key in REQUIRED:
        if not brief.get(key):
            _fail(f"В брифе нет обязательного поля: {key}")

    slug = str(brief["slug"]).strip()
    folder = base_dir / slug
    db_path = folder / "bot.db"

    if db_path.exists() and not force:
        _fail(f"БД уже существует: {db_path}. Удалите её или запустите с --force (перезапишет .env, БД не трогает).")

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "works").mkdir(exist_ok=True)

    env_path = folder / ".env"
    if env_path.exists() and not force:
        _fail(f".env уже существует: {env_path}. Запустите с --force, чтобы перезаписать.")
    env_path.write_text(_env_lines(brief), encoding="utf-8")

    if not db_path.exists():
        asyncio.run(_seed_db(db_path, brief))

    billing_paid_until = asyncio.run(_register_billing(brief))

    n_services = len(brief.get("services", []))
    n_masters = len(brief.get("masters", []))
    print(f"✅ Клиент «{slug}» развёрнут в {folder}")
    print(f"   .env записан, БД засеяна: услуг {n_services}, мастеров {n_masters}")
    if billing_paid_until:
        print(f"   В биллинге: оплачено до {billing_paid_until:%d.%m.%Y}")
    print(f"   Фото примеров работ кладите в: {folder / 'works'}/")
    print("\nЗапуск на сервере:")
    print(f"   sudo systemctl enable --now bot@{slug}")


if __name__ == "__main__":
    main()

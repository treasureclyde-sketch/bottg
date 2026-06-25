"""Барбер-Лиды — бэкенд Telegram Mini App.

- Раздаёт мини-апп из ./static
- /api/shops  — барбершопы Уфы из 2ГИС (рейтинг, отзывы, фото), ключ на сервере
- /api/base   — личная база (лайки/скрытые) в Postgres, по Telegram-id
- авторизация — проверка подписи Telegram initData ботовым токеном

Env (см. .env.example): DATABASE_URL, BOT_TOKEN, DGIS_KEY, DGIS_CITY (по умолч. Уфа)
Запуск:  uvicorn app:app --host 127.0.0.1 --port 8000
"""
import hashlib
import hmac
import json
import math
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

import asyncpg
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://barber:barber@localhost:5432/barber")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DGIS_KEY = os.environ.get("DGIS_KEY", "")
DGIS_CITY = os.environ.get("DGIS_CITY", "Уфа")
DGIS_QUERY = os.environ.get("DGIS_QUERY", "барбершоп")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_base (
    owner      TEXT PRIMARY KEY,
    data       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

pool = None
_shops_cache = {"ts": 0, "items": []}
_region_id = None


@asynccontextmanager
async def lifespan(_app):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as c:
        await c.execute(SCHEMA)
    yield
    await pool.close()


app = FastAPI(title="Barber Leads", lifespan=lifespan)


# ---------- Telegram initData ----------
def verify_init(init_data: str) -> str:
    """Проверяет подпись initData и возвращает Telegram user id (строкой)."""
    if not init_data:
        raise HTTPException(401, "no init data")
    if not BOT_TOKEN:
        # без токена не можем проверить — отдаём id из данных только для локалки
        raise HTTPException(503, "bot token not configured")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got_hash = pairs.pop("hash", None)
    if not got_hash:
        raise HTTPException(401, "no hash")
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got_hash):
        raise HTTPException(401, "bad signature")
    user = json.loads(pairs.get("user", "{}"))
    uid = user.get("id")
    if not uid:
        raise HTTPException(401, "no user")
    return str(uid)


# ---------- 2ГИС ----------
async def dgis_region(client: httpx.AsyncClient) -> str:
    global _region_id
    if _region_id:
        return _region_id
    r = await client.get("https://catalog.api.2gis.com/2.0/region/search",
                         params={"q": DGIS_CITY, "key": DGIS_KEY})
    items = (r.json().get("result") or {}).get("items") or []
    if not items:
        raise HTTPException(502, "2gis: регион не найден")
    _region_id = str(items[0]["id"])
    return _region_id


def _photo_from(item):
    for ec in item.get("external_content", []) or []:
        for k in ("main_photo_url", "url", "preview_url"):
            if ec.get(k):
                return ec[k]
        for u in (ec.get("preview_urls") or []):
            if u:
                return u
    return ""


def _phone_from(item):
    for g in item.get("contact_groups", []) or []:
        for c in g.get("contacts", []) or []:
            if c.get("type") == "phone":
                return c.get("value") or c.get("text") or ""
    return ""


async def fetch_shops():
    if not DGIS_KEY:
        return []
    now = time.time()
    if _shops_cache["items"] and now - _shops_cache["ts"] < 6 * 3600:
        return _shops_cache["items"]
    out = []
    async with httpx.AsyncClient(timeout=20) as client:
        region = await dgis_region(client)
        fields = "items.point,items.reviews,items.external_content,items.contact_groups,items.address"
        for page in range(1, 5):  # до 200 организаций
            r = await client.get("https://catalog.api.2gis.com/3.0/items", params={
                "q": DGIS_QUERY, "region_id": region, "fields": fields,
                "page": page, "page_size": 50, "key": DGIS_KEY,
            })
            items = (r.json().get("result") or {}).get("items") or []
            if not items:
                break
            for it in items:
                rev = it.get("reviews") or {}
                rating = float(rev.get("general_rating") or 0)
                count = int(rev.get("general_review_count") or 0)
                pt = it.get("point") or {}
                out.append({
                    "id": "2gis/" + str(it.get("id")),
                    "name": it.get("name") or "",
                    "rating": rating,
                    "reviews": count,
                    "photo": _photo_from(it),
                    "address": it.get("address_name") or "",
                    "phone": _phone_from(it),
                    "lat": pt.get("lat"), "lon": pt.get("lon"),
                })
    # самые рейтинговые и обсуждаемые — вперёд
    for s in out:
        s["_score"] = s["rating"] * math.log10(s["reviews"] + 10)
    out = [s for s in out if s["name"] and s["rating"] >= 4.0]
    out.sort(key=lambda s: s["_score"], reverse=True)
    for s in out:
        s.pop("_score", None)
    out = out[:80]
    _shops_cache.update(ts=now, items=out)
    return out


@app.get("/api/shops")
async def api_shops(x_init_data: str = Header(default="")):
    try:
        shops = await fetch_shops()
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"shops": [], "error": str(e)}, status_code=200)
    return {"shops": shops}


@app.get("/api/base")
async def base_get(x_init_data: str = Header(default="")):
    owner = verify_init(x_init_data)
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT data FROM user_base WHERE owner=$1", owner)
    data = row["data"] if row else None
    if isinstance(data, str):
        data = json.loads(data)
    data = data or {}
    return {"liked": data.get("liked", []), "hidden": data.get("hidden", []), "seen": data.get("seen", [])}


@app.put("/api/base")
async def base_put(request: Request, x_init_data: str = Header(default="")):
    owner = verify_init(x_init_data)
    body = await request.json()
    data = {"liked": body.get("liked", []), "hidden": body.get("hidden", []), "seen": body.get("seen", [])}
    payload = json.dumps(data, ensure_ascii=False)
    async with pool.acquire() as c:
        await c.execute(
            """INSERT INTO user_base(owner, data, updated_at) VALUES($1,$2::jsonb,now())
               ON CONFLICT (owner) DO UPDATE SET data=$2::jsonb, updated_at=now()""",
            owner, payload)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True, "dgis": bool(DGIS_KEY), "bot": bool(BOT_TOKEN)}


STATIC = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")

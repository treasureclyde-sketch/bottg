"""Бэкенд барбершоп-CRM: FastAPI + Postgres.

Хранит «доску» (список барбершопов) для каждого кода доступа и отдаёт
статичный фронтенд из ./static. Один пользователь = один код доступа.

Запуск:
    uvicorn app:app --host 0.0.0.0 --port 8000

Переменные окружения (см. .env.example):
    DATABASE_URL  строка подключения к Postgres
    ACCESS_CODE   секретный код; если задан — все запросы к API должны
                  присылать заголовок X-Access-Code с этим значением.
"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://barber:barber@localhost:5432/barbershop"
)
# Если пусто — API открыт без кода (только для локальной проверки, не для прода).
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")

SCHEMA = """
CREATE TABLE IF NOT EXISTS boards (
    owner      TEXT PRIMARY KEY,
    shops      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
    yield
    await pool.close()


app = FastAPI(title="Barbershop CRM", lifespan=lifespan)

# Разрешаем обращаться к API и когда фронт открыт как локальный файл.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def owner_for(code: str) -> str:
    """Проверяет код доступа и возвращает «владельца» (пространство данных)."""
    if ACCESS_CODE:
        if code != ACCESS_CODE:
            raise HTTPException(status_code=401, detail="bad access code")
        return code
    return code or "default"


@app.get("/api/board")
async def get_board(x_access_code: str = Header(default="")):
    owner = owner_for(x_access_code)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT shops, updated_at FROM boards WHERE owner = $1", owner
        )
    if row is None:
        return {"shops": [], "updated_at": None}
    shops = row["shops"]
    if isinstance(shops, str):  # asyncpg отдаёт jsonb строкой
        shops = json.loads(shops)
    return {"shops": shops, "updated_at": row["updated_at"].isoformat()}


@app.put("/api/board")
async def put_board(request: Request, x_access_code: str = Header(default="")):
    owner = owner_for(x_access_code)
    body = await request.json()
    shops = body.get("shops", [])
    if not isinstance(shops, list):
        raise HTTPException(status_code=400, detail="shops must be a list")
    payload = json.dumps(shops, ensure_ascii=False)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO boards (owner, shops, updated_at)
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (owner)
            DO UPDATE SET shops = $2::jsonb, updated_at = now()
            RETURNING updated_at
            """,
            owner,
            payload,
        )
    return {"ok": True, "count": len(shops), "updated_at": row["updated_at"].isoformat()}


@app.get("/health")
async def health():
    return {"ok": True}


# Статика (index.html) — монтируется последней, чтобы не перехватывать /api.
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

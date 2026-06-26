"""Хендлеры (роутеры) бота."""
from aiogram import Router

from handlers import admin, booking, client, master


def build_root_router() -> Router:
    """Собрать корневой роутер. Порядок важен: сначала клиент/booking/master, затем admin."""
    root = Router()
    root.include_router(client.router)
    root.include_router(booking.router)
    root.include_router(master.router)
    root.include_router(admin.router)
    return root

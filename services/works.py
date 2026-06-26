"""Раздел «Наши работы»: список фото-примеров из папки клиента.

Фото лежат файлами в `WORKS_DIR` (по умолчанию ./works). Если папки нет или
она пуста — раздел в меню не показывается. Это удобно для «конвейера»: на каждого
клиента просто кладём его фото в его папку.
"""
from __future__ import annotations

from pathlib import Path

from config import get_settings

settings = get_settings()

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_TELEGRAM_ALBUM_LIMIT = 10  # максимум фото в одном альбоме


def list_work_photos(limit: int = _TELEGRAM_ALBUM_LIMIT) -> list[Path]:
    """Отсортированный список путей к фото примеров работ (не больше `limit`)."""
    folder = Path(settings.works_dir)
    if not folder.is_dir():
        return []
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    )
    return files[:limit]


def has_works() -> bool:
    return bool(list_work_photos(limit=1))

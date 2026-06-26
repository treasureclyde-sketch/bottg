"""Распознавание речи (голосовое -> текст) через OpenAI Whisper API.

Тот же OpenAI-ключ, что и для мозга. Если захочешь бесплатно/офлайн —
можно вернуть локальный faster-whisper, но это отдельная установка.
"""

from openai import OpenAI

import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY не задан в .env — он нужен для распознавания голоса"
            )
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def transcribe(path: str) -> str:
    with open(path, "rb") as f:
        resp = _get_client().audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
    return resp.text.strip()

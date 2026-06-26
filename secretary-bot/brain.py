"""Мозг секретаря на OpenAI (GPT).

Принимает текст пользователя, держит короткую память на чат и отвечает
по-человечески. Сюда же позже подключим поиск по 2ГИС и зрение (фото/меню).
"""

from collections import defaultdict, deque

from openai import AuthenticationError, OpenAI, RateLimitError

import config

MODEL = "gpt-4o-mini"  # дёшево и шустро для диалога; для фото/меню возьмём gpt-4o

SYSTEM = (
    "Ты — личный секретарь Тимура в Telegram. "
    "Общайся коротко, дружелюбно и по-человечески, на русском. "
    "Помогаешь с делами и напоминаниями. "
    "Поиск заведений по 2ГИС (кафе, рестораны и т.п.) скоро появится — "
    "если просят что-то найти или забронировать, честно скажи, что эта функция в разработке."
)

_client = None
# короткая память: последние реплики на каждый чат
_history = defaultdict(lambda: deque(maxlen=10))


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY не задан в .env")
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def reply(chat_id: int, user_text: str) -> str:
    hist = _history[chat_id]
    hist.append({"role": "user", "content": user_text})
    messages = [{"role": "system", "content": SYSTEM}, *hist]
    try:
        resp = _get_client().chat.completions.create(model=MODEL, messages=messages)
    except RateLimitError:
        raise RuntimeError(
            "Закончились кредиты OpenAI. Пополни баланс: platform.openai.com → Billing."
        )
    except AuthenticationError:
        raise RuntimeError("Ключ OpenAI не принят — проверь OPENAI_API_KEY в .env.")
    answer = resp.choices[0].message.content.strip()
    hist.append({"role": "assistant", "content": answer})
    return answer

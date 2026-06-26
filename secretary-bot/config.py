import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# Telegram — токен бота от @BotFather (НЕ номер телефона)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Твой личный telegram user id (бот слушается только тебя)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# OpenAI — мозг (GPT) + распознавание голоса (Whisper), один ключ на оба
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# 2ГИС — поиск мест (шаг 2)
DGIS_API_KEY = os.getenv("DGIS_API_KEY", "")

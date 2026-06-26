# Образ для запуска бота на любом контейнерном хостинге (Railway / Fly.io / Render / VPS).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Конфиг берётся из переменных окружения (BOT_TOKEN, ADMIN_IDS, ...) — .env не нужен.
# Для сохранности БД смонтируйте том и задайте DB_PATH=/data/bot.db
CMD ["python", "bot.py"]

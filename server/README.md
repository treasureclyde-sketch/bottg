# Барбершоп-CRM — сервер

Бэкенд на **FastAPI + Postgres**, который хранит твою базу барбершопов и
синхронизирует её между всеми устройствами. Фронтенд (`static/index.html`) —
тот же помощник по звонкам, но с облачной синхронизацией.

Инструкция для **Ubuntu / Debian** без Docker. Команды выполняешь на сервере
по SSH.

---

## 1. Поставить Postgres и Python

```bash
sudo apt update
sudo apt install -y postgresql python3 python3-venv git
```

## 2. Создать базу и пользователя

Придумай пароль и подставь его вместо `СВОЙ_ПАРОЛЬ`:

```bash
sudo -u postgres psql -c "CREATE USER barber WITH PASSWORD 'СВОЙ_ПАРОЛЬ';"
sudo -u postgres psql -c "CREATE DATABASE barbershop OWNER barber;"
```

## 3. Забрать код

```bash
sudo git clone https://github.com/treasureclyde-sketch/bottg.git /opt/bottg
cd /opt/bottg/server
```
*(репозиторий приватный — git попросит логин и токен GitHub)*

## 4. Установить зависимости

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 5. Настроить переменные

```bash
cp .env.example .env
nano .env
```
В `.env` укажи:
- `DATABASE_URL` — тот же пароль, что задал в шаге 2;
- `ACCESS_CODE` — придумай длинный секретный код (его же введёшь в приложении).

## 6. Запустить (проверка)

```bash
set -a; . .env; set +a
uvicorn app:app --host 0.0.0.0 --port 8000
```
Открой в браузере `http://АДРЕС_СЕРВЕРА:8000`, зайди на вкладку **★ База** →
блок **«Синхронизация»** → поле адреса оставь пустым, введи свой `ACCESS_CODE`
→ **Подключить**. Должно появиться «Синхронизировано ✓».

> Если открываешь приложение не с сервера (локальный файл), в поле адреса
> впиши полный `http://АДРЕС_СЕРВЕРА:8000`.

## 7. Автозапуск (чтобы работало постоянно)

```bash
sudo cp systemd/barbershop.service /etc/systemd/system/
# при необходимости поправь User/пути в файле
sudo systemctl daemon-reload
sudo systemctl enable --now barbershop
journalctl -u barbershop -f      # смотреть логи
```

---

## Порт и безопасность

- Открой порт: `sudo ufw allow 8000` (если включён ufw).
- **HTTPS (важно):** код доступа ходит в заголовке, по голому HTTP его видно в
  сети. Для боевого использования поставь домен + Nginx + бесплатный сертификат:
  ```bash
  sudo apt install -y nginx certbot python3-certbot-nginx
  ```
  Nginx проксирует `:80/:443` → `127.0.0.1:8000`, certbot выдаёт сертификат.
  Скажи мне — пришлю готовый конфиг под твой домен.

## Как устроены данные

- Таблица `boards(owner, shops jsonb, updated_at)`. `owner` = твой код доступа.
- Вся база барбершопов лежит в одной строке как JSON — приложение при любом
  изменении присылает её целиком (`PUT /api/board`), а при открытии забирает
  (`GET /api/board`). Для одного пользователя это просто и надёжно.
- Бэкап Postgres: `pg_dump -U barber barbershop > backup.sql`.

## API (если понадобится)

| Метод | Путь | Заголовок | Тело | Ответ |
|---|---|---|---|---|
| GET | `/api/board` | `X-Access-Code` | — | `{shops, updated_at}` |
| PUT | `/api/board` | `X-Access-Code` | `{shops:[…]}` | `{ok, count, updated_at}` |
| GET | `/health` | — | — | `{ok:true}` |

#!/usr/bin/env bash
# Деплой барбершоп-CRM на чистый Ubuntu/Debian одной командой.
#
# Запуск (от root или через sudo), из папки server/:
#     sudo bash deploy.sh
#
# Можно заранее задать свои значения:
#     ACCESS_CODE=мой-код DB_PASSWORD=мой-пароль PORT=8000 sudo -E bash deploy.sh
#
# Скрипт идемпотентный — можно запускать повторно (например, после git pull).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"   # путь к server/
PORT="${PORT:-8000}"

rand(){ head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-"${1:-24}"; }
DB_PASSWORD="${DB_PASSWORD:-$(rand 24)}"
ACCESS_CODE="${ACCESS_CODE:-$(rand 16)}"

echo "==> Установка пакетов (postgres, python)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y postgresql python3 python3-venv

echo "==> Запуск postgres"
systemctl enable --now postgresql

echo "==> База и пользователь"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='barber'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER barber WITH PASSWORD '${DB_PASSWORD}';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='barbershop'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE barbershop OWNER barber;"
sudo -u postgres psql -c "ALTER USER barber WITH PASSWORD '${DB_PASSWORD}';"

echo "==> Виртуальное окружение и зависимости"
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Файл .env"
if [ ! -f .env ]; then
  cat > .env <<EOF
DATABASE_URL=postgresql://barber:${DB_PASSWORD}@localhost:5432/barbershop
ACCESS_CODE=${ACCESS_CODE}
EOF
fi
ACCESS_CODE="$(grep -E '^ACCESS_CODE=' .env | cut -d= -f2-)"

echo "==> systemd-сервис (автозапуск)"
cat > /etc/systemd/system/barbershop.service <<EOF
[Unit]
Description=Barbershop CRM (FastAPI)
After=network.target postgresql.service

[Service]
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app:app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable barbershop
systemctl restart barbershop

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q active; then
  ufw allow "${PORT}" >/dev/null 2>&1 || true
fi

sleep 2
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "================= ГОТОВО ================="
echo "Приложение:   http://${IP}:${PORT}"
echo "Код доступа:  ${ACCESS_CODE}"
echo
echo "В приложении: вкладка «★ База» -> блок «Синхронизация»"
echo "  адрес сервера: оставь пустым (открываешь сайт с сервера)"
echo "  код доступа:   ${ACCESS_CODE}  -> Подключить"
echo
echo "Статус:  systemctl status barbershop"
echo "Логи:    journalctl -u barbershop -f"
echo "=========================================="

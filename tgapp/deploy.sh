#!/usr/bin/env bash
# Деплой Telegram Mini App «Барбер-Лиды» на Ubuntu/Debian одной командой.
# Поднимает: Postgres, Python-бэкенд (uvicorn), бота, nginx и БЕСПЛАТНЫЙ HTTPS
# (Let's Encrypt) на твой DuckDNS-поддомен. Покупать домен не нужно.
#
# Перед запуском заполни .env (см. .env.example): DOMAIN, BOT_TOKEN, DGIS_KEY,
# (опц.) DUCKDNS_TOKEN.
#
# Запуск из папки tgapp/:
#     cp .env.example .env && nano .env      # заполнить
#     sudo bash deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$APP_DIR/.env" ] || { echo "Нет .env — скопируй .env.example в .env и заполни."; exit 1; }
set -a; . "$APP_DIR/.env"; set +a

: "${DOMAIN:?Заполни DOMAIN в .env}"
: "${BOT_TOKEN:?Заполни BOT_TOKEN в .env}"
rand(){ head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-"${1:-24}"; }
DB_PASSWORD="${DB_PASSWORD:-$(rand 24)}"

echo "==> Пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y postgresql python3 python3-venv nginx certbot python3-certbot-nginx curl

echo "==> DuckDNS (привязка поддомена к IP сервера)"
SUB="${DOMAIN%%.duckdns.org}"
if [ -n "${DUCKDNS_TOKEN:-}" ] && [ "$SUB" != "$DOMAIN" ]; then
  curl -s "https://www.duckdns.org/update?domains=${SUB}&token=${DUCKDNS_TOKEN}&ip=" && echo " (ok)"
else
  echo "  DUCKDNS_TOKEN пуст — убедись, что на duckdns.org поддомен уже указывает на IP сервера."
fi

echo "==> Postgres"
systemctl enable --now postgresql
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='barber'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER barber WITH PASSWORD '${DB_PASSWORD}';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='barber'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE barber OWNER barber;"
# если DATABASE_URL c плейсхолдером — пропишем реальный
if grep -q 'ПОМЕНЯЙ_ПАРОЛЬ' "$APP_DIR/.env"; then
  sudo -u postgres psql -c "ALTER USER barber WITH PASSWORD '${DB_PASSWORD}';"
  sed -i "s#^DATABASE_URL=.*#DATABASE_URL=postgresql://barber:${DB_PASSWORD}@localhost:5432/barber#" "$APP_DIR/.env"
fi

echo "==> venv + зависимости"
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> systemd: бэкенд + бот"
cat > /etc/systemd/system/barber-app.service <<EOF
[Unit]
Description=Barber Leads API
After=network.target postgresql.service
[Service]
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/barber-bot.service <<EOF
[Unit]
Description=Barber Leads Bot
After=network.target
[Service]
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python bot.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now barber-app barber-bot
systemctl restart barber-app barber-bot

echo "==> nginx"
cat > /etc/nginx/sites-available/barber <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/barber /etc/nginx/sites-enabled/barber
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q active; then
  ufw allow 80 >/dev/null 2>&1 || true; ufw allow 443 >/dev/null 2>&1 || true
fi

echo "==> HTTPS-сертификат (Let's Encrypt)"
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --register-unsafely-without-email --redirect \
  || echo "  Certbot не выдал сертификат. Проверь, что ${DOMAIN} указывает на IP сервера и порт 80 открыт, потом запусти: sudo certbot --nginx -d ${DOMAIN}"

echo
echo "================= ГОТОВО ================="
echo "Мини-апп:  https://${DOMAIN}"
echo "Бот:       открой бота в Telegram -> /start -> кнопка приложения"
echo "Статус:    systemctl status barber-app barber-bot"
echo "Логи:      journalctl -u barber-app -f   |   journalctl -u barber-bot -f"
echo "=========================================="

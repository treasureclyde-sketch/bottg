#!/usr/bin/env bash
# Раздаёт статичный мини-апп (tgapp/static) на твоём сервере по HTTPS.
# Лёгкий: только nginx + бесплатный сертификат. Никаких БД и сервисов.
#
# Запуск на сервере (Ubuntu/Debian):
#     sudo DOMAIN=твой-домен bash serve.sh
# Если на сервере уже настроен HTTPS — DOMAIN можно не задавать, просто
# направь свой веб-сервер на папку tgapp/static.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/static" && pwd)"
DOMAIN="${DOMAIN:-_}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get install -y nginx

cat >/etc/nginx/sites-available/barber <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    root ${DIR};
    index index.html;
    location / { try_files \$uri \$uri/ /index.html; }
}
EOF
ln -sf /etc/nginx/sites-available/barber /etc/nginx/sites-enabled/barber
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q active; then
  ufw allow 80 >/dev/null 2>&1 || true; ufw allow 443 >/dev/null 2>&1 || true
fi

if [ "$DOMAIN" != "_" ]; then
  apt-get install -y certbot python3-certbot-nginx
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect \
    && echo "ГОТОВО: https://${DOMAIN}" \
    || echo "Certbot не выдал сертификат. Проверь, что ${DOMAIN} указывает на IP сервера и открыт порт 80."
else
  echo "Раздаётся по HTTP (для проверки). Telegram требует HTTPS — запусти с доменом:"
  echo "    sudo DOMAIN=твой-домен bash serve.sh"
fi

# 🚀 Деплой на VPS (Timeweb, Ubuntu 24.04)

Поднимаем на одном сервере **«Гагарин»** (реальный клиент) и **демо-бота** (витрина для показа).
Все команды — copy-paste. Где `SERVER_IP` — подставь IP своего сервера из панели Timeweb.

> Один токен = один работающий поллинг. Пока бот крутится на VPS — **не запускай его же локально**,
> иначе Telegram будет ругаться на конфликт. (Локальный тестовый процесс к этому моменту уже не нужен.)

---

## 0. Что нужно перед стартом
- VPS заказан, есть **IP** и **root-пароль** (или SSH-ключ) из панели Timeweb.
- Для демо — **отдельный бот-токен** от [@BotFather](https://t.me/BotFather) (`/newbot`). Вставь его
  в `briefs/demo.json` в поле `bot_token` (можно прямо сейчас, локально).

---

## 1. Скопировать проект на сервер (с Mac)

В терминале на Маке (не на сервере):

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='run.log' \
  /Users/tim/Barbershops/ root@SERVER_IP:/opt/booking-bot/
```

Спросит root-пароль. Это перенесёт код + готовую базу «Гагарина» (с фото) + брифы.

---

## 2. Настроить окружение (на сервере)

Зайди на сервер: `ssh root@SERVER_IP`, дальше:

```bash
apt update && apt install -y python3 python3-venv python3-pip rsync
cd /opt/booking-bot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## 3. Разложить данные клиентов

```bash
mkdir -p /opt/bots
# реальные данные «Гагарина» (БД с фото + .env) переносим в стандартное место
mv /opt/booking-bot/clients/gagarin /opt/bots/gagarin
```

---

## 4. systemd-юнит и запуск «Гагарина»

Юнит написан под пользователя `ubuntu`. На root-VPS проще запускать от root —
поправим одной командой:

```bash
sed 's/^User=ubuntu/User=root/' /opt/booking-bot/deploy/bot@.service \
  > /etc/systemd/system/bot@.service
systemctl daemon-reload
systemctl enable --now bot@gagarin
systemctl status bot@gagarin --no-pager
```

Должно быть `active (running)`. Логи в реальном времени: `journalctl -u bot@gagarin -f`

---

## 5. Демо-бот (витрина)

Токен демо-бота уже должен быть в `briefs/demo.json`. Засеваем и запускаем:

```bash
cd /opt/booking-bot
.venv/bin/python new_client.py briefs/demo.json /opt/bots
systemctl enable --now bot@demo
systemctl status bot@demo --no-pager
```

Готово — демо живёт по своему `@username`, кидай ссылку кому угодно.

---

## 6. Бэкапы БД (сделай сразу)

```bash
mkdir -p /opt/backups
crontab -e
```
Добавь строку (бэкап всех баз каждую ночь в 4:00, хранить 14 дней):
```
0 4 * * *  tar czf /opt/backups/bots-$(date +\%F).tgz /opt/bots/*/bot.db && find /opt/backups -name 'bots-*.tgz' -mtime +14 -delete
```

---

## 7. Управление

```bash
systemctl restart bot@gagarin     # после правки .env / данных
systemctl stop bot@demo           # приостановить
systemctl list-units 'bot@*'      # какие боты запущены
journalctl -u bot@gagarin -n 50   # последние логи
```

## 8. Обновление кода в будущем

С Мака:
```bash
rsync -av --exclude='.venv' --exclude='__pycache__' \
  --exclude='clients' --exclude='run.log' \
  /Users/tim/Barbershops/ root@SERVER_IP:/opt/booking-bot/
ssh root@SERVER_IP 'systemctl restart bot@gagarin bot@demo'
```
(Здесь `--exclude='clients'` — чтобы не затереть рабочие данные на сервере.)

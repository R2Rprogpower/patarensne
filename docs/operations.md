# Запуск и эксплуатация

Архитектура компонентов описана в [architecture.md](architecture.md), а воспроизводимые unit, Docker, end-to-end и интеграционные проверки — в [testing.md](testing.md).

Пошаговая инструкция для оператора без технической подготовки находится в
[user-guide.md](user-guide.md). Этот документ оставлен как краткая памятка для
ежедневной эксплуатации.

## Требования

- Docker Engine с Compose v2;
- отдельный Telegram user account для MTProto;
- Telegram API-приложение, созданное владельцем аккаунта;
- локальный `.env`, который никогда не отправляется в чат и не коммитится.

## Подготовка

```bash
cp .env.example .env
mkdir -p data/imports data/exports
chmod 700 data
docker compose build discovery
```

После копирования заполнить пустые Telegram-поля `.env` локально. Для профиля `web-search` также задать локальный `SEARXNG_SECRET`. Не размещать значения в командах или скриншотах.

## Первая авторизация

```bash
docker compose run --rm discovery auth
```

Телефон, одноразовый код и 2FA-пароль вводятся в скрытых интерактивных запросах. В `data/` появится session-файл.

## Поиск только в Telegram

```bash
docker compose run --rm discovery discover
```

## Добавление ручного списка

Положить файл в `data/imports/`, затем:

```bash
docker compose run --rm discovery discover --input /app/data/imports/seeds.txt
```

Флаг `--input` можно повторять для нескольких TXT/CSV.

## Telegram + локальный SearXNG

Первый раз запустить внутренний поисковик:

```bash
docker compose --profile web-search up -d searxng
docker compose run --rm discovery discover --web
```

SearXNG не публикуется на хост и доступен только контейнерам Compose-сети. Исходящий доступ сети нужен Telegram и поисковикам.

## Повторный экспорт

```bash
docker compose run --rm discovery export
```

## Полезные параметры

```text
--query-file PATH
--input PATH                 можно повторять
--limit-per-query N
--min-score N
--telegram / --no-telegram
--web / --no-web
--validate / --no-validate
--activity-days N
--active-min-messages N
--activity-max-messages N
--min-members N
--min-messages N
--min-unique-authors N
--max-days-since-last-message N
--entity-type group|channel|unknown
--activity-status active|low_activity|inactive|unknown|unavailable
--captcha-status yes|no|unknown
```

Команда без `--query` и `--query-file` использует legacy-файл запросов про
Киев. Для любого нового задания запросы необходимо указывать явно.

Для офлайн-нормализации импортированного файла без Telegram:

```bash
docker compose run --rm discovery discover \
  --no-telegram --no-validate \
  --input /app/data/imports/seeds.csv
```

## Резервное копирование

Достаточно локально копировать:

- `data/discovery.sqlite3`;
- `data/telegram.session` — отдельно и как секрет;
- `data/exports/` — если нужна история выгрузок.

Session-файл нельзя отправлять заказчику, в чат или добавлять в Git.

## Планировщик

Запуск по cron/systemd должен вызывать одну команду `docker compose run --rm discovery discover`. Не запускайте два экземпляра одновременно на одной SQLite-базе и одной Telegram-сессии.

# Передача проекта другому агенту или разработчику

Этот документ нужен тому, кто продолжает разработку, тестирует приложение или
выполняет сбор данных вместо предыдущего оператора.

## 1. Назначение и текущий статус

Приложение — локальный read-only конвейер поиска публичных Telegram-групп и
каналов. Реализованы:

- Telegram Search по нескольким запросам;
- импорт TXT/CSV;
- опциональный SearXNG-провайдер;
- нормализация и дедупликация;
- проверка публичных метаданных;
- evidence-based определение captcha по публичному тексту;
- подсчёт доступной активности без сохранения текста сообщений;
- SQLite с автоматическими миграциями;
- полный и filtered экспорт CSV/JSON/TXT;
- unit/integration tests с моками и живой read-only smoke-test.

Приложение не вступает в группы, не пишет сообщения и не обходит ограничения.

## 2. Быстрая ориентация по файлам

```text
src/chat_discovery/cli.py                 CLI, аргументы и запуск команд
src/chat_discovery/service.py             orchestration конвейера
src/chat_discovery/providers/telegram.py  поиск, metadata, activity
src/chat_discovery/providers/files.py     TXT/CSV импорт
src/chat_discovery/providers/searxng.py   web provider
src/chat_discovery/captcha.py             публичные признаки captcha
src/chat_discovery/filtering.py           фильтры результата
src/chat_discovery/storage.py             SQLite и миграции
src/chat_discovery/export.py              CSV/JSON/TXT контракт
src/chat_discovery/models.py              доменные модели
tests/                                    автоматические тесты
docs/user-guide.md                        инструкция оператору
docs/testing.md                           расширенная приёмка
```

## 3. Первый безопасный осмотр

```bash
git status --short
git log -5 --oneline
docker compose config --quiet
docker compose --profile test build test
docker compose build discovery
```

Не удалять и не перезаписывать пользовательские `.env`, `data/` и незакоммиченные
изменения. Сначала проверить `git status`.

## 4. Секреты и данные

Никогда не читать вслух, логировать, коммитить или отправлять:

- `.env`;
- `data/telegram.session*`;
- содержимое `tdata`;
- Telegram code/2FA/API hash;
- пользовательскую SQLite-базу без разрешения владельца.

Для проверки наличия настроек достаточно метаданных файлов и факта, что
`docker compose run --rm discovery auth` сообщает об авторизованной сессии.
Не печатать значения переменных.

Для согласованной миграции защищённого ZIP использовать только
`scripts/import_session_bundle.py` и инструкцию `docs/session-migration.md`.
Скрипт импортирует минимально необходимые credentials и игнорирует остальное.

## 5. Контракт CLI

Основные команды:

```bash
docker compose run --rm discovery auth
docker compose run --rm discovery discover --help
docker compose run --rm discovery export --help
```

Ключевые свойства:

- без явных запросов используется `config/queries-kyiv.txt`;
- `--activity-days 0` отключает историю;
- фильтры на `discover` создают дополнительный `<name>-filtered.*`;
- фильтры на `export` экспортируют только отфильтрованную выборку под заданным
  `--output-name`;
- `--min-score` — legacy-фильтр географической релевантности, по умолчанию `0`;
- несколько значений `entity/activity/captcha` задаются повторением флага;
- лимит Telegram Search внутри провайдера не выше 100 на один запрос;
- exit code `0` — успех, `1` — ошибка, `130` — прерывание оператором.

## 6. Контракт данных

Экспортируемые поля определены в `src/chat_discovery/export.py:CSV_FIELDS`.
При изменении полей синхронно обновить:

1. модели;
2. SQLite schema/migration;
3. upsert/read mapping;
4. CSV и JSON serialization;
5. tests;
6. `docs/user-guide.md`.

Семантика важных значений:

- `None`/пустая ячейка — значение не предоставлено, не равно нулю;
- `captcha_status=unknown` — проверка без вступления невозможна;
- `activity_status=unknown` — сканирование не запускалось;
- `activity_status=unavailable` — запускалось, но история недоступна;
- `message limit reached; counts are lower bounds` — метрики не точные сверху;
- `unique_authors` считает доступные sender IDs, а не реальных физических лиц.

## 7. Минимальная приёмка после изменений

```bash
docker compose config --quiet
docker compose --profile test build test
docker compose build discovery
git diff --check
```

Офлайн smoke-test выполнять по `docs/testing.md`. Он обязателен после изменения
storage, export, normalization, CLI или migrations.

Живой Telegram smoke-test нужен после изменения Telegram provider, activity или
авторизации. Использовать:

- отдельную тестовую базу/каталог;
- один нейтральный запрос;
- `--limit-per-query 2`;
- `--activity-days 1`;
- `--activity-max-messages 20`;
- только read-only действия.

Запрещено ради теста вступать в чат, отправлять сообщения или проходить captcha.

## 8. Рекомендуемый живой smoke-test

Команда должна выполняться только при наличии разрешённой локальной сессии:

```bash
docker compose run --rm discovery discover \
  --query "чаты Киев" \
  --limit-per-query 2 \
  --activity-days 1 \
  --activity-max-messages 20 \
  --output-name smoke-live
```

Проверить:

- exit code 0;
- созданы три экспорта;
- ссылки нормализованы;
- тексты сообщений нигде не сохранены;
- capped result помечен как lower bound;
- повторный запуск не создаёт дублей.

## 9. Известные ограничения

1. Telegram не предоставляет полный публичный каталог.
2. Search выдача зависит от аккаунта, языка, региона и времени.
3. Наличие captcha обычно нельзя доказать без вступления.
4. Публичная история некоторых объектов недоступна.
5. Каналы и группы имеют разную семантику авторов.
6. Большой activity scan выполняется долго и может вызвать FloodWait.
7. SQLite и session-файл не рассчитаны на параллельные процессы.
8. Общая база содержит накопленные результаты всех прошлых запусков.
9. `no` для captcha не следует выводить только из отсутствия ключевых слов.
10. Географический scorer сохранён как legacy-компонент; универсальные запросы
    должны использовать `--min-score 0` (значение по умолчанию).

## 10. Как выполнить пользовательский сбор

1. Уточнить тему, города/языки, период и критерии активности.
2. Сформировать 3–6 вариантов запроса, не десятки почти одинаковых.
3. Выбрать отдельный `--output-name`.
4. Сначала выполнить малый запуск с `--limit-per-query 3`.
5. Если он успешен, выполнить полный запуск.
6. Проверить несколько ссылок и метрик вручную.
7. Отдать CSV/JSON и краткую сводку, объяснив lower bounds и captcha unknown.
8. Не отдавать session, `.env`, SQLite и внутренние тестовые файлы.

## 11. Как передать код дальше

Перед commit/push:

```bash
git status --short
git diff --check
docker compose --profile test build test
git diff --stat
```

Проверить, что в staged changes отсутствуют:

```text
.env
data/
*.session
*.session-journal
*.sqlite3
tdata/
```

В handoff-сообщении указать:

- commit hash и branch;
- что именно реализовано;
- результаты tests/offline/live smoke-test;
- какие live-действия выполнялись;
- известные ограничения;
- команды запуска;
- что secrets и пользовательские данные не включены.

## 12. Правило честной отчётности

Не писать «капчи нет», если статус `unknown`. Не писать «ровно 500 сообщений»,
если достигнут лимит. Не писать «найдены все чаты». Корректные формулировки:

- «публичных признаков captcha не найдено; статус unknown»;
- «не менее 500 сообщений за период»;
- «найдено N уникальных результатов в выдаче Telegram по заданным запросам».

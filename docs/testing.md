# Инструкция по тестированию

## Что покрывает эта инструкция

Автоматические тесты и команды ниже проверяют discovery, captcha-маркировку, Activity Scanner, фильтрацию и экспорт.

Тестирование разделено на четыре уровня:

1. быстрые unit-тесты без сети;
2. сборка и security-параметры Docker;
3. офлайн end-to-end через TXT/CSV → SQLite → экспорт;
4. ручные интеграционные тесты Telegram и SearXNG.

Живые Telegram-тесты не должны запускаться в публичном CI: для них нужна локальная пользовательская сессия.

## Предварительные условия

- Docker Engine и Docker Compose v2;
- Git;
- для живых тестов — локально подготовленные `.env` и `data/telegram.session` по [инструкции эксплуатации](operations.md);
- команды выполняются из корня репозитория.

Проверить окружение:

```bash
docker version
docker compose version
git status --short
```

Перед тестом рабочее дерево должно содержать только ожидаемые изменения. Не удаляйте существующий `data/`: там может находиться Telegram-сессия.

## 1. Автоматические тесты

Основная команда запускает pytest внутри изолированного test-stage образа:

```bash
docker compose --profile test build test
```

Ожидаемый результат:

```text
17 passed
```

Текущие тесты проверяют:

- нормализацию `t.me`-ссылок и отбрасывание неподдерживаемых ссылок;
- распознавание Киева и районов в разных вариантах написания;
- пороговый скоринг;
- создание схемы SQLite;
- idempotent upsert кандидатов и источников;
- сохранение качественных метаданных при повторном импорте;
- CSV/JSON/TXT-экспорт и фильтрацию входа для Activity Scanner.
- консервативное определение captcha;
- подсчёт сообщений и уникальных авторов на моках;
- фильтры активности, участников, типа и captcha.

Дополнительная быстрая проверка синтаксиса без Docker:

```bash
python3 -m compileall -q src tests
```

## 2. Проверка Docker-конфигурации

Проверить корректность Compose:

```bash
docker compose config --quiet
docker compose --profile web-search config --quiet
```

Собрать production-образ:

```bash
docker compose build discovery
```

Проверить непривилегированного пользователя образа:

```bash
docker image inspect telegram-group-activity-scanner-discovery \
  --format '{{.Config.User}}'
```

Ожидается непустое значение `app`. В `docker compose config` у сервисов также должны присутствовать:

- `read_only: true`;
- `cap_drop: ALL`;
- `no-new-privileges:true`;
- отсутствие секции `ports`;
- запись только в `./data:/app/data` и `tmpfs`.

Проверить исключение секретов и runtime-данных из Git:

```bash
git check-ignore .env data/telegram.session data/discovery.sqlite3
```

Команда должна вывести все три пути.

## 3. Офлайн end-to-end тест

Этот сценарий не использует Telegram, SearXNG или секреты. Он проверяет весь локальный путь от CSV до трёх экспортов.

Подготовить копию тестового набора в примонтированном каталоге:

```bash
mkdir -p data/imports data/smoke/exports
cp tests/fixtures/seeds.csv data/imports/smoke-seeds.csv
```

Запустить конвейер:

```bash
docker compose run --rm \
  -e DATABASE_PATH=/app/data/smoke/discovery.sqlite3 \
  discovery discover \
  --no-telegram \
  --no-validate \
  --input /app/data/imports/smoke-seeds.csv \
  --output-dir /app/data/smoke/exports
```

Ожидается сообщение о завершённом запуске и файлы:

```text
data/smoke/exports/telegram-results.csv
data/smoke/exports/telegram-results.json
data/smoke/exports/telegram-results.txt
```

Проверить результат:

```bash
test -s data/smoke/exports/telegram-results.csv
test -s data/smoke/exports/telegram-results.json
test -s data/smoke/exports/telegram-results.txt
wc -l data/smoke/exports/telegram-results.txt
```

Для текущего fixture TXT должен содержать две ссылки. CSV и JSON могут содержать больше диагностических полей, чем TXT.

### Проверка идемпотентности

Повторить ту же команду `discover`, затем снова проверить TXT:

```bash
wc -l data/smoke/exports/telegram-results.txt
```

Количество ссылок должно остаться прежним. В SQLite не должны появиться дубли кандидатов или одинаковых записей provenance. При необходимости проверить напрямую:

```bash
docker compose run --rm --entrypoint python discovery -c \
  "import sqlite3; db=sqlite3.connect('/app/data/smoke/discovery.sqlite3'); print(db.execute('select count(*) from candidates').fetchone()[0]); print(db.execute('select count(*) from candidate_sources').fetchone()[0])"
```

Числа не должны увеличиваться при повторе идентичного импорта.

## 4. Живой тест Telegram

Этот тест выполнять только локально и только после интерактивной авторизации:

```bash
docker compose run --rm discovery auth
```

Не копируйте телефон, код входа, пароль 2FA, `.env` или session-файл в issue, чат, лог CI либо командную строку.

Для короткого smoke-теста ограничить число результатов:

```bash
docker compose run --rm discovery discover --query "Київ чат" --limit-per-query 5
```

Безопасный короткий тест активности:

```bash
docker compose run --rm discovery discover \
  --query "Київ чат" \
  --limit-per-query 3 \
  --activity-days 1 \
  --activity-max-messages 100
```

Критерии успешности:

- команда завершается кодом `0`;
- в выводе есть идентификатор запуска и количество кандидатов;
- `data/exports/telegram-results.csv`, `.json` и `.txt` созданы;
- у проверенных записей заполнены `checked_at`, `entity_type` и `access_status`;
- клиент не вступил ни в одну группу и не отправил сообщений.

Если Telegram вернул `FloodWait`, сервис должен выдержать указанную паузу и повторить проверку. Не запускайте несколько контейнеров с одной session и SQLite одновременно.

## 5. Тест SearXNG

Запустить поисковик во внутренней сети Compose:

```bash
docker compose --profile web-search up -d searxng
docker compose run --rm discovery discover \
  --web \
  --no-telegram \
  --no-validate \
  --limit-per-query 5
```

Критерии успешности:

- сервис `searxng` остаётся `Up`;
- команда discovery завершается кодом `0`;
- в `candidate_sources.provider` появляются записи `searxng`;
- SearXNG не имеет опубликованного порта на хосте.

После теста остановить профиль:

```bash
docker compose --profile web-search down
```

## 6. Негативные сценарии

Проверить хотя бы следующие случаи перед релизом:

| Сценарий | Ожидаемое поведение |
|---|---|
| Несуществующий `--input` | Код завершения `1`, запуск в БД получает `failed`. |
| Некорректные строки в TXT/CSV | Неподдерживаемые ссылки пропускаются, валидные продолжают обрабатываться. |
| `--web` без доступного SearXNG | Код завершения `1`, ошибка не повреждает уже сохранённые данные. |
| Telegram-сущность удалена/недоступна | Кандидат получает диагностический статус, весь запуск не должен терять другие результаты. |
| Повторный одинаковый импорт | Нет дублей кандидатов и provenance. |
| Повторный экспорт | Файлы пересобираются из SQLite без обращения к Telegram. |

Повторный экспорт проверяется командой:

```bash
docker compose run --rm discovery export
```

## 7. Приёмочный чек-лист

Перед передачей версии:

- [ ] `docker compose --profile test build test` завершается успешно;
- [ ] `docker compose config --quiet` не сообщает ошибок;
- [ ] офлайн end-to-end создаёт три непустых файла;
- [ ] повторный импорт не создаёт дубли;
- [ ] в Compose нет опубликованных портов;
- [ ] `.env`, SQLite, session и exports игнорируются Git;
- [ ] живой Telegram smoke-тест пройден локально, если доступны учётные данные;
- [ ] вручную просмотрены несколько строк CSV и соответствующие причины `kyiv_reasons`;
- [ ] в `git status --short` нет случайных session-файлов, баз или экспортов.

## Диагностика

Показать последние логи контейнера:

```bash
docker compose logs --tail=200 discovery
docker compose logs --tail=200 searxng
```

Посмотреть журнал запусков без вывода чувствительных данных:

```bash
docker compose run --rm --entrypoint python discovery -c \
  "import sqlite3; db=sqlite3.connect('/app/data/discovery.sqlite3'); print(db.execute('select id, started_at, finished_at, status, query_count, candidate_count, error from discovery_runs order by id desc limit 10').fetchall())"
```

Если тест изменил только содержимое `data/`, исходный код и Git не затронуты. Session-файл нельзя удалять при обычной очистке тестовых экспортов.

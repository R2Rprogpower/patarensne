# Полное руководство пользователя

Это руководство позволяет запустить приложение без знания Python, Telegram API
или устройства проекта. Все команды выполняются из корневой папки проекта.

## 1. Что делает приложение

Приложение ищет публичные Telegram-группы и каналы по фразам, например
`чаты Львов`, проверяет открытые метаданные, удаляет повторы и создаёт таблицы.

Оно может собрать:

- название, ссылку и описание;
- тип: группа или канал;
- количество участников, если Telegram его показывает;
- открытый вход или вход по заявке;
- активность за выбранное число дней;
- число сообщений и уникальных авторов за период;
- признаки captcha/verification в публичном названии или описании;
- запросы и источники, по которым результат был найден.

Приложение **не вступает** в группы, **не отправляет** сообщения, не читает
личные чаты, не сохраняет тексты сообщений и не обходит ограничения Telegram.

## 2. Что понадобится

1. Компьютер с Docker Engine и Docker Compose v2.
2. Отдельный Telegram user account. Бот-токен не подходит.
3. Telegram `api_id` и `api_hash`, созданные владельцем аккаунта на
   <https://my.telegram.org/apps>.
4. Доступ к номеру, коду входа и 2FA этого аккаунта при первой авторизации.

Используйте отдельный аккаунт, номер и recovery-настройки которого контролирует
оператор приложения или заказчик. Переданная третьей стороной сессия может быть
отозвана и не подходит для хранения личных данных.

## 3. Что нельзя передавать другим

Следующие файлы и значения являются секретами:

- `.env`;
- `data/telegram.session` и соседние session-файлы;
- Telegram `api_hash`;
- код входа и пароль 2FA;
- архив `tdata` от Telegram Desktop;
- база `data/discovery.sqlite3`, если её содержимое нельзя раскрывать.

Session-файл фактически даёт доступ к аккаунту. Его нельзя отправлять в чат,
добавлять в Git или класть в release-архив.

## 4. Первый запуск с нуля

Если заказчику передали защищённый ZIP с готовой Telethon-сессией, используйте
отдельную инструкцию [по миграции сессии](session-migration.md). Импортируйте
только данные, необходимые приложению.

### 4.1. Открыть папку проекта

```bash
cd /путь/к/telegram-group-activity-scanner
```

### 4.2. Создать локальные настройки и каталоги

```bash
cp .env.example .env
mkdir -p data/imports data/exports
chmod 700 data
```

Открыть `.env` локальным редактором и заполнить только:

```dotenv
TELEGRAM_API_ID=числовой_api_id
TELEGRAM_API_HASH=api_hash
```

Не вставляйте секреты в командную строку, скриншоты или сообщения.

### 4.3. Собрать приложение

```bash
docker compose build discovery
```

Пересобирать образ нужно после получения новой версии кода:

```bash
docker compose build discovery
```

### 4.4. Один раз авторизовать Telegram

```bash
docker compose run --rm discovery auth
```

Программа скрыто запросит номер, код входа и, если включена, 2FA. После успеха
в `data/` появится локальная сессия. При следующих запусках код обычно не нужен.

Проверка повторной авторизацией безопасна:

```bash
docker compose run --rm discovery auth
```

Если вывод содержит `Telegram session is already authorized`, всё готово.

## 5. Самый простой поиск

Один запрос:

```bash
docker compose run --rm discovery discover \
  --query "чаты Львов" \
  --output-name lviv-chats
```

Несколько вариантов одного запроса дают более полную выдачу:

```bash
docker compose run --rm discovery discover \
  --query "чаты Львов" \
  --query "Львов чат" \
  --query "чати Львів" \
  --query "Львів чат" \
  --limit-per-query 30 \
  --output-name lviv-chats
```

Готовые файлы появятся в `data/exports/`:

- `lviv-chats.csv` — основная таблица для Excel/Google Sheets;
- `lviv-chats.json` — данные для другой программы;
- `lviv-chats.txt` — простой список ссылок на группы.

CSV использует разделитель `;` и кодировку UTF-8 с BOM, поэтому обычно
корректно открывается в Excel двойным щелчком.

> Не запускайте просто `discover`, если ищете не Киев: без явного запроса
> приложение использует исторический файл `config/queries-kyiv.txt`.

## 6. Поиск с метриками активности

Пример: проверить публичную историю за 7 дней, считать чат активным от 10
сообщений и читать не больше 500 сообщений из одного чата:

```bash
docker compose run --rm discovery discover \
  --query "чаты Львов" \
  --query "Львів чат" \
  --activity-days 7 \
  --active-min-messages 10 \
  --activity-max-messages 500 \
  --output-name lviv-chats
```

Значения активности:

- `active` — сообщений не меньше `--active-min-messages`;
- `low_activity` — сообщения есть, но их меньше порога;
- `inactive` — за период не найдено сообщений;
- `unavailable` — историю нельзя прочитать без дополнительного доступа;
- `unknown` — сканирование активности не выполнялось.

Если `activity_unavailable_reason` содержит
`message limit reached; counts are lower bounds`, число сообщений и авторов —
**нижняя граница**. Например, `500` означает «не меньше 500», а не ровно 500.

Подсчёт уникальных авторов применим прежде всего к группам. В канале сообщения
могут публиковаться от имени самого канала, поэтому этот показатель не равен
числу реальных редакторов.

## 7. Полный и отфильтрованный список за один запуск

Фильтры не удаляют исходные данные. При наличии хотя бы одного фильтра команда
создаёт две группы файлов:

- `<имя>.csv/json/txt` — полный результат;
- `<имя>-filtered.csv/json/txt` — только строки, прошедшие фильтры.

Пример: оставить группы от 100 участников, активные за 7 дней, с 10 сообщениями
и 3 авторами:

```bash
docker compose run --rm discovery discover \
  --query "чаты Львов" \
  --query "Львів чат" \
  --activity-days 7 \
  --active-min-messages 10 \
  --activity-max-messages 500 \
  --entity-type group \
  --activity-status active \
  --min-members 100 \
  --min-messages 10 \
  --min-unique-authors 3 \
  --output-name lviv-chats
```

Доступные фильтры:

```text
--min-members N
--min-messages N
--min-unique-authors N
--max-days-since-last-message N
--entity-type group|channel|unknown
--activity-status active|low_activity|inactive|unknown|unavailable
--captcha-status yes|no|unknown
```

Флаги `--entity-type`, `--activity-status` и `--captcha-status` можно повторять,
чтобы разрешить несколько значений.

### Важное ограничение captcha

- `yes` — в публичном названии/описании найден явный признак проверки;
- `unknown` — определить без вступления нельзя;
- `no` предусмотрен форматом, но отсутствие слова `captcha` не доказывает
  отсутствие проверки, поэтому безопасный сканер обычно его не выставляет.

Не используйте `--captcha-status no`, ожидая полный список «без капчи»: без
вступления Telegram не позволяет это доказать.

## 8. Перефильтровать уже собранную базу

Повторно обращаться к Telegram не обязательно. Команда `export` читает текущую
SQLite-базу и создаёт новые файлы:

```bash
docker compose run --rm discovery export \
  --activity-status active \
  --min-members 500 \
  --output-name active-500-plus
```

Это удобно, когда заказчик меняет критерии после завершения сбора.

## 9. Большой список запросов из файла

Создать файл `data/imports/queries.txt`, по одному запросу на строку:

```text
чаты Львов
Львов чат
чати Львів
Львів чат
```

Запуск:

```bash
docker compose run --rm discovery discover \
  --query-file /app/data/imports/queries.txt \
  --activity-days 7 \
  --output-name lviv-chats
```

Пустые строки и строки, начинающиеся с `#`, игнорируются. Повторы запросов
автоматически удаляются.

## 10. Импорт готовых ссылок TXT/CSV

Положить файл в `data/imports/`, затем выполнить:

```bash
docker compose run --rm discovery discover \
  --input /app/data/imports/seeds.csv \
  --output-name imported-chats
```

`--input` можно повторять. Найденные через файлы и Telegram ссылки приводятся к
единому виду и дедуплицируются по Telegram ID, username и нормализованной ссылке.

Только привести файл к единому формату, без Telegram и без проверки ссылок:

```bash
docker compose run --rm discovery discover \
  --no-telegram \
  --no-validate \
  --input /app/data/imports/seeds.csv \
  --output-name normalized
```

## 11. Дополнительный веб-поиск

Опциональный SearXNG помогает находить Telegram-ссылки на открытых веб-страницах.
Он не заменяет поиск Telegram и не гарантирует полный каталог.

```bash
docker compose --profile web-search up -d searxng
docker compose run --rm discovery discover \
  --query "чаты Львов" \
  --web \
  --output-name lviv-web-and-telegram
```

Остановить SearXNG:

```bash
docker compose --profile web-search down
```

Не используйте сторонние каталоги, требующие обхода CAPTCHA, авторизации или
запрета автоматического доступа.

## 12. Как читать CSV

Основные колонки:

| Колонка | Значение |
|---|---|
| `url` | Нормализованная ссылка `https://t.me/...` |
| `title`, `description` | Публичное название и описание |
| `entity_type` | `group`, `channel` или `unknown` |
| `access_status` | Доступность объекта |
| `members_count` | Участники/подписчики, если Telegram сообщил число |
| `captcha_status` | `yes`, `no` или `unknown` |
| `captcha_evidence` | Публичное основание для отметки |
| `activity_status` | Итоговая категория активности |
| `activity_period_days` | Период, за который считалась активность |
| `messages_count` | Сообщения за период |
| `unique_authors` | Уникальные доступные `sender_id` за период |
| `messages_per_day` | Среднее число сообщений в день |
| `last_message_at` | Дата последнего доступного сообщения, UTC |
| `days_since_last_message` | Сколько дней прошло до момента сканирования |
| `activity_unavailable_reason` | Причина недоступности или отметка нижней границы |
| `sources` | Источники: Telegram, файл, SearXNG |
| `source_queries` | Запросы, по которым найдена ссылка |
| `checked_at` | Время проверки метаданных, UTC |

`access_status`:

- `open` — публичная группа;
- `approval_required` — для вступления требуется заявка;
- `channel` — публичный канал;
- `private` — приватная ссылка/объект;
- `unavailable` — удалён или недоступен;
- `unverified` — найден, но не проверен через Telegram.

Пустая ячейка означает, что Telegram не предоставил значение. Это не ноль.

## 13. Как получать воспроизводимые результаты

Для каждого отдельного задания используйте:

- новую базу или сохранённую копию старой базы;
- явные `--query`/`--query-file`;
- уникальное `--output-name`;
- записанные дату, период и лимит сообщений;
- один экземпляр приложения на одну Telegram-сессию.

Повторные запуски обновляют существующие записи в общей базе и не создают
дубликаты. Экспорты отражают всё актуальное содержимое базы, а не только новые
результаты одного запроса. Для полностью изолированного заказа временно укажите
другой `DATABASE_PATH` прямо для контейнера и отдельный каталог вывода:

```bash
mkdir -p data/jobs/lviv/exports
docker compose run --rm \
  -e DATABASE_PATH=/app/data/jobs/lviv/discovery.sqlite3 \
  discovery discover \
  --query "чаты Львов" \
  --query "Львів чат" \
  --activity-days 7 \
  --output-dir /app/data/jobs/lviv/exports \
  --output-name lviv-chats
```

Такой запуск не смешивает новый отчёт с основной `data/discovery.sqlite3`.
Названия каталога и файла должны быть простыми и понятными, без секретов.

## 14. Диагностика

### `Telegram session is not authorized`

```bash
docker compose run --rm discovery auth
```

Если сессия отозвана владельцем аккаунта, потребуется новая локальная
авторизация.

### `TELEGRAM_API_ID and TELEGRAM_API_HASH are required`

Проверить, что `.env` существует и оба поля заполнены без кавычек и пробелов.

### Команда не знает новый флаг

Локальный Docker-образ устарел:

```bash
docker compose build --no-cache discovery
```

### FloodWait

Не запускайте несколько сборов одновременно. Уменьшите число запросов и
`--limit-per-query`, подождите указанное Telegram время. Приложение повторяет
поиск после FloodWait, поэтому большой запуск может долго не выводить результат.

### Долго считает активность

Это ожидаемо: история проверяется последовательно и с задержкой. Уменьшите
`--activity-days`, `--activity-max-messages` или число результатов.

### В CSV есть старые города/темы

База общая для повторных запусков. Для нового независимого отчёта используйте
пример с отдельным `DATABASE_PATH` из раздела 13 или сначала безопасно сохраните
старую базу. Не удаляйте базу, если она нужна заказчику.

### Метрики равны лимиту

Если одновременно присутствует сообщение про `lower bounds`, реальное значение
выше или равно лимиту. Увеличьте `--activity-max-messages` и повторите запуск,
учитывая дополнительную нагрузку на Telegram.

### Нет результатов

Попробуйте несколько формулировок на разных языках, проверьте авторизацию и
запустите с небольшим `--limit-per-query 5`. Telegram возвращает только свою
поисковую выдачу; приложение не может найти абсолютно все существующие чаты.

## 15. Проверка перед передачей результата

1. Открыть CSV и проверить несколько ссылок вручную.
2. Убедиться, что запросы присутствуют в `source_queries`.
3. Проверить период активности и отметки нижней границы.
4. Не выдавать `captcha_status=unknown` за отсутствие captcha.
5. Передать только необходимые CSV/JSON/TXT.
6. Не передавать `.env`, session-файл, `tdata`, 2FA и коды входа.
7. Если передаётся код — собрать чистый архив или использовать Git.

## 16. Готовые рецепты

### Быстрый список без активности

```bash
docker compose run --rm discovery discover \
  --query "чаты Одесса" \
  --query "чати Одеса" \
  --limit-per-query 30 \
  --output-name odesa-chats
```

### Активные группы за неделю

```bash
docker compose run --rm discovery discover \
  --query "чаты Одесса" \
  --query "чати Одеса" \
  --activity-days 7 \
  --active-min-messages 10 \
  --activity-max-messages 500 \
  --entity-type group \
  --activity-status active \
  --output-name odesa-chats
```

### Только группы от 1000 участников

```bash
docker compose run --rm discovery export \
  --entity-type group \
  --min-members 1000 \
  --output-name groups-1000-plus
```

## 17. Получить встроенную справку

```bash
docker compose run --rm discovery --help
docker compose run --rm discovery discover --help
docker compose run --rm discovery export --help
```

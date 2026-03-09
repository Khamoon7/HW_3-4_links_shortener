# URL Shortener API

Сервис сокращения URL-ссылок на FastAPI с PostgreSQL, Redis-кэшированием и JWT-аутентификацией.

## Стек технологий

| Компонент | Технология |
|---|---|
| Web-фреймворк | FastAPI + Uvicorn/Gunicorn |
| База данных | PostgreSQL + SQLAlchemy (async) |
| Миграции | Alembic |
| Кэш | Redis + fastapi-cache2 |
| Аутентификация | fastapi-users (JWT Bearer) |
| Контейнеризация | Docker + docker-compose |

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone <repo_url>
cd <repo_directory>
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
# Отредактировать .env — задать DB_PASS, SECRET и BASE_URL
```

### 3. Запустить через Docker Compose

```bash
docker compose up --build
```

Приложение будет доступно на `http://localhost:8000`.
Swagger UI: `http://localhost:8000/docs`

### 4. Локальный запуск (без Docker)

```bash
pip install -r requirements.txt

# Запустить PostgreSQL и Redis локально, затем:
alembic upgrade head
cd src
uvicorn main:app --reload
```

---

## Структура проекта

```
Проект №3/
├── .env                    # Переменные окружения (секреты, хосты)
├── .env.example            # Шаблон для .env
├── alembic.ini             # Конфиг Alembic (миграции)
├── docker-compose.yml      # 3 сервиса: db, redis, app
├── Dockerfile              # Образ Python 3.11-slim
├── requirements.txt        # Зависимости pip
├── pyproject.toml          # Конфиг pytest
├── README.md               # Документация
│
├── docker/
│   └── app.sh              # Запуск: alembic upgrade + gunicorn
│
├── migrations/
│   ├── env.py              # Конфиг Alembic (подставляет .env в URL)
│   ├── script.py.mako      # Шаблон новых миграций
│   └── versions/
│       └── 0001_initial_schema.py  # Создаёт таблицы: user, links, link_history
│
└── src/
    ├── main.py             # Точка входа: FastAPI app, CORS, роутеры, lifespan
    ├── config.py           # Загрузка переменных из .env
    ├── database.py         # async engine, session_maker, get_async_session()
    ├── models.py           # Базовый класс Base для всех ORM моделей
    │
    ├── auth/
    │   ├── db.py           # ORM модель User (fastapi-users)
    │   ├── schemas.py      # Pydantic: UserCreate, UserRead
    │   └── users.py        # UserManager, JWT стратегия, current_user_optional
    │
    └── links/
        ├── models.py       # ORM: Link (активные), LinkHistory (деактивированные)
        ├── schemas.py      # Pydantic схемы для всех запросов и ответов API
        ├── service.py      # Вся бизнес-логика: CRUD, поиск, статистика, очистка
        └── router.py       # FastAPI роутер: 12 эндпоинтов, кэширование
```

| Файл | Ответственность |
|---|---|
| `src/main.py` | Запуск приложения, lifespan, CORS, подключение роутеров, фоновая задача очистки (каждые 30 мин) |
| `src/config.py` | Читает `.env` и экспортирует переменные (DB, Redis, SECRET, BASE_URL) |
| `src/database.py` | Async подключение к PostgreSQL, фабрика сессий, dependency `get_async_session` |
| `src/models.py` | Базовый класс `Base` — от него наследуют все ORM модели |
| `src/auth/db.py` | ORM модель `User` (UUID PK, email, hashed_password и т.д.) |
| `src/auth/schemas.py` | Pydantic схемы для регистрации и чтения пользователя |
| `src/auth/users.py` | `UserManager`, JWT backend, `current_active_user`, `current_user_optional` |
| `src/links/models.py` | ORM таблицы `links` и `link_history` со всеми полями |
| `src/links/schemas.py` | Pydantic схемы для всех запросов и ответов API |
| `src/links/service.py` | Вся бизнес-логика: создание, редирект, статистика, поиск, архивирование, очистка |
| `src/links/router.py` | 12 API эндпоинтов, кэш через `@cache`, инвалидация при POST/PUT/DELETE/cleanup |
| `migrations/versions/0001_initial_schema.py` | Создаёт таблицы `user`, `links`, `link_history` в PostgreSQL |
| `docker-compose.yml` | Поднимает PostgreSQL 16, Redis 7, приложение с healthcheck-ами |

---

## Описание базы данных

### Таблица `links` — активные ссылки

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Первичный ключ |
| `short_code` | VARCHAR(20) | Уникальный короткий код |
| `original_url` | TEXT | Оригинальный URL |
| `user_id` | UUID (FK) | Владелец (NULL = анонимный) |
| `created_at` | TIMESTAMPTZ | Дата создания |
| `expires_at` | TIMESTAMPTZ | Срок истечения (NULL = бессрочная) |
| `last_used_at` | TIMESTAMPTZ | Дата последнего перехода |
| `click_count` | INTEGER | Счётчик переходов |
| `is_active` | BOOLEAN | Активна ли ссылка |
| `project` | VARCHAR(100) | Группа/проект |

### Таблица `link_history` — история деактивированных ссылок

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Первичный ключ |
| `short_code` | VARCHAR(20) | Бывший короткий код |
| `original_url` | TEXT | Оригинальный URL |
| `user_id` | UUID | Бывший владелец |
| `created_at` | TIMESTAMPTZ | Дата создания ссылки |
| `deactivated_at` | TIMESTAMPTZ | Дата деактивации |
| `reason` | VARCHAR(20) | Причина: `expired` / `deleted` / `unused` |
| `click_count` | INTEGER | Итоговое число переходов |
| `project` | VARCHAR(100) | Проект |

---

## API: описание эндпоинтов

### Аутентификация

| Метод | Путь | Описание |
|---|---|---|
| POST | `/auth/register` | Регистрация нового пользователя |
| POST | `/auth/jwt/login` | Вход (получить JWT-токен) |
| POST | `/auth/jwt/logout` | Выход |

**Пример регистрации:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'
```

**Пример логина:**
```bash
curl -X POST http://localhost:8000/auth/jwt/login \
  -d 'username=user@example.com&password=secret123'
# Ответ: {"access_token": "...", "token_type": "bearer"}
```

---

### Ссылки

#### Обязательные функции

**1. Создать короткую ссылку**
```
POST /links/shorten
```
Доступно всем. Поддерживает кастомный alias, срок жизни, проект.

```bash
# Анонимно
curl -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/very/long/url"}'

# С токеном + кастомный alias + срок жизни
curl -X POST http://localhost:8000/links/shorten \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "original_url": "https://example.com/article",
    "custom_alias": "my-article",
    "expires_at": "2026-12-31T23:59:00Z",
    "project": "blog"
  }'
```

**2. Перейти по короткой ссылке**
```
GET /links/{short_code}
```
Доступно всем. Редирект 307 на оригинальный URL. Кэш не применяется — каждый переход обновляет счётчик.

```bash
curl -L http://localhost:8000/links/my-article
```

**3. Удалить ссылку**
```
DELETE /links/{short_code}
```
Только владелец. Требует JWT-токен.

```bash
curl -X DELETE http://localhost:8000/links/my-article \
  -H "Authorization: Bearer <token>"
```

**4. Обновить ссылку**
```
PUT /links/{short_code}
```
Только владелец. Можно изменить original_url, expires_at, project.

```bash
curl -X PUT http://localhost:8000/links/my-article \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/new-url"}'
```

**5. Статистика по ссылке**
```
GET /links/{short_code}/stats
```
Доступно всем. Кэш 30 сек.

```bash
curl http://localhost:8000/links/my-article/stats
# Ответ:
# {
#   "short_code": "my-article",
#   "original_url": "https://example.com/article",
#   "created_at": "2026-03-04T10:00:00Z",
#   "expires_at": "2026-12-31T23:59:00Z",
#   "click_count": 42,
#   "last_used_at": "2026-03-04T15:30:00Z",
#   "project": "blog",
#   "is_active": true
# }
```

**6. Поиск ссылок по оригинальному URL**
```
GET /links/search?original_url={url}
```
Поиск по подстроке URL. Кэш 30 сек.

```bash
curl "http://localhost:8000/links/search?original_url=example.com"
```

---

#### Дополнительные функции

**7. История деактивированных ссылок**
```
GET /links/history/expired
```
Доступно всем. Показывает истёкшие, удалённые и неиспользуемые ссылки.

```bash
curl "http://localhost:8000/links/history/expired?limit=20"
```

**8. Удаление неиспользуемых ссылок**
```
DELETE /links/cleanup?days=N
```
Требует авторизации. Удаляет только свои ссылки, не использованные N дней.

```bash
curl -X DELETE "http://localhost:8000/links/cleanup?days=30" \
  -H "Authorization: Bearer <token>"
# Ответ: {"deleted_count": 5, "days": 30}
```

**9. Мои ссылки (с пагинацией)**
```
GET /links/?project=blog&skip=0&limit=20
```
Требует авторизации. Список ссылок пользователя с фильтром по проекту.

```bash
curl "http://localhost:8000/links/?project=blog" \
  -H "Authorization: Bearer <token>"
```

**10. Топ ссылок по переходам**
```
GET /links/top?limit=10
```
Публичный. Рейтинг самых кликабельных ссылок. Кэш 60 сек.

```bash
curl "http://localhost:8000/links/top?limit=5"
```

**11. QR-код ссылки**
```
GET /links/{short_code}/qr
```
Доступно всем. Возвращает PNG-изображение QR-кода для короткой ссылки.

```bash
curl "http://localhost:8000/links/my-article/qr" -o qr.png
```

**12. Статистика по проекту**
```
GET /links/projects/{project}/stats
```
Требует авторизации. Агрегированная статистика по всем ссылкам проекта.

```bash
curl "http://localhost:8000/links/projects/blog/stats" \
  -H "Authorization: Bearer <token>"
# Ответ:
# {
#   "project": "blog",
#   "total_links": 12,
#   "total_clicks": 384,
#   "avg_clicks": 32.0,
#   "top_link": "my-article",
#   "top_link_clicks": 42
# }
```

---

## Кэширование

| Эндпоинт | TTL | Инвалидация |
|---|---|---|
| `GET /links/{short_code}` | — | Не кэшируется (каждый переход обновляет статистику) |
| `GET /links/{short_code}/stats` | 30 сек | При PUT/DELETE/cleanup/shorten |
| `GET /links/search` | 30 сек | При PUT/DELETE/cleanup/shorten |
| `GET /links/top` | 60 сек | При PUT/DELETE/cleanup/shorten |

---

## Инструкция по запуску

```bash
# 1. Скопировать и настроить окружение
cp .env.example .env

# 2. Собрать и запустить контейнеры
docker compose up --build -d

# 3. Проверить логи
docker compose logs -f app

# 4. Открыть документацию в браузере
# Windows: start http://localhost:8000/docs
# Linux:   xdg-open http://localhost:8000/docs
# macOS:   open http://localhost:8000/docs

# 5. Остановить
docker compose down
```

### Переменные окружения (.env)

```dotenv
DB_USER=postgres
DB_PASS=your_password
DB_HOST=db
DB_PORT=5432
DB_NAME=url_shortener

REDIS_HOST=redis
REDIS_PORT=6379

SECRET=your_jwt_secret_key
BASE_URL=http://localhost:8000
```

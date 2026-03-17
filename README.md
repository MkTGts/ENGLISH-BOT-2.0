# English Bot 2.0 — Telegram AI bot for English practice

Бот для практики английского “как с живым собеседником”: отвечает по‑английски и отдельно показывает исправления ошибок. Проект построен на `aiogram 3.x`, хранит историю в SQLite и интегрируется с **OpenAI‑compatible** API (Timeweb Agent / OpenAI / др.).

## Что уже реализовано

- **Чат**: пользователь пишет сообщение → бот отвечает по‑английски.
- **Исправления ошибок**: LLM возвращает JSON по контракту `reply_text / corrections[] / follow_up_question`.
- **История**: `MessageHistory` хранится в SQLite.
- **Приватность**:
  - `/privacy` показывает политику хранения
  - кнопка “Очистить историю” удаляет историю пользователя
  - фоновая TTL‑очистка удаляет записи старше `HISTORY_TTL_DAYS`
- **Лимиты (business‑style)**:
  - лимитируются **именно запросы к AI** (LLM‑requests/day), а не любые сообщения
  - токены учитываются из ответа провайдера (`usage`) или оценочно (если `usage` нет)
  - задел под подписку: модели `Subscription`/`Usage`, планы `free/pro`
- **Антиспам**: простое in‑memory ограничение по сообщениям в минуту.
- **Наблюдаемость**:
  - логи с корреляцией `user_id/chat_id`
  - логируется `llm_ok latency_ms=...`
- **Статистика**: фоновой задачей пишется текстовый файл `stats.txt` (users/messages/errors).

## Быстрый старт

### 1) Установка зависимостей

Создай виртуальное окружение и установи зависимости.

Windows PowerShell:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/VPS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Настройка окружения (.env)

Скопируй `.env.example` → `.env` и заполни минимум:

- `BOT_TOKEN`: токен Telegram‑бота
- `AI_AGENT_ID`: `agent_access_id` из панели Timeweb AI‑агента
- `AI_API_KEY`: API‑токен (передаётся как `Authorization: Bearer ...`)
- `AI_MODEL`: модель

Остальное можно оставить дефолтным.

### 3) Запуск

Запуск из корня проекта:

```bash
python3 main.py
```

На Windows также можно:

```bash
python main.py
```

## Команды бота

- **`/start`** — приветствие и краткая инструкция.
- **`/help`** — подсказка по использованию.
- **`/settings`** — заготовка под настройки.
- **`/privacy`** — политика хранения + кнопка очистки истории.
- **`/admin ...`** — админские команды (доступ только для `ADMIN_IDS`).

Также все основные действия доступны через **кнопки меню** (Reply-клавиатура): `Chat`, `Help`, `Privacy`, `Settings`, а у админа дополнительно `Admin`.

## Переменные окружения

Смотри `.env.example`. Ключевые:

- **`DB_PATH`**: путь к SQLite базе (`./ai_eng_bot/data/database.db`)
- **`STATS_PATH`**: куда писать `stats.txt`
- **`HISTORY_TTL_DAYS`**: TTL истории (дни)
- **`LLM_CONTEXT_MESSAGES`**: максимум сообщений истории, которые отправляем в модель (дополнительно ограничивается планом)
- **`LLM_REQUEST_TIMEOUT_S`**: таймаут запроса к LLM
- **`LLM_MAX_RETRIES`**: число ретраев (backoff)
- **`LLM_JSON_MODE`**: пытаться включить `response_format={"type":"json_object"}` (если провайдер не поддерживает — выключи)
- **`RATE_LIMIT_WINDOW_S`**, **`RATE_LIMIT_MAX_MESSAGES`**: антиспам для входящих сообщений
- **`ADMIN_IDS`**: Telegram user IDs админов (через запятую)

## Архитектура / где что лежит

- `main.py` — точка входа (соответствует запуску `python3 main.py`)
- `ai_eng_bot/src/main.py` — инициализация бота, БД, middleware, роутеров, фоновых задач
- `ai_eng_bot/src/config.py` — настройки из `.env`
- `ai_eng_bot/src/handlers/commands.py` — `/start`, `/help`, `/settings`, `/privacy`
- `ai_eng_bot/src/handlers/admin.py` — админка (`/admin ...`)
- `ai_eng_bot/src/handlers/chat.py` — основной чат + typing + лимиты LLM + логирование latency
- `ai_eng_bot/src/services/ai_engine.py` — интеграция с LLM (OpenAI‑compatible)
- `ai_eng_bot/src/database/models.py` — модели SQLAlchemy (`User`, `MessageHistory`, `ErrorLog`, `Subscription`, `Usage`)
- `ai_eng_bot/src/database/repository.py` — CRUD + TTL cleanup + usage/subscription helpers
- `ai_eng_bot/data/` — данные (`database.db`, `stats.txt`)

## Примечания и типовые проблемы

- **Если видишь предупреждение про `AI_API_KEY is not set`** — бот запустится, но ответы LLM будут падать, пока не настроишь ключ.
- **SQLite при росте**: при большой нагрузке лучше мигрировать на Postgres, архитектура к этому готова (слои `repository/services/handlers`).



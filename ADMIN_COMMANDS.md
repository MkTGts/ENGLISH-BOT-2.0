## Admin Commands

Этот файл описывает админ-команды бота и что именно они делают.

### Доступ

- Все команды ниже доступны **только** пользователям, чьи Telegram ID перечислены в `.env` в переменной `ADMIN_IDS`.
- В проекте проверка реализована фильтром `IsAdmin` (см. `ai_eng_bot/src/filters/admin.py`).

### Где живёт логика

- **Команды**: `ai_eng_bot/src/handlers/admin.py`
- **Операции с БД**: `ai_eng_bot/src/database/repository.py`
- **Планы/лимиты**: `ai_eng_bot/src/services/access.py`
- **Хранение админского промпта**: `ai_eng_bot/src/services/prompt_store.py` (`ai_eng_bot/data/system_prompt.txt`)

---

## Команды

### `/admin`

**Назначение**: legacy-справка и поддержка старого формата `/admin sub grant ...`.

**Что делает**:
- Если вызвать без аргументов (`/admin`) — выводит справку админ-команд.
- Если вызвать в legacy-формате (`/admin status`, `/admin sub grant ...`) — выполнит действие.

Рекомендуемый формат — отдельные команды `/admin_*` ниже.

---

### `/admin_status`

**Назначение**: показать конфигурацию/состояние бота.

**Выводит** (примерно):
- `AI_AGENT_ID`, `AI_MODEL`
- `HISTORY_TTL_DAYS`, `LLM_CONTEXT_MESSAGES`, `LLM_JSON_MODE`
- параметры rate limit
- список `ADMIN_IDS`

**Где реализовано**: `admin_status()` в `ai_eng_bot/src/handlers/admin.py`.

---

### `/admin_stats`

**Назначение**: агрегированная статистика по БД.

**Выводит**:
- кол-во пользователей
- кол-во сообщений
- кол-во записей об ошибках

**Где реализовано**: `admin_stats()` в `ai_eng_bot/src/handlers/admin.py`, использует `Repository.count_*`.

---

### `/admin_user [id|@username]`

**Назначение**: “карточка” конкретного пользователя.

**Аргументы**:
- `id` — Telegram user id
- `@username` — username (если известен и сохранён)

**Выводит**:
- id, username, `active`
- текущий план (`free/pro/...`)
- usage за сегодня (`llm_requests`, `tokens`)
- даты `created_at/updated_at`

**Где реализовано**: `admin_user()` в `ai_eng_bot/src/handlers/admin.py`.

---

### `/admin_users_list [limit] [offset]`

**Назначение**: выгрузка списка пользователей с метриками в **CSV-файл**.

**Зачем CSV**: Telegram ограничивает длину сообщений, а список может быть большим.

**Аргументы**:
- `limit` (по умолчанию 200, максимум 2000)
- `offset` (по умолчанию 0)

**Формат CSV (колонки)**:
- `@username`
- `tg_id`
- `registered_at`
- `plan`
- `total_messages`
- `total_tokens`
- `month_messages`
- `month_tokens`
- `week_messages`
- `week_tokens`
- `day_messages`
- `day_tokens`

**Как считаются метрики**:
- `messages`: кол-во записей в `MessageHistory` с `role="user"`
- `tokens`: сумма `tokens_in + tokens_out` по `MessageHistory` с `role="assistant"`
- период “день/неделя/месяц” считается относительно текущего UTC времени (последние 1/7/30 дней).

**Где реализовано**:
- `admin_users_list_cmd()` в `ai_eng_bot/src/handlers/admin.py`
- `Repository.users_usage_report()` в `ai_eng_bot/src/database/repository.py`

---

### `/admin_ban [id]` и `/admin_unban [id]`

**Назначение**: заблокировать/разблокировать пользователя.

**Что меняет в БД**:
- выставляет `User.is_active = false/true`

**Эффект**:
- в чате (`ai_eng_bot/src/handlers/chat.py`) заблокированный пользователь получает сообщение “Доступ ограничен…”

**Где реализовано**: `admin_ban()` + `Repository.set_user_active()`.

---

### `/admin_sub_grant [id] [free|pro] [days]`

**Назначение**: вручную выдать пользователю план/подписку.

**Аргументы**:
- `id`: Telegram user id
- `plan`: `free` или `pro` (можно расширять)
- `days` (опционально): если задано — выставляется `expires_at = now + days`

**Что меняет в БД**:
- добавляет новую запись `Subscription` со статусом `active`, `provider="admin"`

**Где реализовано**:
- команда вызывает `admin_sub(... "grant ...")`
- запись создаётся в `Repository.set_user_plan()`

---

### `/admin_sub_revoke [id]`

**Назначение**: отменить активные подписки пользователя.

**Что меняет в БД**:
- для всех `Subscription(status="active")` проставляет `status="canceled"` и `expires_at=now`

**Где реализовано**: `Repository.revoke_user_plan()`.

---

### `/admin_sub_expiring [days]`

**Назначение**: показать подписки, которые истекают в ближайшие `days` дней.

**Где реализовано**: `Repository.expiring_subscriptions()`.

---

### `/admin_cleanup`

**Назначение**: принудительная TTL-очистка истории.

**Что делает**:
- удаляет `MessageHistory` старше `HISTORY_TTL_DAYS`
- удаляет связанные `ErrorLog`

**Где реализовано**: `Repository.ttl_cleanup()`.

---

### `/admin_broadcast [text]`

**Назначение**: рассылка сообщения всем активным пользователям.

**Что делает**:
- берёт список `User.id` где `is_active=true`
- пытается отправить сообщение каждому
- возвращает итог `ok/fail`

**Ограничения/риски**:
- Telegram может ограничивать частоту (flood control)
- при большой базе лучше делать рассылку батчами/очередью

**Где реализовано**: `admin_broadcast()` + `Repository.list_active_user_ids()`.

---

### `/admin_prompt_show`

**Назначение**: показать текущий системный промпт.

**Что делает**:
- если `ai_eng_bot/data/system_prompt.txt` существует — показывает его
- иначе сообщает, что используется дефолтный промпт

**Где реализовано**: `load_prompt()` в `ai_eng_bot/src/services/prompt_store.py`.

---

### `/admin_prompt_set [text]`

**Назначение**: установить системный промпт (перезапишет файл).

**Что делает**:
- сохраняет текст в `ai_eng_bot/data/system_prompt.txt`
- после этого `system_prompt_ru()` будет возвращать сохранённый промпт вместо дефолтного

**Где реализовано**: `save_prompt()` в `ai_eng_bot/src/services/prompt_store.py`.


from __future__ import annotations

import logging
from datetime import datetime

from aiogram.filters import Command
from aiogram.types import Message
from aiogram import Router

from ai_eng_bot.src.config import settings
from ai_eng_bot.src.database.repository import Repository
from ai_eng_bot.src.filters.admin import IsAdmin
from ai_eng_bot.src.handlers.menu import main_menu
from ai_eng_bot.src.services.prompt_store import load_prompt, save_prompt

router = Router()
router.message.filter(IsAdmin())

logger = logging.getLogger(__name__)


def _help_text() -> str:
    return (
        "Admin commands:\n"
        "/admin status — конфиг/состояние\n"
        "/admin stats — агрегированная статистика\n"
        "/admin user [id|@username] — карточка пользователя\n"
        "/admin ban [id] — заблокировать\n"
        "/admin unban [id] — разблокировать\n"
        "/admin sub grant [id] [free|pro] [days] — выдать план\n"
        "/admin sub revoke [id] — отменить активные подписки\n"
        "/admin sub expiring [days] — истекающие подписки\n"
        "/admin cleanup — принудительная TTL-очистка\n"
        "/admin broadcast [text] — рассылка активным\n"
        "/admin prompt show — показать текущий prompt\n"
        "/admin prompt set [text] — установить prompt\n"
    )


def _args(message: Message) -> str:
    if not message.text:
        return ""
    parts = message.text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


@router.message(Command("admin"))
async def admin_dispatch(message: Message, db_session):
    text = _args(message).strip()
    if not text or text in ("help", "-h", "--help"):
        return await message.answer(_help_text())

    cmd, *rest = text.split(maxsplit=1)
    tail = rest[0] if rest else ""

    if cmd == "status":
        return await admin_status(message)
    if cmd == "stats":
        return await admin_stats(message, db_session)
    if cmd == "user":
        return await admin_user(message, db_session, tail)
    if cmd == "ban":
        return await admin_ban(message, db_session, tail, True)
    if cmd == "unban":
        return await admin_ban(message, db_session, tail, False)
    if cmd == "cleanup":
        return await admin_cleanup(message, db_session)
    if cmd == "broadcast":
        return await admin_broadcast(message, db_session, tail)
    if cmd == "prompt":
        return await admin_prompt(message, tail)
    if cmd == "sub":
        return await admin_sub(message, db_session, tail)

    await message.answer("Неизвестная admin-команда.\n\n" + _help_text(), reply_markup=main_menu(is_admin=True))


async def admin_status(message: Message):
    admins = sorted(settings.admin_id_set())
    await message.answer(
        "Status:\n"
        f"- AI_AGENT_ID: {settings.ai_agent_id}\n"
        f"- AI_MODEL: {settings.ai_model}\n"
        f"- HISTORY_TTL_DAYS: {settings.history_ttl_days}\n"
        f"- LLM_CONTEXT_MESSAGES: {settings.llm_context_messages}\n"
        f"- LLM_JSON_MODE: {settings.llm_json_mode}\n"
        f"- RATE_LIMIT: {settings.rate_limit_max_messages}/{settings.rate_limit_window_s}s\n"
        f"- ADMIN_IDS: {admins}\n"
        ,
        reply_markup=main_menu(is_admin=True),
    )


async def admin_stats(message: Message, db_session):
    repo = Repository(db_session)
    users = await repo.count_users()
    msgs = await repo.count_messages()
    errs = await repo.count_errors()
    await message.answer(
        "Stats:\n"
        f"- users: {users}\n"
        f"- messages: {msgs}\n"
        f"- errors: {errs}\n"
        f"- updated: {datetime.utcnow().isoformat()}Z\n"
        ,
        reply_markup=main_menu(is_admin=True),
    )


async def admin_user(message: Message, db_session, tail: str):
    repo = Repository(db_session)
    q = tail.strip()
    if not q:
        return await message.answer("Usage: /admin user [id|@username]", reply_markup=main_menu(is_admin=True))

    user = None
    if q.startswith("@"):
        user = await repo.find_user_by_username(username=q)
    else:
        try:
            user = await repo.get_user(user_id=int(q))
        except ValueError:
            user = None

    if user is None:
        return await message.answer("Пользователь не найден.", reply_markup=main_menu(is_admin=True))

    plan = await repo.get_active_plan(user_id=int(user.id))
    usage = await repo.get_or_create_daily_usage(user_id=int(user.id))

    await message.answer(
        "User card:\n"
        f"- id: {user.id}\n"
        f"- username: @{user.username}\n"
        f"- active: {user.is_active}\n"
        f"- plan: {plan}\n"
        f"- usage_today: llm_requests={usage.messages_used}, tokens={usage.tokens_used}\n"
        f"- created_at: {user.created_at}\n"
        f"- updated_at: {user.updated_at}\n"
        ,
        reply_markup=main_menu(is_admin=True),
    )


async def admin_ban(message: Message, db_session, tail: str, ban: bool):
    q = tail.strip()
    if not q:
        return await message.answer("Usage: /admin ban [id]  |  /admin unban [id]", reply_markup=main_menu(is_admin=True))
    try:
        user_id = int(q)
    except ValueError:
        return await message.answer("ID должен быть числом.", reply_markup=main_menu(is_admin=True))

    repo = Repository(db_session)
    ok = await repo.set_user_active(user_id=user_id, is_active=(not ban))
    logger.info(
        "admin_action %s target=%s",
        "ban" if ban else "unban",
        user_id,
        extra={"user_id": int(message.from_user.id) if message.from_user else "-", "chat_id": int(message.chat.id)},
    )
    if not ok:
        return await message.answer("Пользователь не найден.", reply_markup=main_menu(is_admin=True))
    await message.answer("Готово.", reply_markup=main_menu(is_admin=True))


async def admin_cleanup(message: Message, db_session):
    repo = Repository(db_session)
    deleted = await repo.ttl_cleanup(ttl_days=settings.history_ttl_days)
    logger.info(
        "admin_action cleanup deleted=%s",
        deleted,
        extra={"user_id": int(message.from_user.id) if message.from_user else "-", "chat_id": int(message.chat.id)},
    )
    await message.answer(f"Cleanup done. Deleted messages: {deleted}", reply_markup=main_menu(is_admin=True))


async def admin_broadcast(message: Message, db_session, tail: str):
    text = tail.strip()
    if not text:
        return await message.answer("Usage: /admin broadcast [text]", reply_markup=main_menu(is_admin=True))

    repo = Repository(db_session)
    user_ids = await repo.list_active_user_ids(limit=10000)

    ok = 0
    fail = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(chat_id=uid, text=text)
            ok += 1
        except Exception:  # noqa: BLE001
            fail += 1

    logger.info(
        "admin_action broadcast ok=%s fail=%s",
        ok,
        fail,
        extra={"user_id": int(message.from_user.id) if message.from_user else "-", "chat_id": int(message.chat.id)},
    )
    await message.answer(f"Broadcast finished. ok={ok}, fail={fail}", reply_markup=main_menu(is_admin=True))


async def admin_prompt(message: Message, tail: str):
    sub = tail.strip()
    if not sub or sub == "show":
        current = load_prompt()
        if not current:
            return await message.answer("Prompt не задан (используется дефолтный).", reply_markup=main_menu(is_admin=True))
        return await message.answer("Current prompt:\n\n" + current, reply_markup=main_menu(is_admin=True))

    if sub.startswith("set "):
        new_text = sub[len("set ") :].strip()
        if not new_text:
            return await message.answer("Usage: /admin prompt set [text]", reply_markup=main_menu(is_admin=True))
        save_prompt(new_text)
        logger.info(
            "admin_action prompt_set",
            extra={"user_id": int(message.from_user.id) if message.from_user else "-", "chat_id": int(message.chat.id)},
        )
        return await message.answer("Prompt сохранён.", reply_markup=main_menu(is_admin=True))

    await message.answer("Usage:\n/admin prompt show\n/admin prompt set <text>", reply_markup=main_menu(is_admin=True))


async def admin_sub(message: Message, db_session, tail: str):
    repo = Repository(db_session)
    parts = tail.split()
    if not parts:
        return await message.answer("Usage: /admin sub grant|revoke|expiring ...", reply_markup=main_menu(is_admin=True))

    action = parts[0]
    if action == "grant":
        if len(parts) < 3:
            return await message.answer("Usage: /admin sub grant [id] [free|pro] [days]", reply_markup=main_menu(is_admin=True))
        try:
            user_id = int(parts[1])
        except ValueError:
            return await message.answer("ID должен быть числом.", reply_markup=main_menu(is_admin=True))
        plan = parts[2]
        days = None
        if len(parts) >= 4:
            try:
                days = int(parts[3])
            except ValueError:
                return await message.answer("days должен быть числом.", reply_markup=main_menu(is_admin=True))
        await repo.set_user_plan(user_id=user_id, plan=plan, days=days)
        logger.info(
            "admin_action sub_grant target=%s plan=%s days=%s",
            user_id,
            plan,
            days,
            extra={"user_id": int(message.from_user.id) if message.from_user else "-", "chat_id": int(message.chat.id)},
        )
        return await message.answer("Подписка выдана.", reply_markup=main_menu(is_admin=True))

    if action == "revoke":
        if len(parts) < 2:
            return await message.answer("Usage: /admin sub revoke [id]", reply_markup=main_menu(is_admin=True))
        try:
            user_id = int(parts[1])
        except ValueError:
            return await message.answer("ID должен быть числом.", reply_markup=main_menu(is_admin=True))
        n = await repo.revoke_user_plan(user_id=user_id)
        logger.info(
            "admin_action sub_revoke target=%s rows=%s",
            user_id,
            n,
            extra={"user_id": int(message.from_user.id) if message.from_user else "-", "chat_id": int(message.chat.id)},
        )
        return await message.answer(f"Отменено подписок: {n}", reply_markup=main_menu(is_admin=True))

    if action == "expiring":
        if len(parts) < 2:
            return await message.answer("Usage: /admin sub expiring [days]", reply_markup=main_menu(is_admin=True))
        try:
            days = int(parts[1])
        except ValueError:
            return await message.answer("days должен быть числом.", reply_markup=main_menu(is_admin=True))
        subs = await repo.expiring_subscriptions(within_days=days)
        if not subs:
            return await message.answer("Нет истекающих подписок.", reply_markup=main_menu(is_admin=True))
        lines = ["Expiring subscriptions:"]
        for s in subs:
            lines.append(f"- user_id={s.user_id} plan={s.plan} expires_at={s.expires_at}")
        return await message.answer("\n".join(lines), reply_markup=main_menu(is_admin=True))

    await message.answer("Usage: /admin sub grant|revoke|expiring ...", reply_markup=main_menu(is_admin=True))


@router.message(lambda m: (m.text or "").strip().lower() == "admin")
async def menu_admin(message: Message):
    return await message.answer(_help_text(), reply_markup=main_menu(is_admin=True))


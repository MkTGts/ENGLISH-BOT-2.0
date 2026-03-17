from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from ai_eng_bot.src.config import settings
from ai_eng_bot.src.database.repository import Repository
from ai_eng_bot.src.services.ai_engine import AiEngine, LlmError
from ai_eng_bot.src.services.access import DEFAULT_PLANS
from ai_eng_bot.src.services.prompt_manager import system_prompt_ru

router = Router()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def typing_indicator(message: Message):
    stop = asyncio.Event()

    async def _loop():
        # Keep sending typing while request is running
        while not stop.is_set():
            try:
                await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
            except Exception:  # noqa: BLE001
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(Exception):
            await task


def _format_reply(reply_text: str, corrections: list[dict], follow_up_question: str | None) -> str:
    parts: list[str] = [reply_text.strip()]
    if corrections:
        lines = ["", "Corrections:"]
        for c in corrections:
            raw = c.get("raw", "").strip()
            corrected = c.get("corrected", "").strip()
            explanation = c.get("explanation", "").strip()
            ctype = c.get("type", "").strip()
            lines.append(f"- ({ctype}) {raw} → {corrected}")
            if explanation:
                lines.append(f"  - {explanation}")
        parts.append("\n".join(lines).strip())
    if follow_up_question:
        parts.append(f"\n{follow_up_question.strip()}")
    return "\n\n".join([p for p in parts if p])


@router.message(F.text)
async def chat_handler(message: Message, db_session, ai_engine: AiEngine):
    if message.from_user is None or message.text is None:
        return

    repo = Repository(db_session)
    user_id = int(message.from_user.id)
    chat_id = int(message.chat.id)

    log_extra = {"user_id": user_id, "chat_id": chat_id}

    user = await repo.get_user(user_id=user_id)
    if user is not None and not user.is_active:
        logger.info("user_blocked", extra=log_extra)
        try:
            return await message.answer("Доступ к боту ограничен. Если это ошибка — напишите в поддержку.")
        except Exception:  # noqa: BLE001
            logger.exception("failed_to_send_blocked_message", extra=log_extra)
            return

    # Determine plan & limits (subscription-ready)
    plan = await repo.get_active_plan(user_id=user_id)
    limits = DEFAULT_PLANS.get(plan, DEFAULT_PLANS["free"])

    usage = await repo.get_or_create_daily_usage(user_id=user_id)
    if usage.messages_used >= limits.max_messages_per_day:
        logger.info(
            "limit_exceeded llm_requests_per_day plan=%s used=%s",
            plan,
            usage.messages_used,
            extra=log_extra,
        )
        try:
            return await message.answer(
                "Лимит запросов к AI на сегодня исчерпан. Попробуй завтра или оформи подписку (план Pro)."
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed_to_send_limit_message", extra=log_extra)
            return
    if usage.tokens_used >= limits.max_tokens_per_day:
        logger.info("limit_exceeded tokens_per_day plan=%s used=%s", plan, usage.tokens_used, extra=log_extra)
        try:
            return await message.answer(
                "Лимит токенов на сегодня исчерпан. Попробуй завтра или оформи подписку (план Pro)."
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed_to_send_limit_message", extra=log_extra)
            return

    # Store user message
    user_msg = await repo.add_message(
        user_id=user_id,
        chat_id=chat_id,
        telegram_message_id=message.message_id,
        role="user",
        content=message.text,
    )

    ctx_limit = min(settings.llm_context_messages, limits.max_context_messages)
    history = await repo.recent_messages(user_id=user_id, limit=ctx_limit)
    llm_messages = [{"role": m.role, "content": m.content} for m in history]

    async with typing_indicator(message):
        try:
            result = await ai_engine.chat_json(system_prompt=system_prompt_ru(), messages=llm_messages)
        except LlmError as e:
            logger.exception("LLM error: %s", e, extra=log_extra)
            try:
                return await message.answer("Похоже, сейчас AI недоступен. Попробуй чуть позже.")
            except Exception:  # noqa: BLE001
                logger.exception("failed_to_send_llm_error_message", extra=log_extra)
                return
        except Exception as e:  # noqa: BLE001
            logger.exception("Unexpected error: %s", e, extra=log_extra)
            try:
                return await message.answer("Произошла ошибка. Попробуй ещё раз.")
            except Exception:  # noqa: BLE001
                logger.exception("failed_to_send_generic_error_message", extra=log_extra)
                return

    logger.info("llm_ok latency_ms=%s plan=%s", result.latency_ms, plan, extra=log_extra)

    # Persist assistant message (+ usage/latency in metadata)
    meta = {"latency_ms": result.latency_ms, "model": settings.ai_model}
    await repo.add_message(
        user_id=user_id,
        chat_id=chat_id,
        telegram_message_id=None,
        role="assistant",
        content=result.parsed.reply_text,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        metadata=meta,
    )

    used_tokens = int(result.tokens_in or 0) + int(result.tokens_out or 0)
    # Business usage accounting:
    # - increment LLM request count only for successful model calls
    # - increment tokens based on provider usage or estimation from AiEngine
    await repo.increment_daily_usage(usage_id=usage.id, add_messages=1, add_tokens=used_tokens)

    # Persist corrections to ErrorLog (link to user's message)
    for c in result.parsed.corrections:
        try:
            await repo.add_error(
                message_id=user_msg.id,
                raw_error=c.raw,
                correction=c.corrected,
                error_type=c.type,
                rule_hint=c.explanation,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to store corrections", extra=log_extra)

    # Render message
    text = _format_reply(
        result.parsed.reply_text,
        [c.model_dump() for c in result.parsed.corrections],
        result.parsed.follow_up_question,
    )
    try:
        await message.answer(text)
    except Exception:  # noqa: BLE001
        logger.exception("failed_to_send_reply", extra=log_extra)


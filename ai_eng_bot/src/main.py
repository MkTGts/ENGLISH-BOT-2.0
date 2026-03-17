from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, Update

from ai_eng_bot.src.config import settings
from ai_eng_bot.src.database.db import create_engine, create_sessionmaker
from ai_eng_bot.src.database.models import Base
from ai_eng_bot.src.database.repository import Repository
from ai_eng_bot.src.handlers import admin, chat, commands
from ai_eng_bot.src.middlewares.db_session import DbSessionMiddleware
from ai_eng_bot.src.middlewares.rate_limit import RateLimitMiddleware
from ai_eng_bot.src.middlewares.user_register import UserRegisterMiddleware
from ai_eng_bot.src.services.ai_engine import AiEngine


def _setup_logging() -> None:
    class SafeCorrelationFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:  # noqa: A003
            if not hasattr(record, "user_id"):
                record.user_id = "-"
            if not hasattr(record, "chat_id"):
                record.chat_id = "-"
            return super().format(record)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        SafeCorrelationFormatter("%(asctime)s %(levelname)s %(name)s | user=%(user_id)s chat=%(chat_id)s | %(message)s")
    )

    root.handlers.clear()
    root.addHandler(handler)


async def _init_db(db_path: str) -> tuple:
    engine = create_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_sessionmaker(engine)
    return engine, session_factory


async def _write_stats(stats_path: str, repo: Repository) -> None:
    users = await repo.count_users()
    messages = await repo.count_messages()
    errors = await repo.count_errors()
    content = (
        f"Generated at: {datetime.utcnow().isoformat()}Z\n"
        f"Users: {users}\n"
        f"Messages: {messages}\n"
        f"Errors: {errors}\n"
    )
    Path(stats_path).write_text(content, encoding="utf-8")


async def _background_tasks(session_factory, stop_event: asyncio.Event) -> None:
    # Periodically: TTL cleanup + stats file update
    while not stop_event.is_set():
        async with session_factory() as session:
            repo = Repository(session)
            try:
                await repo.ttl_cleanup(ttl_days=settings.history_ttl_days)
                await _write_stats(settings.stats_path, repo)
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).exception("Background task failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            continue


async def main_async() -> None:
    settings.ensure_paths()
    _setup_logging()

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Create .env from .env.example")
    if not settings.ai_agent_id:
        raise RuntimeError("AI_AGENT_ID is not set. Create .env from .env.example")
    if not settings.ai_api_key:
        logging.getLogger(__name__).warning("AI_API_KEY is not set. LLM replies will fail until configured.")

    engine, session_factory = await _init_db(settings.db_path)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Dependencies for handlers (centralized in services)
    ai_engine = AiEngine(
        agent_id=settings.ai_agent_id,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_s=settings.llm_request_timeout_s,
        max_retries=settings.llm_max_retries,
        json_mode=settings.llm_json_mode,
    )
    dp["ai_engine"] = ai_engine

    # Middlewares
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.update.middleware(UserRegisterMiddleware())
    dp.update.middleware(
        RateLimitMiddleware(window_s=settings.rate_limit_window_s, max_messages=settings.rate_limit_max_messages)
    )

    # Routers
    dp.include_router(admin.router)
    dp.include_router(commands.router)
    dp.include_router(chat.router)

    @dp.errors()
    async def on_error(event: ErrorEvent):  # type: ignore[override]
        logging.getLogger(__name__).exception("Unhandled aiogram error: %r", event.exception)
        return True

    @dp.update()
    async def catch_all_update(update: Update):  # type: ignore[override]
        # If we ever see "Update is not handled", this ensures we log the raw update type.
        logging.getLogger(__name__).info("update_catch_all type=%s", type(update).__name__)
        return

    stop_event = asyncio.Event()
    bg_task = asyncio.create_task(_background_tasks(session_factory, stop_event))

    try:
        await dp.start_polling(bot, ai_engine=ai_engine)
    finally:
        stop_event.set()
        bg_task.cancel()
        with contextlib.suppress(Exception):
            await bg_task
        await bot.session.close()
        await engine.dispose()


def run() -> None:
    asyncio.run(main_async())


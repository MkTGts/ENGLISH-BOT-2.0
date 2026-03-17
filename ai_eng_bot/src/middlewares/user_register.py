from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ai_eng_bot.src.database.repository import Repository


class UserRegisterMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):  # type: ignore[override]
        session = data.get("db_session")
        user = data.get("event_from_user")
        if session is not None and user is not None:
            repo = Repository(session)
            await repo.upsert_user(user_id=int(user.id), username=user.username, language_ui="ru")
            await repo.ensure_free_subscription(user_id=int(user.id))
        return await handler(event, data)


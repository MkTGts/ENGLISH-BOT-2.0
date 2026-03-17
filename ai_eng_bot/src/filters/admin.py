from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message

from ai_eng_bot.src.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:  # type: ignore[override]
        if message.from_user is None:
            return False
        admins = settings.admin_id_set()
        return int(message.from_user.id) in admins


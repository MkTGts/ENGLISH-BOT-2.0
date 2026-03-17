from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, *, window_s: int, max_messages: int):
        super().__init__()
        self.window_s = window_s
        self.max_messages = max_messages
        self._events: defaultdict[int, deque[float]] = defaultdict(deque)
        self._logger = logging.getLogger(__name__)

    async def __call__(self, handler, event: TelegramObject, data: dict):  # type: ignore[override]
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        now = time.time()
        q = self._events[int(user.id)]
        cutoff = now - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.max_messages:
            message = data.get("event_update").message if data.get("event_update") else None
            chat_id = getattr(getattr(message, "chat", None), "id", None) if message else None
            self._logger.info(
                "rate_limit_blocked window_s=%s max_messages=%s",
                self.window_s,
                self.max_messages,
                extra={"user_id": int(user.id), "chat_id": int(chat_id) if chat_id is not None else "-"},
            )
            if message:
                await message.answer("Слишком много сообщений. Подожди немного и попробуй снова.")
            return

        q.append(now)
        return await handler(event, data)


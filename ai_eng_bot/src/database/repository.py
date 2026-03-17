from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_eng_bot.src.database.models import ErrorLog, MessageHistory, Subscription, Usage, User


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_user(
        self,
        *,
        user_id: int,
        username: str | None,
        language_ui: str = "ru",
    ) -> User:
        existing = await self.session.get(User, user_id)
        if existing is None:
            user = User(id=user_id, username=username, language_ui=language_ui)
            self.session.add(user)
            await self.session.commit()
            return user

        changed = False
        if username != existing.username:
            existing.username = username
            changed = True
        if language_ui != existing.language_ui:
            existing.language_ui = language_ui
            changed = True
        if changed:
            await self.session.commit()
        return existing

    async def ensure_free_subscription(self, *, user_id: int) -> None:
        q = select(Subscription.id).where(Subscription.user_id == user_id).limit(1)
        res = await self.session.execute(q)
        if res.scalar_one_or_none() is not None:
            return
        sub = Subscription(user_id=user_id, plan="free", status="active", auto_renew=False)
        self.session.add(sub)
        await self.session.commit()

    async def get_user(self, *, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def find_user_by_username(self, *, username: str) -> User | None:
        q = select(User).where(User.username == username.lstrip("@")).limit(1)
        res = await self.session.execute(q)
        return res.scalars().first()

    async def set_user_active(self, *, user_id: int, is_active: bool) -> bool:
        res = await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=is_active, updated_at=datetime.utcnow())
        )
        await self.session.commit()
        return bool(res.rowcount)

    async def set_user_plan(self, *, user_id: int, plan: str, days: int | None = None) -> None:
        now = datetime.utcnow()
        expires_at = None
        if days is not None:
            expires_at = now + timedelta(days=days)
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status="active",
            started_at=now,
            expires_at=expires_at,
            auto_renew=False,
            provider="admin",
            provider_payment_id=None,
        )
        self.session.add(sub)
        await self.session.commit()

    async def revoke_user_plan(self, *, user_id: int) -> int:
        now = datetime.utcnow()
        res = await self.session.execute(
            update(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status == "active")
            .values(status="canceled", expires_at=now, updated_at=now)
        )
        await self.session.commit()
        return int(res.rowcount or 0)

    async def expiring_subscriptions(self, *, within_days: int) -> list[Subscription]:
        now = datetime.utcnow()
        cutoff = now + timedelta(days=within_days)
        q = (
            select(Subscription)
            .where(
                Subscription.status == "active",
                Subscription.expires_at.is_not(None),
                Subscription.expires_at <= cutoff,
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.asc())
            .limit(100)
        )
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def get_active_plan(self, *, user_id: int, now: datetime | None = None) -> str:
        now = now or datetime.utcnow()
        q = (
            select(Subscription.plan)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            )
            .order_by(Subscription.id.desc())
            .limit(1)
        )
        res = await self.session.execute(q)
        plan = res.scalar_one_or_none()
        return plan or "free"

    async def get_or_create_daily_usage(self, *, user_id: int, now: datetime | None = None) -> Usage:
        now = now or datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        q = (
            select(Usage)
            .where(
                Usage.user_id == user_id,
                Usage.period_start == day_start,
                Usage.period_end == day_end,
            )
            .limit(1)
        )
        res = await self.session.execute(q)
        existing = res.scalars().first()
        if existing is not None:
            return existing

        usage = Usage(user_id=user_id, period_start=day_start, period_end=day_end, messages_used=0, tokens_used=0)
        self.session.add(usage)
        await self.session.commit()
        await self.session.refresh(usage)
        return usage

    async def increment_daily_usage(
        self,
        *,
        usage_id: int,
        add_messages: int = 0,
        add_tokens: int = 0,
    ) -> None:
        await self.session.execute(
            update(Usage)
            .where(Usage.id == usage_id)
            .values(
                messages_used=Usage.messages_used + add_messages,
                tokens_used=Usage.tokens_used + add_tokens,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.commit()

    async def add_message(
        self,
        *,
        user_id: int,
        chat_id: int,
        telegram_message_id: int | None,
        role: str,
        content: str,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        metadata: dict | None = None,
        timestamp: datetime | None = None,
    ) -> MessageHistory:
        msg = MessageHistory(
            user_id=user_id,
            chat_id=chat_id,
            telegram_message_id=telegram_message_id,
            role=role,
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
            timestamp=timestamp or datetime.utcnow(),
        )
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def recent_messages(self, *, user_id: int, limit: int) -> list[MessageHistory]:
        q = (
            select(MessageHistory)
            .where(MessageHistory.user_id == user_id)
            .order_by(MessageHistory.id.desc())
            .limit(limit)
        )
        res = await self.session.execute(q)
        return list(res.scalars().all())[::-1]

    async def add_error(
        self,
        *,
        message_id: int,
        raw_error: str,
        correction: str,
        error_type: str = "grammar",
        rule_hint: str | None = None,
    ) -> ErrorLog:
        e = ErrorLog(
            message_id=message_id,
            raw_error=raw_error,
            correction=correction,
            error_type=error_type,
            rule_hint=rule_hint,
        )
        self.session.add(e)
        await self.session.commit()
        await self.session.refresh(e)
        return e

    async def delete_user_history(self, *, user_id: int) -> int:
        # delete errors first (FK)
        subq = select(MessageHistory.id).where(MessageHistory.user_id == user_id).subquery()
        await self.session.execute(delete(ErrorLog).where(ErrorLog.message_id.in_(select(subq.c.id))))
        res = await self.session.execute(delete(MessageHistory).where(MessageHistory.user_id == user_id))
        await self.session.commit()
        return int(res.rowcount or 0)

    async def ttl_cleanup(self, *, ttl_days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)
        subq = select(MessageHistory.id).where(MessageHistory.timestamp < cutoff).subquery()
        await self.session.execute(delete(ErrorLog).where(ErrorLog.message_id.in_(select(subq.c.id))))
        res = await self.session.execute(delete(MessageHistory).where(MessageHistory.timestamp < cutoff))
        await self.session.commit()
        return int(res.rowcount or 0)

    async def count_users(self) -> int:
        res = await self.session.execute(select(func.count()).select_from(User))
        return int(res.scalar_one())

    async def count_messages(self) -> int:
        res = await self.session.execute(select(func.count()).select_from(MessageHistory))
        return int(res.scalar_one())

    async def count_errors(self) -> int:
        res = await self.session.execute(select(func.count()).select_from(ErrorLog))
        return int(res.scalar_one())

    async def list_active_user_ids(self, *, limit: int = 10000) -> list[int]:
        q = select(User.id).where(User.is_active == True).limit(limit)  # noqa: E712
        res = await self.session.execute(q)
        return [int(x) for x in res.scalars().all()]


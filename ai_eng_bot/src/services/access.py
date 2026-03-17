from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    max_messages_per_window: int
    window_s: int
    max_context_messages: int
    max_messages_per_day: int
    max_tokens_per_day: int


DEFAULT_PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        max_messages_per_window=20,
        window_s=60,
        max_context_messages=8,
        max_messages_per_day=200,
        max_tokens_per_day=50_000,
    ),
    "pro": PlanLimits(
        max_messages_per_window=60,
        window_s=60,
        max_context_messages=15,
        max_messages_per_day=2_000,
        max_tokens_per_day=500_000,
    ),
}


def can_chat(*, plan: str) -> bool:
    return plan in DEFAULT_PLANS


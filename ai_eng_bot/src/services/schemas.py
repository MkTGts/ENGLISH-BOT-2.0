from __future__ import annotations

from pydantic import BaseModel, Field


class Correction(BaseModel):
    raw: str
    corrected: str
    explanation: str
    type: str = Field(default="grammar", description="grammar|lexis|style")


class LlmResponse(BaseModel):
    reply_text: str
    corrections: list[Correction] = Field(default_factory=list)
    follow_up_question: str | None = None


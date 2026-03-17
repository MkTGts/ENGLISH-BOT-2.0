from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx
import asyncio

from ai_eng_bot.src.services.schemas import LlmResponse


class LlmError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    # Fallback: try to find the first JSON object in the text
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise LlmError("Model did not return JSON")
    return m.group(0)

def _estimate_tokens(text: str) -> int:
    """
    Lightweight token estimate (provider-agnostic).
    Typical English is ~4 chars/token; Cyrillic tends to be slightly denser.
    """
    s = (text or "").strip()
    if not s:
        return 0
    avg = 3.2 if re.search(r"[А-Яа-яЁё]", s) else 4.0
    return max(1, int(len(s) / avg))


def _estimate_prompt_tokens(system_prompt: str, messages: list[dict]) -> int:
    parts = [system_prompt] + [str(m.get("content", "")) for m in messages]
    return sum(_estimate_tokens(p) for p in parts)


@dataclass
class LlmResult:
    parsed: LlmResponse
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    raw_text: str | None = None


class AiEngine:
    def __init__(
        self,
        *,
        agent_id: str,
        api_key: str,
        model: str,
        timeout_s: int,
        max_retries: int,
        json_mode: bool = True,
    ):
        self.agent_id = agent_id
        self.base_url = f"https://agent.timeweb.cloud/api/v1/cloud-ai/agents/{agent_id}/v1".rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.json_mode = json_mode

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(self.timeout_s),
        )

    async def chat_json(
        self,
        *,
        system_prompt: str,
        messages: list[dict],
    ) -> LlmResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "temperature": 0.7,
        }
        # Some providers may not support response_format. Keep it optional.
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(1, max(1, self.max_retries) + 1):
            t0 = time.perf_counter()
            try:
                async with self._client() as client:
                    resp = await client.post("/chat/completions", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                latency_ms = int((time.perf_counter() - t0) * 1000)
            except httpx.HTTPStatusError as e:
                last_err = e
                status = e.response.status_code
                # Retry for transient issues
                if status in (408, 409, 425, 429, 500, 502, 503, 504) and attempt < self.max_retries:
                    await asyncio.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
                    continue
                raise
            except httpx.HTTPError as e:
                last_err = e
                if attempt < self.max_retries:
                    await asyncio.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
                    continue
                raise

            try:
                content = data["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001
                raise LlmError(f"Unexpected LLM response shape: {e}") from e

            raw_text = str(content)
            try:
                json_str = _extract_json(raw_text)
                parsed_obj = json.loads(json_str)
                parsed = LlmResponse.model_validate(parsed_obj)
            except Exception as e:  # noqa: BLE001
                # If json_mode is off or provider ignored it, allow retries on invalid JSON
                last_err = e
                if attempt < self.max_retries:
                    await asyncio.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
                    continue
                raise LlmError(f"Invalid JSON from model: {e}") from e

            usage = data.get("usage") or {}
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
            if not isinstance(tokens_in, int):
                tokens_in = _estimate_prompt_tokens(system_prompt, messages)
            if not isinstance(tokens_out, int):
                tokens_out = _estimate_tokens(parsed.reply_text) + sum(
                    _estimate_tokens(c.explanation) + _estimate_tokens(c.corrected) for c in parsed.corrections
                )

            return LlmResult(
                parsed=parsed,
                latency_ms=latency_ms,
                tokens_in=tokens_in if isinstance(tokens_in, int) else None,
                tokens_out=tokens_out if isinstance(tokens_out, int) else None,
                raw_text=raw_text,
            )

        raise LlmError(f"LLM call failed after retries: {last_err}")


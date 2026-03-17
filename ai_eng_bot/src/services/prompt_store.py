from __future__ import annotations

from pathlib import Path


def prompt_path() -> Path:
    return Path("./ai_eng_bot/data/system_prompt.txt")


def load_prompt() -> str | None:
    p = prompt_path()
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return text or None


def save_prompt(text: str) -> None:
    p = prompt_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")


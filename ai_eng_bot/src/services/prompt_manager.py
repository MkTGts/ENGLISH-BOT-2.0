from __future__ import annotations

from ai_eng_bot.src.services.prompt_store import load_prompt


def system_prompt_ru() -> str:
    stored = load_prompt()
    if stored:
        return stored
    return (
        "Ты — дружелюбный собеседник для практики английского языка. "
        "Пиши основной ответ по-английски, естественно и поддерживая тему. "
        "Ошибки пользователя исправляй отдельно в поле corrections JSON-ответа. "
        "Если ошибок нет — corrections должен быть пустым массивом. "
        "Всегда возвращай валидный JSON строго по контракту."
    )


def system_prompt_en() -> str:
    return (
        "You are a friendly conversation partner to practice English. "
        "Write the main reply in English, naturally and on-topic. "
        "Put corrections in the corrections field of the JSON response. "
        "If there are no mistakes, corrections must be an empty array. "
        "Always return valid JSON strictly following the contract."
    )


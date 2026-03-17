from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""

    # Timeweb AI Agent
    ai_agent_id: str = ""
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"

    db_path: str = "./ai_eng_bot/data/database.db"
    stats_path: str = "./ai_eng_bot/data/stats.txt"

    history_ttl_days: int = 90
    llm_context_messages: int = 10

    llm_request_timeout_s: int = 30
    llm_max_retries: int = 3
    llm_json_mode: bool = True

    rate_limit_window_s: int = 60
    rate_limit_max_messages: int = 20

    # Admin
    admin_ids: str = ""  # comma-separated Telegram user IDs, e.g. "123,456"

    def ensure_paths(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.stats_path).parent.mkdir(parents=True, exist_ok=True)

    def admin_id_set(self) -> set[int]:
        raw = (self.admin_ids or "").strip()
        if not raw:
            return set()
        out: set[int] = set()
        for part in raw.split(","):
            p = part.strip()
            if not p:
                continue
            try:
                out.add(int(p))
            except ValueError:
                continue
        return out


settings = Settings()  # type: ignore[call-arg]


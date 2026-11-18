"""Settings loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at import time (tests)
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int | None
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bot.sqlite3"

    @property
    def receipts_dir(self) -> Path:
        return self.data_dir / "receipts"


def _token_from_file() -> str:
    """Fallback for non-technical setup: put the token alone in a file named token.txt."""
    f = Path("token.txt")
    if f.exists():
        value = f.read_text(encoding="utf-8").strip().splitlines()
        value = value[0].strip() if value else ""
        if ":" in value and " " not in value:
            return value
    return ""


def load_settings() -> Settings:
    admin_raw = os.getenv("ADMIN_ID", "").strip()
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"
    default_models = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini"}
    model = os.getenv("LLM_MODEL", "").strip() or default_models.get(provider, "")
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip() or _token_from_file(),
        admin_id=int(admin_raw) if admin_raw.isdigit() else None,
        llm_provider=provider,
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=model,
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip() or "https://api.openai.com/v1",
        data_dir=Path(os.getenv("DATA_DIR", "data")),
    )

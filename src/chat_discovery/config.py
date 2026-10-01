from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    session_path: Path
    telegram_api_id: int | None
    telegram_api_hash: str | None
    searxng_url: str | None

    @classmethod
    def from_environment(cls) -> Settings:
        data_dir = Path(os.environ.get("DATA_DIR", "data")).resolve()
        api_id_raw = os.environ.get("TELEGRAM_API_ID", "").strip()
        return cls(
            data_dir=data_dir,
            database_path=Path(os.environ.get("DATABASE_PATH", data_dir / "discovery.sqlite3")),
            session_path=Path(os.environ.get("TELEGRAM_SESSION_PATH", data_dir / "telegram.session")),
            telegram_api_id=int(api_id_raw) if api_id_raw else None,
            telegram_api_hash=os.environ.get("TELEGRAM_API_HASH") or None,
            searxng_url=os.environ.get("SEARXNG_URL") or None,
        )

    def require_telegram(self) -> tuple[int, str]:
        if self.telegram_api_id is None or not self.telegram_api_hash:
            raise RuntimeError("Telegram API configuration is missing from the local environment file.")
        return self.telegram_api_id, self.telegram_api_hash

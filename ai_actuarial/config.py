"""
Centralized configuration management for ai_actuarial.

All configuration values are defined here in one place.
Replace scattered os.getenv() calls throughout the codebase with settings.KEY.

Usage:
    from ai_actuarial.config import settings
    if settings.RATE_LIMIT_ENABLED:
        ...
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

__all__ = [
    "settings",
    "Settings",
]


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            warnings.warn(f"Invalid integer value for {key}: {raw!r}", RuntimeWarning)
    return default


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default) or default


def _env_list(key: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default if default is not None else []
    return [p.strip() for p in raw.split(",") if p.strip()]


class Settings:
    """Centralized settings for the entire application.

    All os.getenv() calls should be replaced with settings.ATTRIBUTE access.
    This class provides type-safe access to all configuration values with
    sensible defaults.
    """

    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------
    DATA_DIR: Path = Path("data")
    DB_PATH: str = "data/index.db"
    DOWNLOAD_DIR: str = "data/files"
    LOG_FILE: Path = Path("data/app.log")

    # -------------------------------------------------------------------------
    # Security / Auth
    # -------------------------------------------------------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "")
    TOKEN_ENCRYPTION_KEY: str = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    REQUIRE_AUTH: bool = _env_bool("REQUIRE_AUTH", False)
    TRUST_PROXY: bool = _env_bool("TRUST_PROXY", False)

    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = _env_bool("RATE_LIMIT_ENABLED", True)
    RATE_LIMIT_PER_MINUTE: int = _env_int("RATE_LIMIT_PER_MINUTE", 60)
    RATE_LIMIT_BURST: int = _env_int("RATE_LIMIT_BURST", 10)

    # -------------------------------------------------------------------------
    # Chat / Quota
    # -------------------------------------------------------------------------
    DEFAULT_CHAT_QUOTA_PER_DAY: int = _env_int("DEFAULT_CHAT_QUOTA_PER_DAY", 100)
    DEFAULT_CHAT_QUOTA_PER_WEEK: int = _env_int("DEFAULT_CHAT_QUOTA_PER_WEEK", 500)
    DEFAULT_CHAT_QUOTA_GUEST_PER_DAY: int = _env_int("DEFAULT_CHAT_QUOTA_GUEST_PER_DAY", 10)
    EXPOSE_ERROR_DETAILS: bool = _env_bool("EXPOSE_ERROR_DETAILS", False)

    # -------------------------------------------------------------------------
    # API Auth Tokens
    # -------------------------------------------------------------------------
    CONFIG_WRITE_AUTH_TOKEN: str = os.getenv("CONFIG_WRITE_AUTH_TOKEN", "")
    LOGS_READ_AUTH_TOKEN: str = os.getenv("LOGS_READ_AUTH_TOKEN", "")
    FILE_DELETION_AUTH_TOKEN: str = os.getenv("FILE_DELETION_AUTH_TOKEN", "")
    ENABLE_FILE_DELETION: bool = _env_bool("ENABLE_FILE_DELETION", False)

    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------
    ENABLE_GLOBAL_LOGS_API: bool = _env_bool("ENABLE_GLOBAL_LOGS_API", False)
    FASTAPI_ALLOW_LEGACY_API_FALLBACK: bool = _env_bool("FASTAPI_ALLOW_LEGACY_API_FALLBACK", False)
    FASTAPI_ENABLE_MIGRATION_INVENTORY: bool = _env_bool("FASTAPI_ENABLE_MIGRATION_INVENTORY", False)

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    CORS_ORIGINS: list[str] = _env_list(
        "FASTAPI_CORS_ORIGINS",
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # -------------------------------------------------------------------------
    # Search Engine API Keys
    # -------------------------------------------------------------------------
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    def is_search_engine_configured(self, engine_id: str) -> bool:
        """Check if a search engine has its API key configured."""
        mapping = {
            "brave": self.BRAVE_API_KEY,
            "google": self.SERPAPI_API_KEY,
            "serper": self.SERPER_API_KEY,
            "tavily": self.TAVILY_API_KEY,
        }
        return bool(mapping.get(engine_id, "").strip())

    @classmethod
    def resolve_db_path(cls, config_data: dict[str, Any] | None = None) -> str:
        """Resolve the database path from config or environment defaults."""
        if config_data:
            db_path = (config_data.get("paths") or {}).get("db", "data/index.db")
            db_path = str(db_path or "data/index.db")
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
            return db_path
        return os.path.abspath(cls.DB_PATH)


# Global singleton instance
settings = Settings()

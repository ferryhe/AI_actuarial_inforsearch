"""Create the authoritative PostgreSQL-backed storage implementation."""

from __future__ import annotations

import os
from typing import Any

from .postgres import DatabaseConfigurationError, resolve_data_root, resolve_database_config
from .storage import Storage


def create_storage_from_config(config: dict[str, Any] | None = None) -> Storage:
    """Return the full Storage implementation using DATABASE_URL only."""
    config = config or {}
    database_cfg = config.get("database")
    if isinstance(database_cfg, dict):
        database_type = str(database_cfg.get("type") or "postgresql").lower()
        if database_type not in {"postgres", "postgresql"}:
            raise DatabaseConfigurationError("PostgreSQL is required for application storage")
    return Storage(resolve_database_config(config), data_root=resolve_data_root(config))


def get_database_config_from_env() -> dict[str, Any]:
    """Return a non-secret PostgreSQL configuration reference for callers."""
    database_url_env = os.getenv("DATABASE_URL_ENV", "DATABASE_URL").strip() or "DATABASE_URL"
    return {"type": "postgresql", "url_env": database_url_env}

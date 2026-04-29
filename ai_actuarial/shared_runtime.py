from __future__ import annotations

import os
from collections import deque
from pathlib import Path
from typing import Any

import yaml


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_int_clamped(
    value: object,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except Exception:
        number = default
    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number


def get_sites_config_path() -> str:
    return os.getenv("CONFIG_PATH", "config/sites.yaml")


def get_categories_config_path() -> str:
    return os.getenv("CATEGORIES_CONFIG_PATH", "config/categories.yaml")


def load_yaml(path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = default.copy() if isinstance(default, dict) else {}
    if not path or not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else fallback


def get_default_catalog_provider() -> str:
    config = load_yaml(get_sites_config_path(), default={})
    ai_cfg = config.get("ai_config") or {}
    if not isinstance(ai_cfg, dict):
        ai_cfg = {}
    catalog_cfg = ai_cfg.get("catalog") or {}
    if not isinstance(catalog_cfg, dict):
        catalog_cfg = {}
    provider = str(catalog_cfg.get("provider") or ai_cfg.get("catalog_provider") or "").strip().lower()
    return provider or "openai"


def task_log_path(task_id: str) -> Path:
    return Path("data/task_logs") / f"{task_id}.log"


def append_task_log(task_id: str, level: str, message: str) -> None:
    path = task_log_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{level}] {message}\n")


def tail_text_file(path: Path, max_lines: int = 400) -> str:
    if max_lines <= 0 or not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = deque(handle, maxlen=max_lines)
    return "".join(lines)


def serialize_backend_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    defaults = config_data.get("defaults") or {}
    paths = config_data.get("paths") or {}
    search = config_data.get("search") or {}
    system_cfg = config_data.get("system") or {}
    file_deletion_enabled = system_cfg.get(
        "file_deletion_enabled",
        os.getenv("ENABLE_FILE_DELETION") == "true",
    )
    return {
        "defaults": {
            "user_agent": defaults.get("user_agent", ""),
            "max_pages": defaults.get("max_pages", 200),
            "max_depth": defaults.get("max_depth", 2),
            "delay_seconds": defaults.get("delay_seconds", 0.5),
            "file_exts": defaults.get("file_exts", []),
            "keywords": defaults.get("keywords", []),
            "exclude_keywords": defaults.get("exclude_keywords", []),
            "exclude_prefixes": defaults.get("exclude_prefixes", []),
            "schedule_interval": defaults.get("schedule_interval", ""),
        },
        "paths": {
            "db": paths.get("db", "data/index.db"),
            "download_dir": paths.get("download_dir", "data/files"),
            "updates_dir": paths.get("updates_dir", "data/updates"),
            "last_run_new": paths.get("last_run_new", "data/last_run_new.json"),
        },
        "search": {
            "enabled": bool(search.get("enabled", True)),
            "max_results": search.get("max_results", 5),
            "delay_seconds": search.get("delay_seconds", 0.5),
            "languages": search.get("languages", ["en"]),
            "country": search.get("country", "us"),
            "exclude_keywords": search.get("exclude_keywords", []),
            "queries": search.get("queries", []),
        },
        "runtime": {
            "config_path": get_sites_config_path(),
            "categories_config_path": get_categories_config_path(),
            "require_auth": env_flag("REQUIRE_AUTH", False),
            "session_secret_key_set": bool(os.getenv("FASTAPI_SESSION_SECRET")),
            "bootstrap_admin_token_set": bool(os.getenv("BOOTSTRAP_ADMIN_TOKEN")),
            "file_deletion_enabled": bool(file_deletion_enabled),
            "file_deletion_auth_required": bool(os.getenv("FILE_DELETION_AUTH_TOKEN")),
            "config_write_auth_required": bool(os.getenv("CONFIG_WRITE_AUTH_TOKEN")),
            "enable_global_logs_api": env_flag("ENABLE_GLOBAL_LOGS_API", False),
            "logs_read_auth_required": bool(os.getenv("LOGS_READ_AUTH_TOKEN")),
            "enable_rate_limiting": env_flag("ENABLE_RATE_LIMITING", False),
            "enable_csrf": env_flag("ENABLE_CSRF", False),
            "enable_security_headers": env_flag("ENABLE_SECURITY_HEADERS", True),
        },
    }

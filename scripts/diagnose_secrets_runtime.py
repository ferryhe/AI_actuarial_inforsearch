#!/usr/bin/env python3
"""Diagnose secret, credential, and routing state without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_actuarial.ai_runtime import (  # noqa: E402
    PROVIDER_STARTUP_ENV_MAP,
    get_ai_routing,
    list_provider_credentials,
)
from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml  # noqa: E402
from ai_actuarial.storage import Storage  # noqa: E402


AUTH_SECRET_KEYS = (
    "FASTAPI_SESSION_SECRET",
    "TOKEN_ENCRYPTION_KEY",
    "BOOTSTRAP_ADMIN_TOKEN",
    "BOOTSTRAP_ADMIN_SUBJECT",
    "CONFIG_WRITE_AUTH_TOKEN",
    "LOGS_READ_AUTH_TOKEN",
    "FILE_DELETION_AUTH_TOKEN",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value:
            try:
                parsed = shlex.split(value, comments=True, posix=True)
                value = parsed[0] if parsed else ""
            except ValueError:
                value = value.strip("'").strip('"')
        values[key] = value
    return values


def _merged_env(dotenv_values: dict[str, str]) -> dict[str, str]:
    merged = dict(dotenv_values)
    for key, value in os.environ.items():
        if value:
            merged[key] = value
    return merged


def _valid_fernet_key(value: str) -> bool:
    if not value:
        return False
    try:
        Fernet(value.encode())
    except Exception:
        return False
    return True


def _resolve_db_path(config: dict[str, Any], raw_path: str | None) -> Path:
    if raw_path:
        return Path(raw_path).expanduser()
    paths = config.get("paths") or {}
    database = config.get("database") or {}
    return Path(str(paths.get("db") or database.get("path") or "data/index.db"))


def _provider_env_status(env_values: dict[str, str]) -> dict[str, Any]:
    configured: list[dict[str, str]] = []
    empty: list[dict[str, str]] = []
    for provider, (key_env, base_env) in sorted(PROVIDER_STARTUP_ENV_MAP.items()):
        row = {"provider_id": provider, "api_key_env": key_env}
        if base_env:
            row["base_url_env"] = base_env
        if env_values.get(key_env):
            configured.append(row)
        else:
            empty.append(row)
    return {
        "configured_count": len(configured),
        "empty_count": len(empty),
        "configured": configured,
        "empty": empty,
    }


def _db_report(db_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str | None]:
    if not db_path.exists():
        return (
            {"path": str(db_path), "exists": False, "credential_count": 0, "usable_count": 0},
            [],
            [],
            "database_not_found",
        )
    storage = Storage(str(db_path))
    try:
        credentials = list_provider_credentials(storage=storage).get("credentials", [])
        routing = get_ai_routing(storage=storage).get("bindings", [])
    except Exception as exc:  # noqa: BLE001
        return (
            {"path": str(db_path), "exists": True, "credential_count": 0, "usable_count": 0},
            [],
            [],
            f"database_report_failed: {type(exc).__name__}",
        )
    finally:
        storage.close()

    safe_credentials = [
        {
            "provider_id": row.get("provider_id"),
            "category": row.get("category"),
            "source": row.get("source"),
            "status": row.get("status"),
            "decrypt_ok": row.get("decrypt_ok"),
            "last_error": row.get("last_error"),
            "stable_credential_id": row.get("stable_credential_id"),
            "is_default": row.get("is_default"),
        }
        for row in credentials
    ]
    safe_routing = [
        {
            "function_name": row.get("function_name"),
            "provider": row.get("provider"),
            "model": row.get("model"),
            "credential_source": row.get("credential_source"),
            "stable_credential_id": row.get("stable_credential_id"),
            "configured": row.get("configured"),
            "credential_error": row.get("credential_error"),
        }
        for row in routing
    ]
    usable_count = sum(
        1
        for row in safe_credentials
        if row.get("status") != "inactive"
        and row.get("decrypt_ok") is not False
        and not row.get("last_error")
    )
    return (
        {
            "path": str(db_path),
            "exists": True,
            "credential_count": len(safe_credentials),
            "usable_count": usable_count,
            "routing_configured_count": sum(1 for row in safe_routing if row.get("configured")),
        },
        safe_credentials,
        safe_routing,
        None,
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    env_path = Path(args.env).expanduser()
    dotenv_values = _parse_env_file(env_path)
    env_values = _merged_env(dotenv_values)
    config_path = Path(args.config).expanduser() if args.config else Path(get_sites_config_path())
    config = load_yaml(str(config_path), default={})
    db_path = _resolve_db_path(config, args.db)

    db_summary, credentials, routing, db_error = _db_report(db_path)

    db_provider_pairs = {
        (str(row.get("provider_id") or ""), str(row.get("category") or ""))
        for row in credentials
        if row.get("source") == "db"
    }
    duplicated_provider_keys = []
    for provider, (key_env, _) in sorted(PROVIDER_STARTUP_ENV_MAP.items()):
        category = "search" if provider in {"brave_search", "serpapi", "serper", "tavily"} else "llm"
        if env_values.get(key_env) and (provider, category) in db_provider_pairs:
            duplicated_provider_keys.append(
                {"provider_id": provider, "category": category, "api_key_env": key_env}
            )

    warnings: list[str] = []
    if not env_values.get("FASTAPI_SESSION_SECRET"):
        warnings.append("FASTAPI_SESSION_SECRET is missing; email registration/login cannot set sessions.")
    if not env_values.get("TOKEN_ENCRYPTION_KEY"):
        warnings.append("TOKEN_ENCRYPTION_KEY is missing; DB credentials cannot be decrypted.")
    elif not _valid_fernet_key(env_values["TOKEN_ENCRYPTION_KEY"]):
        warnings.append("TOKEN_ENCRYPTION_KEY is present but is not a valid Fernet key.")
    if db_error:
        warnings.append(db_error)
    if any(row.get("decrypt_ok") is False or row.get("last_error") for row in credentials):
        warnings.append("At least one DB credential is not decryptable with the current TOKEN_ENCRYPTION_KEY.")
    if duplicated_provider_keys:
        warnings.append(
            "Some provider API keys exist in both .env and encrypted DB credentials; runtime prefers DB and treats env as fallback."
        )
    if env_values.get("CONFIG_WRITE_AUTH_TOKEN") and (
        env_values.get("BOOTSTRAP_ADMIN_TOKEN") != env_values.get("CONFIG_WRITE_AUTH_TOKEN")
    ):
        warnings.append("BOOTSTRAP_ADMIN_TOKEN and CONFIG_WRITE_AUTH_TOKEN differ; token login may not satisfy legacy write-token checks.")
    if not warnings:
        warnings.append("Secret and credential state looks consistent.")

    return {
        "env_file": str(env_path),
        "config_file": str(config_path),
        "secret_presence": {key: bool(env_values.get(key)) for key in AUTH_SECRET_KEYS},
        "token_encryption_key": {
            "present": bool(env_values.get("TOKEN_ENCRYPTION_KEY")),
            "valid_fernet": _valid_fernet_key(env_values.get("TOKEN_ENCRYPTION_KEY", "")),
        },
        "auth_token_alignment": {
            "bootstrap_matches_config_write": bool(env_values.get("BOOTSTRAP_ADMIN_TOKEN"))
            and env_values.get("BOOTSTRAP_ADMIN_TOKEN") == env_values.get("CONFIG_WRITE_AUTH_TOKEN"),
            "logs_matches_config_write": bool(env_values.get("LOGS_READ_AUTH_TOKEN"))
            and env_values.get("LOGS_READ_AUTH_TOKEN") == env_values.get("CONFIG_WRITE_AUTH_TOKEN"),
            "file_delete_matches_config_write": bool(env_values.get("FILE_DELETION_AUTH_TOKEN"))
            and env_values.get("FILE_DELETION_AUTH_TOKEN") == env_values.get("CONFIG_WRITE_AUTH_TOKEN"),
        },
        "provider_env_keys": _provider_env_status(env_values),
        "database": db_summary,
        "database_credentials": credentials,
        "ai_routing": routing,
        "duplicated_provider_keys": duplicated_provider_keys,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env", help="Path to the dotenv file to inspect.")
    parser.add_argument("--config", help="Path to sites.yaml. Defaults to the active project config.")
    parser.add_argument("--db", help="Path to SQLite database. Defaults to sites.yaml paths.db/database.path.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, value in report.items():
            if isinstance(value, (dict, list)):
                print(f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}")
            else:
                print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

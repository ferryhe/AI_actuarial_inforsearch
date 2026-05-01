#!/usr/bin/env python3
"""Diagnose the effective RAG embedding runtime without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_actuarial.ai_runtime import list_provider_credentials, resolve_ai_function_runtime
from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml
from ai_actuarial.storage import Storage


def _resolve_config_path(raw_path: str | None) -> str:
    if raw_path:
        return str(Path(raw_path).expanduser())
    return get_sites_config_path()


def _resolve_db_path(config: dict[str, Any], raw_path: str | None) -> str:
    if raw_path:
        return str(Path(raw_path).expanduser())
    paths = config.get("paths") or {}
    database = config.get("database") or {}
    return str(paths.get("db") or database.get("path") or "data/index.db")


def _find_credential_status(credentials: list[dict[str, Any]], credential_id: str | None, stable_id: str | None) -> dict[str, Any]:
    for row in credentials:
        if credential_id and row.get("credential_id") == credential_id:
            return row
        if stable_id and row.get("stable_credential_id") == stable_id:
            return row
    return {}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    config_path = _resolve_config_path(args.config)
    config = load_yaml(config_path, default={})
    db_path = _resolve_db_path(config, args.db)
    token_key_configured = bool(os.getenv("TOKEN_ENCRYPTION_KEY"))

    storage = Storage(db_path)
    try:
        runtime = resolve_ai_function_runtime("embeddings", storage=storage, yaml_config=config)
        credentials = list_provider_credentials(storage=storage).get("credentials", [])
    finally:
        storage.close()

    credential_status = _find_credential_status(
        credentials,
        runtime.credential_id,
        runtime.stable_credential_id,
    )
    suggested_next_steps: list[str] = []
    if not token_key_configured:
        suggested_next_steps.append("Set TOKEN_ENCRYPTION_KEY in the API and worker environments.")
    if runtime.credential_source == "missing":
        suggested_next_steps.append("Create or select a usable provider credential for ai_config.embeddings.")
    if credential_status.get("decrypt_ok") is False:
        suggested_next_steps.append("Check TOKEN_ENCRYPTION_KEY consistency or re-encrypt provider credentials.")
    if not suggested_next_steps:
        suggested_next_steps.append("Embedding runtime appears configured.")

    report = {
        "config_path": config_path,
        "db_path": db_path,
        "embeddings": {
            "provider": runtime.provider,
            "model": runtime.model,
            "credential_source": runtime.credential_source,
            "credential_id": runtime.credential_id,
            "stable_credential_id": runtime.stable_credential_id,
            "credential_label": runtime.credential_label,
            "credential_error": runtime.credential_error,
            "has_api_key": bool(runtime.api_key),
            "has_base_url": bool(runtime.base_url),
            "configured": runtime.configured,
        },
        "credential_status": {
            "decrypt_ok": credential_status.get("decrypt_ok"),
            "status": credential_status.get("status"),
            "source": credential_status.get("source"),
            "last_error": credential_status.get("last_error"),
        },
        "token_encryption_key_configured": token_key_configured,
        "suggested_next_steps": suggested_next_steps,
    }
    if args.include_env_status:
        report["env_status"] = {
            "OPENAI_API_KEY_configured": bool(os.getenv("OPENAI_API_KEY")),
            "RAG_EMBEDDING_PROVIDER": os.getenv("RAG_EMBEDDING_PROVIDER") or "",
            "RAG_EMBEDDING_MODEL": os.getenv("RAG_EMBEDDING_MODEL") or "",
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose RAG embedding runtime without printing secrets.")
    parser.add_argument("--config", help="Path to sites.yaml. Defaults to the configured project path.")
    parser.add_argument("--db", help="Path to SQLite database. Defaults to config paths.db/database.path.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--include-env-status", action="store_true", help="Include boolean env/config status only.")
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

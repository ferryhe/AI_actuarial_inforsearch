"""Resumable catalog generation script.

NOTE: As of this version, the CLI has integrated incremental catalog processing.
You can run `python -m ai_actuarial catalog` directly instead of this script.

This script is kept for backward compatibility and as a standalone alternative
that can be configured via environment variables:
  - DATABASE_URL: PostgreSQL connection URL (or CATALOG_DATABASE_URL_ENV)
  - DATA_DIR: Artifact directory (default: data)
  - CATALOG_JSONL: Output JSONL path (default: data/catalog.jsonl)
  - CATALOG_MD: Output Markdown path (default: data/catalog.md)
  - CATALOG_BATCH: Batch size (default: 200)
  - CATALOG_SITE: Site filter (comma-separated)
  - CATALOG_AI_ONLY: Set to "1" for AI-only filtering
  - CATALOG_VERSION: Version string for reprocessing (default: catalog_v1)
  - CATALOG_MAX_CHARS: Max chars to extract (default: 20000)
  - CATALOG_RETRY_ERRORS: Set to "1" to retry previously failed files
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_actuarial.catalog_incremental import run_incremental_catalog
from ai_actuarial.postgres import resolve_data_root, resolve_database_config
from ai_actuarial.shared_runtime import load_sites_config, resolve_data_path


def main() -> int:
    config = load_sites_config(default={})
    url_env = os.getenv("CATALOG_DATABASE_URL_ENV", "DATABASE_URL").strip() or "DATABASE_URL"
    database_config = dict(config)
    database_config["database"] = {"type": "postgresql", "url_env": url_env}
    db_path = resolve_database_config(database_config)
    data_root = resolve_data_root(config)
    out_jsonl = resolve_data_path(
        os.getenv("CATALOG_JSONL", str(data_root / "catalog.jsonl")), data_root=data_root
    )
    out_md = resolve_data_path(
        os.getenv("CATALOG_MD", str(data_root / "catalog.md")), data_root=data_root
    )
    batch = int(os.getenv("CATALOG_BATCH", "200"))
    site_filter = os.getenv("CATALOG_SITE")
    ai_only = os.getenv("CATALOG_AI_ONLY", "0") == "1"
    catalog_version = os.getenv("CATALOG_VERSION", "catalog_v1")
    max_chars = int(os.getenv("CATALOG_MAX_CHARS", "20000"))
    retry_errors = os.getenv("CATALOG_RETRY_ERRORS", "0") == "1"

    stats = run_incremental_catalog(
        db_path=db_path,
        out_jsonl=out_jsonl,
        out_md=out_md,
        batch=batch,
        site_filter=site_filter,
        ai_only=ai_only,
        catalog_version=catalog_version,
        max_chars=max_chars,
        retry_errors=retry_errors,
    )

    print(
        f"finished: scanned={stats['scanned']} processed={stats['processed']} "
        f"written={stats['written']} skipped_ai={stats['skipped_ai']} errors={stats['errors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

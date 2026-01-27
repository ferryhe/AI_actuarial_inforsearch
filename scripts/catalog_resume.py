from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# NOTE:
# - This script assumes you are using the updated ai_actuarial.catalog (e.g. catalog_replacement.py content)
#   that provides: extract_text, extract_keywords, summarize, categorize, is_ai_related, CatalogItem, write_catalog_md
from ai_actuarial.catalog import (
    CatalogItem,
    categorize,
    extract_keywords,
    extract_text,
    is_ai_related,
    summarize,
    write_catalog_md,
)

# ----------------------------
# DB helpers
# ----------------------------

CATALOG_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS catalog_items (
    file_url TEXT PRIMARY KEY,
    file_sha256 TEXT,
    title TEXT,
    source_site TEXT,
    original_filename TEXT,
    local_path TEXT,
    keywords_json TEXT,
    summary TEXT,
    category TEXT,
    catalog_version TEXT,
    processed_at TEXT,
    status TEXT,
    error TEXT
);
"""

CATALOG_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_catalog_items_status ON catalog_items(status);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute(CATALOG_TABLE_DDL)
    conn.execute(CATALOG_INDEX_DDL)
    conn.commit()
    return conn


def _ensure_output_header_md(out_md: Path) -> None:
    if out_md.exists():
        return
    # write_catalog_md writes header when append=False; we just keep file absent on first write.
    out_md.parent.mkdir(parents=True, exist_ok=True)


def _append_jsonl(out_jsonl: Path, items: Iterable[dict]) -> None:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(out_jsonl, "a", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _fetch_candidates(
    conn: sqlite3.Connection,
    *,
    batch: int,
    site_filter: Optional[str],
    catalog_version: str,
) -> list[sqlite3.Row]:
    """
    Select files that are:
    - not in catalog_items, OR
    - sha256 changed, OR
    - catalog_version changed, OR
    - last run status != 'ok' (retry)
    Deterministic order: files.id ASC.
    """
    filters: list[str] = []
    params: list[object] = []

    if site_filter:
        # support comma separated
        sites = [s.strip().lower() for s in site_filter.split(",") if s.strip()]
        if sites:
            # Build OR LIKEs for source_site
            filters.append("(" + " OR ".join(["LOWER(f.source_site) LIKE ?"] * len(sites)) + ")")
            params.extend([f"%{s}%" for s in sites])

    where_extra = (" AND " + " AND ".join(filters)) if filters else ""

    sql = f"""
    SELECT
        f.id,
        f.url,
        f.sha256,
        f.title,
        f.source_site,
        f.original_filename,
        f.local_path,
        c.file_sha256 AS c_sha256,
        c.catalog_version AS c_version,
        c.status AS c_status
    FROM files f
    LEFT JOIN catalog_items c
        ON c.file_url = f.url
    WHERE
        f.local_path IS NOT NULL
        AND f.local_path != ''
        AND (
            c.file_url IS NULL
            OR c.file_sha256 IS NULL
            OR c.file_sha256 != f.sha256
            OR c.catalog_version != ?
            OR c.status IS NULL
            OR c.status != 'ok'
        )
        {where_extra}
    ORDER BY f.id ASC
    LIMIT ?
    """
    params2 = params + [catalog_version, batch]
    cur = conn.execute(sql, params2)
    return list(cur.fetchall())


def _upsert_catalog_row(
    conn: sqlite3.Connection,
    *,
    item: CatalogItem,
    file_sha256: str,
    catalog_version: str,
    status: str,
    processed_at: str,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO catalog_items (
            file_url, file_sha256, title, source_site, original_filename, local_path,
            keywords_json, summary, category, catalog_version, processed_at, status, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_url) DO UPDATE SET
            file_sha256=excluded.file_sha256,
            title=excluded.title,
            source_site=excluded.source_site,
            original_filename=excluded.original_filename,
            local_path=excluded.local_path,
            keywords_json=excluded.keywords_json,
            summary=excluded.summary,
            category=excluded.category,
            catalog_version=excluded.catalog_version,
            processed_at=excluded.processed_at,
            status=excluded.status,
            error=excluded.error
        """,
        (
            item.url,
            file_sha256,
            item.title,
            item.source_site,
            item.original_filename,
            item.local_path,
            json.dumps(item.keywords, ensure_ascii=False),
            item.summary,
            item.category,
            catalog_version,
            processed_at,
            status,
            error,
        ),
    )


def main() -> int:
    db_path = os.getenv("CATALOG_DB", "data/index.db")
    out_jsonl = Path(os.getenv("CATALOG_JSONL", "data/catalog.jsonl"))
    out_md = Path(os.getenv("CATALOG_MD", "data/catalog.md"))

    batch = int(os.getenv("CATALOG_BATCH", "200"))
    site_filter = os.getenv("CATALOG_SITE")
    ai_only = os.getenv("CATALOG_AI_ONLY", "0") == "1"

    # Bump this when you change categorization/keyword/summarization logic and want selective re-run.
    catalog_version = os.getenv("CATALOG_VERSION", "catalog_v1")

    max_chars = int(os.getenv("CATALOG_MAX_CHARS", "20000"))

    conn = _connect(db_path)
    _ensure_output_header_md(out_md)

    total_processed = 0
    total_written = 0
    total_skipped_ai = 0
    total_errors = 0

    while True:
        rows = _fetch_candidates(
            conn,
            batch=batch,
            site_filter=site_filter,
            catalog_version=catalog_version,
        )
        if not rows:
            break

        batch_items: list[CatalogItem] = []
        batch_jsonl: list[dict] = []

        # Run in one transaction per batch
        conn.execute("BEGIN")
        for r in rows:
            file_url = r["url"]
            file_sha256 = r["sha256"] or ""
            title = r["title"]
            source_site = r["source_site"]
            original_filename = r["original_filename"]
            local_path = r["local_path"]

            try:
                text = extract_text(Path(local_path), max_chars=max_chars)
                if not text.strip():
                    raise RuntimeError("empty extracted text")

                keywords = extract_keywords(text, title=title)
                if ai_only and not is_ai_related(text, keywords, title=title):
                    total_skipped_ai += 1
                    # Still mark as ok to avoid repeated work if ai_only stays on.
                    item = CatalogItem(
                        source_site=source_site,
                        title=title,
                        original_filename=original_filename,
                        url=file_url,
                        local_path=local_path,
                        keywords=keywords,
                        summary="",
                        category="(filtered: non-AI)",
                    )
                    _upsert_catalog_row(
                        conn,
                        item=item,
                        file_sha256=file_sha256,
                        catalog_version=catalog_version,
                        status="ok",
                        processed_at=datetime.now(timezone.utc).isoformat(),
                        error=None,
                    )
                    total_processed += 1
                    continue

                summary = summarize(text, keywords)
                category = categorize(title, text, keywords)

                item = CatalogItem(
                    source_site=source_site,
                    title=title,
                    original_filename=original_filename,
                    url=file_url,
                    local_path=local_path,
                    keywords=keywords,
                    summary=summary,
                    category=category,
                )

                _upsert_catalog_row(
                    conn,
                    item=item,
                    file_sha256=file_sha256,
                    catalog_version=catalog_version,
                    status="ok",
                    processed_at=datetime.now(timezone.utc).isoformat(),
                    error=None,
                )

                batch_items.append(item)
                batch_jsonl.append(asdict(item))
                total_processed += 1

            except Exception as e:
                total_errors += 1
                # Record the failure so we can retry later; status != ok will be picked up again
                item = CatalogItem(
                    source_site=source_site,
                    title=title,
                    original_filename=original_filename,
                    url=file_url,
                    local_path=local_path,
                    keywords=[],
                    summary="",
                    category="(error)",
                )
                _upsert_catalog_row(
                    conn,
                    item=item,
                    file_sha256=file_sha256,
                    catalog_version=catalog_version,
                    status="error",
                    processed_at=datetime.now(timezone.utc).isoformat(),
                    error=str(e),
                )

        conn.commit()

        # Write outputs incrementally (no full-file rewrite)
        if batch_items:
            _append_jsonl(out_jsonl, batch_jsonl)
            write_catalog_md(out_md, batch_items, append=out_md.exists())
            total_written += len(batch_items)

        print(
            f"batch done: scanned={len(rows)} processed={total_processed} written={total_written} "
            f"skipped_ai={total_skipped_ai} errors={total_errors}"
        )

    conn.close()
    print(
        f"finished: processed={total_processed} written={total_written} "
        f"skipped_ai={total_skipped_ai} errors={total_errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

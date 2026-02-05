"""Incremental catalog processing with DB-based state tracking and JSONL output.

This module provides incremental catalog generation that:
- Tracks processed files in catalog_items table
- Only processes new/changed files (by sha256 or catalog_version)
- Appends output to JSONL and Markdown files (no full rewrites)
- Supports resumable batch processing
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .catalog import (
    CatalogItem,
    categorize,
    extract_keywords,
    extract_text,
    is_ai_related,
    summarize,
    write_catalog_md,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL for catalog_items (same as storage.py, kept as fallback)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    # Ensure table exists (fallback if Storage didn't create it)
    conn.execute(CATALOG_TABLE_DDL)
    conn.execute(CATALOG_INDEX_DDL)
    conn.commit()
    return conn


def _fetch_candidates(
    conn: sqlite3.Connection,
    *,
    batch: int,
    site_filter: Optional[str],
    catalog_version: str,
    retry_errors: bool = False,
) -> list[sqlite3.Row]:
    """
    Select files that are:
    - not in catalog_items, OR
    - sha256 changed, OR
    - catalog_version changed
    
    By default, already-processed files (including errors) are NOT retried.
    Set retry_errors=True to reprocess files with status='error'.
    Deterministic order: files.id ASC.
    """
    filters: list[str] = []
    params: list[object] = []

    if site_filter:
        sites = [s.strip().lower() for s in site_filter.split(",") if s.strip()]
        if sites:
            filters.append(
                "(" + " OR ".join(["LOWER(f.source_site) LIKE ?"] * len(sites)) + ")"
            )
            params.extend([f"%{s}%" for s in sites])

    where_extra = (" AND " + " AND ".join(filters)) if filters else ""

    # Build the reprocess condition:
    # - c.file_url IS NULL: never processed
    # - c.file_sha256 != f.sha256: file content changed
    # - c.catalog_version != ?: catalog version changed (force reprocess)
    # Errors are NOT retried by default (they typically keep failing)
    if retry_errors:
        status_cond = "OR c.status = 'error'"
    else:
        status_cond = ""

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
            {status_cond}
        )
        {where_extra}
    -- ORDER BY f.id ASC ensures deterministic, incremental processing
    -- (oldest files first). Alternative: DESC for newest files first.
    ORDER BY f.id ASC
    LIMIT ?
    """
    cur = conn.execute(sql, [catalog_version, batch] + params)
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


def _append_jsonl(out_jsonl: Path, items: list[dict]) -> None:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with open(out_jsonl, "a", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main incremental catalog function
# ---------------------------------------------------------------------------


def run_incremental_catalog(
    db_path: str,
    out_jsonl: Path,
    out_md: Path,
    batch: int = 200,
    site_filter: Optional[str] = None,
    ai_only: bool = False,
    catalog_version: str = "catalog_v1",
    max_chars: int = 20000,
    retry_errors: bool = False,
) -> dict:
    """Run incremental catalog processing.
    
    Args:
        db_path: Path to SQLite database
        out_jsonl: Path to output JSONL file (append mode)
        out_md: Path to output Markdown file (append mode)
        batch: Number of files to process per batch
        site_filter: Comma-separated site names to filter (optional)
        ai_only: Only keep AI-related items
        catalog_version: Version string for tracking reprocessing
        max_chars: Max characters to extract from each file
        retry_errors: If True, retry files that previously failed
        
    Returns:
        dict with stats: {scanned, processed, written, skipped_ai, errors}
    """
    conn = _connect(db_path)
    
    # Ensure output directories exist
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "scanned": 0,
        "processed": 0,
        "written": 0,
        "skipped_ai": 0,
        "errors": 0,
    }
    
    while True:
        rows = _fetch_candidates(
            conn,
            batch=batch,
            site_filter=site_filter,
            catalog_version=catalog_version,
            retry_errors=retry_errors,
        )
        if not rows:
            break
            
        stats["scanned"] += len(rows)
        batch_items: list[CatalogItem] = []
        batch_jsonl: list[dict] = []
        
        # Use BEGIN IMMEDIATE to prevent concurrent write conflicts
        conn.execute("BEGIN IMMEDIATE")
        for r in rows:
            file_url = r["url"]
            file_sha256 = r["sha256"] or ""
            title = r["title"]
            source_site = r["source_site"]
            original_filename = r["original_filename"]
            local_path = r["local_path"]
            processed_at = datetime.now(timezone.utc).isoformat()
            
            try:
                text = extract_text(Path(local_path), max_chars=max_chars)
                if not text.strip():
                    raise RuntimeError("empty extracted text")
                    
                keywords = extract_keywords(text, title=title)
                
                if ai_only and not is_ai_related(text, keywords, title=title):
                    stats["skipped_ai"] += 1
                    # Mark as skipped instead of ok to distinguish from successfully processed items
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
                        status="skipped",
                        processed_at=processed_at,
                    )
                    # Don't increment processed count for skipped items
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
                    processed_at=processed_at,
                )
                
                batch_items.append(item)
                batch_jsonl.append(asdict(item))
                stats["processed"] += 1
                
            except Exception as e:
                stats["errors"] += 1
                logger.warning("Error processing %s: %s", file_url, e)
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
                    processed_at=processed_at,
                    error=str(e),
                )
                
        conn.commit()
        
        # Append outputs incrementally
        if batch_items:
            _append_jsonl(out_jsonl, batch_jsonl)
            write_catalog_md(out_md, batch_items, append=out_md.exists())
            stats["written"] += len(batch_items)
            
        logger.info(
            "Batch done: scanned=%d processed=%d written=%d skipped_ai=%d errors=%d",
            len(rows), stats["processed"], stats["written"], 
            stats["skipped_ai"], stats["errors"]
        )
        
    conn.close()
    logger.info(
        "Incremental catalog finished: scanned=%d processed=%d written=%d skipped_ai=%d errors=%d",
        stats["scanned"], stats["processed"], stats["written"],
        stats["skipped_ai"], stats["errors"]
    )
    return stats

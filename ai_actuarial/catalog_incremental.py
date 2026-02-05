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

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)

# Lock for DB writes since SQLite doesn't like concurrent writes from threads
# even in WAL mode if using the same connection object, but here we share connection?
# Ideally each thread gets its own connection or we write centrally.
# To be safe and simple: process in parallel, write sequentially.
_db_lock = threading.Lock()

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

    # Sort newest first (descending ID) so we process recent content first.
    # Deterministic order: files.id DESC.
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
    ORDER BY f.id DESC
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


def _resolve_path(path_str: str, base_dirs: list[Path] | None = None) -> Path:
    """Resolve file path trying multiple base directories."""
    p = Path(path_str)
    if p.exists():
        return p
        
    if base_dirs:
        for base in base_dirs:
            # Try combining
            candidate = base / p
            if candidate.exists():
                return candidate
            # Try relative to base if p is absolute or contains redundant parts?
            # E.g. base=data, p=files/foo -> data/files/foo
            
    # Hardcoded fallback for common project structure issues
    # If path starts with 'files' and 'data/files' exists
    if str(p).startswith("files") or str(p).startswith("files\\"):
        candidate = Path("data") / p
        if candidate.exists():
            return candidate
            
    return p


def _process_single_row(
    row_data: dict, 
    ai_only: bool, 
    max_chars: int
) -> tuple[dict, CatalogItem, str]:
    """Process a single row in a worker thread.
    Returns: (row_data, result_item, status)
    """
    file_url = row_data["url"]
    title = row_data["title"]
    source_site = row_data["source_site"]
    original_filename = row_data["original_filename"]
    local_path = row_data["local_path"]
    
    try:
        resolved_path = _resolve_path(local_path)
        text = extract_text(resolved_path, max_chars=max_chars)
        if not text.strip():
            # If still empty check if exist
            if not resolved_path.exists():
                raise RuntimeError(f"File not found: {resolved_path} (orig: {local_path})")
            raise RuntimeError("empty extracted text")
            
        keywords = extract_keywords(text, title=title)
        
        if ai_only and not is_ai_related(text, keywords, title=title):
            # Skipped
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
            return (row_data, item, "skipped")
            
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
        return (row_data, item, "ok")
        
    except Exception as e:
        # Return error item
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
        # Store error in item temporarily or pass back? 
        # We can attach it to the item wrapper or just use the status return
        # Using status to pass exception string
        return (row_data, item, f"error:{str(e)}")


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
    max_workers: int = 5,
    limit: int = 0
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
        max_workers: Threads for parallel processing
        limit: Max total items to process (0 for unlimited)
        
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
        "missing_files": 0,
    }
    
    seen_urls = set()

    while True:
        # Check global limit
        if limit > 0 and stats["processed"] >= limit:
            logger.info(f"Reached limit of {limit} items")
            break

        current_batch_size = batch
        # We generally want to fetch enough to make progress, even if we discard duplicates
        # But we don't want to fetch too many.
        
        rows = _fetch_candidates(
            conn,
            batch=current_batch_size,
            site_filter=site_filter,
            catalog_version=catalog_version,
            retry_errors=retry_errors,
        )
        
        # Filter already seen URLs to prevent infinite loops when retrying errors
        new_rows = [r for r in rows if r["url"] not in seen_urls]
        
        if not new_rows:
            if not rows:
                # No more candidates at all
                break
            else:
                # Candidates exist but we've seen them all in this run = loop detected
                logger.info("Infinite loop detected (all duplicates), stopping")
                break
            
        stats["scanned"] += len(new_rows)
        batch_items: list[CatalogItem] = []
        batch_jsonl: list[dict] = []
        
        # Convert sqlite rows to dicts for thread safety (sqlite3.Row might bind to thread?)
        row_dicts = [dict(r) for r in new_rows]
        
        # Mark as seen
        for r in row_dicts:
            seen_urls.add(r["url"])
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(_process_single_row, r, ai_only, max_chars): r['url'] 
                for r in row_dicts
            }
            
            # We will batch writes at the end of the batch processing to keep DB logic simple
            # Or writing as they complete? Batch write is safer for transaction.
            
            for future in as_completed(future_to_url):
                try:
                    r_data, item, status = future.result()
                    processed_at = datetime.now(timezone.utc).isoformat()
                    file_sha256 = r_data["sha256"] or ""
                    
                    if status == "ok":
                        stats["processed"] += 1
                        batch_items.append(item)
                        batch_jsonl.append(asdict(item))
                        
                        _upsert_catalog_row(
                            conn,
                            item=item,
                            file_sha256=file_sha256,
                            catalog_version=catalog_version,
                            status="ok",
                            processed_at=processed_at,
                        )
                        
                    elif status == "skipped":
                        # Non-AI (or otherwise skipped) items are treated as fully processed.
                        # Persist this status so they are not retried on subsequent runs.
                        stats["skipped_ai"] += 1
                        _upsert_catalog_row(
                            conn,
                            item=item,
                            file_sha256=file_sha256,
                            catalog_version=catalog_version,
                            status="skipped",
                            processed_at=processed_at,
                        )
                        
                    elif status.startswith("error:"):
                        stats["errors"] += 1
                        err_msg = status[6:]
                        if "File not found" in err_msg:
                            stats["missing_files"] += 1
                            
                        logger.warning("Error processing %s: %s", r_data["url"], err_msg)
                        _upsert_catalog_row(
                            conn,
                            item=item,
                            file_sha256=file_sha256,
                            catalog_version=catalog_version,
                            status="error",
                            processed_at=processed_at,
                            error=err_msg,
                        )
                        
                except Exception as e:
                    logger.exception("Worker thread crashed")
                    stats["errors"] += 1
        
        conn.commit()
        
        # Append outputs incrementally
        if batch_items:
            _append_jsonl(out_jsonl, batch_jsonl)
            write_catalog_md(out_md, batch_items, append=out_md.exists())
            stats["written"] += len(batch_items)
            
        logger.info(
            "Batch done: scanned=%d processed=%d written=%d skipped_ai=%d errors=%d missing=%d",
            len(new_rows), stats["processed"], stats["written"], 
            stats["skipped_ai"], stats["errors"], stats["missing_files"]
        )
        
    conn.close()
    logger.info(
        "Incremental catalog finished: scanned=%d processed=%d written=%d skipped_ai=%d errors=%d missing=%d",
        stats["scanned"], stats["processed"], stats["written"],
        stats["skipped_ai"], stats["errors"], stats["missing_files"]
    )
    return stats

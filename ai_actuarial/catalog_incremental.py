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
from typing import Callable, Optional

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

CATALOG_OPTIONAL_COLUMNS = {
    "file_sha256": "TEXT",
    "title": "TEXT",
    "source_site": "TEXT",
    "original_filename": "TEXT",
    "local_path": "TEXT",
    "keywords_json": "TEXT",
    "summary": "TEXT",
    "category": "TEXT",
    "catalog_version": "TEXT",
    "processed_at": "TEXT",
    "status": "TEXT",
    "error": "TEXT",
    # Optional markdown cache (populated by markdown conversion / manual edits).
    "markdown_content": "TEXT",
    "markdown_updated_at": "TEXT",
    "markdown_source": "TEXT",
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _ensure_catalog_schema(conn: sqlite3.Connection) -> None:
    """Ensure catalog_items supports both legacy and incremental schemas."""
    existing = _table_columns(conn, "catalog_items")

    for col_name, col_type in CATALOG_OPTIONAL_COLUMNS.items():
        if col_name not in existing:
            conn.execute(
                f"ALTER TABLE catalog_items ADD COLUMN {col_name} {col_type}"
            )

    existing = _table_columns(conn, "catalog_items")

    # Backfill incremental columns from legacy schema when available.
    if "sha256" in existing and "file_sha256" in existing:
        conn.execute(
            """
            UPDATE catalog_items
            SET file_sha256 = sha256
            WHERE (file_sha256 IS NULL OR file_sha256 = '')
              AND sha256 IS NOT NULL
            """
        )
    if "pipeline_version" in existing and "catalog_version" in existing:
        conn.execute(
            """
            UPDATE catalog_items
            SET catalog_version = pipeline_version
            WHERE (catalog_version IS NULL OR catalog_version = '')
              AND pipeline_version IS NOT NULL
            """
        )
    if "keywords" in existing and "keywords_json" in existing:
        conn.execute(
            """
            UPDATE catalog_items
            SET keywords_json = keywords
            WHERE (keywords_json IS NULL OR keywords_json = '')
              AND keywords IS NOT NULL
            """
        )
    # Keep legacy sha256/pipeline_version/keywords populated for NOT NULL schemas.
    if "sha256" in existing and "file_sha256" in existing:
        conn.execute(
            """
            UPDATE catalog_items
            SET sha256 = file_sha256
            WHERE (sha256 IS NULL OR sha256 = '')
              AND file_sha256 IS NOT NULL
            """
        )
    if "pipeline_version" in existing and "catalog_version" in existing:
        conn.execute(
            """
            UPDATE catalog_items
            SET pipeline_version = catalog_version
            WHERE (pipeline_version IS NULL OR pipeline_version = '')
              AND catalog_version IS NOT NULL
            """
        )
    if "keywords" in existing and "keywords_json" in existing:
        conn.execute(
            """
            UPDATE catalog_items
            SET keywords = keywords_json
            WHERE (keywords IS NULL OR keywords = '')
              AND keywords_json IS NOT NULL
            """
        )


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    # Ensure table exists (fallback if Storage didn't create it)
    conn.execute(CATALOG_TABLE_DDL)
    conn.execute(CATALOG_INDEX_DDL)
    _ensure_catalog_schema(conn)
    conn.commit()
    return conn


def _fetch_candidates(
    conn: sqlite3.Connection,
    *,
    batch: int,
    offset: int = 0,
    site_filter: Optional[str],
    catalog_version: str,
    retry_errors: bool = False,
    skip_existing: bool = True,
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
    where_extra, params, status_cond = _candidate_filter_sql(site_filter, retry_errors)

    # Sort newest first (descending ID) so we process recent content first.
    # Deterministic order: files.id DESC.
    candidate_pred = ""
    candidate_params: list[object] = []
    if skip_existing:
        candidate_pred = f"""
        AND (
            c.file_url IS NULL
            OR c.file_sha256 IS NULL
            OR c.file_sha256 != f.sha256
            OR c.catalog_version != ?
            {status_cond}
        )
        """
        candidate_params = [catalog_version]

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
        {candidate_pred}
        {where_extra}
    ORDER BY f.id DESC
    LIMIT ? OFFSET ?
    """
    cur = conn.execute(sql, candidate_params + params + [batch, max(0, int(offset or 0))])
    return list(cur.fetchall())


def _candidate_filter_sql(
    site_filter: Optional[str],
    retry_errors: bool,
) -> tuple[str, list[object], str]:
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
    status_cond = "OR c.status = 'error'" if retry_errors else ""
    return where_extra, params, status_cond


def _count_candidates(
    conn: sqlite3.Connection,
    *,
    site_filter: Optional[str],
    catalog_version: str,
    retry_errors: bool = False,
    skip_existing: bool = True,
) -> int:
    where_extra, params, status_cond = _candidate_filter_sql(site_filter, retry_errors)
    candidate_pred = ""
    candidate_params: list[object] = []
    if skip_existing:
        candidate_pred = f"""
        AND (
            c.file_url IS NULL
            OR c.file_sha256 IS NULL
            OR c.file_sha256 != f.sha256
            OR c.catalog_version != ?
            {status_cond}
        )
        """
        candidate_params = [catalog_version]
    sql = f"""
    SELECT COUNT(*)
    FROM files f
    LEFT JOIN catalog_items c
        ON c.file_url = f.url
    WHERE
        f.local_path IS NOT NULL
        AND f.local_path != ''
        {candidate_pred}
        {where_extra}
    """
    cur = conn.execute(sql, candidate_params + params)
    row = cur.fetchone()
    return int(row[0]) if row else 0


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
    """Upsert catalog item with thread-safe locking.
    
    Uses _db_lock to prevent concurrent write conflicts with SQLite.
    """
    with _db_lock:
        existing = _table_columns(conn, "catalog_items")
        keywords_json = json.dumps(item.keywords, ensure_ascii=False)
        value_map: dict[str, object] = {
            "file_url": item.url,
            "file_sha256": file_sha256,
            "sha256": file_sha256,
            "title": item.title,
            "source_site": item.source_site,
            "original_filename": item.original_filename,
            "local_path": item.local_path,
            "keywords_json": keywords_json,
            "keywords": keywords_json,
            "summary": item.summary,
            "category": item.category,
            "catalog_version": catalog_version,
            "pipeline_version": catalog_version,
            "processed_at": processed_at,
            "status": status,
            "error": error,
        }
        insert_columns = [
            col
            for col in [
                "file_url",
                "file_sha256",
                "sha256",
                "title",
                "source_site",
                "original_filename",
                "local_path",
                "keywords_json",
                "keywords",
                "summary",
                "category",
                "catalog_version",
                "pipeline_version",
                "processed_at",
                "status",
                "error",
            ]
            if col in existing
        ]
        values = [value_map[col] for col in insert_columns]
        update_columns = [col for col in insert_columns if col != "file_url"]
        placeholders = ", ".join(["?"] * len(insert_columns))
        if update_columns:
            assignments = ", ".join([f"{col}=excluded.{col}" for col in update_columns])
            sql = f"""
                INSERT INTO catalog_items ({", ".join(insert_columns)})
                VALUES ({placeholders})
                ON CONFLICT(file_url) DO UPDATE SET
                    {assignments}
            """
        else:
            sql = f"""
                INSERT OR IGNORE INTO catalog_items ({", ".join(insert_columns)})
                VALUES ({placeholders})
            """
        conn.execute(sql, values)
        conn.commit()


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


_thread_local = threading.local()


def _thread_db_conn(db_path: str) -> sqlite3.Connection:
    """Thread-local SQLite connection for read-only lookups (e.g. markdown_content)."""
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _thread_local.conn = conn
    return conn


def _load_markdown_text(db_path: str, file_url: str, max_chars: int) -> str:
    conn = _thread_db_conn(db_path)
    row = conn.execute(
        "SELECT markdown_content FROM catalog_items WHERE file_url = ?",
        (file_url,),
    ).fetchone()
    text = ""
    if row:
        text = (row[0] or "").strip()
    if not text:
        return ""
    if max_chars and max_chars > 0 and len(text) > max_chars:
        return text[:max_chars]
    return text


def _process_single_row(
    row_data: dict, 
    ai_only: bool, 
    max_chars: int,
    *,
    db_path: str,
    provider: str,
    input_source: str,
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
        provider_norm = (provider or "local").strip().lower()
        if provider_norm not in {"local"}:
            raise RuntimeError(f"unsupported catalog provider: {provider}")

        source_norm = (input_source or "source").strip().lower()
        if source_norm not in {"source", "markdown"}:
            raise RuntimeError(f"unsupported catalog input_source: {input_source}")

        text = ""
        if source_norm == "markdown":
            text = _load_markdown_text(db_path, file_url, max_chars=max_chars)
            if not text.strip():
                raise RuntimeError("missing markdown content")
        else:
            resolved_path = _resolve_path(local_path)
            text = extract_text(resolved_path, max_chars=max_chars)
        if not text.strip():
            # If still empty check if exist
            if source_norm == "source" and not resolved_path.exists():
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
    skip_existing: bool = True,
    provider: str = "local",
    input_source: str = "source",
    max_workers: int = 5,
    limit: int = 0,
    candidate_offset: int = 0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
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
        "error_samples": [],
    }
    
    seen_urls = set()
    total_candidates = _count_candidates(
        conn,
        site_filter=site_filter,
        catalog_version=catalog_version,
        retry_errors=retry_errors,
        skip_existing=skip_existing,
    )
    if candidate_offset > 0:
        total_candidates = max(0, total_candidates - int(candidate_offset))
    if limit > 0:
        total_candidates = min(total_candidates, limit)
    if progress_callback:
        progress_callback(
            0,
            max(total_candidates, 1),
            f"Catalog candidates: {total_candidates}",
        )

    remaining_offset = max(0, int(candidate_offset or 0))
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
            offset=remaining_offset,
            site_filter=site_filter,
            catalog_version=catalog_version,
            retry_errors=retry_errors,
            skip_existing=skip_existing,
        )
        remaining_offset = 0
        
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
                executor.submit(
                    _process_single_row,
                    r,
                    ai_only,
                    max_chars,
                    db_path=db_path,
                    provider=provider,
                    input_source=input_source,
                ): r["url"]
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
                        if progress_callback:
                            completed = (
                                stats["processed"] + stats["skipped_ai"] + stats["errors"]
                            )
                            progress_callback(
                                completed,
                                max(total_candidates, completed, 1),
                                f"Cataloging {completed}/{max(total_candidates, 1)}",
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
                        if progress_callback:
                            completed = (
                                stats["processed"] + stats["skipped_ai"] + stats["errors"]
                            )
                            progress_callback(
                                completed,
                                max(total_candidates, completed, 1),
                                f"Cataloging {completed}/{max(total_candidates, 1)}",
                            )
                        
                    elif status.startswith("error:"):
                        stats["errors"] += 1
                        err_msg = status[6:]
                        if len(stats["error_samples"]) < 20:
                            stats["error_samples"].append(err_msg)
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
                        if progress_callback:
                            completed = (
                                stats["processed"] + stats["skipped_ai"] + stats["errors"]
                            )
                            progress_callback(
                                completed,
                                max(total_candidates, completed, 1),
                                f"Cataloging {completed}/{max(total_candidates, 1)}",
                            )
                        
                except Exception as e:
                    logger.exception("Worker thread crashed")
                    stats["errors"] += 1
                    if len(stats["error_samples"]) < 20:
                        stats["error_samples"].append(str(e))
        
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
    if progress_callback:
        completed = stats["processed"] + stats["skipped_ai"] + stats["errors"]
        progress_callback(
            max(total_candidates, completed, 1),
            max(total_candidates, completed, 1),
            f"Catalog finished: processed={stats['processed']} skipped={stats['skipped_ai']} errors={stats['errors']}",
        )
    return stats


def run_catalog_for_urls(
    *,
    db_path: str,
    file_urls: list[str],
    out_jsonl: Path,
    out_md: Path,
    ai_only: bool = False,
    catalog_version: str = "catalog_v1",
    max_chars: int = 20000,
    retry_errors: bool = False,
    skip_existing: bool = True,
    provider: str = "local",
    input_source: str = "source",
    max_workers: int = 5,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """Catalog a specific list of file URLs (used by File Details actions)."""
    conn = _connect(db_path)

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "scanned": 0,
        "processed": 0,
        "written": 0,
        "skipped_ai": 0,
        "errors": 0,
        "missing_files": 0,
        "error_samples": [],
    }

    urls = [u for u in (file_urls or []) if isinstance(u, str) and u.strip()]
    urls = [u.strip() for u in urls]
    if not urls:
        conn.close()
        return stats

    placeholders = ", ".join(["?"] * len(urls))
    rows = conn.execute(
        f"""
        SELECT
            f.id,
            f.url,
            f.sha256,
            f.title,
            f.source_site,
            f.original_filename,
            f.local_path,
            c.file_url AS c_url,
            c.file_sha256 AS c_sha256,
            c.catalog_version AS c_version,
            c.status AS c_status
        FROM files f
        LEFT JOIN catalog_items c ON c.file_url = f.url
        WHERE f.url IN ({placeholders})
          AND f.deleted_at IS NULL
        """,
        urls,
    ).fetchall()

    by_url = {r["url"]: dict(r) for r in rows}
    ordered_rows = []
    for u in urls:
        r = by_url.get(u)
        if r:
            ordered_rows.append(r)
        else:
            stats["errors"] += 1
            if len(stats["error_samples"]) < 20:
                stats["error_samples"].append(f"File not found in DB: {u}")

    def is_candidate(r: dict) -> bool:
        if not skip_existing:
            return True
        c_url = r.get("c_url")
        c_sha = (r.get("c_sha256") or "").strip()
        c_ver = (r.get("c_version") or "").strip()
        c_status = (r.get("c_status") or "").strip()
        f_sha = (r.get("sha256") or "").strip()
        return (
            (c_url is None)
            or (not c_sha)
            or (c_sha != f_sha)
            or (c_ver != catalog_version)
            or (retry_errors and c_status == "error")
        )

    candidates = [r for r in ordered_rows if is_candidate(r)]
    stats["scanned"] = len(candidates)

    if progress_callback:
        progress_callback(0, max(len(candidates), 1), f"Catalog candidates: {len(candidates)}")

    batch_items: list[CatalogItem] = []
    batch_jsonl: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(
                _process_single_row,
                r,
                ai_only,
                max_chars,
                db_path=db_path,
                provider=provider,
                input_source=input_source,
            ): r["url"]
            for r in candidates
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                r_data, item, status = future.result()
                processed_at = datetime.now(timezone.utc).isoformat()
                file_sha256 = (r_data.get("sha256") or "").strip()
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
                    if len(stats["error_samples"]) < 20:
                        stats["error_samples"].append(err_msg)
                    if "File not found" in err_msg:
                        stats["missing_files"] += 1
                    _upsert_catalog_row(
                        conn,
                        item=item,
                        file_sha256=file_sha256,
                        catalog_version=catalog_version,
                        status="error",
                        processed_at=processed_at,
                        error=err_msg,
                    )
                if progress_callback:
                    completed = stats["processed"] + stats["skipped_ai"] + stats["errors"]
                    progress_callback(completed, max(len(candidates), completed, 1), f"Cataloging {completed}/{max(len(candidates), 1)}")
            except Exception as e:
                logger.exception("Worker thread crashed for %s", url)
                stats["errors"] += 1
                if len(stats["error_samples"]) < 20:
                    stats["error_samples"].append(str(e))

    if batch_items:
        _append_jsonl(out_jsonl, batch_jsonl)
        write_catalog_md(out_md, batch_items, append=out_md.exists())
        stats["written"] += len(batch_items)

    conn.close()
    if progress_callback:
        completed = stats["processed"] + stats["skipped_ai"] + stats["errors"]
        progress_callback(
            max(len(candidates), completed, 1),
            max(len(candidates), completed, 1),
            f"Catalog finished: processed={stats['processed']} skipped={stats['skipped_ai']} errors={stats['errors']}",
        )
    return stats

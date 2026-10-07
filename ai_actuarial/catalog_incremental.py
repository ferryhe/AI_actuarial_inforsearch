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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from .storage import Storage
from .task_item_errors import record_item_error

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
            conn.execute(f"ALTER TABLE catalog_items ADD COLUMN {col_name} {col_type}")

    existing = _table_columns(conn, "catalog_items")

    # Backfill incremental columns from legacy schema when available.
    if "sha256" in existing and "file_sha256" in existing:
        conn.execute("""
            UPDATE catalog_items
            SET file_sha256 = sha256
            WHERE (file_sha256 IS NULL OR file_sha256 = '')
              AND sha256 IS NOT NULL
            """)
    if "pipeline_version" in existing and "catalog_version" in existing:
        conn.execute("""
            UPDATE catalog_items
            SET catalog_version = pipeline_version
            WHERE (catalog_version IS NULL OR catalog_version = '')
              AND pipeline_version IS NOT NULL
            """)
    if "keywords" in existing and "keywords_json" in existing:
        conn.execute("""
            UPDATE catalog_items
            SET keywords_json = keywords
            WHERE (keywords_json IS NULL OR keywords_json = '')
              AND keywords IS NOT NULL
            """)
    # Keep legacy sha256/pipeline_version/keywords populated for NOT NULL schemas.
    if "sha256" in existing and "file_sha256" in existing:
        conn.execute("""
            UPDATE catalog_items
            SET sha256 = file_sha256
            WHERE (sha256 IS NULL OR sha256 = '')
              AND file_sha256 IS NOT NULL
            """)
    if "pipeline_version" in existing and "catalog_version" in existing:
        conn.execute("""
            UPDATE catalog_items
            SET pipeline_version = catalog_version
            WHERE (pipeline_version IS NULL OR pipeline_version = '')
              AND catalog_version IS NOT NULL
            """)
    if "keywords" in existing and "keywords_json" in existing:
        conn.execute("""
            UPDATE catalog_items
            SET keywords = keywords_json
            WHERE (keywords IS NULL OR keywords = '')
              AND keywords_json IS NOT NULL
            """)


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
    seen_urls: set[str] | None = None,
    max_id: int | None = None,
    site_filter: Optional[str],
    category_filter: Optional[str] = None,
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
    Deterministic order: files.id DESC.
    """
    where_extra, params, status_cond = _candidate_filter_sql(
        site_filter, retry_errors, category_filter
    )
    seen_urls = seen_urls or set()
    seen_filter = ""
    seen_params: list[str] = []
    if seen_urls:
        seen_filter = f"AND f.url NOT IN ({','.join('?' for _ in seen_urls)})"
        seen_params = list(seen_urls)
    start_filter = "AND f.id <= ?" if max_id is not None else ""
    start_params = [max_id] if max_id is not None else []

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
            OR TRIM(IFNULL(c.summary, '')) = ''
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
        AND f.deleted_at IS NULL
        {candidate_pred}
        {where_extra}
        {seen_filter}
        {start_filter}
    ORDER BY f.id DESC
    LIMIT ? OFFSET ?
    """
    cur = conn.execute(
        sql,
        candidate_params
        + params
        + seen_params
        + start_params
        + [batch, max(0, int(offset or 0))],
    )
    return list(cur.fetchall())


def _candidate_filter_sql(
    site_filter: Optional[str],
    retry_errors: bool,
    category_filter: Optional[str] = None,
) -> tuple[str, list[object], str]:
    filters: list[str] = []
    params: list[object] = []

    if site_filter:
        sites = [s.strip().lower() for s in site_filter.split(",") if s.strip()]
        if sites:
            filters.append("(" + " OR ".join(["LOWER(f.source_site) LIKE ?"] * len(sites)) + ")")
            params.extend([f"%{s}%" for s in sites])

    category_name = str(category_filter or "").strip()
    if category_name:
        filters.append(
            "(c.category = ? OR c.category LIKE ? OR c.category LIKE ? OR c.category LIKE ?)"
        )
        params.extend(
            [
                category_name,
                f"{category_name};%",
                f"%; {category_name}",
                f"%; {category_name};%",
            ]
        )

    where_extra = (" AND " + " AND ".join(filters)) if filters else ""
    status_cond = "OR c.status = 'error'" if retry_errors else ""
    return where_extra, params, status_cond


def _count_candidates(
    conn: sqlite3.Connection,
    *,
    site_filter: Optional[str],
    category_filter: Optional[str] = None,
    catalog_version: str,
    retry_errors: bool = False,
    skip_existing: bool = True,
) -> int:
    where_extra, params, status_cond = _candidate_filter_sql(
        site_filter, retry_errors, category_filter
    )
    candidate_pred = ""
    candidate_params: list[object] = []
    if skip_existing:
        candidate_pred = f"""
        AND (
            c.file_url IS NULL
            OR c.file_sha256 IS NULL
            OR c.file_sha256 != f.sha256
            OR c.catalog_version != ?
            OR TRIM(IFNULL(c.summary, '')) = ''
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
        AND f.deleted_at IS NULL
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
    storage: Storage | None = None,
    suggested_title: str | None = None,
) -> None:
    """Upsert catalog item with thread-safe locking.

    Uses _db_lock to prevent concurrent write conflicts with SQLite.
    """
    with _db_lock:
        write_conn = storage._conn if storage is not None else conn
        existing = _table_columns(write_conn, "catalog_items")
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
        if storage is None:
            write_conn.execute(sql, values)
            if suggested_title:
                write_conn.execute(
                    "UPDATE files SET title = ? WHERE url = ?",
                    (suggested_title, item.url),
                )
            write_conn.commit()
            return

        file_url = str(item.url or "")
        with storage.transaction(immediate=True):
            before = storage._ready_data_builder_metadata_snapshot(file_url)
            write_conn.execute(sql, values)
            if suggested_title:
                write_conn.execute(
                    "UPDATE files SET title = ? WHERE url = ?",
                    (suggested_title, file_url),
                )
            storage._mark_ready_data_builder_metadata_change(
                file_url=file_url,
                before=before,
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
    catalog_model: str | None = None,
    catalog_api_key: str | None = None,
    catalog_base_url: str | None = None,
    input_source: str,
    catalog_system_prompt: str | None = None,
    output_language: str = "auto",
) -> tuple[dict, CatalogItem, str, str | None]:
    """Process a single row in a worker thread.
    Returns: (row_data, result_item, status, suggested_title)
    suggested_title is only populated when the OpenAI provider returns one.
    """
    file_url = row_data["url"]
    title = row_data["title"]
    source_site = row_data["source_site"]
    original_filename = row_data["original_filename"]
    local_path = row_data["local_path"]
    suggested_title: str | None = None
    failure_code = "catalog_failed"

    try:
        provider_norm = (provider or "local").strip().lower()
        from .ai_runtime import is_catalog_provider_supported

        if provider_norm != "local" and not is_catalog_provider_supported(provider_norm):
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
            if not resolved_path.exists():
                failure_code = "file_not_found"
                raise FileNotFoundError
            text = extract_text(resolved_path, max_chars=max_chars)
        if not text.strip():
            raise RuntimeError("empty extracted text")

        if provider_norm == "local":
            keywords = extract_keywords(text, title=title)

            if ai_only and not is_ai_related(text, keywords, title=title):
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
                return (row_data, item, "skipped", None)

            summary = summarize(text, keywords)
            category = categorize(title, text, keywords)
        else:
            from .catalog_llm import catalog_with_openai

            llm = catalog_with_openai(
                title=title,
                content=text,
                custom_system_prompt=catalog_system_prompt,
                output_language=output_language,
                provider=provider_norm,
                model=catalog_model,
                api_key=catalog_api_key,
                base_url=catalog_base_url,
            )
            keywords = llm.keywords
            suggested_title = llm.suggested_title

            if ai_only and not is_ai_related(text, keywords, title=title):
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
                return (row_data, item, "skipped", None)

            summary = llm.summary
            category = llm.category

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
        return (row_data, item, "ok", suggested_title)

    except Exception:
        # Return error item
        item = CatalogItem(
            source_site=source_site,
            title=title,
            original_filename=original_filename,
            url=file_url,
            local_path=local_path,
            keywords=[],
            summary="",
            category="",
        )
        return (row_data, item, f"error:{failure_code}", None)


def run_incremental_catalog(
    db_path: str,
    out_jsonl: Path,
    out_md: Path,
    batch: int = 200,
    site_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
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
    update_title: bool = False,
    catalog_system_prompt: str | None = None,
    output_language: str = "auto",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
    task_id: str | None = None,
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
        update_title: If True, update files.title with the AI-suggested title
        catalog_system_prompt: Optional system prompt override for the LLM cataloger.
        output_language: Language for LLM output (``"auto"``, ``"en"``, ``"zh"``).

    Returns:
        dict with stats: {scanned, processed, written, skipped_ai, errors}
    """
    storage = Storage(db_path)
    conn = storage._conn
    conn.row_factory = sqlite3.Row
    _ensure_catalog_schema(conn)
    conn.commit()
    provider_norm = (provider or "local").strip().lower()
    catalog_model: str | None = None
    catalog_api_key: str | None = None
    catalog_base_url: str | None = None
    if provider_norm != "local":
        from .ai_runtime import is_catalog_provider_supported, resolve_ai_function_runtime

        if not is_catalog_provider_supported(provider_norm):
            storage.close()
            raise RuntimeError(f"unsupported catalog provider: {provider}")

        runtime_storage = Storage(db_path)
        try:
            runtime = resolve_ai_function_runtime(
                "catalog",
                storage=runtime_storage,
                provider_override=provider_norm,
            )
        finally:
            runtime_storage.close()

        provider = runtime.provider
        catalog_model = runtime.model
        catalog_api_key = runtime.api_key
        catalog_base_url = runtime.base_url

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
        "failed_items": 0,
        "item_errors": [],
        "item_errors_truncated": False,
        "stopped": False,
        "candidate_exhausted": False,
        "target_successes": max(0, int(limit or 0)),
    }
    failed_object_ids: set[str] = set()

    def record_failure(code: str, file_url: str) -> None:
        if record_item_error(
            stats["item_errors"],
            failed_object_ids,
            "catalog",
            code,
            file_url,
            task_id=task_id,
        ):
            stats["failed_items"] += 1
        stats["item_errors_truncated"] = stats["failed_items"] > len(stats["item_errors"])

    candidate_offset = max(0, int(candidate_offset or 0))
    seen_urls: set[str] = set()
    candidate_count = _count_candidates(
        conn,
        site_filter=site_filter,
        category_filter=category_filter,
        catalog_version=catalog_version,
        retry_errors=retry_errors,
        skip_existing=skip_existing,
    )
    if candidate_offset > 0:
        candidate_count = max(0, candidate_count - int(candidate_offset))
        start_rows = _fetch_candidates(
            conn,
            batch=1,
            offset=candidate_offset,
            site_filter=site_filter,
            category_filter=category_filter,
            catalog_version=catalog_version,
            retry_errors=retry_errors,
            skip_existing=skip_existing,
        )
        candidate_start_id = int(start_rows[0]["id"]) if start_rows else None
    else:
        candidate_start_id = None
    progress_total = max(limit if limit > 0 else candidate_count, 1)
    if progress_callback:
        progress_callback(
            0,
            progress_total,
            f"Catalog candidates: {candidate_count}; target successes: {limit or candidate_count}",
        )

    while True:
        if stop_check and stop_check():
            logger.info("Catalog stop requested before next batch")
            stats["stopped"] = True
            break

        if limit > 0 and stats["processed"] >= limit:
            logger.info(f"Reached limit of {limit} items")
            break

        if candidate_offset > 0 and candidate_start_id is None:
            stats["candidate_exhausted"] = True
            break

        current_batch_size = max(1, int(batch or 1))
        if limit > 0:
            current_batch_size = min(current_batch_size, limit - stats["processed"])

        rows = _fetch_candidates(
            conn,
            batch=current_batch_size,
            seen_urls=seen_urls,
            max_id=candidate_start_id,
            site_filter=site_filter,
            category_filter=category_filter,
            catalog_version=catalog_version,
            retry_errors=retry_errors,
            skip_existing=skip_existing,
        )
        if not rows:
            stats["candidate_exhausted"] = True
            break

        stats["scanned"] += len(rows)
        batch_items: list[CatalogItem] = []
        batch_jsonl: list[dict] = []

        # Convert sqlite rows to dicts for thread safety (sqlite3.Row might bind to thread?)
        row_dicts = [dict(r) for r in rows]

        # Mark as seen
        for r in row_dicts:
            seen_urls.add(r["url"])

        stop_requested = False
        shutdown_without_wait = False
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            future_to_url = {}
            for r in row_dicts:
                if stop_check and stop_check():
                    logger.info("Catalog stop requested before submitting more items")
                    stats["stopped"] = True
                    stop_requested = True
                    if future_to_url:
                        executor.shutdown(wait=False, cancel_futures=True)
                        shutdown_without_wait = True
                    break
                future = executor.submit(
                    _process_single_row,
                    r,
                    ai_only,
                    max_chars,
                    db_path=db_path,
                    provider=provider,
                    catalog_model=catalog_model,
                    catalog_api_key=catalog_api_key,
                    catalog_base_url=catalog_base_url,
                    input_source=input_source,
                    catalog_system_prompt=catalog_system_prompt,
                    output_language=output_language,
                )
                future_to_url[future] = r["url"]

            # We will batch writes at the end of the batch processing to keep DB logic simple
            # Or writing as they complete? Batch write is safer for transaction.

            for future in as_completed(future_to_url):
                if stop_check and stop_check():
                    logger.info("Catalog stop requested while workers are running")
                    stats["stopped"] = True
                    stop_requested = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    shutdown_without_wait = True
                    break
                url = future_to_url[future]
                try:
                    r_data, item, status, suggested_title = future.result()
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
                            storage=storage,
                            suggested_title=(suggested_title if update_title else None),
                        )
                        if progress_callback:
                            progress_callback(
                                stats["processed"],
                                progress_total,
                                (
                                    f"Cataloging successes={stats['processed']}/"
                                    f"{limit or candidate_count} "
                                    f"checked={stats['scanned']} failed={stats['errors']} "
                                    f"skipped={stats['skipped_ai']}"
                                ),
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
                            storage=storage,
                        )
                        if progress_callback:
                            progress_callback(
                                stats["processed"],
                                progress_total,
                                (
                                    f"Cataloging successes={stats['processed']}/"
                                    f"{limit or candidate_count} "
                                    f"checked={stats['scanned']} failed={stats['errors']} "
                                    f"skipped={stats['skipped_ai']}"
                                ),
                            )

                    elif status.startswith("error:"):
                        stats["errors"] += 1
                        error_code = (
                            "file_not_found" if status[6:] == "file_not_found" else "catalog_failed"
                        )
                        if len(stats["error_samples"]) < 20:
                            stats["error_samples"].append(error_code)
                        if error_code == "file_not_found":
                            stats["missing_files"] += 1
                        record_failure(error_code, str(r_data["url"]))

                        logger.warning("Catalog item failed: %s", error_code)
                        _upsert_catalog_row(
                            conn,
                            item=item,
                            file_sha256=file_sha256,
                            catalog_version=catalog_version,
                            status="error",
                            processed_at=processed_at,
                            error=error_code,
                            storage=storage,
                        )
                        if progress_callback:
                            progress_callback(
                                stats["processed"],
                                progress_total,
                                (
                                    f"Cataloging successes={stats['processed']}/"
                                    f"{limit or candidate_count} "
                                    f"checked={stats['scanned']} failed={stats['errors']} "
                                    f"skipped={stats['skipped_ai']}"
                                ),
                            )

                except Exception:
                    logger.error("Catalog worker failed: catalog_failed")
                    stats["errors"] += 1
                    if len(stats["error_samples"]) < 20:
                        stats["error_samples"].append("catalog_failed")
                    record_failure("catalog_failed", str(url))
        finally:
            if not shutdown_without_wait:
                executor.shutdown(wait=True)

        # Append outputs incrementally
        if batch_items:
            _append_jsonl(out_jsonl, batch_jsonl)
            write_catalog_md(out_md, batch_items, append=out_md.exists())
            stats["written"] += len(batch_items)
        if stop_requested:
            break

        logger.info(
            "Batch done: scanned=%d processed=%d written=%d skipped_ai=%d errors=%d missing=%d",
            len(rows),
            stats["processed"],
            stats["written"],
            stats["skipped_ai"],
            stats["errors"],
            stats["missing_files"],
        )

    storage.close()
    logger.info(
        "Incremental catalog finished: scanned=%d processed=%d written=%d skipped_ai=%d errors=%d missing=%d",
        stats["scanned"],
        stats["processed"],
        stats["written"],
        stats["skipped_ai"],
        stats["errors"],
        stats["missing_files"],
    )
    if progress_callback:
        if stats["stopped"]:
            progress_callback(
                stats["processed"],
                progress_total,
                (
                    f"Catalog stopped: successes={stats['processed']}/"
                    f"{limit or candidate_count} "
                    f"checked={stats['scanned']} "
                    f"skipped={stats['skipped_ai']} errors={stats['errors']}"
                ),
            )
            return stats
        progress_callback(
            stats["processed"],
            progress_total,
            (
                f"Catalog finished: successes={stats['processed']}/"
                f"{limit or candidate_count} "
                f"checked={stats['scanned']} failed={stats['errors']} "
                f"skipped={stats['skipped_ai']}"
                f"{'; candidates exhausted' if stats['candidate_exhausted'] else ''}"
            ),
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
    update_title: bool = False,
    catalog_system_prompt: str | None = None,
    output_language: str = "auto",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
    task_id: str | None = None,
) -> dict:
    """Catalog a specific list of file URLs (used by File Details actions)."""
    storage = Storage(db_path)
    conn = storage._conn
    conn.row_factory = sqlite3.Row
    _ensure_catalog_schema(conn)
    conn.commit()
    provider_norm = (provider or "local").strip().lower()
    catalog_model: str | None = None
    catalog_api_key: str | None = None
    catalog_base_url: str | None = None
    if provider_norm != "local":
        from .ai_runtime import is_catalog_provider_supported, resolve_ai_function_runtime

        if not is_catalog_provider_supported(provider_norm):
            storage.close()
            raise RuntimeError(f"unsupported catalog provider: {provider}")

        runtime_storage = Storage(db_path)
        try:
            runtime = resolve_ai_function_runtime(
                "catalog",
                storage=runtime_storage,
                provider_override=provider_norm,
            )
        finally:
            runtime_storage.close()

        provider = runtime.provider
        catalog_model = runtime.model
        catalog_api_key = runtime.api_key
        catalog_base_url = runtime.base_url

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
        "failed_items": 0,
        "item_errors": [],
        "item_errors_truncated": False,
        "stopped": False,
    }
    failed_object_ids: set[str] = set()

    def record_failure(code: str, file_url: str) -> None:
        if record_item_error(
            stats["item_errors"],
            failed_object_ids,
            "catalog",
            code,
            file_url,
            task_id=task_id,
        ):
            stats["failed_items"] += 1
        stats["item_errors_truncated"] = stats["failed_items"] > len(stats["item_errors"])

    urls = [u for u in (file_urls or []) if isinstance(u, str) and u.strip()]
    urls = [u.strip() for u in urls]
    if not urls:
        storage.close()
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
            c.status AS c_status,
            c.summary AS c_summary
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
                stats["error_samples"].append("file_not_found")
            stats["missing_files"] += 1
            record_failure("file_not_found", u)

    def is_candidate(r: dict) -> bool:
        if not skip_existing:
            return True
        c_url = r.get("c_url")
        c_sha = (r.get("c_sha256") or "").strip()
        c_ver = (r.get("c_version") or "").strip()
        c_status = (r.get("c_status") or "").strip()
        c_summary = (r.get("c_summary") or "").strip()
        f_sha = (r.get("sha256") or "").strip()
        return (
            (c_url is None)
            or (not c_sha)
            or (c_sha != f_sha)
            or (c_ver != catalog_version)
            or (not c_summary)
            or (retry_errors and c_status == "error")
        )

    candidates = [r for r in ordered_rows if is_candidate(r)]
    stats["scanned"] = len(candidates)

    if progress_callback:
        progress_callback(0, max(len(candidates), 1), f"Catalog candidates: {len(candidates)}")

    batch_items: list[CatalogItem] = []
    batch_jsonl: list[dict] = []

    stop_requested = False
    shutdown_without_wait = False
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_url = {}
        for r in candidates:
            if stop_check and stop_check():
                logger.info("Catalog stop requested before submitting more explicit file URLs")
                stats["stopped"] = True
                stop_requested = True
                if future_to_url:
                    executor.shutdown(wait=False, cancel_futures=True)
                    shutdown_without_wait = True
                break
            future = executor.submit(
                _process_single_row,
                r,
                ai_only,
                max_chars,
                db_path=db_path,
                provider=provider,
                catalog_model=catalog_model,
                catalog_api_key=catalog_api_key,
                catalog_base_url=catalog_base_url,
                input_source=input_source,
                catalog_system_prompt=catalog_system_prompt,
                output_language=output_language,
            )
            future_to_url[future] = r["url"]
        for future in as_completed(future_to_url):
            if stop_check and stop_check():
                logger.info("Catalog stop requested while explicit file URL workers are running")
                stats["stopped"] = True
                stop_requested = True
                executor.shutdown(wait=False, cancel_futures=True)
                shutdown_without_wait = True
                break
            url = future_to_url[future]
            try:
                r_data, item, status, suggested_title = future.result()
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
                        storage=storage,
                        suggested_title=(suggested_title if update_title else None),
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
                        storage=storage,
                    )
                elif status.startswith("error:"):
                    stats["errors"] += 1
                    error_code = (
                        "file_not_found" if status[6:] == "file_not_found" else "catalog_failed"
                    )
                    if len(stats["error_samples"]) < 20:
                        stats["error_samples"].append(error_code)
                    if error_code == "file_not_found":
                        stats["missing_files"] += 1
                    record_failure(error_code, str(r_data["url"]))
                    _upsert_catalog_row(
                        conn,
                        item=item,
                        file_sha256=file_sha256,
                        catalog_version=catalog_version,
                        status="error",
                        processed_at=processed_at,
                        error=error_code,
                        storage=storage,
                    )
                if progress_callback:
                    completed = stats["processed"] + stats["skipped_ai"] + stats["errors"]
                    progress_callback(
                        completed,
                        max(len(candidates), completed, 1),
                        f"Cataloging {completed}/{max(len(candidates), 1)}",
                    )
            except Exception:
                logger.error("Catalog worker failed: catalog_failed")
                stats["errors"] += 1
                if len(stats["error_samples"]) < 20:
                    stats["error_samples"].append("catalog_failed")
                record_failure("catalog_failed", str(url))
    finally:
        if not shutdown_without_wait:
            executor.shutdown(wait=True)
    if stop_requested:
        logger.info("Catalog processing stopped for explicit file URL run")

    if batch_items:
        _append_jsonl(out_jsonl, batch_jsonl)
        write_catalog_md(out_md, batch_items, append=out_md.exists())
        stats["written"] += len(batch_items)

    storage.close()
    if progress_callback:
        completed = stats["processed"] + stats["skipped_ai"] + stats["errors"]
        if stats["stopped"]:
            progress_callback(
                completed,
                max(len(candidates), completed, 1),
                (
                    f"Catalog stopped: processed={stats['processed']} "
                    f"skipped={stats['skipped_ai']} errors={stats['errors']}"
                ),
            )
            return stats
        progress_callback(
            max(len(candidates), completed, 1),
            max(len(candidates), completed, 1),
            f"Catalog finished: processed={stats['processed']} skipped={stats['skipped_ai']} errors={stats['errors']}",
        )
    return stats

"""
Task-related service layer.

Contains SQL query patterns and task operations extracted from ops_read.py
and ops_write.py for better code organization and reduced duplication.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ai_actuarial.shared_runtime import (
    get_sites_config_path,
    load_yaml,
    parse_int_clamped,
    tail_text_file,
    task_log_path,
)
from ai_actuarial.storage import Storage


# ---------------------------------------------------------------------------
# Task query helpers (from ops_read.py)
# ---------------------------------------------------------------------------


def _task_error_count(task_data: dict[str, Any]) -> int:
    errors = task_data.get("errors")
    if isinstance(errors, list):
        return len(errors)
    count = task_data.get("error_count")
    try:
        return int(count or 0)
    except Exception:
        return 0


def _task_metric(label_key: str, label_fallback: str, value: Any) -> dict[str, Any]:
    return {"label_key": label_key, "label_fallback": label_fallback, "value": value}


def _build_task_display_summary(task_data: dict[str, Any]) -> dict[str, Any]:
    task_type = str(task_data.get("type") or "")
    items_processed = int(task_data.get("items_processed") or 0)
    items_downloaded = int(task_data.get("items_downloaded") or 0)
    items_skipped = int(task_data.get("items_skipped") or 0)
    error_count = _task_error_count(task_data)

    if task_type == "catalog":
        primary = _task_metric("tasks.metric_cataloged", "Cataloged", task_data.get("catalog_ok", items_processed))
        secondary = [
            _task_metric("tasks.metric_errors", "Errors", error_count),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
        ]
    elif task_type in {"markdown", "markdown_conversion"}:
        primary = _task_metric("tasks.metric_converted", "Converted", items_downloaded or items_processed)
        secondary = [
            _task_metric("tasks.metric_errors", "Errors", error_count),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
        ]
    elif task_type in {"chunk", "chunk_generation"}:
        primary = _task_metric("tasks.metric_chunked", "Chunked", items_downloaded or items_processed)
        secondary = [
            _task_metric("tasks.metric_errors", "Errors", error_count),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
        ]
    elif task_type in {"search", "url", "file", "scheduled", "adhoc", "quick_check"}:
        primary = _task_metric("tasks.metric_found", "Found", items_processed)
        secondary = [
            _task_metric("tasks.metric_downloaded", "Downloaded", items_downloaded),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
            _task_metric("tasks.metric_errors", "Errors", error_count),
        ]
    else:
        primary = _task_metric("tasks.metric_processed", "Processed", items_processed)
        secondary = [
            _task_metric("tasks.metric_completed", "Completed", items_downloaded),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
            _task_metric("tasks.metric_errors", "Errors", error_count),
        ]
    return {"primary": primary, "secondary": secondary, "error_count": error_count}


def _serialize_task_for_api(task_data: dict[str, Any]) -> dict[str, Any]:
    row = dict(task_data)
    row["error_count"] = _task_error_count(row)
    row["display_summary"] = _build_task_display_summary(row)
    return row


def list_active_tasks(active_tasks_ref: dict[str, dict[str, Any]], task_lock: Any) -> dict[str, list[dict[str, Any]]]:
    if task_lock is None:
        tasks = [_serialize_task_for_api(task) for task in active_tasks_ref.values()]
    else:
        with task_lock:
            tasks = [_serialize_task_for_api(task) for task in active_tasks_ref.values()]
    return {"tasks": tasks}


def list_task_history(task_history_ref: list[dict[str, Any]], limit: int) -> dict[str, list[dict[str, Any]]]:
    tasks = [
        _serialize_task_for_api(task)
        for task in sorted(task_history_ref, key=lambda x: x.get("started_at", ""), reverse=True)[:limit]
    ]
    return {"tasks": tasks}


def get_task_log(task_id: str, tail: int) -> dict[str, Any]:
    """Read the log file for a task, returning the last `tail` lines."""
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", task_id or "")
    if not safe_id:
        raise ValueError("Invalid task id")
    path = task_log_path(safe_id)
    content = tail_text_file(path, max_lines=tail)
    if not content:
        return {"success": True, "log": "", "log_file": str(path)}
    return {"success": True, "log": content, "log_file": str(path)}


def parse_task_history_limit(raw_value: str | None) -> int:
    return parse_int_clamped(raw_value or "10", default=10, min_value=1, max_value=200)


def parse_task_log_tail(raw_value: str | None) -> int:
    return parse_int_clamped(raw_value or "400", default=400, min_value=1, max_value=5000)


# ---------------------------------------------------------------------------
# Schedule / site task helpers (from ops_read.py)
# ---------------------------------------------------------------------------


def get_schedule_status(schedule_ref: Any) -> dict[str, object]:
    jobs = []
    for job in list(getattr(schedule_ref, "jobs", []) or []):
        next_run = job.next_run.isoformat() if getattr(job, "next_run", None) else None
        last_run = job.last_run.isoformat() if getattr(job, "last_run", None) else None
        unit = getattr(job, "unit", None) or ""
        interval = getattr(job, "interval", None)
        at_time = getattr(job, "at_time", None)
        at_str = at_time.strftime("%H:%M") if at_time else None
        if unit == "days" and interval == 1 and at_str:
            label = f"daily at {at_str}"
        elif unit == "weeks" and interval == 1 and at_str:
            label = f"weekly on {getattr(job, 'start_day', 'monday')} at {at_str}"
        elif interval and unit:
            label = f"every {interval} {unit}"
            if at_str:
                label += f" at {at_str}"
        else:
            label = str(job)
        jobs.append({"label": label, "next_run": next_run, "last_run": last_run})
    return {"jobs": jobs, "count": len(jobs)}


def get_scheduled_tasks() -> dict[str, list[dict[str, Any]]]:
    config_path = get_sites_config_path()
    config_data = load_yaml(config_path, default={})
    tasks = config_data.get("scheduled_tasks") or []
    return {"tasks": tasks if isinstance(tasks, list) else []}


# ---------------------------------------------------------------------------
# Catalog / file stats helpers (from ops_write.py)
# ---------------------------------------------------------------------------


def get_catalog_stats(
    *,
    db_path: str,
    provider: str | None = None,
    input_source: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Return aggregated catalog statistics from the database."""
    storage = Storage(db_path)
    try:
        filters, params = _build_catalog_stats_filters(provider, input_source, category)
        where_clause = f"WHERE {filters}" if filters else ""
        total = storage._conn.execute(f"SELECT COUNT(*) FROM catalog_items c {where_clause}", params).fetchone()[0]
        total_ok = storage._conn.execute(
            f"SELECT COUNT(*) FROM catalog_items c WHERE c.status = 'ok' {filters.replace('WHERE', 'AND') if filters else ''}",
            params,
        ).fetchone()[0]

        cursor = storage._conn.execute(
            f"""
            SELECT
                c.category,
                COUNT(*) as cnt,
                SUM(CASE WHEN c.status = 'ok' THEN 1 ELSE 0 END) as ok_count,
                SUM(CASE WHEN c.status != 'ok' THEN 1 ELSE 0 END) as error_count
            FROM catalog_items c
            {where_clause}
            GROUP BY c.category
            ORDER BY cnt DESC
            """,
            params,
        )
        by_category = [
            {
                "category": row[0] or "(none)",
                "total": row[1],
                "ok": row[2],
                "errors": row[3],
            }
            for row in cursor.fetchall()
        ]

        return {"total": total, "ok": total_ok, "errors": total - total_ok, "by_category": by_category}
    finally:
        storage.close()


def _build_catalog_stats_filters(
    provider: str | None,
    input_source: str | None,
    category: str | None,
) -> tuple[str, list[Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if provider:
        filters.append("c.category LIKE ?")
        params.append(f"%{provider}%")
    if input_source:
        filters.append("EXISTS (SELECT 1 FROM files f WHERE f.url = c.file_url AND f.source_site LIKE ?)")
        params.append(f"%{input_source}%")
    if category:
        filters.append("c.category = ?")
        params.append(category)
    return (" AND ".join(filters), params)


def get_markdown_conversion_stats(*, db_path: str, category: str | None = None) -> dict[str, Any]:
    """Return markdown conversion statistics."""
    storage = Storage(db_path)
    try:
        alias = "c"
        sql_where, params = _category_sql(category, alias=alias)
        total = storage._conn.execute(
            f"""
            SELECT COUNT(*)
            FROM catalog_items {alias}
            {sql_where}
            """,
            params,
        ).fetchone()[0]

        has_md_filter = ""
        has_md_params: list[Any] = []
        if category:
            has_md_filter = f" AND {alias}.category = ?"
            has_md_params = [category]

        has_md = storage._conn.execute(
            f"""
            SELECT COUNT(*)
            FROM catalog_items {alias}
            WHERE {alias}.markdown_content IS NOT NULL
              AND {alias}.markdown_content != ''
            {has_md_filter}
            """,
            has_md_params,
        ).fetchone()[0]

        missing_md = total - has_md
        sources_filter = "c.category" if category else "f.source_site"
        rows = storage._conn.execute(
            f"""
            SELECT
                {sources_filter} AS label,
                COUNT(*) AS total,
                SUM(CASE WHEN c.markdown_content IS NOT NULL AND c.markdown_content != '' THEN 1 ELSE 0 END) AS with_md,
                SUM(CASE WHEN c.markdown_content IS NULL OR c.markdown_content = '' THEN 1 ELSE 0 END) AS missing_md
            FROM catalog_items c
            LEFT JOIN files f ON f.url = c.file_url
            WHERE c.category IS NOT NULL
            GROUP BY {sources_filter}
            ORDER BY total DESC
            LIMIT 20
            """,
        ).fetchall()

        by_source = [
            {
                "label": row[0] or "(none)",
                "total": row[1],
                "with_md": row[2],
                "missing_md": row[3],
            }
            for row in rows
        ]
        return {
            "total": total,
            "with_markdown": has_md,
            "missing_markdown": missing_md,
            "by_source": by_source,
        }
    finally:
        storage.close()


def get_chunk_generation_stats(*, db_path: str, category: str | None = None) -> dict[str, Any]:
    """Return chunk generation statistics."""
    storage = Storage(db_path)
    try:
        sql_where, params = _category_sql(category, alias="c")
        total = storage._conn.execute(
            f"SELECT COUNT(*) FROM catalog_items c {sql_where}",
            params,
        ).fetchone()[0]

        chunked = storage._conn.execute(
            f"""
            SELECT COUNT(DISTINCT c.file_url)
            FROM catalog_items c
            LEFT JOIN file_chunk_sets s ON s.file_url = c.file_url
            {sql_where}
            AND s.chunk_set_id IS NOT NULL
            """,
            params,
        ).fetchone()[0]

        pending = total - chunked
        by_source_rows = storage._conn.execute(
            f"""
            SELECT
                COALESCE(f.source_site, '(none)') AS label,
                COUNT(DISTINCT c.file_url) AS total,
                COUNT(DISTINCT s.chunk_set_id) AS chunked,
                COALESCE(SUM(s.chunk_count), 0) AS total_chunks
            FROM catalog_items c
            LEFT JOIN files f ON f.url = c.file_url
            LEFT JOIN file_chunk_sets s ON s.file_url = c.file_url
            WHERE c.category IS NOT NULL
            GROUP BY COALESCE(f.source_site, '(none)')
            ORDER BY total DESC
            LIMIT 20
            """,
        ).fetchall()

        by_source = [
            {
                "label": row[0],
                "total": row[1],
                "chunked": row[2],
                "pending": row[1] - row[2],
                "total_chunks": row[3],
            }
            for row in by_source_rows
        ]
        return {
            "total": total,
            "chunked": chunked,
            "pending": pending,
            "by_source": by_source,
        }
    finally:
        storage.close()


def _category_sql(category_filter: str, *, alias: str = "c") -> tuple[str, list[Any]]:
    """Build WHERE clause for category filter."""
    if not category_filter:
        return ("", [])
    return (f"WHERE {alias}.category = ?", [category_filter])


# ---------------------------------------------------------------------------
# File catalog queries (from ops_read.py)
# ---------------------------------------------------------------------------


def get_file_catalog_stats(db_path: str) -> dict[str, Any]:
    """Return file-level catalog statistics."""
    storage = Storage(db_path)
    try:
        file_count = storage.get_file_count(require_local=True)
        cataloged_count = storage.get_cataloged_count()
        sources_count = storage.get_sources_count()
        unique_categories = storage.get_unique_categories()
        return {
            "file_count": file_count,
            "cataloged_count": cataloged_count,
            "sources_count": sources_count,
            "unique_categories": unique_categories,
        }
    finally:
        storage.close()

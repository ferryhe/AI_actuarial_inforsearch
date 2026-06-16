from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ai_actuarial.shared_runtime import parse_int_clamped
from ai_actuarial.storage import Storage

WEEKLY_UPDATE_FILE_FIELDS: tuple[str, ...] = (
    "url",
    "title",
    "source_site",
    "source_page_url",
    "original_filename",
    "bytes",
    "content_type",
    "published_time",
    "first_seen",
    "last_seen",
    "summary",
    "category",
    "keywords",
)


def current_utc_iso_week_period(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    start = (current - timedelta(days=current.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


def parse_weekly_update_list_query(raw_query: Mapping[str, str | None]) -> dict[str, int]:
    return {
        "limit": parse_int_clamped(raw_query.get("limit", 20), default=20, min_value=1, max_value=100),
        "offset": parse_int_clamped(raw_query.get("offset", 0), default=0, min_value=0, max_value=1_000_000),
    }


def _project_weekly_file(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in WEEKLY_UPDATE_FILE_FIELDS}


def _format_summary_markdown(*, period_start: str, period_end: str, files: list[dict[str, Any]]) -> str:
    lines = [
        f"# Weekly Updates ({period_start} to {period_end})",
        "",
        f"New files: {len(files)}",
    ]
    if not files:
        return "\n".join(lines) + "\n"

    lines.extend(["", "## New Files"])
    for file_row in files:
        title = str(file_row.get("title") or file_row.get("original_filename") or file_row.get("url") or "Untitled")
        url = str(file_row.get("url") or "")
        source = str(file_row.get("source_site") or "")
        first_seen = str(file_row.get("first_seen") or "")
        suffix = f" ({source})" if source else ""
        lines.append(f"- [{title}]({url}){suffix} — first seen {first_seen}")
    return "\n".join(lines) + "\n"


def generate_weekly_update_summary(
    *,
    db_path: str,
    period_start: str | None = None,
    period_end: str | None = None,
    max_files: int = 500,
) -> dict[str, Any]:
    if not period_start or not period_end:
        default_start, default_end = current_utc_iso_week_period()
        period_start = period_start or default_start
        period_end = period_end or default_end

    storage = Storage(db_path)
    try:
        files = [
            _project_weekly_file(row)
            for row in storage.list_files_first_seen_between(
                period_start=period_start,
                period_end=period_end,
                limit=max(1, int(max_files or 500)),
            )
        ]
        summary = {
            "period_start": period_start,
            "period_end": period_end,
            "file_count": len(files),
            "files": files,
            "summary_markdown": _format_summary_markdown(
                period_start=period_start,
                period_end=period_end,
                files=files,
            ),
            "metadata": {
                "logic": "files.first_seen >= period_start AND files.first_seen < period_end",
                "content_change_detection": False,
            },
        }
        stored = storage.upsert_weekly_update_summary(summary)
    finally:
        storage.close()
    return stored


def list_weekly_update_summaries(*, db_path: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        summaries, total = storage.list_weekly_update_summaries(limit=limit, offset=offset)
    finally:
        storage.close()
    return {"summaries": summaries, "total": total, "limit": limit, "offset": offset}


def get_latest_weekly_update_summary(*, db_path: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        summary = storage.get_latest_weekly_update_summary()
    finally:
        storage.close()
    return {"summary": summary}

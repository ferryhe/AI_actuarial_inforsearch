from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ai_actuarial.shared_runtime import coerce_bool, parse_int_clamped
from ai_actuarial.storage import Storage

_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
WEEKLY_UPDATE_FILE_FIELDS: tuple[str, ...] = (
    "url",
    "title",
    "original_filename",
    "first_seen",
    "summary",
    "category",
    "keywords",
)


class WeeklySnapshotValidationError(ValueError):
    pass


class WeeklySnapshotNotFoundError(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class WeeklySnapshotPeriod:
    period_start: str
    period_end: str
    relative_period: str | None


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_iso_week_period(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    start = (current - timedelta(days=current.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


def previous_utc_iso_week_period(now: datetime | None = None) -> tuple[str, str]:
    current_start, _current_end = current_utc_iso_week_period(now)
    end = datetime.fromisoformat(current_start)
    start = end - timedelta(days=7)
    return start.isoformat(), end.isoformat()


def _parse_rfc3339(value: str, *, field: str) -> datetime:
    text = str(value or "").strip()
    if not _RFC3339_RE.fullmatch(text):
        raise WeeklySnapshotValidationError(f"{field} must be a timezone-aware RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(
            text.replace("t", "T").replace("z", "+00:00").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise WeeklySnapshotValidationError(
            f"{field} must be a timezone-aware RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WeeklySnapshotValidationError(f"{field} must be a timezone-aware RFC3339 timestamp")
    return parsed.astimezone(timezone.utc)


def validate_weekly_snapshot_period(
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    relative_period: str | None = None,
    now: datetime | None = None,
) -> WeeklySnapshotPeriod:
    start_text = str(period_start or "").strip()
    end_text = str(period_end or "").strip()
    relative_text = str(relative_period or "").strip()
    has_explicit = bool(start_text or end_text)
    if relative_text and has_explicit:
        raise WeeklySnapshotValidationError(
            "Choose relative_period or period_start/period_end, not both"
        )
    if relative_text:
        if relative_text != "previous_week":
            raise WeeklySnapshotValidationError("relative_period must be exactly 'previous_week'")
        start, end = previous_utc_iso_week_period(now)
        return WeeklySnapshotPeriod(start, end, "previous_week")
    if not start_text and not end_text:
        raise WeeklySnapshotValidationError(
            "Provide relative_period='previous_week' or both period_start and period_end"
        )
    if not start_text or not end_text:
        raise WeeklySnapshotValidationError("period_start and period_end must be provided together")
    start = _parse_rfc3339(start_text, field="period_start")
    end = _parse_rfc3339(end_text, field="period_end")
    if start >= end:
        raise WeeklySnapshotValidationError("period_start must be before period_end")
    return WeeklySnapshotPeriod(_utc_iso(start), _utc_iso(end), None)


def parse_weekly_update_list_query(raw_query: Mapping[str, str | None]) -> dict[str, int]:
    return {
        "limit": parse_int_clamped(
            raw_query.get("limit", 20),
            default=20,
            min_value=1,
            max_value=100,
        ),
        "offset": parse_int_clamped(
            raw_query.get("offset", 0),
            default=0,
            min_value=0,
            max_value=1_000_000,
        ),
    }


def parse_weekly_update_files_query(raw_query: Mapping[str, str | None]) -> dict[str, int]:
    return {
        "limit": parse_int_clamped(
            raw_query.get("limit", 100),
            default=100,
            min_value=1,
            max_value=500,
        ),
        "offset": parse_int_clamped(
            raw_query.get("offset", 0),
            default=0,
            min_value=0,
            max_value=1_000_000,
        ),
    }


def _project_weekly_file(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in WEEKLY_UPDATE_FILE_FIELDS}


def _format_summary_markdown(
    *,
    period_start: str,
    period_end: str,
    file_count: int,
    files: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Weekly Updates ({period_start} to {period_end})",
        "",
        f"New files: {file_count}",
    ]
    if not files:
        return "\n".join(lines) + "\n"

    lines.extend(["", "## New Files"])
    for file_row in files:
        title = str(
            file_row.get("title")
            or file_row.get("original_filename")
            or file_row.get("url")
            or "Untitled"
        )
        url = str(file_row.get("url") or "")
        first_seen = str(file_row.get("first_seen") or "")
        lines.append(f"- [{title}]({url}) — first seen {first_seen}")
    return "\n".join(lines) + "\n"


def generate_weekly_update_summary(
    *,
    db_path: str,
    storage: Storage | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    relative_period: str | None = None,
    max_files: int = 500,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    period = validate_weekly_snapshot_period(
        period_start=period_start,
        period_end=period_end,
        relative_period=relative_period,
        now=now,
    )
    preview_limit = parse_int_clamped(
        max_files,
        default=500,
        min_value=1,
        max_value=500,
    )
    force_rebuild = coerce_bool(force, default=False)
    request_started_at = _utc_now()
    active_storage = storage or Storage(db_path)
    try:
        with active_storage.transaction(immediate=True):
            existing = active_storage.get_published_weekly_snapshot_for_period(
                period_start=period.period_start,
                period_end=period.period_end,
                include_detail=True,
            )
            if existing is not None and not force_rebuild:
                stored = existing
            else:
                file_count = active_storage.count_files_first_seen_between(
                    period_start=period.period_start,
                    period_end=period.period_end,
                )
                members = active_storage.list_file_identities_first_seen_between(
                    period_start=period.period_start,
                    period_end=period.period_end,
                )
                source_preview = [
                    _project_weekly_file(row)
                    for row in active_storage.list_files_first_seen_between(
                        period_start=period.period_start,
                        period_end=period.period_end,
                        limit=preview_limit,
                    )
                ]
                summary = {
                    "period_start": period.period_start,
                    "period_end": period.period_end,
                    "file_count": file_count,
                    "summary_markdown": _format_summary_markdown(
                        period_start=period.period_start,
                        period_end=period.period_end,
                        file_count=file_count,
                        files=source_preview,
                    ),
                    "metadata": {
                        "logic": "files.first_seen >= period_start AND files.first_seen < period_end",
                        "content_change_detection": False,
                        "relative_period": period.relative_period,
                    },
                }
                stored = active_storage.publish_weekly_snapshot(
                    summary,
                    members=members,
                    force=force_rebuild,
                    request_started_at=request_started_at,
                )
            preview, total = active_storage.list_weekly_snapshot_files(
                snapshot_id=str(stored["id"]),
                limit=preview_limit,
                offset=0,
            )
    finally:
        if storage is None:
            active_storage.close()
    return {
        **stored,
        "files": preview,
        "included_count": len(preview),
        "truncated": total > len(preview),
    }


def list_weekly_update_summaries(
    *,
    db_path: str,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    query = parse_weekly_update_list_query({"limit": str(limit), "offset": str(offset)})
    storage = Storage(db_path)
    try:
        summaries, total = storage.list_weekly_snapshots(**query)
    finally:
        storage.close()
    return {"summaries": summaries, "total": total, **query}


def get_latest_weekly_update_summary(*, db_path: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        summary = storage.get_latest_weekly_snapshot(now=_utc_now())
    finally:
        storage.close()
    return {"summary": summary}


def get_weekly_update_summary_detail(
    *,
    db_path: str,
    snapshot_id: str,
) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        summary = storage.get_weekly_snapshot(
            snapshot_id=str(snapshot_id or "").strip(),
            include_detail=True,
        )
    finally:
        storage.close()
    if summary is None:
        raise WeeklySnapshotNotFoundError(snapshot_id)
    return {"summary": summary}


def get_weekly_update_summary_files(
    *,
    db_path: str,
    snapshot_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = parse_weekly_update_files_query({"limit": str(limit), "offset": str(offset)})
    storage = Storage(db_path)
    try:
        try:
            files, total = storage.list_weekly_snapshot_files(
                snapshot_id=str(snapshot_id or "").strip(),
                **query,
            )
        except KeyError as exc:
            raise WeeklySnapshotNotFoundError(snapshot_id) from exc
    finally:
        storage.close()
    included_count = len(files)
    return {
        "snapshot_id": snapshot_id,
        "files": files,
        "total": total,
        **query,
        "included_count": included_count,
        "truncated": query["offset"] + included_count < total,
    }

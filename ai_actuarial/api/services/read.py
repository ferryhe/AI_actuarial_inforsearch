from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from ai_actuarial.shared_runtime import get_categories_config_path, load_yaml, parse_int_clamped
from ai_actuarial.storage import Storage

PUBLIC_FILE_LIST_FIELDS: tuple[str, ...] = (
    "url",
    "title",
    "source_site",
    "source_page_url",
    "original_filename",
    "bytes",
    "content_type",
    "last_modified",
    "published_time",
    "first_seen",
    "last_seen",
    "crawl_time",
    "category",
    "summary",
    "keywords",
    "has_markdown",
    "markdown_source",
    "markdown_updated_at",
    "rag_chunk_count",
    "rag_indexed_at",
)

SENSITIVE_FILE_FIELDS: tuple[str, ...] = (
    "sha256",
    "local_path",
    "etag",
    "deleted_at",
)

FILE_LIST_FIELDS: tuple[str, ...] = PUBLIC_FILE_LIST_FIELDS + SENSITIVE_FILE_FIELDS

PUBLIC_FILE_DETAIL_FIELDS: tuple[str, ...] = PUBLIC_FILE_LIST_FIELDS + (
    "catalog_status",
    "catalog_version",
    "catalog_processed_at",
    "catalog_updated_at",
    "rag_kb_entries",
)

FILE_LIST_ORDER_FIELDS = frozenset(
    {"id", "url", "title", "source_site", "bytes", "first_seen", "last_seen", "crawl_time"}
)
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)


class FileListValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FileListQuery:
    limit: int
    offset: int
    order_by: str
    order_dir: str
    query: str
    source: str
    category: str
    include_deleted: bool
    first_seen_from: str | None
    first_seen_before: str | None


def _parse_first_seen_boundary(value: str, *, field: str) -> tuple[str, datetime]:
    text = str(value or "").strip()
    if not _RFC3339_RE.fullmatch(text):
        raise FileListValidationError(
            f"{field} must be a timezone-aware RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(
            text.replace("t", "T").replace("z", "+00:00").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise FileListValidationError(
            f"{field} must be a timezone-aware RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FileListValidationError(
            f"{field} must be a timezone-aware RFC3339 timestamp"
        )
    normalized = parsed.astimezone(timezone.utc)
    return normalized.isoformat(), normalized


def parse_file_list_query(raw_query: Mapping[str, str | None]) -> FileListQuery:
    order_by = str(raw_query.get("order_by", "last_seen") or "").strip().lower()
    order_dir = str(raw_query.get("order_dir", "desc") or "").strip().lower()
    if order_by not in FILE_LIST_ORDER_FIELDS:
        raise FileListValidationError("Invalid order_by")
    if order_dir not in {"asc", "desc"}:
        raise FileListValidationError("Invalid order_dir")

    first_seen_from_raw = str(raw_query.get("first_seen_from", "") or "").strip()
    first_seen_before_raw = str(raw_query.get("first_seen_before", "") or "").strip()
    has_period_boundary = (
        "first_seen_from" in raw_query or "first_seen_before" in raw_query
    )
    first_seen_from = None
    first_seen_before = None
    parsed_from = None
    parsed_before = None
    if first_seen_from_raw:
        first_seen_from, parsed_from = _parse_first_seen_boundary(
            first_seen_from_raw,
            field="first_seen_from",
        )
    if first_seen_before_raw:
        first_seen_before, parsed_before = _parse_first_seen_boundary(
            first_seen_before_raw,
            field="first_seen_before",
        )
    if has_period_boundary and not (first_seen_from_raw and first_seen_before_raw):
        raise FileListValidationError(
            "first_seen_from and first_seen_before must be provided together"
        )
    if parsed_from is not None and parsed_before is not None:
        if parsed_from >= parsed_before:
            raise FileListValidationError(
                "first_seen_from must be before first_seen_before"
            )

    return FileListQuery(
        limit=parse_int_clamped(raw_query.get("limit", 20), default=20, min_value=1, max_value=1000),
        offset=parse_int_clamped(raw_query.get("offset", 0), default=0, min_value=0, max_value=1_000_000),
        order_by=order_by,
        order_dir=order_dir,
        query=str(raw_query.get("query", "") or ""),
        source=str(raw_query.get("source", "") or ""),
        category=str(raw_query.get("category", "") or ""),
        include_deleted=str(raw_query.get("include_deleted", "false") or "false").lower() == "true",
        first_seen_from=first_seen_from,
        first_seen_before=first_seen_before,
    )


def _project_file_row(file_row: dict[str, Any], *, include_sensitive: bool = False) -> dict[str, Any]:
    fields = FILE_LIST_FIELDS if include_sensitive else PUBLIC_FILE_LIST_FIELDS
    return {field: file_row.get(field) for field in fields}


def project_recent_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("url", "title", "original_filename", "source_site", "content_type", "last_seen")
    return [{field: item.get(field) for field in fields} for item in files]


def project_database_files(files: list[dict[str, Any]], *, include_sensitive: bool = False) -> list[dict[str, Any]]:
    return [_project_file_row(item, include_sensitive=include_sensitive) for item in files]


def get_dashboard_stats(*, db_path: str, active_tasks: int) -> dict[str, int]:
    storage = Storage(db_path)
    try:
        return {
            "total_files": storage.get_file_count(require_local=True),
            "cataloged_files": storage.get_cataloged_count(),
            "total_sources": storage.get_sources_count(),
            "active_tasks": active_tasks,
        }
    finally:
        storage.close()


def list_categories(*, db_path: str, mode: str = "") -> dict[str, list[str]]:
    if mode.strip().lower() == "used":
        storage = Storage(db_path)
        try:
            categories = storage.get_unique_categories()
        finally:
            storage.close()
        return {"categories": categories}

    category_config_path = get_categories_config_path()
    if os.path.exists(category_config_path):
        cat_config = load_yaml(category_config_path, default={})
        configured = cat_config.get("categories") or {}
        if isinstance(configured, dict):
            return {"categories": list(configured.keys())}
        return {"categories": []}

    storage = Storage(db_path)
    try:
        categories = storage.get_unique_categories()
    finally:
        storage.close()
    return {"categories": categories}


def list_sources(*, db_path: str) -> dict[str, list[str]]:
    storage = Storage(db_path)
    try:
        sources = storage.get_unique_sources()
    finally:
        storage.close()
    return {"sources": sources}


def get_file_detail(*, db_path: str, url: str, include_sensitive: bool = False) -> dict[str, Any] | None:
    storage = Storage(db_path)
    try:
        file_data = storage.get_file_with_catalog(url)
    finally:
        storage.close()
    if not file_data:
        return None
    if include_sensitive:
        return file_data
    return {field: file_data.get(field) for field in PUBLIC_FILE_DETAIL_FIELDS}


def get_file_markdown(*, db_path: str, url: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        markdown_data = storage.get_file_markdown(url)
    finally:
        storage.close()

    if markdown_data and markdown_data.get("markdown_content"):
        return {
            "success": True,
            "markdown": markdown_data,
        }

    return {
        "success": True,
        "markdown": None,
    }


def list_files(*, db_path: str, query: FileListQuery, include_sensitive: bool = False) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        files, total = storage.query_files_with_catalog(
            limit=query.limit,
            offset=query.offset,
            order_by=query.order_by,
            order_dir=query.order_dir,
            query=query.query,
            source=query.source,
            category=query.category,
            include_deleted=query.include_deleted,
            first_seen_from=query.first_seen_from,
            first_seen_before=query.first_seen_before,
        )
    finally:
        storage.close()

    return {
        "files": project_database_files(files, include_sensitive=include_sensitive),
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
    }

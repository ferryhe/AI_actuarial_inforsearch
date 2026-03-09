from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from ai_actuarial.storage import Storage
from ai_actuarial.web.app import _get_categories_config_path, _load_yaml, _parse_int_clamped

FILE_LIST_FIELDS: tuple[str, ...] = (
    "url",
    "sha256",
    "title",
    "source_site",
    "source_page_url",
    "original_filename",
    "local_path",
    "bytes",
    "content_type",
    "last_modified",
    "etag",
    "published_time",
    "first_seen",
    "last_seen",
    "crawl_time",
    "deleted_at",
    "category",
    "summary",
    "keywords",
    "markdown_content",
    "markdown_source",
    "markdown_updated_at",
    "rag_chunk_count",
    "rag_indexed_at",
)


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


def parse_file_list_query(raw_query: Mapping[str, str | None]) -> FileListQuery:
    return FileListQuery(
        limit=_parse_int_clamped(raw_query.get("limit", 20), default=20, min_value=1, max_value=1000),
        offset=_parse_int_clamped(raw_query.get("offset", 0), default=0, min_value=0, max_value=1_000_000),
        order_by=str(raw_query.get("order_by", "last_seen") or "last_seen"),
        order_dir=str(raw_query.get("order_dir", "desc") or "desc"),
        query=str(raw_query.get("query", "") or ""),
        source=str(raw_query.get("source", "") or ""),
        category=str(raw_query.get("category", "") or ""),
        include_deleted=str(raw_query.get("include_deleted", "false") or "false").lower() == "true",
    )


def _project_file_row(file_row: dict[str, Any]) -> dict[str, Any]:
    return {field: file_row.get(field) for field in FILE_LIST_FIELDS}


def project_recent_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("url", "title", "original_filename", "source_site", "content_type", "last_seen")
    return [{field: item.get(field) for field in fields} for item in files]


def project_database_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_project_file_row(item) for item in files]


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

    category_config_path = _get_categories_config_path()
    if os.path.exists(category_config_path):
        cat_config = _load_yaml(category_config_path, default={})
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


def list_files(*, db_path: str, query: FileListQuery) -> dict[str, Any]:
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
        )
    finally:
        storage.close()

    return {
        "files": project_database_files(files),
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
    }

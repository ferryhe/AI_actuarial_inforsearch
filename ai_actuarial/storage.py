from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                sha256 TEXT,
                title TEXT,
                source_site TEXT,
                source_page_url TEXT,
                original_filename TEXT,
                local_path TEXT,
                bytes INTEGER,
                content_type TEXT,
                last_modified TEXT,
                etag TEXT,
                published_time TEXT,
                first_seen TEXT,
                last_seen TEXT,
                crawl_time TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                last_seen TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blobs (
                sha256 TEXT PRIMARY KEY,
                canonical_path TEXT,
                bytes INTEGER,
                content_type TEXT,
                first_seen TEXT,
                last_seen TEXT
            )
            """
        )
        # catalog_items: incremental catalog state tracking
        self._conn.execute(
            """
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
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_items_status ON catalog_items(status)
            """
        )
        self._conn.commit()
        self._ensure_columns(
            "files",
            {
                "source_page_url": "TEXT",
                "original_filename": "TEXT",
                "bytes": "INTEGER",
                "content_type": "TEXT",
                "last_modified": "TEXT",
                "etag": "TEXT",
                "published_time": "TEXT",
                "crawl_time": "TEXT",
            },
        )
        self._ensure_columns(
            "catalog_items",
            {
                "file_sha256": "TEXT",
                "keywords_json": "TEXT",
                "summary": "TEXT",
                "category": "TEXT",
                "catalog_version": "TEXT",
                "processed_at": "TEXT",
                "status": "TEXT",
                "error": "TEXT",
            },
        )

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        cur = self._conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        for name, col_type in columns.items():
            if name not in existing:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"
                )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def file_exists(self, url: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM files WHERE url = ? LIMIT 1", (url,))
        return cur.fetchone() is not None

    def upsert_file(
        self,
        url: str,
        sha256: str,
        title: str | None,
        source_site: str,
        source_page_url: str | None,
        original_filename: str | None,
        local_path: str,
        bytes_size: int | None,
        content_type: str | None,
        last_modified: str | None,
        etag: str | None,
        published_time: str | None,
    ) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO files (
                url, sha256, title, source_site, source_page_url, original_filename,
                local_path, bytes, content_type, last_modified, etag, published_time,
                first_seen, last_seen, crawl_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                sha256=excluded.sha256,
                title=excluded.title,
                source_site=excluded.source_site,
                source_page_url=excluded.source_page_url,
                original_filename=excluded.original_filename,
                local_path=excluded.local_path,
                bytes=excluded.bytes,
                content_type=excluded.content_type,
                last_modified=excluded.last_modified,
                etag=excluded.etag,
                published_time=excluded.published_time,
                last_seen=excluded.last_seen,
                crawl_time=excluded.crawl_time
            """,
            (
                url,
                sha256,
                title,
                source_site,
                source_page_url,
                original_filename,
                local_path,
                bytes_size,
                content_type,
                last_modified,
                etag,
                published_time,
                ts,
                ts,
                ts,
            ),
        )
        self._conn.commit()

    def mark_page_seen(self, url: str) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO pages (url, last_seen)
            VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE SET last_seen=excluded.last_seen
            """,
            (url, ts),
        )
        self._conn.commit()

    def export_files(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT url, sha256, title, source_site, source_page_url, original_filename,
                   local_path, bytes, content_type, last_modified, etag, published_time,
                   first_seen, last_seen, crawl_time
            FROM files
            ORDER BY last_seen DESC
            """
        )
        rows = cur.fetchall()
        keys = [
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
        ]
        return [dict(zip(keys, row)) for row in rows]

    # Allowed columns for ORDER BY to prevent SQL injection
    _ALLOWED_ORDER_COLUMNS = frozenset([
        "id", "url", "sha256", "title", "source_site", "local_path",
        "bytes", "first_seen", "last_seen", "crawl_time"
    ])

    def iter_files(
        self,
        site_filter: str | None,
        limit: int | None,
        offset: int = 0,
        require_local_path: bool = True,
        order_by: str = "id",
        only_changed: bool = False,
        extractor_version: str | None = None,
    ) -> list[dict]:
        # Validate order_by to prevent SQL injection
        if order_by not in self._ALLOWED_ORDER_COLUMNS:
            raise ValueError(f"Invalid order_by column: {order_by}. Allowed: {self._ALLOWED_ORDER_COLUMNS}")
        
        filters: list[str] = []
        params: list[object] = []
        if require_local_path:
            filters.append("local_path IS NOT NULL AND local_path != ''")
        if site_filter:
            tokens = [t.strip().lower() for t in site_filter.split(",") if t.strip()]
            if tokens:
                like_parts = []
                for t in tokens:
                    like_parts.append("LOWER(source_site) LIKE ?")
                    params.append(f"%{t}%")
                    like_parts.append("LOWER(url) LIKE ?")
                    params.append(f"%{t}%")
                filters.append("(" + " OR ".join(like_parts) + ")")
        join = ""
        if only_changed:
            if not extractor_version:
                raise ValueError("extractor_version is required when only_changed is True")
            join = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            filters.append(
                "(c.file_url IS NULL OR c.sha256 != f.sha256 OR c.extractor_version != ?)"
            )
            params.append(extractor_version)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cur = self._conn.execute(
            f"""
            SELECT f.url, f.sha256, f.title, f.source_site, f.source_page_url, f.original_filename,
                   f.local_path, f.bytes, f.content_type, f.last_modified, f.etag, f.published_time,
                   f.first_seen, f.last_seen, f.crawl_time
            FROM files f
            {join}
            {where}
            ORDER BY f.{order_by}
            {limit_clause}
            """,
            tuple(params),
        )
        rows = cur.fetchall()
        keys = [
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
        ]
        return [dict(zip(keys, row)) for row in rows]

    def get_blob(self, sha256: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT sha256, canonical_path, bytes, content_type FROM blobs WHERE sha256 = ?",
            (sha256,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "sha256": row[0],
            "canonical_path": row[1],
            "bytes": row[2],
            "content_type": row[3],
        }

    def upsert_blob(
        self,
        sha256: str,
        canonical_path: str,
        bytes_size: int | None,
        content_type: str | None,
    ) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO blobs (sha256, canonical_path, bytes, content_type, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
                canonical_path=excluded.canonical_path,
                bytes=excluded.bytes,
                content_type=excluded.content_type,
                last_seen=excluded.last_seen
            """,
            (sha256, canonical_path, bytes_size, content_type, ts, ts),
        )
        self._conn.commit()

    def catalog_item_fresh(self, url: str, sha256: str, extractor_version: str) -> bool:
        cur = self._conn.execute(
            """
            SELECT 1 FROM catalog_items
            WHERE file_url = ? AND sha256 = ? AND extractor_version = ?
            """,
            (url, sha256, extractor_version),
        )
        return cur.fetchone() is not None

    def upsert_catalog_item(self, item: dict, extractor_version: str) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO catalog_items (
                file_url, sha256, extractor_version, title, source_site,
                original_filename, local_path, keywords, summary, category, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_url) DO UPDATE SET
                sha256=excluded.sha256,
                extractor_version=excluded.extractor_version,
                title=excluded.title,
                source_site=excluded.source_site,
                original_filename=excluded.original_filename,
                local_path=excluded.local_path,
                keywords=excluded.keywords,
                summary=excluded.summary,
                category=excluded.category,
                updated_at=excluded.updated_at
            """,
            (
                item.get("url"),
                item.get("sha256"),
                extractor_version,
                item.get("title"),
                item.get("source_site"),
                item.get("original_filename"),
                item.get("local_path"),
                json.dumps(item.get("keywords") or [], ensure_ascii=False),
                item.get("summary") or "",
                item.get("category") or "",
                ts,
            ),
        )
        self._conn.commit()

    def write_last_run(self, output_path: str, items: Iterable[dict]) -> None:
        Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(list(items), f, ensure_ascii=False, indent=2)

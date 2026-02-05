from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._tx_depth = 0
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
                sha256 TEXT NOT NULL,
                pipeline_version TEXT NOT NULL,
                processed_at TEXT,
                status TEXT NOT NULL DEFAULT 'ok',
                error TEXT,
                keywords TEXT,
                summary TEXT,
                category TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
                "sha256": "TEXT",
                "pipeline_version": "TEXT",
                "processed_at": "TEXT",
                "status": "TEXT DEFAULT 'ok'",
                "error": "TEXT",
                "keywords": "TEXT",
                "summary": "TEXT",
                "category": "TEXT",
                "updated_at": "TEXT",
            },
        )
        self._migrate_catalog_items()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        cur = self._conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        for name, col_type in columns.items():
            if name not in existing:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"
                )
        self._conn.commit()

    def _maybe_commit(self) -> None:
        if self._tx_depth == 0:
            self._conn.commit()

    @contextmanager
    def transaction(self):
        sp_name = None
        if self._tx_depth == 0:
            self._conn.execute("BEGIN")
        else:
            sp_name = f"sp_{self._tx_depth}"
            self._conn.execute(f"SAVEPOINT {sp_name}")
        self._tx_depth += 1
        try:
            yield
        except Exception:
            self._tx_depth -= 1
            if sp_name is None:
                self._conn.rollback()
            else:
                self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                self._conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            raise
        else:
            self._tx_depth -= 1
            if sp_name is None:
                self._conn.commit()
            else:
                self._conn.execute(f"RELEASE SAVEPOINT {sp_name}")

    def _migrate_catalog_items(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(catalog_items)")
        existing = {row[1] for row in cur.fetchall()}

        # Map legacy columns into the unified schema without dropping data.
        if "sha256" in existing and "file_sha256" in existing:
            self._conn.execute(
                """
                UPDATE catalog_items
                SET sha256 = file_sha256
                WHERE (sha256 IS NULL OR sha256 = '') AND file_sha256 IS NOT NULL
                """
            )
        if "pipeline_version" in existing:
            if "extractor_version" in existing:
                self._conn.execute(
                    """
                    UPDATE catalog_items
                    SET pipeline_version = extractor_version
                    WHERE (pipeline_version IS NULL OR pipeline_version = '')
                      AND extractor_version IS NOT NULL
                    """
                )
            if "catalog_version" in existing:
                self._conn.execute(
                    """
                    UPDATE catalog_items
                    SET pipeline_version = catalog_version
                    WHERE (pipeline_version IS NULL OR pipeline_version = '')
                      AND catalog_version IS NOT NULL
                    """
                )
        if "keywords" in existing and "keywords_json" in existing:
            self._conn.execute(
                """
                UPDATE catalog_items
                SET keywords = keywords_json
                WHERE (keywords IS NULL OR keywords = '') AND keywords_json IS NOT NULL
                """
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def file_exists_by_hash(self, sha256: str) -> bool:
        """Check if a file with the given hash already exists in the database.
        
        Args:
            sha256: The SHA256 hash of the file content.
            
        Returns:
            True if a file with this hash exists, False otherwise.
        """
        cur = self._conn.execute(
            "SELECT 1 FROM blobs WHERE sha256 = ?", (sha256,)
        )
        if cur.fetchone():
            return True
            
        # Also check files table as fallback
        cur = self._conn.execute(
            "SELECT 1 FROM files WHERE sha256 = ?", (sha256,)
        )
        return cur.fetchone() is not None

    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def file_exists(self, url: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM files WHERE url = ? LIMIT 1", (url,))
        return cur.fetchone() is not None

    def get_file_by_url(self, url: str) -> dict | None:
        """Get file record by URL.
        
        Args:
            url: File URL
            
        Returns:
            File record dict or None if not found
        """
        cur = self._conn.execute(
            "SELECT * FROM files WHERE url = ? LIMIT 1", (url,)
        )
        row = cur.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    
    def get_file_by_sha256(self, sha256: str) -> dict | None:
        """Get file record by SHA256 hash.
        
        Args:
            sha256: File SHA256 hash
            
        Returns:
            File record dict or None if not found
        """
        cur = self._conn.execute(
            "SELECT * FROM files WHERE sha256 = ? LIMIT 1", (sha256,)
        )
        row = cur.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    
    def insert_file(
        self,
        url: str,
        sha256: str,
        title: str | None,
        source_site: str,
        source_page_url: str | None,
        original_filename: str | None,
        local_path: str,
        bytes: int | None,
        content_type: str | None,
        last_modified: str | None = None,
        etag: str | None = None,
        published_time: str | None = None,
    ) -> None:
        """Insert a new file record (raises error if URL exists).
        
        Args:
            url: File URL
            sha256: SHA256 hash
            title: File title
            source_site: Source site name
            source_page_url: URL of the page where file was found
            original_filename: Original filename
            local_path: Path to downloaded file
            bytes: File size in bytes
            content_type: Content type
            last_modified: Last modified timestamp
            etag: ETag header value
            published_time: Published time
        """
        # Note: Parameter 'bytes' shadows built-in, but this is intentional
        # to match the database column name 'bytes' for consistency
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO files (
                url, sha256, title, source_site, source_page_url, original_filename,
                local_path, bytes, content_type, last_modified, etag, published_time,
                first_seen, last_seen, crawl_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                sha256,
                title,
                source_site,
                source_page_url,
                original_filename,
                local_path,
                bytes,
                content_type,
                last_modified,
                etag,
                published_time,
                ts,
                ts,
                ts,
            ),
        )
        self._maybe_commit()

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
        self._maybe_commit()

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
        self._maybe_commit()

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
        include_errors: bool = False,
    ) -> list[dict]:
        # Validate order_by to prevent SQL injection
        if order_by not in self._ALLOWED_ORDER_COLUMNS:
            raise ValueError(f"Invalid order_by column: {order_by}. Allowed: {self._ALLOWED_ORDER_COLUMNS}")
        
        filters: list[str] = []
        params: list[object] = []
        if require_local_path:
            filters.append("f.local_path IS NOT NULL AND f.local_path != ''")
        if site_filter:
            tokens = [t.strip().lower() for t in site_filter.split(",") if t.strip()]
            if tokens:
                like_parts = []
                for t in tokens:
                    like_parts.append("LOWER(f.source_site) LIKE ?")
                    params.append(f"%{t}%")
                    like_parts.append("LOWER(f.url) LIKE ?")
                    params.append(f"%{t}%")
                filters.append("(" + " OR ".join(like_parts) + ")")
        join = ""
        if only_changed:
            if not extractor_version:
                raise ValueError("extractor_version is required when only_changed is True")
            join = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            clause = "c.file_url IS NULL OR c.sha256 != f.sha256 OR c.pipeline_version != ?"
            if include_errors:
                clause += " OR c.status IS NULL OR c.status != 'ok'"
            filters.append(f"({clause})")
            params.append(extractor_version)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cur = self._conn.execute(
            f"""
            SELECT f.url AS url,
                   f.sha256 AS sha256,
                   f.title AS title,
                   f.source_site AS source_site,
                   f.source_page_url AS source_page_url,
                   f.original_filename AS original_filename,
                   f.local_path AS local_path,
                   f.bytes AS bytes,
                   f.content_type AS content_type,
                   f.last_modified AS last_modified,
                   f.etag AS etag,
                   f.published_time AS published_time,
                   f.first_seen AS first_seen,
                   f.last_seen AS last_seen,
                   f.crawl_time AS crawl_time
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
        self._maybe_commit()

    def catalog_item_fresh(
        self,
        url: str,
        sha256: str,
        pipeline_version: str | None = None,
        extractor_version: str | None = None,
    ) -> bool:
        effective_pipeline_version = pipeline_version or extractor_version or ""
        cur = self._conn.execute(
            """
            SELECT 1 FROM catalog_items
            WHERE file_url = ? AND sha256 = ? AND pipeline_version = ? AND status = 'ok'
            """,
            (url, sha256, effective_pipeline_version),
        )
        return cur.fetchone() is not None

    def upsert_catalog_item(
        self,
        item: dict,
        pipeline_version: str | None = None,
        status: str = "ok",
        error: str | None = None,
        processed_at: str | None = None,
        extractor_version: str | None = None,
    ) -> None:
        processed_ts = processed_at or self.now()
        updated_ts = self.now()
        effective_pipeline_version = pipeline_version or extractor_version or ""
        self._conn.execute(
            """
            INSERT INTO catalog_items (
                file_url, sha256, pipeline_version, processed_at, status, error,
                keywords, summary, category, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_url) DO UPDATE SET
                sha256=excluded.sha256,
                pipeline_version=excluded.pipeline_version,
                processed_at=excluded.processed_at,
                status=excluded.status,
                error=excluded.error,
                keywords=excluded.keywords,
                summary=excluded.summary,
                category=excluded.category,
                updated_at=excluded.updated_at
            """,
            (
                item.get("url"),
                item.get("sha256"),
                effective_pipeline_version,
                processed_ts,
                status,
                error,
                json.dumps(item.get("keywords") or [], ensure_ascii=False),
                item.get("summary") or "",
                item.get("category") or "",
                updated_ts,
            ),
        )
        self._maybe_commit()

    def write_last_run(self, output_path: str, items: Iterable[dict]) -> None:
        Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(list(items), f, ensure_ascii=False, indent=2)

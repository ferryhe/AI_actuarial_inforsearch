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

    def file_exists(self, url: str, sha256: str | None = None) -> bool:
        if sha256:
            cur = self._conn.execute(
                "SELECT 1 FROM files WHERE url = ? OR sha256 = ? LIMIT 1", (url, sha256)
            )
        else:
            cur = self._conn.execute(
                "SELECT 1 FROM files WHERE url = ? LIMIT 1", (url,)
            )
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

    def write_last_run(self, output_path: str, items: Iterable[dict]) -> None:
        Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(list(items), f, ensure_ascii=False, indent=2)

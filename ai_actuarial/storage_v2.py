"""StorageV2: SQLAlchemy-based storage implementation with PostgreSQL support.

This is a new implementation of the Storage interface using SQLAlchemy ORM,
providing support for both SQLite and PostgreSQL backends.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Any

from sqlalchemy import or_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db_backend import create_backend
from .db_models import File, Page, Blob, CatalogItem


class StorageV2:
    """Storage implementation using SQLAlchemy for multi-database support."""
    
    def __init__(self, db_config: dict[str, Any]) -> None:
        """Initialize storage with database configuration.
        
        Args:
            db_config: Database configuration dict:
                - type: 'sqlite' or 'postgresql'
                - path: for SQLite
                - host, port, database, username, password: for PostgreSQL
        """
        self.backend = create_backend(db_config)
        self.backend.connect()
        self.db_path = db_config.get("path") if db_config.get("type") == "sqlite" else None
        
    def close(self) -> None:
        """Close database connection."""
        self.backend.close()
    
    def now(self) -> str:
        """Get current timestamp."""
        return self.backend.now()
    
    @property
    def _session(self):
        """Get current database session."""
        return self.backend.get_session()
    
    @property
    def _conn(self):
        """Get raw database connection for compatibility."""
        return self._session.connection()
    
    def transaction(self):
        """Context manager for database transactions."""
        return self.backend.transaction()
    
    def file_exists(self, url: str) -> bool:
        """Check if file exists by URL."""
        result = self._session.query(File).filter(File.url == url).first()
        return result is not None
    
    def get_file_by_url(self, url: str) -> dict | None:
        """Get file record by URL."""
        file_obj = self._session.query(File).filter(File.url == url).first()
        if not file_obj:
            return None
        return self._model_to_dict(file_obj)
    
    def get_file_by_sha256(self, sha256: str) -> dict | None:
        """Get file record by SHA256 hash."""
        file_obj = self._session.query(File).filter(File.sha256 == sha256).first()
        if not file_obj:
            return None
        return self._model_to_dict(file_obj)
    
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
        """Insert a new file record."""
        ts = self.now()
        file_obj = File(
            url=url,
            sha256=sha256,
            title=title,
            source_site=source_site,
            source_page_url=source_page_url,
            original_filename=original_filename,
            local_path=local_path,
            bytes=bytes,
            content_type=content_type,
            last_modified=last_modified,
            etag=etag,
            published_time=published_time,
            first_seen=ts,
            last_seen=ts,
            crawl_time=ts,
        )
        self._session.add(file_obj)
        self.backend._maybe_commit()
    
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
        """Upsert file record."""
        ts = self.now()
        values = {
            "url": url,
            "sha256": sha256,
            "title": title,
            "source_site": source_site,
            "source_page_url": source_page_url,
            "original_filename": original_filename,
            "local_path": local_path,
            "bytes": bytes_size,
            "content_type": content_type,
            "last_modified": last_modified,
            "etag": etag,
            "published_time": published_time,
            "first_seen": ts,
            "last_seen": ts,
            "crawl_time": ts,
        }
        
        # Use database-specific upsert
        if self.backend.engine.dialect.name == "postgresql":
            stmt = pg_insert(File).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "sha256": stmt.excluded.sha256,
                    "title": stmt.excluded.title,
                    "source_site": stmt.excluded.source_site,
                    "source_page_url": stmt.excluded.source_page_url,
                    "original_filename": stmt.excluded.original_filename,
                    "local_path": stmt.excluded.local_path,
                    "bytes": stmt.excluded.bytes,
                    "content_type": stmt.excluded.content_type,
                    "last_modified": stmt.excluded.last_modified,
                    "etag": stmt.excluded.etag,
                    "published_time": stmt.excluded.published_time,
                    "last_seen": stmt.excluded.last_seen,
                    "crawl_time": stmt.excluded.crawl_time,
                }
            )
        else:  # SQLite
            stmt = sqlite_insert(File).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "sha256": stmt.excluded.sha256,
                    "title": stmt.excluded.title,
                    "source_site": stmt.excluded.source_site,
                    "source_page_url": stmt.excluded.source_page_url,
                    "original_filename": stmt.excluded.original_filename,
                    "local_path": stmt.excluded.local_path,
                    "bytes": stmt.excluded.bytes,
                    "content_type": stmt.excluded.content_type,
                    "last_modified": stmt.excluded.last_modified,
                    "etag": stmt.excluded.etag,
                    "published_time": stmt.excluded.published_time,
                    "last_seen": stmt.excluded.last_seen,
                    "crawl_time": stmt.excluded.crawl_time,
                }
            )
        
        self._session.execute(stmt)
        self.backend._maybe_commit()
    
    def mark_page_seen(self, url: str) -> None:
        """Mark page as seen."""
        ts = self.now()
        values = {"url": url, "last_seen": ts}
        
        if self.backend.engine.dialect.name == "postgresql":
            stmt = pg_insert(Page).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={"last_seen": stmt.excluded.last_seen}
            )
        else:  # SQLite
            stmt = sqlite_insert(Page).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={"last_seen": stmt.excluded.last_seen}
            )
        
        self._session.execute(stmt)
        self.backend._maybe_commit()
    
    def export_files(self) -> list[dict]:
        """Export all files."""
        files = self._session.query(File).order_by(File.last_seen.desc()).all()
        return [self._model_to_dict(f) for f in files]
    
    # Allowed columns for ORDER BY
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
        """Iterate files with filtering."""
        # Validate order_by
        if order_by not in self._ALLOWED_ORDER_COLUMNS:
            raise ValueError(f"Invalid order_by column: {order_by}")
        
        # Build query
        query = self._session.query(File)
        
        # Apply filters
        if require_local_path:
            query = query.filter(File.local_path.isnot(None), File.local_path != "")
        
        if site_filter:
            def _escape_like(token: str) -> str:
                """Escape SQL LIKE wildcard characters so they are treated literally."""
                return (
                    token.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
            
            tokens = [t.strip().lower() for t in site_filter.split(",") if t.strip()]
            if tokens:
                or_conditions = []
                for t in tokens:
                    escaped_token = _escape_like(t)
                    or_conditions.append(
                        func.lower(File.source_site).like(f"%{escaped_token}%", escape="\\")
                    )
                    or_conditions.append(
                        func.lower(File.url).like(f"%{escaped_token}%", escape="\\")
                    )
                query = query.filter(or_(*or_conditions))
        
        if only_changed:
            if not extractor_version:
                raise ValueError("extractor_version is required when only_changed is True")
            # Left join with catalog_items
            query = query.outerjoin(CatalogItem, CatalogItem.file_url == File.url)
            conditions = or_(
                CatalogItem.file_url.is_(None),
                CatalogItem.sha256 != File.sha256,
                CatalogItem.pipeline_version != extractor_version
            )
            if include_errors:
                conditions = or_(
                    conditions,
                    CatalogItem.status.is_(None),
                    CatalogItem.status != "ok"
                )
            query = query.filter(conditions)
        
        # Apply ordering
        order_col = getattr(File, order_by)
        query = query.order_by(order_col)
        
        # Apply pagination
        if limit is not None:
            query = query.limit(limit).offset(offset)
        
        files = query.all()
        return [self._model_to_dict(f) for f in files]
    
    def get_blob(self, sha256: str) -> dict | None:
        """Get blob by SHA256."""
        blob = self._session.query(Blob).filter(Blob.sha256 == sha256).first()
        if not blob:
            return None
        return {
            "sha256": blob.sha256,
            "canonical_path": blob.canonical_path,
            "bytes": blob.bytes,
            "content_type": blob.content_type,
        }
    
    def upsert_blob(
        self,
        sha256: str,
        canonical_path: str,
        bytes_size: int | None,
        content_type: str | None,
    ) -> None:
        """Upsert blob record."""
        ts = self.now()
        values = {
            "sha256": sha256,
            "canonical_path": canonical_path,
            "bytes": bytes_size,
            "content_type": content_type,
            "first_seen": ts,
            "last_seen": ts,
        }
        
        if self.backend.engine.dialect.name == "postgresql":
            stmt = pg_insert(Blob).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["sha256"],
                set_={
                    "canonical_path": stmt.excluded.canonical_path,
                    "bytes": stmt.excluded.bytes,
                    "content_type": stmt.excluded.content_type,
                    "last_seen": stmt.excluded.last_seen,
                }
            )
        else:  # SQLite
            stmt = sqlite_insert(Blob).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["sha256"],
                set_={
                    "canonical_path": stmt.excluded.canonical_path,
                    "bytes": stmt.excluded.bytes,
                    "content_type": stmt.excluded.content_type,
                    "last_seen": stmt.excluded.last_seen,
                }
            )
        
        self._session.execute(stmt)
        self.backend._maybe_commit()
    
    def catalog_item_fresh(
        self,
        url: str,
        sha256: str,
        pipeline_version: str | None = None,
        extractor_version: str | None = None,
    ) -> bool:
        """Check if catalog item is fresh."""
        effective_version = pipeline_version or extractor_version or ""
        result = self._session.query(CatalogItem).filter(
            CatalogItem.file_url == url,
            CatalogItem.sha256 == sha256,
            CatalogItem.pipeline_version == effective_version,
            CatalogItem.status == "ok"
        ).first()
        return result is not None
    
    def upsert_catalog_item(
        self,
        item: dict,
        pipeline_version: str | None = None,
        status: str = "ok",
        error: str | None = None,
        processed_at: str | None = None,
        extractor_version: str | None = None,
    ) -> None:
        """Upsert catalog item."""
        processed_ts = processed_at or self.now()
        updated_ts = self.now()
        effective_version = pipeline_version or extractor_version or ""
        
        values = {
            "file_url": item.get("url"),
            "sha256": item.get("sha256"),
            "pipeline_version": effective_version,
            "processed_at": processed_ts,
            "status": status,
            "error": error,
            "keywords": json.dumps(item.get("keywords") or [], ensure_ascii=False),
            "summary": item.get("summary") or "",
            "category": item.get("category") or "",
            "updated_at": updated_ts,
        }
        
        if self.backend.engine.dialect.name == "postgresql":
            stmt = pg_insert(CatalogItem).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["file_url"],
                set_={
                    "sha256": stmt.excluded.sha256,
                    "pipeline_version": stmt.excluded.pipeline_version,
                    "processed_at": stmt.excluded.processed_at,
                    "status": stmt.excluded.status,
                    "error": stmt.excluded.error,
                    "keywords": stmt.excluded.keywords,
                    "summary": stmt.excluded.summary,
                    "category": stmt.excluded.category,
                    "updated_at": stmt.excluded.updated_at,
                }
            )
        else:  # SQLite
            stmt = sqlite_insert(CatalogItem).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["file_url"],
                set_={
                    "sha256": stmt.excluded.sha256,
                    "pipeline_version": stmt.excluded.pipeline_version,
                    "processed_at": stmt.excluded.processed_at,
                    "status": stmt.excluded.status,
                    "error": stmt.excluded.error,
                    "keywords": stmt.excluded.keywords,
                    "summary": stmt.excluded.summary,
                    "category": stmt.excluded.category,
                    "updated_at": stmt.excluded.updated_at,
                }
            )
        
        self._session.execute(stmt)
        self.backend._maybe_commit()
    
    def write_last_run(self, output_path: str, items: Iterable[dict]) -> None:
        """Write last run results to file."""
        Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(list(items), f, ensure_ascii=False, indent=2)
    
    def _model_to_dict(self, model) -> dict:
        """Convert SQLAlchemy model to dictionary."""
        if isinstance(model, File):
            return {
                "id": model.id,
                "url": model.url,
                "sha256": model.sha256,
                "title": model.title,
                "source_site": model.source_site,
                "source_page_url": model.source_page_url,
                "original_filename": model.original_filename,
                "local_path": model.local_path,
                "bytes": model.bytes,
                "content_type": model.content_type,
                "last_modified": model.last_modified,
                "etag": model.etag,
                "published_time": model.published_time,
                "first_seen": model.first_seen,
                "last_seen": model.last_seen,
                "crawl_time": model.crawl_time,
            }
        # Add other model types as needed
        return {}

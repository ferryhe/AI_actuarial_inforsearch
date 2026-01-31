"""SQLAlchemy database models for the application."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class File(Base):
    """File metadata table."""
    
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True)
    url = Column(Text, unique=True, nullable=False)
    sha256 = Column(Text)
    title = Column(Text)
    source_site = Column(Text)
    source_page_url = Column(Text)
    original_filename = Column(Text)
    local_path = Column(Text)
    bytes = Column(Integer)
    content_type = Column(Text)
    last_modified = Column(Text)
    etag = Column(Text)
    published_time = Column(Text)
    first_seen = Column(Text)
    last_seen = Column(Text)
    crawl_time = Column(Text)


class Page(Base):
    """Page tracking table."""
    
    __tablename__ = "pages"
    
    id = Column(Integer, primary_key=True)
    url = Column(Text, unique=True, nullable=False)
    last_seen = Column(Text)


class Blob(Base):
    """Blob storage tracking table."""
    
    __tablename__ = "blobs"
    
    sha256 = Column(Text, primary_key=True)
    canonical_path = Column(Text)
    bytes = Column(Integer)
    content_type = Column(Text)
    first_seen = Column(Text)
    last_seen = Column(Text)


class CatalogItem(Base):
    """Catalog items table for processed files."""
    
    __tablename__ = "catalog_items"
    
    file_url = Column(Text, primary_key=True)
    sha256 = Column(Text, nullable=False)
    pipeline_version = Column(Text, nullable=False)
    processed_at = Column(Text)
    status = Column(Text, nullable=False, default="ok")
    error = Column(Text)
    keywords = Column(Text)
    summary = Column(Text)
    category = Column(Text)
    updated_at = Column(Text)
    
    __table_args__ = (
        Index("idx_catalog_items_status", "status"),
    )


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()

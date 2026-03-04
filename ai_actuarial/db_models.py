"""SQLAlchemy database models for the application."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Text, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

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


# ============== RAG Models ==============

class ChunkProfile(Base):
    """Chunk configuration profiles."""
    
    __tablename__ = "chunk_profiles"
    
    profile_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    config_hash = Column(Text, unique=True, nullable=False)
    config_json = Column(Text, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    chunk_overlap = Column(Integer, nullable=False)
    splitter = Column(Text, nullable=False)
    tokenizer = Column(Text, nullable=False)
    version = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)


class FileChunkSet(Base):
    """Chunk sets for files."""
    
    __tablename__ = "file_chunk_sets"
    
    chunk_set_id = Column(Text, primary_key=True)
    file_url = Column(Text, nullable=False)
    profile_id = Column(Text, nullable=False)
    markdown_hash = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="ready")
    chunk_count = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('file_url', 'profile_id', 'markdown_hash', name='uq_file_profile_hash'),
        Index('idx_file_chunk_sets_file_url', 'file_url'),
        Index('idx_file_chunk_sets_profile_id', 'profile_id'),
    )


class GlobalChunk(Base):
    """Global chunks for KB composition."""
    
    __tablename__ = "global_chunks"
    
    chunk_id = Column(Text, primary_key=True)
    chunk_set_id = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    section_hierarchy = Column(Text)
    content_hash = Column(Text)
    created_at = Column(Text, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('chunk_set_id', 'chunk_index', name='uq_chunk_set_index'),
        Index('idx_global_chunks_chunk_set_id', 'chunk_set_id'),
    )


class ChunkEmbedding(Base):
    """Chunk embeddings for vector search."""
    
    __tablename__ = "chunk_embeddings"
    
    chunk_id = Column(Text, primary_key=True)
    embedding_model = Column(Text, primary_key=True)
    dim = Column(Integer, default=0)
    vector_json = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)


class KBChunkBinding(Base):
    """KB-Chunk bindings for RAG."""
    
    __tablename__ = "kb_chunk_bindings"
    
    kb_id = Column(Text, primary_key=True)
    file_url = Column(Text, primary_key=True)
    chunk_set_id = Column(Text, primary_key=True)
    bound_at = Column(Text, nullable=False)
    bound_by = Column(Text)
    binding_mode = Column(Text, nullable=False, default="pin")
    target_profile_id = Column(Text)
    
    __table_args__ = (
        Index('idx_kb_chunk_bindings_kb_id', 'kb_id'),
        Index('idx_kb_chunk_bindings_file_url', 'file_url'),
        Index('idx_kb_chunk_bindings_target_profile_id', 'target_profile_id'),
    )


class KBIndexVersion(Base):
    """KB index versions."""
    
    __tablename__ = "kb_index_versions"
    
    index_version_id = Column(Text, primary_key=True)
    kb_id = Column(Text, nullable=False)
    embedding_model = Column(Text, nullable=False)
    index_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    artifact_path = Column(Text)
    chunk_count = Column(Integer, nullable=False, default=0)
    built_at = Column(Text)
    created_at = Column(Text, nullable=False)
    
    __table_args__ = (
        Index('idx_kb_index_versions_kb_id', 'kb_id'),
    )


class KBIndexItem(Base):
    """KB index items (chunk references)."""
    
    __tablename__ = "kb_index_items"
    
    index_version_id = Column(Text, primary_key=True)
    chunk_id = Column(Text, primary_key=True)


# ============== Auth Models ==============

class AuthToken(Base):
    """Authentication tokens."""
    
    __tablename__ = "auth_tokens"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(Text, nullable=False)
    group_name = Column(Text, nullable=False)
    token_hash = Column(Text, unique=True, nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(Text)
    last_used_at = Column(Text)
    revoked_at = Column(Text)
    expires_at = Column(Text)


# Note: APIToken is defined in ai_actuarial.models.api_token
# Import it from there to avoid duplicate model definitions
# from ai_actuarial.models.api_token import ApiToken


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()

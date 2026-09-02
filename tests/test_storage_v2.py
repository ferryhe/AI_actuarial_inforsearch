"""Tests for storage_v2, storage_v2_rag, and storage_v2_auth modules."""

import os
import sqlite3
import tempfile

import pytest


class TestStorageV2Basic:
    """Test basic StorageV2 operations."""

    def test_storage_v2_creation(self):
        """Test StorageV2 can be created with SQLite."""
        from ai_actuarial.storage_v2 import StorageV2

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = StorageV2({"type": "sqlite", "path": db_path})
            assert storage is not None
            storage.close()

    def test_file_operations(self):
        """Test file insert and retrieval."""
        from ai_actuarial.storage_v2 import StorageV2

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = StorageV2({"type": "sqlite", "path": db_path})

            storage.upsert_file(
                url="https://example.com/test.pdf",
                sha256="abc123",
                title="Test Document",
                source_site="example.com",
                source_page_url="https://example.com/page",
                original_filename="test.pdf",
                local_path="/tmp/test.pdf",
                bytes_size=1024,
                content_type="application/pdf",
                last_modified="2024-01-01",
                etag="abc",
                published_time=None,
            )

            file = storage.get_file_by_url("https://example.com/test.pdf")
            assert file is not None
            assert file["sha256"] == "abc123"
            assert storage.file_exists("https://example.com/test.pdf") is True
            storage.close()


class TestStorageV2RAG:
    """Test StorageV2 RAG operations."""

    def test_rag_methods_exist(self):
        """Test RAG methods exist."""
        from ai_actuarial.storage_v2_rag import StorageV2RAGMixin

        class TestStorage(StorageV2RAGMixin):
            def __init__(self, db_config):
                self.backend = None
                self.db_path = db_config.get("path") if db_config.get("type") == "sqlite" else None

        storage = TestStorage({})
        assert hasattr(storage, "create_chunk_profile")
        assert hasattr(storage, "list_chunk_profiles")
        assert hasattr(storage, "get_chunk_profile")
        assert hasattr(storage, "bind_chunk_set_to_kb")
        assert hasattr(storage, "get_kb_composition_status")
        assert hasattr(storage, "sync_follow_latest_bindings_for_chunk_set")

    def test_storage_v2_full_chunk_sets_use_immutable_contract_lifecycle(self, tmp_path):
        from ai_actuarial.db_models import FileChunkSet, GlobalChunk
        from ai_actuarial.storage_v2_full import StorageV2Full

        storage = StorageV2Full({"type": "sqlite", "path": str(tmp_path / "fresh.db")})
        try:
            file_url = "https://example.test/fresh.pdf"
            storage.insert_file(
                file_url,
                "hash",
                "Fresh",
                "test",
                None,
                "fresh.pdf",
                "fresh.pdf",
                10,
                "application/pdf",
            )
            profile = storage.create_chunk_profile(
                name="fresh-profile", chunk_size=100, chunk_overlap=10
            )
            chunk_set = storage.get_or_create_file_chunk_set(
                file_url=file_url,
                profile_id=profile["profile_id"],
                markdown_hash="markdown-v1",
            )
            assert chunk_set["profile_config_hash"] == profile["config_hash"]
            assert chunk_set["status"] == "building"

            published = storage.replace_global_chunks(
                chunk_set_id=chunk_set["chunk_set_id"],
                chunks=[{"chunk_index": 0, "content": "alpha", "token_count": 1}],
            )
            ready = storage.get_or_create_file_chunk_set(
                file_url=file_url,
                profile_id=profile["profile_id"],
                markdown_hash="markdown-v1",
            )
            before = (
                storage._session.query(FileChunkSet)
                .filter_by(chunk_set_id=chunk_set["chunk_set_id"])
                .one()
            )
            before_updated_at = before.updated_at

            no_op = storage.replace_global_chunks(
                chunk_set_id=chunk_set["chunk_set_id"],
                chunks=[{"chunk_index": 0, "content": "must-not-overwrite"}],
                overwrite=True,
            )
            changed_contract = storage.get_or_create_file_chunk_set(
                file_url=file_url,
                profile_id=profile["profile_id"],
                markdown_hash="markdown-v1",
                profile_config_hash="different-contract",
            )

            assert published["inserted"] == 1
            assert ready["status"] == "ready"
            assert no_op["replaced"] is False
            assert changed_contract["chunk_set_id"] != chunk_set["chunk_set_id"]
            persisted = (
                storage._session.query(GlobalChunk)
                .filter_by(chunk_set_id=chunk_set["chunk_set_id"])
                .one()
            )
            assert persisted.content == "alpha"
            assert (
                storage._session.query(FileChunkSet)
                .filter_by(chunk_set_id=chunk_set["chunk_set_id"])
                .one()
                .updated_at
                == before_updated_at
            )

            ready_zero = storage.get_or_create_file_chunk_set(
                file_url=file_url,
                profile_id=profile["profile_id"],
                markdown_hash="legacy-ready-zero",
                status="ready",
            )
            with pytest.raises(ValueError, match="ready chunk set"):
                storage.replace_global_chunks(
                    chunk_set_id=ready_zero["chunk_set_id"],
                    chunks=[{"chunk_index": 0, "content": "must-not-repair"}],
                )
        finally:
            storage.close()

    def test_storage_v2_full_migrates_existing_sqlite_chunk_identity(self, tmp_path):
        from ai_actuarial.storage_v2_full import StorageV2Full

        db_path = tmp_path / "legacy-v2.db"
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE files (
                    id INTEGER PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
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
                );
                CREATE TABLE chunk_profiles (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config_hash TEXT NOT NULL UNIQUE,
                    config_json TEXT NOT NULL,
                    chunk_size INTEGER NOT NULL,
                    chunk_overlap INTEGER NOT NULL,
                    splitter TEXT NOT NULL,
                    tokenizer TEXT NOT NULL,
                    version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE file_chunk_sets (
                    chunk_set_id TEXT PRIMARY KEY,
                    file_url TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    markdown_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(file_url, profile_id, markdown_hash),
                    FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                    FOREIGN KEY(profile_id) REFERENCES chunk_profiles(profile_id) ON DELETE CASCADE
                );
                CREATE TABLE global_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    chunk_set_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    section_hierarchy TEXT,
                    content_hash TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(chunk_set_id, chunk_index),
                    FOREIGN KEY(chunk_set_id) REFERENCES file_chunk_sets(chunk_set_id) ON DELETE CASCADE
                );
                INSERT INTO files(id, url) VALUES (
                    1, 'https://example.test/legacy.pdf'
                );
                INSERT INTO chunk_profiles VALUES (
                    'cp-1', 'Legacy', 'profile-hash', '{}', 100, 10,
                    'semantic', 'cl100k_base', 'v1', 'created', 'updated'
                );
                INSERT INTO file_chunk_sets VALUES (
                    'cs-legacy', 'https://example.test/legacy.pdf', 'cp-1',
                    'markdown-hash', 'ready', 1, 'created', 'updated'
                );
                INSERT INTO file_chunk_sets VALUES (
                    'cs-legacy-zero', 'https://example.test/legacy.pdf', 'cp-1',
                    'markdown-zero', 'ready', 0, 'created', 'updated'
                );
                INSERT INTO global_chunks VALUES (
                    'cs-legacy:0', 'cs-legacy', 0, 'legacy child', 2,
                    'Root', 'content-hash', 'created'
                );
                """)

        storage = StorageV2Full({"type": "sqlite", "path": str(db_path)})
        try:
            migrated = storage.get_or_create_file_chunk_set(
                file_url="https://example.test/legacy.pdf",
                profile_id="cp-1",
                markdown_hash="markdown-hash",
            )
            assert migrated["chunk_set_id"] == "cs-legacy"
            assert migrated["profile_config_hash"] == "profile-hash"
            assert migrated["status"] == "ready"
            no_op = storage.replace_global_chunks(
                chunk_set_id="cs-legacy",
                chunks=[{"chunk_index": 0, "content": "must-not-overwrite"}],
            )
            assert no_op["replaced"] is False
            assert (
                storage._session.connection()
                .exec_driver_sql("SELECT content FROM global_chunks WHERE chunk_id = 'cs-legacy:0'")
                .scalar_one()
                == "legacy child"
            )
            foreign_keys = (
                storage._session.connection()
                .exec_driver_sql("PRAGMA foreign_key_list(file_chunk_sets)")
                .fetchall()
            )
            assert {
                (str(row[2]), str(row[3]), str(row[4]), str(row[6])) for row in foreign_keys
            } == {
                ("files", "file_url", "url", "CASCADE"),
                ("chunk_profiles", "profile_id", "profile_id", "CASCADE"),
            }
            with pytest.raises(ValueError, match="ready chunk set"):
                storage.replace_global_chunks(
                    chunk_set_id="cs-legacy-zero",
                    chunks=[{"chunk_index": 0, "content": "must-not-repair"}],
                )

            changed = storage.get_or_create_file_chunk_set(
                file_url="https://example.test/legacy.pdf",
                profile_id="cp-1",
                markdown_hash="markdown-hash",
                profile_config_hash="new-contract",
            )
            assert changed["chunk_set_id"] != "cs-legacy"
        finally:
            storage.close()


class TestStorageV2Auth:
    """Test StorageV2 Auth operations."""

    def test_auth_methods_exist(self):
        """Test auth methods exist."""
        from ai_actuarial.storage_v2_auth import StorageV2AuthMixin

        class TestStorage(StorageV2AuthMixin):
            def __init__(self, db_config):
                self.backend = None
                self.db_path = db_config.get("path") if db_config.get("type") == "sqlite" else None

        storage = TestStorage({})
        assert hasattr(storage, "get_auth_token_by_id")
        assert hasattr(storage, "create_auth_token")
        assert hasattr(storage, "revoke_auth_token")
        assert hasattr(storage, "upsert_llm_provider")
        assert hasattr(storage, "list_llm_providers")


class TestStorageFactory:
    """Test storage factory configuration."""

    def test_create_storage_v1(self):
        """Test creating legacy Storage."""
        from ai_actuarial.storage_factory import create_storage_from_config

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"paths": {"db": db_path}}
            storage = create_storage_from_config(config)
            from ai_actuarial.storage import Storage

            assert isinstance(storage, Storage)
            storage.close()

    def test_create_storage_v2(self):
        """Test creating StorageV2."""
        from ai_actuarial.storage_factory import create_storage_from_config

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"database": {"type": "sqlite", "path": db_path}, "storage_version": "v2"}
            storage = create_storage_from_config(config)
            from ai_actuarial.storage_v2 import StorageV2

            assert isinstance(storage, StorageV2)
            storage.close()

    def test_create_storage_v2_full(self):
        """Test creating StorageV2Full."""
        from ai_actuarial.storage_factory import create_storage_from_config

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"database": {"type": "sqlite", "path": db_path}, "storage_version": "v2_full"}
            storage = create_storage_from_config(config)
            from ai_actuarial.storage_v2_full import StorageV2Full

            assert isinstance(storage, StorageV2Full)
            storage.close()


class TestDBModels:
    """Test database models."""

    def test_all_models_importable(self):
        """Test all models can be imported."""
        from ai_actuarial.db_models import (
            AuthToken,
            Blob,
            CatalogItem,
            ChunkProfile,
            File,
            FileChunkSet,
            GlobalChunk,
            Page,
        )
        from ai_actuarial.models.api_token import ApiToken

        assert File.__tablename__ == "files"
        assert Page.__tablename__ == "pages"
        assert Blob.__tablename__ == "blobs"
        assert CatalogItem.__tablename__ == "catalog_items"
        assert ChunkProfile.__tablename__ == "chunk_profiles"
        assert FileChunkSet.__tablename__ == "file_chunk_sets"
        assert GlobalChunk.__tablename__ == "global_chunks"
        assert AuthToken.__tablename__ == "auth_tokens"
        assert getattr(ApiToken, "__tablename__", None) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

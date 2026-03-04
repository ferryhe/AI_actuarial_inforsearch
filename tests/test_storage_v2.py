"""Tests for storage_v2, storage_v2_rag, and storage_v2_auth modules."""

import pytest
import tempfile
import os


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
        assert hasattr(storage, 'create_chunk_profile')
        assert hasattr(storage, 'list_chunk_profiles')
        assert hasattr(storage, 'get_chunk_profile')
        assert hasattr(storage, 'bind_chunk_set_to_kb')
        assert hasattr(storage, 'get_kb_composition_status')
        assert hasattr(storage, 'sync_follow_latest_bindings_for_chunk_set')


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
        assert hasattr(storage, 'get_auth_token_by_id')
        assert hasattr(storage, 'create_auth_token')
        assert hasattr(storage, 'revoke_auth_token')
        assert hasattr(storage, 'upsert_llm_provider')
        assert hasattr(storage, 'list_llm_providers')


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
            File, Page, Blob, CatalogItem,
            ChunkProfile, FileChunkSet, GlobalChunk,
            AuthToken,
        )
        from ai_actuarial.models.api_token import ApiToken
        assert File.__tablename__ == "files"
        assert ChunkProfile.__tablename__ == "chunk_profiles"
        assert AuthToken.__tablename__ == "auth_tokens"
        assert getattr(ApiToken, "__tablename__", None) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for YAML configuration loader.
"""

import os
import tempfile
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from config.yaml_config import (
    load_yaml_config,
    load_ai_config,
    load_rag_config,
    load_features,
    load_server_config,
    load_database_config,
    invalidate_config_cache,
    _extract_ai_config_from_env,
    _extract_rag_config_from_env,
    _extract_features_from_env,
)


class TestYAMLConfigLoader:
    """Tests for YAML configuration loader."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create a temporary config file
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "sites.yaml"
        
        # Sample configuration
        self.sample_config = {
            "defaults": {
                "user_agent": "test-agent",
                "max_pages": 100,
            },
            "paths": {
                "db": "data/primary-index.db",
            },
            "ai_config": {
                "catalog": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.7,
                    "timeout_seconds": 60,
                },
                "embeddings": {
                    "provider": "openai",
                    "model": "text-embedding-3-large",
                    "batch_size": 64,
                    "similarity_threshold": 0.4,
                },
                "chatbot": {
                    "provider": "openai",
                    "model": "gpt-4-turbo",
                    "temperature": 0.7,
                    "max_tokens": 1000,
                    "streaming_enabled": True,
                    "max_context_messages": 10,
                    "default_mode": "expert",
                    "enable_citation": True,
                    "min_citation_score": 0.4,
                    "max_citations_per_response": 5,
                },
                "ocr": {
                    "provider": "local",
                    "model": "docling",
                },
            },
            "rag_config": {
                "chunk_strategy": "semantic_structure",
                "max_chunk_tokens": 800,
                "min_chunk_tokens": 100,
                "preserve_headers": True,
                "preserve_citations": True,
                "index_type": "Flat",
            },
            "features": {
                "enable_file_deletion": False,
                "require_auth": False,
                "enable_csrf": False,
                "enable_security_headers": True,
                "expose_error_details": False,
                "enable_global_logs_api": False,
                "enable_rate_limiting": False,
            },
            "server": {
                "host": "0.0.0.0",
                "port": 5000,
                "max_content_length": 52428800,
                "fastapi_env": "production",
                "fastapi_debug": False,
            },
            "database": {
                "type": "sqlite",
                "path": "data/legacy-index.db",
            },
        }
        
        # Write sample config
        with open(self.config_path, 'w') as f:
            yaml.dump(self.sample_config, f)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
        # Invalidate cache after each test
        invalidate_config_cache()
    
    def test_load_yaml_config_from_file(self):
        """Test loading full YAML configuration from file."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            config = load_yaml_config()
            
            assert "defaults" in config
            assert "ai_config" in config
            assert config["defaults"]["user_agent"] == "test-agent"

    def test_config_path_environment_override(self):
        """CONFIG_PATH should be respected by the YAML loader."""
        with patch.dict(os.environ, {"CONFIG_PATH": str(self.config_path)}, clear=False):
            invalidate_config_cache()
            config = load_yaml_config()

        assert config["defaults"]["user_agent"] == "test-agent"
    
    def test_load_ai_config_from_yaml(self):
        """Test loading AI configuration from YAML."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            ai_config = load_ai_config()
            
            assert "catalog" in ai_config
            assert "embeddings" in ai_config
            assert "chatbot" in ai_config
            assert "ocr" in ai_config
            assert ai_config["catalog"]["model"] == "gpt-4o-mini"
            assert ai_config["embeddings"]["provider"] == "openai"
    
    def test_load_rag_config_from_yaml(self):
        """Test loading RAG configuration from YAML."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            rag_config = load_rag_config()
            
            assert rag_config["chunk_strategy"] == "semantic_structure"
            assert rag_config["max_chunk_tokens"] == 800
            assert rag_config["index_type"] == "Flat"
    
    def test_load_features_from_yaml(self):
        """Test loading feature flags from YAML."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            features = load_features()
            
            assert features["enable_file_deletion"] is False
            assert features["require_auth"] is False
            assert features["enable_security_headers"] is True
    
    def test_load_server_config_from_yaml(self):
        """Test loading server configuration from YAML."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            server = load_server_config()
            
            assert server["host"] == "0.0.0.0"
            assert server["port"] == 5000
            assert server["fastapi_env"] == "production"
    
    def test_load_database_config_from_yaml(self):
        """Test loading database configuration from the canonical paths.db YAML value."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            db_config = load_database_config()
            
            assert db_config["type"] == "sqlite"
            assert db_config["path"] == "data/primary-index.db"
            assert db_config["source"] == "paths.db"
    
    def test_fallback_to_env_when_yaml_missing(self):
        """Test fallback to environment variables when YAML sections missing."""
        # Create config without ai_config section
        minimal_config = {"defaults": {"user_agent": "test"}}
        with open(self.config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        # Set environment variables
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            with patch.dict(os.environ, {
                'OPENAI_DEFAULT_MODEL': 'gpt-3.5-turbo',
                'CHATBOT_MODEL': 'gpt-4',
                'RAG_CHUNK_STRATEGY': 'token_based',
            }):
                ai_config = load_ai_config()
                rag_config = load_rag_config()
                
                assert ai_config["catalog"]["model"] == "gpt-3.5-turbo"
                assert ai_config["chatbot"]["model"] == "gpt-4"
                assert rag_config["chunk_strategy"] == "token_based"
    
    def test_cache_invalidation(self):
        """Test configuration cache can be invalidated."""
        with patch('config.yaml_config._get_sites_config_path', return_value=self.config_path):
            # Load config first time
            config1 = load_yaml_config()
            assert config1["defaults"]["user_agent"] == "test-agent"
            
            # Modify config file
            modified_config = self.sample_config.copy()
            modified_config["defaults"]["user_agent"] = "modified-agent"
            with open(self.config_path, 'w') as f:
                yaml.dump(modified_config, f)
            
            # File metadata is part of the cache key, so in-process file edits
            # are visible without an explicit invalidation call.
            config2 = load_yaml_config()
            assert config2["defaults"]["user_agent"] == "modified-agent"
            
            # Explicit invalidation still forces a reload and keeps the new value.
            invalidate_config_cache()
            config3 = load_yaml_config()
            assert config3["defaults"]["user_agent"] == "modified-agent"
    
    def test_extract_ai_config_from_env(self):
        """Test extracting AI config from environment variables."""
        with patch.dict(os.environ, {
            'OPENAI_DEFAULT_MODEL': 'test-model',
            'CHATBOT_LLM_PROVIDER': 'deepseek',
            'CHATBOT_MODEL': 'test-chatbot',
            'CHATBOT_TEMPERATURE': '0.9',
            'CHATBOT_MAX_TOKENS': '2000',
        }):
            ai_config = _extract_ai_config_from_env()
            
            assert ai_config["catalog"]["model"] == "test-model"
            assert ai_config["chatbot"]["provider"] == "deepseek"
            assert ai_config["chatbot"]["model"] == "test-chatbot"
            assert ai_config["chatbot"]["temperature"] == 0.9
            assert ai_config["chatbot"]["max_tokens"] == 2000
    
    def test_extract_rag_config_from_env(self):
        """Test extracting RAG config from environment variables."""
        with patch.dict(os.environ, {
            'RAG_CHUNK_STRATEGY': 'token_based',
            'RAG_MAX_CHUNK_TOKENS': '1000',
            'RAG_INDEX_TYPE': 'HNSW',
        }):
            rag_config = _extract_rag_config_from_env()
            
            assert rag_config["chunk_strategy"] == "token_based"
            assert rag_config["max_chunk_tokens"] == 1000
            assert rag_config["index_type"] == "HNSW"
    
    def test_extract_features_from_env(self):
        """Test extracting feature flags from environment variables."""
        with patch.dict(os.environ, {
            'ENABLE_FILE_DELETION': 'true',
            'REQUIRE_AUTH': 'true',
            'ENABLE_CSRF': 'false',
        }):
            features = _extract_features_from_env()
            
            assert features["enable_file_deletion"] is True
            assert features["require_auth"] is True
            assert features["enable_csrf"] is False
    
    def test_boolean_parsing_from_env(self):
        """Test boolean values are correctly parsed from environment strings."""
        with patch.dict(os.environ, {
            'CHATBOT_STREAMING_ENABLED': 'false',
            'CHATBOT_ENABLE_CITATION': 'True',
            'ENABLE_FILE_DELETION': 'TRUE',
        }):
            ai_config = _extract_ai_config_from_env()
            features = _extract_features_from_env()
            
            assert ai_config["chatbot"]["streaming_enabled"] is False
            assert ai_config["chatbot"]["enable_citation"] is True
            assert features["enable_file_deletion"] is True
    
    def test_numeric_parsing_from_env(self):
        """Test numeric values are correctly parsed from environment strings."""
        with patch.dict(os.environ, {
            'CHATBOT_MAX_TOKENS': '1500',
            'CHATBOT_TEMPERATURE': '0.8',
            'RAG_MAX_CHUNK_TOKENS': '900',
        }):
            ai_config = _extract_ai_config_from_env()
            rag_config = _extract_rag_config_from_env()
            
            assert ai_config["chatbot"]["max_tokens"] == 1500
            assert ai_config["chatbot"]["temperature"] == 0.8
            assert rag_config["max_chunk_tokens"] == 900


"""
Configuration for RAG module.

Provides centralized configuration management for RAG components with
environment variable support and sensible defaults.
"""

import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class RAGConfig:
    """Configuration for RAG system."""
    
    # Chunking configuration
    chunk_strategy: Literal["semantic_structure", "token_based"] = "semantic_structure"
    max_chunk_tokens: int = 800  # Larger for academic content
    min_chunk_tokens: int = 100  # Avoid tiny fragments
    preserve_headers: bool = True  # Preserve markdown headers
    preserve_citations: bool = True  # Keep citations intact
    include_hierarchy: bool = True  # Add parent section context
    
    # Embedding configuration
    embedding_provider: Literal["openai", "local"] = "openai"
    embedding_model: str = "text-embedding-3-large"  # or "text-embedding-3-small"
    embedding_batch_size: int = 64  # Batch size for API calls
    embedding_cache_enabled: bool = True
    
    # Vector store configuration
    similarity_threshold: float = 0.4  # Filter low-quality matches
    index_type: str = "Flat"  # FAISS index type (Flat, IVF, HNSW)
    
    # API configuration
    openai_api_key: str = ""
    openai_max_retries: int = 3
    openai_timeout: int = 60
    
    # Storage paths
    data_dir: str = "data/rag"
    
    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Create configuration from environment variables."""
        return cls(
            chunk_strategy=os.getenv("RAG_CHUNK_STRATEGY", "semantic_structure"),
            max_chunk_tokens=int(os.getenv("RAG_MAX_CHUNK_TOKENS", "800")),
            min_chunk_tokens=int(os.getenv("RAG_MIN_CHUNK_TOKENS", "100")),
            preserve_headers=os.getenv("RAG_PRESERVE_HEADERS", "true").lower() == "true",
            preserve_citations=os.getenv("RAG_PRESERVE_CITATIONS", "true").lower() == "true",
            include_hierarchy=os.getenv("RAG_INCLUDE_HIERARCHY", "true").lower() == "true",
            
            embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "openai"),
            embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large"),
            embedding_batch_size=int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "64")),
            embedding_cache_enabled=os.getenv("RAG_EMBEDDING_CACHE_ENABLED", "true").lower() == "true",
            
            similarity_threshold=float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.4")),
            index_type=os.getenv("RAG_INDEX_TYPE", "Flat"),
            
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
            openai_timeout=int(os.getenv("OPENAI_TIMEOUT", "60")),
            
            data_dir=os.getenv("RAG_DATA_DIR", "data/rag"),
        )
    
    @classmethod
    def from_yaml(cls, yaml_config: dict) -> "RAGConfig":
        """Create configuration from sites.yaml rag_config and ai_config sections."""
        rag_cfg = yaml_config.get("rag_config", {})
        ai_cfg = yaml_config.get("ai_config", {}).get("embeddings", {})
        
        def safe_int(value, key: str, default: int):
            """Safely convert value to int with helpful error message."""
            if value is None:
                return default
            try:
                return int(value)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid value for {key} in sites.yaml: {value!r}. Expected integer."
                ) from e
        
        def safe_float(value, key: str, default: float):
            """Safely convert value to float with helpful error message."""
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid value for {key} in sites.yaml: {value!r}. Expected float."
                ) from e
        
        def safe_bool(value, key: str, default: bool):
            """Safely convert value to bool with proper string handling."""
            if value is None:
                return default
            # Handle string boolean values
            if isinstance(value, str):
                if value.lower() in ('true', '1', 'yes'):
                    return True
                elif value.lower() in ('false', '0', 'no'):
                    return False
                else:
                    raise ValueError(
                        f"Invalid boolean value for {key} in sites.yaml: {value!r}. "
                        f"Expected true/false, yes/no, 1/0, or boolean type."
                    )
            # Handle actual boolean values from YAML
            return bool(value)
        
        try:
            return cls(
                # Chunking configuration from rag_config
                chunk_strategy=rag_cfg.get("chunk_strategy", "semantic_structure"),
                max_chunk_tokens=safe_int(rag_cfg.get("max_chunk_tokens"), "rag_config.max_chunk_tokens", 800),
                min_chunk_tokens=safe_int(rag_cfg.get("min_chunk_tokens"), "rag_config.min_chunk_tokens", 100),
                preserve_headers=safe_bool(rag_cfg.get("preserve_headers"), "rag_config.preserve_headers", True),
                preserve_citations=safe_bool(rag_cfg.get("preserve_citations"), "rag_config.preserve_citations", True),
                include_hierarchy=safe_bool(rag_cfg.get("include_hierarchy"), "rag_config.include_hierarchy", True),
                
                # Embedding configuration from ai_config.embeddings
                embedding_provider=ai_cfg.get("provider", "openai"),
                embedding_model=ai_cfg.get("model", "text-embedding-3-large"),
                embedding_batch_size=safe_int(ai_cfg.get("batch_size"), "ai_config.embeddings.batch_size", 64),
                embedding_cache_enabled=safe_bool(ai_cfg.get("cache_enabled"), "ai_config.embeddings.cache_enabled", True),
                
                # Vector store configuration from ai_config.embeddings
                similarity_threshold=safe_float(ai_cfg.get("similarity_threshold"), "ai_config.embeddings.similarity_threshold", 0.4),
                index_type=rag_cfg.get("index_type", "Flat"),
                
                # API configuration (still from environment for sensitive data)
                openai_api_key=os.getenv("OPENAI_API_KEY", ""),
                openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
                openai_timeout=int(os.getenv("OPENAI_TIMEOUT", "60")),
                
                # Storage paths (can be overridden by environment)
                data_dir=os.getenv("RAG_DATA_DIR", "data/rag"),
            )
        except ValueError:
            # Re-raise configuration errors with context
            raise
        except Exception as e:
            raise ValueError(f"Error loading RAG configuration from sites.yaml: {e}") from e
    
    @classmethod
    def from_config(cls) -> "RAGConfig":
        """
        Create configuration from sites.yaml with .env fallback.
        
        This is the recommended method for loading configuration. It will:
        1. Try to load from sites.yaml rag_config and ai_config sections
        2. Fall back to environment variables if not found
        
        Raises:
            ValueError: If configuration values are invalid in sites.yaml
        """
        try:
            from config.yaml_config import load_yaml_config
        except (ImportError, ModuleNotFoundError):
            # If the YAML config loader is not available, fall back to env
            return cls.from_env()
        
        try:
            yaml_config = load_yaml_config()
        except (FileNotFoundError, OSError):
            # If the YAML file is missing or inaccessible, fall back to env
            return cls.from_env()
        
        # Check if either rag_config or ai_config.embeddings exist
        has_rag_config = "rag_config" in yaml_config
        has_ai_embeddings = "ai_config" in yaml_config and "embeddings" in yaml_config.get("ai_config", {})
        
        if has_rag_config or has_ai_embeddings:
            # This may raise ValueError if configuration is invalid
            return cls.from_yaml(yaml_config)
        
        # Fallback to environment variables if sections are not present
        return cls.from_env()
    
    def validate(self) -> None:
        """Validate configuration."""
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI embeddings")
        
        if self.max_chunk_tokens <= self.min_chunk_tokens:
            raise ValueError("max_chunk_tokens must be greater than min_chunk_tokens")
        
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")

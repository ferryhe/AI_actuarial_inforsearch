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
    
    def validate(self) -> None:
        """Validate configuration."""
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI embeddings")
        
        if self.max_chunk_tokens <= self.min_chunk_tokens:
            raise ValueError("max_chunk_tokens must be greater than min_chunk_tokens")
        
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")

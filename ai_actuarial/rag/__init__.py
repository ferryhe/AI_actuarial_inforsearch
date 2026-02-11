"""
RAG (Retrieval-Augmented Generation) module for AI Actuarial Info Search.

This module provides functionality for creating and managing knowledge bases
using vector embeddings and semantic search with FAISS.

Key components:
- semantic_chunking: Structure-aware chunking for legal/academic documents
- embeddings: OpenAI and local embedding generation
- vector_store: FAISS-based vector storage with incremental updates
- knowledge_base: Knowledge base management and CRUD operations
"""

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import (
    RAGException,
    ChunkingException,
    EmbeddingException,
    VectorStoreException,
    KnowledgeBaseException,
)

__all__ = [
    "RAGConfig",
    "RAGException",
    "ChunkingException",
    "EmbeddingException",
    "VectorStoreException",
    "KnowledgeBaseException",
]

__version__ = "0.1.0"

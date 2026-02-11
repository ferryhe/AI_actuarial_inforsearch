"""
Custom exceptions for RAG module.
"""


class RAGException(Exception):
    """Base exception for RAG module."""
    pass


class ChunkingException(RAGException):
    """Exception raised during chunking operations."""
    pass


class EmbeddingException(RAGException):
    """Exception raised during embedding generation."""
    pass


class VectorStoreException(RAGException):
    """Exception raised during vector store operations."""
    pass


class KnowledgeBaseException(RAGException):
    """Exception raised during knowledge base operations."""
    pass

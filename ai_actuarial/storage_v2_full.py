"""StorageV2 Full - Integrated storage with RAG and Auth support.

This module provides a complete StorageV2 implementation that combines:
- Base file/catalog operations from StorageV2
- RAG operations from StorageV2RAGMixin  
- Auth and LLM Provider operations from StorageV2AuthMixin

Usage:
    from ai_actuarial.storage_v2_full import StorageV2Full
    
    storage = StorageV2Full({"type": "sqlite", "path": "data/index.db"})
"""

from .storage_v2 import StorageV2
from .storage_v2_rag import StorageV2RAGMixin
from .storage_v2_auth import StorageV2AuthMixin

# For backward compatibility, we also provide these as separate imports
__all__ = [
    "StorageV2",
    "StorageV2RAGMixin", 
    "StorageV2AuthMixin",
]

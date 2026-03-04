"""StorageV2 Full - Integrated storage with RAG and Auth support."""

from .storage_v2 import StorageV2
from .storage_v2_rag import StorageV2RAGMixin
from .storage_v2_auth import StorageV2AuthMixin


class StorageV2Full(StorageV2, StorageV2RAGMixin, StorageV2AuthMixin):
    """Full StorageV2 implementation with RAG and Auth capabilities."""

    def __init__(self, db_config: dict):
        # Explicitly initialize StorageV2 to ensure the backend is set up
        StorageV2.__init__(self, db_config)


__all__ = [
    "StorageV2Full",
    "StorageV2",
    "StorageV2RAGMixin", 
    "StorageV2AuthMixin",
]

"""Base collector interface for data gathering workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CollectionConfig:
    """Configuration for a collection operation."""
    
    name: str
    source_type: str  # 'scheduled', 'adhoc', 'url', 'file'
    auto_download: bool = True
    check_database: bool = True
    keywords: list[str] | None = None
    file_exts: list[str] | None = None
    exclude_keywords: list[str] | None = None
    metadata: dict[str, Any] | None = None
    
    def __post_init__(self):
        """Initialize empty dict for metadata if None."""
        if self.metadata is None:
            self.metadata = {}


@dataclass
class CollectionResult:
    """Result of a collection operation."""
    
    success: bool
    items_found: int
    items_downloaded: int
    items_skipped: int
    errors: list[str]
    metadata: dict[str, Any] | None = None


class BaseCollector(ABC):
    """Base class for all collectors."""
    
    @abstractmethod
    def collect(self, config: CollectionConfig, progress_callback=None) -> CollectionResult:
        """Execute the collection operation.
        
        Args:
            config: Configuration for this collection
            progress_callback: Optional callback(current, total, status_message)
            
        Returns:
            CollectionResult with operation statistics
        """
        pass
    
    @abstractmethod
    def should_download(self, url: str, sha256: str | None = None) -> bool:
        """Check if a file should be downloaded based on database state.
        
        Args:
            url: URL of the file
            sha256: Optional SHA256 hash if known
            
        Returns:
            True if file should be downloaded, False if it exists in database
        """
        pass

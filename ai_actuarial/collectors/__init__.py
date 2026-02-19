"""Collection modules for different data gathering workflows."""

from .base import BaseCollector, CollectionConfig, CollectionResult
from .web_page import WebPageCollector

__all__ = ["BaseCollector", "CollectionConfig", "CollectionResult", "WebPageCollector"]

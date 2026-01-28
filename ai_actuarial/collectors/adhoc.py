"""Ad-hoc collection workflow - one-time manual collection operations."""

from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseCollector, CollectionConfig, CollectionResult
from ..crawler import Crawler, SiteConfig
from ..storage import Storage

logger = logging.getLogger(__name__)


class AdhocCollector(BaseCollector):
    """Collector for ad-hoc/manual collection operations."""
    
    def __init__(self, storage: Storage, crawler: Crawler):
        """Initialize ad-hoc collector.
        
        Args:
            storage: Storage instance for database operations
            crawler: Crawler instance for web scraping
        """
        self.storage = storage
        self.crawler = crawler
    
    def collect(self, config: CollectionConfig) -> CollectionResult:
        """Execute ad-hoc collection.
        
        Args:
            config: Collection configuration
            
        Returns:
            CollectionResult with statistics
        """
        logger.info("Starting ad-hoc collection: %s", config.name)
        
        errors = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0
        
        try:
            # Get site configuration from metadata
            site_configs = config.metadata.get("site_configs", [])
            
            for site_config in site_configs:
                try:
                    # Ad-hoc collections typically have lower limits
                    new_items = self.crawler.crawl_site(site_config)
                    items_found += len(new_items)
                    
                    for item in new_items:
                        if item.get("local_path"):
                            items_downloaded += 1
                        else:
                            items_skipped += 1
                            
                except Exception as e:
                    error_msg = f"Error in ad-hoc crawl of {site_config.name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            success = len(errors) == 0 or items_found > 0
            
            return CollectionResult(
                success=success,
                items_found=items_found,
                items_downloaded=items_downloaded,
                items_skipped=items_skipped,
                errors=errors,
                metadata={
                    "source_type": "adhoc",
                    "sites_processed": len(site_configs),
                }
            )
            
        except Exception as e:
            logger.exception("Ad-hoc collection failed")
            return CollectionResult(
                success=False,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[str(e)],
            )
    
    def should_download(self, url: str, sha256: str | None = None) -> bool:
        """Check if file should be downloaded.
        
        Args:
            url: URL of the file
            sha256: Optional SHA256 hash
            
        Returns:
            True if file should be downloaded
        """
        # For ad-hoc collections, always check database first
        existing = self.storage.get_file_by_url(url)
        if existing:
            logger.info("Skipping existing file: %s", url)
            return False
        
        if sha256:
            existing_by_hash = self.storage.get_file_by_sha256(sha256)
            if existing_by_hash:
                logger.info("Skipping duplicate content: %s", sha256)
                return False
        
        return True

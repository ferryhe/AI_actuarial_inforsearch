"""Scheduled collection workflow - regular periodic crawling of configured sites."""

from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseCollector, CollectionConfig, CollectionResult
from ..crawler import Crawler, SiteConfig
from ..storage import Storage

logger = logging.getLogger(__name__)


class ScheduledCollector(BaseCollector):
    """Collector for scheduled/periodic site crawling."""
    
    def __init__(self, storage: Storage, crawler: Crawler):
        """Initialize scheduled collector.
        
        Args:
            storage: Storage instance for database operations
            crawler: Crawler instance for web scraping
        """
        self.storage = storage
        self.crawler = crawler
    
    def collect(self, config: CollectionConfig) -> CollectionResult:
        """Execute scheduled collection from configured sites.
        
        Args:
            config: Collection configuration
            
        Returns:
            CollectionResult with statistics
        """
        logger.info("Starting scheduled collection: %s", config.name)
        
        errors = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0
        
        try:
            # Get site configuration from metadata
            site_configs = config.metadata.get("site_configs", [])
            
            for site_config in site_configs:
                try:
                    new_items = self.crawler.crawl_site(site_config)
                    items_found += len(new_items)
                    
                    # Count downloaded vs skipped
                    for item in new_items:
                        if item.get("local_path"):
                            items_downloaded += 1
                        else:
                            items_skipped += 1
                            
                except Exception as e:
                    error_msg = f"Error crawling {site_config.name}: {e}"
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
                    "source_type": "scheduled",
                    "sites_processed": len(site_configs),
                }
            )
            
        except Exception as e:
            logger.exception("Scheduled collection failed")
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
        # Check if URL already exists in database
        existing = self.storage.get_file_by_url(url)
        if existing:
            logger.debug("File already exists in database: %s", url)
            return False
        
        # If SHA256 provided, check for duplicate content
        if sha256:
            existing_by_hash = self.storage.get_file_by_sha256(sha256)
            if existing_by_hash:
                logger.debug("File with same SHA256 exists: %s", sha256)
                return False
        
        return True

"""URL collection workflow - collect from specific URLs."""

from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseCollector, CollectionConfig, CollectionResult
from ..crawler import Crawler, SiteConfig
from ..storage import Storage

logger = logging.getLogger(__name__)


class URLCollector(BaseCollector):
    """Collector for specific URL-based collection."""
    
    def __init__(self, storage: Storage, crawler: Crawler):
        """Initialize URL collector.
        
        Args:
            storage: Storage instance for database operations
            crawler: Crawler instance for web scraping
        """
        self.storage = storage
        self.crawler = crawler
    
    def collect(self, config: CollectionConfig, progress_callback=None) -> CollectionResult:
        """Execute URL-based collection.
        
        Args:
            config: Collection configuration with URLs in metadata
            progress_callback: Optional callback for progress updates
            
        Returns:
            CollectionResult with statistics
        """
        logger.info("Starting URL collection: %s", config.name)
        
        errors = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0
        
        try:
            urls = config.metadata.get("urls", [])
            total_urls = len(urls)
            
            if progress_callback:
                progress_callback(0, total_urls, "Starting URL collection")
            
            for i, url in enumerate(urls):
                if progress_callback:
                    progress_callback(i, total_urls, f"Processing: {url}")
                    
                try:
                    # Check if should download
                    if config.check_database and not self.should_download(url):
                        logger.info("Skipping already downloaded URL: %s", url)
                        items_skipped += 1
                        continue
                    
                    # Create minimal site config for this URL
                    site_config = SiteConfig(
                        name=config.name,
                        url=url,
                        max_pages=1,
                        max_depth=1,
                        delay_seconds=0.5,
                        keywords=config.keywords,
                        file_exts=config.file_exts,
                        exclude_keywords=config.exclude_keywords,
                    )
                    
                    new_items = self.crawler.scan_page_for_files(
                        url, site_config, source_site=config.name, progress_callback=lambda c, t, m: None
                    )
                    
                    items_found += len(new_items)
                    
                    for item in new_items:
                        if item.get("local_path"):
                            items_downloaded += 1
                        else:
                            items_skipped += 1
                            
                except Exception as e:
                    error_msg = f"Error collecting from URL {url}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            if progress_callback:
                progress_callback(total_urls, total_urls, "Completed")
            
            success = len(errors) == 0 or items_found > 0
            
            return CollectionResult(
                success=success,
                items_found=items_found,
                items_downloaded=items_downloaded,
                items_skipped=items_skipped,
                errors=errors,
                metadata={
                    "source_type": "url",
                    "urls_processed": len(urls),
                }
            )
            
        except Exception as e:
            logger.exception("URL collection failed")
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
        existing = self.storage.get_file_by_url(url)
        if existing:
            logger.debug("URL already in database: %s", url)
            return False
        
        if sha256:
            existing_by_hash = self.storage.get_file_by_sha256(sha256)
            if existing_by_hash:
                logger.debug("Content already in database: %s", sha256)
                return False
        
        return True

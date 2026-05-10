"""Scheduled collection workflow - regular periodic crawling of configured sites."""

from __future__ import annotations

import logging
import re

from .base import BaseCollector, CollectionConfig, CollectionResult
from ..crawler import Crawler, SiteConfig
from ..storage import Storage

logger = logging.getLogger(__name__)

_BLOCKED_ERROR_PATTERNS = (
    ("http_403", re.compile(r"\b403\b|forbidden", re.IGNORECASE)),
    ("http_429", re.compile(r"\b429\b|too many requests|rate limit", re.IGNORECASE)),
    ("access_denied", re.compile(r"access denied", re.IGNORECASE)),
    ("cloudflare", re.compile(r"cloudflare", re.IGNORECASE)),
    ("sucuri", re.compile(r"sucuri", re.IGNORECASE)),
    ("timeout", re.compile(r"timed?\s*out|timeout", re.IGNORECASE)),
    ("zero_pages_visited", re.compile(r"\b0\s+pages?\s+visited\b", re.IGNORECASE)),
)


def _crawler_diagnostic_error_text(crawler: Crawler) -> str:
    diagnostic: dict[str, object] = {}
    get_diagnostic = getattr(crawler, "get_last_crawl_diagnostic", None)
    if callable(get_diagnostic):
        try:
            raw = get_diagnostic()
            if isinstance(raw, dict):
                diagnostic = raw
        except Exception:  # noqa: BLE001
            diagnostic = {}
    if not diagnostic:
        raw = getattr(crawler, "last_crawl_diagnostic", None)
        if isinstance(raw, dict):
            diagnostic = raw

    error_text = str(diagnostic.get("error_text") or "").strip()
    if error_text:
        return error_text
    request_errors = diagnostic.get("request_errors")
    if isinstance(request_errors, (list, tuple)):
        return "; ".join(str(error).strip() for error in request_errors if str(error).strip())
    return ""


def _classify_site_outcome(error_text: str, *, items_found: int) -> tuple[str, bool]:
    """Classify direct crawl outcome for later fallback decisions."""
    haystack = str(error_text or "")
    for reason, pattern in _BLOCKED_ERROR_PATTERNS:
        if pattern.search(haystack):
            return reason, True
    if haystack:
        return "error", False
    if items_found <= 0:
        return "zero_results", False
    return "success", False


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
    
    def collect(self, config: CollectionConfig, progress_callback=None) -> CollectionResult:
        """Execute scheduled collection from configured sites.
        
        Args:
            config: Collection configuration
            progress_callback: Optional callback for progress updates
            
        Returns:
            CollectionResult with statistics
        """
        logger.info("Starting scheduled collection: %s", config.name)
        
        errors = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0
        site_results = []
        
        try:
            # Get site configuration from metadata
            site_configs = config.metadata.get("site_configs", [])
            total_sites = len(site_configs)
            
            if progress_callback:
                progress_callback(0, total_sites, "Starting scheduled collection")
            
            for i, site_config in enumerate(site_configs):
                
                # Wrapper for site-level progress to include site info
                def site_progress(c, t, m):
                    if progress_callback:
                        # We can either show per-site progress or overall
                        # For now, let's show "Site X/Y: [Site Progress]"
                        # and pass the site's local progress numbers.
                        # The UI might fluctuate but at least it moves.
                        prefix = f"[{i+1}/{total_sites}] {site_config.name}"
                        progress_callback(c, t, f"{prefix}: {m}")
                
                try:
                    new_items = self.crawler.crawl_site(site_config, progress_callback=site_progress)
                    site_items_found = len(new_items)
                    site_items_downloaded = 0
                    site_items_skipped = 0
                    items_found += site_items_found
                    
                    # Count downloaded vs skipped
                    for item in new_items:
                        if item.get("local_path"):
                            site_items_downloaded += 1
                            items_downloaded += 1
                        else:
                            site_items_skipped += 1
                            items_skipped += 1

                    diagnostic_error_text = _crawler_diagnostic_error_text(self.crawler) if site_items_found <= 0 else ""
                    reason, blocked = _classify_site_outcome(diagnostic_error_text, items_found=site_items_found)
                    site_results.append(
                        {
                            "name": site_config.name,
                            "url": site_config.url,
                            "items_found": site_items_found,
                            "items_downloaded": site_items_downloaded,
                            "items_skipped": site_items_skipped,
                            "success": not blocked,
                            "failed": blocked,
                            "error": diagnostic_error_text,
                            "error_text": diagnostic_error_text,
                            "blocked": blocked,
                            "classification": reason,
                            "fallback_reason": reason,
                        }
                    )
                except Exception as e:
                    error_msg = f"Error crawling {site_config.name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    reason, blocked = _classify_site_outcome(error_msg, items_found=0)
                    site_results.append(
                        {
                            "name": site_config.name,
                            "url": site_config.url,
                            "items_found": 0,
                            "items_downloaded": 0,
                            "items_skipped": 0,
                            "success": False,
                            "failed": True,
                            "error": error_msg,
                            "error_text": error_msg,
                            "blocked": blocked,
                            "classification": reason,
                            "fallback_reason": reason,
                        }
                    )
            
            if progress_callback:
                progress_callback(total_sites, total_sites, "Completed")
            
            success = len(errors) == 0 or items_found > 0
            
            return CollectionResult(
                success=success,
                items_found=items_found,
                items_downloaded=items_downloaded,
                items_skipped=items_skipped,
                errors=errors,
                metadata={
                    "source_type": config.source_type,
                    "sites_processed": len(site_configs),
                    "site_results": site_results,
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

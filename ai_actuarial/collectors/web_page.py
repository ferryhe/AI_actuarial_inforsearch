"""Web page content collection workflow.

Extracts and stores readable text content directly from HTML web pages,
inspired by smart-scraping approaches (e.g. ScrapeGraphAI). Unlike the file-
based collectors that only download linked documents (PDF, DOCX …), this
collector captures the article/body text of HTML pages themselves and saves it
as Markdown for downstream RAG/cataloguing pipelines.
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .base import BaseCollector, CollectionConfig, CollectionResult
from ..storage import Storage
from ..utils import extract_metadata

logger = logging.getLogger(__name__)

# Default timeout for fetching a web page (seconds)
_DEFAULT_FETCH_TIMEOUT = 30
# Minimum length of extracted text to be worth storing (characters)
_MIN_CONTENT_LENGTH = 100
# Maximum attempts to find a unique filename before falling back to timestamp
_MAX_CONFLICT_ATTEMPTS = 1000


class WebPageCollector(BaseCollector):
    """Collector that extracts readable text content from HTML web pages.

    Uses ``trafilatura`` for high-quality article-text extraction.  The
    extracted text is saved as a ``.md`` file so that existing RAG and
    cataloguing pipelines can process it without changes.

    Inspired by ScrapeGraphAI's approach of treating *page content* as a
    first-class collectible, not just files linked from pages.
    """

    def __init__(
        self,
        storage: Storage,
        download_dir: str,
        user_agent: str = "AI-Actuarial-InfoSearch/0.1",
    ) -> None:
        """Initialise the collector.

        Args:
            storage: Storage instance for database operations.
            download_dir: Base directory for storing extracted content files.
            user_agent: User-Agent header string for HTTP requests.
        """
        self.storage = storage
        self.download_dir = Path(download_dir)
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # BaseCollector interface
    # ------------------------------------------------------------------

    def collect(
        self, config: CollectionConfig, progress_callback=None
    ) -> CollectionResult:
        """Extract and store text content from a list of web page URLs.

        Expected ``config.metadata`` keys:
            urls (list[str]): Web page URLs whose content should be extracted.

        Args:
            config: Collection configuration.
            progress_callback: Optional ``(current, total, message)`` callback.

        Returns:
            :class:`CollectionResult` with operation statistics.
        """
        logger.info("Starting web-page content collection: %s", config.name)

        errors: list[str] = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0

        try:
            urls: list[str] = config.metadata.get("urls", [])
            total_urls = len(urls)

            if progress_callback:
                progress_callback(0, total_urls, "Starting web-page collection")

            for i, url in enumerate(urls):
                if progress_callback:
                    progress_callback(i, total_urls, f"Processing: {url}")

                try:
                    if config.check_database and not self.should_download(url):
                        logger.info(
                            "Skipping already-collected web page: %s", url
                        )
                        items_skipped += 1
                        continue

                    item = self._collect_page(url, config)
                    if item is None:
                        # Extraction failed or content too short – skip
                        items_skipped += 1
                    else:
                        items_found += 1
                        items_downloaded += 1

                except Exception as exc:
                    error_msg = f"Error collecting web page {url}: {exc}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            if progress_callback:
                progress_callback(total_urls, total_urls, "Completed")

            success = len(errors) == 0 or items_downloaded > 0

            return CollectionResult(
                success=success,
                items_found=items_found,
                items_downloaded=items_downloaded,
                items_skipped=items_skipped,
                errors=errors,
                metadata={
                    "source_type": "web_page",
                    "urls_processed": total_urls,
                },
            )

        except Exception as exc:
            logger.exception("Web-page collection failed")
            return CollectionResult(
                success=False,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[str(exc)],
            )

    def should_download(self, url: str, sha256: str | None = None) -> bool:
        """Return ``True`` if the URL has not been collected before.

        Args:
            url: Web page URL.
            sha256: Optional SHA256 of the extracted content (if already known).

        Returns:
            ``True`` if the page should be collected.
        """
        if self.storage.file_exists(url):
            logger.debug("Web page already in database: %s", url)
            return False

        if sha256 and self.storage.file_exists_by_hash(sha256):
            logger.debug("Content already in database (hash match): %s", sha256)
            return False

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_html(self, url: str) -> tuple[bytes, dict[str, str], str]:
        """Fetch the raw HTML for *url*.

        Returns:
            Tuple of ``(raw_bytes, response_headers, final_url)``.

        Raises:
            urllib.error.URLError: On network errors.
        """
        req = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent}
        )
        with urllib.request.urlopen(req, timeout=_DEFAULT_FETCH_TIMEOUT) as resp:
            data = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return data, headers, resp.geturl()

    def _extract_text(self, html: str, url: str) -> str | None:
        """Extract clean article text from *html* using trafilatura.

        Falls back to a simple HTML-strip if trafilatura is unavailable.

        Args:
            html: Raw HTML source.
            url: Source URL (used as a hint by trafilatura).

        Returns:
            Extracted Markdown/plain text, or ``None`` if extraction failed.
        """
        try:
            import trafilatura  # type: ignore

            text = trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                favor_precision=True,
            )
            return text or None
        except ImportError:
            logger.warning(
                "trafilatura not installed; falling back to basic text extraction"
            )
            # Simple fallback: strip tags
            from ..utils import html_to_text

            return html_to_text(html) or None

    def _save_content(
        self, url: str, content: str, source_site: str
    ) -> Path:
        """Persist *content* to a ``.md`` file under ``download_dir``.

        The file is placed in a sub-directory named after the URL's hostname
        so that it matches the layout used by the :class:`~ai_actuarial.crawler.Crawler`.

        Args:
            url: Source URL (used for directory naming and filename generation).
            content: Extracted Markdown text.
            source_site: Human-readable name of the source site.

        Returns:
            Path to the saved file.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.replace(":", "_") or "unknown_domain"
        target_dir = self.download_dir / domain / "_web_pages"
        target_dir.mkdir(parents=True, exist_ok=True)

        # Build a safe filename from the URL path
        path_part = parsed.path.strip("/").replace("/", "_") or "index"
        # Truncate to avoid excessively long filenames
        safe_name = _sanitize_filename(path_part)[:100] or "page"
        filename = f"{safe_name}.md"

        target_path = _resolve_conflict(target_dir, filename)
        target_path.write_text(content, encoding="utf-8")
        return target_path

    def _collect_page(
        self, url: str, config: CollectionConfig
    ) -> dict | None:
        """Fetch, extract, and store content for a single web page URL.

        Args:
            url: Web page URL.
            config: Collection configuration (used for ``source_site``).

        Returns:
            Dict with file metadata on success, or ``None`` if collection
            should be skipped.
        """
        try:
            raw_bytes, headers, final_url = self._fetch_html(url)
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return None

        # Skip non-HTML responses
        content_type = headers.get("content-type", "")
        if content_type and "html" not in content_type.lower():
            logger.debug("Skipping non-HTML URL %s (content-type: %s)", url, content_type)
            return None

        html = raw_bytes.decode("utf-8", errors="ignore")
        title, published_time = extract_metadata(html, final_url)

        text_content = self._extract_text(html, final_url)
        if not text_content or len(text_content) < _MIN_CONTENT_LENGTH:
            logger.debug(
                "Skipping %s: extracted content too short (%d chars)",
                url,
                len(text_content) if text_content else 0,
            )
            return None

        # Prepend title as a top-level heading for better RAG quality
        if title:
            text_content = f"# {title}\n\n{text_content}"

        sha256 = hashlib.sha256(text_content.encode("utf-8")).hexdigest()

        # Deduplication by content hash
        if self.storage.file_exists_by_hash(sha256):
            logger.info(
                "Skipping %s: same content already in database (sha256=%s)",
                url,
                sha256,
            )
            return None

        # Save to disk
        target_path = self._save_content(final_url, text_content, config.name)
        bytes_size = len(text_content.encode("utf-8"))

        # Store relative path (parent of download_dir → data/)
        base_dir = self.download_dir.parent.resolve()
        try:
            relative_path = str(target_path.resolve().relative_to(base_dir))
        except ValueError:
            relative_path = str(target_path.resolve())

        ts = self.storage.now()
        self.storage._conn.execute(
            """
            INSERT OR REPLACE INTO files (
                url, sha256, title, source_site, source_page_url,
                original_filename, local_path, bytes, content_type,
                published_time, first_seen, last_seen, crawl_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                final_url,
                sha256,
                title,
                config.name,
                final_url,
                target_path.name,
                relative_path,
                bytes_size,
                "text/markdown",
                published_time,
                ts,
                ts,
                ts,
            ),
        )
        self.storage._conn.commit()

        logger.info(
            "Saved web page content: %s (%d bytes) -> %s",
            title or url,
            bytes_size,
            target_path,
        )

        return {
            "url": final_url,
            "sha256": sha256,
            "title": title,
            "source_site": config.name,
            "source_page_url": final_url,
            "original_filename": target_path.name,
            "local_path": relative_path,
            "bytes": bytes_size,
            "content_type": "text/markdown",
            "published_time": published_time,
        }


# ---------------------------------------------------------------------------
# Module-level filename helpers (mirrors patterns in FileCollector / Crawler)
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """Replace characters that are unsafe in filenames."""
    import re

    name = name.strip().replace("\x00", "")
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "page"


def _resolve_conflict(folder: Path, filename: str) -> Path:
    """Return a unique path inside *folder*, appending ``_N`` if needed.

    Tries up to ``_MAX_CONFLICT_ATTEMPTS`` numeric suffixes before falling back
    to a timestamp-based suffix, which is always unique.
    """
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(1, _MAX_CONFLICT_ATTEMPTS + 1):
        alt = folder / f"{stem}_{i}{suffix}"
        if not alt.exists():
            return alt
    return folder / f"{stem}_{int(time.time())}{suffix}"

from __future__ import annotations

import logging
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
import hashlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    import curl_cffi.requests as _curl_requests  # type: ignore
    _CURL_CFFI_AVAILABLE = True
    logger.debug("curl_cffi available; using Chrome impersonation for HTTP requests")
except ImportError:
    _curl_requests = None  # type: ignore
    _CURL_CFFI_AVAILABLE = False

from .storage import Storage
from .utils import (
    extract_metadata,
    html_to_text,
    normalize_url,
    same_domain,
    sleep_with_jitter,
)


DEFAULT_FILE_EXTS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


@dataclass
class SiteConfig:
    name: str
    url: str
    max_pages: int = 200
    max_depth: int = 2
    delay_seconds: float = 0.5
    keywords: list[str] | None = None
    file_exts: list[str] | None = None
    exclude_keywords: list[str] | None = None
    exclude_prefixes: list[str] | None = None
    collect_page_content: bool = False  # Also save text extracted from HTML pages
    content_selector: str | None = None  # CSS selector to narrow link extraction to content area
    allow_url_patterns: list[str] | None = None  # Regex allow-list for sub-page URLs (Scrapy-style); if set, only matching sub-pages are queued
    queries: list[str] | None = None  # Site-specific search queries to supplement or bypass direct crawling (useful for anti-bot-protected sites)
    check_database: bool = True


class Crawler:
    def __init__(self, storage: Storage, download_dir: str, user_agent: str, stop_check=None) -> None:
        self.storage = storage
        self.download_dir = download_dir
        self.user_agent = user_agent
        self.stop_check = stop_check
        self._cleanup_old_temp_files()

    def _cleanup_old_temp_files(self, max_age_hours: int = 24) -> None:
        """Clean up stale .part files from previous failed downloads."""
        download_path = Path(self.download_dir)
        if not download_path.exists():
            return
        cutoff = time.time() - (max_age_hours * 3600)
        cleaned = 0
        for tmp_dir in download_path.glob("*/_tmp"):
            if not tmp_dir.is_dir():
                continue
            for part_file in tmp_dir.glob("*.part"):
                try:
                    if part_file.stat().st_mtime < cutoff:
                        part_file.unlink()
                        cleaned += 1
                except Exception:
                    pass
        if cleaned > 0:
            logger.info("Cleaned up %d stale temporary files", cleaned)

    def _request(self, url: str) -> tuple[bytes, dict[str, str], str]:
        if _CURL_CFFI_AVAILABLE:
            try:
                resp = _curl_requests.get(
                    url,
                    impersonate="chrome",
                    headers={"User-Agent": self.user_agent},
                    timeout=30,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.content
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return data, headers, resp.url
            except Exception as exc:
                logger.debug("curl_cffi request failed for %s, falling back to urllib: %s", url, exc)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return data, headers, resp.geturl()

    def _download_file(self, url: str, target_dir: Path) -> tuple[Path, dict[str, str], str, str, int]:
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = target_dir / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"download_{time.time_ns()}.part"
        hasher = hashlib.sha256()
        size = 0
        success = False
        try:
            if _CURL_CFFI_AVAILABLE:
                try:
                    resp = _curl_requests.get(
                        url,
                        impersonate="chrome",
                        headers={"User-Agent": self.user_agent},
                        timeout=60,
                        allow_redirects=True,
                        stream=True,
                    )
                    resp.raise_for_status()
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    final_url = resp.url
                    with open(tmp_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 128):
                            if chunk:
                                f.write(chunk)
                                hasher.update(chunk)
                                size += len(chunk)
                    success = True
                    logger.debug("Downloaded %s (%d bytes) via curl_cffi", url, size)
                    return tmp_path, headers, final_url, hasher.hexdigest(), size
                except Exception as exc:
                    logger.debug("curl_cffi download failed for %s, falling back to urllib: %s", url, exc)
                    # Reset state for fallback attempt
                    try:
                        if tmp_path.exists():
                            tmp_path.unlink()
                    except Exception:
                        pass
                    tmp_path = tmp_dir / f"download_{time.time_ns()}.part"
                    hasher = hashlib.sha256()
                    size = 0

            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                final_url = resp.geturl()
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 128)
                        if not chunk:
                            break
                        f.write(chunk)
                        hasher.update(chunk)
                        size += len(chunk)
            success = True
            logger.debug("Downloaded %s (%d bytes)", url, size)
            return tmp_path, headers, final_url, hasher.hexdigest(), size
        finally:
            if not success and tmp_path.exists():
                try:
                    tmp_path.unlink()
                    logger.debug("Cleaned up failed download: %s", tmp_path)
                except Exception:
                    pass

    def _is_file_url(self, url: str, exts: set[str]) -> bool:
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in exts)

    def _is_excluded(self, text: str, exclude: list[str]) -> bool:
        """Check if text contains any excluded keyword."""
        text = text.lower()
        return any(k in text for k in exclude)

    def _has_excluded_prefix(self, name: str, prefixes: list[str]) -> bool:
        """Check if name starts with any excluded prefix."""
        name = name.lower()
        return any(name.startswith(p) for p in prefixes)
    
    def _should_exclude_url(self, url: str, exclude: list[str] | None, exclude_prefixes: list[str] | None) -> bool:
        """Consolidated check for URL exclusion based on keywords and prefixes.
        
        Args:
            url: URL to check
            exclude: List of excluded keywords
            exclude_prefixes: List of excluded filename prefixes
            
        Returns:
            True if URL should be excluded
        """
        if exclude and self._is_excluded(url, exclude):
            return True
        if exclude_prefixes and self._has_excluded_prefix(os.path.basename(url), exclude_prefixes):
            return True
        return False

    def _extract_links(self, base_url: str, html: str, content_selector: str | None = None) -> list[tuple[str, str]]:
        # If a content_selector is given, narrow HTML to matching section(s)
        if content_selector:
            html = self._extract_content_html(html, content_selector) or html
        out: list[tuple[str, str]] = []
        for match in re.finditer(
            r'<a[^>]+href=["\\\'](.*?)["\\\'][^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            href = match.group(1)
            text = re.sub(r"<[^>]+>", " ", match.group(2))
            text = re.sub(r"\s+", " ", text).strip()
            norm = normalize_url(base_url, href)
            if norm:
                out.append((norm, text))
        if out:
            return out
        links = re.findall(r'href=["\\\'](.*?)["\\\']', html, flags=re.IGNORECASE)
        for link in links:
            norm = normalize_url(base_url, link)
            if norm:
                out.append((norm, ""))
        return out

    def _link_matches_keywords(self, url: str, text: str, keywords: list[str]) -> bool:
        if not keywords:
            return True
        base = os.path.basename(url)
        hay = f"{url} {base} {text}".lower()
        return any(k in hay for k in keywords)

    @staticmethod
    def _extract_content_html(html: str, selector: str) -> str | None:
        """Extract HTML from elements matching a CSS selector.

        Falls back to ``None`` if *beautifulsoup4* is not available or no
        elements match.
        """
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except ImportError:
            logger.warning("beautifulsoup4 not installed; content_selector ignored")
            return None
        soup = BeautifulSoup(html, "html.parser")
        try:
            parts = soup.select(selector)
        except Exception as exc:
            logger.warning("Invalid content_selector '%s'; ignoring selector: %s", selector, exc)
            return None
        if not parts:
            return None
        return "\n".join(str(p) for p in parts)

    def _load_sitemap(self, site_url: str) -> list[str]:
        sitemap_url = site_url.rstrip("/") + "/sitemap.xml"
        try:
            data, _, _ = self._request(sitemap_url)
        except Exception:
            logger.debug("No sitemap found at %s", sitemap_url)
            return []
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            logger.warning("Failed to parse sitemap at %s", sitemap_url)
            return []

        urls: list[str] = []
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.findall(".//ns:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
        logger.info("Loaded %d URLs from sitemap: %s", len(urls), sitemap_url)
        return urls

    def crawl_site(self, cfg: SiteConfig, progress_callback=None) -> list[dict]:
        # Check stop signal at start
        if self.stop_check and self.stop_check():
            logger.info("Crawl stopped by user signal.")
            return []

        logger.info("Starting crawl of site: %s (max_pages=%d, max_depth=%d)", 
                   cfg.name, cfg.max_pages, cfg.max_depth)
        
        if progress_callback:
            progress_callback(0, cfg.max_pages, f"Starting crawl of {cfg.name}")

        keywords = [k.lower() for k in (cfg.keywords or [])]
        exts = {e.lower() for e in (cfg.file_exts or [])} or DEFAULT_FILE_EXTS
        exclude = [k.lower() for k in (cfg.exclude_keywords or [])]
        exclude_prefixes = [p.lower() for p in (cfg.exclude_prefixes or [])]
        # Compile allow_url_patterns to regex; if set, only matching URLs are queued / downloaded.
        # Invalid patterns are skipped with a warning rather than aborting the crawl.
        allow_patterns = []
        for raw_pat in (cfg.allow_url_patterns or []):
            try:
                allow_patterns.append(re.compile(raw_pat))
            except re.error as exc:
                logger.warning(
                    "Skipping invalid allow_url_pattern %r for site %r: %s",
                    raw_pat, cfg.name, exc
                )
        new_items: list[dict] = []

        sitemap_urls = self._load_sitemap(cfg.url)
        if sitemap_urls:
            # When allow_url_patterns is configured, only seed URLs that match at
            # least one pattern — otherwise the allow-list is bypassed for sitemaps.
            if allow_patterns:
                sitemap_urls = [
                    u for u in sitemap_urls
                    if any(p.search(u) for p in allow_patterns)
                ]
            if sitemap_urls:
                page_queue: deque[tuple[str, int]] = deque(
                    [(u, 0) for u in sitemap_urls[: cfg.max_pages]]
                )
            else:
                # All sitemap URLs were filtered out by allow_patterns;
                # fall back to the site root so the crawl is not silently a no-op.
                logger.debug(
                    "Sitemap URLs all filtered by allow_url_patterns for %r; "
                    "falling back to seed URL %s",
                    cfg.name, cfg.url,
                )
                page_queue = deque([(cfg.url, 0)])
        else:
            page_queue = deque([(cfg.url, 0)])

        seen_pages: set[str] = set()
        pages_fetched = 0

        while page_queue and pages_fetched < cfg.max_pages:
            # Check stop signal in loop
            if self.stop_check and self.stop_check():
                logger.info("Crawl stopped by user signal.")
                break

            url, depth = page_queue.popleft()
            if url in seen_pages:
                continue
            if not same_domain(cfg.url, url):
                continue
            if self._should_exclude_url(url, exclude, exclude_prefixes):
                continue

            seen_pages.add(url)
            
            if progress_callback:
                progress_callback(pages_fetched, cfg.max_pages, f"Crawling: {url}")

            try:
                data, headers, final_url = self._request(url)
            except Exception:
                continue

            pages_fetched += 1

            self.storage.mark_page_seen(final_url)

            if self._should_exclude_url(final_url, exclude, exclude_prefixes):
                continue

            if self._is_file_url(final_url, exts):
                if cfg.check_database and self.storage.file_exists(final_url):
                    sleep_with_jitter(cfg.delay_seconds)
                    continue
                parsed = urlparse(final_url)
                domain = parsed.netloc.replace(":", "_")
                target_dir = Path(self.download_dir) / domain
                tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                    final_url, target_dir
                )
                if self._should_exclude_url(ffinal, exclude, exclude_prefixes):
                    if tmp_path.exists():
                        tmp_path.unlink()
                    sleep_with_jitter(cfg.delay_seconds)
                    continue
                item = self._handle_file(
                    ffinal,
                    tmp_path,
                    fheaders,
                    sha256,
                    bytes_size,
                    cfg,
                    source_page_url=None,
                )
                if item:
                    new_items.append(item)
                sleep_with_jitter(cfg.delay_seconds)
                continue

            try:
                html = data.decode("utf-8", errors="ignore")
            except Exception:
                html = ""

            page_title, published_time = extract_metadata(html, final_url)

            page_text = html_to_text(html).lower()
            is_relevant = any(k in page_text for k in keywords) if keywords else True

            # Optionally save the HTML page content itself as Markdown
            if cfg.collect_page_content and is_relevant:
                page_item = self._handle_page_content(
                    final_url, html, page_title, published_time, cfg
                )
                if page_item:
                    new_items.append(page_item)

            links = self._extract_links(final_url, html, content_selector=cfg.content_selector)
            for link, link_text in links:
                if exclude and self._is_excluded(link, exclude):
                    continue
                if exclude_prefixes and self._has_excluded_prefix(os.path.basename(link), exclude_prefixes):
                    continue
                if self._is_file_url(link, exts):
                    # When allow_url_patterns is configured, enforce it on file links too
                    # (e.g. /globalassets/ pattern gates PDF downloads, not just subpage queuing).
                    if allow_patterns and not any(p.search(link) for p in allow_patterns):
                        continue
                    # Without allow_patterns, include the file if the page it lives on
                    # is topically relevant OR the link URL/text matches keywords.
                    # Both conditions were originally OR'd; dropping is_relevant caused
                    # generic filenames (e.g. bulletin.pdf) on relevant pages to be missed.
                    if not allow_patterns and keywords:
                        if not (is_relevant or self._link_matches_keywords(link, link_text, keywords)):
                            continue
                    if cfg.check_database and self.storage.file_exists(link):
                        continue
                    try:
                        parsed = urlparse(link)
                        domain = parsed.netloc.replace(":", "_")
                        target_dir = Path(self.download_dir) / domain
                        tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                            link, target_dir
                        )
                    except Exception:
                        continue
                    
                    # Enhanced Exclusion Check:
                    # Use consolidated helper to check both URL and filename against
                    # exclude patterns and excluded prefixes.
                    if self._should_exclude_url(ffinal, exclude, exclude_prefixes) or \
                       self._should_exclude_url(tmp_path.name, exclude, exclude_prefixes):
                        logger.info(
                            "Excluding downloaded file based on exclude rules: url=%s, name=%s",
                            ffinal,
                            tmp_path.name,
                        )
                        if tmp_path.exists():
                            tmp_path.unlink()
                        continue
                    item = self._handle_file(
                        ffinal,
                        tmp_path,
                        fheaders,
                        sha256,
                        bytes_size,
                        cfg,
                        source_page_url=final_url,
                        page_title=page_title,
                        published_time=published_time,
                        link_text=link_text,
                    )
                    if item:
                        new_items.append(item)
                else:
                    if depth + 1 <= cfg.max_depth:
                        if allow_patterns:
                            # Only queue sub-pages that match at least one allow pattern
                            if any(p.search(link) for p in allow_patterns):
                                page_queue.append((link, depth + 1))
                        else:
                            # No allow patterns: always queue, rely on exclude filters
                            page_queue.append((link, depth + 1))

            sleep_with_jitter(cfg.delay_seconds)

        logger.info("Crawl completed for %s: %d new files found, %d pages visited", 
                   cfg.name, len(new_items), pages_fetched)
        return new_items

    def _extract_text_from_html(self, html: str, url: str) -> str | None:
        """Extract clean article text from HTML using trafilatura.

        Falls back to a basic tag-strip if trafilatura is unavailable.

        Args:
            html: Raw HTML source.
            url: Source URL (used as a hint by trafilatura).

        Returns:
            Extracted Markdown/plain text, or ``None`` if extraction failed or
            the content is too short to be useful.
        """
        _MIN_CONTENT_LENGTH = 100
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
        except ImportError:
            text = html_to_text(html) or None

        if text and len(text) >= _MIN_CONTENT_LENGTH:
            return text
        return None

    def _handle_page_content(
        self,
        url: str,
        html: str,
        page_title: str | None,
        published_time: str | None,
        cfg: SiteConfig,
    ) -> dict | None:
        """Extract and store text content from an HTML page as a Markdown file.

        This method is called by :meth:`crawl_site` when
        ``cfg.collect_page_content`` is ``True``.  It mirrors the approach used
        by ScrapeGraphAI: treat the page *content itself* as a collectible
        document, not just the files it links to.

        Args:
            url: Final (possibly redirected) URL of the page.
            html: Raw HTML source.
            page_title: Title extracted from HTML (may be ``None``).
            published_time: Publication time extracted from HTML (may be ``None``).
            cfg: Site configuration.

        Returns:
            File-metadata dict on success, or ``None`` if the page should be
            skipped (already stored, content too short, etc.).
        """
        if cfg.check_database and self.storage.file_exists(url):
            return None

        text_content = self._extract_text_from_html(html, url)
        if not text_content:
            return None

        if page_title:
            text_content = f"# {page_title}\n\n{text_content}"

        sha256 = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        if cfg.check_database and self.storage.file_exists_by_hash(sha256):
            logger.debug(
                "Skipping page %s: same content already stored (sha256=%s)", url, sha256
            )
            return None

        # Persist as a Markdown file under <domain>/_web_pages/
        parsed = urlparse(url)
        domain = parsed.netloc.replace(":", "_") or "unknown_domain"
        target_dir = Path(self.download_dir) / domain / "_web_pages"
        target_dir.mkdir(parents=True, exist_ok=True)

        path_part = parsed.path.strip("/").replace("/", "_") or "index"
        safe_name = self._sanitize_filename(path_part)[:100] or "page"
        path = self._resolve_conflict(target_dir, f"{safe_name}.md")
        path.write_text(text_content, encoding="utf-8")

        bytes_size = len(text_content.encode("utf-8"))

        # Store relative path to keep it consistent with file downloads
        base_dir = Path(self.download_dir).parent.resolve()
        try:
            relative_path = str(path.resolve().relative_to(base_dir))
        except ValueError:
            relative_path = str(path.resolve())

        ts = self.storage.now()
        self.storage._conn.execute(
            """
            INSERT OR IGNORE INTO files (
                url, sha256, title, source_site, source_page_url,
                original_filename, local_path, bytes, content_type,
                published_time, first_seen, last_seen, crawl_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                sha256,
                page_title,
                cfg.name,
                url,
                path.name,
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
            "Saved page content: %s (%d bytes) -> %s",
            page_title or url,
            bytes_size,
            path,
        )

        return {
            "url": url,
            "sha256": sha256,
            "title": page_title,
            "source_site": cfg.name,
            "source_page_url": url,
            "original_filename": path.name,
            "local_path": relative_path,
            "bytes": bytes_size,
            "content_type": "text/markdown",
            "published_time": published_time,
        }

    def _handle_file(
        self,
        url: str,
        tmp_path: Path,
        headers: dict[str, str],
        sha256: str,
        bytes_size: int,
        cfg: SiteConfig,
        source_page_url: str | None,
        page_title: str | None = None,
        published_time: str | None = None,
        source_site_override: str | None = None,
        link_text: str | None = None,
    ) -> dict | None:
        if self.storage.file_exists(url):
            if tmp_path.exists():
                tmp_path.unlink()
            return None

        parsed = urlparse(url)
        ext = Path(parsed.path).suffix or ".bin"
        domain = parsed.netloc.replace(":", "_")
        target_dir = Path(self.download_dir) / domain
        target_dir.mkdir(parents=True, exist_ok=True)
        content_disposition = headers.get("content-disposition", "")
        filename_match = re.search(r'filename="?([^"]+)"?', content_disposition)
        original_filename = None
        if filename_match:
            original_filename = filename_match.group(1).strip()
        if not original_filename:
            original_filename = os.path.basename(parsed.path) or None
        
        # Security check: Ensure filename doesn't contain excluded keywords
        # This is a second line of defense after URL checking
        if cfg.exclude_keywords:
            raw_name = original_filename or ""
            if self._is_excluded(raw_name, [k.lower() for k in cfg.exclude_keywords]):
                logger.info("Dropping file %s (matched exclude keywords in filename)", raw_name)
                if tmp_path.exists():
                    tmp_path.unlink()
                return None
        
        safe_name = self._sanitize_filename(original_filename or f"{sha256}{ext}")
        if not safe_name.lower().endswith(ext):
            safe_name = f"{safe_name}{ext}"
        path = self._resolve_conflict(target_dir, safe_name)

        # Check if hash already exists in DB (Global Deduplication)
        if self.storage.file_exists_by_hash(sha256):
            logger.info("Dropping file %s (SHA256 %s already exists in DB)", url, sha256)
            if tmp_path.exists():
                tmp_path.unlink()
            return None

        blob = self.storage.get_blob(sha256)
        if blob and blob.get("canonical_path"):
            canonical = Path(blob["canonical_path"])
            if canonical.exists() and path != canonical:
                try:
                    os.link(canonical, path)
                    local_path = str(path)
                except Exception:
                    local_path = str(canonical)
            else:
                local_path = str(canonical)
            if tmp_path.exists():
                tmp_path.unlink()
        else:
            if path.exists():
                path = self._resolve_conflict(target_dir, safe_name)
            tmp_path.replace(path)
            local_path = str(path)
            self.storage.upsert_blob(
                sha256=sha256,
                canonical_path=str(path),
                bytes_size=bytes_size,
                content_type=headers.get("content-type"),
            )

        # Store relative path for consistency with FileCollector
        # Relative to parent of download_dir (typically the 'data' directory)
        base_dir = Path(self.download_dir).parent.resolve()
        local_path_resolved = Path(local_path).resolve()
        try:
            relative_path = str(local_path_resolved.relative_to(base_dir))
        except ValueError:
            # Fallback to absolute path if relative path cannot be determined
            relative_path = str(local_path_resolved)

        # Select the best available title using three signals:
        # 1. link_text: anchor text from the HTML link — the most document-specific label.
        # 2. page_title: HTML page title — good when each document has its own page, but
        #    unhelpful when many files are listed on a generic page (e.g. the institution's
        #    home/publications page).  Skip it when it equals the site name (cfg.name) to
        #    avoid storing the institution name as the document title.
        # 3. original_filename / URL basename: always available last resort.
        clean_link_text = link_text.strip() if link_text else None
        useful_page_title: str | None = None
        if page_title:
            site_name = (cfg.name or "").strip().lower()
            if not (site_name and page_title.strip().lower() == site_name):
                useful_page_title = page_title
        title = clean_link_text or useful_page_title or original_filename or os.path.basename(parsed.path)
        content_type = headers.get("content-type")
        last_modified = headers.get("last-modified")
        etag = headers.get("etag")
        source_site = source_site_override or cfg.name
        self.storage.upsert_file(
            url=url,
            sha256=sha256,
            title=title,
            source_site=source_site,
            source_page_url=source_page_url,
            original_filename=original_filename,
            local_path=relative_path,
            bytes_size=bytes_size,
            content_type=content_type,
            last_modified=last_modified,
            etag=etag,
            published_time=published_time,
        )
        logger.info("Saved file: %s (%d bytes) -> %s", original_filename or url, bytes_size, local_path)
        return {
            "url": url,
            "sha256": sha256,
            "title": title,
            "source_site": source_site,
            "source_page_url": source_page_url,
            "original_filename": original_filename,
            "local_path": local_path,
            "bytes": bytes_size,
            "content_type": content_type,
            "last_modified": last_modified,
            "etag": etag,
            "published_time": published_time,
        }

    def _sanitize_filename(self, name: str) -> str:
        name = name.strip().replace("\u0000", "")
        name = re.sub(r'[<>:"/\\|?*]+', "_", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name or "file"

    def _resolve_conflict(self, folder: Path, filename: str) -> Path:
        candidate = folder / filename
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        for i in range(1, 1000):
            alt = folder / f"{stem}_{i}{suffix}"
            if not alt.exists():
                return alt
        return folder / f"{stem}_{int(time.time())}{suffix}"

    def scan_page_for_files(
        self, url: str, cfg: SiteConfig, source_site: str, progress_callback=None
    ) -> list[dict]:
        if progress_callback:
            progress_callback(None, None, f"Scanning: {url}")
            
        exts = {e.lower() for e in (cfg.file_exts or [])} or DEFAULT_FILE_EXTS
        keywords = [k.lower() for k in (cfg.keywords or [])]
        exclude = [k.lower() for k in (cfg.exclude_keywords or [])]
        exclude_prefixes = [p.lower() for p in (cfg.exclude_prefixes or [])]
        try:
            data, headers, final_url = self._request(url)
        except Exception:
            return []

        if exclude and self._is_excluded(final_url, exclude):
            return []
        if exclude_prefixes and self._has_excluded_prefix(os.path.basename(final_url), exclude_prefixes):
            return []

        if self._is_file_url(final_url, exts):
            if cfg.check_database and self.storage.file_exists(final_url):
                return []
            parsed = urlparse(final_url)
            domain = parsed.netloc.replace(":", "_")
            target_dir = Path(self.download_dir) / domain
            tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                final_url, target_dir
            )
            if exclude and self._is_excluded(ffinal, exclude):
                if tmp_path.exists():
                    tmp_path.unlink()
                return []
            if exclude_prefixes and self._has_excluded_prefix(os.path.basename(ffinal), exclude_prefixes):
                if tmp_path.exists():
                    tmp_path.unlink()
                return []
            item = self._handle_file(
                ffinal,
                tmp_path,
                fheaders,
                sha256,
                bytes_size,
                cfg,
                source_page_url=None,
                source_site_override=source_site,
            )
            return [item] if item else []

        try:
            html = data.decode("utf-8", errors="ignore")
        except Exception:
            html = ""

        page_title, published_time = extract_metadata(html, final_url)
        page_text = html_to_text(html).lower()
        page_relevant = any(k in page_text for k in keywords) if keywords else True
        if exclude and page_title and self._is_excluded(page_title, exclude):
            return []

        new_items: list[dict] = []
        links = self._extract_links(final_url, html)
        for link, link_text in links:
            if not self._is_file_url(link, exts):
                continue
            if exclude and self._is_excluded(link, exclude):
                continue
            if exclude_prefixes and self._has_excluded_prefix(os.path.basename(link), exclude_prefixes):
                continue
            if keywords and not (page_relevant or self._link_matches_keywords(link, link_text, keywords)):
                continue
            if cfg.check_database and self.storage.file_exists(link):
                continue
            try:
                parsed = urlparse(link)
                domain = parsed.netloc.replace(":", "_")
                target_dir = Path(self.download_dir) / domain
                tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                    link, target_dir
                )
            except Exception:
                continue
            if exclude and self._is_excluded(ffinal, exclude):
                if tmp_path.exists():
                    tmp_path.unlink()
                continue
            if exclude_prefixes and self._has_excluded_prefix(os.path.basename(ffinal), exclude_prefixes):
                if tmp_path.exists():
                    tmp_path.unlink()
                continue
            item = self._handle_file(
                ffinal,
                tmp_path,
                fheaders,
                sha256,
                bytes_size,
                cfg,
                source_page_url=final_url,
                page_title=page_title,
                published_time=published_time,
                source_site_override=source_site,
                link_text=link_text,
            )
            if item:
                new_items.append(item)
        sleep_with_jitter(cfg.delay_seconds)
        return new_items

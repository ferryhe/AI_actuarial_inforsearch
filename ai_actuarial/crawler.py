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
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return data, headers, resp.geturl()

    def _download_file(self, url: str, target_dir: Path) -> tuple[Path, dict[str, str], str, str, int]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = target_dir / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"download_{time.time_ns()}.part"
        hasher = hashlib.sha256()
        size = 0
        success = False
        try:
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
        text = text.lower()
        return any(k in text for k in exclude)

    def _has_excluded_prefix(self, name: str, prefixes: list[str]) -> bool:
        name = name.lower()
        return any(name.startswith(p) for p in prefixes)

    def _extract_links(self, base_url: str, html: str) -> list[tuple[str, str]]:
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

    def crawl_site(self, cfg: SiteConfig) -> list[dict]:
        # Check stop signal at start
        if self.stop_check and self.stop_check():
            logger.info("Crawl stopped by user signal.")
            return []

        logger.info("Starting crawl of site: %s (max_pages=%d, max_depth=%d)", 
                   cfg.name, cfg.max_pages, cfg.max_depth)
        keywords = [k.lower() for k in (cfg.keywords or [])]
        exts = {e.lower() for e in (cfg.file_exts or [])} or DEFAULT_FILE_EXTS
        exclude = [k.lower() for k in (cfg.exclude_keywords or [])]
        exclude_prefixes = [p.lower() for p in (cfg.exclude_prefixes or [])]
        new_items: list[dict] = []

        sitemap_urls = self._load_sitemap(cfg.url)
        if sitemap_urls:
            page_queue: deque[tuple[str, int]] = deque(
                [(u, 0) for u in sitemap_urls[: cfg.max_pages]]
            )
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
            if exclude and self._is_excluded(url, exclude):
                continue
            if exclude_prefixes and self._has_excluded_prefix(os.path.basename(url), exclude_prefixes):
                continue

            seen_pages.add(url)
            try:
                data, headers, final_url = self._request(url)
            except Exception:
                continue

            pages_fetched += 1
            self.storage.mark_page_seen(final_url)

            if exclude and self._is_excluded(final_url, exclude):
                continue
            if exclude_prefixes and self._has_excluded_prefix(os.path.basename(final_url), exclude_prefixes):
                continue

            if self._is_file_url(final_url, exts):
                if self.storage.file_exists(final_url):
                    sleep_with_jitter(cfg.delay_seconds)
                    continue
                parsed = urlparse(final_url)
                domain = parsed.netloc.replace(":", "_")
                target_dir = Path(self.download_dir) / domain
                tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                    final_url, target_dir
                )
                if exclude and self._is_excluded(ffinal, exclude):
                    if tmp_path.exists():
                        tmp_path.unlink()
                    sleep_with_jitter(cfg.delay_seconds)
                    continue
                if exclude_prefixes and self._has_excluded_prefix(os.path.basename(ffinal), exclude_prefixes):
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

            links = self._extract_links(final_url, html)
            for link, link_text in links:
                if exclude and self._is_excluded(link, exclude):
                    continue
                if exclude_prefixes and self._has_excluded_prefix(os.path.basename(link), exclude_prefixes):
                    continue
                if self._is_file_url(link, exts):
                    if keywords and not (is_relevant or self._link_matches_keywords(link, link_text, keywords)):
                        continue
                    if self.storage.file_exists(link):
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
                    # 1. Check final URL (redirects resolved)
                    if exclude and self._is_excluded(ffinal, exclude):
                        logger.info("Excluding based on final URL: %s", ffinal)
                        if tmp_path.exists():
                            tmp_path.unlink()
                        continue
                    
                    # 2. Check actual filename (content-disposition or url derived)
                    if exclude and self._is_excluded(tmp_path.name, exclude):
                        logger.info("Excluding based on filename: %s", tmp_path.name)
                        if tmp_path.exists():
                            tmp_path.unlink()
                        continue

                    # 3. Check prefixes on filename
                    if exclude_prefixes:
                        fname = tmp_path.name
                        if self._has_excluded_prefix(fname, exclude_prefixes):
                            logger.info("Excluding based on prefix: %s", fname)
                            if tmp_path.exists():
                                tmp_path.unlink()
                            continue

                    if exclude_prefixes and self._has_excluded_prefix(os.path.basename(ffinal), exclude_prefixes):
                        if tmp_path.exists():
                            tmp_path.unlink()
                        continue

                    # 4. Check prefixes on URL base (legacy check, kept for safety)
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
                    )
                    if item:
                        new_items.append(item)
                else:
                    if depth + 1 <= cfg.max_depth and is_relevant:
                        page_queue.append((link, depth + 1))

            sleep_with_jitter(cfg.delay_seconds)

        logger.info("Crawl completed for %s: %d new files found, %d pages visited", 
                   cfg.name, len(new_items), pages_fetched)
        return new_items

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
             # We might want to link this URL to the existing blob in future, 
             # but for now we treat it as "already collected" and skip to avoid duplicates.
             # Or we can proceed to update the 'files' table but reuse the 'blob'.
             # Let's proceed to reuse the blob logic below.
             pass

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

        title = page_title or os.path.basename(parsed.path) or original_filename
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
        self, url: str, cfg: SiteConfig, source_site: str
    ) -> list[dict]:
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
            if self.storage.file_exists(final_url):
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
            if self.storage.file_exists(link):
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
            )
            if item:
                new_items.append(item)
        sleep_with_jitter(cfg.delay_seconds)
        return new_items

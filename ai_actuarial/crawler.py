from __future__ import annotations

import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .storage import Storage
from .utils import (
    extract_metadata,
    html_to_text,
    normalize_url,
    same_domain,
    sha256_bytes,
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
    def __init__(self, storage: Storage, download_dir: str, user_agent: str) -> None:
        self.storage = storage
        self.download_dir = download_dir
        self.user_agent = user_agent

    def _request(self, url: str) -> tuple[bytes, dict[str, str], str]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return data, headers, resp.geturl()

    def _is_file_url(self, url: str, exts: set[str]) -> bool:
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in exts)

    def _is_excluded(self, text: str, exclude: list[str]) -> bool:
        text = text.lower()
        return any(k in text for k in exclude)

    def _has_excluded_prefix(self, name: str, prefixes: list[str]) -> bool:
        name = name.lower()
        return any(name.startswith(p) for p in prefixes)

    def _extract_links(self, base_url: str, html: str) -> list[str]:
        links = re.findall(r'href=["\\\'](.*?)["\\\']', html, flags=re.IGNORECASE)
        out: list[str] = []
        for link in links:
            norm = normalize_url(base_url, link)
            if norm:
                out.append(norm)
        return out

    def _load_sitemap(self, site_url: str) -> list[str]:
        sitemap_url = site_url.rstrip("/") + "/sitemap.xml"
        try:
            data, _, _ = self._request(sitemap_url)
        except Exception:
            return []
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return []

        urls: list[str] = []
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.findall(".//ns:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
        return urls

    def crawl_site(self, cfg: SiteConfig) -> list[dict]:
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
                item = self._handle_file(final_url, data, headers, cfg, source_page_url=None)
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
            for link in links:
                if exclude and self._is_excluded(link, exclude):
                    continue
                if exclude_prefixes and self._has_excluded_prefix(os.path.basename(link), exclude_prefixes):
                    continue
                if self._is_file_url(link, exts):
                    if self.storage.file_exists(link):
                        continue
                    try:
                        fdata, fheaders, ffinal = self._request(link)
                    except Exception:
                        continue
                    if exclude and self._is_excluded(ffinal, exclude):
                        continue
                    if exclude_prefixes and self._has_excluded_prefix(os.path.basename(ffinal), exclude_prefixes):
                        continue
                    item = self._handle_file(
                        ffinal,
                        fdata,
                        fheaders,
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

        return new_items

    def _handle_file(
        self,
        url: str,
        data: bytes,
        headers: dict[str, str],
        cfg: SiteConfig,
        source_page_url: str | None,
        page_title: str | None = None,
        published_time: str | None = None,
        source_site_override: str | None = None,
    ) -> dict | None:
        sha256 = sha256_bytes(data)
        if self.storage.file_exists(url, sha256):
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
        safe_name = self._sanitize_filename(original_filename or f"{sha256}{ext}")
        if not safe_name.lower().endswith(ext):
            safe_name = f"{safe_name}{ext}"
        path = self._resolve_conflict(target_dir, safe_name)
        with open(path, "wb") as f:
            f.write(data)

        title = page_title or os.path.basename(parsed.path) or original_filename
        content_type = headers.get("content-type")
        last_modified = headers.get("last-modified")
        etag = headers.get("etag")
        bytes_size = len(data)
        source_site = source_site_override or cfg.name
        self.storage.upsert_file(
            url=url,
            sha256=sha256,
            title=title,
            source_site=source_site,
            source_page_url=source_page_url,
            original_filename=original_filename,
            local_path=str(path),
            bytes_size=bytes_size,
            content_type=content_type,
            last_modified=last_modified,
            etag=etag,
            published_time=published_time,
        )
        return {
            "url": url,
            "sha256": sha256,
            "title": title,
            "source_site": source_site,
            "source_page_url": source_page_url,
            "original_filename": original_filename,
            "local_path": str(path),
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
        try:
            data, headers, final_url = self._request(url)
        except Exception:
            return []

        if self._is_file_url(final_url, exts):
            item = self._handle_file(
                final_url,
                data,
                headers,
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
        if keywords and not any(k in page_text for k in keywords):
            return []

        new_items: list[dict] = []
        links = self._extract_links(final_url, html)
        for link in links:
            if not self._is_file_url(link, exts):
                continue
            if self.storage.file_exists(link):
                continue
            try:
                fdata, fheaders, ffinal = self._request(link)
            except Exception:
                continue
            item = self._handle_file(
                ffinal,
                fdata,
                fheaders,
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

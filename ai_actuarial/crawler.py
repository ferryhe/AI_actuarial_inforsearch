from __future__ import annotations

import hashlib
import http.client
import ipaddress
import logging
import os
import random
import re
import socket
import sqlite3
import ssl
import time
import xml.etree.ElementTree as ET
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from .search_acquisition import (
    SearchAcquisitionReport,
    make_acquisition_outcome,
    normalize_acquisition_url,
    safe_outcome_url,
)
from .security import SafeUrlResolution, UnsafeUrlError, resolve_safe_http_url
from .storage import Storage
from .utils import extract_metadata, html_to_text, normalize_url, same_domain

try:
    import curl_cffi.requests as _curl_requests
    from curl_cffi import CurlOpt as _CurlOpt

    _CURL_CFFI_AVAILABLE = True
except ImportError:  # pragma: no cover - requirements.txt installs curl_cffi
    _CurlOpt = None  # type: ignore[assignment]
    _curl_requests = None  # type: ignore[assignment]
    _CURL_CFFI_AVAILABLE = False

logger = logging.getLogger(__name__)


DEFAULT_FILE_EXTS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_ARTIFACT_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".doc": {"application/msword", "application/vnd.ms-word"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}
_MAX_REDIRECT_HOPS = 10
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


class _StagingIOError(OSError):
    pass


class _AcquisitionStopped(RuntimeError):
    pass


class _PinnedHTTPResponse:
    def __init__(
        self, conn: http.client.HTTPConnection, response: http.client.HTTPResponse, url: str
    ) -> None:
        self._conn = conn
        self._response = response
        self._url = url
        self.status = response.status
        self.headers = {k.lower(): v for k, v in response.getheaders()}

    def read(self, size: int = -1) -> bytes:
        return self._response.read(size)

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()


class _CurlHTTPResponse:
    def __init__(self, response) -> None:
        self._response = response
        self._chunks = iter(response.iter_content(chunk_size=1024 * 128))
        self._buffer = bytearray()
        self.status = int(response.status_code)
        self.headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
        self._url = str(response.url)

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            data = bytes(self._buffer) + b"".join(self._chunks)
            self._buffer.clear()
            return data
        while len(self._buffer) < size:
            try:
                self._buffer.extend(next(self._chunks))
            except StopIteration:
                break
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self._response.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()


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
    collect_linked_files: bool | None = None  # None preserves the legacy file-collection default
    collect_page_content: bool | None = None  # Also save text extracted from HTML pages
    acquisition_tools: list[str] | None = None  # Supported values: crawler, search
    content_selector: str | None = None  # CSS selector to narrow link extraction to content area
    allow_url_patterns: list[str] | None = (
        None  # Regex allow-list for sub-page URLs (Scrapy-style); if set, only matching sub-pages are queued
    )
    queries: list[str] | None = (
        None  # Site-specific search queries to supplement or bypass direct crawling (useful for anti-bot-protected sites)
    )
    check_database: bool = True
    allowed_domain: str | None = (
        None  # Search acquisition scope; None keeps legacy crawling behavior
    )


class Crawler:
    def __init__(
        self,
        storage: Storage,
        download_dir: str,
        user_agent: str,
        stop_check=None,
        default_delay_seconds: float = 0.5,
    ) -> None:
        self.storage = storage
        self.download_dir = download_dir
        self.user_agent = user_agent
        self.stop_check = stop_check
        self.default_delay_seconds = max(float(default_delay_seconds), 0.0)
        self.last_crawl_diagnostic: dict[str, object] = {}
        self._next_request_at: dict[str, float] = {}
        self._request_attempts = 0
        self._curl_sessions: dict[tuple[str, int, str], object] = {}
        self._cleanup_old_temp_files()

    def get_last_crawl_diagnostic(self) -> dict[str, object]:
        """Return non-contract crawl diagnostics from the most recent site crawl."""
        return dict(self.last_crawl_diagnostic or {})

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

    def _request(
        self,
        url: str,
        *,
        timeout: int = 30,
        delay_seconds: float | None = None,
    ) -> tuple[bytes, dict[str, str], str]:
        current_url = url
        for _hop in range(_MAX_REDIRECT_HOPS):
            resolution = resolve_safe_http_url(current_url)
            with self._open_pinned_http(
                current_url,
                resolution,
                timeout=timeout,
                delay_seconds=delay_seconds,
            ) as resp:
                headers = {k.lower(): str(v) for k, v in resp.headers.items()}
                redirect_target = self._redirect_target(
                    current_url, self._response_code(resp), headers
                )
                if redirect_target:
                    current_url = redirect_target
                    continue
                self._raise_for_status(current_url, self._response_code(resp))
                data = resp.read()
                return data, headers, resp.geturl()

        raise UnsafeUrlError(f"Too many redirects while fetching {url}")

    def _download_file(
        self,
        url: str,
        target_dir: Path,
        *,
        delay_seconds: float | None = None,
    ) -> tuple[Path, dict[str, str], str, str, int]:
        if self.stop_check and self.stop_check():
            raise _AcquisitionStopped("task stopped by user")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            tmp_dir = target_dir / "_tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _StagingIOError(str(exc)) from exc
        tmp_path = tmp_dir / f"download_{time.time_ns()}.part"
        hasher = hashlib.sha256()
        size = 0
        success = False
        try:
            current_url = url
            for _hop in range(_MAX_REDIRECT_HOPS):
                resolution = resolve_safe_http_url(current_url)
                with self._open_pinned_http(
                    current_url,
                    resolution,
                    timeout=60,
                    delay_seconds=delay_seconds,
                ) as resp:
                    headers = {k.lower(): str(v) for k, v in resp.headers.items()}
                    redirect_target = self._redirect_target(
                        current_url, self._response_code(resp), headers
                    )
                    if redirect_target:
                        current_url = redirect_target
                        continue
                    self._raise_for_status(current_url, self._response_code(resp))
                    final_url = resp.geturl()
                    try:
                        staging_file = open(tmp_path, "wb")
                    except OSError as exc:
                        raise _StagingIOError(str(exc)) from exc
                    try:
                        while True:
                            if self.stop_check and self.stop_check():
                                raise _AcquisitionStopped("task stopped by user")
                            chunk = resp.read(1024 * 128)
                            if self.stop_check and self.stop_check():
                                raise _AcquisitionStopped("task stopped by user")
                            if not chunk:
                                break
                            try:
                                staging_file.write(chunk)
                            except OSError as exc:
                                raise _StagingIOError(str(exc)) from exc
                            hasher.update(chunk)
                            size += len(chunk)
                    except BaseException:
                        try:
                            staging_file.close()
                        except OSError:
                            pass
                        raise
                    try:
                        staging_file.flush()
                        staging_file.close()
                    except OSError as exc:
                        try:
                            staging_file.close()
                        except OSError:
                            pass
                        raise _StagingIOError(str(exc)) from exc
                success = True
                logger.debug("Downloaded %s (%d bytes)", safe_outcome_url(current_url), size)
                return tmp_path, headers, final_url, hasher.hexdigest(), size

            raise UnsafeUrlError(f"Too many redirects while downloading {url}")
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

    @staticmethod
    def _origin_key(url: str) -> str:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        return f"{parsed.scheme.lower()}://{parsed.hostname or ''}:{port}"

    def _pace_request(self, url: str, delay_seconds: float | None) -> None:
        delay = (
            self.default_delay_seconds if delay_seconds is None else max(float(delay_seconds), 0.0)
        )
        origin = self._origin_key(url)
        now = time.monotonic()
        next_request_at = self._next_request_at.get(origin, now)
        if next_request_at > now:
            time.sleep(next_request_at - now)
            now = time.monotonic()
        randomized_delay = random.uniform(delay, delay * 1.5) if delay > 0 else 0.0
        self._next_request_at[origin] = now + randomized_delay
        self._request_attempts += 1

    @staticmethod
    def _preferred_addresses(
        resolution: SafeUrlResolution,
    ) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return tuple(
            sorted(
                resolution.addresses,
                key=lambda address: isinstance(address, ipaddress.IPv6Address),
            )
        )

    @staticmethod
    def _curl_resolve_entry(host: str, port: int, address: object) -> str:
        address_text = str(address)
        if isinstance(ipaddress.ip_address(address_text), ipaddress.IPv6Address):
            address_text = f"[{address_text}]"
        return f"{host}:{port}:{address_text}"

    def _curl_session_for(self, host: str, port: int, address: object):
        address_text = str(address)
        key = (host, port, address_text)
        session = self._curl_sessions.get(key)
        if session is not None:
            return session
        if not _CURL_CFFI_AVAILABLE or _curl_requests is None or _CurlOpt is None:
            raise RuntimeError("curl_cffi is not available")
        try:
            ipaddress.ip_address(host)
            curl_options = {}
        except ValueError:
            curl_options = {
                _CurlOpt.RESOLVE: [self._curl_resolve_entry(host, port, address)],
            }
        session = _curl_requests.Session(
            curl_options=curl_options,
            impersonate="chrome",
            default_headers=False,
            allow_redirects=False,
            trust_env=False,
        )
        self._curl_sessions[key] = session
        return session

    def _open_pinned_curl(
        self,
        url: str,
        resolution: SafeUrlResolution,
        *,
        timeout: int,
        delay_seconds: float | None,
    ):
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        last_error: Exception | None = None
        for address in self._preferred_addresses(resolution):
            try:
                session = self._curl_session_for(resolution.host, port, address)
                self._pace_request(url, delay_seconds)
                response = session.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=timeout,
                    allow_redirects=False,
                    stream=True,
                )
                return _CurlHTTPResponse(response)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise UnsafeUrlError(f"No validated address available for {url}")

    def _open_pinned_http(
        self,
        url: str,
        resolution: SafeUrlResolution,
        *,
        timeout: int,
        delay_seconds: float | None = None,
    ):
        if _CURL_CFFI_AVAILABLE:
            return self._open_pinned_curl(
                url,
                resolution,
                timeout=timeout,
                delay_seconds=delay_seconds,
            )
        return self._open_pinned_stdlib(
            url,
            resolution,
            timeout=timeout,
            delay_seconds=delay_seconds,
        )

    def _open_pinned_stdlib(
        self,
        url: str,
        resolution: SafeUrlResolution,
        *,
        timeout: int,
        delay_seconds: float | None = None,
    ):
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        port = parsed.port or (443 if scheme == "https" else 80)
        target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        host_header = resolution.host
        try:
            if isinstance(ipaddress.ip_address(resolution.host), ipaddress.IPv6Address):
                host_header = f"[{resolution.host}]"
        except ValueError:
            pass
        if (scheme == "http" and port != 80) or (scheme == "https" and port != 443):
            host_header = f"{host_header}:{port}"

        last_error: Exception | None = None
        ssl_context = ssl.create_default_context() if scheme == "https" else None
        for address in self._preferred_addresses(resolution):
            conn = http.client.HTTPConnection(resolution.host, port=port, timeout=timeout)
            try:
                self._pace_request(url, delay_seconds)
                sock = socket.create_connection((str(address), port), timeout=timeout)
                if ssl_context is not None:
                    sock = ssl_context.wrap_socket(sock, server_hostname=resolution.host)
                conn.sock = sock
                conn.request(
                    "GET", target, headers={"User-Agent": self.user_agent, "Host": host_header}
                )
                response = conn.getresponse()
                return _PinnedHTTPResponse(conn, response, url)
            except Exception as exc:
                conn.close()
                last_error = exc
        if last_error is not None:
            raise last_error
        raise UnsafeUrlError(f"No validated address available for {url}")

    @staticmethod
    def _response_code(resp) -> int:
        code = getattr(resp, "status", None)
        if code is None:
            code = resp.getcode()
        return int(code)

    @staticmethod
    def _redirect_target(
        current_url: str, status_code: int | None, headers: dict[str, str]
    ) -> str | None:
        if status_code is None or int(status_code) not in _REDIRECT_STATUS_CODES:
            return None
        location = str(headers.get("location") or "").strip()
        if not location:
            raise UnsafeUrlError(f"Redirect response from {current_url} is missing Location header")
        return urljoin(current_url, location)

    @staticmethod
    def _raise_for_status(url: str, status_code: int) -> None:
        if status_code >= 400:
            raise RuntimeError(f"HTTP Error {status_code} for {url}")

    def _is_excluded(self, text: str, exclude: list[str]) -> bool:
        """Check if text contains any excluded keyword."""
        text = text.lower()
        return any(k in text for k in exclude)

    def _has_excluded_prefix(self, name: str, prefixes: list[str]) -> bool:
        """Check if name starts with any excluded prefix."""
        name = name.lower()
        return any(name.startswith(p) for p in prefixes)

    def _should_exclude_url(
        self, url: str, exclude: list[str] | None, exclude_prefixes: list[str] | None
    ) -> bool:
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

    def _extract_links(
        self, base_url: str, html: str, content_selector: str | None = None
    ) -> list[tuple[str, str]]:
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

    def _load_sitemap(self, site_url: str, *, delay_seconds: float | None = None) -> list[str]:
        sitemap_url = site_url.rstrip("/") + "/sitemap.xml"
        try:
            data, _, _ = self._request(sitemap_url, delay_seconds=delay_seconds)
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
        request_errors: list[str] = []
        self.last_crawl_diagnostic = {}
        request_attempts_before = self._request_attempts

        # Check stop signal at start
        if self.stop_check and self.stop_check():
            logger.info("Crawl stopped by user signal.")
            self.last_crawl_diagnostic = {
                "site_name": cfg.name,
                "site_url": cfg.url,
                "pages_attempted": 0,
                "pages_visited": 0,
                "request_attempts": 0,
                "file_download_attempts": 0,
                "dedup_skips": 0,
                "request_errors": [],
                "error_text": "",
                "stopped": True,
            }
            return []

        logger.info(
            "Starting crawl of site: %s (max_pages=%d, max_depth=%d)",
            cfg.name,
            cfg.max_pages,
            cfg.max_depth,
        )

        if progress_callback:
            progress_callback(0, cfg.max_pages, f"Starting crawl of {cfg.name}")

        keywords = [k.lower() for k in (cfg.keywords or [])]
        exts = {e.lower() for e in (cfg.file_exts or [])} or DEFAULT_FILE_EXTS
        exclude = [k.lower() for k in (cfg.exclude_keywords or [])]
        exclude_prefixes = [p.lower() for p in (cfg.exclude_prefixes or [])]
        # Compile allow_url_patterns to regex; if set, only matching URLs are queued / downloaded.
        # Invalid patterns are skipped with a warning rather than aborting the crawl.
        allow_patterns = []
        for raw_pat in cfg.allow_url_patterns or []:
            try:
                allow_patterns.append(re.compile(raw_pat))
            except re.error as exc:
                logger.warning(
                    "Skipping invalid allow_url_pattern %r for site %r: %s", raw_pat, cfg.name, exc
                )
        new_items: list[dict] = []

        sitemap_urls = self._load_sitemap(cfg.url, delay_seconds=cfg.delay_seconds)
        if sitemap_urls:
            # When allow_url_patterns is configured, only seed URLs that match at
            # least one pattern — otherwise the allow-list is bypassed for sitemaps.
            if allow_patterns:
                sitemap_urls = [u for u in sitemap_urls if any(p.search(u) for p in allow_patterns)]
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
                    cfg.name,
                    cfg.url,
                )
                page_queue = deque([(cfg.url, 0)])
        else:
            page_queue = deque([(cfg.url, 0)])

        seen_pages: set[str] = set()
        pages_attempted = 0
        pages_fetched = 0
        file_download_attempts = 0
        dedup_skips = 0
        stopped = False

        while page_queue and pages_attempted < cfg.max_pages:
            # Check stop signal in loop
            if self.stop_check and self.stop_check():
                logger.info("Crawl stopped by user signal.")
                stopped = True
                break

            url, depth = page_queue.popleft()
            if url in seen_pages:
                continue
            if not same_domain(cfg.url, url):
                continue
            if self._should_exclude_url(url, exclude, exclude_prefixes):
                continue

            seen_pages.add(url)
            pages_attempted += 1

            if progress_callback:
                progress_callback(pages_attempted, cfg.max_pages, f"Crawling: {url}")

            try:
                data, headers, final_url = self._request(url, delay_seconds=cfg.delay_seconds)
            except Exception as exc:
                request_errors.append(f"{url}: {exc}")
                continue

            pages_fetched += 1

            self.storage.mark_page_seen(final_url)

            if self._should_exclude_url(final_url, exclude, exclude_prefixes):
                continue

            if self._is_file_url(final_url, exts):
                if cfg.collect_linked_files is False:
                    continue
                if cfg.check_database and self.storage.file_exists(final_url):
                    dedup_skips += 1
                    continue
                parsed = urlparse(final_url)
                domain = parsed.netloc.replace(":", "_")
                target_dir = Path(self.download_dir) / domain
                file_download_attempts += 1
                tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                    final_url,
                    target_dir,
                    delay_seconds=cfg.delay_seconds,
                )
                if self._should_exclude_url(ffinal, exclude, exclude_prefixes):
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
                    source_page_url=None,
                )
                if item:
                    new_items.append(item)
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
                if exclude_prefixes and self._has_excluded_prefix(
                    os.path.basename(link), exclude_prefixes
                ):
                    continue
                if cfg.collect_linked_files is not False and self._is_file_url(link, exts):
                    # When allow_url_patterns is configured, enforce it on file links too
                    # (e.g. /globalassets/ pattern gates PDF downloads, not just subpage queuing).
                    if allow_patterns and not any(p.search(link) for p in allow_patterns):
                        continue
                    # Without allow_patterns, include the file if the page it lives on
                    # is topically relevant OR the link URL/text matches keywords.
                    # Both conditions were originally OR'd; dropping is_relevant caused
                    # generic filenames (e.g. bulletin.pdf) on relevant pages to be missed.
                    if not allow_patterns and keywords:
                        if not (
                            is_relevant or self._link_matches_keywords(link, link_text, keywords)
                        ):
                            continue
                    if cfg.check_database and self.storage.file_exists(link):
                        dedup_skips += 1
                        continue
                    try:
                        parsed = urlparse(link)
                        domain = parsed.netloc.replace(":", "_")
                        target_dir = Path(self.download_dir) / domain
                        file_download_attempts += 1
                        tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                            link,
                            target_dir,
                            delay_seconds=cfg.delay_seconds,
                        )
                    except Exception as exc:
                        request_errors.append(f"{link}: {exc}")
                        continue

                    # Enhanced Exclusion Check:
                    # Use consolidated helper to check both URL and filename against
                    # exclude patterns and excluded prefixes.
                    if self._should_exclude_url(
                        ffinal, exclude, exclude_prefixes
                    ) or self._should_exclude_url(tmp_path.name, exclude, exclude_prefixes):
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

        logger.info(
            "Crawl completed for %s: %d new files found, %d/%d pages visited/attempted",
            cfg.name,
            len(new_items),
            pages_fetched,
            pages_attempted,
        )
        self.last_crawl_diagnostic = {
            "site_name": cfg.name,
            "site_url": cfg.url,
            "pages_attempted": pages_attempted,
            "pages_visited": pages_fetched,
            "request_attempts": self._request_attempts - request_attempts_before,
            "file_download_attempts": file_download_attempts,
            "dedup_skips": dedup_skips,
            "request_errors": request_errors,
            "error_text": "; ".join(request_errors),
            "stopped": stopped,
        }
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
        *,
        duplicate_counts: Counter[str] | None = None,
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
        if cfg.check_database:
            duplicate_reason = self._existing_url_subreason(url)
            if duplicate_reason:
                if duplicate_counts is not None:
                    duplicate_counts[duplicate_reason] += 1
                return None

        text_content = self._extract_text_from_html(html, url)
        if not text_content:
            return None

        if page_title:
            text_content = f"# {page_title}\n\n{text_content}"

        sha256 = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        if cfg.check_database and self.storage.file_exists_by_hash(sha256):
            if duplicate_counts is not None:
                duplicate_counts["content_hash"] += 1
            logger.debug(
                "Skipping page %s: same content already stored (sha256=%s)",
                safe_outcome_url(url),
                sha256,
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
        created_path = path
        try:
            path.write_text(text_content, encoding="utf-8")

            bytes_size = len(text_content.encode("utf-8"))

            # Store relative path to keep it consistent with file downloads
            base_dir = Path(self.download_dir).parent.resolve()
            try:
                relative_path = str(path.resolve().relative_to(base_dir))
            except ValueError:
                relative_path = str(path.resolve())

            with self.storage.transaction(immediate=True):
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
        except Exception:
            self._remove_temp_file(created_path)
            raise

        logger.info(
            "Saved page content: %s (%d bytes) -> %s",
            page_title or safe_outcome_url(url),
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
            logger.info(
                "Dropping file %s (SHA256 %s already exists in DB)",
                safe_outcome_url(url),
                sha256,
            )
            if tmp_path.exists():
                tmp_path.unlink()
            return None

        blob = self.storage.get_blob(sha256)
        created_path: Path | None = None
        try:
            with self.storage.transaction(immediate=True):
                if blob and blob.get("canonical_path"):
                    canonical = Path(blob["canonical_path"])
                    if canonical.exists() and path != canonical:
                        try:
                            os.link(canonical, path)
                            created_path = path
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
                    created_path = path
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
                title = (
                    clean_link_text
                    or useful_page_title
                    or original_filename
                    or os.path.basename(parsed.path)
                )
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
        except Exception:
            self._remove_temp_file(created_path)
            raise
        logger.info(
            "Saved file: %s (%d bytes) -> %s",
            original_filename or safe_outcome_url(url),
            bytes_size,
            local_path,
        )
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

    @staticmethod
    def _http_status_from_exception(exc: Exception) -> int | None:
        match = re.search(r"\b(?:HTTP(?: Error)?\s*)?(\d{3})\b", str(exc), re.IGNORECASE)
        if not match:
            return None
        status = int(match.group(1))
        return status if 100 <= status <= 599 else None

    @staticmethod
    def _remove_temp_file(path: Path | None) -> None:
        if path is None or not path.exists():
            return
        try:
            path.unlink()
        except OSError:
            pass

    def _failure_outcome(
        self,
        url: str,
        exc: Exception,
        *,
        final_url: str | None = None,
        phase: str = "download",
    ) -> dict[str, object]:
        status = self._http_status_from_exception(exc)
        text = str(exc).lower()
        if isinstance(exc, _AcquisitionStopped):
            return make_acquisition_outcome(
                "stopped_or_timeout",
                url=url,
                final_url=final_url,
                subreason="stopped",
                reason="task stopped by user",
                failed=1,
            )
        if phase == "storage" or isinstance(exc, _StagingIOError):
            return make_acquisition_outcome(
                "storage_failed",
                url=url,
                final_url=final_url,
                http_status=status,
                subreason="storage",
                reason="storage operation failed",
                failed=1,
            )
        if status in {401, 403, 429}:
            return make_acquisition_outcome(
                "access_blocked",
                url=url,
                final_url=final_url,
                http_status=status,
                subreason="http_status",
                reason=f"HTTP {status} access blocked",
                failed=1,
            )
        if (
            isinstance(exc, (TimeoutError, socket.timeout))
            or "timed out" in text
            or "timeout" in text
        ):
            return make_acquisition_outcome(
                "stopped_or_timeout",
                url=url,
                final_url=final_url,
                http_status=status,
                subreason="timeout",
                reason="request timed out",
                failed=1,
            )
        access_markers = (
            ("challenge", "challenge"),
            ("captcha", "challenge"),
            ("login", "login"),
            ("cookie", "cookie"),
            ("javascript", "javascript"),
        )
        for marker, subreason in access_markers:
            if marker in text:
                return make_acquisition_outcome(
                    "access_blocked",
                    url=url,
                    final_url=final_url,
                    http_status=status,
                    subreason=subreason,
                    reason=f"access blocked by {subreason} requirement",
                    failed=1,
                )
        return make_acquisition_outcome(
            "download_failed",
            url=url,
            final_url=final_url,
            http_status=status,
            subreason="network",
            reason="request or download failed",
            failed=1,
        )

    @staticmethod
    def _access_page_subreason(data: bytes, headers: dict[str, str]) -> str | None:
        content_type = str(headers.get("content-type") or "").lower()
        if "html" not in content_type and not data.lstrip().lower().startswith(b"<"):
            return None
        sample = data[:16384].decode("utf-8", errors="ignore").lower()
        strong_markers = (
            ("cf-chl-", "challenge"),
            ("verify you are human", "challenge"),
            ("captcha", "challenge"),
            ("<title>sign in", "login"),
            ("<title>login", "login"),
            ("login required", "login"),
            ("cookies are required", "cookie"),
            ("enable cookies", "cookie"),
            ("enable javascript", "javascript"),
        )
        for marker, subreason in strong_markers:
            if marker in sample:
                return subreason
        return None

    @staticmethod
    def _content_type_mismatch(url: str, headers: dict[str, str]) -> bool:
        content_type = str(headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if not content_type or content_type == "application/octet-stream":
            return False
        if content_type in {
            "text/html",
            "application/xhtml+xml",
            "application/json",
        }:
            return True
        extension = Path(urlparse(url).path).suffix.lower()
        expected_types = _ARTIFACT_CONTENT_TYPES.get(extension)
        return bool(expected_types and content_type not in expected_types)

    def _staged_access_page_subreason(self, path: Path, headers: dict[str, str]) -> str | None:
        try:
            with path.open("rb") as staged_file:
                sample = staged_file.read(16384)
        except OSError as exc:
            raise _StagingIOError(str(exc)) from exc
        return self._access_page_subreason(sample, headers)

    def _existing_url_subreason(self, *urls: str) -> str | None:
        seen: set[str] = set()
        for candidate in urls:
            raw = str(candidate or "").strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            if self.storage.file_exists(raw):
                return "url"
            normalized = normalize_acquisition_url(raw)
            if normalized and normalized != raw and normalized not in seen:
                seen.add(normalized)
                if self.storage.file_exists(normalized):
                    return "normalized_url"
        return None

    def _url_filter_subreason(
        self,
        url: str,
        exclude: list[str],
        exclude_prefixes: list[str],
    ) -> str | None:
        if exclude and self._is_excluded(url, exclude):
            return "keyword"
        if exclude_prefixes and self._has_excluded_prefix(os.path.basename(url), exclude_prefixes):
            return "path"
        return None

    @staticmethod
    def _normalized_filter_host(value: str | None) -> str:
        raw = str(value or "").strip().lower().removeprefix("site:")
        if not raw:
            return ""
        candidate = raw if "://" in raw else f"//{raw}"
        try:
            host = str(urlsplit(candidate).hostname or "").strip(".")
        except ValueError:
            return ""
        return host.removeprefix("www.")

    def _outside_allowed_domain(self, url: str, allowed_domain: str | None) -> bool:
        allowed = self._normalized_filter_host(allowed_domain)
        if not allowed:
            return False
        host = self._normalized_filter_host(url)
        return not host or (host != allowed and not host.endswith(f".{allowed}"))

    def _downloaded_name_filter_subreason(
        self,
        url: str,
        headers: dict[str, str],
        exclude: list[str],
        exclude_prefixes: list[str],
    ) -> str | None:
        disposition = str(headers.get("content-disposition") or "")
        match = re.search(r'filename="?([^";]+)"?', disposition, re.IGNORECASE)
        filename = match.group(1).strip() if match else (os.path.basename(urlparse(url).path) or "")
        if exclude and self._is_excluded(filename, exclude):
            return "keyword"
        if exclude_prefixes and self._has_excluded_prefix(filename, exclude_prefixes):
            return "path"
        return None

    def scan_page_for_files(
        self, url: str, cfg: SiteConfig, source_site: str, progress_callback=None
    ) -> list[dict]:
        """Legacy list contract retained for URL collection and external callers."""
        return self._scan_page_for_files_with_outcome(
            url,
            cfg,
            source_site,
            progress_callback=progress_callback,
            legacy_exceptions=True,
        ).items

    def scan_page_for_files_with_outcome(
        self,
        url: str,
        cfg: SiteConfig,
        source_site: str,
        progress_callback=None,
    ) -> SearchAcquisitionReport:
        try:
            return self._scan_page_for_files_with_outcome(
                url,
                cfg,
                source_site,
                progress_callback=progress_callback,
            )
        except Exception as exc:  # noqa: BLE001
            return SearchAcquisitionReport(
                items=[],
                outcome=self._failure_outcome(url, exc, phase="storage"),
            )

    def _scan_page_for_files_with_outcome(
        self,
        url: str,
        cfg: SiteConfig,
        source_site: str,
        progress_callback=None,
        *,
        legacy_exceptions: bool = False,
    ) -> SearchAcquisitionReport:
        if progress_callback:
            progress_callback(None, None, f"Scanning: {safe_outcome_url(url)}")
        if self.stop_check and self.stop_check():
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "stopped_or_timeout",
                    url=url,
                    subreason="stopped",
                    reason="task stopped by user",
                    failed=1,
                ),
            )
        if self._outside_allowed_domain(url, cfg.allowed_domain):
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "filtered",
                    url=url,
                    subreason="domain",
                    reason="filtered by domain rule",
                    skipped=1,
                ),
            )

        exts = {e.lower() for e in (cfg.file_exts or [])} or DEFAULT_FILE_EXTS
        keywords = [k.lower() for k in (cfg.keywords or [])]
        exclude = [k.lower() for k in (cfg.exclude_keywords or [])]
        exclude_prefixes = [p.lower() for p in (cfg.exclude_prefixes or [])]
        requested_file = self._is_file_url(url, exts)
        if self._is_file_url(url, DEFAULT_FILE_EXTS) and not requested_file:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "filtered",
                    url=url,
                    subreason="extension",
                    reason="direct document filtered by extension rule",
                    skipped=1,
                ),
            )
        try:
            data, headers, final_url = self._request(url, delay_seconds=cfg.delay_seconds)
        except Exception as exc:  # noqa: BLE001
            return SearchAcquisitionReport(items=[], outcome=self._failure_outcome(url, exc))

        if self.stop_check and self.stop_check():
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "stopped_or_timeout",
                    url=url,
                    final_url=final_url,
                    subreason="stopped",
                    reason="task stopped by user",
                    failed=1,
                ),
            )

        final_is_file = self._is_file_url(final_url, exts)
        if self._is_file_url(final_url, DEFAULT_FILE_EXTS) and not final_is_file:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "filtered",
                    url=url,
                    final_url=final_url,
                    subreason="extension",
                    reason="direct document filtered by extension rule",
                    skipped=1,
                ),
            )

        blocked_subreason = self._access_page_subreason(data, headers)
        if blocked_subreason:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "access_blocked",
                    url=url,
                    final_url=final_url,
                    subreason=blocked_subreason,
                    reason=f"access blocked by {blocked_subreason} requirement",
                    failed=1,
                ),
            )

        filter_subreason = self._url_filter_subreason(final_url, exclude, exclude_prefixes)
        if filter_subreason:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "filtered",
                    url=url,
                    final_url=final_url,
                    subreason=filter_subreason,
                    reason=f"filtered by {filter_subreason} rule",
                    skipped=1,
                ),
            )

        if requested_file and (
            not final_is_file or self._content_type_mismatch(final_url, headers)
        ):
            subreason = "redirect" if not final_is_file else "content_type"
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "redirect_or_content_type_mismatch",
                    url=url,
                    final_url=final_url,
                    subreason=subreason,
                    reason=f"file request ended with {subreason} mismatch",
                    failed=1,
                ),
            )

        if final_is_file:
            if cfg.collect_linked_files is False:
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "filtered",
                        url=url,
                        final_url=final_url,
                        subreason="collection_disabled",
                        reason="linked file collection is disabled",
                        skipped=1,
                    ),
                )
            if cfg.check_database:
                duplicate_reason = self._existing_url_subreason(url, final_url)
                if duplicate_reason:
                    return SearchAcquisitionReport(
                        items=[],
                        outcome=make_acquisition_outcome(
                            "already_exists",
                            url=url,
                            final_url=final_url,
                            subreason=duplicate_reason,
                            reason=f"file already exists by {duplicate_reason}",
                            skipped=1,
                        ),
                    )
            parsed = urlparse(final_url)
            target_dir = Path(self.download_dir) / parsed.netloc.replace(":", "_")
            try:
                tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                    final_url,
                    target_dir,
                    delay_seconds=cfg.delay_seconds,
                )
            except _AcquisitionStopped as exc:
                return SearchAcquisitionReport(
                    items=[],
                    outcome=self._failure_outcome(url, exc, final_url=final_url),
                )
            except Exception as exc:  # noqa: BLE001
                if legacy_exceptions:
                    raise
                return SearchAcquisitionReport(
                    items=[],
                    outcome=self._failure_outcome(url, exc, final_url=final_url),
                )
            if self.stop_check and self.stop_check():
                self._remove_temp_file(tmp_path)
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "stopped_or_timeout",
                        url=url,
                        final_url=ffinal,
                        subreason="stopped",
                        reason="task stopped by user",
                        failed=1,
                    ),
                )
            staged_is_file = self._is_file_url(ffinal, exts)
            if self._is_file_url(ffinal, DEFAULT_FILE_EXTS) and not staged_is_file:
                self._remove_temp_file(tmp_path)
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "filtered",
                        url=url,
                        final_url=ffinal,
                        subreason="extension",
                        reason="download filtered by extension rule",
                        skipped=1,
                    ),
                )
            try:
                blocked_subreason = self._staged_access_page_subreason(tmp_path, fheaders)
            except Exception as exc:  # noqa: BLE001
                self._remove_temp_file(tmp_path)
                if legacy_exceptions:
                    raise
                return SearchAcquisitionReport(
                    items=[],
                    outcome=self._failure_outcome(url, exc, final_url=ffinal),
                )
            if blocked_subreason:
                self._remove_temp_file(tmp_path)
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "access_blocked",
                        url=url,
                        final_url=ffinal,
                        subreason=blocked_subreason,
                        reason=f"access blocked by {blocked_subreason} requirement",
                        failed=1,
                    ),
                )
            if not staged_is_file or self._content_type_mismatch(ffinal, fheaders):
                self._remove_temp_file(tmp_path)
                subreason = "redirect" if not staged_is_file else "content_type"
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "redirect_or_content_type_mismatch",
                        url=url,
                        final_url=ffinal,
                        subreason=subreason,
                        reason=f"download ended with {subreason} mismatch",
                        failed=1,
                    ),
                )
            filter_subreason = self._url_filter_subreason(ffinal, exclude, exclude_prefixes)
            filter_subreason = filter_subreason or self._downloaded_name_filter_subreason(
                ffinal,
                fheaders,
                exclude,
                exclude_prefixes,
            )
            if filter_subreason:
                self._remove_temp_file(tmp_path)
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "filtered",
                        url=url,
                        final_url=ffinal,
                        subreason=filter_subreason,
                        reason=f"download filtered by {filter_subreason} rule",
                        skipped=1,
                    ),
                )
            if cfg.check_database:
                try:
                    hash_exists = self.storage.file_exists_by_hash(sha256)
                except (OSError, sqlite3.Error) as exc:
                    self._remove_temp_file(tmp_path)
                    if legacy_exceptions:
                        raise
                    return SearchAcquisitionReport(
                        items=[],
                        outcome=self._failure_outcome(
                            url,
                            exc,
                            final_url=ffinal,
                            phase="storage",
                        ),
                    )
                if hash_exists:
                    self._remove_temp_file(tmp_path)
                    return SearchAcquisitionReport(
                        items=[],
                        outcome=make_acquisition_outcome(
                            "already_exists",
                            url=url,
                            final_url=ffinal,
                            subreason="content_hash",
                            reason="file already exists by content hash",
                            skipped=1,
                        ),
                    )
            if self.stop_check and self.stop_check():
                self._remove_temp_file(tmp_path)
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "stopped_or_timeout",
                        url=url,
                        final_url=ffinal,
                        subreason="stopped",
                        reason="task stopped by user",
                        failed=1,
                    ),
                )
            try:
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
            except Exception as exc:  # noqa: BLE001
                self._remove_temp_file(tmp_path)
                if legacy_exceptions:
                    raise
                return SearchAcquisitionReport(
                    items=[],
                    outcome=self._failure_outcome(
                        url,
                        exc,
                        final_url=ffinal,
                        phase="storage",
                    ),
                )
            if item:
                return SearchAcquisitionReport(
                    items=[item],
                    outcome=make_acquisition_outcome(
                        "downloaded_new",
                        url=url,
                        final_url=ffinal,
                        reason="downloaded 1 new file",
                        downloaded=1,
                    ),
                )
            duplicate_reason = self._existing_url_subreason(ffinal) if cfg.check_database else None
            if duplicate_reason or (
                cfg.check_database and self.storage.file_exists_by_hash(sha256)
            ):
                return SearchAcquisitionReport(
                    items=[],
                    outcome=make_acquisition_outcome(
                        "already_exists",
                        url=url,
                        final_url=ffinal,
                        subreason=duplicate_reason or "content_hash",
                        reason="file became a duplicate while being stored",
                        skipped=1,
                    ),
                )
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "no_eligible_file_found",
                    url=url,
                    final_url=ffinal,
                    subreason="empty",
                    reason="file handler produced no eligible file",
                    skipped=1,
                ),
            )

        html = data.decode("utf-8", errors="ignore")
        page_title, published_time = extract_metadata(html, final_url)
        page_text = html_to_text(html).lower()
        if self.stop_check and self.stop_check():
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "stopped_or_timeout",
                    url=url,
                    final_url=final_url,
                    subreason="stopped",
                    reason="task stopped by user",
                    failed=1,
                ),
            )
        page_relevant = any(k in page_text for k in keywords) if keywords else True
        if exclude and page_title and self._is_excluded(page_title, exclude):
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "filtered",
                    url=url,
                    final_url=final_url,
                    subreason="keyword",
                    reason="page title filtered by keyword rule",
                    skipped=1,
                ),
            )

        new_items: list[dict] = []
        duplicates: Counter[str] = Counter()
        filters: Counter[str] = Counter()
        failures: list[dict[str, object]] = []
        if cfg.collect_page_content:
            if not page_relevant:
                filters["keyword"] += 1
            else:
                if self.stop_check and self.stop_check():
                    return SearchAcquisitionReport(
                        items=[],
                        outcome=make_acquisition_outcome(
                            "stopped_or_timeout",
                            url=url,
                            final_url=final_url,
                            subreason="stopped",
                            reason="task stopped by user",
                            failed=1,
                        ),
                    )
                try:
                    page_item = self._handle_page_content(
                        final_url,
                        html,
                        page_title,
                        published_time,
                        cfg,
                        duplicate_counts=duplicates,
                    )
                except Exception as exc:  # noqa: BLE001
                    if legacy_exceptions:
                        raise
                    failures.append(
                        self._failure_outcome(url, exc, final_url=final_url, phase="storage")
                    )
                else:
                    if page_item:
                        new_items.append(page_item)

        links = self._extract_links(final_url, html, content_selector=cfg.content_selector)
        for link, link_text in links:
            if self.stop_check and self.stop_check():
                failures.append(
                    make_acquisition_outcome(
                        "stopped_or_timeout",
                        url=url,
                        final_url=final_url,
                        subreason="stopped",
                        reason="task stopped by user",
                        failed=1,
                    )
                )
                break
            if not self._is_file_url(link, exts):
                if self._is_file_url(link, DEFAULT_FILE_EXTS):
                    filters["extension"] += 1
                continue
            if cfg.collect_linked_files is False:
                filters["collection_disabled"] += 1
                continue
            filter_subreason = self._url_filter_subreason(link, exclude, exclude_prefixes)
            if filter_subreason:
                filters[filter_subreason] += 1
                continue
            if keywords and not (
                page_relevant or self._link_matches_keywords(link, link_text, keywords)
            ):
                filters["keyword"] += 1
                continue
            if cfg.check_database:
                try:
                    duplicate_reason = self._existing_url_subreason(link)
                except (OSError, sqlite3.Error) as exc:
                    if legacy_exceptions:
                        raise
                    failures.append(
                        self._failure_outcome(url, exc, final_url=link, phase="storage")
                    )
                    continue
                if duplicate_reason:
                    duplicates[duplicate_reason] += 1
                    continue
            parsed = urlparse(link)
            target_dir = Path(self.download_dir) / parsed.netloc.replace(":", "_")
            try:
                tmp_path, fheaders, ffinal, sha256, bytes_size = self._download_file(
                    link,
                    target_dir,
                    delay_seconds=cfg.delay_seconds,
                )
            except _AcquisitionStopped as exc:
                failures.append(self._failure_outcome(url, exc, final_url=link))
                break
            except Exception as exc:  # noqa: BLE001
                if legacy_exceptions:
                    continue
                failures.append(self._failure_outcome(url, exc, final_url=link))
                continue
            if self.stop_check and self.stop_check():
                self._remove_temp_file(tmp_path)
                failures.append(
                    make_acquisition_outcome(
                        "stopped_or_timeout",
                        url=url,
                        final_url=ffinal,
                        subreason="stopped",
                        reason="task stopped by user",
                        failed=1,
                    )
                )
                break
            staged_is_file = self._is_file_url(ffinal, exts)
            if self._is_file_url(ffinal, DEFAULT_FILE_EXTS) and not staged_is_file:
                self._remove_temp_file(tmp_path)
                filters["extension"] += 1
                continue
            try:
                blocked_subreason = self._staged_access_page_subreason(tmp_path, fheaders)
            except Exception as exc:  # noqa: BLE001
                self._remove_temp_file(tmp_path)
                if legacy_exceptions:
                    raise
                failures.append(self._failure_outcome(url, exc, final_url=ffinal))
                continue
            if blocked_subreason:
                self._remove_temp_file(tmp_path)
                failures.append(
                    make_acquisition_outcome(
                        "access_blocked",
                        url=url,
                        final_url=ffinal,
                        subreason=blocked_subreason,
                        reason=f"access blocked by {blocked_subreason} requirement",
                        failed=1,
                    )
                )
                continue
            if not staged_is_file or self._content_type_mismatch(ffinal, fheaders):
                self._remove_temp_file(tmp_path)
                failures.append(
                    make_acquisition_outcome(
                        "redirect_or_content_type_mismatch",
                        url=url,
                        final_url=ffinal,
                        subreason=("redirect" if not staged_is_file else "content_type"),
                        reason="linked file download ended with a redirect or content-type mismatch",
                        failed=1,
                    )
                )
                continue
            filter_subreason = self._url_filter_subreason(ffinal, exclude, exclude_prefixes)
            filter_subreason = filter_subreason or self._downloaded_name_filter_subreason(
                ffinal,
                fheaders,
                exclude,
                exclude_prefixes,
            )
            if filter_subreason:
                self._remove_temp_file(tmp_path)
                filters[filter_subreason] += 1
                continue
            if cfg.check_database:
                try:
                    hash_exists = self.storage.file_exists_by_hash(sha256)
                except (OSError, sqlite3.Error) as exc:
                    self._remove_temp_file(tmp_path)
                    if legacy_exceptions:
                        raise
                    failures.append(
                        self._failure_outcome(url, exc, final_url=ffinal, phase="storage")
                    )
                    continue
                if hash_exists:
                    self._remove_temp_file(tmp_path)
                    duplicates["content_hash"] += 1
                    continue
            if self.stop_check and self.stop_check():
                self._remove_temp_file(tmp_path)
                failures.append(
                    make_acquisition_outcome(
                        "stopped_or_timeout",
                        url=url,
                        final_url=ffinal,
                        subreason="stopped",
                        reason="task stopped by user",
                        failed=1,
                    )
                )
                break
            try:
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
            except Exception as exc:  # noqa: BLE001
                self._remove_temp_file(tmp_path)
                if legacy_exceptions:
                    raise
                failures.append(self._failure_outcome(url, exc, final_url=ffinal, phase="storage"))
                continue
            if item:
                new_items.append(item)
            elif cfg.check_database:
                try:
                    duplicate_reason = self._existing_url_subreason(ffinal)
                    hash_exists = not duplicate_reason and self.storage.file_exists_by_hash(sha256)
                except (OSError, sqlite3.Error) as exc:
                    self._remove_temp_file(tmp_path)
                    if legacy_exceptions:
                        raise
                    failures.append(
                        self._failure_outcome(url, exc, final_url=ffinal, phase="storage")
                    )
                    continue
                if duplicate_reason:
                    duplicates[duplicate_reason] += 1
                elif hash_exists:
                    duplicates["content_hash"] += 1

        stopped = next(
            (
                row
                for row in failures
                if row.get("disposition") == "stopped_or_timeout"
                and row.get("subreason") == "stopped"
            ),
            None,
        )
        if stopped:
            return SearchAcquisitionReport(
                items=new_items,
                outcome=make_acquisition_outcome(
                    "stopped_or_timeout",
                    url=url,
                    final_url=stopped.get("final_url") or final_url,
                    subreason="stopped",
                    reason="task stopped by user",
                    downloaded=len(new_items),
                    failed=1,
                ),
            )
        priority = (
            "storage_failed",
            "access_blocked",
            "redirect_or_content_type_mismatch",
            "download_failed",
            "stopped_or_timeout",
        )
        selected_failure = (
            next(
                row
                for disposition in priority
                for row in failures
                if row.get("disposition") == disposition
            )
            if failures
            else None
        )
        if new_items:
            if selected_failure:
                return SearchAcquisitionReport(
                    items=new_items,
                    outcome=make_acquisition_outcome(
                        str(selected_failure["disposition"]),
                        url=url,
                        final_url=str(selected_failure.get("final_url") or final_url),
                        http_status=selected_failure.get("http_status"),
                        subreason=str(selected_failure.get("subreason") or "other"),
                        reason=(
                            f"downloaded {len(new_items)} new file(s) with {len(failures)} failed linked "
                            f"acquisition(s): {selected_failure.get('reason')}"
                        ),
                        downloaded=len(new_items),
                        failed=1,
                    ),
                )
            return SearchAcquisitionReport(
                items=new_items,
                outcome=make_acquisition_outcome(
                    "downloaded_new",
                    url=url,
                    final_url=final_url,
                    reason=f"downloaded {len(new_items)} new file(s)",
                    downloaded=len(new_items),
                ),
            )
        if selected_failure:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    str(selected_failure["disposition"]),
                    url=url,
                    final_url=str(selected_failure.get("final_url") or final_url),
                    http_status=selected_failure.get("http_status"),
                    subreason=str(selected_failure.get("subreason") or "other"),
                    reason=(
                        f"{len(failures)} linked acquisition attempt(s) failed: "
                        f"{selected_failure.get('reason')}"
                    ),
                    failed=1,
                ),
            )
        duplicate_count = sum(duplicates.values())
        duplicate_subreason = duplicates.most_common(1)[0][0] if duplicate_count else "url"
        if duplicate_count and not filters:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "already_exists",
                    url=url,
                    final_url=final_url,
                    subreason=duplicate_subreason,
                    reason=f"{duplicate_count} eligible file(s) already exist by {duplicate_subreason}",
                    skipped=1,
                ),
            )
        if filters:
            filter_priority = ("keyword", "path", "extension", "collection_disabled", "domain")
            subreason = next((name for name in filter_priority if filters[name]), "other")
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "filtered",
                    url=url,
                    final_url=final_url,
                    subreason=subreason,
                    reason=f"eligible candidates filtered by {subreason} rule",
                    skipped=1,
                ),
            )
        if duplicate_count:
            return SearchAcquisitionReport(
                items=[],
                outcome=make_acquisition_outcome(
                    "already_exists",
                    url=url,
                    final_url=final_url,
                    subreason=duplicate_subreason,
                    reason=f"{duplicate_count} eligible file(s) already exist by {duplicate_subreason}",
                    skipped=1,
                ),
            )
        return SearchAcquisitionReport(
            items=[],
            outcome=make_acquisition_outcome(
                "no_eligible_file_found",
                url=url,
                final_url=final_url,
                subreason="empty",
                reason="no eligible file found",
                skipped=1,
            ),
        )

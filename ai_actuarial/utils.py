from __future__ import annotations

import hashlib
import json
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.get_text()
    return re.sub(r"\s+", " ", text).strip()


def extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def extract_published_time(html: str) -> str | None:
    meta_patterns = [
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']publishdate["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']date["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+property=["\']og:updated_time["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']dc.date["\'][^>]+content=["\'](.*?)["\']',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict):
                for key in ("datePublished", "dateCreated", "dateModified"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

    return None


def extract_metadata(html: str, url: str | None = None) -> tuple[str | None, str | None]:
    try:
        import trafilatura  # type: ignore
        from trafilatura.metadata import extract_metadata as tf_extract_metadata  # type: ignore
    except Exception:
        trafilatura = None
        tf_extract_metadata = None

    if trafilatura and tf_extract_metadata:
        try:
            downloaded = trafilatura.extract(
                html,
                output_format="json",
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            meta = tf_extract_metadata(html, url=url)
            title = None
            date = None
            if meta:
                title = getattr(meta, "title", None) or None
                date = getattr(meta, "date", None) or None
            if not title and downloaded:
                data = json.loads(downloaded)
                title = data.get("title") or None
                date = date or data.get("date") or None
            if title or date:
                return title, date
        except Exception:
            pass

    return extract_title(html), extract_published_time(html)


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


def normalize_url(base: str, link: str) -> str | None:
    if not link:
        return None
    link = link.strip()
    if not link:
        return None
    if link.startswith("mailto:") or link.startswith("javascript:"):
        return None
    return urljoin(base, link)


def sleep_with_jitter(seconds: float) -> None:
    if seconds <= 0:
        return
    time.sleep(seconds)


def load_category_config(config_path: str = "config/categories.yaml") -> dict:
    """Load category configuration from YAML file.
    
    Args:
        config_path: Path to categories.yaml file
        
    Returns:
        Dictionary with categories, ai_filter_keywords, and ai_keywords
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required to load category configuration")
    
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Category config not found: {config_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

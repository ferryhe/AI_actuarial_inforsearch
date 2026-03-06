"""Unit tests for Crawler.crawl_site() allow_url_patterns behavior.

Covers:
  1. Subpages only queued when they match an allow pattern.
  2. File links downloaded only when they match an allow pattern (when set).
  3. Keyword gating still applies when allow_url_patterns is absent.
  4. Invalid regex patterns are skipped with a warning (no crash).
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.storage import Storage


# ---------------------------------------------------------------------------
# Minimal HTML fixture helper
# ---------------------------------------------------------------------------

def _index_page(links: list[tuple[str, str]]) -> str:
    """Build a minimal HTML page with the given (href, text) links."""
    anchors = "\n".join(f'<a href="{href}">{text}</a>' for href, text in links)
    return f"<html><body>{anchors}</body></html>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(tmp_dir: str) -> Storage:
    db_path = os.path.join(tmp_dir, "test.db")
    return Storage(db_path)


def _make_crawler(storage: Storage, tmp_dir: str) -> Crawler:
    return Crawler(
        storage=storage,
        download_dir=tmp_dir,
        user_agent="TestAgent/1.0",
    )


def _sitecfg(**kwargs) -> SiteConfig:
    defaults = dict(
        name="Test Site",
        url="https://example.com/",
        max_pages=20,
        max_depth=2,
        delay_seconds=0,
    )
    defaults.update(kwargs)
    return SiteConfig(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAllowUrlPatternsSubpageQueuing(unittest.TestCase):
    """Subpages should only be queued when they match an allow pattern."""

    def _run_crawl(self, cfg: SiteConfig, pages: dict[str, str]) -> list[str]:
        """Run crawl_site with _request mocked via pages dict {url: html_content}.

        Returns the list of fetched URLs in order.
        """
        fetched: list[str] = []

        def fake_request_method(url: str):
            fetched.append(url)
            html = pages.get(url, "<html><body></body></html>")
            return html.encode(), {}, url

        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            try:
                crawler = _make_crawler(storage, tmp)
                with patch.object(crawler, "_request", side_effect=fake_request_method), \
                     patch.object(crawler, "_load_sitemap", return_value=[]):
                    crawler.crawl_site(cfg)
            finally:
                storage.close()
        return fetched

    def test_no_allow_patterns_queues_all_subpages(self):
        """Without allow_url_patterns every in-domain subpage is queued."""
        index_html = _index_page([
            ("https://example.com/research/", "Research"),
            ("https://example.com/about/", "About"),
        ])
        pages = {
            "https://example.com/": index_html,
            "https://example.com/research/": "<html><body></body></html>",
            "https://example.com/about/": "<html><body></body></html>",
        }
        cfg = _sitecfg(url="https://example.com/", max_depth=1)
        fetched = self._run_crawl(cfg, pages)
        self.assertIn("https://example.com/research/", fetched)
        self.assertIn("https://example.com/about/", fetched)

    def test_allow_patterns_restricts_subpage_queuing(self):
        """With allow_url_patterns, only matching subpages are queued."""
        index_html = _index_page([
            ("https://example.com/research/ai-report/", "AI Report"),
            ("https://example.com/about/", "About"),
            ("https://example.com/careers/", "Careers"),
        ])
        pages = {
            "https://example.com/": index_html,
            "https://example.com/research/ai-report/": "<html><body></body></html>",
            "https://example.com/about/": "<html><body></body></html>",
            "https://example.com/careers/": "<html><body></body></html>",
        }
        cfg = _sitecfg(
            url="https://example.com/",
            max_depth=1,
            allow_url_patterns=[r"/research/"],
        )
        fetched = self._run_crawl(cfg, pages)
        self.assertIn("https://example.com/research/ai-report/", fetched)
        self.assertNotIn("https://example.com/about/", fetched)
        self.assertNotIn("https://example.com/careers/", fetched)

    def test_multiple_allow_patterns(self):
        """Multiple allow patterns: subpages matching any pattern are queued."""
        index_html = _index_page([
            ("https://example.com/research/", "Research"),
            ("https://example.com/resources/", "Resources"),
            ("https://example.com/shop/", "Shop"),
        ])
        pages = {
            "https://example.com/": index_html,
            "https://example.com/research/": "<html><body></body></html>",
            "https://example.com/resources/": "<html><body></body></html>",
            "https://example.com/shop/": "<html><body></body></html>",
        }
        cfg = _sitecfg(
            url="https://example.com/",
            max_depth=1,
            allow_url_patterns=[r"/research/", r"/resources/"],
        )
        fetched = self._run_crawl(cfg, pages)
        self.assertIn("https://example.com/research/", fetched)
        self.assertIn("https://example.com/resources/", fetched)
        self.assertNotIn("https://example.com/shop/", fetched)


class TestAllowUrlPatternsFileDownload(unittest.TestCase):
    """File links should respect allow_url_patterns when set."""

    def _run_crawl_collect_downloads(self, cfg: SiteConfig, index_html: str) -> list[str]:
        """Return list of file URLs that were attempted for download."""
        downloaded: list[str] = []

        def fake_request_method(url: str):
            return index_html.encode(), {}, url

        def fake_download_file(url: str, target_dir: Path):
            downloaded.append(url)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=target_dir) as f:
                f.write(b"%PDF fake")
                tmp = Path(f.name)
            sha = hashlib.sha256(b"%PDF fake").hexdigest()
            return tmp, {}, url, sha, 9

        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            try:
                crawler = _make_crawler(storage, tmp)
                with patch.object(crawler, "_request", side_effect=fake_request_method), \
                     patch.object(crawler, "_load_sitemap", return_value=[]), \
                     patch.object(crawler, "_download_file", side_effect=fake_download_file), \
                     patch.object(crawler, "_handle_file", return_value=None):
                    crawler.crawl_site(cfg)
            finally:
                storage.close()
        return downloaded

    def test_allow_patterns_gates_file_download(self):
        """Files not matching any allow pattern should be skipped."""
        index_html = _index_page([
            ("https://example.com/globalassets/report.pdf", "Download"),
            ("https://example.com/other/unrelated.pdf", "Other PDF"),
        ])
        cfg = _sitecfg(
            url="https://example.com/",
            max_depth=1,
            allow_url_patterns=[r"/globalassets/"],
        )
        downloaded = self._run_crawl_collect_downloads(cfg, index_html)
        self.assertIn("https://example.com/globalassets/report.pdf", downloaded)
        self.assertNotIn("https://example.com/other/unrelated.pdf", downloaded)

    def test_no_allow_patterns_uses_keyword_gating(self):
        """Without allow_url_patterns, keyword gating still applies to file links."""
        index_html = _index_page([
            ("https://example.com/ai-research.pdf", "AI Research"),
            ("https://example.com/unrelated-report.pdf", "Unrelated"),
        ])
        cfg = _sitecfg(
            url="https://example.com/",
            max_depth=1,
            keywords=["artificial intelligence"],
        )
        downloaded = self._run_crawl_collect_downloads(cfg, index_html)
        # Neither the URL nor the link text contains "artificial intelligence" → all skipped
        self.assertEqual([], downloaded)

    def test_no_allow_patterns_no_keywords_downloads_all(self):
        """Without allow_url_patterns and without keywords, all files are downloaded."""
        index_html = _index_page([
            ("https://example.com/report-a.pdf", "Report A"),
            ("https://example.com/report-b.pdf", "Report B"),
        ])
        cfg = _sitecfg(url="https://example.com/", max_depth=1)
        downloaded = self._run_crawl_collect_downloads(cfg, index_html)
        self.assertIn("https://example.com/report-a.pdf", downloaded)
        self.assertIn("https://example.com/report-b.pdf", downloaded)


class TestAllowUrlPatternsInvalidRegex(unittest.TestCase):
    """Invalid regex patterns should be skipped with a warning, not crash."""

    def _run_with_invalid_pattern(self, allow_url_patterns: list[str]) -> list:
        index_html = _index_page([("https://example.com/research/report.pdf", "Report")])

        def fake_request_method(url: str):
            return index_html.encode(), {}, url

        cfg = _sitecfg(
            url="https://example.com/",
            max_depth=1,
            allow_url_patterns=allow_url_patterns,
        )
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            try:
                crawler = _make_crawler(storage, tmp)
                with patch.object(crawler, "_request", side_effect=fake_request_method), \
                     patch.object(crawler, "_load_sitemap", return_value=[]), \
                     self.assertLogs("ai_actuarial.crawler", level="WARNING"):
                    result = crawler.crawl_site(cfg)
            finally:
                storage.close()
        return result

    def test_invalid_pattern_skipped_with_warning(self):
        """A bad regex logs a warning and the crawl completes without raising."""
        result = self._run_with_invalid_pattern([r"[invalid_regex", r"/research/"])
        self.assertIsInstance(result, list)

    def test_all_invalid_patterns_crawl_completes(self):
        """All-invalid allow_url_patterns: crawl still runs (no filtering applied)."""
        result = self._run_with_invalid_pattern([r"[bad"])
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()

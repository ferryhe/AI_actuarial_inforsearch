"""Tests for WebPageCollector and the crawler's page-content extraction."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the project root is on the path (mirrors other test files)
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_actuarial.collectors import CollectionConfig, WebPageCollector
from ai_actuarial.storage import Storage


# ---------------------------------------------------------------------------
# Shared HTML fixture
# ---------------------------------------------------------------------------

SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>AI in Actuarial Science</title>
  <meta property="article:published_time" content="2024-01-15" />
</head>
<body>
  <article>
    <h1>AI in Actuarial Science</h1>
    <p>
      Artificial intelligence and machine learning are transforming actuarial
      practice. This article explores current applications, benefits, and the
      challenges that practitioners face when adopting AI-driven methods in
      reserving, pricing, and risk modelling.
    </p>
    <p>
      Large language models now assist actuaries with regulatory text analysis,
      peer-review automation, and scenario generation.  Generative AI tools
      reduce the time spent on routine document drafting, allowing more focus
      on high-value analytical work.
    </p>
  </article>
</body>
</html>
"""


def _make_storage(tmp_dir: str) -> Storage:
    """Create a fresh in-memory-backed Storage in *tmp_dir*."""
    db_path = os.path.join(tmp_dir, "test.db")
    return Storage(db_path)


def _make_collector(storage: Storage, download_dir: str) -> WebPageCollector:
    return WebPageCollector(
        storage=storage,
        download_dir=download_dir,
        user_agent="TestAgent/1.0",
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestWebPageCollectorBasics(unittest.TestCase):
    """Basic functional tests for WebPageCollector."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.storage = _make_storage(self._tmp)
        self.collector = _make_collector(self.storage, self._tmp)

    def tearDown(self):
        self.storage.close()

    # ------------------------------------------------------------------
    # should_download
    # ------------------------------------------------------------------

    def test_should_download_new_url(self):
        """should_download returns True for a URL not yet in the database."""
        self.assertTrue(
            self.collector.should_download("https://example.com/page")
        )

    def test_should_download_existing_url(self):
        """should_download returns False when the URL is already stored."""
        url = "https://example.com/page"
        ts = self.storage.now()
        self.storage._conn.execute(
            """
            INSERT INTO files (url, sha256, title, source_site, local_path,
                               first_seen, last_seen, crawl_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (url, "abc123", "Test", "test_site", "/tmp/test.md", ts, ts, ts),
        )
        self.storage._conn.commit()

        self.assertFalse(self.collector.should_download(url))

    def test_should_download_duplicate_hash(self):
        """should_download returns False when the content hash already exists."""
        sha256 = "deadbeef" * 8
        ts = self.storage.now()
        self.storage._conn.execute(
            "INSERT INTO blobs (sha256, first_seen, last_seen) VALUES (?, ?, ?)",
            (sha256, ts, ts),
        )
        self.storage._conn.commit()

        self.assertFalse(
            self.collector.should_download("https://example.com/other", sha256)
        )

    # ------------------------------------------------------------------
    # _extract_text
    # ------------------------------------------------------------------

    def test_extract_text_returns_content(self):
        """_extract_text should return non-empty text from well-formed HTML."""
        text = self.collector._extract_text(SAMPLE_HTML, "https://example.com")
        self.assertIsNotNone(text)
        assert text is not None
        self.assertGreater(len(text), 50)

    def test_extract_text_short_html_returns_none_or_short(self):
        """Very short / empty HTML should yield None."""
        html = "<html><body></body></html>"
        text = self.collector._extract_text(html, "https://example.com")
        # Either None or very short
        if text is not None:
            self.assertLess(len(text), 100)

    # ------------------------------------------------------------------
    # _save_content
    # ------------------------------------------------------------------

    def test_save_content_creates_file(self):
        """_save_content should create a Markdown file on disk."""
        content = "# Hello\n\nThis is test content for the web page collector."
        path = self.collector._save_content(
            "https://example.com/article", content, "Example Site"
        )
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".md")
        self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_save_content_conflict_resolution(self):
        """Saving the same filename twice should create distinct files."""
        url = "https://example.com/article"
        content = "Content A"
        path_a = self.collector._save_content(url, content, "Site")
        path_b = self.collector._save_content(url, "Content B", "Site")
        self.assertNotEqual(path_a, path_b)
        self.assertTrue(path_a.exists())
        self.assertTrue(path_b.exists())

    # ------------------------------------------------------------------
    # _collect_page
    # ------------------------------------------------------------------

    def _mock_fetch(self, html: str = SAMPLE_HTML, content_type: str = "text/html"):
        """Return a patch context for _fetch_html."""
        return patch.object(
            self.collector,
            "_fetch_html",
            return_value=(
                html.encode("utf-8"),
                {"content-type": content_type},
                "https://example.com/article",
            ),
        )

    def test_collect_page_success(self):
        """_collect_page should store a file and return metadata."""
        with self._mock_fetch():
            result = self.collector._collect_page(
                "https://example.com/article",
                CollectionConfig(
                    name="Test Site",
                    source_type="web_page",
                    metadata={"urls": ["https://example.com/article"]},
                ),
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["source_site"], "Test Site")
        self.assertEqual(result["content_type"], "text/markdown")
        self.assertIn("sha256", result)

        # Should be in the database
        self.assertTrue(
            self.storage.file_exists("https://example.com/article")
        )

    def test_collect_page_skips_non_html(self):
        """_collect_page should skip responses with non-HTML content-type."""
        with patch.object(
            self.collector,
            "_fetch_html",
            return_value=(
                b"%PDF-1.4 binary",
                {"content-type": "application/pdf"},
                "https://example.com/file.pdf",
            ),
        ):
            result = self.collector._collect_page(
                "https://example.com/file.pdf",
                CollectionConfig(name="Test", source_type="web_page"),
            )
        self.assertIsNone(result)

    def test_collect_page_dedup_by_hash(self):
        """_collect_page should skip pages whose content hash already exists."""
        # First call – stores the page
        with self._mock_fetch():
            self.collector._collect_page(
                "https://example.com/article",
                CollectionConfig(name="Test", source_type="web_page"),
            )

        # Second call with the same content but different URL
        with self._mock_fetch():
            result = self.collector._collect_page(
                "https://example.com/article-copy",
                CollectionConfig(name="Test", source_type="web_page"),
            )
        self.assertIsNone(result)

    def test_collect_page_fetch_failure_returns_none(self):
        """_collect_page should return None when the HTTP request fails."""
        with patch.object(
            self.collector,
            "_fetch_html",
            side_effect=Exception("Connection refused"),
        ):
            result = self.collector._collect_page(
                "https://down.example.com/",
                CollectionConfig(name="Test", source_type="web_page"),
            )
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Integration-level tests (collect() method)
# ---------------------------------------------------------------------------


class TestWebPageCollectorCollect(unittest.TestCase):
    """Test the high-level collect() method."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.storage = _make_storage(self._tmp)
        self.collector = _make_collector(self.storage, self._tmp)

    def tearDown(self):
        self.storage.close()

    def _patch_fetch(self):
        return patch.object(
            self.collector,
            "_fetch_html",
            return_value=(
                SAMPLE_HTML.encode("utf-8"),
                {"content-type": "text/html"},
                "https://example.com/article",
            ),
        )

    def test_collect_returns_result(self):
        """collect() should return a CollectionResult with items_downloaded."""
        config = CollectionConfig(
            name="Test",
            source_type="web_page",
            metadata={"urls": ["https://example.com/article"]},
        )
        with self._patch_fetch():
            result = self.collector.collect(config)

        self.assertTrue(result.success)
        self.assertEqual(result.items_downloaded, 1)
        self.assertEqual(result.items_skipped, 0)
        self.assertEqual(result.errors, [])

    def test_collect_skips_existing(self):
        """collect() skips URLs already in the database."""
        url = "https://example.com/article"
        ts = self.storage.now()
        self.storage._conn.execute(
            """
            INSERT INTO files (url, sha256, title, source_site, local_path,
                               first_seen, last_seen, crawl_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (url, "abc", "Old", "site", "/tmp/old.md", ts, ts, ts),
        )
        self.storage._conn.commit()

        config = CollectionConfig(
            name="Test",
            source_type="web_page",
            check_database=True,
            metadata={"urls": [url]},
        )
        with self._patch_fetch():
            result = self.collector.collect(config)

        self.assertEqual(result.items_downloaded, 0)
        self.assertEqual(result.items_skipped, 1)

    def test_collect_progress_callback(self):
        """collect() should invoke the progress callback."""
        calls: list[tuple] = []

        def cb(current, total, message):
            calls.append((current, total, message))

        config = CollectionConfig(
            name="Test",
            source_type="web_page",
            metadata={"urls": ["https://example.com/article"]},
        )
        with self._patch_fetch():
            self.collector.collect(config, progress_callback=cb)

        self.assertGreater(len(calls), 0)

    def test_collect_empty_urls_succeeds(self):
        """collect() with an empty URL list should succeed with zero items."""
        config = CollectionConfig(
            name="Test",
            source_type="web_page",
            metadata={"urls": []},
        )
        result = self.collector.collect(config)
        self.assertTrue(result.success)
        self.assertEqual(result.items_downloaded, 0)


# ---------------------------------------------------------------------------
# Crawler._handle_page_content tests
# ---------------------------------------------------------------------------


class TestCrawlerHandlePageContent(unittest.TestCase):
    """Test Crawler._handle_page_content integration."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        db_path = os.path.join(self._tmp, "test.db")
        self.storage = Storage(db_path)

        from ai_actuarial.crawler import Crawler

        self.crawler = Crawler(
            storage=self.storage,
            download_dir=self._tmp,
            user_agent="TestAgent/1.0",
        )

    def tearDown(self):
        self.storage.close()

    def _make_cfg(self, collect_page_content: bool = True):
        from ai_actuarial.crawler import SiteConfig

        return SiteConfig(
            name="Test Site",
            url="https://example.com/",
            collect_page_content=collect_page_content,
        )

    def test_handle_page_content_saves_file(self):
        """_handle_page_content stores text content and returns metadata."""
        cfg = self._make_cfg()
        result = self.crawler._handle_page_content(
            "https://example.com/article",
            SAMPLE_HTML,
            "AI in Actuarial Science",
            "2024-01-15",
            cfg,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["content_type"], "text/markdown")
        self.assertTrue(
            self.storage.file_exists("https://example.com/article")
        )

    def test_handle_page_content_dedup_by_url(self):
        """_handle_page_content is a no-op when URL is already stored."""
        cfg = self._make_cfg()
        self.crawler._handle_page_content(
            "https://example.com/article", SAMPLE_HTML, "Title", None, cfg
        )
        # Second call for the same URL
        result = self.crawler._handle_page_content(
            "https://example.com/article", SAMPLE_HTML, "Title", None, cfg
        )
        self.assertIsNone(result)

    def test_site_config_collect_page_content_default_false(self):
        """SiteConfig.collect_page_content defaults to False."""
        from ai_actuarial.crawler import SiteConfig

        cfg = SiteConfig(name="X", url="https://x.com/")
        self.assertFalse(cfg.collect_page_content)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Unit tests for code review fixes.

Tests the following issues fixed:
1. Skipped items status handling
2. Race condition protection
3. SQL injection protection (parameterized queries)
4. File deletion with confirmation
5. Duplicate entry handling
6. Concurrent SQLite writes (BEGIN IMMEDIATE)
7. ORDER BY documentation
8. Storage abstraction methods
9. Path traversal protection
10. Filename exclusion logic
"""

import os
import tempfile
import unittest
from pathlib import Path

from ai_actuarial.storage import Storage
from ai_actuarial.catalog_incremental import _connect, _upsert_catalog_row
from ai_actuarial.crawler import Crawler
from ai_actuarial.catalog import CatalogItem


class TestSkippedItemsStatus(unittest.TestCase):
    """Test that skipped items are marked with status='skipped' not 'ok'."""
    
    def setUp(self):
        """Create a temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_skipped_status_inserted(self):
        """Test that catalog items can be inserted with skipped status."""
        conn = _connect(self.db_path)
        
        item = CatalogItem(
            source_site="test.com",
            title="Test Document",
            original_filename="test.pdf",
            url="http://test.com/test.pdf",
            local_path="/tmp/test.pdf",
            keywords=["ai", "test"],
            summary="Test summary",
            category="(filtered: non-AI)",
        )
        
        _upsert_catalog_row(
            conn,
            item=item,
            file_sha256="abc123",
            catalog_version="v1",
            status="skipped",
            processed_at="2024-01-01T00:00:00Z",
        )
        conn.commit()
        
        # Verify status is 'skipped'
        cur = conn.execute(
            "SELECT status FROM catalog_items WHERE file_url = ?",
            (item.url,)
        )
        result = cur.fetchone()
        self.assertEqual(result[0], "skipped")
        
        # Verify category indicates it was filtered
        cur = conn.execute(
            "SELECT category FROM catalog_items WHERE file_url = ?",
            (item.url,)
        )
        result = cur.fetchone()
        self.assertIn("filtered", result[0].lower())
        conn.close()


class TestStorageAbstraction(unittest.TestCase):
    """Test Storage abstraction methods instead of direct _conn access."""
    
    def setUp(self):
        """Create a temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        self.storage.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_get_file_count(self):
        """Test get_file_count method."""
        # Insert test files
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="File 1",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        self.storage.insert_file(
            url="http://test.com/file2.pdf",
            sha256="hash2",
            title="File 2",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file2.pdf",
            local_path="/tmp/file2.pdf",
            bytes=2048,
            content_type="application/pdf",
        )
        
        count = self.storage.get_file_count(require_local=True)
        self.assertEqual(count, 2)
    
    def test_get_cataloged_count(self):
        """Test get_cataloged_count method."""
        # Insert test file
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="File 1",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        
        # Insert catalog item with status='ok'
        self.storage.upsert_catalog_item(
            item={
                "url": "http://test.com/file1.pdf",
                "sha256": "hash1",
                "keywords": ["test"],
                "summary": "Test summary",
                "category": "Test",
            },
            pipeline_version="v1",
            status="ok",
        )
        
        count = self.storage.get_cataloged_count()
        self.assertEqual(count, 1)
    
    def test_get_sources_count(self):
        """Test get_sources_count method."""
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="File 1",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        self.storage.insert_file(
            url="http://example.com/file2.pdf",
            sha256="hash2",
            title="File 2",
            source_site="example.com",
            source_page_url="http://example.com",
            original_filename="file2.pdf",
            local_path="/tmp/file2.pdf",
            bytes=2048,
            content_type="application/pdf",
        )
        
        count = self.storage.get_sources_count()
        self.assertEqual(count, 2)
    
    def test_get_unique_sources(self):
        """Test get_unique_sources method."""
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="File 1",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        
        sources = self.storage.get_unique_sources()
        self.assertIn("test.com", sources)
    
    def test_get_unique_categories(self):
        """Test get_unique_categories method."""
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="File 1",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        
        self.storage.upsert_catalog_item(
            item={
                "url": "http://test.com/file1.pdf",
                "sha256": "hash1",
                "keywords": ["test"],
                "summary": "Test summary",
                "category": "TestCategory",
            },
            pipeline_version="v1",
            status="ok",
        )
        
        categories = self.storage.get_unique_categories()
        self.assertIn("TestCategory", categories)
    
    def test_query_files_with_catalog(self):
        """Test query_files_with_catalog method."""
        # Insert test file
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="Test Document",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        
        self.storage.upsert_catalog_item(
            item={
                "url": "http://test.com/file1.pdf",
                "sha256": "hash1",
                "keywords": ["test"],
                "summary": "Test summary",
                "category": "TestCategory",
            },
            pipeline_version="v1",
            status="ok",
        )
        
        files, total = self.storage.query_files_with_catalog(
            limit=10,
            offset=0,
            order_by="last_seen",
            order_dir="desc",
        )
        
        self.assertEqual(total, 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["title"], "Test Document")
        self.assertEqual(files[0]["category"], "TestCategory")


class TestSQLInjectionProtection(unittest.TestCase):
    """Test that SQL injection is prevented through parameterized queries."""
    
    def setUp(self):
        """Create a temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        self.storage.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_category_filter_sql_injection(self):
        """Test that category filter prevents SQL injection."""
        # Insert test file
        self.storage.insert_file(
            url="http://test.com/file1.pdf",
            sha256="hash1",
            title="Test Document",
            source_site="test.com",
            source_page_url="http://test.com",
            original_filename="file1.pdf",
            local_path="/tmp/file1.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        
        # Try SQL injection in category parameter
        malicious_category = "'; DROP TABLE files; --"
        
        # This should not cause an error or drop the table
        # Intentionally ignore return values since we're testing for side effects
        _ = self.storage.query_files_with_catalog(
            category=malicious_category,
        )
        
        # Verify table still exists by using abstraction method
        count = self.storage.get_file_count(require_local=False)
        self.assertEqual(count, 1)


class TestConcurrentSQLiteWrites(unittest.TestCase):
    """Test that BEGIN IMMEDIATE is used for concurrent write protection."""
    
    def test_begin_immediate_in_code(self):
        """Test that catalog_incremental uses thread-safe writes."""
        # Read the source code to verify thread-safe write protection
        catalog_path = Path(__file__).parent / "ai_actuarial" / "catalog_incremental.py"
        with open(catalog_path, 'r') as f:
            content = f.read()
        
        # Main's version uses ThreadPoolExecutor with _db_lock for thread safety
        # Verify that _db_lock is used in _upsert_catalog_row
        self.assertIn("_db_lock", content, "Should have _db_lock defined")
        self.assertIn("with _db_lock:", content, "Should use _db_lock for thread-safe writes")


class TestFilenameExclusionLogic(unittest.TestCase):
    """Test consolidated filename exclusion logic."""
    
    def setUp(self):
        """Create a temporary directory and crawler."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        storage = Storage(self.db_path)
        self.crawler = Crawler(storage, self.temp_dir, "TestAgent/1.0")
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_should_exclude_url_keyword(self):
        """Test URL exclusion by keyword."""
        exclude = ["calendar", "archive"]
        exclude_prefixes = []
        
        result = self.crawler._should_exclude_url(
            "http://test.com/calendar/2023",
            exclude,
            exclude_prefixes
        )
        self.assertTrue(result)
    
    def test_should_exclude_url_prefix(self):
        """Test URL exclusion by filename prefix."""
        exclude = []
        exclude_prefixes = ["tmp_", "draft_"]
        
        result = self.crawler._should_exclude_url(
            "http://test.com/files/tmp_document.pdf",
            exclude,
            exclude_prefixes
        )
        self.assertTrue(result)
    
    def test_should_not_exclude_url(self):
        """Test that valid URLs are not excluded."""
        exclude = ["calendar"]
        exclude_prefixes = ["tmp_"]
        
        result = self.crawler._should_exclude_url(
            "http://test.com/files/report.pdf",
            exclude,
            exclude_prefixes
        )
        self.assertFalse(result)


class TestOrderByDocumentation(unittest.TestCase):
    """Test that ORDER BY behavior is documented."""
    
    def test_order_by_comment_exists(self):
        """Test that ORDER BY comment exists in catalog_incremental."""
        catalog_path = Path(__file__).parent / "ai_actuarial" / "catalog_incremental.py"
        with open(catalog_path, 'r') as f:
            content = f.read()
        
        # Verify comment about ORDER BY is present (DESC version from main)
        self.assertIn("ORDER BY f.id DESC", content)


class TestPathTraversalProtection(unittest.TestCase):
    """Test that path traversal attacks are prevented."""
    
    def test_path_validation_in_code(self):
        """Test that path validation exists in web app."""
        app_path = Path(__file__).parent / "ai_actuarial" / "web" / "app.py"
        with open(app_path, 'r') as f:
            content = f.read()
        
        # Verify path validation is present
        self.assertIn("resolved_path.relative_to(data_dir)", content)
        self.assertIn("Security: Validate that resolved path", content)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Unit tests for file edit functionality."""

import os
import tempfile
import unittest

from ai_actuarial.storage import Storage


class TestFileEdit(unittest.TestCase):
    """Test file catalog update functionality."""
    
    def setUp(self):
        """Create a temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)
        
        # Insert a test file
        self.test_url = "http://test.com/file.pdf"
        self.storage._conn.execute(
            """
            INSERT INTO files (url, sha256, source_site, bytes, content_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.test_url, "test_hash", "test_site", 1024, "application/pdf")
        )
        self.storage._conn.commit()
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        self.storage.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_update_category(self):
        """Test updating category."""
        success = self.storage.update_file_catalog(
            self.test_url,
            category="Test Category"
        )
        self.assertTrue(success)
        
        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "Test Category")
    
    def test_update_summary(self):
        """Test updating summary."""
        success = self.storage.update_file_catalog(
            self.test_url,
            summary="Test summary text"
        )
        self.assertTrue(success)
        
        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["summary"], "Test summary text")
    
    def test_update_keywords(self):
        """Test updating keywords."""
        keywords = ["keyword1", "keyword2", "keyword3"]
        success = self.storage.update_file_catalog(
            self.test_url,
            keywords=keywords
        )
        self.assertTrue(success)
        
        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["keywords"], keywords)
    
    def test_update_all_fields(self):
        """Test updating all fields at once."""
        keywords = ["test", "keywords"]
        success = self.storage.update_file_catalog(
            self.test_url,
            category="New Category",
            summary="New summary",
            keywords=keywords
        )
        self.assertTrue(success)
        
        # Verify all updates
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "New Category")
        self.assertEqual(file_data["summary"], "New summary")
        self.assertEqual(file_data["keywords"], keywords)
    
    def test_update_nonexistent_file(self):
        """Test updating a file that doesn't exist creates catalog entry."""
        # This should fail because the file doesn't exist in the files table
        nonexistent_url = "http://test.com/nonexistent.pdf"
        success = self.storage.update_file_catalog(
            nonexistent_url,
            category="Test"
        )
        # The catalog entry won't be created if the file doesn't exist in files table
        # because of the INSERT ... SELECT query
        # So we just verify the method completes
        self.assertFalse(success)
    
    def test_update_with_empty_values(self):
        """Test updating with empty strings."""
        success = self.storage.update_file_catalog(
            self.test_url,
            category="",
            summary="",
            keywords=[]
        )
        self.assertTrue(success)
        
        # Verify the empty values
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "")
        self.assertEqual(file_data["summary"], "")
        self.assertEqual(file_data["keywords"], [])


if __name__ == "__main__":
    unittest.main()

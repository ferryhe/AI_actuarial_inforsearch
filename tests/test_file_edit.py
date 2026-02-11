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
        
        # Insert a test file using the public Storage API
        self.test_url = "http://test.com/file.pdf"
        self.storage.insert_file(
            url=self.test_url,
            sha256="test_hash",
            title="Test File",
            source_site="test_site",
            source_page_url="http://test.com",
            original_filename="file.pdf",
            local_path="/tmp/file.pdf",
            bytes=1024,
            content_type="application/pdf"
        )
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        self.storage.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_update_category(self):
        """Test updating category."""
        success, error = self.storage.update_file_catalog(
            self.test_url,
            category="Test Category"
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "Test Category")
    
    def test_update_summary(self):
        """Test updating summary."""
        success, error = self.storage.update_file_catalog(
            self.test_url,
            summary="Test summary text"
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["summary"], "Test summary text")
    
    def test_update_keywords(self):
        """Test updating keywords."""
        keywords = ["keyword1", "keyword2", "keyword3"]
        success, error = self.storage.update_file_catalog(
            self.test_url,
            keywords=keywords
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["keywords"], keywords)
    
    def test_update_all_fields(self):
        """Test updating all fields at once."""
        keywords = ["test", "keywords"]
        success, error = self.storage.update_file_catalog(
            self.test_url,
            category="New Category",
            summary="New summary",
            keywords=keywords
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify all updates
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "New Category")
        self.assertEqual(file_data["summary"], "New summary")
        self.assertEqual(file_data["keywords"], keywords)
    
    def test_update_nonexistent_file(self):
        """Test updating a nonexistent file returns file_not_found error."""
        nonexistent_url = "http://test.com/nonexistent.pdf"
        success, error = self.storage.update_file_catalog(
            nonexistent_url,
            category="Test"
        )
        self.assertFalse(success)
        self.assertEqual(error, "file_not_found")
    
    def test_update_with_empty_values(self):
        """Test updating with empty strings."""
        success, error = self.storage.update_file_catalog(
            self.test_url,
            category="",
            summary="",
            keywords=[]
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify the empty values
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "")
        self.assertEqual(file_data["summary"], "")
        self.assertEqual(file_data["keywords"], [])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for markdown functionality - storage layer and API endpoints."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from ai_actuarial.storage import Storage


class TestMarkdownStorage(unittest.TestCase):
    """Test Storage layer markdown methods."""
    
    def setUp(self):
        """Create a temporary database for each test."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.storage = Storage(self.db_path)
        
        # Insert a test file
        self.test_url = "file:///test/document.pdf"
        self.storage._conn.execute(
            """
            INSERT INTO files (url, sha256, title, source_site, content_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.test_url, "test123", "Test Document", "Test Site", "application/pdf")
        )
        self.storage._conn.commit()
    
    def tearDown(self):
        """Close storage and remove temporary database."""
        self.storage.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_update_file_markdown_success(self):
        """Test successfully updating markdown content."""
        markdown_content = "# Test Document\n\nThis is a test."
        success, error = self.storage.update_file_markdown(
            url=self.test_url,
            markdown_content=markdown_content,
            markdown_source="manual"
        )
        
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify content was saved
        markdown_data = self.storage.get_file_markdown(self.test_url)
        self.assertIsNotNone(markdown_data)
        self.assertEqual(markdown_data['markdown_content'], markdown_content)
        self.assertEqual(markdown_data['markdown_source'], "manual")
        self.assertIsNotNone(markdown_data['markdown_updated_at'])
    
    def test_update_file_markdown_file_not_found(self):
        """Test updating markdown for non-existent file."""
        success, error = self.storage.update_file_markdown(
            url="file:///nonexistent/file.pdf",
            markdown_content="# Test",
            markdown_source="manual"
        )
        
        self.assertFalse(success)
        self.assertEqual(error, "file_not_found")
    
    def test_get_file_markdown_empty(self):
        """Test getting markdown when none exists."""
        markdown_data = self.storage.get_file_markdown(self.test_url)
        
        # Should return None since no catalog entry exists yet
        self.assertIsNone(markdown_data)
    
    def test_get_file_markdown_with_content(self):
        """Test getting markdown after it's been saved."""
        # First save some markdown
        markdown_content = "# Test\n\n## Section"
        self.storage.update_file_markdown(
            self.test_url, markdown_content, "converted_marker"
        )
        
        # Then retrieve it
        markdown_data = self.storage.get_file_markdown(self.test_url)
        
        self.assertIsNotNone(markdown_data)
        self.assertEqual(markdown_data['markdown_content'], markdown_content)
        self.assertEqual(markdown_data['markdown_source'], "converted_marker")
    
    def test_update_file_markdown_creates_catalog_entry(self):
        """Test that updating markdown creates catalog entry if missing."""
        # Verify no catalog entry exists
        cur = self.storage._conn.execute(
            "SELECT file_url FROM catalog_items WHERE file_url = ?",
            (self.test_url,)
        )
        self.assertIsNone(cur.fetchone())
        
        # Update markdown
        self.storage.update_file_markdown(
            self.test_url, "# Test", "manual"
        )
        
        # Verify catalog entry was created
        cur = self.storage._conn.execute(
            "SELECT file_url FROM catalog_items WHERE file_url = ?",
            (self.test_url,)
        )
        self.assertIsNotNone(cur.fetchone())
    
    def test_get_file_with_catalog_includes_markdown(self):
        """Test that get_file_with_catalog includes markdown fields."""
        # Save some markdown
        markdown_content = "# Document\n\nContent here."
        self.storage.update_file_markdown(
            self.test_url, markdown_content, "manual"
        )
        
        # Get file with catalog
        file_data = self.storage.get_file_with_catalog(self.test_url)
        
        self.assertIsNotNone(file_data)
        self.assertIn('markdown_content', file_data)
        self.assertIn('markdown_updated_at', file_data)
        self.assertIn('markdown_source', file_data)
        self.assertEqual(file_data['markdown_content'], markdown_content)
        self.assertEqual(file_data['markdown_source'], "manual")
    
    def test_update_file_markdown_overwrites(self):
        """Test that updating markdown replaces previous content."""
        # Save initial markdown
        self.storage.update_file_markdown(
            self.test_url, "# First Version", "manual"
        )
        
        # Update with new content
        new_content = "# Second Version\n\nUpdated content."
        self.storage.update_file_markdown(
            self.test_url, new_content, "converted_docling"
        )
        
        # Verify new content replaced old
        markdown_data = self.storage.get_file_markdown(self.test_url)
        self.assertEqual(markdown_data['markdown_content'], new_content)
        self.assertEqual(markdown_data['markdown_source'], "converted_docling")
    
    def test_markdown_source_tracking(self):
        """Test that markdown source is correctly tracked."""
        sources = ["manual", "converted_marker", "converted_docling", "original"]
        
        for source in sources:
            self.storage.update_file_markdown(
                self.test_url, f"# Content from {source}", source
            )
            
            markdown_data = self.storage.get_file_markdown(self.test_url)
            self.assertEqual(markdown_data['markdown_source'], source)


class TestMarkdownConversionRuntime(unittest.TestCase):
    def test_convert_file_to_markdown_passes_runtime_kwargs(self):
        from doc_to_md.registry import ConversionOutput
        from ai_actuarial.web.app import convert_file_to_markdown

        with patch("doc_to_md.registry.convert_path") as mock_convert_path:
            mock_convert_path.return_value = ConversionOutput(
                markdown="# Converted",
                engine="deepseekocr",
                model="deepseek-ai/DeepSeek-OCR",
            )

            result = convert_file_to_markdown(
                "C:/tmp/test.pdf",
                "deepseekocr",
                "application/pdf",
                model="deepseek-ai/DeepSeek-OCR",
                api_key="runtime-key",
                base_url="https://custom.siliconflow.test/v1",
            )

        mock_convert_path.assert_called_once()
        _, kwargs = mock_convert_path.call_args
        self.assertEqual(kwargs["engine"], "deepseekocr")
        self.assertEqual(kwargs["model"], "deepseek-ai/DeepSeek-OCR")
        self.assertEqual(kwargs["api_key"], "runtime-key")
        self.assertEqual(kwargs["base_url"], "https://custom.siliconflow.test/v1")
        self.assertEqual(result["engine"], "deepseekocr")
        self.assertEqual(result["model"], "deepseek-ai/DeepSeek-OCR")


class TestMarkdownAPI(unittest.TestCase):
    """Test REST API endpoints for markdown functionality."""
    
    def setUp(self):
        """Set up test client with temporary database."""
        import yaml
        
        # Create temporary database
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        
        # Create temporary config file
        self.config_fd, self.config_path = tempfile.mkstemp(suffix='.yaml', text=True)
        config_data = {
            'paths': {
                'db': self.db_path,
                'download_dir': 'data/files',
                'updates_dir': 'data/updates'
            },
            'defaults': {
                'user_agent': 'TestAgent/1.0',
                'max_pages': 10,
                'max_depth': 2,
                'file_exts': ['.pdf'],
                'keywords': [],
                'exclude_keywords': []
            }
        }
        
        with os.fdopen(self.config_fd, 'w') as f:
            yaml.dump(config_data, f)
        
        # Set environment variable for config path
        os.environ['CONFIG_PATH'] = self.config_path
        # Bootstrap an admin token for protected write endpoints (markdown.write).
        self._orig_bootstrap = os.environ.get("BOOTSTRAP_ADMIN_TOKEN")
        self._orig_flask_secret = os.environ.get("FLASK_SECRET_KEY")
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = "test-bootstrap-admin-token"
        os.environ["FLASK_SECRET_KEY"] = "test-flask-secret-key"
        
        # Import and create app
        from ai_actuarial.web.app import create_app
        self.app = create_app()
        self.client = self.app.test_client()
        
        # Insert a test file
        from ai_actuarial.storage import Storage
        storage = Storage(self.db_path)
        self.test_url = "file:///test/document.pdf"
        storage._conn.execute(
            """
            INSERT INTO files (url, sha256, title, source_site, content_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.test_url, "test123", "Test Document", "Test Site", "application/pdf")
        )
        storage._conn.commit()
        storage.close()
    
    def tearDown(self):
        """Clean up temporary files."""
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.config_path)
        if 'CONFIG_PATH' in os.environ:
            del os.environ['CONFIG_PATH']
        if self._orig_bootstrap is None:
            os.environ.pop("BOOTSTRAP_ADMIN_TOKEN", None)
        else:
            os.environ["BOOTSTRAP_ADMIN_TOKEN"] = self._orig_bootstrap
        if self._orig_flask_secret is None:
            os.environ.pop("FLASK_SECRET_KEY", None)
        else:
            os.environ["FLASK_SECRET_KEY"] = self._orig_flask_secret
    
    def test_get_markdown_empty(self):
        """Test GET markdown when no content exists."""
        from urllib.parse import quote
        encoded_url = quote(self.test_url, safe='')
        
        response = self.client.get(f'/api/files/{encoded_url}/markdown')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsNone(data['markdown'])
    
    def test_get_markdown_with_content(self):
        """Test GET markdown when content exists."""
        from urllib.parse import quote
        from ai_actuarial.storage import Storage
        
        # First save some markdown
        storage = Storage(self.db_path)
        markdown_content = "# Test Document\n\nThis is a test."
        storage.update_file_markdown(self.test_url, markdown_content, "manual")
        storage.close()
        
        # Then retrieve via API
        encoded_url = quote(self.test_url, safe='')
        response = self.client.get(f'/api/files/{encoded_url}/markdown')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsNotNone(data['markdown'])
        self.assertEqual(data['markdown']['markdown_content'], markdown_content)
        self.assertEqual(data['markdown']['markdown_source'], "manual")
    
    def test_post_markdown_create(self):
        """Test POST to create new markdown content."""
        from urllib.parse import quote
        
        markdown_content = "# New Document\n\n## Section 1"
        encoded_url = quote(self.test_url, safe='')
        
        response = self.client.post(
            f'/api/files/{encoded_url}/markdown',
            json={
                'markdown_content': markdown_content,
                'markdown_source': 'manual'
            },
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['markdown']['markdown_content'], markdown_content)
    
    def test_post_markdown_update(self):
        """Test POST to update existing markdown content."""
        from urllib.parse import quote
        from ai_actuarial.storage import Storage
        
        # First save some markdown
        storage = Storage(self.db_path)
        storage.update_file_markdown(self.test_url, "# Old Content", "manual")
        storage.close()
        
        # Then update via API
        new_content = "# Updated Content\n\nNew information."
        encoded_url = quote(self.test_url, safe='')
        
        response = self.client.post(
            f'/api/files/{encoded_url}/markdown',
            json={
                'markdown_content': new_content,
                'markdown_source': 'manual'
            },
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['markdown']['markdown_content'], new_content)
    
    def test_post_markdown_roundtrip(self):
        """Test POST then GET to verify roundtrip."""
        from urllib.parse import quote
        
        markdown_content = "# Roundtrip Test\n\n- Item 1\n- Item 2"
        encoded_url = quote(self.test_url, safe='')
        
        # POST
        post_response = self.client.post(
            f'/api/files/{encoded_url}/markdown',
            json={
                'markdown_content': markdown_content,
                'markdown_source': 'converted_marker'
            },
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(post_response.status_code, 200)
        
        # GET
        get_response = self.client.get(f'/api/files/{encoded_url}/markdown')
        self.assertEqual(get_response.status_code, 200)
        
        data = get_response.get_json()
        self.assertEqual(data['markdown']['markdown_content'], markdown_content)
        self.assertEqual(data['markdown']['markdown_source'], 'converted_marker')
    
    def test_get_markdown_for_unknown_file(self):
        """Test GET returns null markdown for non-existent file (not 404)."""
        from urllib.parse import quote
        
        unknown_url = "file:///nonexistent/file.pdf"
        encoded_url = quote(unknown_url, safe='')
        
        response = self.client.get(f'/api/files/{encoded_url}/markdown')
        
        # API returns 200 with success=true and markdown=None for missing files
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        # Should return None for non-existent file (not an error, just no content)
        self.assertIsNone(data['markdown'])
    
    def test_post_markdown_400_on_missing_content(self):
        """Test POST returns 400 when markdown_content is missing."""
        from urllib.parse import quote
        
        encoded_url = quote(self.test_url, safe='')
        
        response = self.client.post(
            f'/api/files/{encoded_url}/markdown',
            json={
                'markdown_source': 'manual'
                # Missing markdown_content
            },
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn('error', data)
    
    def test_url_encoding_with_percent_sequences(self):
        """Test handling of URLs with percent-encoded characters."""
        from urllib.parse import quote
        from ai_actuarial.storage import Storage
        
        # Create a file with a URL containing special characters
        # Flask decodes once, so the URL in DB should match what Flask receives
        special_url = "file:///test/document with spaces.pdf"
        storage = Storage(self.db_path)
        storage._conn.execute(
            """
            INSERT INTO files (url, sha256, title, source_site, content_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (special_url, "test456", "Special Document", "Test Site", "application/pdf")
        )
        storage._conn.commit()
        storage.close()
        
        # Update markdown - encode the URL for the HTTP request
        markdown_content = "# Document with spaces in filename"
        # quote() will encode spaces as %20 for the HTTP request
        # Flask will decode to "document with spaces" matching DB
        encoded_url = quote(special_url, safe='')
        
        post_response = self.client.post(
            f'/api/files/{encoded_url}/markdown',
            json={
                'markdown_content': markdown_content,
                'markdown_source': 'manual'
            },
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        
        self.assertEqual(post_response.status_code, 200)
        
        # Retrieve markdown
        get_response = self.client.get(f'/api/files/{encoded_url}/markdown')
        self.assertEqual(get_response.status_code, 200)
        
        data = get_response.get_json()
        self.assertEqual(data['markdown']['markdown_content'], markdown_content)


if __name__ == '__main__':
    unittest.main()

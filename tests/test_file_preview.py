"""
Test file preview functionality
"""
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

import yaml

# Constants
MAX_CLEANUP_RETRIES = 10

# Mock schedule module if not available
if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.storage import Storage
from ai_actuarial.web.app import FLASK_AVAILABLE, create_app


class TestFilePreview(unittest.TestCase):
    """Test file preview API and routes."""

    def setUp(self):
        """Set up test fixtures."""
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed in this environment")
            
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_path = os.path.join(self.temp_dir, "categories.yaml")
        self.admin_token = "test-preview-admin-token"
        
        # Create config files
        config_data = {
            "paths": {
                "db": self.db_path,
                "download_dir": os.path.join(self.temp_dir, "files"),
                "updates_dir": os.path.join(self.temp_dir, "updates"),
                "last_run_new": os.path.join(self.temp_dir, "last_run_new.json"),
            },
            "defaults": {
                "user_agent": "test-agent/1.0",
                "max_pages": 10,
                "max_depth": 1,
                "file_exts": [".pdf", ".docx"],
                "keywords": ["actuarial"],
            },
            "sites": [],
        }
        categories_data = {"categories": {"Test": ["test"]}}
        
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, sort_keys=False, allow_unicode=True)
        with open(self.categories_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(categories_data, f, sort_keys=False, allow_unicode=True)
        
        # Set environment
        self.original_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_path
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = self.admin_token
        os.environ["FLASK_SECRET_KEY"] = "test-preview-secret-key"
        os.environ["REQUIRE_AUTH"] = "false"
        os.environ["RAG_DATA_DIR"] = os.path.join(self.temp_dir, "rag_data")
        
        # Create test app
        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()
        self.auth_header = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Initialize storage and add test data
        self.storage = Storage(self.db_path)
        
        # Add a test file
        self.test_file_url = "test://file1.pdf"
        self.storage.insert_file(
            url=self.test_file_url,
            sha256="abc123",
            title="Test Document",
            source_site="test",
            source_page_url="test://page",
            original_filename="test.pdf",
            local_path="/tmp/test.pdf",
            bytes=1024,
            content_type="application/pdf"
        )
        
        # Add markdown content
        self.storage.update_file_markdown(
            self.test_file_url,
            "# Test Document\n\nThis is a test markdown content.",
            "test"
        )

    def tearDown(self):
        """Clean up test fixtures."""
        if hasattr(self, 'storage'):
            self.storage.close()
        
        # Restore environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up temp directory
        if os.path.exists(self.temp_dir):
            for _ in range(MAX_CLEANUP_RETRIES):
                try:
                    shutil.rmtree(self.temp_dir)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def test_preview_route_exists(self):
        """Test that the preview route is accessible."""
        response = self.client.get("/file_preview", headers=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"File Preview", response.data)

    def test_preview_api_endpoint(self):
        """Test the preview API endpoint."""
        response = self.client.get(
            f"/api/rag/files/preview?file_url={self.test_file_url}",
            headers=self.auth_header
        )
        
        # RAG might not be available in test environment (missing dependencies)
        if response.status_code == 503:
            self.skipTest("RAG functionality not available (missing dependencies)")
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("file_info", data["data"])
        self.assertIn("markdown", data["data"])
        self.assertIn("chunks", data["data"])
        
        # Verify file info
        file_info = data["data"]["file_info"]
        self.assertEqual(file_info["url"], self.test_file_url)
        self.assertEqual(file_info["title"], "Test Document")
        
        # Verify markdown
        markdown = data["data"]["markdown"]
        self.assertIn("Test Document", markdown["content"])

    def test_preview_api_missing_file(self):
        """Test preview API with non-existent file."""
        response = self.client.get(
            "/api/rag/files/preview?file_url=nonexistent://file.pdf",
            headers=self.auth_header
        )
        
        # RAG might not be available in test environment
        if response.status_code == 503:
            self.skipTest("RAG functionality not available (missing dependencies)")
        
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])

    def test_preview_api_no_file_url(self):
        """Test preview API without file_url parameter."""
        response = self.client.get(
            "/api/rag/files/preview",
            headers=self.auth_header
        )
        
        # RAG might not be available in test environment
        if response.status_code == 503:
            self.skipTest("RAG functionality not available (missing dependencies)")
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("required", data["error"].lower())


if __name__ == "__main__":
    unittest.main()

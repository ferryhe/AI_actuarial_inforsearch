#!/usr/bin/env python3
"""Integration-style tests for RAG web routes and task wiring."""

import os
import shutil
import sys
import tempfile
import time
import types
import unittest

import yaml

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.web.app import FLASK_AVAILABLE, create_app


class TestRagWebIntegration(unittest.TestCase):
    def setUp(self):
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed in this environment")

        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "index.db")
        self.config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_path = os.path.join(self.temp_dir, "categories.yaml")
        self.admin_token = "test-rag-admin-token"

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
        categories_data = {"categories": {"Pricing": ["premium"], "Risk": ["capital"]}}

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, sort_keys=False, allow_unicode=True)
        with open(self.categories_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(categories_data, f, sort_keys=False, allow_unicode=True)

        self.original_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_path
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = self.admin_token
        os.environ["FLASK_SECRET_KEY"] = "test-rag-secret-key"
        os.environ["REQUIRE_AUTH"] = "false"

        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()
        self.auth_header = {"Authorization": f"Bearer {self.admin_token}"}

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        if os.path.exists(self.temp_dir):
            for _ in range(10):
                try:
                    shutil.rmtree(self.temp_dir)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def test_rag_pages_available(self):
        list_resp = self.client.get("/rag", headers=self.auth_header)
        self.assertEqual(list_resp.status_code, 200)
        self.assertIn(b"Knowledge Bases", list_resp.data)

        detail_resp = self.client.get("/rag/test_kb", headers=self.auth_header)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertIn(b"Knowledge Base", detail_resp.data)

    def test_index_endpoint_creates_background_task(self):
        create_resp = self.client.post(
            "/api/rag/knowledge-bases",
            headers=self.auth_header,
            json={
                "kb_id": "test_kb",
                "name": "Test KB",
                "kb_mode": "manual",
            },
        )
        self.assertEqual(create_resp.status_code, 201)

        index_resp = self.client.post(
            "/api/rag/knowledge-bases/test_kb/index",
            headers=self.auth_header,
            json={"file_urls": ["https://example.com/file-1.pdf"]},
        )
        self.assertEqual(index_resp.status_code, 202)
        task_payload = index_resp.get_json()
        self.assertTrue(task_payload.get("success"))
        self.assertTrue(task_payload["data"].get("job_id"))

        # Wait briefly for async thread to move task into active/history list.
        found = False
        for _ in range(15):
            tasks_resp = self.client.get(
                "/api/rag/knowledge-bases/test_kb/tasks",
                headers=self.auth_header,
            )
            self.assertEqual(tasks_resp.status_code, 200)
            data = tasks_resp.get_json().get("data", {})
            if data.get("active") or data.get("history"):
                found = True
                break
            time.sleep(0.2)

        self.assertTrue(found, "Expected rag_indexing task to appear in active/history")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for public chat access when REQUIRE_AUTH=false."""

import json
import os
import shutil
import sys
import tempfile
import types
import unittest

import yaml

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.web.app import FLASK_AVAILABLE, create_app


class TestPublicChatAccess(unittest.TestCase):
    def setUp(self):
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed in this environment")

        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "index.db")
        self.sites_config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_config_path = os.path.join(self.temp_dir, "categories.yaml")

        sites_config = {
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
                "file_exts": [".pdf"],
                "keywords": ["actuarial"],
            },
            "sites": [],
        }
        categories_config = {"categories": {"General": ["insurance"]}}

        with open(self.sites_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(sites_config, f)
        with open(self.categories_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(categories_config, f)

        self.original_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.sites_config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_config_path
        os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
        os.environ["REQUIRE_AUTH"] = "false"
        os.environ["OPENAI_API_KEY"] = "test-openai-key"

        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_chat_page_open_without_auth(self):
        response = self.client.get("/chat")
        # Public chat should not require auth redirect or auth errors.
        self.assertNotIn(response.status_code, (302, 401, 403))

    def test_public_chat_query_without_auth(self):
        # Missing message should return validation error, not auth error.
        response = self.client.post("/api/chat/query", json={})
        self.assertEqual(response.status_code, 400)

        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("Message is required", data["error"])

    def test_public_guest_sessions_are_isolated(self):
        client_a = self.app.test_client()
        client_b = self.app.test_client()

        create_a = client_a.post(
            "/api/chat/conversations",
            json={"kb_id": "kb-public", "mode": "expert"},
        )
        create_b = client_b.post(
            "/api/chat/conversations",
            json={"kb_id": "kb-public", "mode": "expert"},
        )
        self.assertEqual(create_a.status_code, 201)
        self.assertEqual(create_b.status_code, 201)

        list_a = client_a.get("/api/chat/conversations")
        list_b = client_b.get("/api/chat/conversations")
        self.assertEqual(list_a.status_code, 200)
        self.assertEqual(list_b.status_code, 200)

        data_a = list_a.get_json()
        data_b = list_b.get_json()
        conv_ids_a = {c["conversation_id"] for c in data_a["data"]["conversations"]}
        conv_ids_b = {c["conversation_id"] for c in data_b["data"]["conversations"]}

        self.assertTrue(conv_ids_a)
        self.assertTrue(conv_ids_b)
        self.assertTrue(conv_ids_a.isdisjoint(conv_ids_b))


if __name__ == "__main__":
    unittest.main()

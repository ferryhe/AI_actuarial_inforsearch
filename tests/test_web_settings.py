#!/usr/bin/env python3
"""Tests for backend settings and categories config APIs."""

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


class TestWebSettingsApi(unittest.TestCase):
    def setUp(self):
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed in this environment")

        self.temp_dir = tempfile.mkdtemp()
        self.sites_config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_config_path = os.path.join(self.temp_dir, "categories.yaml")
        self.db_path = os.path.join(self.temp_dir, "index.db")

        sites_config = {
            "defaults": {
                "user_agent": "test-agent/1.0",
                "max_pages": 100,
                "max_depth": 2,
                "delay_seconds": 0.5,
                "file_exts": [".pdf", ".docx"],
                "keywords": ["ai", "ml"],
            },
            "paths": {
                "db": self.db_path,
                "download_dir": os.path.join(self.temp_dir, "files"),
                "updates_dir": os.path.join(self.temp_dir, "updates"),
                "last_run_new": os.path.join(self.temp_dir, "last_run_new.json"),
            },
            "search": {
                "enabled": True,
                "max_results": 5,
                "delay_seconds": 0.5,
                "languages": ["en", "zh"],
                "country": "us",
                "exclude_keywords": [],
                "queries": ["actuary ai report filetype:pdf"],
            },
            "sites": [],
        }
        categories_config = {
            "categories": {
                "AI": ["artificial intelligence", "machine learning"],
                "Risk": ["capital", "stress"],
            },
            "ai_filter_keywords": ["artificial intelligence", "llm"],
            "ai_keywords": ["machine learning", "deep learning"],
        }

        with open(self.sites_config_path, "w", encoding="utf-8") as f:
            yaml.dump(sites_config, f, sort_keys=False, allow_unicode=True)
        with open(self.categories_config_path, "w", encoding="utf-8") as f:
            yaml.dump(categories_config, f, sort_keys=False, allow_unicode=True)

        self.original_config_path = os.environ.get("CONFIG_PATH")
        self.original_categories_path = os.environ.get("CATEGORIES_CONFIG_PATH")
        self.original_bootstrap_token = os.environ.get("BOOTSTRAP_ADMIN_TOKEN")
        self.original_flask_secret_key = os.environ.get("FLASK_SECRET_KEY")
        os.environ["CONFIG_PATH"] = self.sites_config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_config_path
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = "test-bootstrap-admin-token"
        os.environ["FLASK_SECRET_KEY"] = "test-flask-secret-key"

        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()

    def tearDown(self):
        if self.original_config_path is None:
            os.environ.pop("CONFIG_PATH", None)
        else:
            os.environ["CONFIG_PATH"] = self.original_config_path

        if self.original_categories_path is None:
            os.environ.pop("CATEGORIES_CONFIG_PATH", None)
        else:
            os.environ["CATEGORIES_CONFIG_PATH"] = self.original_categories_path
        if self.original_bootstrap_token is None:
            os.environ.pop("BOOTSTRAP_ADMIN_TOKEN", None)
        else:
            os.environ["BOOTSTRAP_ADMIN_TOKEN"] = self.original_bootstrap_token
        if self.original_flask_secret_key is None:
            os.environ.pop("FLASK_SECRET_KEY", None)
        else:
            os.environ["FLASK_SECRET_KEY"] = self.original_flask_secret_key

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_settings_page_available(self):
        # REQUIRE_AUTH defaults to false, but settings should still require a token.
        guest = self.client.get("/settings", follow_redirects=False)
        self.assertEqual(guest.status_code, 302)
        admin = self.client.get(
            "/settings",
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(admin.status_code, 200)
        self.assertIn(b"Backend Settings", admin.data)

    def test_categories_config_roundtrip(self):
        # Guest cannot read config APIs.
        guest = self.client.get("/api/config/categories")
        self.assertEqual(guest.status_code, 401)

        resp = self.client.get(
            "/api/config/categories",
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("AI", data["categories"])

        payload = {
            "categories": {
                "AI": ["ai", "llm"],
                "Pricing": ["premium", "rate"],
            },
            "ai_filter_keywords": ["ai", "genai"],
            "ai_keywords": ["llm", "transformer"],
        }
        save_resp = self.client.post(
            "/api/config/categories",
            json=payload,
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(save_resp.status_code, 200)
        self.assertTrue(save_resp.get_json().get("success"))

        with open(self.categories_config_path, "r", encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        self.assertEqual(saved["categories"]["AI"], ["ai", "llm"])
        self.assertIn("Pricing", saved["categories"])
        self.assertEqual(saved["ai_filter_keywords"], ["ai", "genai"])
        self.assertEqual(saved["ai_keywords"], ["llm", "transformer"])

        list_resp = self.client.get("/api/categories")
        self.assertEqual(list_resp.status_code, 200)
        self.assertIn("Pricing", list_resp.get_json()["categories"])

    def test_backend_settings_roundtrip(self):
        guest = self.client.get("/api/config/backend-settings")
        self.assertEqual(guest.status_code, 401)

        resp = self.client.get(
            "/api/config/backend-settings",
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["defaults"]["max_pages"], 100)

        payload = {
            "defaults": {
                "user_agent": "changed-agent/2.0",
                "max_pages": 240,
                "max_depth": 3,
                "delay_seconds": 1.2,
                "file_exts": [".pdf", ".txt"],
                "keywords": ["actuary", "ai"],
                "exclude_keywords": ["newsletter"],
                "exclude_prefixes": ["book_"],
                "schedule_interval": "daily at 01:00",
            },
            "paths": {
                "db": self.db_path,
                "download_dir": os.path.join(self.temp_dir, "new_files"),
                "updates_dir": os.path.join(self.temp_dir, "new_updates"),
                "last_run_new": os.path.join(self.temp_dir, "new_last_run.json"),
            },
            "search": {
                "enabled": False,
                "max_results": 20,
                "delay_seconds": 0.8,
                "country": "ca",
                "languages": ["en", "fr"],
                "exclude_keywords": ["brochure"],
                "queries": ["actuary machine learning filetype:pdf"],
            },
        }
        save_resp = self.client.post(
            "/api/config/backend-settings",
            json=payload,
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(save_resp.status_code, 200)
        self.assertTrue(save_resp.get_json().get("success"))

        with open(self.sites_config_path, "r", encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        self.assertEqual(saved["defaults"]["max_pages"], 240)
        # user_agent is locked by API for safety.
        self.assertEqual(saved["defaults"]["user_agent"], "test-agent/1.0")
        self.assertEqual(saved["defaults"]["file_exts"], [".pdf", ".txt"])
        # db path is locked by API for safety.
        self.assertEqual(saved["paths"]["db"], self.db_path)
        self.assertEqual(saved["paths"]["download_dir"], payload["paths"]["download_dir"])
        self.assertFalse(saved["search"]["enabled"])
        self.assertEqual(saved["search"]["languages"], ["en", "fr"])

        verify = self.client.get(
            "/api/config/backend-settings",
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        verify_data = verify.get_json()
        self.assertEqual(verify_data["defaults"]["user_agent"], "test-agent/1.0")
        self.assertEqual(verify_data["search"]["country"], "ca")

    def test_search_defaults_endpoint(self):
        # This endpoint is tasks-related and should require a token.
        guest = self.client.get("/api/config/search-defaults")
        self.assertEqual(guest.status_code, 401)

        resp = self.client.get(
            "/api/config/search-defaults",
            headers={"Authorization": "Bearer test-bootstrap-admin-token"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["max_results"], 5)
        self.assertEqual(data["country"], "us")


if __name__ == "__main__":
    unittest.main()

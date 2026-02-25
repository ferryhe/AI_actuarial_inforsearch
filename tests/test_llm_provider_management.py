#!/usr/bin/env python3
"""Tests for LLM provider management API endpoints and storage methods."""

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
from ai_actuarial.storage import Storage


class TestStorageLlmProviders(unittest.TestCase):
    """Tests for Storage CRUD methods for LLM providers."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.storage.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_upsert_and_get_provider(self):
        """Test inserting a provider and retrieving it."""
        self.storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted="enc_key_openai",
            base_url="https://api.openai.com/v1",
            notes="test",
        )
        row = self.storage.get_llm_provider("openai")
        self.assertIsNotNone(row)
        self.assertEqual(row["provider"], "openai")
        self.assertEqual(row["api_key_encrypted"], "enc_key_openai")
        self.assertEqual(row["api_base_url"], "https://api.openai.com/v1")
        self.assertEqual(row["notes"], "test")
        self.assertEqual(row["status"], "active")

    def test_upsert_updates_existing(self):
        """Test that upsert replaces the existing API key."""
        self.storage.upsert_llm_provider("mistral", "old_key")
        self.storage.upsert_llm_provider("mistral", "new_key", base_url="https://custom.api")
        row = self.storage.get_llm_provider("mistral")
        self.assertEqual(row["api_key_encrypted"], "new_key")
        self.assertEqual(row["api_base_url"], "https://custom.api")

    def test_get_nonexistent_provider_returns_none(self):
        """Test that getting a missing provider returns None."""
        self.assertIsNone(self.storage.get_llm_provider("nonexistent"))

    def test_list_providers(self):
        """Test listing all providers."""
        self.storage.upsert_llm_provider("openai", "key1")
        self.storage.upsert_llm_provider("mistral", "key2")
        self.storage.upsert_llm_provider("siliconflow", "key3")

        providers = self.storage.list_llm_providers()
        self.assertEqual(len(providers), 3)
        # Should be sorted by provider name
        names = [p["provider"] for p in providers]
        self.assertEqual(names, sorted(names))

    def test_list_empty_providers(self):
        """Test that listing with no providers returns empty list."""
        providers = self.storage.list_llm_providers()
        self.assertEqual(providers, [])

    def test_delete_provider(self):
        """Test deleting a provider."""
        self.storage.upsert_llm_provider("openai", "key1")
        deleted = self.storage.delete_llm_provider("openai")
        self.assertTrue(deleted)
        self.assertIsNone(self.storage.get_llm_provider("openai"))

    def test_delete_nonexistent_returns_false(self):
        """Test that deleting a missing provider returns False."""
        result = self.storage.delete_llm_provider("nonexistent")
        self.assertFalse(result)

    def test_category_isolation(self):
        """Test that category='llm' is the default and isolates records."""
        self.storage.upsert_llm_provider("openai", "key1", category="llm")
        self.storage.upsert_llm_provider("openai", "key2", category="search")

        llm = self.storage.get_llm_provider("openai", category="llm")
        search = self.storage.get_llm_provider("openai", category="search")
        self.assertEqual(llm["api_key_encrypted"], "key1")
        self.assertEqual(search["api_key_encrypted"], "key2")

        llm_list = self.storage.list_llm_providers(category="llm")
        self.assertEqual(len(llm_list), 1)
        search_list = self.storage.list_llm_providers(category="search")
        self.assertEqual(len(search_list), 1)


class TestLlmProviderApiEndpoints(unittest.TestCase):
    """Integration tests for the LLM provider management HTTP endpoints."""

    def setUp(self):
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed in this environment")

        self.temp_dir = tempfile.mkdtemp()
        self.sites_config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_config_path = os.path.join(self.temp_dir, "categories.yaml")
        self.db_path = os.path.join(self.temp_dir, "index.db")

        sites_config = {
            "defaults": {"user_agent": "test/1.0", "max_pages": 10, "max_depth": 2,
                         "delay_seconds": 0, "file_exts": [], "keywords": []},
            "paths": {
                "db": self.db_path,
                "download_dir": os.path.join(self.temp_dir, "files"),
                "updates_dir": os.path.join(self.temp_dir, "updates"),
                "last_run_new": os.path.join(self.temp_dir, "last_run.json"),
            },
            "search": {"enabled": False, "max_results": 5, "delay_seconds": 0,
                       "languages": [], "country": "us", "exclude_keywords": [], "queries": []},
            "sites": [],
        }
        categories_config = {"categories": {}, "ai_filter_keywords": [], "ai_keywords": []}

        with open(self.sites_config_path, "w") as f:
            yaml.dump(sites_config, f)
        with open(self.categories_config_path, "w") as f:
            yaml.dump(categories_config, f)

        self._orig_config = os.environ.get("CONFIG_PATH")
        self._orig_categories = os.environ.get("CATEGORIES_CONFIG_PATH")
        self._orig_bootstrap = os.environ.get("BOOTSTRAP_ADMIN_TOKEN")
        self._orig_secret = os.environ.get("FLASK_SECRET_KEY")
        # Clear any provider API key env vars that would pollute test isolation
        self._orig_provider_keys = {}
        for var in ("OPENAI_API_KEY", "MISTRAL_API_KEY", "SILICONFLOW_API_KEY",
                    "ANTHROPIC_API_KEY", "OPENAI_BASE_URL", "MISTRAL_BASE_URL",
                    "SILICONFLOW_BASE_URL"):
            self._orig_provider_keys[var] = os.environ.pop(var, None)

        os.environ["CONFIG_PATH"] = self.sites_config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_config_path
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = "test-admin-token"
        os.environ["FLASK_SECRET_KEY"] = "test-secret"

        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        self.auth_header = {"Authorization": "Bearer test-admin-token"}

    def tearDown(self):
        for k, v in [
            ("CONFIG_PATH", self._orig_config),
            ("CATEGORIES_CONFIG_PATH", self._orig_categories),
            ("BOOTSTRAP_ADMIN_TOKEN", self._orig_bootstrap),
            ("FLASK_SECRET_KEY", self._orig_secret),
        ]:
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # Restore provider env vars
        for var, val in self._orig_provider_keys.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_providers_empty(self):
        """GET /api/config/llm-providers returns empty list initially."""
        resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("providers", data)
        self.assertEqual(data["providers"], [])
        self.assertIn("known", data)
        self.assertIn("openai", data["known"])

    def test_list_providers_requires_auth(self):
        """GET /api/config/llm-providers requires authentication."""
        resp = self.client.get("/api/config/llm-providers")
        self.assertEqual(resp.status_code, 401)

    def test_add_provider(self):
        """POST /api/config/llm-providers adds a provider."""
        resp = self.client.post(
            "/api/config/llm-providers",
            json={"provider": "openai", "api_key": "sk-test-1234567890"},
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # Verify it appears in the list with source='db'
        list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
        providers = list_resp.get_json()["providers"]
        db_providers = [p for p in providers if p["source"] == "db"]
        self.assertEqual(len(db_providers), 1)
        self.assertEqual(db_providers[0]["provider"], "openai")
        self.assertEqual(db_providers[0]["api_key_masked"], "****")  # Key is masked
        # Actual plaintext key must NOT be in the response
        self.assertNotIn("sk-test-1234567890", str(providers))

    def test_add_provider_with_base_url(self):
        """POST /api/config/llm-providers supports custom base URL."""
        resp = self.client.post(
            "/api/config/llm-providers",
            json={"provider": "openai", "api_key": "sk-test-key", "api_base_url": "https://custom.endpoint/v1"},
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200)

        list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
        providers = list_resp.get_json()["providers"]
        db_providers = [p for p in providers if p["source"] == "db"]
        self.assertEqual(db_providers[0]["api_base_url"], "https://custom.endpoint/v1")

    def test_add_provider_sets_env_var(self):
        """POST /api/config/llm-providers sets the env var for immediate use."""
        import os
        self.assertIsNone(os.environ.get("OPENAI_API_KEY"))
        self.client.post(
            "/api/config/llm-providers",
            json={"provider": "openai", "api_key": "sk-env-test"},
            headers=self.auth_header,
        )
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-env-test")

    def test_add_provider_missing_fields(self):
        """POST /api/config/llm-providers returns 400 if required fields missing."""
        # Missing api_key
        resp = self.client.post(
            "/api/config/llm-providers",
            json={"provider": "openai"},
            headers=self.auth_header,
        )
        self.assertIn(resp.status_code, [400, 500])

        # Missing provider
        resp2 = self.client.post(
            "/api/config/llm-providers",
            json={"api_key": "sk-test"},
            headers=self.auth_header,
        )
        self.assertIn(resp2.status_code, [400, 500])

    def test_update_existing_provider(self):
        """POST /api/config/llm-providers updates an existing provider (upsert)."""
        self.client.post(
            "/api/config/llm-providers",
            json={"provider": "mistral", "api_key": "old-key"},
            headers=self.auth_header,
        )
        self.client.post(
            "/api/config/llm-providers",
            json={"provider": "mistral", "api_key": "new-key"},
            headers=self.auth_header,
        )
        # Should still be one DB entry (upsert, not duplicate)
        list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
        providers = list_resp.get_json()["providers"]
        db_providers = [p for p in providers if p["source"] == "db"]
        self.assertEqual(len(db_providers), 1)

    def test_delete_provider(self):
        """DELETE /api/config/llm-providers/<provider> removes the DB entry and clears env var."""
        self.client.post(
            "/api/config/llm-providers",
            json={"provider": "siliconflow", "api_key": "sf-key"},
            headers=self.auth_header,
        )
        # Confirm env var was set
        self.assertEqual(os.environ.get("SILICONFLOW_API_KEY"), "sf-key")

        del_resp = self.client.delete(
            "/api/config/llm-providers/siliconflow",
            headers=self.auth_header,
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.get_json()["success"])

        # After deletion: DB entry gone and env var cleared
        list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
        providers = list_resp.get_json()["providers"]
        db_providers = [p for p in providers if p["source"] == "db"]
        self.assertEqual(len(db_providers), 0)
        self.assertIsNone(os.environ.get("SILICONFLOW_API_KEY"))

    def test_delete_nonexistent_provider_returns_404(self):
        """DELETE /api/config/llm-providers/<provider> returns 404 if not found."""
        resp = self.client.delete(
            "/api/config/llm-providers/nonexistent",
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 404)

    def test_multiple_providers(self):
        """Multiple providers can be added and listed."""
        for provider, key in [("openai", "key1"), ("mistral", "key2"), ("anthropic", "key3")]:
            self.client.post(
                "/api/config/llm-providers",
                json={"provider": provider, "api_key": key},
                headers=self.auth_header,
            )

        list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
        providers = list_resp.get_json()["providers"]
        db_providers = [p for p in providers if p["source"] == "db"]
        self.assertEqual(len(db_providers), 3)
        provider_names = {p["provider"] for p in db_providers}
        self.assertEqual(provider_names, {"openai", "mistral", "anthropic"})

    def test_env_var_backward_compat(self):
        """Providers configured via env vars appear in the list with source='env'."""
        import os
        os.environ["OPENAI_API_KEY"] = "sk-from-env"
        try:
            list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
            providers = list_resp.get_json()["providers"]
            env_providers = [p for p in providers if p["source"] == "env"]
            self.assertEqual(len(env_providers), 1)
            self.assertEqual(env_providers[0]["provider"], "openai")
            self.assertNotIn("sk-from-env", str(providers))  # Key still masked
        finally:
            os.environ.pop("OPENAI_API_KEY", None)

    def test_db_overrides_env_var(self):
        """A DB-stored provider takes priority over the same provider's env var."""
        import os
        os.environ["OPENAI_API_KEY"] = "sk-from-env"
        try:
            # Also save to DB
            self.client.post(
                "/api/config/llm-providers",
                json={"provider": "openai", "api_key": "sk-from-db"},
                headers=self.auth_header,
            )
            list_resp = self.client.get("/api/config/llm-providers", headers=self.auth_header)
            providers = list_resp.get_json()["providers"]
            # Only one openai entry, from DB
            openai_entries = [p for p in providers if p["provider"] == "openai"]
            self.assertEqual(len(openai_entries), 1)
            self.assertEqual(openai_entries[0]["source"], "db")
        finally:
            os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    unittest.main()

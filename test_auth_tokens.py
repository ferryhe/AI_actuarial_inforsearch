#!/usr/bin/env python3
"""Tests for token auth + group permissions when REQUIRE_AUTH=true."""

import os
import tempfile
import unittest
import sys
import types

import yaml

from ai_actuarial.storage import Storage

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.web.app import create_app


def _hash_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TestTokenAuth(unittest.TestCase):
    def setUp(self):
        # Temp db + config
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.cfg_fd, self.cfg_path = tempfile.mkstemp(suffix=".yaml", text=True)

        cfg = {
            "paths": {"db": self.db_path, "download_dir": "data/files", "updates_dir": "data/updates"},
            "defaults": {"user_agent": "TestAgent/1.0", "max_pages": 10, "max_depth": 1, "file_exts": [".pdf"]},
            "sites": [],
        }
        with os.fdopen(self.cfg_fd, "w") as f:
            yaml.dump(cfg, f)

        # Create tokens
        self.reader_token = "reader_" + os.urandom(16).hex()
        self.operator_token = "operator_" + os.urandom(16).hex()
        self.admin_token = "admin_" + os.urandom(16).hex()

        storage = Storage(self.db_path)
        storage.upsert_auth_token_by_hash(
            subject="reader",
            group_name="reader",
            token_hash=_hash_token(self.reader_token),
            is_active=True,
        )
        storage.upsert_auth_token_by_hash(
            subject="operator",
            group_name="operator",
            token_hash=_hash_token(self.operator_token),
            is_active=True,
        )
        storage.upsert_auth_token_by_hash(
            subject="admin",
            group_name="admin",
            token_hash=_hash_token(self.admin_token),
            is_active=True,
        )
        storage.close()

        # Env for app
        self._orig_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.cfg_path
        os.environ["REQUIRE_AUTH"] = "true"
        os.environ["FLASK_SECRET_KEY"] = "test-secret"
        os.environ["ENABLE_FILE_DELETION"] = "true"

        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.cfg_path)
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_login_page_public(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)

    def test_api_requires_auth(self):
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 401)

    def test_bearer_token_reader_can_read_stats(self):
        resp = self.client.get("/api/stats", headers={"Authorization": f"Bearer {self.reader_token}"})
        self.assertEqual(resp.status_code, 200)

    def test_reader_forbidden_on_admin_config(self):
        resp = self.client.get(
            "/api/config/categories",
            headers={"Authorization": f"Bearer {self.reader_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_operator_forbidden_on_admin_config(self):
        resp = self.client.get(
            "/api/config/categories",
            headers={"Authorization": f"Bearer {self.operator_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_operator_can_edit_scheduled_sites(self):
        # Add site
        add = self.client.post(
            "/api/config/sites/add",
            json={"name": "TestSite", "url": "https://example.com"},
            headers={"Authorization": f"Bearer {self.operator_token}"},
        )
        self.assertEqual(add.status_code, 200)
        self.assertTrue(add.get_json().get("success"))

        # Update site
        update = self.client.post(
            "/api/config/sites/update",
            json={"original_name": "TestSite", "name": "TestSite2", "url": "https://example.com/x"},
            headers={"Authorization": f"Bearer {self.operator_token}"},
        )
        self.assertEqual(update.status_code, 200)
        self.assertTrue(update.get_json().get("success"))

        # Delete site
        delete = self.client.post(
            "/api/config/sites/delete",
            json={"name": "TestSite2"},
            headers={"Authorization": f"Bearer {self.operator_token}"},
        )
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.get_json().get("success"))

    def test_operator_can_use_delete_file_api(self):
        # Permission gate: operator should pass authz and reach business validation.
        resp = self.client.post(
            "/api/files/delete",
            json={},
            headers={"Authorization": f"Bearer {self.operator_token}"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_reader_forbidden_on_delete_file_api(self):
        resp = self.client.post(
            "/api/files/delete",
            json={},
            headers={"Authorization": f"Bearer {self.reader_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access_config(self):
        resp = self.client.get(
            "/api/config/categories",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        # Might be 200 or 500 if config file missing, but must not be 401/403.
        self.assertNotIn(resp.status_code, (401, 403))

    def test_session_login_uses_token(self):
        # Login via form POST should set session and allow subsequent API calls.
        resp = self.client.post("/login", data={"token": self.reader_token, "next": "/"})
        self.assertEqual(resp.status_code, 302)

        api = self.client.get("/api/stats")
        self.assertEqual(api.status_code, 200)

    def test_admin_can_create_and_revoke_token(self):
        create = self.client.post(
            "/api/auth/tokens",
            json={"subject": "new-user", "group_name": "reader"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(create.status_code, 200)
        data = create.get_json()
        self.assertTrue(data.get("success"))
        new_plain = data["token"]["token"]
        new_id = data["token"]["id"]

        # New token works
        ok = self.client.get("/api/stats", headers={"Authorization": f"Bearer {new_plain}"})
        self.assertEqual(ok.status_code, 200)

        # Revoke and verify blocked
        revoke = self.client.post(
            f"/api/auth/tokens/{new_id}/revoke",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(revoke.status_code, 200)

        blocked = self.client.get("/api/stats", headers={"Authorization": f"Bearer {new_plain}"})
        self.assertEqual(blocked.status_code, 401)


if __name__ == "__main__":
    unittest.main()

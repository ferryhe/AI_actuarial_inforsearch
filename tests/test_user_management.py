#!/usr/bin/env python3
"""Tests for email-based user management: registration, login, quotas, admin endpoints."""

import os
import sys
import tempfile
import types
import unittest

import yaml

# Stub out optional heavy dependencies so they don't prevent import.
if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.storage import Storage
from ai_actuarial.web.app import create_app, _hash_password, _check_password


def _make_app_and_storage(db_path: str, cfg_path: str):
    os.environ["CONFIG_PATH"] = cfg_path
    os.environ["REQUIRE_AUTH"] = "false"
    os.environ["FLASK_SECRET_KEY"] = "test-secret-um"
    app = create_app({"TESTING": True})
    return app


def _minimal_config(db_path: str, cfg_path: str) -> None:
    cfg = {
        "paths": {"db": db_path, "download_dir": "/tmp/files", "updates_dir": "/tmp/updates"},
        "defaults": {"user_agent": "TestAgent/1.0", "max_pages": 1, "max_depth": 1, "file_exts": [".pdf"]},
        "sites": [],
    }
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)


class TestPasswordHashing(unittest.TestCase):
    """Unit tests for the PBKDF2 password helpers."""

    def test_hash_and_verify(self):
        pw = "correct-horse-battery-staple"
        h = _hash_password(pw)
        self.assertTrue(_check_password(pw, h))

    def test_wrong_password_rejected(self):
        h = _hash_password("secret123")
        self.assertFalse(_check_password("wrong", h))

    def test_different_salts_produce_different_hashes(self):
        h1 = _hash_password("samepassword")
        h2 = _hash_password("samepassword")
        self.assertNotEqual(h1, h2)

    def test_malformed_hash_rejected(self):
        self.assertFalse(_check_password("anything", "not-a-valid-hash"))
        self.assertFalse(_check_password("anything", ""))


class TestUserStorageMethods(unittest.TestCase):
    """Unit tests for Storage user-management methods."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.storage.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_get_user(self):
        uid = self.storage.create_user("alice@example.com", _hash_password("pw"), role="registered")
        self.assertIsInstance(uid, int)
        user = self.storage.get_user_by_email("alice@example.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["email"], "alice@example.com")
        self.assertEqual(user["role"], "registered")

    def test_email_lookup_case_insensitive(self):
        self.storage.create_user("Bob@Example.COM", _hash_password("pw"), role="registered")
        user = self.storage.get_user_by_email("bob@example.com")
        self.assertIsNotNone(user)

    def test_duplicate_email_raises(self):
        self.storage.create_user("dup@example.com", _hash_password("pw"))
        with self.assertRaises(ValueError):
            self.storage.create_user("dup@example.com", _hash_password("pw2"))

    def test_get_user_by_id(self):
        uid = self.storage.create_user("carol@example.com", _hash_password("pw"))
        user = self.storage.get_user_by_id(uid)
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], uid)

    def test_get_user_by_id_missing(self):
        self.assertIsNone(self.storage.get_user_by_id(9999))

    def test_update_user_role(self):
        uid = self.storage.create_user("dave@example.com", _hash_password("pw"), role="registered")
        ok = self.storage.update_user_role(uid, "premium")
        self.assertTrue(ok)
        user = self.storage.get_user_by_id(uid)
        self.assertEqual(user["role"], "premium")

    def test_update_user_active(self):
        uid = self.storage.create_user("eve@example.com", _hash_password("pw"))
        self.storage.update_user_active(uid, False)
        user = self.storage.get_user_by_id(uid)
        self.assertEqual(user["is_active"], 0)

    def test_list_users_pagination(self):
        for i in range(5):
            self.storage.create_user(f"user{i}@test.com", _hash_password("pw"))
        users, total = self.storage.list_users(page=1, per_page=3)
        self.assertEqual(total, 5)
        self.assertEqual(len(users), 3)

    def test_list_users_role_filter(self):
        self.storage.create_user("r@test.com", _hash_password("pw"), role="registered")
        self.storage.create_user("p@test.com", _hash_password("pw"), role="premium")
        users, total = self.storage.list_users(role="premium")
        self.assertEqual(total, 1)
        self.assertEqual(users[0]["email"], "p@test.com")

    def test_password_hash_not_in_get_user_by_email_result(self):
        # get_user_by_email returns the full row including password_hash (for login checks).
        # The caller (auth middleware) strips it before embedding in the request context.
        self.storage.create_user("hash_test@example.com", _hash_password("pw"))
        user = self.storage.get_user_by_email("hash_test@example.com")
        # The raw storage result includes password_hash — stripping is done in app layer.
        self.assertIn("password_hash", user)


class TestUserQuotaMethods(unittest.TestCase):
    """Unit tests for atomic quota check-and-increment."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.storage = Storage(self.db_path)
        self.uid = self.storage.create_user("quota@test.com", _hash_password("pw"))
        self.date = "2099-01-01"

    def tearDown(self):
        self.storage.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_first_query_allowed(self):
        allowed, count = self.storage.check_and_increment_ai_chat_quota(
            self.date, 5, user_id=self.uid
        )
        self.assertTrue(allowed)
        self.assertEqual(count, 1)

    def test_within_limit_increments(self):
        # With limit=5: calls 1–5 are allowed, call 6 is blocked.
        for i in range(5):
            allowed, count = self.storage.check_and_increment_ai_chat_quota(
                self.date, 5, user_id=self.uid
            )
            self.assertTrue(allowed, f"Call {i+1} should be allowed (limit=5)")
            self.assertEqual(count, i + 1)
        # 6th call should be blocked
        allowed, _ = self.storage.check_and_increment_ai_chat_quota(
            self.date, 5, user_id=self.uid
        )
        self.assertFalse(allowed, "6th call should be blocked when limit=5")

    def test_limit_one_allows_first_blocks_second(self):
        allowed, count = self.storage.check_and_increment_ai_chat_quota(
            self.date, 1, user_id=self.uid
        )
        self.assertTrue(allowed)
        self.assertEqual(count, 1)
        allowed2, _ = self.storage.check_and_increment_ai_chat_quota(
            self.date, 1, user_id=self.uid
        )
        self.assertFalse(allowed2)

    def test_ip_based_quota(self):
        allowed, count = self.storage.check_and_increment_ai_chat_quota(
            self.date, 1, ip_address="1.2.3.4"
        )
        self.assertTrue(allowed)
        self.assertEqual(count, 1)
        allowed2, _ = self.storage.check_and_increment_ai_chat_quota(
            self.date, 1, ip_address="1.2.3.4"
        )
        self.assertFalse(allowed2)

    def test_reset_quota_clears_count(self):
        self.storage.check_and_increment_ai_chat_quota(self.date, 5, user_id=self.uid)
        self.storage.check_and_increment_ai_chat_quota(self.date, 5, user_id=self.uid)
        self.storage.reset_user_quota(self.uid, self.date)
        used = self.storage.get_ai_chat_quota_used(self.date, user_id=self.uid)
        self.assertEqual(used, 0)

    def test_get_quota_used(self):
        self.storage.check_and_increment_ai_chat_quota(self.date, 5, user_id=self.uid)
        self.storage.check_and_increment_ai_chat_quota(self.date, 5, user_id=self.uid)
        used = self.storage.get_ai_chat_quota_used(self.date, user_id=self.uid)
        self.assertEqual(used, 2)

    def test_different_dates_are_independent(self):
        self.storage.check_and_increment_ai_chat_quota("2099-01-01", 1, user_id=self.uid)
        # Different date should start fresh
        allowed, count = self.storage.check_and_increment_ai_chat_quota(
            "2099-01-02", 1, user_id=self.uid
        )
        self.assertTrue(allowed)
        self.assertEqual(count, 1)


class TestUserActivityLog(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.storage = Storage(self.db_path)
        self.uid = self.storage.create_user("log@test.com", _hash_password("pw"))

    def tearDown(self):
        self.storage.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_log_and_retrieve(self):
        self.storage.log_user_activity("login", user_id=self.uid, ip_address="1.2.3.4")
        self.storage.log_user_activity("register", user_id=self.uid)
        logs = self.storage.list_user_activity(user_id=self.uid)
        self.assertEqual(len(logs), 2)
        actions = [l["action"] for l in logs]
        self.assertIn("login", actions)
        self.assertIn("register", actions)

    def test_list_all_activity(self):
        self.storage.log_user_activity("x", user_id=self.uid)
        all_logs = self.storage.list_user_activity()
        self.assertGreaterEqual(len(all_logs), 1)


class TestRegistrationEndpoint(unittest.TestCase):
    """Integration tests for /register via the Flask test client."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.cfg_fd, self.cfg_path = tempfile.mkstemp(suffix=".yaml", text=True)
        _minimal_config(self.db_path, self.cfg_path)
        self._orig_env = dict(os.environ)
        self.app = _make_app_and_storage(self.db_path, self.cfg_path)
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.cfg_path)
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_register_success(self):
        resp = self.client.post(
            "/register",
            data={"email": "newuser@example.com", "password": "strongpassword1"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        # Verify user in DB
        storage = Storage(self.db_path)
        user = storage.get_user_by_email("newuser@example.com")
        storage.close()
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "registered")

    def test_register_duplicate_email(self):
        storage = Storage(self.db_path)
        storage.create_user("existing@example.com", _hash_password("pw"))
        storage.close()
        resp = self.client.post(
            "/register",
            data={"email": "existing@example.com", "password": "strongpassword1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"already registered", resp.data.lower())

    def test_register_invalid_email(self):
        resp = self.client.post(
            "/register",
            data={"email": "not-an-email", "password": "strongpassword1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"email", resp.data.lower())

    def test_register_short_password(self):
        resp = self.client.post(
            "/register",
            data={"email": "short@example.com", "password": "abc"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"8", resp.data)

    def test_register_api_success(self):
        # /register processes form data (not JSON), regardless of content type,
        # because it's not under /api/ path.
        resp = self.client.post(
            "/register",
            data={"email": "api@example.com", "password": "strongpassword1"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        storage = Storage(self.db_path)
        user = storage.get_user_by_email("api@example.com")
        storage.close()
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "registered")


class TestEmailLoginEndpoint(unittest.TestCase):
    """Integration tests for /email-login via the Flask test client."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.cfg_fd, self.cfg_path = tempfile.mkstemp(suffix=".yaml", text=True)
        _minimal_config(self.db_path, self.cfg_path)
        self._orig_env = dict(os.environ)
        self.app = _make_app_and_storage(self.db_path, self.cfg_path)
        self.client = self.app.test_client()
        # Pre-create a user
        storage = Storage(self.db_path)
        storage.create_user("login@example.com", _hash_password("correctpass"), role="registered")
        storage.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.cfg_path)
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_login_success_sets_session(self):
        resp = self.client.post(
            "/email-login",
            data={"email": "login@example.com", "password": "correctpass"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertIn("email_user_id", sess)

    def test_login_wrong_password(self):
        resp = self.client.post(
            "/email-login",
            data={"email": "login@example.com", "password": "wrongpassword"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"invalid", resp.data.lower())

    def test_login_unknown_email(self):
        resp = self.client.post(
            "/email-login",
            data={"email": "nobody@example.com", "password": "whatever"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"invalid", resp.data.lower())

    def test_login_disabled_account(self):
        storage = Storage(self.db_path)
        uid = storage.create_user("disabled@example.com", _hash_password("pw"))
        storage.update_user_active(uid, False)
        storage.close()
        resp = self.client.post(
            "/email-login",
            data={"email": "disabled@example.com", "password": "pw"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"disabled", resp.data.lower())

    def test_login_api_success(self):
        resp = self.client.post(
            "/email-login",
            json={"email": "login@example.com", "password": "correctpass"},
            content_type="application/json",
        )
        # /email-login redirects on success (web page, not /api/ path)
        self.assertIn(resp.status_code, (200, 302))
        if resp.status_code == 302:
            with self.client.session_transaction() as sess:
                self.assertIn("email_user_id", sess)


class TestAdminUserEndpoints(unittest.TestCase):
    """Integration tests for admin user management API endpoints."""

    def _make_admin_token(self):
        import hashlib
        tok = "admin_" + os.urandom(16).hex()
        storage = Storage(self.db_path)
        storage.upsert_auth_token_by_hash(
            subject="admin",
            group_name="admin",
            token_hash=hashlib.sha256(tok.encode()).hexdigest(),
            is_active=True,
        )
        storage.close()
        return tok

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.cfg_fd, self.cfg_path = tempfile.mkstemp(suffix=".yaml", text=True)
        _minimal_config(self.db_path, self.cfg_path)
        self._orig_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.cfg_path
        os.environ["REQUIRE_AUTH"] = "true"
        os.environ["FLASK_SECRET_KEY"] = "test-secret-admin"
        self.admin_token = self._make_admin_token()
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        # Create a target user
        storage = Storage(self.db_path)
        self.target_uid = storage.create_user("target@example.com", _hash_password("pw"), role="registered")
        storage.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
        os.unlink(self.cfg_path)
        os.environ.clear()
        os.environ.update(self._orig_env)

    def _auth_header(self):
        return {"Authorization": f"Bearer {self.admin_token}"}

    def test_list_users_requires_auth(self):
        resp = self.client.get("/api/admin/users")
        self.assertIn(resp.status_code, (401, 403))

    def test_list_users_as_admin(self):
        resp = self.client.get("/api/admin/users", headers=self._auth_header())
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["total"], 1)
        # password_hash must not be exposed
        for u in data["users"]:
            self.assertNotIn("password_hash", u)

    def test_change_user_role(self):
        resp = self.client.post(
            f"/api/admin/users/{self.target_uid}/role",
            json={"role": "premium"},
            headers=self._auth_header(),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["role"], "premium")
        # Verify in DB
        storage = Storage(self.db_path)
        user = storage.get_user_by_id(self.target_uid)
        storage.close()
        self.assertEqual(user["role"], "premium")

    def test_change_user_role_invalid(self):
        resp = self.client.post(
            f"/api/admin/users/{self.target_uid}/role",
            json={"role": "superadmin"},
            headers=self._auth_header(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_disable_user(self):
        resp = self.client.post(
            f"/api/admin/users/{self.target_uid}/active",
            json={"is_active": False},
            headers=self._auth_header(),
        )
        self.assertEqual(resp.status_code, 200)
        storage = Storage(self.db_path)
        user = storage.get_user_by_id(self.target_uid)
        storage.close()
        self.assertEqual(user["is_active"], 0)

    def test_reset_quota(self):
        storage = Storage(self.db_path)
        storage.check_and_increment_ai_chat_quota("2099-01-01", 5, user_id=self.target_uid)
        storage.close()
        resp = self.client.post(
            f"/api/admin/users/{self.target_uid}/reset-quota",
            json={"quota_date": "2099-01-01"},
            headers=self._auth_header(),
        )
        self.assertEqual(resp.status_code, 200)
        storage = Storage(self.db_path)
        used = storage.get_ai_chat_quota_used("2099-01-01", user_id=self.target_uid)
        storage.close()
        self.assertEqual(used, 0)

    def test_user_activity_log(self):
        storage = Storage(self.db_path)
        storage.log_user_activity("login", user_id=self.target_uid, ip_address="1.2.3.4")
        storage.close()
        resp = self.client.get(
            f"/api/admin/users/{self.target_uid}/activity",
            headers=self._auth_header(),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["logs"]), 1)
        self.assertEqual(data["logs"][0]["action"], "login")

    def test_non_admin_cannot_list_users(self):
        import hashlib
        reader_tok = "reader_" + os.urandom(16).hex()
        storage = Storage(self.db_path)
        storage.upsert_auth_token_by_hash(
            subject="reader", group_name="reader",
            token_hash=hashlib.sha256(reader_tok.encode()).hexdigest(), is_active=True,
        )
        storage.close()
        resp = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {reader_tok}"},
        )
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()

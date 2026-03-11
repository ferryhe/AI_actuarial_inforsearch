import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import yaml

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.storage import Storage
from ai_actuarial.web.app import FLASK_AVAILABLE, create_app

MAX_CLEANUP_RETRIES = 10


class TestGlobalChunkPhaseA(unittest.TestCase):
    def setUp(self):
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed")

        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_path = os.path.join(self.temp_dir, "categories.yaml")
        self.admin_token = "test-global-chunk-admin-token"

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

        self.original_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_path
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = self.admin_token
        os.environ["FLASK_SECRET_KEY"] = "test-global-chunk-secret"
        os.environ["REQUIRE_AUTH"] = "false"
        os.environ["RAG_DATA_DIR"] = os.path.join(self.temp_dir, "rag_data")

        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()
        self.auth_header = {"Authorization": f"Bearer {self.admin_token}"}

        self.storage = Storage(self.db_path)
        self.file_url = "test://global-chunk-file.pdf"
        self.storage.insert_file(
            url=self.file_url,
            sha256="sha-test-1",
            title="Global Chunk Test Document",
            source_site="test",
            source_page_url="test://source",
            original_filename="test.pdf",
            local_path="/tmp/test.pdf",
            bytes=2048,
            content_type="application/pdf",
        )
        self.storage.update_file_markdown(
            self.file_url,
            "# Section 1\n\nThis is a paragraph for chunking.\n\n## Section 1.1\n\nAnother paragraph.",
            "manual",
        )

    def tearDown(self):
        if hasattr(self, "storage"):
            self.storage.close()

        os.environ.clear()
        os.environ.update(self.original_env)

        if os.path.exists(self.temp_dir):
            for _ in range(MAX_CLEANUP_RETRIES):
                try:
                    shutil.rmtree(self.temp_dir)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def test_phase_a_profile_chunk_binding_flow(self):
        profile_resp = self.client.post(
            "/api/chunk/profiles",
            headers=self.auth_header,
            json={
                "name": "KB default profile",
                "chunk_size": 300,
                "chunk_overlap": 50,
                "splitter": "semantic",
                "tokenizer": "cl100k_base",
                "version": "v1",
            },
        )
        if profile_resp.status_code == 503:
            self.skipTest("RAG functionality not available")
        self.assertEqual(profile_resp.status_code, 201)
        profile_data = profile_resp.get_json()
        self.assertTrue(profile_data["success"])
        profile_id = profile_data["data"]["profile_id"]

        encoded_file_url = quote(self.file_url, safe="")
        gen_resp = self.client.post(
            f"/api/files/{encoded_file_url}/chunk-sets/generate",
            headers=self.auth_header,
            json={"profile_id": profile_id, "overwrite_same_profile": True},
        )
        self.assertIn(gen_resp.status_code, [200, 201])
        gen_data = gen_resp.get_json()
        self.assertTrue(gen_data["success"])
        self.assertGreater(gen_data["data"]["chunk_count"], 0)
        chunk_set_id = gen_data["data"]["chunk_set_id"]

        list_resp = self.client.get(f"/api/files/{encoded_file_url}/chunk-sets", headers=self.auth_header)
        self.assertEqual(list_resp.status_code, 200)
        list_data = list_resp.get_json()
        self.assertTrue(list_data["success"])
        self.assertGreaterEqual(list_data["data"]["count"], 1)

        kb_id = "kb_phasea_test"
        create_kb_resp = self.client.post(
            "/api/rag/knowledge-bases",
            headers=self.auth_header,
            json={
                "kb_id": kb_id,
                "name": "PhaseA KB",
                "kb_mode": "manual",
                "chunk_size": 300,
                "chunk_overlap": 50,
                "embedding_model": "text-embedding-3-small",
            },
        )
        self.assertEqual(create_kb_resp.status_code, 201)
        add_file_resp = self.client.post(
            f"/api/rag/knowledge-bases/{kb_id}/files",
            headers=self.auth_header,
            json={"file_urls": [self.file_url]},
        )
        self.assertEqual(add_file_resp.status_code, 200)

        bind_resp = self.client.post(
            f"/api/rag/knowledge-bases/{kb_id}/bindings",
            headers=self.auth_header,
            json={"file_url": self.file_url, "chunk_set_id": chunk_set_id, "bound_by": "test"},
        )
        self.assertEqual(bind_resp.status_code, 200)
        bind_data = bind_resp.get_json()
        self.assertTrue(bind_data["success"])
        self.assertEqual(bind_data["data"]["created"], 1)

        files_resp = self.client.get(
            f"/api/rag/knowledge-bases/{kb_id}/files",
            headers=self.auth_header,
        )
        self.assertEqual(files_resp.status_code, 200)
        files_payload = files_resp.get_json()["data"]
        self.assertEqual(files_payload["total_files"], 1)
        self.assertIn("profile_summary", files_payload)
        file_row = files_payload["files"][0]
        self.assertEqual(file_row.get("chunk_set_id"), chunk_set_id)
        self.assertGreaterEqual(int(file_row.get("chunk_version_count") or 0), 1)
        self.assertIn("chunk_set_updated_at", file_row)

        status_resp = self.client.get(
            f"/api/rag/knowledge-bases/{kb_id}/composition/status",
            headers=self.auth_header,
        )
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.get_json()
        self.assertTrue(status_data["success"])
        self.assertEqual(status_data["data"]["file_count"], 1)
        self.assertGreaterEqual(status_data["data"]["chunk_set_count"], 1)

    def test_chunk_profile_delete_endpoint_removes_profile(self):
        profile_resp = self.client.post(
            "/api/chunk/profiles",
            headers=self.auth_header,
            json={
                "name": "Delete Me",
                "chunk_size": 256,
                "chunk_overlap": 32,
                "splitter": "semantic",
                "tokenizer": "cl100k_base",
                "version": "v1",
            },
        )
        if profile_resp.status_code == 503:
            self.skipTest("RAG functionality not available")
        self.assertEqual(profile_resp.status_code, 201)
        profile_id = profile_resp.get_json()["data"]["profile_id"]

        delete_resp = self.client.delete(
            f"/api/chunk/profiles/{profile_id}",
            headers=self.auth_header,
        )
        self.assertEqual(delete_resp.status_code, 200)
        delete_data = delete_resp.get_json()
        self.assertTrue(delete_data["success"])
        self.assertEqual(delete_data["data"]["profile_id"], profile_id)
        self.assertTrue(delete_data["data"]["deleted"])

        list_resp = self.client.get("/api/chunk/profiles", headers=self.auth_header)
        self.assertEqual(list_resp.status_code, 200)
        profiles = list_resp.get_json()["data"]["profiles"]
        self.assertFalse(any(item["profile_id"] == profile_id for item in profiles))

    def test_follow_latest_binding_auto_sync_on_new_chunk(self):
        profile_resp = self.client.post(
            "/api/chunk/profiles",
            headers=self.auth_header,
            json={
                "name": "Follow Latest Profile",
                "chunk_size": 280,
                "chunk_overlap": 40,
                "splitter": "semantic",
                "tokenizer": "cl100k_base",
                "version": "v1",
            },
        )
        if profile_resp.status_code == 503:
            self.skipTest("RAG functionality not available")
        self.assertEqual(profile_resp.status_code, 201)
        profile_id = profile_resp.get_json()["data"]["profile_id"]

        encoded_file_url = quote(self.file_url, safe="")
        first_gen_resp = self.client.post(
            f"/api/files/{encoded_file_url}/chunk-sets/generate",
            headers=self.auth_header,
            json={"profile_id": profile_id, "overwrite_same_profile": True},
        )
        self.assertIn(first_gen_resp.status_code, [200, 201])
        first_data = first_gen_resp.get_json()["data"]
        first_chunk_set_id = first_data["chunk_set_id"]
        self.assertGreater(first_data["chunk_count"], 0)

        kb_id = "kb_follow_latest_sync"
        create_kb_resp = self.client.post(
            "/api/rag/knowledge-bases",
            headers=self.auth_header,
            json={
                "kb_id": kb_id,
                "name": "FollowLatest KB",
                "kb_mode": "manual",
                "chunk_size": 280,
                "chunk_overlap": 40,
                "embedding_model": "text-embedding-3-small",
            },
        )
        self.assertEqual(create_kb_resp.status_code, 201)

        bind_resp = self.client.post(
            f"/api/rag/knowledge-bases/{kb_id}/bindings",
            headers=self.auth_header,
            json={
                "file_url": self.file_url,
                "chunk_set_id": first_chunk_set_id,
                "binding_mode": "follow_latest",
                "bound_by": "test",
            },
        )
        self.assertEqual(bind_resp.status_code, 200)
        bind_data = bind_resp.get_json()
        self.assertTrue(bind_data["success"])
        self.assertEqual(bind_data["data"]["created"], 1)

        # Simulate an index snapshot before markdown/chunk update.
        self.storage.create_kb_index_version(
            kb_id=kb_id,
            embedding_model="text-embedding-3-small",
            index_type="Flat",
            chunk_count=int(first_data["chunk_count"]),
            status="ready",
            artifact_path="",
        )

        # Markdown changed -> a new chunk_set should be created and follow_latest should auto-sync.
        self.storage.update_file_markdown(
            self.file_url,
            "# Section 1\n\nUpdated markdown content.\n\n## Section 2\n\nMore updated text.",
            "manual",
        )
        second_gen_resp = self.client.post(
            f"/api/files/{encoded_file_url}/chunk-sets/generate",
            headers=self.auth_header,
            json={"profile_id": profile_id, "overwrite_same_profile": True},
        )
        self.assertIn(second_gen_resp.status_code, [200, 201])
        second_payload = second_gen_resp.get_json()["data"]
        second_chunk_set_id = second_payload["chunk_set_id"]
        self.assertNotEqual(second_chunk_set_id, first_chunk_set_id)
        self.assertGreaterEqual(int(second_payload.get("auto_synced_kb_bindings", 0)), 1)

        status_resp = self.client.get(
            f"/api/rag/knowledge-bases/{kb_id}/composition/status",
            headers=self.auth_header,
        )
        self.assertEqual(status_resp.status_code, 200)
        status_payload = status_resp.get_json()["data"]
        self.assertTrue(status_payload["needs_reindex"])

        bindings = status_payload.get("bindings") or []
        self.assertTrue(any(b.get("chunk_set_id") == second_chunk_set_id for b in bindings))
        self.assertTrue(any((b.get("binding_mode") or "") == "follow_latest" for b in bindings))
        self.assertFalse(any(b.get("chunk_set_id") == first_chunk_set_id for b in bindings))

    def test_cleanup_orphan_chunk_sets_endpoint(self):
        profile_resp = self.client.post(
            "/api/chunk/profiles",
            headers=self.auth_header,
            json={
                "name": "Cleanup Profile",
                "chunk_size": 256,
                "chunk_overlap": 32,
                "splitter": "semantic",
                "tokenizer": "cl100k_base",
                "version": "v1",
            },
        )
        if profile_resp.status_code == 503:
            self.skipTest("RAG functionality not available")
        self.assertEqual(profile_resp.status_code, 201)
        profile_id = profile_resp.get_json()["data"]["profile_id"]

        encoded_file_url = quote(self.file_url, safe="")
        gen_resp = self.client.post(
            f"/api/files/{encoded_file_url}/chunk-sets/generate",
            headers=self.auth_header,
            json={"profile_id": profile_id, "overwrite_same_profile": True},
        )
        self.assertIn(gen_resp.status_code, [200, 201])
        chunk_set_id = gen_resp.get_json()["data"]["chunk_set_id"]

        old_ts = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        self.storage._conn.execute(
            "UPDATE file_chunk_sets SET updated_at = ?, created_at = ? WHERE chunk_set_id = ?",
            (old_ts, old_ts, chunk_set_id),
        )
        self.storage._conn.commit()

        preview_resp = self.client.post(
            "/api/chunk-sets/cleanup",
            headers=self.auth_header,
            json={"older_than_days": 30, "dry_run": True},
        )
        self.assertEqual(preview_resp.status_code, 200)
        preview_data = preview_resp.get_json()["data"]
        self.assertGreaterEqual(int(preview_data["candidates"]), 1)

        run_resp = self.client.post(
            "/api/chunk-sets/cleanup",
            headers=self.auth_header,
            json={"older_than_days": 30, "dry_run": False},
        )
        self.assertEqual(run_resp.status_code, 200)
        run_data = run_resp.get_json()["data"]
        self.assertGreaterEqual(int(run_data["deleted_chunk_sets"]), 1)

        exists = self.storage._conn.execute(
            "SELECT 1 FROM file_chunk_sets WHERE chunk_set_id = ? LIMIT 1",
            (chunk_set_id,),
        ).fetchone()
        self.assertIsNone(exists)

    def test_create_kb_index_version_keeps_latest_only(self):
        kb_id = "kb_index_retention_test"
        create_kb_resp = self.client.post(
            "/api/rag/knowledge-bases",
            headers=self.auth_header,
            json={
                "kb_id": kb_id,
                "name": "IndexRetention KB",
                "kb_mode": "manual",
                "chunk_size": 300,
                "chunk_overlap": 50,
                "embedding_model": "text-embedding-3-small",
            },
        )
        if create_kb_resp.status_code == 503:
            self.skipTest("RAG functionality not available")
        self.assertEqual(create_kb_resp.status_code, 201)

        first = self.storage.create_kb_index_version(
            kb_id=kb_id,
            embedding_model="text-embedding-3-small",
            index_type="Flat",
            chunk_count=10,
            status="ready",
            artifact_path="index1.faiss",
        )
        second = self.storage.create_kb_index_version(
            kb_id=kb_id,
            embedding_model="text-embedding-3-small",
            index_type="Flat",
            chunk_count=12,
            status="ready",
            artifact_path="index2.faiss",
        )
        self.assertNotEqual(first["index_version_id"], second["index_version_id"])

        count = int(
            self.storage._conn.execute(
                "SELECT COUNT(*) FROM kb_index_versions WHERE kb_id = ?",
                (kb_id,),
            ).fetchone()[0]
            or 0
        )
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()

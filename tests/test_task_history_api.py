import json
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

import ai_actuarial.web.app as web_app_module
from ai_actuarial.web.app import FLASK_AVAILABLE, create_app


class TestTaskHistoryApi(unittest.TestCase):
    def setUp(self):
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed")

        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_path = os.path.join(self.temp_dir, "categories.yaml")

        config_data = {
            "paths": {
                "db": self.db_path,
                "download_dir": os.path.join(self.temp_dir, "files"),
                "updates_dir": os.path.join(self.temp_dir, "updates"),
                "last_run_new": os.path.join(self.temp_dir, "last_run_new.json"),
            },
            "defaults": {
                "user_agent": "test-agent/1.0",
                "max_pages": 5,
                "max_depth": 1,
                "file_exts": [".pdf"],
                "keywords": ["actuarial"],
            },
            "sites": [],
        }
        categories_data = {"categories": {"General": ["test"]}}

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, sort_keys=False, allow_unicode=True)
        with open(self.categories_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(categories_data, f, sort_keys=False, allow_unicode=True)

        self.original_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_path
        os.environ["FLASK_SECRET_KEY"] = "test-task-history-secret"
        os.environ["REQUIRE_AUTH"] = "false"
        os.environ["RAG_DATA_DIR"] = os.path.join(self.temp_dir, "rag_data")

        self.original_history = list(web_app_module._task_history)
        self.original_active = dict(web_app_module._active_tasks)
        with web_app_module._task_lock:
            web_app_module._task_history.clear()
            web_app_module._active_tasks.clear()

        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()

    def tearDown(self):
        with web_app_module._task_lock:
            web_app_module._task_history.clear()
            web_app_module._task_history.extend(self.original_history)
            web_app_module._active_tasks.clear()
            web_app_module._active_tasks.update(self.original_active)

        os.environ.clear()
        os.environ.update(self.original_env)

        for _ in range(10):
            try:
                shutil.rmtree(self.temp_dir)
                break
            except PermissionError:
                time.sleep(0.1)

    def test_history_includes_display_summary_for_task_types(self):
        with web_app_module._task_lock:
            web_app_module._task_history.extend(
                [
                    {
                        "id": "task_md_1",
                        "name": "Markdown Batch",
                        "type": "markdown_conversion",
                        "status": "partial",
                        "started_at": "2026-03-11T10:00:00",
                        "completed_at": "2026-03-11T10:05:00",
                        "items_processed": 3,
                        "items_downloaded": 1,
                        "items_skipped": 1,
                        "errors": ["file-3 failed"],
                    },
                    {
                        "id": "task_rag_1",
                        "name": "KB Index",
                        "type": "rag_indexing",
                        "status": "completed",
                        "started_at": "2026-03-11T09:00:00",
                        "completed_at": "2026-03-11T09:04:00",
                        "items_processed": 4,
                        "items_downloaded": 4,
                        "items_skipped": 0,
                        "errors": [],
                        "rag_total_chunks": 27,
                        "rag_error_files": 0,
                    },
                ]
            )

        response = self.client.get("/api/tasks/history?limit=10")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.data)
        self.assertIn("tasks", payload)
        self.assertEqual(len(payload["tasks"]), 2)

        markdown_task = next(task for task in payload["tasks"] if task["type"] == "markdown_conversion")
        self.assertEqual(markdown_task["error_count"], 1)
        self.assertEqual(markdown_task["display_summary"]["primary"]["label"], "Converted")
        self.assertEqual(markdown_task["display_summary"]["primary"]["value"], 1)
        self.assertEqual(markdown_task["display_summary"]["secondary"][0]["label"], "Skipped")

        rag_task = next(task for task in payload["tasks"] if task["type"] == "rag_indexing")
        self.assertEqual(rag_task["display_summary"]["primary"]["label"], "Indexed Files")
        self.assertEqual(rag_task["display_summary"]["primary"]["value"], 4)
        self.assertEqual(rag_task["display_summary"]["secondary"][2]["value"], 27)

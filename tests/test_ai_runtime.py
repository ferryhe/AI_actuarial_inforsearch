#!/usr/bin/env python3
"""Tests for unified AI runtime configuration resolution."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ai_actuarial.ai_runtime import (
    get_ai_function_section,
    resolve_ai_function_runtime,
)
from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.storage import Storage


class TestAiRuntime(unittest.TestCase):
    """Test unified provider and AI function resolution."""

    def setUp(self):
        self.original_env = dict(os.environ)
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        self.storage.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_ai_function_section_supports_chatbot_provider_key(self):
        """chatbot.provider should normalize without legacy llm_provider."""
        yaml_config = {
            "ai_config": {
                "chatbot": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                }
            }
        }

        section = get_ai_function_section("chatbot", yaml_config=yaml_config)

        self.assertEqual(section["provider"], "deepseek")
        self.assertEqual(section["model"], "deepseek-chat")

    def test_resolve_ai_function_runtime_prefers_db_credentials(self):
        """DB provider credentials should override env fallback for runtime use."""
        yaml_config = {
            "ai_config": {
                "chatbot": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                }
            }
        }
        os.environ["DEEPSEEK_API_KEY"] = "env-deepseek-key"

        encrypted = TokenEncryption().encrypt("db-deepseek-key")
        self.storage.upsert_llm_provider(
            provider="deepseek",
            api_key_encrypted=encrypted,
            base_url="https://custom.deepseek.test/v1",
        )

        runtime = resolve_ai_function_runtime(
            "chatbot",
            storage=self.storage,
            yaml_config=yaml_config,
        )

        self.assertEqual(runtime.provider, "deepseek")
        self.assertEqual(runtime.model, "deepseek-chat")
        self.assertEqual(runtime.api_key, "db-deepseek-key")
        self.assertEqual(runtime.base_url, "https://custom.deepseek.test/v1")
        self.assertEqual(runtime.credential_source, "db")


if __name__ == "__main__":
    unittest.main()

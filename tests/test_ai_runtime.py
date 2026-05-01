#!/usr/bin/env python3
"""Tests for unified AI runtime configuration resolution."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from ai_actuarial.ai_runtime import (
    get_ai_function_section,
    resolve_provider_credentials,
    resolve_ai_function_runtime,
    resolve_ocr_runtime,
)
from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.storage import Storage


class TestAiRuntime(unittest.TestCase):
    """Test unified provider and AI function resolution."""

    def setUp(self):
        self.original_env = dict(os.environ)
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        TokenEncryption._instance = None
        self.storage = Storage(self.db_path)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        TokenEncryption._instance = None
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

    def test_resolve_ocr_runtime_uses_provider_mapping(self):
        """OCR runtime should map ai_config provider to engine/model consistently."""
        yaml_config = {
            "ai_config": {
                "ocr": {
                    "provider": "mistral",
                    "model": "mistral-ocr-latest",
                }
            }
        }
        encrypted = TokenEncryption().encrypt("db-mistral-key")
        self.storage.upsert_llm_provider(
            provider="mistral",
            api_key_encrypted=encrypted,
            base_url="https://api.mistral.ai/v1",
        )

        runtime = resolve_ocr_runtime(storage=self.storage, yaml_config=yaml_config)

        self.assertEqual(runtime.provider, "mistral")
        self.assertEqual(runtime.engine, "mistral")
        self.assertEqual(runtime.model, "mistral-ocr-latest")
        self.assertEqual(runtime.api_key, "db-mistral-key")

    def test_resolve_ocr_runtime_engine_override_resets_model(self):
        """Explicit OCR engine selection should not inherit an incompatible YAML model."""
        yaml_config = {
            "ai_config": {
                "ocr": {
                    "provider": "mistral",
                    "model": "mistral-ocr-latest",
                }
            }
        }

        runtime = resolve_ocr_runtime(
            storage=self.storage,
            yaml_config=yaml_config,
            engine_override="marker",
        )

        self.assertEqual(runtime.provider, "local")
        self.assertEqual(runtime.engine, "marker")
        self.assertEqual(runtime.model, "marker")

    def test_resolve_ocr_runtime_supports_recommended_local_pdf_engines(self):
        """OpenDataLoader and MarkItDown should behave as local OCR engines."""
        yaml_config = {
            "ai_config": {
                "ocr": {
                    "provider": "mistral",
                    "model": "mistral-ocr-latest",
                }
            }
        }

        opendataloader = resolve_ocr_runtime(
            storage=self.storage,
            yaml_config=yaml_config,
            engine_override="opendataloader",
        )
        markitdown = resolve_ocr_runtime(
            storage=self.storage,
            yaml_config=yaml_config,
            engine_override="markitdown",
        )

        self.assertEqual(opendataloader.provider, "local")
        self.assertEqual(opendataloader.engine, "opendataloader")
        self.assertEqual(opendataloader.model, "opendataloader")
        self.assertEqual(markitdown.provider, "local")
        self.assertEqual(markitdown.engine, "markitdown")
        self.assertEqual(markitdown.model, "markitdown")

    def test_resolve_ocr_runtime_supports_mathpix_engine_override(self):
        """Mathpix should resolve to the Mathpix OCR provider and model."""
        runtime = resolve_ocr_runtime(
            storage=self.storage,
            yaml_config={"ai_config": {"ocr": {"provider": "local", "model": "docling"}}},
            engine_override="mathpix",
        )

        self.assertEqual(runtime.provider, "mathpix")
        self.assertEqual(runtime.engine, "mathpix")
        self.assertEqual(runtime.model, "mathpix")

    def test_resolve_provider_credentials_invalid_db_credential_id_does_not_fall_back(self):
        """Unknown bound credential ids should be treated as missing instead of silently using the default."""
        encrypted = TokenEncryption().encrypt("db-openai-key")
        self.storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted=encrypted,
            base_url="https://api.openai.example/v1",
            instance_id="primary",
            label="OpenAI Primary",
        )

        credentials = resolve_provider_credentials(
            "openai",
            storage=self.storage,
            credential_id="openai:llm:db:999999",
        )

        self.assertEqual(credentials.provider, "openai")
        self.assertIsNone(credentials.api_key)
        self.assertFalse(credentials.configured)
        self.assertEqual(credentials.source, "missing")

    def test_resolve_provider_credentials_supports_stable_instance_id(self):
        encrypted = TokenEncryption().encrypt("db-openai-key")
        self.storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted=encrypted,
            base_url="https://api.openai.example/v1",
            instance_id="default",
            label="OpenAI Default",
        )

        credentials = resolve_provider_credentials(
            "openai",
            storage=self.storage,
            credential_id="openai:llm:instance:default",
        )

        self.assertEqual(credentials.source, "db")
        self.assertEqual(credentials.api_key, "db-openai-key")
        self.assertEqual(credentials.stable_credential_id, "openai:llm:instance:default")
        self.assertTrue(str(credentials.credential_id).startswith("openai:llm:db:"))

    def test_resolve_provider_credentials_rejects_category_mismatch(self):
        encrypted = TokenEncryption().encrypt("search-key")
        self.storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted=encrypted,
            category="search",
            instance_id="default",
        )

        credentials = resolve_provider_credentials(
            "openai",
            storage=self.storage,
            credential_id="openai:search:instance:default",
        )

        self.assertIsNone(credentials.api_key)
        self.assertEqual(credentials.source, "missing")
        self.assertEqual(credentials.error, "credential_binding_mismatch")

    def test_resolve_provider_credentials_explicit_env_id(self):
        os.environ["OPENAI_API_KEY"] = "env-openai-key"

        credentials = resolve_provider_credentials(
            "openai",
            storage=self.storage,
            credential_id="openai:llm:env",
        )

        self.assertEqual(credentials.source, "env")
        self.assertEqual(credentials.api_key, "env-openai-key")
        self.assertEqual(credentials.stable_credential_id, "openai:llm:env")

    def test_resolve_provider_credentials_preserves_base_url_when_key_missing(self):
        self.storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted="",
            base_url="https://custom-openai.example/v1",
            instance_id="missing-key",
            label="OpenAI Missing Key",
        )

        credentials = resolve_provider_credentials(
            "openai",
            storage=self.storage,
            credential_id="openai:llm:instance:missing-key",
        )

        self.assertIsNone(credentials.api_key)
        self.assertFalse(credentials.configured)
        self.assertEqual(credentials.error, "credential_key_missing")
        self.assertEqual(credentials.base_url, "https://custom-openai.example/v1")

    def test_resolve_provider_credentials_preserves_base_url_when_decrypt_fails(self):
        self.storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted="not-a-valid-ciphertext",
            base_url="https://broken-openai.example/v1",
            instance_id="broken-key",
            label="OpenAI Broken Key",
        )

        credentials = resolve_provider_credentials(
            "openai",
            storage=self.storage,
            credential_id="openai:llm:instance:broken-key",
        )

        self.assertIsNone(credentials.api_key)
        self.assertFalse(credentials.configured)
        self.assertEqual(credentials.error, "decrypt_failed")
        self.assertEqual(credentials.base_url, "https://broken-openai.example/v1")

    def test_resolve_provider_credentials_unknown_provider_does_not_crash(self):
        """Unknown provider names should return an unconfigured runtime instead of crashing."""
        credentials = resolve_provider_credentials("unknown-provider", storage=self.storage)

        self.assertEqual(credentials.provider, "unknown-provider")
        self.assertIsNone(credentials.api_key)
        self.assertIsNone(credentials.base_url)
        self.assertFalse(credentials.configured)
        self.assertEqual(credentials.source, "missing")

    def test_diagnose_script_detects_token_key_from_project_dotenv(self):
        from ai_actuarial.services import token_encryption as token_encryption_module
        from scripts.diagnose_embedding_runtime import _token_encryption_key_configured

        fake_project_root = Path(self.temp_dir) / "dotenv-project"
        fake_project_root.mkdir()
        dotenv_key = Fernet.generate_key().decode()
        (fake_project_root / ".env").write_text(
            f"TOKEN_ENCRYPTION_KEY={dotenv_key}\n",
            encoding="utf-8",
        )
        original_project_root = token_encryption_module.PROJECT_ROOT
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        TokenEncryption._instance = None
        try:
            token_encryption_module.PROJECT_ROOT = fake_project_root
            self.assertTrue(_token_encryption_key_configured())
        finally:
            token_encryption_module.PROJECT_ROOT = original_project_root
            TokenEncryption._instance = None


if __name__ == "__main__":
    unittest.main()

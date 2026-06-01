#!/usr/bin/env python3
"""Tests for RAG runtime configuration unification."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.embeddings import EmbeddingGenerator
from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.storage import Storage


class TestRagRuntime(unittest.TestCase):
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

    def test_rag_config_from_yaml_prefers_db_provider_credentials(self):
        yaml_config = {
            "ai_config": {
                "embeddings": {
                    "provider": "siliconflow",
                    "model": "BAAI/bge-m3",
                    "batch_size": 16,
                    "cache_enabled": False,
                    "similarity_threshold": 0.55,
                }
            },
            "rag_config": {
                "max_chunk_tokens": 900,
                "min_chunk_tokens": 120,
                "index_type": "HNSW",
            },
        }
        encrypted = TokenEncryption().encrypt("db-siliconflow-key")
        self.storage.upsert_llm_provider(
            provider="siliconflow",
            api_key_encrypted=encrypted,
            base_url="https://custom.siliconflow.test/v1",
        )

        config = RAGConfig.from_yaml(yaml_config, storage=self.storage)

        self.assertEqual(config.embedding_provider, "siliconflow")
        self.assertEqual(config.embedding_model, "BAAI/bge-m3")
        self.assertEqual(config.embedding_batch_size, 16)
        self.assertFalse(config.embedding_cache_enabled)
        self.assertEqual(config.similarity_threshold, 0.55)
        self.assertEqual(config.index_type, "HNSW")
        self.assertEqual(config.api_key, "db-siliconflow-key")
        self.assertEqual(config.api_base_url, "https://custom.siliconflow.test/v1")
        self.assertEqual(config.openai_api_key, "db-siliconflow-key")
        self.assertEqual(config.credential_source, "db")
        self.assertTrue(config.credential_configured)
        self.assertEqual(config.credential_error, "")

    def test_rag_config_caps_qwen_batch_size_from_yaml(self):
        yaml_config = {
            "ai_config": {
                "embeddings": {
                    "provider": "qwen",
                    "model": "text-embedding-v3",
                    "batch_size": 64,
                }
            }
        }

        with self.assertLogs("ai_actuarial.rag.config", level="WARNING") as logs:
            config = RAGConfig.from_yaml(yaml_config, storage=self.storage)

        self.assertEqual(config.embedding_provider, "qwen")
        self.assertEqual(config.embedding_batch_size_configured, 64)
        self.assertEqual(config.embedding_batch_size, 10)
        self.assertEqual(config.embedding_config_source, "sites.yaml")
        self.assertEqual(
            config.embedding_batch_size_limit_reason,
            "provider_model_limit:qwen:text-embedding-v3",
        )
        self.assertIn("configured=64 effective=10", "\n".join(logs.output))
        self.assertIn("source='sites.yaml'", "\n".join(logs.output))

    def test_rag_config_caps_qwen_batch_size_from_env(self):
        os.environ["RAG_EMBEDDING_PROVIDER"] = "qwen"
        os.environ["RAG_EMBEDDING_MODEL"] = "text-embedding-v3"
        os.environ["RAG_EMBEDDING_BATCH_SIZE"] = "64"

        config = RAGConfig.from_env()

        self.assertEqual(config.embedding_provider, "qwen")
        self.assertEqual(config.embedding_batch_size_configured, 64)
        self.assertEqual(config.embedding_batch_size, 10)
        self.assertEqual(config.embedding_config_source, "env")

    def test_rag_config_caps_qwen_similarity_threshold_from_yaml(self):
        yaml_config = {
            "ai_config": {
                "embeddings": {
                    "provider": "qwen",
                    "model": "text-embedding-v3",
                    "batch_size": 10,
                    "similarity_threshold": 0.4,
                }
            }
        }

        with self.assertLogs("ai_actuarial.rag.config", level="WARNING") as logs:
            config = RAGConfig.from_yaml(yaml_config, storage=self.storage)

        self.assertEqual(config.similarity_threshold_configured, 0.4)
        self.assertEqual(config.similarity_threshold, 0.02)
        self.assertEqual(
            config.similarity_threshold_limit_reason,
            "provider_model_limit:qwen:text-embedding-v3",
        )
        self.assertIn("Similarity threshold configured=0.4 effective=0.02", "\n".join(logs.output))

    def test_rag_config_defaults_qwen_similarity_threshold_from_yaml(self):
        yaml_config = {
            "ai_config": {
                "embeddings": {
                    "provider": "qwen",
                    "model": "text-embedding-v3",
                    "batch_size": 10,
                }
            }
        }

        config = RAGConfig.from_yaml(yaml_config, storage=self.storage)

        self.assertEqual(config.similarity_threshold_configured, 0.02)
        self.assertEqual(config.similarity_threshold, 0.02)
        self.assertEqual(config.similarity_threshold_limit_reason, "")

    def test_rag_config_env_similarity_threshold_overrides_yaml(self):
        yaml_config = {
            "ai_config": {
                "embeddings": {
                    "provider": "openai",
                    "model": "text-embedding-3-large",
                    "batch_size": 10,
                    "similarity_threshold": 0.55,
                }
            }
        }
        os.environ["RAG_SIMILARITY_THRESHOLD"] = "0.62"

        config = RAGConfig.from_yaml(yaml_config, storage=self.storage)

        self.assertEqual(config.similarity_threshold_configured, 0.62)
        self.assertEqual(config.similarity_threshold, 0.62)

    def test_rag_config_defaults_qwen_similarity_threshold_from_env(self):
        os.environ["RAG_EMBEDDING_PROVIDER"] = "qwen"
        os.environ["RAG_EMBEDDING_MODEL"] = "text-embedding-v3"

        config = RAGConfig.from_env()

        self.assertEqual(config.similarity_threshold_configured, 0.02)
        self.assertEqual(config.similarity_threshold, 0.02)
        self.assertEqual(config.similarity_threshold_limit_reason, "")

    def test_rag_config_caps_qwen_similarity_threshold_from_env(self):
        os.environ["RAG_EMBEDDING_PROVIDER"] = "qwen"
        os.environ["RAG_EMBEDDING_MODEL"] = "text-embedding-v3"
        os.environ["RAG_SIMILARITY_THRESHOLD"] = "0.4"

        config = RAGConfig.from_env()

        self.assertEqual(config.similarity_threshold_configured, 0.4)
        self.assertEqual(config.similarity_threshold, 0.02)
        self.assertEqual(config.embedding_config_source, "env")

    def test_rag_config_keeps_openai_similarity_threshold(self):
        config = RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
            similarity_threshold=0.4,
        )

        self.assertEqual(config.similarity_threshold_configured, 0.4)
        self.assertEqual(config.similarity_threshold, 0.4)
        self.assertEqual(config.similarity_threshold_limit_reason, "")

    def test_rag_config_keeps_other_qwen_similarity_threshold(self):
        config = RAGConfig(
            embedding_provider="qwen",
            embedding_model="qwen3-vl-embedding",
            similarity_threshold=0.4,
        )

        self.assertEqual(config.similarity_threshold_configured, 0.4)
        self.assertEqual(config.similarity_threshold, 0.4)
        self.assertEqual(config.similarity_threshold_limit_reason, "")

    def test_rag_config_rejects_invalid_configured_qwen_similarity_threshold(self):
        config = RAGConfig(
            embedding_provider="qwen",
            embedding_model="text-embedding-v3",
            similarity_threshold=1.5,
            api_key="runtime-key",
            credential_configured=True,
        )

        with self.assertRaisesRegex(ValueError, "similarity_threshold must be between 0 and 1"):
            config.validate()

    def test_rag_config_keeps_other_qwen_models_uncapped(self):
        config = RAGConfig(
            embedding_provider="qwen",
            embedding_model="qwen3-vl-embedding",
            embedding_batch_size=64,
        )

        self.assertEqual(config.embedding_batch_size_configured, 64)
        self.assertEqual(config.embedding_batch_size, 64)
        self.assertEqual(config.embedding_batch_size_limit_reason, "")

    def test_rag_config_keeps_non_qwen_batch_size(self):
        config = RAGConfig(embedding_provider="openai", embedding_batch_size=64)

        self.assertEqual(config.embedding_batch_size_configured, 64)
        self.assertEqual(config.embedding_batch_size, 64)

    def test_rag_config_from_env_uses_provider_default_base_url(self):
        os.environ["RAG_EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["SILICONFLOW_API_KEY"] = "env-siliconflow-key"

        config = RAGConfig.from_env()

        self.assertEqual(config.embedding_provider, "siliconflow")
        self.assertEqual(config.api_key, "env-siliconflow-key")
        self.assertEqual(config.api_base_url, "https://api.siliconflow.cn/v1")
        self.assertEqual(config.credential_source, "env")
        self.assertTrue(config.credential_configured)

    @patch("ai_actuarial.rag.embeddings.OpenAI")
    def test_embedding_generator_uses_openai_compatible_runtime(self, mock_openai):
        config = RAGConfig(
            embedding_provider="siliconflow",
            embedding_model="BAAI/bge-m3",
            api_key="runtime-key",
            api_base_url="https://custom.siliconflow.test/v1",
            openai_timeout=45,
        )

        generator = EmbeddingGenerator(config)

        mock_openai.assert_called_once_with(
            api_key="runtime-key",
            base_url="https://custom.siliconflow.test/v1",
            timeout=45,
        )
        self.assertIsNotNone(generator.openai_client)

    @patch("ai_actuarial.rag.embeddings.OpenAI")
    def test_qwen_embedding_generator_batches_at_provider_limit(self, mock_openai):
        config = RAGConfig(
            embedding_provider="qwen",
            embedding_model="text-embedding-v3",
            embedding_batch_size=64,
            embedding_cache_enabled=False,
            api_key="runtime-key",
        )
        generator = EmbeddingGenerator(config)
        texts = [f"chunk-{i}" for i in range(25)]

        with patch.object(
            generator,
            "_generate_openai_batch_with_retry",
            side_effect=lambda batch: [[float(len(batch))] for _ in batch],
        ) as mock_batch:
            result = generator.generate_embeddings(texts)

        self.assertEqual([len(call.args[0]) for call in mock_batch.call_args_list], [10, 10, 5])
        self.assertEqual(len(result), 25)
        mock_openai.assert_called_once()

    def test_embedding_generator_missing_key_reports_runtime_context(self):
        config = RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
            credential_source="missing",
            credential_id="openai:llm:instance:missing",
            stable_credential_id="openai:llm:instance:missing",
            credential_label="Missing OpenAI",
            credential_error="credential_not_found",
        )

        with self.assertRaisesRegex(Exception, "credential_not_found"):
            EmbeddingGenerator(config)

    def test_embedding_generator_normalizes_local_provider(self):
        config = RAGConfig(
            embedding_provider=" Local ",
            embedding_model="local-model",
            embedding_cache_enabled=False,
        )

        generator = EmbeddingGenerator(config)

        self.assertEqual(generator.provider, "local")
        self.assertIsNone(generator.openai_client)
        with patch.object(
            EmbeddingGenerator,
            "_generate_local_embeddings",
            return_value=[[0.1, 0.2, 0.3]],
        ) as mock_local:
            result = generator.generate_embeddings(["hello"])

        mock_local.assert_called_once_with(["hello"])
        self.assertEqual(result, [[0.1, 0.2, 0.3]])


if __name__ == "__main__":
    unittest.main()

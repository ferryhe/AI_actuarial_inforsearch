#!/usr/bin/env python3
"""Tests for RAG runtime configuration unification."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.embeddings import EmbeddingGenerator
from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.storage import Storage


class TestRagRuntime(unittest.TestCase):
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

    def test_rag_config_from_env_uses_provider_default_base_url(self):
        os.environ["RAG_EMBEDDING_PROVIDER"] = "siliconflow"
        os.environ["SILICONFLOW_API_KEY"] = "env-siliconflow-key"

        config = RAGConfig.from_env()

        self.assertEqual(config.embedding_provider, "siliconflow")
        self.assertEqual(config.api_key, "env-siliconflow-key")
        self.assertEqual(config.api_base_url, "https://api.siliconflow.cn/v1")

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

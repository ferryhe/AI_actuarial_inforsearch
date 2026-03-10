#!/usr/bin/env python3
"""Tests for catalog runtime provider resolution."""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_actuarial.catalog_llm import catalog_with_openai


class TestCatalogRuntime(unittest.TestCase):
    def test_catalog_with_openai_uses_runtime_provider_kwargs(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"summary":"Summary","keywords":["alpha","beta"],'
                            '"category":"Other","suggested_title":"Runtime Title"}'
                        )
                    )
                )
            ]
        )
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = catalog_with_openai(
                title="Document",
                content="Sample content",
                provider="deepseek",
                model="deepseek-chat",
                api_key="runtime-key",
                base_url="https://api.deepseek.com/v1",
            )

        mock_openai.OpenAI.assert_called_once_with(
            api_key="runtime-key",
            base_url="https://api.deepseek.com/v1",
        )
        self.assertEqual(result.model, "deepseek-chat")
        self.assertEqual(result.summary, "Summary")
        self.assertEqual(result.suggested_title, "Runtime Title")

    def test_catalog_with_openai_uses_runtime_timeout_seconds(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"summary":"Summary","keywords":["alpha"],"category":"Other"}'
                    )
                )
            ]
        )
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_runtime = SimpleNamespace(
            provider="deepseek",
            model="deepseek-chat",
            api_key="runtime-key",
            base_url="https://api.deepseek.com/v1",
            raw_config={"timeout_seconds": 12},
        )

        with patch.dict(sys.modules, {"openai": mock_openai}), patch(
            "ai_actuarial.catalog_llm.resolve_ai_function_runtime",
            return_value=mock_runtime,
        ):
            catalog_with_openai(
                title="Document",
                content="Sample content",
                provider="deepseek",
                model="deepseek-chat",
                api_key="runtime-key",
                base_url="https://api.deepseek.com/v1",
            )

        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs["timeout"], 12.0)


if __name__ == "__main__":
    unittest.main()

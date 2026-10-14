#!/usr/bin/env python3
"""Tests for catalog runtime provider resolution."""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_actuarial.catalog_llm import catalog_with_openai, confirm_category_for_summary


def bilingual_response() -> str:
    return (
        '{"bilingual_metadata":{'
        '"zh":{"title":"运行标题","summary":"中文摘要","category":"Other",'
        '"keywords":["中文关键词"]},'
        '"en":{"title":"Runtime Title","summary":"Summary","category":"Other",'
        '"keywords":["alpha","beta"]}}}'
    )


class TestCatalogRuntime(unittest.TestCase):
    def test_catalog_with_openai_uses_runtime_provider_kwargs(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=(bilingual_response())))]
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
                base_url="https://api.deepseek.com",
            )

        mock_openai.OpenAI.assert_called_once_with(
            api_key="runtime-key",
            base_url="https://api.deepseek.com",
        )
        self.assertEqual(result.model, "deepseek-chat")
        self.assertEqual(result.summary, "Summary")
        self.assertEqual(result.suggested_title, "Runtime Title")
        self.assertEqual(result.bilingual_metadata["zh"]["summary"], "中文摘要")
        self.assertEqual(result.bilingual_metadata["en"]["keywords"], ["alpha", "beta"])
        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs["temperature"], 0.2)

    def test_catalog_with_openai_uses_runtime_timeout_seconds(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=bilingual_response()))]
        )
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_runtime = SimpleNamespace(
            provider="deepseek",
            model="deepseek-chat",
            api_key="runtime-key",
            base_url="https://api.deepseek.com",
            raw_config={"timeout_seconds": 12},
        )

        with (
            patch.dict(sys.modules, {"openai": mock_openai}),
            patch(
                "ai_actuarial.catalog_llm.resolve_ai_function_runtime",
                return_value=mock_runtime,
            ),
        ):
            catalog_with_openai(
                title="Document",
                content="Sample content",
                provider="deepseek",
                model="deepseek-chat",
                api_key="runtime-key",
                base_url="https://api.deepseek.com",
            )

        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs["timeout"], 12.0)

    def test_catalog_omits_temperature_for_openai_gpt5(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=bilingual_response()))]
        )
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_runtime = SimpleNamespace(
            provider="openai",
            model="gpt-5.6-luna",
            api_key="runtime-key",
            base_url=None,
            raw_config={},
        )

        with (
            patch.dict(sys.modules, {"openai": mock_openai}),
            patch(
                "ai_actuarial.catalog_llm.resolve_ai_function_runtime",
                return_value=mock_runtime,
            ),
        ):
            catalog_with_openai(title="Document", content="Sample content")

        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertNotIn("temperature", kwargs)

    def test_catalog_rejects_missing_language_package(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"bilingual_metadata":{"en":{"title":"Title","summary":"Summary",'
                            '"category":"Other","keywords":["keyword"]}}}'
                        )
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
            base_url=None,
            raw_config={},
        )
        with (
            patch.dict(sys.modules, {"openai": mock_openai}),
            patch(
                "ai_actuarial.catalog_llm.resolve_ai_function_runtime", return_value=mock_runtime
            ),
            self.assertRaisesRegex(ValueError, "missing the zh metadata package"),
        ):
            catalog_with_openai(title="Document", content="Sample content")

    def test_catalog_rejects_different_category_keys_between_languages(self):
        mock_client = MagicMock()
        response = bilingual_response().replace(
            '"en":{"title":"Runtime Title","summary":"Summary","category":"Other"',
            '"en":{"title":"Runtime Title","summary":"Summary","category":"Life"',
        )
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response))]
        )
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_runtime = SimpleNamespace(
            provider="deepseek",
            model="deepseek-chat",
            api_key="runtime-key",
            base_url=None,
            raw_config={},
        )
        with (
            patch.dict(sys.modules, {"openai": mock_openai}),
            patch(
                "ai_actuarial.catalog_llm.resolve_ai_function_runtime", return_value=mock_runtime
            ),
            self.assertRaisesRegex(ValueError, "different canonical categories"),
        ):
            catalog_with_openai(title="Document", content="Sample content")

    def test_category_confirmation_omits_temperature_for_openai_gpt5(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"belongs":true}'))]
        )
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_runtime = SimpleNamespace(
            provider="openai",
            model="gpt-5.6-luna",
            api_key="runtime-key",
            base_url=None,
            raw_config={},
        )

        with (
            patch.dict(sys.modules, {"openai": mock_openai}),
            patch(
                "ai_actuarial.catalog_llm.resolve_ai_function_runtime",
                return_value=mock_runtime,
            ),
        ):
            result = confirm_category_for_summary(
                summary="Summary",
                candidate_category="Other",
                category_terms=[],
            )

        self.assertTrue(result)
        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertNotIn("temperature", kwargs)


if __name__ == "__main__":
    unittest.main()

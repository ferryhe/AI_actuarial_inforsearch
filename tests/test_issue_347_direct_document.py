from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ai_actuarial.api.services.chat import (
    _chunks_for_llm,
    _estimated_message_tokens,
    _prepare_budgeted_document_chunks,
)
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import LLMContextLengthError
from ai_actuarial.chatbot.llm import LLMClient
from ai_actuarial.chatbot.prompts import build_full_prompt


class CharacterTokenizer:
    def count_tokens(self, text: str, model: str | None = None) -> int:
        return len(text)


def _config(**overrides):
    values = {
        "model": "active-model",
        "max_context_tokens": 4000,
        "max_tokens": 120,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("content", ["long document " * 400, "精算监管要求" * 700])
def test_direct_document_budget_counts_complete_prompt_and_keeps_untrusted_boundary(
    content,
) -> None:
    chunks, notice, bounded_history = _prepare_budgeted_document_chunks(
        llm_client=CharacterTokenizer(),
        config=_config(),
        query="Explain this file",
        mode="expert",
        conversation_history=[{"role": "assistant", "content": "earlier answer"}],
        document_content=content,
        document_filename="report.md",
        document_file_url="https://example.test/report.md",
        document_sources=[],
        document_title="Report",
    )

    assert chunks
    assert bounded_history == [{"role": "assistant", "content": "earlier answer"}]
    assert chunks[0]["metadata"]["untrusted_context"] is True
    assert notice["active_model"] == "active-model"
    assert notice["output_reserve"] == 120
    assert notice["estimated_prompt_tokens"] + notice["output_reserve"] <= 4000
    assert notice["used_chars"] < notice["original_chars"]


def test_empty_direct_document_has_no_chunks() -> None:
    chunks, notice, bounded_history = _prepare_budgeted_document_chunks(
        llm_client=CharacterTokenizer(),
        config=_config(),
        query="Explain",
        mode="expert",
        conversation_history=[],
        document_content="",
        document_filename="empty.md",
        document_file_url="https://example.test/empty.md",
        document_sources=[{"content": "", "filename": "empty.md"}],
        document_title="Empty",
    )

    assert chunks == []
    assert bounded_history == []
    assert notice["original_chars"] == 0


def test_context_error_type_is_stable_and_safe() -> None:
    error = LLMContextLengthError("raw provider payload must not escape")
    assert error.code == "LLM_CONTEXT_LENGTH"
    assert str(error) == "The selected document is too large for the active AI model."


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_default_length_recovery_request_stays_inside_total_budget(mock_openai: Mock) -> None:
    provider_client = Mock()
    mock_openai.return_value = provider_client
    config = ChatbotConfig(
        api_key="test-key",
        model="gpt-5.4-mini",
        max_context_tokens=8000,
        max_tokens=1000,
        max_retries=3,
        retry_delay=0,
        rate_limit_rpm=60_000,
        length_recovery_enabled=True,
        length_recovery_max_tokens=4000,
        _apply_env_defaults=False,
    )
    client = LLMClient(config)
    chunks, notice, bounded_history = _prepare_budgeted_document_chunks(
        llm_client=client,
        config=config,
        query="Explain this file",
        mode="expert",
        conversation_history=[],
        document_content="long actuarial document " * 4000,
        document_filename="long.md",
        document_file_url="https://example.test/long.md",
        document_sources=[],
        document_title="Long document",
    )
    messages = build_full_prompt(
        mode="expert",
        retrieved_chunks=_chunks_for_llm(chunks),
        query="Explain this file",
        conversation_history=bounded_history,
    )
    provider_client.chat.completions.create.side_effect = [
        SimpleNamespace(
            id="first",
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(content="", refusal=None),
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            id="recovered",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="Recovered", refusal=None),
                )
            ],
            usage=None,
        ),
    ]

    assert client.generate(messages) == "Recovered"
    recovery_request = provider_client.chat.completions.create.call_args_list[1].kwargs
    assert notice["output_reserve"] == recovery_request["max_completion_tokens"] == 4000
    assert (
        _estimated_message_tokens(client, recovery_request["messages"], config.model)
        == notice["estimated_prompt_tokens"]
    )
    assert notice["estimated_prompt_tokens"] + notice["output_reserve"] <= 8000


def test_disabled_length_recovery_reserves_only_normal_output() -> None:
    chunks, notice, bounded_history = _prepare_budgeted_document_chunks(
        llm_client=CharacterTokenizer(),
        config=_config(
            max_context_tokens=4000,
            max_tokens=120,
            length_recovery_enabled=False,
            length_recovery_max_tokens=2000,
        ),
        query="Explain",
        mode="expert",
        conversation_history=[],
        document_content="bounded text " * 200,
        document_filename="bounded.md",
        document_file_url="https://example.test/bounded.md",
        document_sources=[],
    )

    assert chunks
    assert bounded_history == []
    assert notice["output_reserve"] == 120

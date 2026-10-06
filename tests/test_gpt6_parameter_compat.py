from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from ai_actuarial.ai_runtime import AIFunctionRuntime
from ai_actuarial.api.services.weekly_explanations import ChatRuntimeWeeklyExplanationGenerator
from ai_actuarial.catalog_llm import catalog_with_openai, confirm_category_for_summary
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import LLMException
from ai_actuarial.chatbot.llm import (
    LLMClient,
    _compatible_reasoning_effort,
    _supports_reasoning_effort,
    _uses_default_temperature_only,
    _uses_max_completion_tokens,
)


def _completion_client(content: str = "response") -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=1),
    )
    return client


@pytest.mark.parametrize(
    ("provider", "model", "token_key", "temperature"),
    [
        ("openai", "gpt-5.4-mini", "max_completion_tokens", None),
        ("azure_openai", "team-gpt5-deployment", "max_completion_tokens", None),
        ("openai", "gpt-6", "max_completion_tokens", None),
        ("openai", "gpt-6.1", "max_completion_tokens", None),
        ("openai", "gpt-6-2026-10-07", "max_completion_tokens", None),
        ("openai", "vendor/gpt-6.1", "max_completion_tokens", None),
        ("azure_openai", "gpt-6.1", "max_completion_tokens", None),
        ("azure_openai", "team-gpt-6-luna-deployment", "max_completion_tokens", None),
        ("openai", "o3", "max_completion_tokens", 0.37),
        ("openai", "gpt-4.1", "max_tokens", 0.37),
        ("azure_openai", "team-gpt-60-deployment", "max_tokens", 0.37),
        ("openai", "gpt-60", "max_tokens", 0.37),
        ("openai", "gpt-6foo", "max_tokens", 0.37),
        ("deepseek", "gpt-6-luna", "max_tokens", 0.37),
    ],
)
def test_chat_generate_gpt6_parameter_matrix(
    provider: str, model: str, token_key: str, temperature: float | None
) -> None:
    client = _completion_client()
    with patch("openai.OpenAI", return_value=client):
        llm = LLMClient(
            ChatbotConfig(
                llm_provider=provider,
                model=model,
                api_key="test-key",
                max_tokens=321,
                temperature=0.37,
                _apply_env_defaults=False,
            )
        )
        llm.generate([{"role": "user", "content": "test"}])

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs[token_key] == 321
    if temperature is None:
        assert "temperature" not in kwargs
    else:
        assert kwargs["temperature"] == temperature
    if token_key == "max_completion_tokens":
        assert "max_tokens" not in kwargs
    else:
        assert "max_completion_tokens" not in kwargs


@pytest.mark.parametrize("function", [catalog_with_openai, confirm_category_for_summary])
@pytest.mark.parametrize(
    ("provider", "model", "expected_temperature"),
    [
        ("openai", "gpt-5.4-mini", None),
        ("openai", "gpt-6.1", None),
        ("azure_openai", "gpt-6.1", None),
        ("azure_openai", "team-gpt-6-luna-deployment", None),
        ("openai", "gpt-4.1", 0.2),
        ("openai", "gpt-6foo", 0.2),
        ("azure_openai", "team-gpt-60-deployment", 0.2),
        ("deepseek", "gpt-6-luna", 0.2),
    ],
)
def test_catalog_and_category_temperature_matrix(
    function, provider: str, model: str, expected_temperature: float | None
) -> None:
    client = _completion_client('{"belongs":true,"summary":"Summary"}')
    runtime = SimpleNamespace(
        provider=provider,
        model=model,
        api_key="test-key",
        base_url=None,
        raw_config={},
    )
    openai_module = MagicMock()
    openai_module.OpenAI.return_value = client
    kwargs = (
        {"title": "Document", "content": "Content"}
        if function is catalog_with_openai
        else {"summary": "Summary", "candidate_category": "Other", "category_terms": []}
    )
    with (
        patch.dict(sys.modules, {"openai": openai_module}),
        patch("ai_actuarial.catalog_llm.resolve_ai_function_runtime", return_value=runtime),
    ):
        function(**kwargs)

    request = client.chat.completions.create.call_args.kwargs
    if expected_temperature is None:
        assert "temperature" not in request
    else:
        expected = expected_temperature if function is catalog_with_openai else 0.0
        assert request["temperature"] == expected
    assert "max_tokens" not in request
    assert "max_completion_tokens" not in request


@pytest.mark.parametrize(
    ("model", "expected_temperature"),
    [("team-gpt5-deployment", 0.2), ("gpt-5.4-mini", None)],
)
def test_catalog_keeps_azure_gpt5_temperature_behavior(
    model: str, expected_temperature: float | None
) -> None:
    client = _completion_client('{"summary":"Summary"}')
    runtime = SimpleNamespace(
        provider="azure_openai",
        model=model,
        api_key="test-key",
        base_url=None,
        raw_config={},
    )
    openai_module = MagicMock()
    openai_module.OpenAI.return_value = client
    with (
        patch.dict(sys.modules, {"openai": openai_module}),
        patch("ai_actuarial.catalog_llm.resolve_ai_function_runtime", return_value=runtime),
    ):
        catalog_with_openai(title="Document", content="Content")

    request = client.chat.completions.create.call_args.kwargs
    if expected_temperature is None:
        assert "temperature" not in request
    else:
        assert request["temperature"] == expected_temperature


@pytest.mark.parametrize(
    ("provider", "model", "max_completion_tokens", "default_temperature"),
    [
        ("openai", "gpt-6", True, True),
        ("openai", "vendor/gpt-6.1", True, True),
        ("azure_openai", "team-gpt-6-luna-deployment", True, True),
        ("azure_openai", "team-gpt-60-deployment", False, False),
        ("openai", "gpt-6foo", False, False),
        ("deepseek", "gpt-6.1", False, False),
    ],
)
def test_openai_capability_helpers_normalize_only_supported_gpt6_names(
    provider: str, model: str, max_completion_tokens: bool, default_temperature: bool
) -> None:
    assert _uses_max_completion_tokens(provider, model) is max_completion_tokens
    assert _uses_default_temperature_only(provider, model) is default_temperature


@pytest.mark.parametrize(
    ("provider", "model", "configured_effort", "expected"),
    [
        ("openai", "gpt-6.1", "low", None),
        ("azure_openai", "team-gpt-6-luna-deployment", "high", None),
        ("openai", "gpt-5.4-mini", "low", "low"),
        ("openai", "o3", "medium", "medium"),
    ],
)
def test_reasoning_effort_capability_excludes_gpt6_only(
    provider: str, model: str, configured_effort: str, expected: str | None
) -> None:
    assert _supports_reasoning_effort(provider, model) is (expected is not None)
    assert _compatible_reasoning_effort(provider, model, configured_effort) == expected


def test_weekly_shared_llm_builder_uses_gpt6_compatible_parameters() -> None:
    client = _completion_client("weekly response")
    client.with_options.return_value = client
    runtime = AIFunctionRuntime(
        function_name="weekly_explanation",
        provider="openai",
        model="gpt-6-luna",
        raw_config={"temperature": 0.7, "max_tokens": 456},
        api_key="test-key",
        configured=True,
    )
    with patch("openai.OpenAI", return_value=client):
        result = ChatRuntimeWeeklyExplanationGenerator(None, runtime=runtime).generate(
            [{"role": "user", "content": "explain"}], timeout_seconds=2
        )

    assert result == "weekly response"
    request = client.chat.completions.create.call_args.kwargs
    assert request["max_completion_tokens"] == 456
    assert "max_tokens" not in request
    assert "temperature" not in request


def test_gpt6_recovery_bad_request_does_not_retry_or_fall_back_to_legacy_parameters() -> None:
    client = _completion_client("")
    client.chat.completions.create.side_effect = [
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content=""))],
            usage=SimpleNamespace(total_tokens=1),
        ),
        openai.BadRequestError(
            "Unsupported parameter: max_completion_tokens",
            response=httpx.Response(
                400,
                request=httpx.Request("POST", "https://api.openai.test/v1/chat/completions"),
            ),
            body={"error": {"code": "unsupported_parameter"}},
        ),
    ]
    with patch("openai.OpenAI", return_value=client):
        llm = LLMClient(
            ChatbotConfig(
                llm_provider="openai",
                model="gpt-6.1",
                api_key="test-key",
                temperature=0.37,
                max_retries=3,
                max_tokens=321,
                length_recovery_enabled=True,
                length_recovery_max_tokens=654,
                _apply_env_defaults=False,
            )
        )
        with pytest.raises(LLMException, match="length recovery request was rejected"):
            llm.generate([{"role": "user", "content": "test"}])

    assert client.chat.completions.create.call_count == 2
    initial_request, recovery_request = (
        call.kwargs for call in client.chat.completions.create.call_args_list
    )
    for request in (initial_request, recovery_request):
        assert "max_tokens" not in request
        assert "temperature" not in request
    assert initial_request["max_completion_tokens"] == 321
    assert recovery_request["max_completion_tokens"] == 654

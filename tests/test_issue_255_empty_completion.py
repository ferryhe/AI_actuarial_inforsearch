from __future__ import annotations

import logging
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import httpx
import openai

from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import LLMException
from ai_actuarial.chatbot.llm import LLMClient


def _response(
    content=...,
    *,
    finish_reason: str | None = "stop",
    refusal=None,
    choices: bool = True,
    message: bool = True,
    response_id: str = "chatcmpl-safe-id",
):
    if not choices:
        response_choices = []
    elif not message:
        response_choices = [SimpleNamespace(finish_reason=finish_reason)]
    else:
        message_values = {"refusal": refusal}
        if content is not ...:
            message_values["content"] = content
        response_choices = [
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(**message_values),
            )
        ]
    return SimpleNamespace(
        id=response_id,
        choices=response_choices,
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=60),
        ),
    )


def _client(mock_openai: Mock, **config_overrides) -> tuple[LLMClient, Mock]:
    provider_client = Mock()
    mock_openai.return_value = provider_client
    values = {
        "api_key": "fake-key",
        "model": "gpt-5.4-mini",
        "max_tokens": 1000,
        "max_retries": 3,
        "retry_delay": 0,
        "rate_limit_rpm": 60_000,
        "_apply_env_defaults": False,
    }
    values.update(config_overrides)
    return LLMClient(ChatbotConfig(**values)), provider_client


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_extracts_normal_and_structured_text_content(mock_openai: Mock) -> None:
    client, provider_client = _client(mock_openai)
    provider_client.chat.completions.create.side_effect = [
        _response("plain response"),
        _response(
            [
                {"type": "text", "text": "structured "},
                SimpleNamespace(type="text", text="response"),
                {"type": "image", "image_url": "ignored"},
            ]
        ),
    ]

    assert client.generate([{"role": "user", "content": "first"}]) == "plain response"
    assert client.generate([{"role": "user", "content": "second"}]) == "structured response"


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_length_empty_runs_exactly_one_bounded_model_aware_recovery(
    mock_openai: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, provider_client = _client(
        mock_openai,
        length_recovery_max_tokens=3200,
        length_recovery_reasoning_effort="low",
    )
    provider_client.chat.completions.create.side_effect = [
        _response("", finish_reason="length"),
        _response("recovered answer"),
    ]
    messages = [{"role": "user", "content": "bounded document prompt"}]
    original_messages = deepcopy(messages)

    with caplog.at_level(logging.INFO, logger="ai_actuarial.chatbot.llm"):
        assert client.generate(messages) == "recovered answer"
    assert provider_client.chat.completions.create.call_count == 2
    first_kwargs = provider_client.chat.completions.create.call_args_list[0].kwargs
    recovery_kwargs = provider_client.chat.completions.create.call_args_list[1].kwargs
    assert first_kwargs["max_completion_tokens"] == 1000
    assert "reasoning_effort" not in first_kwargs
    assert recovery_kwargs["max_completion_tokens"] == 3200
    assert recovery_kwargs["reasoning_effort"] == "low"
    assert recovery_kwargs["messages"] is messages
    assert messages == original_messages
    assert any(
        "attempt=2" in record.getMessage() and "recovery=True" in record.getMessage()
        for record in caplog.records
    )


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_length_recovery_uses_compatible_budget_parameter_without_reasoning_effort(
    mock_openai: Mock,
) -> None:
    client, provider_client = _client(
        mock_openai,
        llm_provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.test",
        length_recovery_max_tokens=2400,
        length_recovery_reasoning_effort="low",
    )
    provider_client.chat.completions.create.side_effect = [
        _response(None, finish_reason="length"),
        _response("compatible recovery"),
    ]

    assert client.generate([{"role": "user", "content": "test"}]) == "compatible recovery"
    recovery_kwargs = provider_client.chat.completions.create.call_args_list[1].kwargs
    assert recovery_kwargs["max_tokens"] == 2400
    assert "max_completion_tokens" not in recovery_kwargs
    assert "reasoning_effort" not in recovery_kwargs


@pytest.mark.parametrize(
    ("model", "configured_effort", "expected_effort"),
    [
        ("gpt-5.1", "minimal", None),
        ("gpt-5.1", "low", "low"),
        ("gpt-5-pro", "low", None),
    ],
)
@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_length_recovery_omits_known_model_incompatible_reasoning_effort(
    mock_openai: Mock,
    model: str,
    configured_effort: str,
    expected_effort: str | None,
) -> None:
    client, provider_client = _client(
        mock_openai,
        model=model,
        length_recovery_reasoning_effort=configured_effort,
    )
    provider_client.chat.completions.create.side_effect = [
        _response("", finish_reason="length"),
        _response("compatible recovery"),
    ]

    assert client.generate([{"role": "user", "content": "test"}]) == "compatible recovery"
    recovery_kwargs = provider_client.chat.completions.create.call_args_list[1].kwargs
    if expected_effort is None:
        assert "reasoning_effort" not in recovery_kwargs
    else:
        assert recovery_kwargs["reasoning_effort"] == expected_effort


@pytest.mark.parametrize(
    ("model", "uses_reasoning_request"),
    [
        ("actuarial-gpt5-deployment", True),
        ("actuarial-gpt4-deployment", False),
        ("actuarial-chat-deployment", False),
    ],
)
@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_azure_deployment_name_uses_only_explicit_reasoning_family_hint(
    mock_openai: Mock,
    model: str,
    uses_reasoning_request: bool,
) -> None:
    client, provider_client = _client(
        mock_openai,
        llm_provider="azure_openai",
        model=model,
        length_recovery_reasoning_effort="low",
    )
    provider_client.chat.completions.create.side_effect = [
        _response("", finish_reason="length"),
        _response("compatible recovery"),
    ]

    assert client.generate([{"role": "user", "content": "test"}]) == "compatible recovery"
    recovery_kwargs = provider_client.chat.completions.create.call_args_list[1].kwargs
    if uses_reasoning_request:
        assert recovery_kwargs["max_completion_tokens"] == 4000
        assert recovery_kwargs["reasoning_effort"] == "low"
        assert "max_tokens" not in recovery_kwargs
        assert "temperature" not in recovery_kwargs
    else:
        assert recovery_kwargs["max_tokens"] == 4000
        assert "max_completion_tokens" not in recovery_kwargs
        assert "reasoning_effort" not in recovery_kwargs
        assert recovery_kwargs["temperature"] == 0.7


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_length_recovery_stops_after_one_unsuccessful_recovery(mock_openai: Mock) -> None:
    client, provider_client = _client(mock_openai)
    provider_client.chat.completions.create.side_effect = [
        _response("", finish_reason="length"),
        _response(None, finish_reason="length"),
        _response("must not be reached"),
    ]

    with pytest.raises(LLMException, match="remained empty after bounded recovery"):
        client.generate([{"role": "user", "content": "test"}])

    assert provider_client.chat.completions.create.call_count == 2


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_recovery_and_transient_retries_share_hard_provider_call_ceiling(
    mock_openai: Mock,
) -> None:
    client, provider_client = _client(mock_openai, max_retries=3)
    provider_client.chat.completions.create.side_effect = [
        _response("", finish_reason="length"),
        _response(choices=False),
        _response(None),
        _response("must not exceed provider call ceiling"),
    ]

    with pytest.raises(LLMException, match="empty or malformed after 3 attempts"):
        client.generate([{"role": "user", "content": "test"}])

    assert provider_client.chat.completions.create.call_count == 3


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_recovery_bad_request_preserves_compatibility_failure_without_budget_fallback(
    mock_openai: Mock,
) -> None:
    client, provider_client = _client(mock_openai, max_retries=3)
    request = httpx.Request("POST", "https://api.openai.test/v1/chat/completions")
    response = httpx.Response(400, request=request)
    recovery_error = openai.BadRequestError(
        "Unsupported parameter: reasoning_effort",
        response=response,
        body={"error": {"code": "unsupported_parameter"}},
    )
    provider_client.chat.completions.create.side_effect = [
        _response("", finish_reason="length"),
        recovery_error,
        _response("must not silently fall back to the original budget"),
    ]

    with pytest.raises(
        LLMException,
        match="length recovery request was rejected due to incompatible parameters",
    ) as exc_info:
        client.generate([{"role": "user", "content": "test"}])

    assert exc_info.value.__cause__ is recovery_error
    assert provider_client.chat.completions.create.call_count == 2
    recovery_kwargs = provider_client.chat.completions.create.call_args_list[1].kwargs
    assert recovery_kwargs["max_completion_tokens"] == 4000
    assert recovery_kwargs["reasoning_effort"] == "low"


@pytest.mark.parametrize(
    ("empty_response", "classification"),
    [
        (_response(choices=False), "missing_choices"),
        (_response(message=False), "missing_message"),
        (_response(...), "missing_content"),
        (_response(None), "null_content"),
        (_response(""), "empty_content"),
        (_response("   \n"), "whitespace_content"),
    ],
)
@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_transient_empty_classifications_retry_then_succeed(
    mock_openai: Mock,
    empty_response,
    classification: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, provider_client = _client(mock_openai)
    provider_client.chat.completions.create.side_effect = [
        empty_response,
        _response("success after transient empty"),
    ]

    with caplog.at_level(logging.WARNING, logger="ai_actuarial.chatbot.llm"):
        assert client.generate([{"role": "user", "content": "private prompt"}]) == (
            "success after transient empty"
        )

    assert provider_client.chat.completions.create.call_count == 2
    assert classification in caplog.text


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_transient_empty_exhausts_existing_attempt_ceiling(mock_openai: Mock) -> None:
    client, provider_client = _client(mock_openai, max_retries=2)
    provider_client.chat.completions.create.side_effect = [
        _response(choices=False),
        _response(None),
    ]

    with pytest.raises(LLMException, match="empty or malformed after 2 attempts") as exc_info:
        client.generate([{"role": "user", "content": "test"}])

    assert "Unexpected error" not in str(exc_info.value)
    assert provider_client.chat.completions.create.call_count == 2


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response(None, refusal="I cannot help"), "LLM response was refused"),
        (_response(None, finish_reason="content_filter"), "LLM response was blocked by content filtering"),
    ],
)
@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_refusal_and_content_filter_are_stable_non_retryable_errors(
    mock_openai: Mock,
    response,
    message: str,
) -> None:
    client, provider_client = _client(mock_openai)
    provider_client.chat.completions.create.return_value = response

    with pytest.raises(LLMException, match=message):
        client.generate([{"role": "user", "content": "test"}])

    assert provider_client.chat.completions.create.call_count == 1


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_empty_response_logs_only_safe_diagnostics(
    mock_openai: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, provider_client = _client(mock_openai, max_retries=1)
    provider_client.chat.completions.create.return_value = _response(
        None,
        response_id="chatcmpl-log-safe",
    )
    secret_prompt = "PRIVATE-DOCUMENT-TEXT-DO-NOT-LOG"

    with caplog.at_level(logging.WARNING, logger="ai_actuarial.chatbot.llm"):
        with pytest.raises(LLMException):
            client.generate([{"role": "user", "content": secret_prompt}])

    assert secret_prompt not in caplog.text
    assert "fake-key" not in caplog.text
    for expected in (
        "provider=openai",
        "model=gpt-5.4-mini",
        "finish_reason=stop",
        "attempt=1",
        "response_id=chatcmpl-log-safe",
        "prompt_tokens=120",
        "completion_tokens=80",
        "total_tokens=200",
        "reasoning_tokens=60",
        "recovery=False",
    ):
        assert expected in caplog.text


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_existing_llm_exception_is_not_rewrapped(mock_openai: Mock) -> None:
    client, provider_client = _client(mock_openai)
    provider_client.chat.completions.create.return_value = _response("unused")

    with pytest.raises(LLMException) as exc_info:
        client.generate([{"role": "user", "content": "test"}], stream=True)

    assert str(exc_info.value) == "Streaming not yet supported"


@patch("ai_actuarial.chatbot.llm.openai.OpenAI")
def test_existing_api_error_retry_behavior_is_preserved(mock_openai: Mock) -> None:
    client, provider_client = _client(mock_openai, max_retries=2)
    provider_client.chat.completions.create.side_effect = [
        openai.APIError(
            "provider failed",
            httpx.Request("POST", "https://api.openai.test/v1/chat/completions"),
            body=None,
        ),
        _response("success after API error"),
    ]

    assert client.generate([{"role": "user", "content": "test"}]) == (
        "success after API error"
    )
    assert provider_client.chat.completions.create.call_count == 2


def test_recovery_policy_is_explicit_and_validated() -> None:
    config = ChatbotConfig(api_key="fake", _apply_env_defaults=False)

    assert config.length_recovery_enabled is True
    assert config.length_recovery_max_tokens > config.max_tokens
    assert config.length_recovery_reasoning_effort == "low"
    assert config.validate() is True

    with pytest.raises(ValueError, match="length_recovery_max_tokens must be positive"):
        ChatbotConfig(
            api_key="fake",
            length_recovery_max_tokens=0,
            _apply_env_defaults=False,
        ).validate()


@pytest.mark.parametrize("recovery_max_tokens", [1000, 999])
def test_recovery_policy_requires_larger_budget_when_enabled(
    recovery_max_tokens: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="length_recovery_max_tokens must be greater than max_tokens",
    ):
        ChatbotConfig(
            api_key="fake",
            max_tokens=1000,
            length_recovery_enabled=True,
            length_recovery_max_tokens=recovery_max_tokens,
            _apply_env_defaults=False,
        ).validate()


def test_recovery_policy_allows_non_larger_budget_when_disabled() -> None:
    config = ChatbotConfig(
        api_key="fake",
        max_tokens=1000,
        length_recovery_enabled=False,
        length_recovery_max_tokens=999,
        _apply_env_defaults=False,
    )

    assert config.validate() is True


def test_recovery_policy_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("CHATBOT_LENGTH_RECOVERY_ENABLED", "false")
    monkeypatch.setenv("CHATBOT_LENGTH_RECOVERY_MAX_TOKENS", "2800")
    monkeypatch.setenv("CHATBOT_LENGTH_RECOVERY_REASONING_EFFORT", "minimal")

    config = ChatbotConfig.from_env()

    assert config.length_recovery_enabled is False
    assert config.length_recovery_max_tokens == 2800
    assert config.length_recovery_reasoning_effort == "minimal"


def test_recovery_policy_environment_distinguishes_unset_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.delenv("CHATBOT_LENGTH_RECOVERY_REASONING_EFFORT", raising=False)
    assert ChatbotConfig.from_env().length_recovery_reasoning_effort == "low"

    monkeypatch.setenv("CHATBOT_LENGTH_RECOVERY_REASONING_EFFORT", "")
    assert ChatbotConfig.from_env().length_recovery_reasoning_effort is None


def test_recovery_policy_loads_from_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    config = ChatbotConfig.from_yaml(
        {
            "ai_config": {
                "chatbot": {
                    "provider": "openai",
                    "model": "gpt-5.4-mini",
                    "length_recovery_enabled": True,
                    "length_recovery_max_tokens": 3600,
                    "length_recovery_reasoning_effort": "medium",
                }
            }
        }
    )

    assert config.length_recovery_enabled is True
    assert config.length_recovery_max_tokens == 3600
    assert config.length_recovery_reasoning_effort == "medium"

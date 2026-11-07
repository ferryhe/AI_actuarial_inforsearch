from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import openai
import pytest

from ai_actuarial.api.deps import AuthContext
from ai_actuarial.assistant import query
from ai_actuarial.assistant.help import load_help_sections, search_help
from ai_actuarial.chatbot import llm
from ai_actuarial.chatbot.config import ChatbotConfig

REAL_OPENAI = openai.OpenAI
REAL_FROM_CONFIG = ChatbotConfig.from_config


@pytest.fixture
def runtime(monkeypatch):
    state = SimpleNamespace(outputs=[], calls=[], options=[], quota=[], initialized=0)

    class FakeStorage:
        def __init__(self, _database):
            pass

        def check_and_increment_ai_chat_quota(self, day, limit, **identity):
            state.quota.append((day, limit, identity))
            return state.allowed, len(state.quota)

        def close(self):
            pass

    class FakeSDK:
        def __init__(self, **_kwargs):
            state.initialized += 1
            self.chat = SimpleNamespace(completions=self)

        def with_options(self, **options):
            state.options.append(options)
            assert options["max_retries"] == 0
            assert 0 < options["timeout"] <= query.REQUEST_SECONDS
            return self

        def close(self):
            pass

        def create(self, **kwargs):
            state.calls.append(kwargs)
            output = state.outputs.pop(0)
            if isinstance(output, Exception):
                raise output
            return {"choices": [{"message": {"content": output}, "finish_reason": "stop"}]}

    config = ChatbotConfig(api_key="unit-test-only", _apply_env_defaults=False)
    monkeypatch.setattr(ChatbotConfig, "from_config", lambda **_kwargs: config)
    monkeypatch.setattr(query.chat, "Storage", FakeStorage)
    monkeypatch.setattr(llm.openai, "OpenAI", FakeSDK)
    monkeypatch.setattr(llm.LLMClient, "_apply_rate_limit", lambda self: None)
    state.allowed = True
    state.config = config
    state.request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_path="mock", feedback_enabled=True)),
        state=SimpleNamespace(),
        headers={},
        client=SimpleNamespace(host="test-ip"),
    )
    monkeypatch.setattr(
        query.chat, "_resolve_chat_user", lambda request, auth: ("guest:mock", None)
    )

    def run(message="A suggestion", mode="auto", locale="en", deadline=None, auth=None):
        return query.query_assistant(
            payload=query.QueryRequest(message=message, mode=mode, locale=locale),
            request=state.request,
            auth=auth or AuthContext(None, frozenset()),
            deadline=deadline or time.monotonic() + query.REQUEST_SECONDS,
        )[0]

    state.run = run
    return state


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Please add a date filter", "feedback"),
        ("The preview button is broken", "feedback"),
        ("How do I preview files?", "usage"),
        ("怎样预览文件", "usage"),
        ("Explain mortality improvement", "knowledge"),
        ("解释死亡率", "knowledge"),
        ("Help", "clarify"),
        ("Add a filter and explain mortality", "clarify"),
        ("怎样提交建议", "usage"),
        ("建议按钮在哪里", "usage"),
        ("How do I send feedback?", "usage"),
        ("Where is the feedback button?", "usage"),
    ],
)
def test_intent_table(runtime, message, intent):
    # Counterexamples also survive a forced classifier misclassification.
    classified = "feedback" if query._feedback_help_question(message) else intent
    runtime.outputs = [json.dumps({"intent": classified}), '{"steps":[]}']
    result = runtime.run(message)
    assert result.intent == intent
    assert result.feedback_draft == (message if intent == "feedback" else None)
    assert len(runtime.calls) <= 2
    assert result.embedding_attempts == 0


@pytest.mark.parametrize(
    "output", ["not json", '{"intent":"unknown"}', '{"intent":"feedback","draft":"summarized"}']
)
def test_malformed_intent_never_returns_a_draft(runtime, output):
    runtime.outputs = [output]
    result = runtime.run()
    assert result.error_code == "INVALID_MODEL_RESPONSE"
    assert result.feedback_draft is None
    assert len(runtime.calls) == 1


def test_feedback_draft_is_original_and_independent_flag(runtime):
    message = "  Please fix this\n原文  "
    runtime.outputs = ['{"intent":"feedback"}']
    result = runtime.run(message)
    assert result.feedback_draft == message
    runtime.request.app.state.feedback_enabled = False
    runtime.outputs = ['{"intent":"feedback"}']
    assert runtime.run(message).error_code == "FEEDBACK_DISABLED"


@pytest.mark.parametrize(
    "message",
    [
        "Please add a help page explaining how to send feedback",
        "建议增加说明，告诉用户如何提交反馈。",
        "How about adding a feedback button?",
    ],
)
def test_feedback_proposal_about_help_preserves_original_draft(runtime, message):
    runtime.outputs = ['{"intent":"feedback"}', '{"steps":[]}']
    result = runtime.run(message)
    assert result.intent == "feedback"
    assert result.feedback_draft == message
    assert result.generation_attempts == 1


@pytest.mark.parametrize("message", ["How do I send feedback?", "怎样提交建议", "建议按钮在哪里"])
def test_genuine_feedback_how_to_corrects_forced_feedback_classification(runtime, message):
    runtime.outputs = ['{"intent":"feedback"}', '{"steps":[]}']
    result = runtime.run(message)
    assert result.intent == "usage"
    assert result.feedback_draft is None


def test_mixed_feedback_help_request_keeps_clarification(runtime):
    runtime.outputs = ['{"intent":"clarify"}']
    result = runtime.run("How do I send feedback and what does mortality improvement mean?")
    assert result.intent == "clarify" and result.feedback_draft is None


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Please add more detail or rephrase your question."),
        ("zh", "请补充更多细节或换一种方式提问。"),
    ],
)
def test_auto_clarification_requests_a_clearer_question(locale, expected, runtime):
    runtime.outputs = ['{"intent":"clarify"}']
    result = runtime.run("Help", locale=locale)
    assert result.answer == expected
    assert result.intent == "clarify" and result.feedback_draft is None
    assert len(runtime.calls) <= 2


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "I could not determine the request. Please add more detail or rephrase your question."),
        ("zh", "无法确定请求，请补充更多细节或换一种方式提问。"),
    ],
)
def test_invalid_model_response_requests_a_clearer_question(locale, expected, runtime):
    runtime.outputs = ["not json"]
    result = runtime.run("Help", locale=locale)
    assert result.answer == expected
    assert result.error_code == "INVALID_MODEL_RESPONSE"


def test_explicit_knowledge_skips_quota_and_provider(runtime):
    result = runtime.run("How do I send feedback?", mode="knowledge")
    assert result.intent == "knowledge" and result.error_code == "KNOWLEDGE_SCOPE_EMPTY"
    assert runtime.initialized == len(runtime.calls) == len(runtime.quota) == 0


def test_explicit_usage_has_one_raw_attempt_and_exact_reference(runtime):
    message = "How can I preview a file?"
    refs = search_help(message, language="en", limit=3)
    sections = load_help_sections()
    chosen = next(
        (index, section)
        for index, ref in enumerate(refs)
        for section in sections
        if section.reference() == {k: v for k, v in ref.items() if k != "snippet"}
        and section.section_id == "file-details"
    )
    index, section = chosen
    quote = "When a local file exists, **Preview** is enabled."
    runtime.outputs = [json.dumps({"steps": [{"source": index, "quote": quote}]})]
    result = runtime.run(message, mode="usage")
    assert result.intent == "usage" and quote in result.answer
    assert result.citations[0].model_dump(exclude={"source_type", "link"}) == section.reference()
    assert result.citations[0].source_type == "help"
    assert result.citations[0].link.startswith("/api/assistant/help/section?")
    assert len(runtime.calls) == result.generation_attempts == 1
    assert runtime.config.max_retries == 3 and runtime.config.length_recovery_enabled
    assert runtime.options[0]["max_retries"] == 0


@pytest.mark.parametrize(
    ("provider", "model", "expected_extra_body"),
    [
        ("deepseek", "deepseek-flash", {"thinking": {"type": "disabled"}}),
        ("deepseek", "deepseek-chat", None),
        ("openai", "gpt-5.4-mini", None),
    ],
)
def test_auto_structured_calls_disable_thinking_only_for_deepseek_flash(
    runtime, provider, model, expected_extra_body
):
    runtime.config.llm_provider = provider
    runtime.config.model = model
    message = "How can I preview a file?"
    refs = search_help(message, language="en", limit=3)
    sections = load_help_sections()
    source = next(
        section
        for ref in refs
        for section in sections
        if section.reference() == {key: value for key, value in ref.items() if key != "snippet"}
    )
    runtime.outputs = [
        '{"intent":"usage"}',
        json.dumps({"steps": [{"source": 0, "quote": source.content[:80]}]}),
    ]

    result = runtime.run(message)

    assert result.intent == "usage" and result.citations[0].source_type == "help"
    assert len(runtime.calls) == result.generation_attempts == 2
    for call in runtime.calls:
        if expected_extra_body is None:
            assert "extra_body" not in call
        else:
            assert call["extra_body"] == expected_extra_body


def test_auto_usage_two_raw_attempts_and_no_extra_retry(runtime):
    runtime.outputs = ['{"intent":"usage"}', '{"steps":[]}']
    result = runtime.run("How do I preview files?")
    assert result.error_code == "HELP_NOT_FOUND"
    assert len(runtime.calls) == result.generation_attempts == 2


@pytest.mark.parametrize(
    "output",
    ['{"steps":[{"source":0,"quote":"Invented menu"}]}', '{"steps":[{"source":2,"quote":" "}]}'],
)
def test_unsupported_help_is_not_returned(runtime, output):
    runtime.outputs = [output]
    result = runtime.run("Preview", mode="usage")
    assert result.error_code == "INVALID_MODEL_RESPONSE"
    assert not result.citations


def test_missing_help_does_not_generate_answer(runtime):
    result = runtime.run("SMTP relay", mode="usage")
    assert result.error_code == "HELP_NOT_FOUND" and not runtime.calls


@pytest.mark.parametrize("mode", ["auto", "usage"])
def test_sdk_rate_limit_gets_no_automatic_retry(runtime, mode):
    runtime.outputs = [
        openai.RateLimitError(
            "test",
            response=httpx.Response(429, request=httpx.Request("POST", "https://example.test")),
            body=None,
        )
    ]
    result = runtime.run("Preview", mode=mode)
    assert result.error_code == "PROVIDER_RATE_LIMITED"
    assert len(runtime.calls) == result.generation_attempts == 1


def test_quota_rejects_before_config_or_provider(runtime):
    runtime.allowed = False
    result = runtime.run()
    assert result.error_code == "QUOTA_EXCEEDED"
    assert runtime.initialized == len(runtime.calls) == 0
    assert runtime.quota[0][1:] == (5, {"ip_address": "test-ip"})


def test_registered_identity_uses_exact_chat_ledger(runtime):
    runtime.outputs = ['{"intent":"clarify"}']
    runtime.run(
        auth=AuthContext({"group_name": "registered", "_email_user": {"id": 42}}, frozenset())
    )
    assert runtime.quota[0][1:] == (20, {"user_id": 42})


def test_expired_deadline_makes_zero_provider_requests(runtime):
    result = runtime.run(deadline=time.monotonic() - 1)
    assert result.error_code == "ASSISTANT_TIMEOUT" and not runtime.calls


def test_missing_credentials_returns_safe_provider_error(runtime, monkeypatch):
    monkeypatch.setattr(
        ChatbotConfig,
        "from_config",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("private config detail")),
    )
    result = runtime.run()
    assert result.error_code == "PROVIDER_UNAVAILABLE"
    assert "private" not in result.model_dump_json() and not runtime.calls


@pytest.mark.parametrize(
    "credential_id",
    ["openai:llm:instance:not-present", "mistral:llm:instance:primary", "openai:llm:env"],
)
def test_actual_config_binding_failure_never_falls_back_or_initializes_provider(
    runtime, monkeypatch, credential_id
):
    import config.yaml_config as yaml_config

    if credential_id.endswith(":env"):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        # An available env credential must not override a missing/mismatched explicit binding.
        monkeypatch.setenv("OPENAI_API_KEY", "unit-test-unusable-fallback")
    monkeypatch.setattr(
        yaml_config,
        "load_yaml_config",
        lambda: {
            "ai_config": {
                "chatbot": {
                    "provider": "openai",
                    "model": "gpt-5.4-mini",
                    "credential_id": credential_id,
                },
                "embeddings": {"provider": "local", "model": "local"},
            }
        },
    )
    monkeypatch.setattr(
        query.chat.Storage, "get_llm_provider", lambda *args, **kwargs: None, raising=False
    )
    monkeypatch.setattr(ChatbotConfig, "from_config", lambda **kwargs: REAL_FROM_CONFIG(**kwargs))
    result = runtime.run("Preview", mode="usage")
    assert result.error_code == "PROVIDER_UNAVAILABLE"
    assert result.feedback_draft is None
    assert runtime.initialized == len(runtime.calls) == result.generation_attempts == 0


@pytest.mark.parametrize("mode", ["auto", "usage"])
def test_real_sdk_transport_counts_every_attempt_without_hidden_retries(runtime, monkeypatch, mode):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            429, json={"error": {"message": "mock rate limit", "type": "rate_limit"}}
        )

    sdk = REAL_OPENAI(
        api_key="unit-test-only", http_client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    monkeypatch.setattr(llm.openai, "OpenAI", lambda **kwargs: sdk)
    try:
        result = runtime.run("Preview", mode=mode)
        assert result.error_code == "PROVIDER_RATE_LIMITED"
        assert len(requests) == result.generation_attempts == 1
    finally:
        sdk.close()


def test_real_storage_single_turn_never_writes_chat_or_feedback(runtime, monkeypatch, tmp_path):
    from ai_actuarial.storage import Storage
    from tests.postgres_helpers import postgres_url_for_path

    database = postgres_url_for_path(tmp_path / "assistant-no-chat.db")
    monkeypatch.setattr(query.chat, "Storage", Storage)
    runtime.request.app.state.db_path = database

    def counts():
        storage = Storage(database)
        try:
            result = {}
            for table in ("conversations", "messages", "feedback_items"):
                exists = storage._conn.execute("SELECT to_regclass(?)", (table,)).fetchone()[0]
                result[table] = (
                    storage._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if exists
                    else 0
                )
            return result
        finally:
            storage.close()

    before = counts()
    for output in (
        '{"intent":"feedback"}',
        '{"intent":"knowledge"}',
        '{"intent":"clarify"}',
        "invalid json",
    ):
        runtime.outputs = [output]
        runtime.run()
        assert counts() == before

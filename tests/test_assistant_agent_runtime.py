"""Issue #475 runtime, registry, Host and legacy boundary regressions."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from ai_actuarial.agent_runtime import Registry, RunContext, RunResult, Tool, ToolResult, run
from ai_actuarial.api import deps
from ai_actuarial.api.deps import AuthContext
from ai_actuarial.api.routers.assistant_runtime import router as feature_router
from ai_actuarial.assistant.query import FeatureResponse, QueryResponse
from ai_actuarial.assistant.router import router as legacy_router
from ai_actuarial.features.assistant import AssistantFeature
from ai_actuarial.features.assistant import feature as host
from ai_actuarial.skills.test_lookup import executors
from ai_actuarial.skills.test_lookup.manifest import ARGUMENT_MODELS, MANIFEST


def action(**values):
    return json.dumps(values)


def scripted(*outputs):
    remaining = list(outputs)
    calls = []

    def model(prompt, timeout):
        calls.append((json.loads(prompt), timeout))
        return remaining.pop(0)

    return model, calls


def block_assistant_feature_import(monkeypatch, missing_name):
    import builtins

    original_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "ai_actuarial.features.assistant":
            raise ModuleNotFoundError(f"No module named '{missing_name}'", name=missing_name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)


def registry(enabled=True):
    return Registry(
        (replace(MANIFEST, enabled=enabled),),
        frozenset({"test_lookup.search", "test_lookup.detail"}),
    )


def execute(tool, args, _context, _remaining):
    return {"test_lookup.search": executors.search, "test_lookup.detail": executors.detail}[
        tool.executor
    ](args)


def test_core_import_does_not_load_host_framework_or_storage():
    code = (
        "import sys, ai_actuarial.agent_runtime; "
        "assert not any(name.startswith(('fastapi', 'ai_actuarial.storage', "
        "'ai_actuarial.assistant.knowledge', 'ai_actuarial.features')) "
        "for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_independent_skill_and_registry_extension_leave_loop_unchanged():
    loop_file = Path(run.__code__.co_filename)
    before = hashlib.sha256(loop_file.read_bytes()).hexdigest()
    model, calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.search",
            args={"term": "sam"},
        ),
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        ),
        action(action="finish", answer="Sample found", evidence_ids=["test_lookup:sample"]),
    )
    result = run(
        message="Find the sample",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset({"chat.query"})),
        model=model,
        execute=execute,
    )
    assert result.availability == "available" and result.answer == "Sample found"
    assert (result.model_attempts, result.tool_attempts, result.embedding_attempts) == (3, 2, 0)
    assert [(item.tool_id, item.status) for item in result.trace] == [
        ("test_lookup.search", "ok"),
        ("test_lookup.detail", "ok"),
    ]
    assert calls[1][0]["observations"][0]["data"] == {"item_ids": ["sample"]}
    assert calls[2][0]["observations"][1]["evidence_ids"] == ["test_lookup:sample"]

    class MoreArgs(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        value: str

    extra = Tool("test_lookup.more", "Another same-class lookup.", "test_lookup.more", MoreArgs)
    expanded = Registry(
        (replace(MANIFEST, tools=MANIFEST.tools + (extra,)),),
        frozenset({"test_lookup.search", "test_lookup.detail", "test_lookup.more"}),
    )
    assert expanded.tool("test_lookup", "test_lookup.more") == extra
    assert hashlib.sha256(loop_file.read_bytes()).hexdigest() == before
    assert not registry(False).descriptions()
    assert not calls[0][0]["observations"]


def test_packaged_skill_discovery_disable_and_call_without_loop_edit():
    assert Path("ai_actuarial/skills/test_lookup/SKILL.md").is_file()
    assert Path("ai_actuarial/skills/test_lookup/skill.json").is_file()
    loaded = Registry.load_skill("ai_actuarial.skills.test_lookup", ARGUMENT_MODELS)
    assert loaded == MANIFEST and "fixture data" in loaded.description
    catalog = Registry((loaded,), frozenset({"test_lookup.search", "test_lookup.detail"}))
    assert [entry["skill_id"] for entry in catalog.descriptions()] == ["test_lookup"]
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        ),
        action(action="finish", answer="sample", evidence_ids=["test_lookup:sample"]),
    )
    result = run(
        message="sample",
        locale="en",
        registry=catalog,
        context=RunContext(principal="admin", scopes=frozenset({"chat.query"})),
        model=model,
        execute=execute,
    )
    assert result.kind == "finish" and result.evidence_ids == ("test_lookup:sample",)
    disabled = Registry(
        (replace(loaded, enabled=False),), frozenset({"test_lookup.search", "test_lookup.detail"})
    )
    assert not disabled.descriptions()
    with pytest.raises(ValueError, match="disabled"):
        disabled.tool("test_lookup", "test_lookup.detail")


@pytest.mark.parametrize(
    "skills,executors,match",
    [
        ((MANIFEST, MANIFEST), {"test_lookup.search", "test_lookup.detail"}, "Duplicate skill ID"),
        (
            (replace(MANIFEST, version="2.0"),),
            {"test_lookup.search", "test_lookup.detail"},
            "Incompatible skill version",
        ),
        ((MANIFEST,), {"test_lookup.search"}, "Unknown executor"),
    ],
)
def test_registry_fails_closed(skills, executors, match):
    with pytest.raises(ValueError, match=match):
        Registry(skills, frozenset(executors))


@pytest.mark.parametrize(
    "output,code",
    [
        (action(action="clarify", question="Which item?", extra=1), "INVALID_MODEL_RESPONSE"),
        (
            action(
                action="call", skill_id="unknown", tool_id="test_lookup.search", args={"term": "a"}
            ),
            "INVALID_MODEL_RESPONSE",
        ),
        (
            action(
                action="call",
                skill_id="test_lookup",
                tool_id="test_lookup.detail",
                args={"item_id": "sample", "kb_id": "staff"},
            ),
            "INVALID_MODEL_RESPONSE",
        ),
        (action(action="finish", answer="unsupported", evidence_ids=[]), "NO_EVIDENCE"),
        ("not json", "INVALID_MODEL_RESPONSE"),
    ],
)
def test_invalid_or_unsupported_action_never_executes_tool(output, code):
    model, _calls = scripted(output)
    invoked = []
    result = run(
        message="question",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset({"chat.query"})),
        model=model,
        execute=lambda *args: invoked.append(args),
    )
    assert result.error_code == code and not invoked


@pytest.mark.parametrize(
    "documents",
    [
        [],
        [
            {
                "target": {"kb_id": "public", "file_id": "https://example.org/report"},
                "source_url": "https://example.org/report",
            }
        ],
    ],
)
def test_catalog_discovery_contract_rejects_mismatched_target_evidence(documents):
    class FindArgs(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        query: str

    tool = Tool(
        "third.locate",
        "Test-only finder",
        "third.locate",
        FindArgs,
        frozenset({"chat.query"}),
        "catalog_discovery",
    )
    test_skill = replace(MANIFEST, skill_id="third", tools=(tool,))
    catalog = Registry((test_skill,), frozenset({"third.locate"}))
    model, _calls = scripted(
        action(action="call", skill_id="third", tool_id="third.locate", args={"query": "x"})
    )
    result = run(
        message="x",
        locale="en",
        registry=catalog,
        context=RunContext(principal="test", scopes=frozenset({"chat.query"})),
        model=model,
        execute=lambda *_: ToolResult("ok", {"documents": documents}, ("catalog:orphan",)),
    )
    assert result.error_code == "TOOL_UNAVAILABLE"
    assert result.trace[0].status == "error" and not result.evidence_ids


def test_no_match_and_ambiguous_target_clarify_without_mode():
    for question in ("unrelated request", "which of two items?"):
        model, _calls = scripted(action(action="clarify", question="Which item do you mean?"))
        result = run(
            message=question,
            locale="en",
            registry=registry(),
            context=RunContext(principal="anon", scopes=frozenset({"chat.query"})),
            model=model,
            execute=execute,
        )
        assert result.answer == "Which item do you mean?" and result.tool_attempts == 0


def test_disabled_skill_and_no_evidence_fail_without_factual_answer():
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.search",
            args={"term": "sample"},
        )
    )
    result = run(
        message="sample",
        locale="en",
        registry=registry(False),
        context=RunContext(principal="anon", scopes=frozenset()),
        model=model,
        execute=lambda *args: pytest.fail("disabled tool executed"),
    )
    assert result.error_code == "INVALID_MODEL_RESPONSE" and result.tool_attempts == 0

    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.search",
            args={"term": "missing"},
        ),
        action(action="finish", answer="a factual claim", evidence_ids=["invented"]),
    )
    result = run(
        message="missing",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset()),
        model=model,
        execute=execute,
    )
    assert result.error_code == "NO_EVIDENCE" and not result.answer


@pytest.mark.parametrize("include_action", [False, True])
def test_prompt_requires_explicit_finish_action_even_with_evidence(include_action):
    finish = {"answer": "Sample found", "evidence_ids": ["test_lookup:sample"]}
    if include_action:
        finish["action"] = "finish"
    model, calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        ),
        action(**finish),
    )
    result = run(
        message="Find sample",
        locale="en",
        registry=registry(),
        context=RunContext(principal="admin", scopes=frozenset({"chat.query"})),
        model=model,
        execute=execute,
    )
    instruction = json.loads(calls[0][0]["prompt"])["instruction"]
    assert '"action":"finish"' in instruction
    assert "no extra or omitted fields" in instruction
    assert result.tool_attempts == 1 and result.model_attempts == 2
    if include_action:
        assert result.kind == "finish" and result.answer == "Sample found"
        assert result.evidence_ids == ("test_lookup:sample",)
    else:
        assert result.error_code == "INVALID_MODEL_RESPONSE"
        assert result.kind == "error" and not result.answer and not result.evidence_ids


def test_fixed_model_and_embedding_attempt_budgets():
    model, calls = scripted(
        *[
            action(
                action="call",
                skill_id="test_lookup",
                tool_id="test_lookup.search",
                args={"term": "sample"},
            )
            for _ in range(6)
        ]
    )
    context = RunContext(principal="anon", scopes=frozenset())
    result = run(
        message="sample",
        locale="en",
        registry=registry(),
        context=context,
        model=model,
        execute=execute,
    )
    assert result.error_code == "ASSISTANT_TIMEOUT"
    assert result.model_attempts == len(calls) == 6 and result.tool_attempts == 6
    assert result.tool_attempts <= 6
    assert context.take_embedding() > 0 and context.take_embedding() > 0
    with pytest.raises(TimeoutError, match="embedding budget"):
        context.take_embedding()


def test_agent_provider_ledger_counts_create_not_unissued_model_slot():
    context = RunContext(principal="anon", scopes=frozenset())
    assert 179 < context.deadline - time.monotonic() <= 180
    context.take_model()
    assert context.model_attempts == 1 and context.provider_requests == 0
    assert 0 < context.take_provider_request(prepaid=True) <= 60
    assert context.model_attempts == context.provider_requests == 1
    context.reserve_verifier = True
    for _ in range(4):
        assert 0 < context.take_provider_request() <= 60
    assert context.model_attempts == context.provider_requests == 5
    with pytest.raises(TimeoutError, match="model budget"):
        context.take_provider_request()
    assert context.provider_requests == 5
    context.reserve_verifier = False
    context.take_model()
    assert context.take_provider_request(prepaid=True) <= 60
    assert context.provider_requests == 6
    with pytest.raises(TimeoutError, match="model budget"):
        context.take_provider_request()


def test_agent_request_deadline_does_not_change_legacy_assistant_deadline():
    from ai_actuarial.agent_runtime.contracts import AgentBudget
    from ai_actuarial.assistant import query

    assert AgentBudget.from_config({}).total_seconds == 180
    assert query.REQUEST_SECONDS == 30


@pytest.mark.parametrize(
    "section",
    [
        {"model_requests": 0},
        {"total_seconds": -1},
        {"initial_tokens": 0},
        {"recovery_tokens": 2000},
        {"request_seconds": float("nan")},
        {"max_retries": 1.5},
    ],
)
def test_agent_budget_config_rejects_invalid_values(section):
    from ai_actuarial.agent_runtime.contracts import AgentBudget

    with pytest.raises(ValueError, match="assistant_agent"):
        AgentBudget.from_config(section)


def test_agent_budget_config_allows_an_explicit_upward_override():
    from ai_actuarial.agent_runtime.contracts import AgentBudget

    budget = AgentBudget.from_config(
        {
            "initial_tokens": 3500,
            "recovery_tokens": 4500,
            "max_retries": 4,
            "model_requests": 8,
            "total_seconds": 240,
            "request_seconds": 75,
        }
    )
    context = RunContext(principal="test", scopes=frozenset(), budget=budget)
    assert 239 < context.deadline - time.monotonic() <= 240
    assert context.take_model() <= 240
    assert context.take_provider_request(prepaid=True) <= 75
    assert (budget.initial_tokens, budget.recovery_tokens, budget.max_retries) == (
        3500,
        4500,
        4,
    )


def test_agent_provider_preflight_respects_cancel_and_deadline():
    cancelled = Event()
    context = RunContext(principal="anon", scopes=frozenset(), cancelled=cancelled)
    context.take_model()
    cancelled.set()
    with pytest.raises(TimeoutError, match="cancelled"):
        context.take_provider_request(prepaid=True)
    assert context.model_attempts == 1 and context.provider_requests == 0
    cancelled.clear()
    context.deadline = time.monotonic() + 0.1
    assert 0 < context.take_provider_request(prepaid=True) <= 0.1
    context.deadline = time.monotonic() - 1
    with pytest.raises(TimeoutError, match="deadline"):
        context.take_provider_request()
    assert context.provider_requests == 1


def test_timeout_cancel_and_tool_failure_are_bounded():
    cancelled = Event()
    cancelled.set()
    model, calls = scripted(action(action="clarify", question="late"))
    result = run(
        message="x",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset(), cancelled=cancelled),
        model=model,
        execute=execute,
    )
    assert result.error_code == "ASSISTANT_TIMEOUT" and not calls

    cancelled.clear()
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        )
    )

    def late_model(prompt, timeout):
        value = model(prompt, timeout)
        cancelled.set()
        return value

    result = run(
        message="x",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset(), cancelled=cancelled),
        model=late_model,
        execute=lambda *args: pytest.fail("late tool executed"),
    )
    assert result.error_code == "ASSISTANT_TIMEOUT" and result.tool_attempts == 0

    cancelled.clear()
    model, calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        ),
        action(action="finish", answer="late", evidence_ids=["test_lookup:sample"]),
    )

    def late_tool(tool, args, context, remaining):
        observed = execute(tool, args, context, remaining)
        cancelled.set()
        return observed

    result = run(
        message="x",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset(), cancelled=cancelled),
        model=model,
        execute=late_tool,
    )
    assert result.error_code == "ASSISTANT_TIMEOUT"
    assert result.model_attempts == len(calls) == 1 and result.tool_attempts == 1
    assert not result.answer
    assert [(item.tool_id, item.status) for item in result.trace] == [
        ("test_lookup.detail", "timeout")
    ]

    cancelled.clear()
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        )
    )
    result = run(
        message="x",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset(), cancelled=cancelled),
        model=model,
        execute=lambda *args: (_ for _ in ()).throw(RuntimeError("tool")),
    )
    assert result.error_code == "TOOL_UNAVAILABLE" and result.tool_attempts == 1
    assert [(item.tool_id, item.status) for item in result.trace] == [
        ("test_lookup.detail", "error")
    ]

    model, calls = scripted(action(action="clarify", question="late"))
    result = run(
        message="x",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset(), deadline=time.monotonic() - 1),
        model=model,
        execute=execute,
    )
    assert result.error_code == "ASSISTANT_TIMEOUT" and not calls


def test_provider_adapter_timeout_is_assistant_timeout():
    from ai_actuarial.chatbot.exceptions import LLMTimeoutError

    def model(_prompt, _remaining):
        raise LLMTimeoutError()

    result = run(
        message="sample",
        locale="en",
        registry=registry(),
        context=RunContext(principal="anon", scopes=frozenset()),
        model=model,
        execute=lambda *args: pytest.fail("tool executed"),
    )
    assert result.error_code == "ASSISTANT_TIMEOUT"
    assert (result.model_attempts, result.tool_attempts) == (1, 0)


@pytest.fixture
def host_fixture(monkeypatch):
    quota = []
    executed = []

    class Storage:
        def __init__(self, database):
            assert database == "test-db"

        def check_and_increment_ai_chat_quota(self, day, limit, **identity):
            quota.append(identity)
            return True, len(quota)

        def close(self):
            pass

    monkeypatch.setattr(host.chat, "Storage", Storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("test", None))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_path="test-db", assistant_public_kb_ids=[], assistant_staff_kb_ids=[]
            )
        ),
        state=SimpleNamespace(),
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    feature = AssistantFeature()
    original = feature.executors["test_lookup.detail"]

    def detail(args):
        executed.append(args)
        return original(args)

    feature.executors["test_lookup.detail"] = detail
    return SimpleNamespace(
        feature=feature, request=request, quota=quota, executed=executed, monkeypatch=monkeypatch
    )


def test_host_quota_once_for_anonymous_and_registered_chains(host_fixture):
    state = host_fixture
    for auth in (
        AuthContext(None, frozenset()),
        AuthContext(
            {"subject": "registered", "_email_user": {"id": 7}, "group_name": "registered"},
            frozenset({"chat.query"}),
        ),
    ):
        state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
        model, _calls = scripted(
            action(
                action="call",
                skill_id="test_lookup",
                tool_id="test_lookup.search",
                args={"term": "sample"},
            ),
            action(
                action="call",
                skill_id="test_lookup",
                tool_id="test_lookup.detail",
                args={"item_id": "sample"},
            ),
            action(action="finish", answer="sample", evidence_ids=["test_lookup:sample"]),
        )
        outcome = state.feature.query(
            request=state.request, auth=auth, message="find sample", model=model
        )
        assert outcome.response.answer == "sample" and outcome.runtime.tool_attempts == 2
    assert len(state.quota) == 2 and len(state.executed) == 2
    assert "ip_address" in state.quota[0] and state.quota[1] == {"user_id": 7}

    admin = AuthContext({"subject": "admin", "group_name": "admin"}, frozenset({"chat.query"}))
    model, _calls = scripted(action(action="clarify", question="Which sample?"))
    outcome = state.feature.query(request=state.request, auth=admin, message="sample", model=model)
    assert outcome.runtime.model_attempts == 1 and len(state.quota) == 2


def test_host_revalidates_before_every_tool_and_rejects_revocation(host_fixture):
    state = host_fixture
    good = AuthContext({"subject": "user", "group_name": "registered"}, frozenset({"chat.query"}))
    revoked = AuthContext(None, frozenset())
    current = iter([good, revoked])
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: next(current))
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.search",
            args={"term": "sample"},
        ),
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        ),
    )
    outcome = state.feature.query(request=state.request, auth=good, message="sample", model=model)
    assert outcome.runtime.error_code == "SCOPE_REVOKED"
    assert outcome.runtime.model_attempts == 2 and not state.executed
    assert len(state.quota) == 1


@pytest.mark.parametrize("revoke", [False, True])
def test_host_rechecks_identity_after_final_resource_model_callback(host_fixture, revoke):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget

    state = host_fixture
    auth = AuthContext(
        {"subject": "reader"}, frozenset({"chat.query", "catalog.read", "files.read"})
    )
    current = [auth]

    def current_auth(request):
        if not hasattr(request.state, "auth_context"):
            request.state.auth_context = current[0]
        return request.state.auth_context

    state.monkeypatch.setattr(host.deps, "get_auth_context", current_auth)
    state.monkeypatch.setattr(host, "permitted_kbs", lambda *_: ["public"])

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, target):
            return Document(
                target=target,
                title="Sensitive report",
                source_url=target.file_id,
                internal_link="/file-detail?url=https%3A%2F%2Fexample.test%2Freport.pdf",
            )

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    target = SelectedTarget(kb_id="public", file_id="https://example.test/report.pdf")
    state.feature.executors["resources_updates.recent"] = lambda *_: ToolResult(
        "ok",
        {
            "files": [
                {
                    "title": "Sensitive report",
                    "source": "Agency",
                    "source_url": target.file_id,
                    "first_seen": "2026-11-01",
                }
            ],
            "total": 1,
        },
        ("resource:current",),
    )
    outputs = [
        action(
            action="call", skill_id="resources_updates", tool_id="resources_updates.recent", args={}
        ),
        action(
            action="finish",
            answer="Sensitive report is available.",
            evidence_ids=["resource:current"],
        ),
    ]

    def model(_prompt, _remaining):
        output = outputs.pop(0)
        if revoke and not outputs:
            current[0] = AuthContext({"subject": "other-reader"}, auth.permissions)
        return output

    outcome = state.feature.query(
        request=state.request, auth=auth, message="Find the latest report", model=model
    )
    if revoke:
        assert outcome.runtime.error_code == "SCOPE_REVOKED"
        assert outcome.runtime.answer == "" and outcome.runtime.evidence_ids == ()
        assert outcome.response.evidence_ids == [] and outcome.response.citations == []
        assert outcome.response.selected_target is None
        assert "Sensitive report" not in outcome.response.answer
    else:
        assert outcome.runtime.error_code is None
        assert "Sensitive report" in outcome.response.answer
        assert outcome.response.evidence_ids == ["resource:current"]
        assert (
            outcome.response.citations and outcome.response.selected_target == target.model_dump()
        )


@pytest.mark.parametrize("revoke", [False, True])
def test_host_rechecks_body_permission_after_summary_verifier_callback(host_fixture, revoke):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget

    state = host_fixture
    auth = AuthContext({"subject": "reader"}, frozenset({"chat.query", "markdown.read"}))
    current = [auth]

    def current_auth(request):
        if not hasattr(request.state, "auth_context"):
            request.state.auth_context = current[0]
        return request.state.auth_context

    state.monkeypatch.setattr(host.deps, "get_auth_context", current_auth)
    state.monkeypatch.setattr(host, "permitted_kbs", lambda *_: ["public"])
    target = SelectedTarget(kb_id="public", file_id="https://example.test/report.pdf")

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, selected):
            return Document(
                target=selected,
                title="Sensitive report",
                publication_date="2026-09-03",
                source_url=selected.file_id,
                internal_link="/file-detail?url=https%3A%2F%2Fexample.test%2Freport.pdf",
            )

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    quote = "The report states that the figure is 42%."
    state.feature.executors["document_research.read_document_sections"] = lambda *_: ToolResult(
        "ok",
        {
            "status": "available",
            "sections": [
                {
                    "target": target.model_dump(),
                    "section_id": "section-1",
                    "excerpt": quote,
                    "source_url": target.file_id,
                }
            ],
        },
        ("body:current",),
    )
    outputs = [
        action(
            action="call",
            skill_id="document_research",
            tool_id="document_research.read_document_sections",
            args={**target.model_dump(), "query": "figure"},
        ),
        action(
            action="finish",
            answer="The report states 42%.",
            evidence_ids=["body:current"],
            findings=[
                {"evidence_id": "body:current", "quote": quote, "summary": "The report states 42%."}
            ],
        ),
        action(supported=[True]),
    ]

    def model(_prompt, _remaining):
        output = outputs.pop(0)
        if revoke and not outputs:
            current[0] = AuthContext({"subject": "reader"}, frozenset({"chat.query"}))
        return output

    outcome = state.feature.query(
        request=state.request,
        auth=auth,
        message="Read the current figure",
        selected_target=target,
        model=model,
    )
    assert outcome.runtime.model_attempts == 3
    if revoke:
        assert outcome.runtime.error_code == "SCOPE_REVOKED"
        assert outcome.runtime.answer == "" and outcome.runtime.evidence_ids == ()
        assert outcome.response.evidence_ids == [] and outcome.response.citations == []
        assert outcome.response.selected_target is None
        assert quote not in outcome.response.answer
        assert "2026-09-03" not in outcome.response.answer
    else:
        assert outcome.runtime.error_code is None
        assert quote in outcome.response.answer
        assert outcome.response.evidence_ids == ["body:current"]
        assert (
            outcome.response.citations and outcome.response.selected_target == target.model_dump()
        )


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("publication_date", ["2026-09-03", None])
@pytest.mark.parametrize("verified", [True, False])
def test_body_answer_states_current_citation_publication_date(
    host_fixture, locale, publication_date, verified
):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget

    state = host_fixture
    auth = AuthContext({"subject": "reader"}, frozenset({"chat.query", "markdown.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    state.monkeypatch.setattr(host, "permitted_kbs", lambda *_: ["public"])
    target = SelectedTarget(kb_id="public", file_id="https://example.test/current.pdf")
    document = Document(
        target=target,
        title="Current report",
        publication_date=publication_date,
        system_first_seen="2026-10-01",
        source_url=target.file_id,
        internal_link="/file-detail?url=https%3A%2F%2Fexample.test%2Fcurrent.pdf",
    )

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, selected):
            return document if selected == target else None

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    quote = "The current report records 42 observations."
    state.feature.executors["document_research.read_document_sections"] = lambda *_: ToolResult(
        "ok",
        {
            "sections": [
                {
                    "target": target.model_dump(),
                    "section_id": "finding",
                    "excerpt": quote,
                    "source_url": target.file_id,
                }
            ]
        },
        ("body:current",),
    )
    model, _ = scripted(
        action(
            action="call",
            skill_id="document_research",
            tool_id="document_research.read_document_sections",
            args={**target.model_dump(), "query": "finding"},
        ),
        action(
            action="finish",
            answer="model draft",
            evidence_ids=["body:current"],
            findings=[
                {
                    "evidence_id": "body:current",
                    "quote": quote,
                    "summary": "The report records 42 observations.",
                }
            ],
        ),
        action(supported=[verified]),
    )
    outcome = state.feature.query(
        request=state.request,
        auth=auth,
        message="State the publication date",
        locale=locale,
        selected_target=target,
        model=model,
    )
    assert outcome.runtime.error_code == (None if verified else "SUMMARY_UNVERIFIED")
    assert outcome.response.citations[0].source_date == publication_date
    assert quote in outcome.response.answer
    assert "2026-10-01" not in outcome.response.answer
    expected = (
        ("发布日期：" if locale == "zh" else "Publication date: ") + publication_date
        if publication_date
        else ("发布日期未记录" if locale == "zh" else "Publication date not recorded")
    )
    assert expected in outcome.response.answer


def test_body_publication_date_uses_only_selected_evidence_id(host_fixture):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget

    state = host_fixture
    auth = AuthContext({"subject": "reader"}, frozenset({"chat.query", "markdown.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    state.monkeypatch.setattr(host, "permitted_kbs", lambda *_: ["public"])
    target = SelectedTarget(kb_id="public", file_id="https://example.test/current.pdf")
    current_date = ["2026-01-01"]

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, selected):
            if selected != target:
                return None
            return Document(
                target=target,
                title="Current report",
                publication_date=current_date[0],
                source_url=target.file_id,
                internal_link="/file-detail?url=current",
            )

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    quote = "The current report records 42 observations."
    read_count = [0]

    def read(_facade, _args):
        read_count[0] += 1
        current_date[0] = "2026-01-01" if read_count[0] == 1 else None
        return ToolResult(
            "ok",
            {
                "sections": [
                    {
                        "target": target.model_dump(),
                        "section_id": "finding",
                        "excerpt": quote,
                        "source_url": target.file_id,
                    }
                ]
            },
            (f"body:{read_count[0]}",),
        )

    state.feature.executors["document_research.read_document_sections"] = read
    call = action(
        action="call",
        skill_id="document_research",
        tool_id="document_research.read_document_sections",
        args={**target.model_dump(), "query": "finding"},
    )
    model, _ = scripted(
        call,
        call,
        action(
            action="finish",
            answer="model draft",
            evidence_ids=["body:2"],
            findings=[
                {
                    "evidence_id": "body:2",
                    "quote": quote,
                    "summary": "The report records 42 observations.",
                }
            ],
        ),
        action(supported=[True]),
    )
    outcome = state.feature.query(
        request=state.request,
        auth=auth,
        message="State the publication date",
        selected_target=target,
        model=model,
    )
    assert outcome.runtime.kind == "finish"
    assert outcome.response.evidence_ids == ["body:2"]
    assert len(outcome.response.citations) == 1
    assert outcome.response.citations[0].source_date is None
    assert "Publication date not recorded" in outcome.response.answer
    assert "2026-01-01" not in outcome.response.answer


@pytest.mark.parametrize("kind", ["body", "resource"])
@pytest.mark.parametrize("kb_id", ["staff", "public"])
def test_host_rechecks_returned_kb_after_internal_access_revoked(host_fixture, kind, kb_id):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget

    state = host_fixture
    state.request.app.state.assistant_public_kb_ids = ["public"]
    state.request.app.state.assistant_staff_kb_ids = ["staff"]
    auth = AuthContext(
        {"subject": "reader"},
        frozenset(
            {"chat.query", "catalog.read", "files.read", "markdown.read", "assistant.internal"}
        ),
    )
    current = [auth]

    def current_auth(request):
        if not hasattr(request.state, "auth_context"):
            request.state.auth_context = current[0]
        return request.state.auth_context

    state.monkeypatch.setattr(host.deps, "get_auth_context", current_auth)
    target = SelectedTarget(kb_id=kb_id, file_id=f"https://example.test/{kb_id}.pdf")

    class Facade:
        def __init__(self, *_args, authorized_kbs, **_kwargs):
            self.authorized_kbs = authorized_kbs

        def _document(self, selected):
            if selected != target or selected.kb_id not in self.authorized_kbs():
                return None
            return Document(
                target=selected,
                title=f"{kb_id} report",
                source_url=selected.file_id,
                internal_link=f"/file-detail?url={selected.file_id}",
            )

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    evidence_id = f"{kind}:{kb_id}:current"
    if kind == "body":
        quote = "The current report says 42%."
        state.feature.executors["document_research.read_document_sections"] = lambda *_: ToolResult(
            "ok",
            {
                "status": "available",
                "sections": [
                    {
                        "target": target.model_dump(),
                        "section_id": "section-1",
                        "excerpt": quote,
                        "source_url": target.file_id,
                    }
                ],
            },
            (evidence_id,),
        )
        outputs = [
            action(
                action="call",
                skill_id="document_research",
                tool_id="document_research.read_document_sections",
                args={**target.model_dump(), "query": "figure"},
            ),
            action(
                action="finish",
                answer="The figure is 42%.",
                evidence_ids=[evidence_id],
                findings=[
                    {"evidence_id": evidence_id, "quote": quote, "summary": "The figure is 42%."}
                ],
            ),
            action(supported=[True]),
        ]
    else:
        state.feature.executors["resources_updates.recent"] = lambda *_: ToolResult(
            "ok",
            {
                "files": [
                    {
                        "title": f"{kb_id} report",
                        "source": "Agency",
                        "source_url": target.file_id,
                        "first_seen": "2026-11-01",
                    }
                ],
                "total": 1,
            },
            (evidence_id,),
        )
        outputs = [
            action(
                action="call",
                skill_id="resources_updates",
                tool_id="resources_updates.recent",
                args={},
            ),
            action(action="finish", answer=f"{kb_id} report found.", evidence_ids=[evidence_id]),
        ]

    def model(_prompt, _remaining):
        output = outputs.pop(0)
        if not outputs:
            current[0] = AuthContext(
                {"subject": "reader"}, auth.permissions - {"assistant.internal"}
            )
        return output

    outcome = state.feature.query(
        request=state.request,
        auth=auth,
        message="Read the current figure" if kind == "body" else "Find the current report",
        selected_target=target if kind == "body" else None,
        model=model,
    )
    assert outcome.runtime.model_attempts == (3 if kind == "body" else 2)
    if kb_id == "staff":
        assert outcome.runtime.error_code == "SCOPE_REVOKED"
        assert outcome.runtime.answer == "" and outcome.runtime.evidence_ids == ()
        assert outcome.response.evidence_ids == [] and outcome.response.citations == []
        assert outcome.response.selected_target is None
        assert f"{kb_id} report" not in outcome.response.answer
    else:
        assert outcome.runtime.error_code is None
        assert outcome.response.evidence_ids == [evidence_id]
        assert outcome.response.citations[0].kb_id == kb_id
        assert outcome.response.selected_target == target.model_dump()


@pytest.mark.parametrize("expire_deadline", [False, True])
def test_host_cancel_or_deadline_during_auth_lookup_prevents_tool_start(
    host_fixture, expire_deadline
):
    state = host_fixture
    cancelled = Event()
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query"}))

    def recheck(request):
        if expire_deadline:
            request.state.assistant_runtime_context.deadline = time.monotonic() - 1
        else:
            cancelled.set()
        return auth

    state.monkeypatch.setattr(host.deps, "get_auth_context", recheck)
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.detail",
            args={"item_id": "sample"},
        )
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="sample", model=model, cancelled=cancelled
    )
    assert outcome.runtime.error_code == "ASSISTANT_TIMEOUT"
    assert (outcome.runtime.model_attempts, outcome.runtime.tool_attempts) == (1, 1)
    assert not state.executed
    assert [(item.tool_id, item.status) for item in outcome.runtime.trace] == [
        ("test_lookup.detail", "timeout")
    ]
    assert state.request.state.assistant_runtime_context.model_attempts == 1


def test_host_quota_rejection_stops_before_model(host_fixture):
    state = host_fixture
    auth = AuthContext(None, frozenset())
    state.monkeypatch.setattr(
        host.chat,
        "_enforce_chat_quota",
        lambda **kwargs: (_ for _ in ()).throw(host.chat.ChatApiError("denied", status_code=429)),
    )
    outcome = state.feature.query(
        request=state.request,
        auth=auth,
        message="sample",
        model=lambda *args: pytest.fail("model called"),
    )
    assert outcome.runtime.error_code == "QUOTA_EXCEEDED"
    assert outcome.runtime.model_attempts == outcome.runtime.tool_attempts == 0


@pytest.mark.parametrize(
    "assistant,feedback", [(False, False), (False, True), (True, False), (True, True)]
)
def test_feature_install_preserves_independent_feedback_switch(assistant, feedback):
    from ai_actuarial.api.app import _apply_runtime_feature_state

    app = FastAPI()
    _apply_runtime_feature_state(
        app,
        {
            "assistant_enabled": assistant,
            "feedback_enabled": feedback,
            "feedback_site_key": "test-site",
        },
    )
    assert app.state.assistant_enabled == assistant
    assert app.state.feedback_enabled == feedback
    assert hasattr(app.state, "assistant_feature") == assistant


def test_removed_assistant_feature_preserves_startup_legacy_and_feedback(monkeypatch):
    from unittest.mock import MagicMock

    from ai_actuarial.api import app as app_module
    from ai_actuarial.api.services import ops_write

    flags = {
        "assistant_enabled": True,
        "feedback_enabled": True,
        "feedback_site_key": "test-site",
        "require_auth": False,
        "enable_csrf": False,
        "enable_rate_limiting": False,
    }
    monkeypatch.setattr(app_module, "validate_proxy_config", lambda: None)
    monkeypatch.setattr(app_module, "load_sites_config", lambda **kwargs: {})
    monkeypatch.setattr(app_module, "resolve_runtime_features", lambda config: flags)
    monkeypatch.setattr(app_module, "_resolve_database", lambda: "test-db")
    monkeypatch.setattr(app_module, "resolve_data_root", lambda config: "test-root")
    monkeypatch.setattr(app_module, "_bootstrap_admin_token", lambda database: None)
    monkeypatch.setattr(app_module, "NativeTaskRuntime", lambda **kwargs: MagicMock())
    monkeypatch.setattr(ops_write, "resolve_runtime_features", lambda config: flags)
    with monkeypatch.context() as imports:
        block_assistant_feature_import(imports, "ai_actuarial.features.assistant")
        app = app_module.create_app()
        ops_write._notify_runtime_features_updated(SimpleNamespace(app_state=app.state), {})

    assert app.state.assistant_enabled and app.state.feedback_enabled
    assert not hasattr(app.state, "assistant_feature")
    paths = set(app.openapi()["paths"])
    assert {"/api/assistant/query", "/api/assistant/runtime/query", "/api/feedback"} <= paths
    admin = AuthContext({"subject": "admin"}, frozenset({"config.write", "chat.query"}))
    monkeypatch.setattr(deps, "_load_auth_context", lambda request: admin)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/feedback", json={}).status_code == 422
        unavailable = client.post(
            "/api/assistant/runtime/query",
            json={"message": "sample"},
            headers={"X-Auth-Token": "test"},
        )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "Assistant Feature is unavailable"


def test_feature_internal_missing_dependency_still_fails(monkeypatch):
    from ai_actuarial.api.app import _apply_runtime_feature_state
    from ai_actuarial.api.services import ops_write

    flags = {"assistant_enabled": True, "feedback_enabled": True, "feedback_site_key": "test-site"}
    monkeypatch.setattr(ops_write, "resolve_runtime_features", lambda config: flags)
    missing = "ai_actuarial.features.assistant.internal_dependency"
    with monkeypatch.context() as imports:
        block_assistant_feature_import(imports, missing)
        with pytest.raises(ModuleNotFoundError) as startup:
            _apply_runtime_feature_state(FastAPI(), flags)
        with pytest.raises(ModuleNotFoundError) as settings:
            ops_write._notify_runtime_features_updated(
                SimpleNamespace(app_state=SimpleNamespace()), {}
            )
    assert startup.value.name == settings.value.name == missing


def test_feature_response_distinguishes_finish_and_clarify():
    app = FastAPI()
    app.include_router(legacy_router, prefix="/api")
    legacy_schema = app.openapi()["paths"]["/api/assistant/query"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert legacy_schema["$ref"].endswith("/QueryResponse")
    assert '"answer"' not in json.dumps(QueryResponse.model_json_schema()["properties"]["intent"])
    assert '"answer"' in json.dumps(FeatureResponse.model_json_schema()["properties"]["intent"])
    finished = RunResult(
        "Sample found", "available", None, ("test_lookup:sample",), 3, 2, 0, (), "finish"
    )
    reply = AssistantFeature._response(finished, "en")
    assert isinstance(reply, FeatureResponse)
    assert reply.intent == "answer" and reply.stop_reason == "finish"
    assert reply.evidence_ids == ["test_lookup:sample"] and reply.citations == []
    assert (
        reply.generation_attempts,
        reply.routing_generation_attempts,
        reply.answer_generation_attempts,
    ) == (3, 1, 2)
    assert FeatureResponse.model_validate_json(reply.model_dump_json()).intent == "answer"

    unclear = RunResult("Which item?", "available", None, (), 1, 0, 0, (), "clarify")
    reply = AssistantFeature._response(unclear, "en")
    assert reply.intent == "clarify" and reply.stop_reason == "clarify"
    assert reply.evidence_ids == [] and reply.answer_generation_attempts == 0


def test_admin_api_mount_calls_public_feature_and_denies_normal_users(monkeypatch):
    app = FastAPI()
    app.state.assistant_enabled = True
    app.include_router(feature_router, prefix="/api")
    called = []
    admin = AuthContext({"subject": "admin"}, frozenset({"config.write", "chat.query"}))
    current = admin
    monkeypatch.setattr(deps, "_load_auth_context", lambda request: current)

    def query(**kwargs):
        called.append(kwargs)
        runtime = RunResult(
            "Sample found", "available", None, ("test_lookup:sample",), 2, 1, 0, (), "finish"
        )
        return host.Outcome(AssistantFeature._response(runtime, "en"), runtime, None)

    app.state.assistant_feature = SimpleNamespace(query=query)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/runtime/query",
            json={"message": "sample"},
            headers={"X-Auth-Token": "test"},
        )
        assert response.status_code == 200
        assert response.json()["intent"] == "answer"
        assert response.json()["evidence_ids"] == ["test_lookup:sample"]
        assert len(called) == 1 and called[0]["message"] == "sample"
        current = AuthContext({"subject": "reader"}, frozenset({"chat.query"}))
        assert (
            client.post(
                "/api/assistant/runtime/query",
                json={"message": "sample"},
                headers={"X-Auth-Token": "test"},
            ).status_code
            == 403
        )
        current = admin
        app.state.assistant_enabled = False
        assert (
            client.post(
                "/api/assistant/runtime/query",
                json={"message": "sample"},
                headers={"X-Auth-Token": "test"},
            ).status_code
            == 404
        )
    assert len(called) == 1


def test_versioned_user_api_requires_chat_query_and_keeps_admin_gate(monkeypatch):
    app = FastAPI()
    app.state.assistant_enabled = True
    app.include_router(feature_router, prefix="/api")
    called = []
    current = AuthContext({"subject": "reader"}, frozenset({"chat.query"}))
    monkeypatch.setattr(deps, "_load_auth_context", lambda request: current)

    def query(**kwargs):
        called.append(kwargs)
        runtime = RunResult(
            "Current answer", "available", None, ("test_lookup:sample",), 1, 0, 0, (), "finish"
        )
        return host.Outcome(AssistantFeature._response(runtime, "en"), runtime, None)

    app.state.assistant_feature = SimpleNamespace(query=query)
    with TestClient(app) as client:
        response = client.post(
            "/api/assistant/v1/query",
            json={"message": "sample", "locale": "en", "recent_questions": ["Earlier question"]},
            headers={"X-Auth-Token": "test"},
        )
        assert response.status_code == 200
        assert response.json()["schema_version"] == "1.0"
        assert called[-1]["auth"].permissions == frozenset({"chat.query"})
        assert called[-1]["recent_questions"] == ["Earlier question"]
        invalid = client.post(
            "/api/assistant/v1/query",
            json={"message": "sample", "recent_questions": ["x" * 501]},
            headers={"X-Auth-Token": "test"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"][0]["loc"] == ["body", "recent_questions"]
        assert (
            client.post(
                "/api/assistant/runtime/query",
                json={"message": "sample"},
                headers={"X-Auth-Token": "test"},
            ).status_code
            == 403
        )
        current = AuthContext({"subject": "reader"}, frozenset())
        assert (
            client.post(
                "/api/assistant/v1/query",
                json={"message": "sample"},
                headers={"X-Auth-Token": "test"},
            ).status_code
            == 403
        )
        current = AuthContext({"subject": "reader"}, frozenset({"chat.query"}))
        app.state.assistant_enabled = False
        assert (
            client.post(
                "/api/assistant/v1/query",
                json={"message": "sample"},
                headers={"X-Auth-Token": "test"},
            ).status_code
            == 404
        )
    assert len(called) == 1


def test_recent_questions_are_prompt_context_not_evidence():
    model, calls = scripted(action(action="clarify", question="Which report?"))
    result = run(
        message="Tell me more",
        locale="en",
        registry=registry(),
        context=RunContext(principal="reader", scopes=frozenset({"chat.query"})),
        model=model,
        execute=execute,
        recent_questions=["Find the latest SOA report"],
    )
    prompt = json.loads(calls[0][0]["prompt"])
    assert prompt["recent_questions"] == ["Find the latest SOA report"]
    assert "not evidence" in prompt["instruction"]
    assert result.evidence_ids == ()


def test_browser_disconnect_stops_runtime_work():
    import asyncio

    from ai_actuarial.api.routers.assistant_runtime import _watch_disconnection

    class Disconnected:
        async def is_disconnected(self):
            return True

    cancelled = Event()
    asyncio.run(_watch_disconnection(Disconnected(), cancelled))
    assert cancelled.is_set()


def test_finished_document_discovery_exposes_only_current_used_source_card(host_fixture):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget

    state = host_fixture
    state.request.app.state.assistant_public_kb_ids = ["public"]
    auth = AuthContext(
        {"subject": "reader"}, frozenset({"chat.query", "catalog.read", "files.read"})
    )
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    document = Document(
        target=SelectedTarget(kb_id="public", file_id="soa-report"),
        title="Latest SOA report",
        source_url="https://example.org/soa.pdf",
        internal_link="/file-detail?url=https%3A%2F%2Fexample.org%2Fsoa.pdf",
        publication_date="2026-11-01",
    )

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, target):
            return document if target == document.target else None

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    state.feature.executors["document_research.find_documents"] = lambda facade, args: ToolResult(
        "ok", {"documents": [document.model_dump()]}, ("document:soa",)
    )
    model, _calls = scripted(
        action(
            action="call",
            skill_id="document_research",
            tool_id="document_research.find_documents",
            args={"query": "SOA"},
        ),
        action(action="finish", answer="Latest report", evidence_ids=["document:soa"]),
    )
    result = state.feature.query(
        request=state.request, auth=auth, message="Latest SOA report", model=model
    )
    assert result.runtime.kind == "finish", result.runtime
    assert result.runtime.evidence_ids == ("document:soa",), result.runtime
    assert result.runtime.availability == "unavailable", result.runtime
    assert result.response.citations[0].link == document.internal_link
    assert result.response.citations[0].title == document.title
    assert result.response.selected_target == document.target.model_dump()


def test_user_api_runs_four_published_skill_families_without_admin_scope(host_fixture, monkeypatch):
    from ai_actuarial.assistant.document_research import Document, SelectedTarget
    from ai_actuarial.skills.feedback.executors import draft
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    state.request.app.state.assistant_public_kb_ids = ["public"]
    auth = AuthContext(
        {"subject": "reader"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    monkeypatch.setattr(deps, "_load_auth_context", lambda request: auth)
    document = Document(
        target=SelectedTarget(kb_id="public", file_id="soa-report"),
        title="SOA report",
        source_url="https://example.org/soa.pdf",
        internal_link="/file-detail?url=https%3A%2F%2Fexample.org%2Fsoa.pdf",
    )

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, target):
            return document if target == document.target else None

    monkeypatch.setattr(host, "DocumentResearch", Facade)
    state.feature.executors["document_research.find_documents"] = lambda facade, args: ToolResult(
        "ok", {"documents": [document.model_dump()]}, ("document:soa",)
    )
    state.feature.executors["resources_updates.weekly"] = lambda facade, args: ToolResult(
        "ok", {"snapshot": None, "total": 0}, ("weekly:empty",)
    )
    cases = [
        (
            "What features are available?",
            "usage_navigation",
            "usage_navigation.guide",
            {"query": "What features are available?", "language": "en"},
            guide({"query": "What features are available?", "language": "en"}).evidence_ids[0],
        ),
        (
            "What is new this week?",
            "resources_updates",
            "resources_updates.weekly",
            {},
            "weekly:empty",
        ),
        (
            "Find the SOA report",
            "document_research",
            "document_research.find_documents",
            {"query": "SOA"},
            "document:soa",
        ),
        (
            "Please add dark mode",
            "feedback",
            "feedback.draft",
            {"text": "Please add dark mode"},
            draft({"text": "Please add dark mode"}).evidence_ids[0],
        ),
    ]
    models = [
        scripted(
            action(action="call", skill_id=skill, tool_id=tool, args=args),
            action(action="finish", answer="Current result", evidence_ids=[evidence_id]),
        )[0]
        for _, skill, tool, args, evidence_id in cases
    ]
    original = state.feature.query
    app = FastAPI()
    app.state.assistant_enabled = True
    app.state.feedback_enabled = True
    app.state.db_path = "test-db"
    app.state.assistant_public_kb_ids = ["public"]
    app.state.assistant_staff_kb_ids = []
    app.state.assistant_feature = SimpleNamespace(
        query=lambda **kwargs: original(**kwargs, model=models.pop(0))
    )
    app.include_router(feature_router, prefix="/api")
    with TestClient(app) as client:
        for message, *_ in cases:
            response = client.post(
                "/api/assistant/v1/query",
                json={"message": message},
                headers={"X-Auth-Token": "test"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["schema_version"] == "1.0"
        assert (
            client.post(
                "/api/assistant/runtime/query",
                json={"message": "admin"},
                headers={"X-Auth-Token": "test"},
            ).status_code
            == 403
        )
    assert not models


def test_admin_api_deadline_reports_started_work(monkeypatch):
    from ai_actuarial.agent_runtime.contracts import AgentBudget
    from ai_actuarial.api.routers import assistant_runtime

    app = FastAPI()
    app.state.assistant_enabled = True
    app.include_router(feature_router, prefix="/api")
    auth = AuthContext({"subject": "admin"}, frozenset({"config.write", "chat.query"}))
    monkeypatch.setattr(deps, "_load_auth_context", lambda request: auth)
    monkeypatch.setattr(
        assistant_runtime,
        "load_agent_budget",
        lambda: AgentBudget(total_seconds=0.1, request_seconds=0.1),
    )
    started = Event()
    release = Event()

    def query(**kwargs):
        assert kwargs["budget"].total_seconds == 0.1
        assert 0 < kwargs["deadline"] - time.monotonic() <= 0.1
        context = RunContext(principal="admin", scopes=auth.permissions)
        kwargs["request"].state.assistant_runtime_context = context
        context.take_model()
        context.take_embedding()
        started.set()
        release.wait(2)
        return None

    app.state.assistant_feature = SimpleNamespace(query=query)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/assistant/runtime/query",
                json={"message": "sample"},
                headers={"X-Auth-Token": "test"},
            )
        assert started.is_set()
        assert response.status_code == 200
        body = response.json()
        assert body["error_code"] == "ASSISTANT_TIMEOUT"
        assert (body["generation_attempts"], body["embedding_attempts"]) == (1, 1)
        assert (body["routing_generation_attempts"], body["answer_generation_attempts"]) == (
            1,
            0,
        )
    finally:
        release.set()


def test_settings_notifier_installs_and_removes_feature(monkeypatch):
    from ai_actuarial.api.services import ops_write

    state = SimpleNamespace(assistant_enabled=False, feedback_enabled=True)
    bridge = SimpleNamespace(app_state=state)
    flags = {"assistant_enabled": True, "feedback_enabled": True}
    monkeypatch.setattr(ops_write, "resolve_runtime_features", lambda data: flags)
    ops_write._notify_runtime_features_updated(bridge, {})
    assert state.assistant_enabled and state.feedback_enabled
    assert isinstance(state.assistant_feature, AssistantFeature)
    flags = {"assistant_enabled": False, "feedback_enabled": True}
    ops_write._notify_runtime_features_updated(bridge, {})
    assert not state.assistant_enabled and state.feedback_enabled
    assert not hasattr(state, "assistant_feature")
    flags = {"assistant_enabled": True, "feedback_enabled": False}
    ops_write._notify_runtime_features_updated(bridge, {})
    assert state.assistant_enabled and not state.feedback_enabled
    assert isinstance(state.assistant_feature, AssistantFeature)


def test_host_rechecks_target_and_initial_scope(host_fixture):
    state = host_fixture

    class TargetArgs(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        kb_id: str

    tool = Tool("test_lookup.target", "Inspect target", "test_lookup.target", TargetArgs)
    state.feature.executors["test_lookup.target"] = lambda args: pytest.fail("target executed")
    state.feature.registry = Registry(
        (replace(MANIFEST, tools=(tool,)),), frozenset(state.feature.executors)
    )
    auth = AuthContext(None, frozenset())
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.target",
            args={"kb_id": "staff"},
        )
    )
    outcome = state.feature.query(request=state.request, auth=auth, message="staff", model=model)
    assert outcome.runtime.error_code == "SCOPE_REVOKED" and len(state.quota) == 1

    restricted = replace(tool, required_scopes=frozenset({"assistant.internal"}))
    state.feature.registry = Registry(
        (replace(MANIFEST, tools=(restricted,)),), frozenset(state.feature.executors)
    )
    model, _calls = scripted(
        action(
            action="call",
            skill_id="test_lookup",
            tool_id="test_lookup.target",
            args={"kb_id": "staff"},
        )
    )
    outcome = state.feature.query(request=state.request, auth=auth, message="staff", model=model)
    assert outcome.runtime.error_code == "SCOPE_REVOKED"


@pytest.mark.parametrize(
    "provider,model_name,expected_body",
    [
        ("openai", "gpt-5.4-mini", None),
        ("deepseek", "deepseek-flash", {"thinking": {"type": "disabled"}}),
    ],
)
def test_host_uses_same_agent_budget_with_bounded_sdk_attempts(
    host_fixture, provider, model_name, expected_body
):
    from ai_actuarial.chatbot import config as config_module
    from ai_actuarial.chatbot import llm as llm_module

    state = host_fixture
    auth = AuthContext(None, frozenset())
    observed = {}

    class SDK:
        def with_options(self, **options):
            observed["options"] = options
            return self

        def close(self):
            observed["closed"] = True

    class Client:
        def __init__(self, config, *, storage):
            observed["config"] = config
            observed["storage"] = storage
            self.client = SDK()
            self._min_request_interval = 0
            self._last_request_time = 0

        def generate(self, **kwargs):
            observed["generate"] = kwargs
            return action(action="clarify", question="Which sample?")

    config = config_module.ChatbotConfig(
        api_key="test-only", llm_provider=provider, model=model_name, _apply_env_defaults=False
    )

    def from_config(**kwargs):
        observed["from_config"] = kwargs
        return config

    state.monkeypatch.setattr(config_module.ChatbotConfig, "from_config", from_config)
    state.monkeypatch.setattr(llm_module, "LLMClient", Client)
    outcome = state.feature.query(request=state.request, auth=auth, message="sample")
    assert outcome.response.answer == "Which sample?"
    assert observed["from_config"]["storage"] is observed["storage"]
    assert observed["config"].max_tokens == 3000
    assert observed["config"].max_retries == 3
    assert observed["config"].length_recovery_enabled is True
    assert observed["config"].length_recovery_max_tokens == 4000
    assert observed["config"].llm_provider == provider
    assert observed["config"].model == model_name
    assert observed["config"].api_key == config.api_key
    assert observed["options"]["max_retries"] == 0
    assert "timeout" not in observed["options"]
    assert callable(observed["generate"]["before_request"])
    assert observed["generate"]["extra_body"] == expected_body
    assert observed["closed"]


@pytest.mark.parametrize(
    "provider,model_name,chat_tokens,token_key,budget_section,initial,recovery,request_seconds",
    [
        ("openai", "gpt-6-luna", 1000, "max_completion_tokens", {}, 3000, 4000, 60),
        ("deepseek", "deepseek-flash", 3000, "max_tokens", {}, 3000, 4000, 60),
        (
            "openai",
            "gpt-6-luna",
            1000,
            "max_completion_tokens",
            {
                "initial_tokens": 2500,
                "recovery_tokens": 3500,
                "max_retries": 2,
                "model_requests": 5,
                "total_seconds": 90,
                "request_seconds": 7,
            },
            2500,
            3500,
            7,
        ),
    ],
)
def test_host_agent_recovery_counts_real_creates_and_refreshes_timeout(
    host_fixture,
    provider,
    model_name,
    chat_tokens,
    token_key,
    budget_section,
    initial,
    recovery,
    request_seconds,
):
    from ai_actuarial.assistant import agent_budget
    from ai_actuarial.chatbot import config as config_module
    from ai_actuarial.chatbot import llm as llm_module

    state = host_fixture
    state.monkeypatch.setattr(
        agent_budget, "load_ai_config", lambda: {"assistant_agent": budget_section}
    )
    requests = []
    options = []

    class SDK:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def with_options(self, **kwargs):
            options.append(kwargs)
            return self

        def create(self, **kwargs):
            requests.append(kwargs)
            if len(requests) == 1:
                state.request.state.assistant_runtime_context.deadline = time.monotonic() + 10
                content, finish_reason = "", "length"
            else:
                content, finish_reason = action(action="clarify", question="Which report?"), "stop"
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason=finish_reason,
                        message=SimpleNamespace(content=content),
                    )
                ]
            )

        def close(self):
            pass

    chat_config = config_module.ChatbotConfig(
        api_key="test-only",
        llm_provider=provider,
        model=model_name,
        max_tokens=chat_tokens,
        retry_delay=0,
        _apply_env_defaults=False,
    )
    state.monkeypatch.setattr(
        config_module.ChatbotConfig, "from_config", lambda **kwargs: chat_config
    )
    state.monkeypatch.setattr(llm_module.openai, "OpenAI", lambda **kwargs: SDK())
    outcome = state.feature.query(
        request=state.request, auth=AuthContext(None, frozenset()), message="Which report?"
    )
    context = state.request.state.assistant_runtime_context
    assert outcome.response.answer == "Which report?"
    assert chat_config.max_tokens == chat_tokens
    assert options == [{"max_retries": 0}]
    assert context.provider_requests == context.model_attempts == 2
    assert [request[token_key] for request in requests] == [initial, recovery]
    assert 0 < requests[0]["timeout"] <= request_seconds
    assert 0 < requests[1]["timeout"] <= min(10, request_seconds)
    assert context.budget.initial_tokens == initial
    assert context.budget.recovery_tokens == recovery
    assert all("reasoning_effort" not in request for request in requests)


@pytest.mark.parametrize(
    "extra,expected_code,expected_tools",
    [
        ({"type": "json_object"}, None, 1),
        ({"type": "wrong"}, "INVALID_MODEL_RESPONSE", 0),
        ({"type": "json_object", "unexpected": 1}, "INVALID_MODEL_RESPONSE", 0),
        ({}, None, 1),
    ],
)
def test_provider_json_object_label_is_the_only_normalized_extra(
    host_fixture, extra, expected_code, expected_tools
):
    from ai_actuarial.chatbot import config as config_module
    from ai_actuarial.chatbot import llm as llm_module

    canonical = action(
        action="call",
        skill_id="test_lookup",
        tool_id="test_lookup.search",
        args={"term": "sample"},
    )
    raw = action(**json.loads(canonical), **extra)
    if not extra:
        assert host._normalize_json_object_label(raw) == raw
    elif extra.get("type") != "json_object":
        assert host._normalize_json_object_label(raw) == raw
    else:
        normalized = json.loads(host._normalize_json_object_label(raw))
        assert "type" not in normalized
        assert all(normalized[key] == value for key, value in json.loads(canonical).items())
        assert ("unexpected" in normalized) == ("unexpected" in extra)

    outputs = [raw, action(action="clarify", question="Which item?")]

    class SDK:
        def with_options(self, **options):
            assert options["max_retries"] == 0
            return self

        def close(self):
            pass

    class Client:
        def __init__(self, config, *, storage):
            self.client = SDK()
            self._min_request_interval = 0
            self._last_request_time = 0

        def generate(self, **kwargs):
            return outputs.pop(0)

    auth = AuthContext(None, frozenset())
    host_fixture.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    host_fixture.monkeypatch.setattr(
        config_module.ChatbotConfig,
        "from_config",
        lambda **kwargs: config_module.ChatbotConfig(
            api_key="test-only",
            llm_provider="deepseek",
            model="deepseek-flash",
            _apply_env_defaults=False,
        ),
    )
    host_fixture.monkeypatch.setattr(llm_module, "LLMClient", Client)
    outcome = host_fixture.feature.query(
        request=host_fixture.request, auth=auth, message="Find sample"
    )
    assert outcome.runtime.error_code == expected_code
    assert outcome.runtime.tool_attempts == expected_tools
    assert [item.tool_id for item in outcome.runtime.trace] == (
        ["test_lookup.search"] if expected_tools else []
    )


def test_feedback_skill_preserves_original_and_never_submits(host_fixture):
    state = host_fixture
    state.request.app.state.feedback_enabled = True
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    message = "Please add dark charts 中文"
    from ai_actuarial.skills.feedback.executors import draft

    evidence_id = draft({"text": message}).evidence_ids[0]
    model, _calls = scripted(
        action(
            action="call",
            skill_id="feedback",
            tool_id="feedback.draft",
            args={"text": "altered by model"},
        ),
        action(action="finish", answer="Already submitted", evidence_ids=[evidence_id]),
    )
    outcome = state.feature.query(request=state.request, auth=auth, message=message, model=model)
    assert outcome.response.intent == "feedback"
    assert outcome.response.feedback_draft == message
    assert "nothing is recorded yet" in outcome.response.answer
    assert outcome.runtime.kind == "finish"
    assert outcome.runtime.trace[0].evidence_ids == (evidence_id,)
    assert len(state.quota) == 1


def test_usage_to_weekly_follow_up_keeps_exact_guide_citation_and_open_action(host_fixture):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query", "files.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    feature_hit = guide({"query": "What features are available?", "language": "en"})
    weekly_hit = guide({"query": "How do I use the weekly report?", "language": "en"})
    contexts = []
    guide_executor = state.feature.executors["usage_navigation.guide"]

    def tracked_guide(args):
        contexts.append(state.request.state.assistant_runtime_context)
        return guide_executor(args)

    def tracked_weekly(facade, args):
        contexts.append(state.request.state.assistant_runtime_context)
        return ToolResult(
            "ok",
            {"snapshot": {"id": "current", "file_count": 1}, "total": 1, "action": "/weekly"},
            ("weekly:current",),
        )

    state.feature.executors["usage_navigation.guide"] = tracked_guide
    state.feature.executors["resources_updates.weekly"] = tracked_weekly
    feature_model, feature_calls = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": "What features are available?", "language": "en"},
        ),
        action(
            action="finish", answer="Read the guide", evidence_ids=[feature_hit.evidence_ids[0]]
        ),
    )
    features = state.feature.query(
        request=state.request,
        auth=auth,
        message="What features are available?",
        model=feature_model,
    )
    assert features.runtime.kind == "finish"
    assert (
        features.response.citations[0].content_hash
        == feature_hit.data["sections"][0]["reference"]["content_hash"]
    )

    weekly_model, weekly_calls = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": "How do I use the weekly report?", "language": "en"},
        ),
        action(
            action="call", skill_id="resources_updates", tool_id="resources_updates.weekly", args={}
        ),
        action(
            action="finish",
            answer="Read the weekly guide and one new file",
            evidence_ids=[weekly_hit.evidence_ids[0], "weekly:current"],
        ),
    )
    weekly = state.feature.query(
        request=state.request,
        auth=auth,
        message="How do I use the weekly report?",
        model=weekly_model,
    )
    assert weekly.runtime.kind == "finish"
    assert weekly.runtime.tool_attempts == 2 and weekly.runtime.model_attempts == 3
    assert set(weekly.runtime.evidence_ids) == {weekly_hit.evidence_ids[0], "weekly:current"}
    assert {item.tool_id for item in weekly.runtime.trace} == {
        "usage_navigation.guide",
        "resources_updates.weekly",
    }
    assert {item.content_hash for item in weekly.response.citations} == {
        weekly_hit.data["sections"][0]["reference"]["content_hash"]
    }
    assert "/weekly" in weekly.response.answer
    assert contexts[1] is contexts[2]
    assert contexts[1].principal == contexts[2].principal == "test"
    assert contexts[1].scopes == auth.permissions
    assert contexts[1].tool_attempts == 2 and contexts[1].model_attempts == 3

    follow_model, follow_calls = scripted(
        action(
            action="call", skill_id="resources_updates", tool_id="resources_updates.weekly", args={}
        ),
        action(action="finish", answer="One newly collected file", evidence_ids=["weekly:current"]),
    )
    follow = state.feature.query(
        request=state.request, auth=auth, message="What was new this week?", model=follow_model
    )
    assert follow.runtime.kind == "finish" and "/weekly" in follow.response.answer
    assert "1 newly first-collected files" in follow.response.answer
    assert "older published period" not in follow.response.answer
    assert follow.runtime.tool_attempts == 1 and follow.runtime.model_attempts == 2
    assert follow.runtime.evidence_ids == ("weekly:current",)
    assert contexts[0] is not contexts[1] and contexts[3] is not contexts[2]
    assert contexts[3].principal == "test" and contexts[3].scopes == auth.permissions
    assert all(
        json.loads(calls[0][0]["prompt"])["question"] == question
        for calls, question in (
            (feature_calls, "What features are available?"),
            (weekly_calls, "How do I use the weekly report?"),
            (follow_calls, "What was new this week?"),
        )
    )
    assert follow_calls[0][0]["observations"] == []
    assert len(state.quota) == 3


@pytest.mark.parametrize(
    "locale,question", [("en", "How do I view weekly updates?"), ("zh", "怎么查看周报")]
)
@pytest.mark.parametrize("snapshot_state", ["published", "none", "no_new"])
def test_combined_weekly_guide_and_snapshot_keeps_steps_and_current_state(
    host_fixture, locale, question, snapshot_state
):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query", "files.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    hit = guide({"query": question, "language": locale})
    weekly_id = next(
        evidence_id
        for evidence_id, item in zip(hit.evidence_ids, hit.data["sections"])
        if item["reference"]["section_id"] == "weekly-reports"
    )
    snapshot = (
        None
        if snapshot_state == "none"
        else {
            "id": "current",
            "period_start": "2026-10-26",
            "period_end": "2026-11-02",
            "file_count": 0 if snapshot_state == "no_new" else 1,
        }
    )
    total = 1 if snapshot_state == "published" else 0
    state.feature.executors["resources_updates.weekly"] = lambda facade, args: ToolResult(
        "ok", {"snapshot": snapshot, "total": total, "action": "/weekly"}, ("weekly:current",)
    )
    model, _ = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": question, "language": locale},
        ),
        action(
            action="call", skill_id="resources_updates", tool_id="resources_updates.weekly", args={}
        ),
        action(action="finish", answer="model prose", evidence_ids=[weekly_id, "weekly:current"]),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message=question, locale=locale, model=model
    )
    answer = outcome.response.answer
    assert outcome.runtime.kind == "finish"
    assert outcome.response.citations[0].section_id == "weekly-reports"
    assert ("查看全部" if locale == "zh" else "View all") in answer
    assert ("较早的已发布周期" if locale == "zh" else "older published period") in answer
    assert ("资料阅读详情" if locale == "zh" else "file to read its details") in answer
    assert ("原文链接" if locale == "zh" else "source link") in answer
    assert "Markdown" in answer
    assert ("[周报](/weekly)" if locale == "zh" else "[Weekly](/weekly)") in answer
    statuses = {
        "published": "2026-10-26",
        "none": (
            "目前没有完整已发布的周报快照"
            if locale == "zh"
            else "No complete published weekly snapshot"
        ),
        "no_new": "没有新增资料" if locale == "zh" else "no newly first-collected files",
    }
    assert answer.count(statuses[snapshot_state]) == 1
    if snapshot_state != "published":
        assert "2026-10-26" not in answer


@pytest.mark.parametrize(
    "empty,expected",
    [("no_snapshot", "No complete published"), ("no_new", "no newly first-collected")],
)
def test_weekly_empty_states_override_unsupported_model_claims(host_fixture, empty, expected):
    state = host_fixture
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query", "files.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    snapshot = None if empty == "no_snapshot" else {"id": "week", "file_count": 0}
    state.feature.executors["resources_updates.weekly"] = lambda facade, args: ToolResult(
        "ok", {"snapshot": snapshot, "total": 0, "action": "/weekly"}, ("weekly:empty",)
    )
    model, calls = scripted(
        action(
            action="call", skill_id="resources_updates", tool_id="resources_updates.weekly", args={}
        ),
        action(
            action="finish",
            answer="Five changed documents were added",
            evidence_ids=["weekly:empty"],
        ),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="What is new this week?", model=model
    )
    assert outcome.runtime.kind == "finish"
    assert expected in outcome.response.answer and "/weekly" in outcome.response.answer
    assert "Five changed" not in outcome.response.answer
    assert "feedback" not in {
        item["skill_id"] for item in json.loads(calls[0][0]["prompt"])["skills"]
    }


@pytest.mark.parametrize(
    "tool_id,data",
    [
        (
            "resources_updates.sources",
            {"sources": [{"source_name_en": "CAS", "count": 1}], "total": 1},
        ),
        (
            "resources_updates.recent",
            {
                "files": [
                    {
                        "title": "CAS report",
                        "source": "CAS",
                        "source_url": "https://cas.example/report",
                        "first_seen": "2026-10-01",
                    }
                ],
                "total": 1,
            },
        ),
        (
            "resources_updates.catalog_search",
            {
                "files": [
                    {
                        "title": "CAS report",
                        "source": "CAS",
                        "source_url": "https://cas.example/report",
                        "publication_date": "2026-09-01",
                        "system_first_seen": "2026-10-01",
                    }
                ],
                "total": 1,
            },
        ),
        (
            "resources_updates.weekly",
            {
                "snapshot": {
                    "id": "w1",
                    "period_start": "2026-09-28",
                    "period_end": "2026-10-05",
                    "file_count": 1,
                },
                "files": [{"title": "CAS report", "first_seen": "2026-10-01"}],
                "total": 1,
                "action": "/weekly",
            },
        ),
    ],
)
def test_resource_facts_are_grounded_despite_contradictory_model_claim(host_fixture, tool_id, data):
    state = host_fixture
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query", "catalog.read", "files.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    state.feature.executors[tool_id] = lambda facade, args: ToolResult(
        "ok", data, ("resource:cas",)
    )
    args = {"query": "CAS"} if tool_id.endswith("catalog_search") else {}
    model, _ = scripted(
        action(action="call", skill_id="resources_updates", tool_id=tool_id, args=args),
        action(
            action="finish",
            answer="SOA published five revised reports today.",
            evidence_ids=["resource:cas"],
        ),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="What changed?", model=model
    )
    assert outcome.runtime.kind == "finish"
    assert "SOA" not in outcome.response.answer
    assert "five revised" not in outcome.response.answer
    assert "CAS" in outcome.response.answer
    assert str(data["total"]) in outcome.response.answer
    if tool_id != "resources_updates.sources":
        assert "2026-10-01" in outcome.response.answer
        assert "revision history is not recorded" in outcome.response.answer


@pytest.mark.parametrize(
    "tool_id", ["resources_updates.recent", "resources_updates.catalog_search"]
)
@pytest.mark.parametrize("membership", ["one", "two_files", "missing", "two_kbs"])
def test_resource_file_cards_keep_catalog_rows_and_require_membership_for_target(
    host_fixture, tool_id, membership
):
    from ai_actuarial.assistant.document_research import Document

    state = host_fixture
    state.request.app.state.assistant_public_kb_ids = ["public", "other"]
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query", "catalog.read", "files.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    files = [
        {
            "title": "CAS report",
            "source_url": "https://cas.example/report",
            "link": "/file-detail?url=https%3A%2F%2Fcas.example%2Freport",
            "published_time": "2026-09-01",
            "first_seen": "2026-10-01",
        }
    ]
    if membership == "two_files":
        files.append(
            {
                "title": "Second report",
                "source_url": "https://cas.example/second",
                "link": "/file-detail?url=https%3A%2F%2Fcas.example%2Fsecond",
                "first_seen": "2026-10-02",
            }
        )

    class Facade:
        def __init__(self, *_args, **_kwargs):
            pass

        def _document(self, target):
            if membership == "missing" or target.file_id not in {
                row["source_url"] for row in files
            }:
                return None
            if target.kb_id != "public" and membership != "two_kbs":
                return None
            return Document(
                target=target,
                title=next(row["title"] for row in files if row["source_url"] == target.file_id),
                source_url=target.file_id,
                internal_link=next(
                    row["link"] for row in files if row["source_url"] == target.file_id
                ),
                publication_date="2026-09-01",
            )

    state.monkeypatch.setattr(host, "DocumentResearch", Facade)
    state.feature.executors[tool_id] = lambda facade, args: ToolResult(
        "ok", {"files": files, "total": len(files)}, ("resource:current-files",)
    )
    args = {"query": "CAS"} if tool_id.endswith("catalog_search") else {}
    model, _ = scripted(
        action(action="call", skill_id="resources_updates", tool_id=tool_id, args=args),
        action(
            action="finish", answer="Catalog summary only", evidence_ids=["resource:current-files"]
        ),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="Find CAS reports", model=model
    )
    cards = outcome.response.citations
    assert len(cards) == len(files)
    if cards:
        assert all(card.source_type == "catalog" for card in cards)
        assert [card.link for card in cards] == [row["link"] for row in files]
    if membership == "missing":
        assert cards[0].title == files[0]["title"]
        assert cards[0].kb_id is None
    assert outcome.response.selected_target == (
        {"kb_id": "public", "file_id": files[0]["source_url"]} if membership == "one" else None
    )
    assert "body evidence" in outcome.response.answer or tool_id.endswith("recent")


def test_weekly_plain_path_is_replaced_by_clickable_action(host_fixture):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query", "files.read"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    hit = guide({"query": "How do I use the weekly report?", "language": "en"})
    model, _ = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": "How do I use the weekly report?", "language": "en"},
        ),
        action(
            action="finish",
            answer="Open /weekly to view the report.",
            evidence_ids=[hit.evidence_ids[0]],
        ),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="How do I use weekly reports?", model=model
    )
    assert outcome.runtime.kind == "finish"
    assert "[Weekly](/weekly)" in outcome.response.answer


@pytest.mark.parametrize("files_read", [True, False])
def test_chinese_weekly_question_first_guide_evidence_keeps_action_and_access(
    host_fixture, files_read
):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    scopes = {"chat.query", "files.read"} if files_read else {"chat.query"}
    auth = AuthContext({"subject": "user"}, frozenset(scopes))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    hit = guide({"query": "怎么查看周报", "language": "zh"})
    assert hit.data["sections"][0]["reference"]["section_id"] == "weekly-reports"
    model, _ = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": "怎么查看周报", "language": "zh"},
        ),
        action(action="finish", answer="请看第一条指南。", evidence_ids=[hit.evidence_ids[0]]),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="怎么查看周报", locale="zh", model=model
    )
    assert outcome.runtime.kind == "finish"
    assert outcome.response.citations[0].section_id == "weekly-reports"
    if files_read:
        assert "[周报](/weekly)" in outcome.response.answer
    else:
        assert "](/weekly)" not in outcome.response.answer
        assert "无法打开周报页" in outcome.response.answer


@pytest.mark.parametrize(
    "locale,query,unsupported",
    [
        ("en", "What features are available?", "All users can manage accounts and delete files."),
        ("zh", "有哪些功能怎么用？", "所有用户都可以管理账户和删除文件。"),
    ],
)
def test_guide_only_feature_answer_cannot_contradict_current_section(
    host_fixture, locale, query, unsupported
):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    auth = AuthContext({"subject": "user"}, frozenset({"chat.query"}))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    hit = guide({"query": query, "language": locale})
    evidence_id, section = next(
        (evidence_id, item)
        for evidence_id, item in zip(hit.evidence_ids, hit.data["sections"])
        if item["reference"]["section_id"] == "features-dashboard"
    )
    model, _ = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": query, "language": locale},
        ),
        action(action="finish", answer=unsupported, evidence_ids=[evidence_id]),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message=query, locale=locale, model=model
    )
    assert outcome.runtime.kind == "finish"
    assert unsupported not in outcome.response.answer
    assert section["content"][:30] in outcome.response.answer
    assert outcome.response.citations[0].content_hash == section["reference"]["content_hash"]


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("mode", ["guide", "data", "denied"])
def test_overview_keeps_all_selected_help_when_weekly_is_included(host_fixture, locale, mode):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    files_read = mode != "denied"
    scopes = {"chat.query", "files.read"} if files_read else {"chat.query"}
    auth = AuthContext({"subject": "user"}, frozenset(scopes))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    reads = []

    class WeeklyStorage(host.chat.Storage):
        def get_latest_weekly_snapshot(self, *, now):
            reads.append(now)
            return {"period_start": "2026-10-26", "period_end": "2026-11-02"}

    state.monkeypatch.setattr(host.chat, "Storage", WeeklyStorage)
    sections = []
    evidence_ids = []
    terms = {
        "en": (
            ("feedback", "feedback-entry"),
            ("features-dashboard", "features-dashboard"),
            ("weekly reports", "weekly-reports"),
        ),
        "zh": (
            ("反馈", "feedback-entry"),
            ("功能", "features-dashboard"),
            ("周报", "weekly-reports"),
        ),
    }
    for query, section_id in terms[locale]:
        hit = guide({"query": query, "language": locale})
        evidence_id, section = next(
            (item_id, item)
            for item_id, item in zip(hit.evidence_ids, hit.data["sections"])
            if item["reference"]["section_id"] == section_id
        )
        evidence_ids.append(evidence_id)
        sections.append(section)
    state.feature.executors["usage_navigation.guide"] = lambda args: ToolResult(
        "ok", {"sections": sections}, tuple(evidence_ids)
    )
    if mode == "data":
        state.feature.executors["resources_updates.weekly"] = lambda facade, args: ToolResult(
            "ok",
            {
                "snapshot": {
                    "id": "published",
                    "period_start": "2026-10-26",
                    "period_end": "2026-11-02",
                    "file_count": 3,
                },
                "total": 3,
                "action": "/weekly",
            },
            ("weekly:published",),
        )
    steps = [
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": "overview", "language": locale},
        )
    ]
    if mode == "data":
        steps.append(
            action(
                action="call",
                skill_id="resources_updates",
                tool_id="resources_updates.weekly",
                args={},
            )
        )
    steps.append(
        action(
            action="finish",
            answer="model overview",
            evidence_ids=[*evidence_ids, *(["weekly:published"] if mode == "data" else [])],
        )
    )
    model, _ = scripted(*steps)
    outcome = state.feature.query(
        request=state.request, auth=auth, message="overview", locale=locale, model=model
    )
    answer = outcome.response.answer
    assert outcome.runtime.kind == "finish"
    assert [citation.section_id for citation in outcome.response.citations] == [
        "feedback-entry",
        "features-dashboard",
        "weekly-reports",
    ]
    assert sections[0]["content"][:30] in answer
    assert sections[1]["content"][:30] in answer
    assert ("查看全部" if locale == "zh" else "View all") in answer
    assert ("](/weekly)" in answer) == files_read
    assert ("2026-10-26" in answer) == files_read
    assert len(reads) == int(mode == "guide")


@pytest.mark.parametrize("path", ["guide", "resource"])
def test_weekly_action_is_not_clickable_after_files_read_is_denied(host_fixture, path):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    denied = AuthContext({"subject": "user"}, frozenset({"chat.query"}))
    allowed = AuthContext({"subject": "user"}, frozenset({"chat.query", "files.read"}))
    if path == "guide":
        auth = denied
        state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: denied)
        hit = guide({"query": "How do I view weekly updates?", "language": "en"})
        evidence_id = next(
            evidence_id
            for evidence_id, item in zip(hit.evidence_ids, hit.data["sections"])
            if item["reference"]["section_id"] == "weekly-reports"
        )
        tool_id, args = "usage_navigation.guide", {
            "query": "How do I view weekly updates?",
            "language": "en",
        }
        skill_id = "usage_navigation"
    else:
        auth = allowed
        calls = []

        def current_auth(request):
            calls.append(None)
            return allowed if len(calls) == 1 else denied

        state.monkeypatch.setattr(host.deps, "get_auth_context", current_auth)
        state.feature.executors["resources_updates.weekly"] = lambda facade, args: ToolResult(
            "ok", {"snapshot": None, "total": 0, "action": "/weekly"}, ("weekly:revoked",)
        )
        evidence_id = "weekly:revoked"
        tool_id, args, skill_id = "resources_updates.weekly", {}, "resources_updates"
    model, _ = scripted(
        action(action="call", skill_id=skill_id, tool_id=tool_id, args=args),
        action(action="finish", answer="Open /weekly", evidence_ids=[evidence_id]),
    )
    outcome = state.feature.query(
        request=state.request, auth=auth, message="How do I view weekly updates?", model=model
    )
    if path == "resource":
        assert outcome.runtime.error_code == "SCOPE_REVOKED"
        assert outcome.response.evidence_ids == [] and outcome.response.citations == []
        assert outcome.response.selected_target is None
        assert "sign in" in outcome.response.answer.lower()
        assert "](/weekly)" not in outcome.response.answer
        return
    assert outcome.runtime.kind == "finish"
    assert "](/weekly)" not in outcome.response.answer
    assert "cannot open" in outcome.response.answer.lower()
    assert "sign in" in outcome.response.answer.lower()
    if path == "guide":
        assert outcome.response.citations[0].section_id == "weekly-reports"


@pytest.mark.parametrize("snapshot_state", ["none", "published", "denied", "error"])
@pytest.mark.parametrize(
    "locale,question",
    [("en", "How do I view weekly updates?"), ("zh", "怎么查看周报")],
)
def test_weekly_guide_only_answer_uses_current_published_state(
    host_fixture, snapshot_state, locale, question
):
    from ai_actuarial.skills.usage_navigation.executors import guide

    state = host_fixture
    base_storage = host.chat.Storage
    reads = []

    class WeeklyStorage(base_storage):
        def get_latest_weekly_snapshot(self, *, now):
            reads.append(now)
            if snapshot_state == "error":
                raise RuntimeError("snapshot unavailable")
            if snapshot_state == "published":
                return {"period_start": "2026-10-26", "period_end": "2026-11-02", "file_count": 2}
            return None

    state.monkeypatch.setattr(host.chat, "Storage", WeeklyStorage)
    scopes = {"chat.query"} if snapshot_state == "denied" else {"chat.query", "files.read"}
    auth = AuthContext({"subject": "user"}, frozenset(scopes))
    state.monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    hit = guide({"query": question, "language": locale})
    weekly_id = next(
        evidence_id
        for evidence_id, item in zip(hit.evidence_ids, hit.data["sections"])
        if item["reference"]["section_id"] == "weekly-reports"
    )
    model, _ = scripted(
        action(
            action="call",
            skill_id="usage_navigation",
            tool_id="usage_navigation.guide",
            args={"query": question, "language": locale},
        ),
        action(
            action="finish",
            answer="Weekly reports are only in admin settings; the current week is already published.",
            evidence_ids=[weekly_id],
        ),
    )
    outcome = state.feature.query(
        request=state.request,
        auth=auth,
        message=question,
        locale=locale,
        model=model,
    )
    assert outcome.runtime.kind == "finish"
    assert "admin settings" not in outcome.response.answer
    assert "current week is already published" not in outcome.response.answer
    assert (
        "资料阅读详情" if locale == "zh" else "file to read its details"
    ) in outcome.response.answer
    assert ("原文链接" if locale == "zh" else "source link") in outcome.response.answer
    assert "Markdown" in outcome.response.answer
    if snapshot_state == "denied":
        assert "](/weekly)" not in outcome.response.answer
        assert (
            "无法打开周报页" if locale == "zh" else "cannot open"
        ) in outcome.response.answer.lower()
    else:
        assert (
            "[周报](/weekly)" if locale == "zh" else "[Weekly](/weekly)"
        ) in outcome.response.answer
    if snapshot_state == "none":
        assert (
            "目前没有完整已发布的周报快照"
            if locale == "zh"
            else "No complete published weekly snapshot"
        ) in outcome.response.answer
    elif snapshot_state == "published":
        assert "2026-10-26" in outcome.response.answer
        assert "2026-11-02" in outcome.response.answer
    else:
        assert "No complete published weekly snapshot" not in outcome.response.answer
        assert "目前没有完整已发布的周报快照" not in outcome.response.answer
        assert "2026-10-26" not in outcome.response.answer
    assert len(reads) == (0 if snapshot_state == "denied" else 1)


@pytest.mark.parametrize(
    "code,fragment",
    [
        ("QUOTA_EXCEEDED", "quota"),
        ("SCOPE_REVOKED", "access"),
        ("PROVIDER_UNAVAILABLE", "model"),
        ("NO_EVIDENCE", "evidence"),
    ],
)
def test_runtime_error_messages_are_actionable(code, fragment):
    response = AssistantFeature._response(RunResult("", "error", code, (), 0, 0, 0, ()), "en")
    assert fragment in response.answer.lower()

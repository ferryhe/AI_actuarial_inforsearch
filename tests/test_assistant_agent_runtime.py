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

from ai_actuarial.agent_runtime import Registry, RunContext, RunResult, Tool, run
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
            for _ in range(4)
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
    assert result.model_attempts == len(calls) == 4 and result.tool_attempts == 4
    assert result.tool_attempts <= 6
    assert context.take_embedding() > 0 and context.take_embedding() > 0
    with pytest.raises(TimeoutError, match="embedding budget"):
        context.take_embedding()


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
    paths = {route.path for route in app.routes}
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


def test_admin_api_deadline_reports_started_work(monkeypatch):
    from ai_actuarial.api.routers import assistant_runtime

    app = FastAPI()
    app.state.assistant_enabled = True
    app.include_router(feature_router, prefix="/api")
    auth = AuthContext({"subject": "admin"}, frozenset({"config.write", "chat.query"}))
    monkeypatch.setattr(deps, "_load_auth_context", lambda request: auth)
    monkeypatch.setattr(assistant_runtime, "REQUEST_SECONDS", 0.1)
    started = Event()
    release = Event()

    def query(**kwargs):
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
def test_host_uses_chat_config_with_one_bounded_sdk_attempt(
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
    assert observed["config"].max_retries == 1
    assert observed["config"].length_recovery_enabled is False
    assert observed["options"]["max_retries"] == 0
    assert 0 < observed["options"]["timeout"] <= 30
    assert observed["generate"]["extra_body"] == expected_body
    assert observed["closed"]


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

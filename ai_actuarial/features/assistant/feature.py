"""Host-owned identity, quota, provider and executor boundary."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from threading import Event
from typing import Callable

from ai_actuarial.agent_runtime import Registry, RunContext, RunResult, ToolResult, run
from ai_actuarial.agent_runtime.artifacts import ArtifactError, ArtifactStore
from ai_actuarial.api import deps
from ai_actuarial.api.deps import AuthContext, public_permissions_for_request
from ai_actuarial.api.services import chat
from ai_actuarial.assistant.knowledge import permitted_kbs
from ai_actuarial.assistant.query import FeatureResponse
from ai_actuarial.postgres import DatabaseConfig, resolve_data_root
from ai_actuarial.skills.test_lookup import executors as test_executors
from ai_actuarial.skills.test_lookup.manifest import ARGUMENT_MODELS
from ai_actuarial.skills.test_lookup.manifest import MANIFEST as TEST_MANIFEST


@dataclass(frozen=True)
class Outcome:
    response: FeatureResponse
    runtime: RunResult
    session_update: chat.SessionUpdate | None


def _identity(auth: AuthContext) -> tuple:
    token = auth.token or {}
    return (token.get("id"), token.get("subject"), token.get("_email_user_id"))


def _normalize_json_object_label(raw: str) -> str:
    try:
        action = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if isinstance(action, dict) and action.get("type") == "json_object":
        del action["type"]
        return json.dumps(action, ensure_ascii=False)
    return raw


class AssistantFeature:
    def __init__(self, *, enabled: bool = True):
        self.executors: dict[str, Callable[[dict], ToolResult]] = {
            "test_lookup.search": test_executors.search,
            "test_lookup.detail": test_executors.detail,
        }
        self.registry = Registry(
            (replace(TEST_MANIFEST, enabled=enabled),), frozenset(self.executors)
        )

    def query(
        self,
        *,
        request,
        auth: AuthContext,
        message: str,
        locale: str = "en",
        model: Callable[[str, float], str] | None = None,
        cancelled: Event | None = None,
        deadline: float | None = None,
    ) -> Outcome:
        initial_identity = _identity(auth)
        initial_scopes = auth.permissions if auth.token else public_permissions_for_request(request)
        if "chat.query" not in initial_scopes:
            raise PermissionError("chat.query required")
        principal, session_update = chat._resolve_chat_user(request, auth)
        context = RunContext(
            principal=principal, scopes=initial_scopes, cancelled=cancelled, deadline=deadline
        )
        request.state.assistant_runtime_context = context
        database = getattr(request.app.state, "database", None) or request.app.state.db_path
        storage = chat.Storage(database)
        client = None
        try:
            registry = self.registry
            if isinstance(database, DatabaseConfig) or str(database).startswith(
                ("postgres://", "postgresql://")
            ):
                store = ArtifactStore(
                    database,
                    getattr(request.app.state, "data_root", None) or resolve_data_root(),
                    executors=frozenset(self.executors),
                    argument_models=ARGUMENT_MODELS,
                    registered_tools=TEST_MANIFEST.tools,
                )
                try:
                    registry, pinned = store.resolve_active(
                        feature_key="assistant", site_key="default"
                    )
                    request.state.assistant_release_ids = pinned
                except ArtifactError:
                    runtime = RunResult("", "error", "INVALID_SKILL_RELEASE", (), 0, 0, 0, ())
                    return Outcome(self._response(runtime, locale), runtime, session_update)
            try:
                chat._enforce_chat_quota(storage=storage, request=request, auth=auth)
            except chat.ChatApiError as exc:
                if exc.status_code != 429:
                    raise
                runtime = RunResult("", "error", "QUOTA_EXCEEDED", (), 0, 0, 0, ())
                return Outcome(self._response(runtime, locale), runtime, session_update)
            if model is None:
                from ai_actuarial.chatbot.config import ChatbotConfig
                from ai_actuarial.chatbot.llm import LLMClient

                config = replace(
                    ChatbotConfig.from_config(storage=storage),
                    max_retries=1,
                    length_recovery_enabled=False,
                )
                client = LLMClient(config, storage=storage)

                def model(prompt: str, remaining: float) -> str:
                    wait = max(
                        0.0,
                        client._min_request_interval - (time.time() - client._last_request_time),
                    )
                    if remaining <= wait:
                        raise TimeoutError("provider wait exceeds deadline")
                    client.client = client.client.with_options(
                        max_retries=0, timeout=remaining - wait
                    )
                    extra_body = (
                        {"thinking": {"type": "disabled"}}
                        if config.llm_provider == "deepseek" and config.model == "deepseek-flash"
                        else None
                    )
                    raw = client.generate(
                        messages=[
                            {"role": "system", "content": "Return the requested JSON action."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0,
                        response_format={"type": "json_object"},
                        extra_body=extra_body,
                    )
                    return _normalize_json_object_label(raw)

            def execute(tool, args: dict, run_context: RunContext, _remaining: float) -> ToolResult:
                # The dependency cache is request-scoped, so force a fresh lookup per action.
                if hasattr(request.state, "auth_context"):
                    del request.state.auth_context
                current = deps.get_auth_context(request)
                current_scopes = (
                    current.permissions
                    if current.token
                    else public_permissions_for_request(request)
                )
                if (
                    _identity(current) != initial_identity
                    or not tool.required_scopes <= run_context.scopes
                    or not tool.required_scopes <= current_scopes
                ):
                    raise PermissionError("identity or scope changed")
                if "kb_id" in args and args["kb_id"] not in permitted_kbs(request, current):
                    raise PermissionError("KB target is outside current scope")
                run_context.remaining()
                return self.executors[tool.executor](args)

            runtime = run(
                message=message,
                locale=locale,
                registry=registry,
                context=context,
                model=model,
                execute=execute,
            )
            return Outcome(self._response(runtime, locale), runtime, session_update)
        finally:
            if client is not None:
                client.client.close()
            storage.close()

    @staticmethod
    def _response(runtime: RunResult, locale: str) -> FeatureResponse:
        zh = locale.startswith("zh")
        answer = runtime.answer or (
            "请补充更多细节或稍后重试。" if zh else "Please add more detail or retry later."
        )
        routing = 1 if runtime.model_attempts else 0
        return FeatureResponse(
            intent="answer" if runtime.kind == "finish" else "clarify",
            answer=answer,
            availability=runtime.availability,
            error_code=runtime.error_code,
            generation_attempts=runtime.model_attempts,
            routing_generation_attempts=routing,
            answer_generation_attempts=runtime.model_attempts - routing,
            embedding_attempts=runtime.embedding_attempts,
            stop_reason=runtime.kind,
            evidence_ids=list(runtime.evidence_ids),
        )


def install(app) -> AssistantFeature:
    feature = AssistantFeature()
    app.state.assistant_feature = feature
    return feature

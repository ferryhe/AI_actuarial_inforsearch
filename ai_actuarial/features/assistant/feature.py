"""Host-owned identity, quota, provider and executor boundary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Event
from typing import Callable
from urllib.parse import urlencode

from ai_actuarial.agent_runtime import Registry, RunContext, RunResult, ToolResult, run
from ai_actuarial.agent_runtime.artifacts import ArtifactError, ArtifactStore
from ai_actuarial.agent_runtime.contracts import AgentBudget
from ai_actuarial.api import deps
from ai_actuarial.api.deps import AuthContext, public_permissions_for_request
from ai_actuarial.api.services import chat
from ai_actuarial.assistant.agent_budget import load_agent_budget
from ai_actuarial.assistant.document_research import DocumentResearch, SelectedTarget
from ai_actuarial.assistant.knowledge import SourceCitation, permitted_kbs
from ai_actuarial.assistant.query import FeatureResponse, HelpCitation
from ai_actuarial.postgres import DatabaseConfig, resolve_data_root
from ai_actuarial.skills.document_research import executors as research_executors
from ai_actuarial.skills.document_research.manifest import (
    ARGUMENT_MODELS as RESEARCH_ARGUMENT_MODELS,
)
from ai_actuarial.skills.document_research.manifest import MANIFEST as RESEARCH_MANIFEST
from ai_actuarial.skills.feedback import executors as feedback_executors
from ai_actuarial.skills.feedback.manifest import ARGUMENT_MODELS as FEEDBACK_ARGUMENT_MODELS
from ai_actuarial.skills.feedback.manifest import MANIFEST as FEEDBACK_MANIFEST
from ai_actuarial.skills.resources_updates import executors as resources_executors
from ai_actuarial.skills.resources_updates.manifest import (
    ARGUMENT_MODELS as RESOURCES_ARGUMENT_MODELS,
)
from ai_actuarial.skills.resources_updates.manifest import MANIFEST as RESOURCES_MANIFEST
from ai_actuarial.skills.test_lookup import executors as test_executors
from ai_actuarial.skills.test_lookup.manifest import ARGUMENT_MODELS
from ai_actuarial.skills.test_lookup.manifest import MANIFEST as TEST_MANIFEST
from ai_actuarial.skills.usage_navigation import executors as usage_executors
from ai_actuarial.skills.usage_navigation.manifest import ARGUMENT_MODELS as USAGE_ARGUMENT_MODELS
from ai_actuarial.skills.usage_navigation.manifest import MANIFEST as USAGE_MANIFEST


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
            "document_research.find_documents": research_executors.find_documents,
            "document_research.read_document_sections": research_executors.read_document_sections,
            "document_research.search_knowledge": research_executors.search_knowledge,
            "document_research.readiness": research_executors.readiness,
            "usage_navigation.guide": usage_executors.guide,
            "resources_updates.sources": resources_executors.sources,
            "resources_updates.recent": resources_executors.recent,
            "resources_updates.catalog_search": resources_executors.catalog_search,
            "resources_updates.weekly": resources_executors.weekly,
            "resources_updates.find_documents": resources_executors.find_documents,
            "resources_updates.document_dates": resources_executors.document_dates,
            "feedback.draft": feedback_executors.draft,
        }
        self.registry = Registry(
            tuple(
                replace(item, enabled=enabled)
                for item in (
                    TEST_MANIFEST,
                    RESEARCH_MANIFEST,
                    USAGE_MANIFEST,
                    RESOURCES_MANIFEST,
                    FEEDBACK_MANIFEST,
                )
            ),
            frozenset(self.executors),
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
        selected_target: SelectedTarget | None = None,
        recent_questions: list[str] | None = None,
        budget: AgentBudget | None = None,
    ) -> Outcome:
        initial_identity = _identity(auth)
        initial_scopes = auth.permissions if auth.token else public_permissions_for_request(request)
        if "chat.query" not in initial_scopes:
            raise PermissionError("chat.query required")
        principal, session_update = chat._resolve_chat_user(request, auth)
        budget = budget or load_agent_budget()
        context = RunContext(
            principal=principal,
            scopes=initial_scopes,
            cancelled=cancelled,
            deadline=deadline,
            budget=budget,
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
                    argument_models=(
                        ARGUMENT_MODELS
                        | RESEARCH_ARGUMENT_MODELS
                        | USAGE_ARGUMENT_MODELS
                        | RESOURCES_ARGUMENT_MODELS
                        | FEEDBACK_ARGUMENT_MODELS
                    ),
                    registered_tools=(
                        TEST_MANIFEST.tools
                        + RESEARCH_MANIFEST.tools
                        + USAGE_MANIFEST.tools
                        + RESOURCES_MANIFEST.tools
                        + FEEDBACK_MANIFEST.tools
                    ),
                )
                try:
                    registry, pinned = store.resolve_active(
                        feature_key="assistant", site_key="default"
                    )
                    request.state.assistant_release_ids = pinned
                except ArtifactError:
                    runtime = RunResult("", "error", "INVALID_SKILL_RELEASE", (), 0, 0, 0, ())
                    return Outcome(self._response(runtime, locale), runtime, session_update)
            if (
                not getattr(request.app.state, "feedback_enabled", False)
                and "feedback" in registry.skills
            ):
                registry = Registry(
                    tuple(
                        replace(skill, enabled=False) if skill.skill_id == "feedback" else skill
                        for skill in registry.skills.values()
                    ),
                    frozenset(self.executors),
                )
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
                    max_tokens=budget.initial_tokens,
                    max_retries=budget.max_retries,
                    length_recovery_enabled=True,
                    length_recovery_max_tokens=budget.recovery_tokens,
                )
                client = LLMClient(config, storage=storage)
                client.client = client.client.with_options(max_retries=0)

                def model(prompt: str, _remaining: float) -> str:
                    first_request = True

                    def before_request() -> float:
                        nonlocal first_request
                        timeout = context.take_provider_request(prepaid=first_request)
                        first_request = False
                        return timeout

                    extra_body = (
                        {"thinking": {"type": "disabled"}}
                        if config.llm_provider == "deepseek" and config.model == "deepseek-flash"
                        else None
                    )
                    raw = client.generate(
                        messages=[
                            {"role": "system", "content": "Return the requested JSON object."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0,
                        response_format={"type": "json_object"},
                        extra_body=extra_body,
                        before_request=before_request,
                    )
                    return _normalize_json_object_label(raw)

            verified_target = selected_target
            found_targets: set[tuple[str, str]] = set()
            found_evidence_targets: dict[str, SelectedTarget] = {}
            body_read_targets: set[tuple[str, str]] = set()
            help_citations: dict[str, HelpCitation] = {}
            source_citations: dict[str, SourceCitation] = {}
            resource_file_citations: dict[str, list[SourceCitation]] = {}
            resource_file_targets: dict[str, SelectedTarget | None] = {}
            help_answers: dict[str, str] = {}
            weekly_actions: set[str] = set()
            weekly_guide_ids: set[str] = set()
            weekly_empty: dict[str, str] = {}
            resource_answers: dict[str, str] = {}
            if verified_target is not None:
                current_facade = DocumentResearch(
                    storage, authorized_kbs=lambda: permitted_kbs(request, auth)
                )
                try:
                    if current_facade._document(verified_target) is None:
                        verified_target = None
                except PermissionError:
                    verified_target = None

            def execute(tool, args: dict, run_context: RunContext, _remaining: float) -> ToolResult:
                nonlocal verified_target
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
                if args.get("kb_id") is not None and args["kb_id"] not in permitted_kbs(
                    request, current
                ):
                    raise PermissionError("KB target is outside current scope")
                run_context.remaining()
                if tool.executor == "feedback.draft":
                    if not getattr(request.app.state, "feedback_enabled", False):
                        return ToolResult("unavailable", {"message": "Feedback is disabled."})
                    return self.executors[tool.executor]({"text": message})
                if tool.executor == "usage_navigation.guide":
                    result = self.executors[tool.executor](
                        {**args, "language": "zh" if locale.startswith("zh") else "en"}
                    )
                    for evidence_id, item in zip(
                        result.evidence_ids, result.data.get("sections", [])
                    ):
                        help_citations[evidence_id] = HelpCitation(
                            **item["reference"],
                            title=item["document_title"],
                            source_type="help",
                            link=item["link"],
                        )
                        help_answers[evidence_id] = item["content"]
                        if item.get("action") == "/weekly":
                            weekly_actions.add(evidence_id)
                            weekly_guide_ids.add(evidence_id)
                    return result
                if (
                    tool.executor.startswith(("document_research.", "resources_updates."))
                    or tool.result_kind == "catalog_discovery"
                ):
                    if tool.executor in {
                        "document_research.read_document_sections",
                        "document_research.search_knowledge",
                        "document_research.readiness",
                    }:
                        requested = (args["kb_id"], args["file_id"])
                        if (
                            verified_target is not None
                            and requested != (verified_target.kb_id, verified_target.file_id)
                            and requested not in found_targets
                        ):
                            raise PermissionError("New target requires a current find")
                    facade = DocumentResearch(
                        storage,
                        authorized_kbs=lambda: permitted_kbs(request, current),
                        deadline=run_context.deadline,
                        on_embedding=run_context.take_embedding,
                    )
                    result = self.executors[tool.executor](facade, args)
                    if result.status == "ok" and tool.executor.startswith("resources_updates."):
                        answer = resources_executors.grounded_answer(
                            tool.executor, result.data, locale
                        )
                        if answer:
                            resource_answers.update({item: answer for item in result.evidence_ids})
                    if result.status == "ok" and tool.executor in {
                        "resources_updates.recent",
                        "resources_updates.catalog_search",
                    }:
                        files = result.data.get("files", [])
                        cards: list[SourceCitation] = []
                        single_target = None
                        for item in files:
                            url = item.get("source_url") if isinstance(item, dict) else None
                            if not isinstance(url, str) or not url or len(url) > 1024:
                                continue
                            documents = [
                                document
                                for kb_id in permitted_kbs(request, current)
                                if (
                                    document := facade._document(
                                        SelectedTarget(kb_id=kb_id, file_id=url)
                                    )
                                )
                                is not None
                                and document.source_url == url
                            ]
                            document = documents[0] if documents else None
                            cards.append(
                                SourceCitation(
                                    source_type="catalog",
                                    file_id=url,
                                    kb_id=(
                                        document.target.kb_id
                                        if document and len(documents) == 1
                                        else None
                                    ),
                                    title=(
                                        document.title
                                        if document
                                        else str(item.get("title") or url)
                                    ),
                                    link=(
                                        document.internal_link
                                        if document
                                        else "/file-detail?" + urlencode({"url": url})
                                    ),
                                    source_date=(
                                        document.publication_date
                                        if document
                                        else str(
                                            item.get("publication_date")
                                            or item.get("published_time")
                                            or ""
                                        )
                                        or None
                                    ),
                                )
                            )
                            found_targets.update(
                                (member.target.kb_id, member.target.file_id) for member in documents
                            )
                            if len(files) == 1 and len(documents) == 1:
                                single_target = document.target
                        for evidence_id in result.evidence_ids:
                            resource_file_citations[evidence_id] = cards
                            resource_file_targets[evidence_id] = single_target
                    if tool.executor == "resources_updates.weekly" and result.status == "ok":
                        weekly_actions.update(result.evidence_ids)
                        if result.data.get("snapshot") is None:
                            weekly_empty.update(
                                {item: "no_snapshot" for item in result.evidence_ids}
                            )
                        elif result.data.get("total") == 0:
                            weekly_empty.update({item: "no_new" for item in result.evidence_ids})
                    if result.status == "ok" and tool.result_kind == "catalog_discovery":
                        documents = result.discovery_documents()
                        for item in documents:
                            target = SelectedTarget.model_validate(item["target"])
                            current_document = facade._document(target)
                            if (
                                current_document is None
                                or current_document.source_url != item["source_url"]
                            ):
                                raise ValueError("Catalog target is no longer current")
                        found_targets.update(
                            (item["target"]["kb_id"], item["target"]["file_id"])
                            for item in documents
                        )
                        found_evidence_targets.update(
                            (evidence_id, SelectedTarget.model_validate(item["target"]))
                            for evidence_id, item in zip(result.evidence_ids, documents)
                        )
                        source_citations.update(
                            (
                                evidence_id,
                                SourceCitation(
                                    source_type="catalog",
                                    file_id=item["target"]["file_id"],
                                    kb_id=item["target"]["kb_id"],
                                    title=item["title"],
                                    link=item["internal_link"],
                                    source_date=item.get("publication_date"),
                                ),
                            )
                            for evidence_id, item in zip(result.evidence_ids, documents)
                        )
                        if len(documents) == 1:
                            verified_target = SelectedTarget.model_validate(documents[0]["target"])
                    if result.status == "ok" and tool.executor in {
                        "document_research.read_document_sections",
                        "document_research.search_knowledge",
                    }:
                        document = facade._document(
                            SelectedTarget(kb_id=args["kb_id"], file_id=args["file_id"])
                        )
                        if document:
                            source_citations.update(
                                (
                                    evidence_id,
                                    SourceCitation(
                                        source_type=(
                                            "kb" if section.get("section_id") else "catalog"
                                        ),
                                        file_id=document.target.file_id,
                                        kb_id=document.target.kb_id,
                                        section_id=section.get("section_id", ""),
                                        title=document.title,
                                        link=document.internal_link,
                                        source_version=section.get("source_version"),
                                        source_date=document.publication_date,
                                        stale=section.get("serving_stale", False),
                                    ),
                                )
                                for evidence_id, section in zip(
                                    result.evidence_ids,
                                    result.data.get("sections")
                                    or [result.data.get("document", {})],
                                )
                            )
                        body_read_targets.add((args["kb_id"], args["file_id"]))
                        verified_target = SelectedTarget(
                            kb_id=args["kb_id"], file_id=args["file_id"]
                        )
                    if (
                        result.status == "not_found"
                        and args.get("file_id")
                        and verified_target is not None
                        and (args["kb_id"], args["file_id"])
                        == (verified_target.kb_id, verified_target.file_id)
                    ):
                        verified_target = None
                    return result
                return self.executors[tool.executor](args)

            def resolve_selected_document(target: dict[str, str]) -> dict | None:
                nonlocal verified_target
                key = (target["kb_id"], target["file_id"])
                if key not in found_targets and (
                    verified_target is None or verified_target.model_dump() != target
                ):
                    return None
                try:
                    if hasattr(request.state, "auth_context"):
                        del request.state.auth_context
                    current = deps.get_auth_context(request)
                    scopes = (
                        current.permissions
                        if current.token
                        else public_permissions_for_request(request)
                    )
                    required = (
                        {"chat.query", "catalog.read", "files.read"}
                        if key in found_targets
                        else {"chat.query", "markdown.read"}
                    )
                    if key in body_read_targets:
                        required.add("markdown.read")
                    if _identity(current) != initial_identity or not required <= scopes:
                        return None
                    facade = DocumentResearch(
                        storage,
                        authorized_kbs=lambda: permitted_kbs(request, current),
                        deadline=context.deadline,
                    )
                    document = facade._document(SelectedTarget.model_validate(target))
                    if (
                        document is None
                        and verified_target is not None
                        and verified_target.model_dump() == target
                    ):
                        verified_target = None
                    return document.model_dump() if document else None
                except TimeoutError:
                    raise
                except Exception:
                    return None

            runtime = run(
                message=message,
                locale=locale,
                registry=registry,
                context=context,
                model=model,
                execute=execute,
                selected_target=verified_target.model_dump() if verified_target else None,
                recent_questions=recent_questions or [],
                resolve_selected_document=resolve_selected_document,
            )
            response = self._response(runtime, locale)
            response.citations = [
                help_citations[item] for item in runtime.evidence_ids if item in help_citations
            ]
            if runtime.kind == "finish" and runtime.error_code != "SCOPE_REVOKED":
                response.citations.extend(
                    source_citations[item]
                    for item in runtime.evidence_ids
                    if item in source_citations
                )
                response.citations.extend(
                    citation
                    for item in runtime.evidence_ids
                    for citation in resource_file_citations.get(item, [])
                )
            weekly_used = runtime.kind == "finish" and bool(
                weekly_actions.intersection(runtime.evidence_ids)
            )
            weekly_guide_used = bool(weekly_guide_ids.intersection(runtime.evidence_ids))
            weekly_access: bool | None = None
            if weekly_used:
                try:
                    if hasattr(request.state, "auth_context"):
                        del request.state.auth_context
                    current = deps.get_auth_context(request)
                    current_scopes = (
                        current.permissions
                        if current.token
                        else public_permissions_for_request(request)
                    )
                    weekly_access = (
                        _identity(current) == initial_identity
                        and {
                            "chat.query",
                            "files.read",
                        }
                        <= current_scopes
                    )
                except Exception:
                    pass
            if runtime.kind == "finish":
                weekly_guide_answer = (
                    (
                        "首页周报卡片的‘查看全部’通往周报页。有快照时，页面展示最近一期完整已发布的周期，未结束的本周不在其中；也可选择较早的已发布周期。有权访问周报清单时，可打开其中资料阅读详情、原文链接，以及可用的预览或 Markdown。"
                        if locale.startswith("zh")
                        else "The Dashboard's weekly View all leads to the Weekly page. When available, it shows the latest complete published period, not an unfinished current week; you can select an older published period. When you can access a weekly list, open a listed file to read its details, source link, and a preview or Markdown when available."
                    )
                    if weekly_guide_used
                    else ""
                )
                grounded = [
                    resource_answers[item]
                    for item in runtime.evidence_ids
                    if item in resource_answers
                ]
                if grounded:
                    response.answer = "\n\n".join(dict.fromkeys(grounded))
                    if weekly_guide_used:
                        response.answer = weekly_guide_answer + "\n\n" + response.answer
                elif weekly_guide_used:
                    response.answer = weekly_guide_answer
                    if weekly_access:
                        try:
                            context.remaining()
                            snapshot = storage.get_latest_weekly_snapshot(
                                now=datetime.now(timezone.utc).isoformat()
                            )
                            if snapshot is None:
                                response.answer += (
                                    " 目前没有完整已发布的周报快照。"
                                    if locale.startswith("zh")
                                    else " No complete published weekly snapshot is available yet."
                                )
                            elif snapshot.get("period_start") and snapshot.get("period_end"):
                                response.answer += (
                                    f" 最近已发布周期：{snapshot['period_start']} 至 {snapshot['period_end']}。"
                                    if locale.startswith("zh")
                                    else f" Latest published period: {snapshot['period_start']} to {snapshot['period_end']}."
                                )
                        except Exception:
                            pass
                else:
                    guide_answers = [
                        help_answers[item] for item in runtime.evidence_ids if item in help_answers
                    ]
                    if guide_answers:
                        response.answer = "\n\n".join(dict.fromkeys(guide_answers))
            if weekly_used:
                if weekly_access is not True:
                    if weekly_access is False:
                        notice = (
                            "当前账户无法打开周报页。请登录有资料读取权限的账户，或联系管理员开通权限。"
                            if locale.startswith("zh")
                            else "You cannot open the Weekly page with your current access. Sign in with a permitted account or ask an administrator for access."
                        )
                    else:
                        notice = (
                            "无法核实当前周报访问权限；请重新登录或联系管理员。"
                            if locale.startswith("zh")
                            else "Current Weekly access could not be verified; sign in again or ask an administrator."
                        )
                    response.answer = (response.answer + " " if weekly_guide_used else "") + notice
                else:
                    empty = next(
                        (
                            weekly_empty[item]
                            for item in runtime.evidence_ids
                            if item in weekly_empty
                        ),
                        None,
                    )
                    if empty == "no_snapshot":
                        status = (
                            "目前没有完整已发布的周报快照。"
                            if locale.startswith("zh")
                            else "No complete published weekly snapshot is available yet."
                        )
                        response.answer = (
                            weekly_guide_answer + " " if weekly_guide_used else ""
                        ) + status
                    elif empty == "no_new":
                        status = (
                            "最近一期已发布周报按系统首次收录时间统计，没有新增资料。"
                            if locale.startswith("zh")
                            else "The latest published weekly period has no newly first-collected files."
                        )
                        response.answer = (
                            weekly_guide_answer + " " if weekly_guide_used else ""
                        ) + status
                    if not re.search(r"\[[^\]]+\]\(/weekly\)", response.answer):
                        response.answer += (
                            "\n\n打开[周报](/weekly)。"
                            if locale.startswith("zh")
                            else "\n\nOpen [Weekly](/weekly)."
                        )
            if (
                runtime.kind == "finish"
                and getattr(request.app.state, "feedback_enabled", False)
                and any(
                    item.tool_id == "feedback.draft" and item.status == "ok"
                    for item in runtime.trace
                )
            ):
                response.intent = "feedback"
                response.feedback_draft = message
                response.answer = (
                    "这只是草稿。请检查、编辑后确认提交；尚未记录。"
                    if locale.startswith("zh")
                    else "This is only a draft. Review, edit and confirm to submit; nothing is recorded yet."
                )
            if runtime.error_code == "SCOPE_REVOKED":
                verified_target = None
            elif runtime.kind == "finish" and len(runtime.evidence_ids) == 1:
                evidence_id = runtime.evidence_ids[0]
                if evidence_id in resource_file_targets:
                    verified_target = resource_file_targets[evidence_id]
                else:
                    verified_target = found_evidence_targets.get(evidence_id, verified_target)
            response.selected_target = verified_target.model_dump() if verified_target else None
            return Outcome(response, runtime, session_update)
        finally:
            if client is not None:
                client.client.close()
            storage.close()

    @staticmethod
    def _response(runtime: RunResult, locale: str) -> FeatureResponse:
        zh = locale.startswith("zh")
        errors = {
            "QUOTA_EXCEEDED": (
                "每日 AI 额度已用完；可免 AI 查阅使用指南，或在 UTC 日期重置后重试。",
                "Daily AI quota reached. Open the guide without AI or retry after the UTC reset.",
            ),
            "SCOPE_REVOKED": (
                "当前身份或权限已变化；请重新登录，或联系管理员确认权限。",
                "Your identity or access changed. Sign in again or ask an administrator to check access.",
            ),
            "ASSISTANT_TIMEOUT": (
                "助手超时；请稍后重试，或免 AI 查阅使用指南。",
                "The assistant timed out. Retry or open the guide without AI.",
            ),
            "PROVIDER_UNAVAILABLE": (
                "模型暂不可用；请稍后重试，或免 AI 查阅使用指南。",
                "The model is unavailable. Retry later or open the guide without AI.",
            ),
            "PROVIDER_RATE_LIMITED": (
                "模型请求过于频繁；请稍后重试，或免 AI 查阅使用指南。",
                "The model is rate limited. Retry later or open the guide without AI.",
            ),
            "NO_EVIDENCE": (
                "没有可核验的当前证据；请缩小问题范围或打开资料原文。",
                "No current evidence was found. Narrow the question or open the source file.",
            ),
        }
        answer = runtime.answer or (
            errors[runtime.error_code][int(not zh)]
            if runtime.error_code in errors
            else "请补充更多细节或稍后重试。" if zh else "Please add more detail or retry later."
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

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ai_actuarial.security import UnsafeUrlError, ensure_safe_http_url

SCHEMA_VERSION = "web-listening-agent-rule.v1"
DEFAULT_FILE_EXTS = [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"]
_DEFAULT_EXCLUDE_KEYWORDS = ["newsletter", "news letter", "login", "signin", "register"]
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


class WebListeningRuleError(ValueError):
    pass


class AcquisitionProfile(BaseModel):
    name: str = Field(..., min_length=1)
    website_url: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    max_pages: int = Field(default=25, ge=1, le=1000)
    max_depth: int = Field(default=2, ge=0, le=10)
    delay_seconds: float = Field(default=0.5, ge=0, le=60)
    file_exts: list[str] = Field(default_factory=lambda: list(DEFAULT_FILE_EXTS))
    collect_page_content: bool = True

    @field_validator("name", "website_url", "goal")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("must be non-empty")
        return normalized

    @field_validator("file_exts")
    @classmethod
    def _normalize_file_exts(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value or []:
            ext = str(item or "").strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = f".{ext}"
            if ext not in out:
                out.append(ext)
        return out or list(DEFAULT_FILE_EXTS)


class MonitorTask(BaseModel):
    name: str = Field(..., min_length=1)
    schedule_interval: str = "weekly"
    enabled: bool = True

    @field_validator("name", "schedule_interval")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("must be non-empty")
        return normalized


class SectionSelection(BaseModel):
    content_selector: str | None = None
    allow_url_patterns: list[str] = Field(default_factory=list)

    @field_validator("content_selector")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("allow_url_patterns")
    @classmethod
    def _normalize_patterns(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value or []:
            pattern = str(item or "").strip()
            if not pattern:
                continue
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
            if pattern not in out:
                out.append(pattern)
        return out


class MonitorScope(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=lambda: list(_DEFAULT_EXCLUDE_KEYWORDS))
    exclude_prefixes: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)

    @field_validator("keywords", "exclude_keywords", "exclude_prefixes", "queries")
    @classmethod
    def _normalize_string_list(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value or []:
            normalized = str(item or "").strip()
            if normalized and normalized not in out:
                out.append(normalized)
        return out


class WebListeningAgentRuleV1(BaseModel):
    schema_version: Literal["web-listening-agent-rule.v1"] = SCHEMA_VERSION
    acquisition_profile: AcquisitionProfile
    monitor_task: MonitorTask
    section_selection: SectionSelection = Field(default_factory=SectionSelection)
    monitor_scope: MonitorScope = Field(default_factory=MonitorScope)

    @model_validator(mode="after")
    def _validate_url_and_schedule(self) -> "WebListeningAgentRuleV1":
        url = self.acquisition_profile.website_url
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("acquisition_profile.website_url must be an absolute http(s) URL")
        if not _is_valid_schedule_interval(self.monitor_task.schedule_interval):
            raise ValueError("monitor_task.schedule_interval must be daily, weekly, daily at HH:MM, or every N hours/minutes")
        return self


class MaterializedConfig(BaseModel):
    site: dict[str, Any]
    scheduled_task: dict[str, Any]
    acquisition_profile: AcquisitionProfile
    monitor_task: MonitorTask
    section_selection: SectionSelection
    monitor_scope: MonitorScope


def rule_from_yaml_or_dict(value: str | dict[str, Any]) -> WebListeningAgentRuleV1:
    if isinstance(value, str):
        try:
            parsed = yaml.safe_load(value) or {}
        except yaml.YAMLError as exc:
            raise WebListeningRuleError(f"Invalid YAML: {exc}") from exc
    elif isinstance(value, dict):
        parsed = dict(value)
    else:
        raise WebListeningRuleError("Rule must be a YAML string or object")
    try:
        return WebListeningAgentRuleV1.model_validate(parsed)
    except ValidationError as exc:
        raise WebListeningRuleError(_validation_error_text(exc)) from exc


def validate_rule(value: str | dict[str, Any], *, check_url_safety: bool = True) -> tuple[WebListeningAgentRuleV1 | None, list[str], list[str]]:
    warnings: list[str] = []
    try:
        rule = rule_from_yaml_or_dict(value)
    except WebListeningRuleError as exc:
        return None, [str(exc)], warnings
    if check_url_safety:
        try:
            ensure_safe_http_url(rule.acquisition_profile.website_url)
        except UnsafeUrlError as exc:
            return None, [f"Unsafe website URL: {exc}"], warnings
    if not rule.monitor_scope.keywords:
        warnings.append("monitor_scope.keywords is empty; crawler will treat all pages as relevant.")
    if not rule.section_selection.allow_url_patterns:
        warnings.append("section_selection.allow_url_patterns is empty; crawl scope is domain-wide within max_depth.")
    return rule, [], warnings


def generate_draft_rule(*, website_url: str, goal: str, name: str | None = None) -> WebListeningAgentRuleV1:
    url = str(website_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WebListeningRuleError("website_url must be an absolute http(s) URL")
    goal_text = str(goal or "").strip()
    if not goal_text:
        raise WebListeningRuleError("goal is required")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    site_name = str(name or "").strip() or f"Web Listening: {host}"
    keywords = _keywords_from_goal(goal_text)
    path_pattern = re.escape(parsed.path.rstrip("/") or "/")
    allow_patterns = [path_pattern] if parsed.path and parsed.path != "/" else []
    acquisition = AcquisitionProfile(name=site_name, website_url=url, goal=goal_text)
    monitor_task = MonitorTask(name=f"{site_name} Monitor", schedule_interval="weekly", enabled=True)
    section_selection = SectionSelection(content_selector="main", allow_url_patterns=allow_patterns)
    scope = MonitorScope(
        keywords=keywords,
        exclude_keywords=list(_DEFAULT_EXCLUDE_KEYWORDS),
        exclude_prefixes=[],
        queries=[f"site:{host} {goal_text} filetype:pdf"],
    )
    return WebListeningAgentRuleV1(
        acquisition_profile=acquisition,
        monitor_task=monitor_task,
        section_selection=section_selection,
        monitor_scope=scope,
    )


def rule_to_yaml(rule: WebListeningAgentRuleV1) -> str:
    return yaml.safe_dump(rule.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


def materialize_rule(rule: WebListeningAgentRuleV1) -> MaterializedConfig:
    acquisition = rule.acquisition_profile
    task = rule.monitor_task
    sections = rule.section_selection
    scope = rule.monitor_scope
    site: dict[str, Any] = {
        "name": acquisition.name,
        "url": acquisition.website_url,
        "max_pages": acquisition.max_pages,
        "max_depth": acquisition.max_depth,
        "delay_seconds": acquisition.delay_seconds,
        "file_exts": list(acquisition.file_exts),
        "collect_page_content": acquisition.collect_page_content,
        "web_listening_rule_schema_version": rule.schema_version,
    }
    if scope.keywords:
        site["keywords"] = list(scope.keywords)
    if scope.exclude_keywords:
        site["exclude_keywords"] = list(scope.exclude_keywords)
    if scope.exclude_prefixes:
        site["exclude_prefixes"] = list(scope.exclude_prefixes)
    if sections.content_selector:
        site["content_selector"] = sections.content_selector
    if sections.allow_url_patterns:
        site["allow_url_patterns"] = list(sections.allow_url_patterns)
    if scope.queries:
        site["queries"] = list(scope.queries)

    scheduled_task = {
        "name": task.name,
        "type": "full_pipeline",
        "interval": task.schedule_interval,
        "enabled": task.enabled,
        "params": {
            "source_collection_type": "scheduled",
            "site": acquisition.name,
            "name": f"Full Pipeline: {acquisition.name}",
            "check_database": True,
            "run_rag_indexing": False,
        },
        "web_listening_rule_schema_version": rule.schema_version,
    }
    return MaterializedConfig(
        site=site,
        scheduled_task=scheduled_task,
        acquisition_profile=acquisition,
        monitor_task=task,
        section_selection=sections,
        monitor_scope=scope,
    )


def _keywords_from_goal(goal: str) -> list[str]:
    stop = {"and", "the", "for", "from", "with", "about", "into", "latest", "updates", "update", "monitor", "track", "find"}
    out: list[str] = []
    for match in _WORD_RE.finditer(goal.lower()):
        word = match.group(0).strip("-_")
        if word and word not in stop and word not in out:
            out.append(word)
        if len(out) >= 8:
            break
    return out or [goal.strip()]


def _is_valid_schedule_interval(interval: str) -> bool:
    normalized = str(interval or "").strip().lower()
    if normalized in {"daily", "weekly"}:
        return True
    if normalized.startswith("daily at "):
        parts = normalized.replace("daily at ", "", 1).strip().split(":", 1)
        if len(parts) != 2:
            return False
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            return False
        return 0 <= hour <= 23 and 0 <= minute <= 59
    if normalized.startswith("every "):
        parts = normalized.split()
        if len(parts) != 3:
            return False
        try:
            qty = int(parts[1])
        except ValueError:
            return False
        return qty > 0 and parts[2] in {"hour", "hours", "minute", "minutes"}
    return False


def _validation_error_text(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ())) or "rule"
        parts.append(f"{loc}: {error.get('msg', 'invalid value')}")
    return "; ".join(parts) or str(exc)

"""Values exchanged by the runtime and its Host ports."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Literal, Mapping


@dataclass(frozen=True)
class AgentBudget:
    initial_tokens: int = 3000
    recovery_tokens: int = 4000
    max_retries: int = 3
    model_requests: int = 6
    total_seconds: float = 180.0
    request_seconds: float = 60.0

    @classmethod
    def from_config(cls, section: Mapping[str, Any]) -> "AgentBudget":
        defaults = cls()
        names = (
            "initial_tokens",
            "recovery_tokens",
            "max_retries",
            "model_requests",
            "total_seconds",
            "request_seconds",
        )
        unknown = set(section) - set(names)
        if unknown:
            raise ValueError(f"Unknown assistant_agent budget keys: {sorted(unknown)}")
        values = {}
        for name in names:
            raw = section.get(name, getattr(defaults, name))
            if isinstance(raw, bool):
                raise ValueError(f"assistant_agent.{name} must be numeric")
            try:
                values[name] = (float if name.endswith("seconds") else int)(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"assistant_agent.{name} must be numeric") from exc
            if (name.endswith("seconds") and not math.isfinite(values[name])) or (
                not name.endswith("seconds") and isinstance(raw, float) and not raw.is_integer()
            ):
                raise ValueError(f"assistant_agent.{name} must be finite and whole where required")
        budget = cls(**values)
        for name in names:
            value = getattr(budget, name)
            if value <= 0:
                raise ValueError(f"assistant_agent.{name} must be positive")
        if budget.recovery_tokens <= budget.initial_tokens:
            raise ValueError("assistant_agent.recovery_tokens must exceed initial_tokens")
        return budget


@dataclass(frozen=True)
class ToolResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    error_code: str | None = None

    def discovery_documents(self) -> list[dict[str, Any]]:
        documents = self.data.get("documents")
        if (
            self.status != "ok"
            or not isinstance(documents, list)
            or not documents
            or len(documents) != len(self.evidence_ids)
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
            or any(
                not isinstance(document, dict)
                or not isinstance(document.get("target"), dict)
                or not all(
                    isinstance(document["target"].get(key), str) and document["target"][key]
                    for key in ("kb_id", "file_id")
                )
                or not isinstance(document.get("title"), str)
                or not document["title"]
                or not isinstance(document.get("source_url"), str)
                or not document["source_url"]
                for document in documents
            )
        ):
            raise ValueError("Invalid catalog discovery result")
        return documents


@dataclass(frozen=True)
class ToolTrace:
    skill_id: str
    tool_id: str
    status: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunResult:
    answer: str
    availability: str
    error_code: str | None
    evidence_ids: tuple[str, ...]
    model_attempts: int
    tool_attempts: int
    embedding_attempts: int
    trace: tuple[ToolTrace, ...]
    kind: Literal["finish", "clarify", "error"] = "error"


class RunContext:
    """Host-owned identity and fixed per-question attempt budgets."""

    def __init__(
        self,
        *,
        principal: str,
        scopes: frozenset[str],
        cancelled: Event | None = None,
        deadline: float | None = None,
        budget: AgentBudget | None = None,
    ):
        self.principal = principal
        self.scopes = scopes
        self.cancelled = cancelled or Event()
        self.budget = budget or AgentBudget()
        self.deadline = min(
            deadline if deadline is not None else time.monotonic() + self.budget.total_seconds,
            time.monotonic() + self.budget.total_seconds,
        )
        self.model_attempts = 0
        self.provider_requests = 0
        self.reserve_verifier = False
        self.tool_attempts = 0
        self.embedding_attempts = 0

    def remaining(self) -> float:
        if self.cancelled.is_set():
            raise TimeoutError("cancelled")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deadline")
        return remaining

    def take_model(self) -> float:
        remaining = self.remaining()
        if self.model_attempts >= self.budget.model_requests:
            raise TimeoutError("model budget")
        self.model_attempts += 1
        return remaining

    def take_provider_request(self, *, prepaid: bool = False) -> float:
        remaining = self.remaining()
        limit = self.budget.model_requests - int(self.reserve_verifier)
        if self.model_attempts > limit or (
            prepaid and self.model_attempts <= self.provider_requests
        ):
            raise TimeoutError("model budget")
        if not prepaid:
            if self.model_attempts >= limit:
                raise TimeoutError("model budget")
            self.model_attempts += 1
        self.provider_requests += 1
        return min(self.budget.request_seconds, remaining)

    def take_tool(self) -> float:
        remaining = self.remaining()
        if self.tool_attempts >= 6:
            raise TimeoutError("tool budget")
        self.tool_attempts += 1
        return remaining

    def take_embedding(self) -> float:
        remaining = self.remaining()
        if self.embedding_attempts >= 2:
            raise TimeoutError("embedding budget")
        self.embedding_attempts += 1
        return remaining

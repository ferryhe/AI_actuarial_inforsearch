"""Values exchanged by the runtime and its Host ports."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Literal


@dataclass(frozen=True)
class ToolResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    error_code: str | None = None


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
    ):
        self.principal = principal
        self.scopes = scopes
        self.cancelled = cancelled or Event()
        self.deadline = min(
            deadline if deadline is not None else time.monotonic() + 30, time.monotonic() + 30
        )
        self.model_attempts = 0
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
        if self.model_attempts >= 4:
            raise TimeoutError("model budget")
        self.model_attempts += 1
        return remaining

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

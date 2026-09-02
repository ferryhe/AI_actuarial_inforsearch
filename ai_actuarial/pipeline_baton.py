from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ai_actuarial.embedding_service import (
    LEGACY_CHUNK_OPTIONS,
    sanitize_legacy_chunk_generation_payload,
)

PIPELINE_STEPS = (
    "scheduled",
    "markdown_conversion",
    "catalog",
    "chunk_generation",
    "rag_indexing",
)
CONFIGURABLE_STEPS = PIPELINE_STEPS[1:]
_TERMINAL_ROUNDS = frozenset({"completed", "error", "stopped"})
_FORBIDDEN_OVERRIDE_KEYS = frozenset({"type", "name", "file_urls"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineBaton:
    """Fixed five-step dispatcher backed by one compact JSON document."""

    def __init__(
        self,
        *,
        state_path: str | Path,
        start_task: Callable[..., str],
        task_status: Callable[[str], str | None],
        task_result: Callable[[str], dict[str, Any] | None] | None = None,
        indexable_kb_ids: Callable[[], list[str]],
        kb_index_input: Callable[[str], dict[str, Any]] | None = None,
        ready_data_input: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        now: Callable[[], str] = _utc_now,
    ) -> None:
        self._state_path = Path(state_path)
        self._start_task = start_task
        self._task_status = task_status
        self._task_result = task_result or (lambda _task_id: None)
        self._indexable_kb_ids = indexable_kb_ids
        self._kb_index_input = kb_index_input
        self._ready_data_input = ready_data_input
        self._now = now
        self._lock = threading.RLock()

    @staticmethod
    def _empty_document() -> dict[str, Any]:
        return {
            "config": {"overrides": {}},
            "state": {
                "current_step": None,
                "current_task_id": None,
                "current_rag_kb": None,
                "round_status": "idle",
                "last_check": None,
                "consumed_scheduled_task_id": None,
                "chunk_embedding_phase": None,
                "chunk_task_id": None,
                "embedding_task_id": None,
                "kb_index_ready_phase": None,
                "kb_index_task_id": None,
                "ready_data_task_id": None,
                "kb_results": [],
                "summary": {
                    "attempted": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "failed_kbs": [],
                },
            },
        }

    def _load(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return self._empty_document()
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_document()
        empty = self._empty_document()
        config = raw.get("config") if isinstance(raw, dict) else None
        state = raw.get("state") if isinstance(raw, dict) else None
        if isinstance(config, dict) and isinstance(config.get("overrides"), dict):
            overrides = dict(config["overrides"])
            chunk_override = overrides.get("chunk_generation")
            if isinstance(chunk_override, dict):
                sanitized = sanitize_legacy_chunk_generation_payload(chunk_override)
                if sanitized:
                    overrides["chunk_generation"] = sanitized
                else:
                    overrides.pop("chunk_generation", None)
            empty["config"]["overrides"] = overrides
        if isinstance(state, dict):
            for key in empty["state"]:
                if key in state:
                    empty["state"][key] = state[key]
        return empty

    def _save(self, document: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def configure(self, overrides: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, dict[str, Any]] = {}
        for step, payload in overrides.items():
            if step not in CONFIGURABLE_STEPS:
                raise ValueError(f"Unknown pipeline step: {step}")
            if not isinstance(payload, dict):
                raise ValueError(f"Pipeline override for {step} must be an object")
            forbidden = _FORBIDDEN_OVERRIDE_KEYS.intersection(payload)
            if step == "chunk_generation":
                forbidden = forbidden.union(LEGACY_CHUNK_OPTIONS.intersection(payload))
            if step == "rag_indexing":
                forbidden = forbidden.union(
                    {"kb_id", "force_reindex", "incremental"}.intersection(payload)
                )
            if forbidden:
                raise ValueError(
                    f"Pipeline override for {step} cannot set: {', '.join(sorted(forbidden))}"
                )
            if payload:
                normalized[step] = dict(payload)
        with self._lock:
            document = self._load()
            document["config"] = {"overrides": normalized}
            self._save(document)
            return self.status()

    def start(self, scheduled_task_id: str) -> dict[str, Any]:
        scheduled_task_id = str(scheduled_task_id or "").strip()
        if not scheduled_task_id:
            raise ValueError("Scheduled Collection task ID is required")
        with self._lock:
            document = self._load()
            state = document["state"]
            if state["round_status"] == "running":
                return self._view(document)
            if state["consumed_scheduled_task_id"] == scheduled_task_id:
                return self._view(document)
            document["state"] = {
                "current_step": "scheduled",
                "current_task_id": scheduled_task_id,
                "current_rag_kb": None,
                "round_status": "running",
                "last_check": self._now(),
                "consumed_scheduled_task_id": scheduled_task_id,
                "chunk_embedding_phase": None,
                "chunk_task_id": None,
                "embedding_task_id": None,
                "kb_index_ready_phase": None,
                "kb_index_task_id": None,
                "ready_data_task_id": None,
                "kb_results": [],
                "summary": {
                    "attempted": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "failed_kbs": [],
                },
            }
            self._save(document)
            return self._view(document)

    def tick(self) -> dict[str, Any]:
        with self._lock:
            document = self._load()
            state = document["state"]
            if state["round_status"] != "running":
                return self._view(document)

            state["last_check"] = self._now()
            current_step = str(state["current_step"] or "")
            if current_step not in PIPELINE_STEPS:
                state["round_status"] = "error"
                self._save(document)
                return self._view(document)

            try:
                task_status = self._task_status(str(state["current_task_id"] or ""))
            except Exception:  # noqa: BLE001 - a broken task read is terminal for this round
                state["round_status"] = "error"
                self._save(document)
                return self._view(document)
            if task_status is None:
                state["round_status"] = "error"
                self._save(document)
                return self._view(document)
            if task_status in {"pending", "running"}:
                self._save(document)
                return self._view(document)
            if task_status not in {"completed", "error", "stopped"}:
                state["round_status"] = "error"
                self._save(document)
                return self._view(document)

            if current_step == "rag_indexing":
                if task_status == "stopped":
                    state["round_status"] = "stopped"
                else:
                    try:
                        self._advance_rag_step(document, task_status)
                    except Exception:  # noqa: BLE001 - hard orchestration failure
                        state["round_status"] = "error"
                self._save(document)
                return self._view(document)

            if task_status == "stopped":
                state["round_status"] = "stopped"
                self._save(document)
                return self._view(document)
            try:
                successful_outputs = self._successful_output_count(document)
                if successful_outputs <= 0:
                    state["round_status"] = "completed" if task_status == "completed" else "error"
                else:
                    self._advance_non_kb_step(document, current_step)
            except Exception:  # noqa: BLE001 - hard orchestration failure
                state["round_status"] = "error"
            self._save(document)
            return self._view(document)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._view(self._load())

    def _start_step(self, document: dict[str, Any], step: str, *, kb_id: str | None = None) -> None:
        overrides = document["config"]["overrides"]
        payload = dict(overrides.get(step) or {})
        if step == "chunk_generation":
            payload = sanitize_legacy_chunk_generation_payload(payload)
        if step == "rag_indexing":
            if self._kb_index_input is not None:
                payload = dict(self._kb_index_input(str(kb_id or "")))
            else:
                payload.update({"kb_id": kb_id, "incremental": True, "force_reindex": False})
        source_task_id = str(document["state"]["consumed_scheduled_task_id"])
        extra_fields = {
            "pipeline_baton_step": step,
            "pipeline_baton_source_task_id": source_task_id,
        }
        if kb_id is not None:
            extra_fields["pipeline_baton_kb_id"] = kb_id
        if step == "rag_indexing":
            extra_fields["pipeline_baton_subtask"] = "kb_index"
        task_id = self._start_task(
            step,
            payload,
            task_name=f"Pipeline: {step.replace('_', ' ').title()}",
            extra_fields=extra_fields,
        )
        document["state"].update(
            current_step=step,
            current_task_id=task_id,
            current_rag_kb=kb_id,
        )
        if step == "chunk_generation":
            document["state"].update(
                chunk_embedding_phase="chunk",
                chunk_task_id=task_id,
                embedding_task_id=None,
            )
        elif step == "rag_indexing":
            summary = document["state"]["summary"]
            summary["attempted"] = int(summary.get("attempted") or 0) + 1
            document["state"].update(
                kb_index_ready_phase="kb_index",
                kb_index_task_id=task_id,
                ready_data_task_id=None,
            )

    def _successful_output_count(self, document: dict[str, Any]) -> int:
        task = self._task_result(str(document["state"].get("current_task_id") or ""))
        if not isinstance(task, dict):
            raise RuntimeError("pipeline task was not found")
        try:
            return max(0, int(task.get("items_downloaded") or 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("pipeline task has an invalid items_downloaded count") from exc

    def _advance_non_kb_step(self, document: dict[str, Any], current_step: str) -> None:
        if current_step == "scheduled":
            self._start_step(document, "markdown_conversion")
        elif current_step == "markdown_conversion":
            self._start_step(document, "catalog")
        elif current_step == "catalog":
            self._start_step(document, "chunk_generation")
        elif current_step == "chunk_generation":
            if document["state"].get("chunk_embedding_phase") == "embedding":
                self._start_next_rag_or_complete(document)
            else:
                self._start_embedding_step(document)

    def _advance_rag_step(self, document: dict[str, Any], task_status: str) -> None:
        state = document["state"]
        if task_status == "error":
            self._record_current_kb(document, succeeded=False, status="error")
            self._start_next_rag_or_complete(document)
        elif state.get("kb_index_ready_phase") == "ready_data":
            self._record_current_kb(document, succeeded=True, status="completed")
            self._start_next_rag_or_complete(document)
        elif self._ready_data_input is None:
            self._record_current_kb(document, succeeded=True, status="completed")
            self._start_next_rag_or_complete(document)
        else:
            task = self._task_result(str(state["current_task_id"] or "")) or {}
            result = task.get("result") if isinstance(task, dict) else None
            if not isinstance(result, dict):
                self._record_current_kb(document, succeeded=False, status="invalid_index_result")
                self._start_next_rag_or_complete(document)
                return
            try:
                ready_payload = self._ready_data_input(
                    str(state.get("current_rag_kb") or ""), result
                )
                self._start_ready_data_step(document, ready_payload)
            except (RuntimeError, ValueError):
                self._record_current_kb(document, succeeded=False, status="ready_launch_failed")
                self._start_next_rag_or_complete(document)

    def _start_embedding_step(self, document: dict[str, Any]) -> None:
        source_task_id = str(document["state"]["consumed_scheduled_task_id"])
        task_id = self._start_task(
            "embedding_generation",
            {"incremental": True},
            task_name="Pipeline: Embedding Generation",
            extra_fields={
                "pipeline_baton_step": "chunk_generation",
                "pipeline_baton_source_task_id": source_task_id,
                "pipeline_baton_subtask": "embedding_generation",
            },
        )
        document["state"].update(
            current_task_id=task_id,
            chunk_embedding_phase="embedding",
            embedding_task_id=task_id,
        )

    def _start_next_rag_or_complete(self, document: dict[str, Any]) -> None:
        state = document["state"]
        current = state["current_rag_kb"]
        kb_ids = sorted({str(kb_id) for kb_id in self._indexable_kb_ids() if str(kb_id)})
        while True:
            next_kb = next(
                (kb_id for kb_id in kb_ids if current is None or kb_id > current),
                None,
            )
            if next_kb is None:
                state["round_status"] = "completed"
                return
            try:
                self._start_step(document, "rag_indexing", kb_id=next_kb)
                return
            except (RuntimeError, ValueError):
                state.update(
                    current_rag_kb=next_kb,
                    kb_index_ready_phase="kb_index",
                    kb_index_task_id=None,
                    ready_data_task_id=None,
                )
                state["summary"]["attempted"] = int(state["summary"].get("attempted") or 0) + 1
                self._record_current_kb(
                    document,
                    succeeded=False,
                    status="index_launch_failed",
                )
                current = next_kb

    def _start_ready_data_step(
        self,
        document: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        state = document["state"]
        kb_id = str(state.get("current_rag_kb") or "")
        source_task_id = str(state["consumed_scheduled_task_id"])
        task_id = self._start_task(
            "ready_data_build",
            dict(payload),
            task_name=f"Pipeline: Ready Data ({kb_id})",
            extra_fields={
                "pipeline_baton_step": "rag_indexing",
                "pipeline_baton_source_task_id": source_task_id,
                "pipeline_baton_kb_id": kb_id,
                "pipeline_baton_subtask": "ready_data_build",
            },
        )
        state.update(
            current_task_id=task_id,
            kb_index_ready_phase="ready_data",
            ready_data_task_id=task_id,
        )

    def _record_current_kb(
        self,
        document: dict[str, Any],
        *,
        succeeded: bool,
        status: str,
    ) -> None:
        state = document["state"]
        kb_id = str(state.get("current_rag_kb") or "")
        result = {
            "kb_id": kb_id,
            "status": "succeeded" if succeeded else "failed",
            "failure_status": "" if succeeded else status,
            "kb_index_task_id": state.get("kb_index_task_id"),
            "ready_data_task_id": state.get("ready_data_task_id"),
        }
        state["kb_results"].append(result)
        summary = state["summary"]
        bucket = "succeeded" if succeeded else "failed"
        summary[bucket] = int(summary.get(bucket) or 0) + 1
        if not succeeded and kb_id not in summary["failed_kbs"]:
            summary["failed_kbs"].append(kb_id)

    @staticmethod
    def _view(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "config": {"overrides": dict(document["config"]["overrides"])},
            "state": dict(document["state"]),
        }

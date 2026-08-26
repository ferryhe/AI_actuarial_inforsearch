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
        category_kb_ids: Callable[[], list[str]],
        now: Callable[[], str] = _utc_now,
    ) -> None:
        self._state_path = Path(state_path)
        self._start_task = start_task
        self._task_status = task_status
        self._task_result = task_result or (lambda _task_id: None)
        self._category_kb_ids = category_kb_ids
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
                "markdown_files": [],
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
                forbidden = forbidden.union({"kb_id", "force_reindex", "incremental"}.intersection(payload))
            if forbidden:
                raise ValueError(f"Pipeline override for {step} cannot set: {', '.join(sorted(forbidden))}")
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
                "markdown_files": [],
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

            task_status = self._task_status(str(state["current_task_id"] or ""))
            if task_status in {None, "pending", "running"}:
                self._save(document)
                return self._view(document)
            if task_status in {"error", "stopped"}:
                state["round_status"] = task_status
                self._save(document)
                return self._view(document)
            if task_status != "completed":
                self._save(document)
                return self._view(document)

            if current_step == "scheduled":
                self._start_step(document, "markdown_conversion")
            elif current_step == "markdown_conversion":
                markdown_files = self._canonical_markdown_files(
                    self._task_result(str(state["current_task_id"] or ""))
                )
                if not markdown_files:
                    state["round_status"] = "error"
                else:
                    state["markdown_files"] = markdown_files
                    self._start_step(document, "catalog")
            elif current_step == "catalog":
                self._start_step(document, "chunk_generation")
            elif current_step == "chunk_generation":
                if state.get("chunk_embedding_phase") == "embedding":
                    self._start_next_rag_or_complete(document)
                else:
                    chunk_task_id = str(state.get("chunk_task_id") or state["current_task_id"] or "")
                    task_result = self._task_result(chunk_task_id) or {}
                    result = task_result.get("result") if isinstance(task_result, dict) else None
                    chunk_sets = (result or {}).get("chunk_sets") if isinstance(result, dict) else None
                    chunk_set_ids = [
                        str(row.get("chunk_set_id") or "")
                        for row in chunk_sets or []
                        if str(row.get("chunk_set_id") or "")
                    ]
                    if not chunk_set_ids:
                        state["round_status"] = "error"
                    else:
                        self._start_embedding_step(document, chunk_set_ids)
            elif current_step == "rag_indexing":
                self._start_next_rag_or_complete(document)
            self._save(document)
            return self._view(document)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._view(self._load())

    def _start_step(self, document: dict[str, Any], step: str, *, kb_id: str | None = None) -> None:
        overrides = document["config"]["overrides"]
        payload = dict(overrides.get(step) or {})
        markdown_files = list(document["state"].get("markdown_files") or [])
        if step == "catalog":
            payload["file_urls"] = [str(row["file_url"]) for row in markdown_files]
        elif step == "chunk_generation":
            payload = sanitize_legacy_chunk_generation_payload(payload)
            payload["files"] = [dict(row) for row in markdown_files]
        if step == "rag_indexing":
            payload.update({"kb_id": kb_id, "incremental": True, "force_reindex": False})
        source_task_id = str(document["state"]["consumed_scheduled_task_id"])
        extra_fields = {
            "pipeline_baton_step": step,
            "pipeline_baton_source_task_id": source_task_id,
        }
        if kb_id is not None:
            extra_fields["pipeline_baton_kb_id"] = kb_id
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

    @staticmethod
    def _canonical_markdown_files(task: dict[str, Any] | None) -> list[dict[str, Any]]:
        result = task.get("result") if isinstance(task, dict) else None
        files = result.get("files") if isinstance(result, dict) else None
        if not isinstance(files, list):
            return []
        canonical: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in files:
            if not isinstance(raw, dict):
                return []
            file_url = str(raw.get("file_url") or "").strip()
            markdown_hash = str(raw.get("markdown_hash") or "").strip()
            markdown_version = str(raw.get("markdown_version") or "").strip()
            if (
                not file_url
                or not markdown_hash
                or markdown_version != markdown_hash
                or str(raw.get("status") or "") != "ready"
                or file_url in seen
            ):
                return []
            seen.add(file_url)
            canonical.append(
                {
                    "file_url": file_url,
                    "markdown_hash": markdown_hash,
                    "markdown_version": markdown_version,
                    "status": "ready",
                }
            )
        return canonical

    def _start_embedding_step(
        self,
        document: dict[str, Any],
        chunk_set_ids: list[str],
    ) -> None:
        source_task_id = str(document["state"]["consumed_scheduled_task_id"])
        task_id = self._start_task(
            "embedding_generation",
            {"chunk_set_ids": chunk_set_ids},
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
        current = document["state"]["current_rag_kb"]
        kb_ids = sorted({str(kb_id) for kb_id in self._category_kb_ids() if str(kb_id)})
        next_kb = next((kb_id for kb_id in kb_ids if current is None or kb_id > current), None)
        if next_kb is None:
            document["state"]["round_status"] = "completed"
            return
        self._start_step(document, "rag_indexing", kb_id=next_kb)

    @staticmethod
    def _view(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "config": {"overrides": dict(document["config"]["overrides"])},
            "state": dict(document["state"]),
        }

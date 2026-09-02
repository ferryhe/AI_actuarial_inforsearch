from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import schedule

from ai_actuarial.ai_runtime import (
    apply_ocr_runtime_environment,
    get_search_runtime_credentials,
    resolve_ocr_runtime,
)
from ai_actuarial.capacity import ensure_capacity
from ai_actuarial.catalog_incremental import run_catalog_for_urls, run_incremental_catalog
from ai_actuarial.collectors.base import CollectionConfig, CollectionResult
from ai_actuarial.collectors.file import FileCollector
from ai_actuarial.collectors.scheduled import ScheduledCollector
from ai_actuarial.collectors.url import URLCollector
from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.embedding_service import (
    embedding_coverage_for_selection,
    ensure_chunk_embeddings,
    resolve_embedding_selection,
    resolve_server_embedding_identity,
    sanitize_legacy_chunk_generation_payload,
    validate_chunk_generation_payload,
    validate_embedding_generation_payload,
)
from ai_actuarial.markdown_conversion_config import (
    HARD_MAX_SCAN_COUNT,
    candidate_chain_for_path,
    load_markdown_conversion_config,
)
from ai_actuarial.pipeline_baton import PIPELINE_STEPS, PipelineBaton
from ai_actuarial.rag.kb_index import (
    KBIndexStopped,
    build_kb_index,
    resolve_kb_bound_chunks,
)
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.search import search_all
from ai_actuarial.search_acquisition import (
    format_acquisition_outcome,
    format_acquisition_summary,
    summarize_acquisition_outcomes,
)
from ai_actuarial.shared_runtime import (
    append_task_log,
    coerce_bool,
    get_sites_config_path,
    load_yaml,
    parse_int_clamped,
    task_log_path,
)
from ai_actuarial.storage import Storage

logger = logging.getLogger(__name__)

_CAPACITY_GATED_TYPES = frozenset({"recategory", "rag_indexing", "ready_data_build"})

# Bounded wait for search-fallback child runs to reach a terminal state before
# the parent pipeline run finalizes (#213). All child runs are required: a hard
# failure or a still-pending (timed-out) child fails the parent, while a partial
# (completed-but-unsuccessful) child is recorded in metadata without failing it.
_CHILD_RUN_WAIT_TIMEOUT_SECONDS = 60.0
_CHILD_RUN_POLL_INTERVAL_SECONDS = 0.2

_QUERY_SITE_FILTER_RE = re.compile(r"(?:^|\s)site:([^\s)]+)", re.IGNORECASE)

_MARKDOWN_PREFLIGHT_READ_BYTES = 8192
_MARKDOWN_TERMINAL_SCAN_PAGE_SIZE = 32
_MARKDOWN_FAILURE_DETAIL_MAX_LENGTH = 800
_OLE_COMPOUND_FILE_HEADER = bytes.fromhex("d0cf11e0a1b11ae1")

_CONVERTIBLE_MARKDOWN_PREDICATE = """
    f.local_path IS NOT NULL AND f.local_path != ''
    AND f.deleted_at IS NULL
    AND (
        LOWER(IFNULL(f.content_type,'')) LIKE '%pdf%'
        OR LOWER(IFNULL(f.content_type,'')) LIKE '%word%'
        OR LOWER(IFNULL(f.content_type,'')) LIKE '%powerpoint%'
        OR LOWER(IFNULL(f.content_type,'')) LIKE '%presentation%'
        OR LOWER(IFNULL(f.content_type,'')) LIKE '%document%'
        OR LOWER(IFNULL(f.content_type,'')) LIKE '%image%'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.pdf'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.docx'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.ppt'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.pptx'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.png'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.jpg'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.jpeg'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.webp'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.bmp'
    )
"""


def generate_file_chunk_sets(
    *,
    db_path: str,
    file_url: str,
    payload: dict[str, Any],
    expected_markdown_hash: str | None = None,
) -> dict[str, Any]:
    from ai_actuarial.api.services.files_write import (
        generate_file_chunk_sets as _generate_file_chunk_sets,
    )

    return _generate_file_chunk_sets(
        db_path=db_path,
        file_url=file_url,
        payload=payload,
        expected_markdown_hash=expected_markdown_hash,
    )


def _convert_document_path(path: Path, **kwargs: Any) -> Any:
    from doc_to_md.registry import convert_path

    return convert_path(path, **kwargs)


def _safe_markdown_failure_detail(exc: Exception, local_path: Path) -> str:
    detail = " ".join(str(exc).split()) or type(exc).__name__
    path_texts = {str(local_path)}
    try:
        path_texts.add(str(local_path.resolve()))
    except OSError:
        pass
    for path_text in sorted(path_texts, key=len, reverse=True):
        if path_text:
            detail = detail.replace(path_text, local_path.name)
    return detail[:_MARKDOWN_FAILURE_DETAIL_MAX_LENGTH]


def _format_markdown_auto_failure(
    local_path: Path,
    failure_details: list[tuple[str, str]],
) -> str:
    prefix = f"Auto conversion failed for {local_path.name}: "
    if not failure_details:
        return f"{prefix}no candidate completed"
    candidate_prefixes = [f"{candidate}: " for candidate, _detail in failure_details]
    separator_length = 2 * (len(failure_details) - 1)
    available = (
        _MARKDOWN_FAILURE_DETAIL_MAX_LENGTH
        - len(prefix)
        - sum(len(candidate_prefix) for candidate_prefix in candidate_prefixes)
        - separator_length
    )
    per_candidate_limit = max(1, available // len(failure_details))
    entries = [
        f"{candidate_prefix}{detail[:per_candidate_limit]}"
        for candidate_prefix, (_candidate, detail) in zip(
            candidate_prefixes, failure_details, strict=True
        )
    ]
    return (prefix + "; ".join(entries))[:_MARKDOWN_FAILURE_DETAIL_MAX_LENGTH]


class _FallbackScheduleJob:
    def __init__(
        self,
        *,
        job_func: Callable[[], None],
        interval: int,
        unit: str,
        at_time: datetime_time | None = None,
        at_time_zone: str | None = None,
        start_day: str | None = None,
    ) -> None:
        self.job_func = job_func
        self.interval = interval
        self.unit = unit
        self.at_time = at_time
        self.at_time_zone = at_time_zone
        self.start_day = start_day
        self.next_run = None
        self.last_run = None


class _FallbackScheduleBuilder:
    def __init__(self, scheduler: "_FallbackScheduler", interval: int) -> None:
        self.scheduler = scheduler
        self.interval = interval
        self.unit = "days"
        self.at_time: datetime_time | None = None
        self.at_time_zone: str | None = None
        self.start_day: str | None = None

    @property
    def day(self) -> "_FallbackScheduleBuilder":
        self.unit = "days"
        return self

    @property
    def monday(self) -> "_FallbackScheduleBuilder":
        self.unit = "weeks"
        self.start_day = "monday"
        return self

    @property
    def hours(self) -> "_FallbackScheduleBuilder":
        self.unit = "hours"
        return self

    @property
    def minutes(self) -> "_FallbackScheduleBuilder":
        self.unit = "minutes"
        return self

    @property
    def seconds(self) -> "_FallbackScheduleBuilder":
        self.unit = "seconds"
        return self

    def at(self, value: str, tz: str | None = None) -> "_FallbackScheduleBuilder":
        parts = str(value or "").split(":")
        if len(parts) >= 2:
            self.at_time = datetime_time(int(parts[0]), int(parts[1]))
        self.at_time_zone = tz
        return self

    def do(self, job_func: Callable[[], None]) -> _FallbackScheduleJob:
        job = _FallbackScheduleJob(
            job_func=job_func,
            interval=self.interval,
            unit=self.unit,
            at_time=self.at_time,
            at_time_zone=self.at_time_zone,
            start_day=self.start_day,
        )
        self.scheduler.jobs.append(job)
        return job


class _FallbackScheduler:
    def __init__(self) -> None:
        self.jobs: list[_FallbackScheduleJob] = []

    def clear(self) -> None:
        self.jobs.clear()

    def every(self, interval: int = 1) -> _FallbackScheduleBuilder:
        return _FallbackScheduleBuilder(self, interval)

    def run_pending(self) -> None:
        return None


def _new_scheduler() -> Any:
    scheduler_cls = getattr(schedule, "Scheduler", None)
    if callable(scheduler_cls):
        return scheduler_cls()
    return _FallbackScheduler()


def _scheduler_job_metadata(
    *,
    kind: str,
    source: str,
    display_name: str,
    managed: bool,
    deletable: bool,
) -> dict[str, Any]:
    identity = f"{kind}\0{source}".encode("utf-8")
    return {
        "job_key": f"job_{hashlib.sha256(identity).hexdigest()[:20]}",
        "kind": kind,
        "source": source,
        "display_name": display_name,
        "managed": managed,
        "deletable": deletable,
    }


def _tag_scheduler_job(
    job: Any,
    *,
    kind: str,
    source: str,
    display_name: str,
    managed: bool,
    deletable: bool,
) -> Any:
    job._ops_metadata = _scheduler_job_metadata(
        kind=kind,
        source=source,
        display_name=display_name,
        managed=managed,
        deletable=deletable,
    )
    return job


@dataclass(slots=True)
class RuntimeRefs:
    active_tasks_ref: dict[str, dict[str, Any]]
    task_history_ref: list[dict[str, Any]]
    task_lock: threading.RLock
    schedule_ref: schedule.Scheduler
    start_background_task: Callable[..., str]
    init_scheduler: Callable[[], None]
    set_site_config: Callable[[dict[str, Any]], None]
    pipeline_baton_status: Callable[[], dict[str, Any]]
    pipeline_baton_start: Callable[[], dict[str, Any]]
    pipeline_baton_tick: Callable[[], dict[str, Any]]
    pipeline_baton_configure: Callable[[dict[str, Any]], dict[str, Any]]


class NativeTaskRuntime:
    def __init__(
        self,
        *,
        ready_data_db_path: str = "",
        ready_data_poll_interval_seconds: int = 60,
        ready_data_runner: Callable[..., dict[str, Any]] | None = None,
        pipeline_baton_state_path: str = "data/pipeline_baton.json",
        weekly_explanation_generator: Any | None = None,
    ) -> None:
        self.active_tasks: dict[str, dict[str, Any]] = {}
        self.task_history: list[dict[str, Any]] = self._load_history_from_disk()
        self.task_lock = threading.RLock()
        self.scheduler = _new_scheduler()
        self._scheduler_lock = threading.RLock()
        self._scheduler_loop_started = False
        self._site_config_override: dict[str, Any] | None = None
        self._ready_data_db_path = str(ready_data_db_path or "")
        self._ready_data_poll_interval_seconds = max(
            1,
            int(ready_data_poll_interval_seconds),
        )
        self._ready_data_runner = ready_data_runner
        self._weekly_explanation_generator = weekly_explanation_generator
        self._ready_data_worker_lock = threading.Lock()
        self._pipeline_baton = PipelineBaton(
            state_path=pipeline_baton_state_path,
            start_task=lambda task_type, payload, **kwargs: self.start_background_task(
                task_type, payload, **kwargs
            ),
            task_status=self._pipeline_task_status,
            task_result=self._pipeline_task_result,
            indexable_kb_ids=self._indexable_kb_ids,
            kb_index_input=self._pipeline_kb_index_input,
            ready_data_input=self._pipeline_ready_data_input,
        )

    def _load_history_from_disk(self) -> list[dict[str, Any]]:
        path = Path("data/job_history.jsonl")
        if not path.exists():
            return []
        try:
            rows: deque[dict[str, Any]] = deque(maxlen=100)
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Skipping malformed job history line %s in %s: %s", line_no, path, exc
                        )
            return list(rows)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load job history: %s", exc)
            return []

    def refs(self) -> RuntimeRefs:
        return RuntimeRefs(
            active_tasks_ref=self.active_tasks,
            task_history_ref=self.task_history,
            task_lock=self.task_lock,
            schedule_ref=self.scheduler,
            start_background_task=self.start_background_task,
            init_scheduler=self.init_scheduler,
            set_site_config=self.set_site_config,
            pipeline_baton_status=self.pipeline_baton_status,
            pipeline_baton_start=self.start_pipeline_baton,
            pipeline_baton_tick=self.tick_pipeline_baton,
            pipeline_baton_configure=self.configure_pipeline_baton,
        )

    def _pipeline_task_status(self, task_id: str) -> str | None:
        with self.task_lock:
            active = self.active_tasks.get(task_id)
            if active is not None:
                return str(active.get("status") or "pending")
            for task in reversed(self.task_history):
                if str(task.get("id") or "") == task_id:
                    return str(task.get("status") or "") or None
        return None

    def _pipeline_task_result(self, task_id: str) -> dict[str, Any] | None:
        with self.task_lock:
            active = self.active_tasks.get(task_id)
            if active is not None:
                return dict(active)
            for task in reversed(self.task_history):
                if str(task.get("id") or "") == task_id:
                    return dict(task)
        return None

    def _indexable_kb_ids(self) -> list[str]:
        db_path = self._ready_data_db_path or self._resolve_db_path(self._load_site_config())
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("""
                SELECT kb_id
                FROM rag_knowledge_bases
                WHERE COALESCE(kb_mode, 'category') IN ('manual', 'category', 'all')
                ORDER BY kb_id
                """).fetchall()
        return [str(row[0]) for row in rows if str(row[0] or "")]

    def _pipeline_kb_index_input(self, kb_id: str) -> dict[str, Any]:
        db_path = self._ready_data_db_path or self._resolve_db_path(self._load_site_config())
        storage = Storage(db_path)
        try:
            from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager

            kb = KnowledgeBaseManager(storage).get_kb(kb_id)
            if not kb:
                raise ValueError(f"knowledge base '{kb_id}' was not found")
            snapshot = resolve_kb_bound_chunks(storage, kb_id)
            return {
                "contract_version": 1,
                "kb_id": kb_id,
                "expected_binding_snapshot_fingerprint": snapshot["binding_snapshot_fingerprint"],
                "embedding_identity_key": str(getattr(kb, "embedding_identity_key", "") or ""),
                "force_rebuild": False,
            }
        finally:
            storage.close()

    def _pipeline_ready_data_input(
        self,
        kb_id: str,
        index_result: dict[str, Any],
    ) -> dict[str, Any]:
        index_version_id = str(index_result.get("index_version_id") or "").strip()
        if not index_version_id:
            raise ValueError("KB Index task did not return index_version_id")
        db_path = self._ready_data_db_path or self._resolve_db_path(self._load_site_config())
        storage = Storage(db_path)
        try:
            from ai_actuarial.agentic_rag.ready_data_builder import (
                get_builder_source_fingerprint,
            )
            from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager

            kb = KnowledgeBaseManager(storage).get_kb(kb_id)
            if not kb:
                raise ValueError(f"knowledge base '{kb_id}' was not found")
            profile = str(getattr(kb, "manifest_profile", "general") or "general")
            source = get_builder_source_fingerprint(
                db_path=db_path,
                kb_id=kb_id,
                profile=profile,
                index_version_id=index_version_id,
            )
            return {
                "contract_version": 1,
                "kb_id": kb_id,
                "profile": profile,
                "index_version_id": index_version_id,
                "expected_source_snapshot_fingerprint": source["source_snapshot_fingerprint"],
            }
        finally:
            storage.close()

    def pipeline_baton_status(self) -> dict[str, Any]:
        view = self._pipeline_baton.status()
        state = view["state"]
        source_task_id = str(state.get("consumed_scheduled_task_id") or "")
        with self.task_lock:
            tasks = [dict(task) for task in self.task_history]
            tasks.extend(dict(task) for task in self.active_tasks.values())
        stage_tasks: dict[str, list[dict[str, Any]]] = {step: [] for step in PIPELINE_STEPS}
        if source_task_id:
            source = next(
                (task for task in tasks if str(task.get("id") or "") == source_task_id), None
            )
            stage_tasks["scheduled"].append(
                {
                    "task_id": source_task_id,
                    "status": str((source or {}).get("status") or "unknown"),
                    "log_url": f"/api/tasks/log/{source_task_id}",
                }
            )
        for task in tasks:
            if str(task.get("pipeline_baton_source_task_id") or "") != source_task_id:
                continue
            step = str(task.get("pipeline_baton_step") or "")
            if step not in stage_tasks:
                continue
            projected = {
                "task_id": str(task.get("id") or ""),
                "status": str(task.get("status") or "unknown"),
                "kb_id": task.get("pipeline_baton_kb_id"),
                "log_url": f"/api/tasks/log/{task.get('id')}",
            }
            if step == "rag_indexing":
                subtask = str(task.get("pipeline_baton_subtask") or "kb_index")
                projected["subtask"] = subtask
                projected["label"] = (
                    "Ready Data Build/Publish" if subtask == "ready_data_build" else "KB Index"
                )
            stage_tasks[step].append(projected)
        view["stages"] = [
            {
                "step": step,
                "label": "KB Index & Ready Data" if step == "rag_indexing" else step,
                "tasks": stage_tasks[step],
            }
            for step in PIPELINE_STEPS
        ]
        return view

    def configure_pipeline_baton(self, overrides: dict[str, Any]) -> dict[str, Any]:
        self._pipeline_baton.configure(overrides)
        return self.pipeline_baton_status()

    def tick_pipeline_baton(self) -> dict[str, Any]:
        self._pipeline_baton.tick()
        return self.pipeline_baton_status()

    def _scheduled_pipeline_baton_tick(self) -> None:
        try:
            self.tick_pipeline_baton()
        except Exception:  # noqa: BLE001 - keep one failed tick from stopping the scheduler
            logger.exception("Scheduled pipeline baton tick failed")

    def start_pipeline_baton(self) -> dict[str, Any]:
        current = self._pipeline_baton.status()
        if current["state"]["round_status"] == "running":
            return self.pipeline_baton_status()
        task_cfg = next(
            (
                task
                for task in list(self._load_site_config().get("scheduled_tasks") or [])
                if str(task.get("name") or "") == "Scheduled Collection"
                and str(task.get("type") or "") == "scheduled"
                and task.get("enabled", True)
            ),
            None,
        )
        if task_cfg is None:
            raise ValueError("Enabled scheduled task 'Scheduled Collection' was not found")
        params = dict(task_cfg.get("params") or {})
        params.setdefault("name", "Scheduled: Scheduled Collection")
        task_id = self.start_background_task(
            "scheduled",
            params,
            task_name="Scheduled: Scheduled Collection",
        )
        self._pipeline_baton.start(task_id)
        return self.pipeline_baton_status()

    def set_site_config(self, new_config: dict[str, Any]) -> None:
        self._site_config_override = dict(new_config or {})

    def _load_site_config(self) -> dict[str, Any]:
        if self._site_config_override is not None:
            return dict(self._site_config_override)
        return load_yaml(get_sites_config_path(), default={})

    def _ensure_chunk_config_compatible(
        self,
        storage: Any,
        kb_id: str,
        *,
        chunk_size: int,
        chunk_overlap: int,
        splitter: str,
        tokenizer: str,
    ) -> None:
        """Fail closed when a KB's committed chunk config would change.

        If the KB already has committed chunk profiles (bound chunk sets with
        chunk data), a chunking config that differs from every committed profile
        would silently produce incompatible artifacts; require a full_reindex
        instead.
        """
        committed = storage.kb_committed_chunk_profiles(kb_id)
        if not committed:
            return
        for profile in committed:
            if (
                int(profile.get("chunk_size")) == int(chunk_size)
                and int(profile.get("chunk_overlap")) == int(chunk_overlap)
                and str(profile.get("splitter") or "") == str(splitter or "")
                and str(profile.get("tokenizer") or "") == str(tokenizer or "")
            ):
                return
        raise RuntimeError(
            "Chunk configuration changed; full_reindex is required before incremental indexing"
        )

    @staticmethod
    def _new_task_id() -> str:
        return f"task_{int(time.time() * 1000)}_{secrets.token_hex(8)}"

    @staticmethod
    def _resolve_db_path(config: dict[str, Any]) -> str:
        db_path = str((config.get("paths") or {}).get("db") or "data/index.db")
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        return db_path

    def start_background_task(
        self,
        collection_type: str,
        data: dict[str, Any],
        *,
        task_name: str | None = None,
        extra_fields: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> str:
        if collection_type == "kb_index_build":
            raise ValueError("kb_index_build is historical; use rag_indexing")
        task_id = task_id or self._new_task_id()
        name = task_name or str(data.get("name") or f"{collection_type.capitalize()} Collection")
        task_data: dict[str, Any] = {
            "id": task_id,
            "name": name,
            "type": collection_type,
            "status": "pending",
            "progress": 0,
            "started_at": datetime.now().isoformat(),
            "items_processed": 0,
            "items_total": 0,
            "items_downloaded": 0,
            "items_skipped": 0,
            "items_terminal_skipped": 0,
            "log_file": str(task_log_path(task_id)),
            "errors": [],
        }
        if extra_fields:
            task_data.update(extra_fields)
        with self.task_lock:
            self.active_tasks[task_id] = task_data
        append_task_log(task_id, "INFO", f"Task created (type={collection_type})")
        thread = threading.Thread(
            target=self._execute_collection_task,
            args=(task_id, collection_type, dict(data)),
            daemon=True,
        )
        thread.start()
        return task_id

    def init_scheduler(self, *, configured_only: bool = False) -> None:
        site_config = self._load_site_config()
        global_schedule = str(
            (site_config.get("defaults") or {}).get("schedule_interval") or ""
        ).strip()
        sites = list(site_config.get("sites") or [])
        generic_tasks = list(site_config.get("scheduled_tasks") or [])
        staged_scheduler = _new_scheduler()

        def global_run() -> None:
            self.start_background_task(
                "scheduled",
                {
                    "site": None,
                    "name": "Scheduled Run (All)",
                    "max_pages": (site_config.get("defaults") or {}).get("max_pages"),
                    "max_depth": (site_config.get("defaults") or {}).get("max_depth"),
                },
                task_name="Scheduled: All Sites",
            )

        def make_site_job(site: dict[str, Any]) -> Callable[[], None]:
            def job_wrapper() -> None:
                self.start_background_task(
                    "scheduled",
                    {
                        "site": site.get("name"),
                        "name": f"Scheduled: {site.get('name')}",
                        "max_pages": site.get("max_pages"),
                        "max_depth": site.get("max_depth"),
                    },
                    task_name=f"Scheduled: {site.get('name')}",
                )

            return job_wrapper

        def make_generic_task_job(task_cfg: dict[str, Any]) -> Callable[[], None]:
            def job_wrapper() -> None:
                params = dict(task_cfg.get("params") or {})
                task_name = str(task_cfg.get("name") or "Generic Task")
                task_type = str(task_cfg.get("type") or "catalog")
                if task_type == "chunk_generation":
                    params = sanitize_legacy_chunk_generation_payload(params)
                is_pipeline_source = (
                    task_name == "Scheduled Collection" and task_type == "scheduled"
                )
                if (
                    is_pipeline_source
                    and self._pipeline_baton.status()["state"]["round_status"] == "running"
                ):
                    return
                params.setdefault("name", f"Scheduled: {task_name}")
                task_id = self.start_background_task(
                    task_type, params, task_name=f"Scheduled: {task_name}"
                )
                if is_pipeline_source:
                    self._pipeline_baton.start(task_id)
                elif (
                    task_type == "chunk_generation"
                    and task_cfg.get("composition") == "chunk_embedding"
                ):
                    threading.Thread(
                        target=self._complete_scheduled_chunk_embedding,
                        args=(task_id, task_name),
                        daemon=True,
                    ).start()

            return job_wrapper

        if not configured_only:
            if global_schedule:
                _tag_scheduler_job(
                    self._register_schedule(
                        global_schedule, global_run, scheduler_ref=staged_scheduler
                    ),
                    kind="global",
                    source="defaults.schedule_interval",
                    display_name="All Sites",
                    managed=False,
                    deletable=False,
                )
            for site in sites:
                interval = str(site.get("schedule_interval") or "").strip()
                if interval:
                    site_name = str(site.get("name") or "Site")
                    _tag_scheduler_job(
                        self._register_schedule(
                            interval,
                            make_site_job(site),
                            scheduler_ref=staged_scheduler,
                        ),
                        kind="site",
                        source=site_name,
                        display_name=f"Site: {site_name}",
                        managed=False,
                        deletable=False,
                    )
        for task_cfg in generic_tasks:
            if not task_cfg.get("enabled", True):
                continue
            interval = str(task_cfg.get("interval") or "").strip()
            if interval:
                task_name = str(task_cfg.get("name") or "Generic Task")
                _tag_scheduler_job(
                    self._register_schedule(
                        interval,
                        make_generic_task_job(task_cfg),
                        at_timezone=("UTC" if task_cfg.get("type") == "weekly_summary" else None),
                        scheduler_ref=staged_scheduler,
                    ),
                    kind="configured_task",
                    source=task_name,
                    display_name=task_name,
                    managed=True,
                    deletable=True,
                )
        if not configured_only:
            _tag_scheduler_job(
                staged_scheduler.every(30).minutes.do(self._scheduled_pipeline_baton_tick),
                kind="pipeline_baton",
                source="pipeline_baton",
                display_name="Pipeline Baton",
                managed=False,
                deletable=False,
            )
            if self._ready_data_db_path:
                _tag_scheduler_job(
                    staged_scheduler.every(self._ready_data_poll_interval_seconds).seconds.do(
                        self._wake_ready_data_automation
                    ),
                    kind="ready_data",
                    source="ready_data_automation",
                    display_name="Ready Data Automation",
                    managed=False,
                    deletable=False,
                )

        with self._scheduler_lock:
            if configured_only:
                system_jobs = []
                for job in self.scheduler.jobs:
                    metadata = getattr(job, "_ops_metadata", None)
                    if not isinstance(metadata, dict) or metadata.get("kind") != "configured_task":
                        system_jobs.append(job)
                self.scheduler.jobs[:] = [*system_jobs, *staged_scheduler.jobs]
            else:
                self.scheduler.jobs[:] = list(staged_scheduler.jobs)

        if not self._scheduler_loop_started:
            thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            thread.start()
            self._scheduler_loop_started = True

    def reconcile_configured_tasks(self) -> None:
        self.init_scheduler(configured_only=True)

    def _complete_scheduled_chunk_embedding(
        self,
        chunk_task_id: str,
        scheduled_name: str,
    ) -> str | None:
        while True:
            status = self._pipeline_task_status(chunk_task_id)
            if status == "completed":
                break
            if status in {None, "error", "stopped"}:
                return None
            time.sleep(1)
        task = self._pipeline_task_result(chunk_task_id) or {}
        result = task.get("result") if isinstance(task, dict) else None
        chunk_sets = result.get("chunk_sets") if isinstance(result, dict) else None
        has_stable_chunk_set = any(
            isinstance(row, dict) and str(row.get("chunk_set_id") or "").strip()
            for row in chunk_sets or []
        )
        if not has_stable_chunk_set:
            append_task_log(
                chunk_task_id,
                "ERROR",
                "Scheduled Chunk & Embedding stopped: chunk task returned no stable chunk_set_ids",
            )
            return None
        return self.start_background_task(
            "embedding_generation",
            {"incremental": True},
            task_name=f"Scheduled: {scheduled_name} (Embedding)",
        )

    def _scheduler_loop(self) -> None:
        logger.info("Native FastAPI scheduler loop started")
        sleep_seconds = (
            min(60, self._ready_data_poll_interval_seconds) if self._ready_data_db_path else 60
        )
        while True:
            with self._scheduler_lock:
                self.scheduler.run_pending()
            time.sleep(sleep_seconds)

    def _wake_ready_data_automation(self) -> None:
        """Wake one worker without making the scheduler thread own durable state."""
        if not self._ready_data_db_path or not self._ready_data_worker_lock.acquire(blocking=False):
            return

        def run() -> None:
            try:
                runner = self._ready_data_runner
                if runner is None:
                    from ai_actuarial.api.services.ready_data_automation import (
                        run_ready_data_automation_once,
                    )

                    runner = run_ready_data_automation_once
                runner(db_path=self._ready_data_db_path)
            except Exception:  # noqa: BLE001
                logger.exception("Ready-data automation wakeup failed")
            finally:
                self._ready_data_worker_lock.release()

        threading.Thread(
            target=run,
            name="ready-data-automation-runner",
            daemon=True,
        ).start()

    def _register_schedule(
        self,
        interval_str: str,
        job_func: Callable[[], None],
        *,
        at_timezone: str | None = None,
        scheduler_ref: Any | None = None,
    ) -> Any:
        scheduler = scheduler_ref or self.scheduler
        interval = str(interval_str or "").strip().lower()
        if interval == "daily":
            return scheduler.every().day.at("00:30").do(job_func)
        if interval == "weekly":
            weekly_job = scheduler.every().monday
            if at_timezone:
                return weekly_job.at("00:30", at_timezone).do(job_func)
            return weekly_job.at("00:30").do(job_func)
        if interval.startswith("daily at "):
            at_value = interval.replace("daily at ", "", 1).strip()
            daily_at = re.fullmatch(r"(\d{1,2}):(\d{1,2})", at_value)
            if daily_at:
                hour, minute = daily_at.groups()
                at_value = f"{int(hour):02d}:{int(minute):02d}"
            return scheduler.every().day.at(at_value).do(job_func)
        if interval.startswith("every "):
            parts = interval.split()
            if len(parts) == 3:
                qty = int(parts[1])
                unit = parts[2]
                if unit in {"hour", "hours"}:
                    return scheduler.every(qty).hours.do(job_func)
                if unit in {"minute", "minutes"}:
                    return scheduler.every(qty).minutes.do(job_func)
        raise ValueError(f"Unsupported schedule interval: {interval_str}")

    def _execute_collection_task(
        self, task_id: str, collection_type: str, data: dict[str, Any]
    ) -> None:
        self._update_task(
            task_id, status="running", current_activity=f"Starting {collection_type} task"
        )
        append_task_log(task_id, "INFO", f"Starting background task (type={collection_type})")
        try:
            result = self._run_collection(task_id, collection_type, data)
            self._finalize_task_success(task_id, collection_type, result)
            self._finalize_child_run(data, result=result)
        except Exception as exc:  # noqa: BLE001
            from ai_actuarial.manifest_ingest import ManifestIngestError

            if isinstance(exc, ManifestIngestError):
                logger.error("Task %s failed: %s", task_id, exc)
                error_code = exc.code
                error_details = exc.details
            else:
                logger.exception("Task %s failed", task_id)
                error_code = None
                error_details = None
            self._finalize_task_error(
                task_id,
                str(exc),
                error_code=error_code,
                error_details=error_details,
            )
            self._finalize_child_run(data, error=str(exc))

    def _run_collection(
        self, task_id: str, collection_type: str, data: dict[str, Any]
    ) -> CollectionResult:
        config = self._load_site_config()
        db_path = str((config.get("paths") or {}).get("db") or "data/index.db")
        download_dir = str((config.get("paths") or {}).get("download_dir") or "data/files")
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        if not os.path.isabs(download_dir):
            download_dir = os.path.abspath(download_dir)

        if collection_type in _CAPACITY_GATED_TYPES:
            ensure_capacity(path="/", operation=collection_type)

        manifest_input: tuple[dict[str, Any], str] | None = None
        if collection_type == "manifest_ingestion":
            from ai_actuarial.manifest_ingest import (
                ManifestIngestError,
                parse_manifest_json,
                validate_manifest,
            )

            manifest_path = str(data.get("manifest_path") or data.get("path") or "").strip()
            if not manifest_path:
                raise ManifestIngestError("manifest_path_required", "manifest_path")
            path = Path(manifest_path)
            if not path.is_file():
                raise ManifestIngestError("manifest_file_unavailable", "manifest_path")
            try:
                manifest_text = path.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                raise ManifestIngestError("manifest_file_unavailable", "manifest_path") from None
            manifest = parse_manifest_json(manifest_text)
            validate_manifest(manifest)
            manifest_input = (manifest, manifest_text)

        storage = Storage(db_path)
        try:
            if collection_type == "file":
                collector = FileCollector(storage, download_dir)
                file_paths = self._collect_file_paths(data)
                cfg = CollectionConfig(
                    name=str(data.get("name") or "File Import"),
                    source_type="file",
                    check_database=True,
                    metadata={
                        "file_paths": file_paths,
                        "target_subdir": str(data.get("target_subdir") or "imported"),
                    },
                )
                return collector.collect(cfg, progress_callback=self._progress_callback(task_id))

            if collection_type == "url":
                defaults = dict(config.get("defaults") or {})
                crawler = Crawler(
                    storage,
                    download_dir,
                    str(defaults.get("user_agent") or "AI-Actuarial/1.0"),
                    stop_check=lambda: self._stop_requested(task_id),
                    default_delay_seconds=self._configured_delay_seconds(
                        defaults.get("delay_seconds")
                    ),
                )
                collector = URLCollector(storage, crawler)
                cfg = CollectionConfig(
                    name=str(data.get("name") or "URL Collection"),
                    source_type="url",
                    check_database=bool(data.get("check_database", True)),
                    keywords=self._coerce_list(data.get("keywords"))
                    or list(defaults.get("keywords") or []),
                    file_exts=self._coerce_list(data.get("file_exts"))
                    or list(defaults.get("file_exts") or []),
                    exclude_keywords=self._coerce_list(data.get("exclude_keywords"))
                    or list(defaults.get("exclude_keywords") or []),
                    metadata={"urls": self._coerce_list(data.get("urls"))},
                )
                return collector.collect(cfg, progress_callback=self._progress_callback(task_id))

            if collection_type == "search":
                return self._run_search_task(task_id, storage, config, download_dir, data)

            if collection_type in {"scheduled", "adhoc", "quick_check"}:
                defaults = dict(config.get("defaults") or {})
                crawler = Crawler(
                    storage,
                    download_dir,
                    str(defaults.get("user_agent") or "AI-Actuarial/1.0"),
                    stop_check=lambda: self._stop_requested(task_id),
                    default_delay_seconds=self._configured_delay_seconds(
                        defaults.get("delay_seconds")
                    ),
                )
                collector = ScheduledCollector(storage, crawler)
                site_configs = (
                    [self._quick_check_site_config(config, data)]
                    if collection_type == "quick_check" and str(data.get("url") or "").strip()
                    else self._site_configs_for_run(config, data)
                )
                cfg = CollectionConfig(
                    name=str(data.get("name") or f"{collection_type.capitalize()} Run"),
                    source_type=collection_type,
                    check_database=bool(data.get("check_database", True)),
                    metadata={"site_configs": site_configs},
                )
                result = collector.collect(cfg, progress_callback=self._progress_callback(task_id))
                if collection_type in {"scheduled", "adhoc"}:
                    self._enqueue_site_query_search_fallbacks(
                        task_id,
                        config,
                        result,
                        site_configs,
                        data,
                    )
                return result

            if collection_type == "catalog":
                if storage.taxonomy_needs_recategory():
                    raise RuntimeError(
                        "categories.yaml taxonomy has changed; run the recategory task before catalog"
                    )
                category = str(data.get("category") or "").strip() or None
                catalog_cfg = (config.get("ai_config") or {}).get("catalog") or {}
                if not isinstance(catalog_cfg, dict):
                    catalog_cfg = {}
                provider = (
                    str(data.get("provider") or catalog_cfg.get("provider") or "local")
                    .strip()
                    .lower()
                    or "local"
                )
                input_source = str(data.get("input_source") or "markdown").strip() or "markdown"
                catalog_version = str(data.get("catalog_version") or "").strip()
                if not catalog_version:
                    from ai_actuarial.catalog import CATALOG_VERSION as base_catalog_version

                    catalog_version = f"{base_catalog_version}:{provider}:{input_source}"
                skip_existing = bool(data.get("skip_existing", True))
                if bool(data.get("overwrite_existing", False)):
                    skip_existing = False
                raw_start_index = data.get("scan_start_index", data.get("candidate_start_index", 1))
                try:
                    candidate_offset = max(0, int(raw_start_index or 1) - 1)
                except (TypeError, ValueError):
                    candidate_offset = 0
                raw_limit = data.get("scan_count")
                if raw_limit in (None, ""):
                    raw_limit = data.get("limit")
                if raw_limit in (None, ""):
                    raw_limit = 100
                try:
                    limit = max(0, int(raw_limit))
                except (TypeError, ValueError):
                    limit = 100
                updates_dir = Path((config.get("paths") or {}).get("updates_dir") or "data/updates")
                common_catalog_kwargs = {
                    "db_path": db_path,
                    "out_jsonl": updates_dir / "catalog_runtime.jsonl",
                    "out_md": updates_dir / "catalog_runtime.md",
                    "ai_only": False,
                    "catalog_version": catalog_version,
                    "max_chars": int(data.get("max_chars") or 12000),
                    "retry_errors": bool(data.get("retry_errors", False)),
                    "skip_existing": skip_existing,
                    "provider": provider,
                    "input_source": input_source,
                    "max_workers": int(data.get("max_workers") or 5),
                    "update_title": bool(data.get("update_title", False)),
                    "catalog_system_prompt": str(catalog_cfg.get("system_prompt") or "").strip()
                    or None,
                    "output_language": str(data.get("output_language") or "auto").strip() or "auto",
                    "progress_callback": self._progress_callback(task_id),
                }
                file_urls = [
                    str(file_url).strip()
                    for file_url in list(data.get("file_urls") or [])
                    if str(file_url).strip()
                ]
                if file_urls:
                    stats = run_catalog_for_urls(
                        file_urls=file_urls,
                        **common_catalog_kwargs,
                    )
                else:
                    stats = run_incremental_catalog(
                        batch=int(data.get("batch") or 50),
                        site_filter=str(data.get("site") or "").strip() or None,
                        limit=limit,
                        candidate_offset=candidate_offset,
                        **common_catalog_kwargs,
                    )
                return CollectionResult(
                    success=not int(stats.get("errors", 0))
                    and not bool(stats.get("stopped", False)),
                    items_found=int(stats.get("scanned", 0)),
                    items_downloaded=int(stats.get("processed", 0)),
                    items_skipped=int(stats.get("skipped_ai", 0)),
                    errors=(
                        []
                        if not int(stats.get("errors", 0))
                        else [f"Catalog errors: {stats.get('errors', 0)}"]
                    ),
                    metadata={
                        "category": category,
                        "provider": provider,
                        "input_source": input_source,
                        "catalog_version": catalog_version,
                        "file_urls": file_urls,
                    },
                )

            if collection_type == "recategory":
                return self._run_recategory(task_id, storage, data)

            if collection_type == "rag_indexing":
                return self._run_rag_indexing(task_id, storage, data)

            if collection_type == "ready_data_build":
                return self._run_ready_data_build(task_id, storage, db_path, data)

            if collection_type == "markdown_conversion":
                return self._run_markdown_conversion(task_id, storage, config, download_dir, data)

            if collection_type == "chunk_generation":
                return self._run_chunk_generation(task_id, storage, db_path, data)

            if collection_type == "embedding_generation":
                return self._run_embedding_generation(task_id, storage, data)

            if collection_type == "weekly_summary":
                return self._run_weekly_summary(db_path, data, storage=storage)

            if collection_type == "weekly_explanation":
                return self._run_weekly_explanation(db_path, data)

            if collection_type == "manifest_ingestion":
                from ai_actuarial.manifest_ingest import ingest_manifest

                assert manifest_input is not None
                manifest, manifest_text = manifest_input
                summary = ingest_manifest(storage, manifest, raw_text=manifest_text)
                imported = int(summary.get("imported", 0))
                return CollectionResult(
                    success=True,
                    items_found=imported,
                    items_downloaded=imported,
                    items_skipped=0,
                    errors=[],
                    metadata=summary,
                )

            raise RuntimeError(
                f"Native runtime does not yet support collection type '{collection_type}'"
            )
        finally:
            storage.close()

    def _run_recategory(
        self, task_id: str, storage: Storage, data: dict[str, Any]
    ) -> CollectionResult:
        from ai_actuarial.recategory import apply_recategory, plan_recategory

        mode = str(data.get("mode") or "plan").strip().lower() or "plan"
        if mode not in {"plan", "apply"}:
            raise RuntimeError(f"Invalid recategory mode: {mode}")

        # Re-categorization operates on the whole taxonomy and ignores per-run
        # scoping. Reject scoped requests fail-closed instead of silently
        # rewriting every catalog item.
        for scope_field in ("site", "category", "kb_id", "file_urls"):
            value = data.get(scope_field)
            if value not in (None, "", [], {}):
                raise RuntimeError(
                    f"recategory does not support per-run scoping ({scope_field}); "
                    "it re-classifies the entire taxonomy"
                )

        progress_callback = self._progress_callback(task_id)

        def stop_check() -> bool:
            return self._stop_requested(task_id)

        if mode == "plan":
            plan = plan_recategory(storage)
            return CollectionResult(
                success=True,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[],
                metadata=plan,
            )

        result = apply_recategory(
            storage, progress_callback=progress_callback, stop_check=stop_check
        )
        if result.get("stopped"):
            return CollectionResult(
                success=False,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=["Task stopped by user"],
                metadata=result,
            )
        changed = int(
            sum(result.get("removed_counts", {}).values())
            + sum(result.get("added_counts", {}).values())
        )
        return CollectionResult(
            success=True,
            items_found=changed,
            items_downloaded=0,
            items_skipped=0,
            errors=[],
            metadata=result,
        )

    def _run_weekly_summary(
        self, db_path: str, data: dict[str, Any], *, storage: Storage | None = None
    ) -> CollectionResult:
        from ai_actuarial.api.services.weekly_updates import generate_weekly_update_summary

        summary = generate_weekly_update_summary(
            db_path=db_path,
            storage=storage,
            period_start=str(data.get("period_start") or "").strip() or None,
            period_end=str(data.get("period_end") or "").strip() or None,
            relative_period=str(data.get("relative_period") or "").strip() or None,
            max_files=parse_int_clamped(
                data.get("max_files"), default=500, min_value=1, max_value=500
            ),
            force=coerce_bool(data.get("force"), default=False),
        )
        file_count = int(summary.get("file_count") or 0)
        return CollectionResult(
            success=True,
            items_found=file_count,
            items_downloaded=0,
            items_skipped=0,
            errors=[],
            metadata={
                "period_start": summary.get("period_start"),
                "period_end": summary.get("period_end"),
                "summary_id": summary.get("id"),
                "file_count": file_count,
            },
        )

    def _run_weekly_explanation(self, db_path: str, data: dict[str, Any]) -> CollectionResult:
        from ai_actuarial.api.services.weekly_explanations import (
            generate_weekly_explanation,
            generate_weekly_explanation_for_period,
        )

        snapshot_id = str(data.get("snapshot_id") or "").strip()
        if snapshot_id:
            explanation = generate_weekly_explanation(
                db_path=db_path,
                snapshot_id=snapshot_id,
                generator=self._weekly_explanation_generator,
            )
        else:
            explanation = generate_weekly_explanation_for_period(
                db_path=db_path,
                period_start=str(data.get("period_start") or "").strip() or None,
                period_end=str(data.get("period_end") or "").strip() or None,
                relative_period=str(data.get("relative_period") or "").strip() or None,
                generator=self._weekly_explanation_generator,
            )
        complete = explanation.get("status") == "complete"
        return CollectionResult(
            success=complete,
            items_found=1,
            items_downloaded=0,
            items_skipped=0 if complete else 1,
            errors=[] if complete else ["Weekly explanation generation failed"],
            metadata={
                "snapshot_id": explanation.get("snapshot_id") or snapshot_id,
                "explanation_status": explanation.get("status"),
                "result": explanation,
            },
        )

    def _enqueue_site_query_search_fallbacks(
        self,
        task_id: str,
        config: dict[str, Any],
        result: CollectionResult,
        site_configs: list[SiteConfig],
        data: dict[str, Any],
    ) -> None:
        search_cfg = dict(config.get("search") or {})
        if result.metadata is None:
            result.metadata = {}
        result.metadata["search_fallback_enqueued"] = 0
        result.metadata["search_fallback_task_ids"] = []
        if not bool(search_cfg.get("enabled", False)):
            return

        site_outcomes = self._site_outcomes_by_key(result)
        enqueued = 0
        child_task_ids: list[str] = []

        # Only track children under a parent pipeline run (#213). For standalone
        # scheduled/adhoc tasks there is no parent run to link or wait on.
        parent_run_id = str(data.get("_pipeline_run_id") or "").strip()
        child_db: Storage | None = None
        try:
            for site_config in site_configs:
                tools = {
                    str(tool).strip().lower()
                    for tool in (site_config.acquisition_tools or [])
                    if str(tool).strip()
                }
                if tools and "search" not in tools:
                    continue
                queries = [
                    str(query).strip()
                    for query in (site_config.queries or [])
                    if str(query).strip()
                ]
                if not queries:
                    continue
                fallback_reason = self._site_search_fallback_reason(site_config, site_outcomes)
                if not fallback_reason:
                    continue

                total_queries = len(queries)
                for query_index, query in enumerate(queries, start=1):
                    task_data = self._site_query_search_task_data(site_config, query, config, data)
                    query_label = query if len(query) <= 80 else f"{query[:77]}..."
                    task_id_kwargs: dict[str, Any] = {}
                    if parent_run_id:
                        if child_db is None:
                            child_db = Storage(self._resolve_db_path(config))
                        child_task_id = self._new_task_id()
                        task_data["child_run_id"] = child_task_id
                        task_data["parent_run_id"] = parent_run_id
                        task_data["_db_path"] = self._resolve_db_path(config)
                        child_db.create_child_run(
                            child_task_id,
                            parent_run_id,
                            correlation_id=str(data.get("correlation_id") or ""),
                        )
                        task_id_kwargs["task_id"] = child_task_id
                    child_task_id = self.start_background_task(
                        "search",
                        task_data,
                        task_name=f"Search fallback: {site_config.name} ({query_index}/{total_queries}): {query_label}",
                        extra_fields={
                            "parent_task_id": task_id,
                            "trigger": "crawler_fallback",
                            "fallback_reason": fallback_reason,
                        },
                        **task_id_kwargs,
                    )
                    enqueued += 1
                    child_task_ids.append(child_task_id)
                    message = (
                        f"{site_config.name}: enqueued search fallback task {child_task_id} "
                        f"(reason={fallback_reason}, query={query})"
                    )
                    logger.info(message)
                    append_task_log(task_id, "INFO", message)
        finally:
            if child_db is not None:
                child_db.close()

        result.metadata["search_fallback_enqueued"] = enqueued
        result.metadata["search_fallback_task_ids"] = child_task_ids

    def _site_query_search_task_data(
        self,
        site_config: SiteConfig,
        query: str,
        config: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        search_cfg = dict(config.get("search") or {})
        engine = (
            str(data.get("engine") or search_cfg.get("engine") or "brave").strip().lower()
            or "brave"
        )
        site_host = self._site_filter_for_query(site_config.url, query)

        task_data = {
            "name": site_config.name,
            "query": query,
            "site": site_host,
            "engine": engine,
            "count": search_cfg.get("max_results"),
            "use_search_defaults": True,
            "file_exts": list(site_config.file_exts or []),
            "keywords": list(site_config.keywords or []),
            "search_exclude_keywords": list(site_config.exclude_keywords or []),
            "check_database": bool(data.get("check_database", True)),
        }
        if site_config.exclude_prefixes:
            task_data["search_exclude_prefixes"] = list(site_config.exclude_prefixes)
        if site_config.collect_linked_files is not None:
            task_data["collect_linked_files"] = site_config.collect_linked_files
        if site_config.collect_page_content is not None:
            task_data["collect_page_content"] = site_config.collect_page_content
        return task_data

    def _site_filter_for_query(self, site_url: str, query: str) -> str:
        query_site = self._site_filter_from_query(query)
        if query_site:
            return query_site
        return self._normalized_site_host(urlparse(site_url).netloc)

    def _site_filter_from_query(self, query: str) -> str:
        match = _QUERY_SITE_FILTER_RE.search(str(query or ""))
        if not match:
            return ""
        return self._normalized_site_host(match.group(1))

    def _normalized_site_host(self, host: str) -> str:
        site = str(host or "").strip().lower().removeprefix("site:")
        site = site.removeprefix("http://").removeprefix("https://").split("/", 1)[0]
        site = site.split(":", 1)[0].strip(".")
        if site.startswith("www."):
            return site[4:]
        return site

    def _site_outcomes_by_key(self, result: CollectionResult) -> dict[str, dict[str, Any]]:
        outcomes: dict[str, dict[str, Any]] = {}
        for row in list((result.metadata or {}).get("site_results") or []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip().lower()
            url = str(row.get("url") or "").strip().lower()
            if name:
                outcomes[f"name:{name}"] = row
            if url:
                outcomes[f"url:{url}"] = row
        return outcomes

    def _site_search_fallback_reason(
        self,
        site_config: SiteConfig,
        site_outcomes: dict[str, dict[str, Any]],
    ) -> str | None:
        outcome = site_outcomes.get(
            f"name:{site_config.name.strip().lower()}"
        ) or site_outcomes.get(f"url:{site_config.url.strip().lower()}")
        if not outcome:
            return None
        reason = str(outcome.get("fallback_reason") or "").strip()
        if bool(outcome.get("blocked")):
            return reason or "blocked"
        if bool(outcome.get("failed")) or not bool(outcome.get("success", True)):
            return reason or "failed"
        try:
            items_found = int(outcome.get("items_found") or 0)
        except (TypeError, ValueError):
            items_found = 0
        if items_found <= 0:
            return reason or "zero_results"
        return None

    def _run_rag_indexing(
        self, task_id: str, storage: Storage, data: dict[str, Any]
    ) -> CollectionResult:
        kb_id = str(data.get("kb_id") or "").strip()
        if not kb_id:
            raise RuntimeError("kb_id is required for RAG indexing")

        manager = KnowledgeBaseManager(storage)
        kb = manager.get_kb(kb_id)
        if not kb:
            raise RuntimeError(f"Knowledge base '{kb_id}' not found")

        force_rebuild = bool(
            data.get("force_rebuild", False)
            or data.get("force_reindex", False)
            or data.get("reindex_all", False)
        )
        file_urls = [
            str(file_url).strip()
            for file_url in list(data.get("file_urls") or [])
            if str(file_url).strip()
        ]
        expected = str(data.get("expected_binding_snapshot_fingerprint") or "").strip()
        identity_key = str(data.get("embedding_identity_key") or "").strip()
        if int(data.get("contract_version") or 0) != 1 or not expected or not identity_key:
            raise RuntimeError(
                "invalid_selector: rag_indexing requires contract_version=1, "
                "expected_binding_snapshot_fingerprint, and embedding_identity_key"
            )
        resolve_kb_bound_chunks(
            storage,
            kb_id,
            file_urls=file_urls if file_urls else None,
        )
        task_progress = self._progress_callback(task_id)
        try:
            result = build_kb_index(
                storage=storage,
                kb_id=kb_id,
                expected_binding_snapshot_fingerprint=expected,
                embedding_identity_key=identity_key,
                force_rebuild=force_rebuild,
                config=manager.config,
                stop_check=lambda: self._stop_requested(task_id),
                progress_callback=lambda message, current, total: task_progress(
                    current, total, message
                ),
            )
        except KBIndexStopped:
            return CollectionResult(
                success=False,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=["Task stopped by user"],
                metadata={"kb_id": kb_id, "stopped": True},
            )
        return CollectionResult(
            success=True,
            items_found=int(result["chunk_count"]),
            items_downloaded=int(result["chunk_count"]),
            items_skipped=0,
            errors=[],
            metadata={
                "kb_id": kb_id,
                "kb_name": kb.name,
                "force_rebuild": force_rebuild,
                "total_chunks": int(result["chunk_count"]),
                "result": result,
            },
        )

    def _run_ready_data_build(
        self,
        task_id: str,
        storage: Storage,
        db_path: str,
        data: dict[str, Any],
    ) -> CollectionResult:
        from ai_actuarial.api.services.rag_admin import _build_agentic_ready_manifest_core

        kb_id = str(data.get("kb_id") or "").strip()
        profile = str(data.get("profile") or "general").strip().lower() or "general"
        index_version_id = str(data.get("index_version_id") or "").strip()
        expected_source = str(data.get("expected_source_snapshot_fingerprint") or "").strip()
        if (
            int(data.get("contract_version") or 0) != 1
            or not kb_id
            or not index_version_id
            or not expected_source
        ):
            raise RuntimeError(
                "invalid_selector: ready_data_build requires contract_version=1, kb_id, "
                "index_version_id, and expected_source_snapshot_fingerprint"
            )
        slot = storage._conn.execute(
            """
            SELECT automatic_publish_enabled
            FROM agentic_ready_slots
            WHERE kb_id = ? AND profile = ?
            """,
            (kb_id, profile),
        ).fetchone()
        publish = bool(slot and slot[0])
        progress = self._progress_callback(task_id)
        progress(0, 2, "Build/validate Ready Data")
        payload = _build_agentic_ready_manifest_core(
            db_path=db_path,
            kb_id=kb_id,
            payload={
                "profile": profile,
                "index_version_id": index_version_id,
                "expected_source_snapshot_fingerprint": expected_source,
            },
            publish=publish,
            should_stop=lambda: self._stop_requested(task_id),
        )
        if bool((payload.get("metadata") or {}).get("stopped")):
            return CollectionResult(
                success=False,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=["Task stopped by user"],
                metadata={"kb_id": kb_id, "stopped": True},
            )
        validation = dict(payload.get("validation") or {})
        if not validation.get("valid"):
            validation_errors = [str(error) for error in validation.get("errors") or []]
            stale_error = next(
                (error for error in validation_errors if "stale_snapshot:" in error),
                None,
            )
            if stale_error:
                raise RuntimeError(stale_error)
            raise RuntimeError("build_failure: Ready Data validation failed")
        candidate = dict(payload.get("candidate_publication") or {})
        state = dict(payload.get("publication_state") or {})
        if publish:
            publication_id = str(state.get("active_publication_id") or "") or None
            candidate_id = str(candidate.get("publication_id") or "")
            active_publication = state.get("active_publication")
            existing_active_is_valid = bool(
                state.get("idempotent") is True
                and state.get("cas_won") is True
                and isinstance(active_publication, dict)
                and publication_id
                and str(active_publication.get("publication_id") or "") == publication_id
                and str(active_publication.get("status") or "") == "active"
            )
            if not publication_id or (
                publication_id != candidate_id and not existing_active_is_valid
            ):
                raise RuntimeError("publish_failure: Ready Data publication did not commit")
            publish_status = "published"
        else:
            publication_id = None
            publish_status = "awaiting_publish"
        result = {
            "contract_version": 1,
            "publication_id": publication_id,
            "publish_status": publish_status,
            "source_snapshot_fingerprint": str(
                candidate.get("source_version_id") or expected_source
            ),
            "index_version_id": index_version_id,
            "artifact_digest": str(candidate.get("artifact_digest") or ""),
            "doc_count": int(candidate.get("doc_count") or 0),
            "section_count": int(candidate.get("section_count") or 0),
        }
        progress(2, 2, "Ready Data build complete")
        return CollectionResult(
            success=True,
            items_found=result["doc_count"],
            items_downloaded=result["section_count"],
            items_skipped=0,
            errors=[],
            metadata={"kb_id": kb_id, "result": result},
        )

    def _run_search_task(
        self,
        task_id: str,
        storage: Storage,
        config: dict[str, Any],
        download_dir: str,
        data: dict[str, Any],
    ) -> CollectionResult:
        query = str(data.get("query") or "").strip()
        if not query:
            raise RuntimeError("query is required for search tasks")

        defaults = dict(config.get("defaults") or {})
        search_cfg = dict(config.get("search") or {})
        delay_seconds = self._configured_delay_seconds(
            search_cfg.get("delay_seconds"), defaults.get("delay_seconds")
        )
        user_agent = str(defaults.get("user_agent") or "AI-Actuarial/1.0")
        use_defaults = bool(data.get("use_search_defaults", True))

        site_filter = str(data.get("site") or "").strip()
        search_query = self._query_with_site_filter(query, site_filter)
        max_results = self._positive_int(
            data.get("count"), self._positive_int(search_cfg.get("max_results"), 5)
        )

        languages = self._coerce_list(data.get("search_lang"))
        if not languages and use_defaults:
            languages = self._coerce_list(search_cfg.get("languages"))
        if not languages:
            languages = ["en"]

        countries = self._coerce_list(data.get("search_country"))
        country = (
            countries[0]
            if countries
            else (str(search_cfg.get("country") or "").strip() if use_defaults else "")
        )
        country = country or None

        file_exts = self._coerce_list(data.get("file_exts"))
        if not file_exts and use_defaults:
            file_exts = self._coerce_list(defaults.get("file_exts"))

        keywords = self._coerce_list(data.get("keywords"))
        if not keywords and use_defaults:
            keywords = self._coerce_list(defaults.get("keywords"))

        exclude_keywords = self._coerce_list(
            data.get("search_exclude_keywords")
        ) or self._coerce_list(data.get("exclude_keywords"))
        if use_defaults:
            exclude_keywords = self._dedupe_list(
                exclude_keywords + self._coerce_list(search_cfg.get("exclude_keywords"))
            )

        exclude_prefixes = self._coerce_list(
            data.get("search_exclude_prefixes")
        ) or self._coerce_list(data.get("exclude_prefixes"))
        if use_defaults:
            exclude_prefixes = self._dedupe_list(
                exclude_prefixes + self._coerce_list(defaults.get("exclude_prefixes"))
            )

        credentials = get_search_runtime_credentials(storage=storage)
        engine = str(data.get("engine") or "auto").strip().lower() or "auto"
        if engine in {"all", "auto"}:
            selected_credentials = dict(credentials)
        else:
            if engine not in {"brave", "google", "serper", "tavily"}:
                raise RuntimeError(f"Unsupported search engine: {engine}")
            if not credentials.get(engine):
                raise RuntimeError(f"Search engine '{engine}' is not configured")
            selected_credentials = {
                key: value if key == engine else None for key, value in credentials.items()
            }

        progress = self._progress_callback(task_id)
        progress(0, max_results, f"Searching: {query}")
        results = search_all(
            [search_query],
            max_results,
            selected_credentials.get("brave"),
            selected_credentials.get("google"),
            user_agent,
            languages=languages,
            country=country,
            serper_key=selected_credentials.get("serper"),
            tavily_key=selected_credentials.get("tavily"),
        )
        discovery_results = list(results)

        crawler = Crawler(
            storage,
            download_dir,
            user_agent,
            stop_check=lambda: self._stop_requested(task_id),
            default_delay_seconds=delay_seconds,
        )
        acquisition_outcomes: list[dict[str, Any]] = []
        total = len(discovery_results)
        progress(0, total, f"Scanning {total} search results")
        for index, result in enumerate(discovery_results, start=1):
            site_config = SiteConfig(
                name=str(data.get("name") or "Search Result"),
                url=result.url,
                max_pages=1,
                max_depth=1,
                delay_seconds=delay_seconds,
                keywords=keywords,
                file_exts=file_exts,
                exclude_keywords=exclude_keywords,
                exclude_prefixes=exclude_prefixes,
                allowed_domain=site_filter or None,
                collect_linked_files=(
                    coerce_bool(data.get("collect_linked_files"), default=True)
                    if "collect_linked_files" in data
                    else None
                ),
                collect_page_content=(
                    coerce_bool(data.get("collect_page_content"), default=False)
                    if "collect_page_content" in data
                    else None
                ),
                check_database=bool(data.get("check_database", True)),
            )
            report = crawler.scan_page_for_files_with_outcome(
                result.url,
                site_config,
                source_site=result.source,
            )
            outcome = dict(report.outcome)
            acquisition_outcomes.append(outcome)
            outcome_level = "ERROR" if int(outcome.get("failed") or 0) else "INFO"
            if int(outcome.get("downloaded") or 0) and int(outcome.get("failed") or 0):
                outcome_level = "WARNING"
            append_task_log(
                task_id,
                outcome_level,
                format_acquisition_outcome(index, total, outcome),
            )
            progress(index, total, f"Scanned search result {index}/{total}")

        acquisition_summary = summarize_acquisition_outcomes(acquisition_outcomes)
        append_task_log(
            task_id,
            "INFO",
            f"Search acquisition summary: {format_acquisition_summary(acquisition_summary)}",
        )
        failed_outcomes = [
            (index, outcome)
            for index, outcome in enumerate(acquisition_outcomes, start=1)
            if int(outcome.get("failed") or 0)
        ]
        errors = [
            (
                f"Search result {index} acquisition {outcome.get('disposition')}: "
                f"{outcome.get('reason')} (url={outcome.get('url')})"
            )
            for index, outcome in failed_outcomes
        ]
        warnings = list(errors) if acquisition_summary["downloaded"] and errors else []
        if warnings:
            count = len(failed_outcomes)
            append_task_log(
                task_id,
                "WARNING",
                f"Search acquisition completed with {count} failed result{'s' if count != 1 else ''}",
            )
        elif errors:
            append_task_log(
                task_id,
                "ERROR",
                f"Search acquisition failed for {len(failed_outcomes)} result(s)",
            )

        search_no_results = acquisition_summary["total"] == 0
        no_op_reason = None
        if search_no_results:
            no_op_reason = "search_no_results"
        elif not acquisition_summary["downloaded"] and not acquisition_summary["failed"]:
            active_noop_dispositions = [
                name
                for name in ("already_exists", "filtered", "no_eligible_file_found")
                if acquisition_summary[name]
            ]
            no_op_reason = (
                active_noop_dispositions[0]
                if len(active_noop_dispositions) == 1
                else "already_exists_or_filtered"
            )
        stopped = any(
            outcome.get("disposition") == "stopped_or_timeout"
            and outcome.get("subreason") == "stopped"
            for outcome in acquisition_outcomes
        )
        success = bool(
            search_no_results
            or not acquisition_summary["failed"]
            or acquisition_summary["downloaded"]
        )

        return CollectionResult(
            success=success,
            items_found=acquisition_summary["downloaded"],
            items_downloaded=acquisition_summary["downloaded"],
            items_skipped=acquisition_summary["skipped"],
            errors=errors,
            metadata={
                "source_type": "search",
                "engine": engine,
                "query": query,
                "search_results": total,
                "site_filter": site_filter,
                "acquisition_outcomes": acquisition_outcomes,
                "acquisition_summary": acquisition_summary,
                "search_no_results": search_no_results,
                "no_op_reason": no_op_reason,
                "warnings": warnings,
                "stopped": stopped,
            },
        )

    def _run_markdown_conversion(
        self,
        task_id: str,
        storage: Storage,
        config: dict[str, Any],
        download_dir: str,
        data: dict[str, Any],
    ) -> CollectionResult:
        candidate_data = dict(data)
        candidate_data["_markdown_download_dir"] = download_dir
        file_rows = self._markdown_candidate_files(storage, candidate_data)
        if not file_rows:
            return CollectionResult(
                success=True,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[],
                metadata={
                    "source_type": "markdown_conversion",
                    "stopped": False,
                    "items_terminal_skipped": 0,
                    "result": {"contract_version": 1, "files": [], "outcomes": []},
                },
            )

        md_config = load_markdown_conversion_config()
        conversion_tool = (
            str(data.get("conversion_tool") or md_config.get("default_tool") or "auto")
            .strip()
            .lower()
            or "auto"
        )
        explicit_runtime = None
        if conversion_tool != "auto":
            explicit_tool_cfg = (md_config.get("tools") or {}).get(conversion_tool) or {}
            if not isinstance(explicit_tool_cfg, dict) or not explicit_tool_cfg.get(
                "enabled", True
            ):
                raise RuntimeError(
                    f"Markdown conversion tool '{conversion_tool}' is disabled or not configured"
                )
            explicit_model = explicit_tool_cfg.get("model")
            explicit_runtime = resolve_ocr_runtime(
                storage=storage,
                yaml_config=config,
                engine_override=conversion_tool,
                model_override=str(explicit_model).strip() if explicit_model else None,
            )
            if explicit_runtime.provider != "local" and not explicit_runtime.api_key:
                raise RuntimeError(f"OCR provider '{explicit_runtime.provider}' is not configured")

        overwrite_existing = bool(data.get("overwrite_existing", False))
        skip_existing = bool(data.get("skip_existing", True)) and not overwrite_existing
        progress = self._progress_callback(task_id)
        errors: list[str] = []
        converted = 0
        skipped = 0
        terminal_skipped = 0
        stopped = False
        total = len(file_rows)
        progress(0, total, "Starting markdown conversion")
        last_resolved_engine = explicit_runtime.engine if explicit_runtime is not None else "auto"
        last_provider = explicit_runtime.provider if explicit_runtime is not None else "auto"
        result_files: list[dict[str, Any]] = []
        result_outcomes: list[dict[str, Any]] = []

        for index, row in enumerate(file_rows, start=1):
            file_url = str(row.get("url") or "").strip()
            if self._stop_requested(task_id):
                stopped = True
                errors.append("Task stopped by user")
                break
            if skip_existing and str(row.get("markdown_content") or "").strip():
                if row.get("terminal_code"):
                    storage.clear_markdown_terminal_source_state(file_url)
                skipped += 1
                markdown_hash = hashlib.sha256(
                    str(row["markdown_content"]).encode("utf-8")
                ).hexdigest()
                file_result = {
                    "file_url": file_url,
                    "markdown_hash": markdown_hash,
                    "markdown_version": markdown_hash,
                    "status": "ready",
                    "outcome": "skipped_existing",
                }
                result_files.append(file_result)
                result_outcomes.append(file_result)
                progress(index, total, f"Skipped existing markdown {index}/{total}")
                if self._stop_requested(task_id):
                    stopped = True
                    errors.append("Task stopped by user")
                    break
                continue
            preflight = row.get("_markdown_preflight")
            if not isinstance(preflight, dict):
                preflight = self._markdown_source_preflight(row, download_dir)
            local_path = Path(str(preflight["local_path"]))
            source_fingerprint = str(preflight["source_fingerprint"])
            terminal_code = str(preflight.get("terminal_code") or "")
            if terminal_code:
                storage.record_markdown_terminal_source_state(
                    file_url=file_url,
                    terminal_code=terminal_code,
                    source_fingerprint=source_fingerprint,
                )
                terminal_skipped += 1
                if hasattr(self, "task_lock") and hasattr(self, "active_tasks"):
                    self._update_task(task_id, items_terminal_skipped=terminal_skipped)
                result_outcomes.append(
                    {
                        "file_url": file_url,
                        "status": "terminal_skipped",
                        "outcome": "terminal_skipped",
                        "terminal_code": terminal_code,
                    }
                )
                progress(index, total, f"Terminal source skipped {index}/{total}")
                continue
            if row.get("terminal_code"):
                storage.clear_markdown_terminal_source_state(file_url)
            try:
                output, provider = self._convert_markdown_candidate_chain(
                    local_path,
                    explicit_runtime=explicit_runtime,
                    storage=storage,
                    config=config,
                    md_config=md_config,
                )
                last_resolved_engine = output.engine
                source_model = str(output.model)
                source_engine = str(output.engine)
                ok, reason = storage.update_file_markdown(
                    file_url,
                    output.markdown,
                    markdown_source=f"{source_engine}:{source_model}".strip(":"),
                )
                if ok:
                    converted += 1
                    last_provider = provider
                    markdown_hash = hashlib.sha256(output.markdown.encode("utf-8")).hexdigest()
                    file_result = {
                        "file_url": file_url,
                        "markdown_hash": markdown_hash,
                        "markdown_version": markdown_hash,
                        "status": "ready",
                        "outcome": "converted",
                    }
                    result_files.append(file_result)
                    result_outcomes.append(file_result)
                else:
                    detail = str(reason or "markdown update failed")
                    errors.append(f"{file_url}: {detail}")
                    result_outcomes.append(
                        {
                            "file_url": file_url,
                            "status": "error",
                            "outcome": "retryable_error",
                            "detail": detail,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                detail = _safe_markdown_failure_detail(exc, local_path)
                errors.append(f"{file_url}: {detail}")
                result_outcomes.append(
                    {
                        "file_url": file_url,
                        "status": "error",
                        "outcome": "retryable_error",
                        "detail": detail,
                    }
                )
            progress(index, total, f"Converted markdown {index}/{total}")
            if self._stop_requested(task_id):
                stopped = True
                errors.append("Task stopped by user")
                break

        return CollectionResult(
            success=not errors and not stopped and terminal_skipped == 0,
            items_found=total,
            items_downloaded=converted,
            items_skipped=skipped,
            errors=errors,
            metadata={
                "source_type": "markdown_conversion",
                "conversion_tool": conversion_tool,
                "resolved_engine": last_resolved_engine,
                "provider": last_provider,
                "stopped": stopped,
                "items_terminal_skipped": terminal_skipped,
                "result": {
                    "contract_version": 1,
                    "files": result_files,
                    "outcomes": result_outcomes,
                },
            },
        )

    def _convert_markdown_candidate_chain(
        self,
        local_path: Path,
        *,
        explicit_runtime: Any | None,
        storage: Storage,
        config: dict[str, Any],
        md_config: dict[str, Any],
    ) -> Any:
        if explicit_runtime is not None:
            apply_ocr_runtime_environment(explicit_runtime)
            output = _convert_document_path(
                local_path,
                engine=explicit_runtime.engine,  # type: ignore[arg-type]
                model=explicit_runtime.model,
                api_key=explicit_runtime.api_key,
                base_url=explicit_runtime.base_url,
            )
            return output, explicit_runtime.provider

        candidates = candidate_chain_for_path(local_path, md_config, auto_only=True)
        if not candidates:
            raise RuntimeError(f"No auto conversion candidates configured for {local_path.name}")

        last_exc: Exception | None = None
        failure_details: list[tuple[str, str]] = []
        for candidate in candidates:
            tool_cfg = (md_config.get("tools") or {}).get(candidate) or {}
            candidate_model = tool_cfg.get("model") if isinstance(tool_cfg, dict) else None
            try:
                runtime = resolve_ocr_runtime(
                    storage=storage,
                    yaml_config=config,
                    engine_override=candidate,
                    model_override=str(candidate_model).strip() if candidate_model else None,
                )
            except Exception as exc:  # noqa: BLE001 - auto mode tries fallbacks
                last_exc = exc
                failure_details.append((candidate, _safe_markdown_failure_detail(exc, local_path)))
                continue
            if runtime.provider != "local" and not runtime.api_key:
                failure_details.append((candidate, "provider not configured"))
                continue
            try:
                apply_ocr_runtime_environment(runtime)
                output = _convert_document_path(
                    local_path,
                    engine=runtime.engine,  # type: ignore[arg-type]
                    model=runtime.model,
                    api_key=runtime.api_key,
                    base_url=runtime.base_url,
                )
                return output, runtime.provider
            except Exception as exc:  # noqa: BLE001 - auto mode tries fallbacks
                last_exc = exc
                failure_details.append((candidate, _safe_markdown_failure_detail(exc, local_path)))
                continue

        raise RuntimeError(_format_markdown_auto_failure(local_path, failure_details)) from last_exc

    def _run_chunk_generation(
        self,
        task_id: str,
        storage: Storage,
        db_path: str,
        data: dict[str, Any],
    ) -> CollectionResult:
        warnings = validate_chunk_generation_payload(data)
        chunk_size = self._positive_int(data.get("chunk_size"), 800)
        chunk_overlap = self._positive_int(data.get("chunk_overlap"), 100, min_value=0)
        if chunk_overlap >= chunk_size:
            chunk_overlap = max(0, chunk_size - 1)
        payload = {
            "profile_id": str(data.get("profile_id") or "").strip(),
            "name": str(data.get("profile_name") or data.get("chunk_profile_name") or "").strip()
            or f"default-{chunk_size}-{chunk_overlap}",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "splitter": str(data.get("splitter") or "semantic").strip(),
            "tokenizer": str(data.get("tokenizer") or "cl100k_base").strip(),
            "version": str(data.get("version") or "v1").strip(),
            "overwrite_same_profile": False,
        }
        if not payload["profile_id"]:
            try:
                profile = storage.create_chunk_profile(
                    name=payload["name"],
                    chunk_size=payload["chunk_size"],
                    chunk_overlap=payload["chunk_overlap"],
                    splitter=payload["splitter"],
                    tokenizer=payload["tokenizer"],
                    version=payload["version"],
                    metadata={},
                    upsert=True,
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            payload["profile_id"] = str(profile.get("profile_id") or "")

        candidate_data = {**data, "profile_id": payload["profile_id"]}
        file_urls = self._chunk_candidate_file_urls(storage, candidate_data)
        expected_hashes = {
            str(item.get("file_url") or "").strip(): str(item.get("markdown_hash") or "").strip()
            for item in (data.get("files") or [])
            if isinstance(item, dict)
        }
        if not file_urls:
            return CollectionResult(
                success=True,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[],
                metadata={
                    "source_type": "chunk_generation",
                    "stopped": False,
                    "warnings": warnings,
                    "result": {"contract_version": 1, "chunk_sets": []},
                },
            )

        progress = self._progress_callback(task_id)
        errors: list[str] = []
        generated = 0
        skipped = 0
        stopped = False
        total_chunks = 0
        chunk_sets: list[dict[str, Any]] = []
        total = len(file_urls)
        progress(0, total, "Starting chunk generation")
        for index, file_url in enumerate(file_urls, start=1):
            if self._stop_requested(task_id):
                stopped = True
                errors.append("Task stopped by user")
                break
            try:
                result = generate_file_chunk_sets(
                    db_path=db_path,
                    file_url=file_url,
                    payload=payload,
                    expected_markdown_hash=expected_hashes.get(file_url) or None,
                )
                if result.get("reused_existing") and not result.get("overwrote_existing"):
                    skipped += 1
                else:
                    generated += 1
                total_chunks += int(result.get("chunk_count") or 0)
                chunk_sets.append(
                    {
                        "file_url": file_url,
                        "markdown_hash": str(result.get("markdown_hash") or ""),
                        "profile_id": str(result.get("profile_id") or ""),
                        "profile_config_hash": str(result.get("profile_config_hash") or ""),
                        "chunk_set_id": str(result.get("chunk_set_id") or ""),
                        "chunk_count": int(result.get("chunk_count") or 0),
                        "reused_existing": bool(result.get("reused_existing", False)),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{file_url}: {exc}")
            progress(index, total, f"Generated chunks {index}/{total}")
            if self._stop_requested(task_id):
                stopped = True
                errors.append("Task stopped by user")
                break

        return CollectionResult(
            success=not errors and not stopped,
            items_found=total,
            items_downloaded=generated,
            items_skipped=skipped,
            errors=errors,
            metadata={
                "source_type": "chunk_generation",
                "profile_name": payload["name"],
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "total_chunks": total_chunks,
                "stopped": stopped,
                "warnings": warnings,
                "result": {"contract_version": 1, "chunk_sets": chunk_sets},
            },
        )

    def _run_embedding_generation(
        self,
        task_id: str,
        storage: Storage,
        data: dict[str, Any],
    ) -> CollectionResult:
        validate_embedding_generation_payload(data)
        identity = resolve_server_embedding_identity(
            storage,
            str(data.get("embedding_identity_key") or "").strip() or None,
        )
        selection = resolve_embedding_selection(
            storage,
            chunk_set_ids=self._coerce_list(data.get("chunk_set_ids")),
            file_urls=self._coerce_list(data.get("file_urls")),
            profile_id=str(data.get("profile_id") or "").strip() or None,
            incremental=coerce_bool(data.get("incremental"), default=False),
            identity=identity,
        )
        progress = self._progress_callback(task_id)
        chunks = list(selection["chunks"])
        ensured = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            batch_size=identity.config.embedding_batch_size,
            stop_check=lambda: self._stop_requested(task_id),
            progress_callback=progress,
        )
        coverage = embedding_coverage_for_selection(
            storage=storage,
            selection=selection,
            identity=identity,
        )
        status = "stopped" if ensured.stopped else ("completed" if not ensured.failed else "error")
        items_processed = (
            ensured.reused + ensured.generated + ensured.invalid_regenerated + ensured.failed
        )
        result = {
            "contract_version": 1,
            "job_id": task_id,
            "status": status,
            **identity.as_dict(),
            "requested_file_urls": selection["requested_file_urls"],
            "requested_chunk_set_ids": selection["requested_chunk_set_ids"],
            "resolved_file_urls": list(
                dict.fromkeys(str(row["file_url"]) for row in selection["chunk_sets"])
            ),
            "chunk_set_ids": selection["chunk_set_ids"],
            "requested_count": len(selection["requested_file_urls"])
            + len(selection["requested_chunk_set_ids"]),
            "resolved_count": len(selection["chunk_set_ids"]),
            "expected_count": ensured.expected_count,
            "ready_count": ensured.ready_count,
            "generated": ensured.generated,
            "reused": ensured.reused,
            "invalid_regenerated": ensured.invalid_regenerated,
            "failed": ensured.failed,
            "persisted_record_count": ensured.persisted_record_count,
            "per_file": coverage["per_file"],
            "errors": ensured.errors,
            "started_at": ensured.started_at,
            "completed_at": ensured.completed_at,
        }
        return CollectionResult(
            success=not ensured.failed and not ensured.stopped,
            items_found=ensured.expected_count,
            items_downloaded=ensured.generated + ensured.invalid_regenerated,
            items_skipped=ensured.reused,
            errors=[str(error["code"]) for error in ensured.errors],
            metadata={
                "source_type": "embedding_generation",
                "stopped": ensured.stopped,
                "items_processed": items_processed,
                "items_total": ensured.expected_count,
                "result": result,
            },
        )

    def _collect_file_paths(self, data: dict[str, Any]) -> list[str]:
        upload_batch_id = str(data.get("upload_batch_id") or "").strip()
        if not upload_batch_id:
            raise ValueError("File imports must use an upload batch")
        from ai_actuarial.api.services.import_batches import file_paths_for_batch

        raw_exts = list(data.get("extensions") or [])
        allowed_exts = {str(ext).lower().lstrip(".") for ext in raw_exts if str(ext).strip()}
        paths = file_paths_for_batch(upload_batch_id)
        if allowed_exts:
            paths = [
                path for path in paths if Path(path).suffix.lower().lstrip(".") in allowed_exts
            ]
        return paths

    def _site_configs_for_run(
        self, config: dict[str, Any], data: dict[str, Any]
    ) -> list[SiteConfig]:
        defaults = dict(config.get("defaults") or {})
        sites = list(config.get("sites") or [])
        selected_site = str(data.get("site") or "").strip()
        site_rows = [
            row for row in sites if not selected_site or str(row.get("name") or "") == selected_site
        ]
        default_exclude_keywords = self._coerce_list(defaults.get("exclude_keywords"))
        default_exclude_prefixes = self._coerce_list(defaults.get("exclude_prefixes"))
        return [
            SiteConfig(
                name=str(row.get("name") or "Unnamed Site"),
                url=str(row.get("url") or ""),
                max_pages=self._positive_int(
                    data.get("max_pages"),
                    self._positive_int(
                        row.get("max_pages"), self._positive_int(defaults.get("max_pages"), 200)
                    ),
                ),
                max_depth=self._positive_int(
                    data.get("max_depth"),
                    self._positive_int(
                        row.get("max_depth"), self._positive_int(defaults.get("max_depth"), 2)
                    ),
                ),
                delay_seconds=self._configured_delay_seconds(
                    row.get("delay_seconds"), defaults.get("delay_seconds")
                ),
                keywords=list(row.get("keywords") or defaults.get("keywords") or []),
                file_exts=list(row.get("file_exts") or defaults.get("file_exts") or []),
                exclude_keywords=self._dedupe_list(
                    default_exclude_keywords + self._coerce_list(row.get("exclude_keywords"))
                ),
                exclude_prefixes=self._dedupe_list(
                    default_exclude_prefixes + self._coerce_list(row.get("exclude_prefixes"))
                ),
                collect_linked_files=(
                    coerce_bool(row.get("collect_linked_files"), default=True)
                    if "collect_linked_files" in row
                    else None
                ),
                collect_page_content=(
                    coerce_bool(row.get("collect_page_content"), default=False)
                    if "collect_page_content" in row
                    else None
                ),
                acquisition_tools=self._coerce_list(row.get("acquisition_tools")) or None,
                content_selector=str(row.get("content_selector") or "").strip() or None,
                allow_url_patterns=self._coerce_list(row.get("allow_url_patterns")),
                queries=list(row.get("queries") or []),
                check_database=bool(data.get("check_database", True)),
            )
            for row in site_rows
            if str(row.get("url") or "").strip()
        ]

    def _quick_check_site_config(self, config: dict[str, Any], data: dict[str, Any]) -> SiteConfig:
        defaults = dict(config.get("defaults") or {})
        search_cfg = dict(config.get("search") or {})
        return SiteConfig(
            name=str(data.get("name") or "Quick Check"),
            url=str(data.get("url") or "").strip(),
            max_pages=self._positive_int(
                data.get("max_pages"), self._positive_int(defaults.get("max_pages"), 10)
            ),
            max_depth=self._positive_int(
                data.get("max_depth"), self._positive_int(defaults.get("max_depth"), 1)
            ),
            delay_seconds=self._configured_delay_seconds(
                data.get("delay_seconds"), defaults.get("delay_seconds")
            ),
            keywords=self._coerce_list(data.get("keywords"))
            or self._coerce_list(defaults.get("keywords")),
            file_exts=self._coerce_list(data.get("file_exts"))
            or self._coerce_list(defaults.get("file_exts")),
            exclude_keywords=self._dedupe_list(
                self._coerce_list(data.get("exclude_keywords"))
                + self._coerce_list(defaults.get("exclude_keywords"))
                + self._coerce_list(search_cfg.get("exclude_keywords"))
            ),
            exclude_prefixes=self._coerce_list(defaults.get("exclude_prefixes")),
            check_database=bool(data.get("check_database", True)),
        )

    def _markdown_source_preflight(
        self,
        row: dict[str, Any],
        download_dir: str,
    ) -> dict[str, Any]:
        raw_path = str(row.get("local_path") or "").strip()
        fingerprint_payload: dict[str, Any] = {
            "sha256": str(row.get("sha256") or ""),
            "local_path": raw_path,
            "bytes": row.get("bytes"),
            "original_filename": str(row.get("original_filename") or ""),
            "content_type": str(row.get("content_type") or "").strip().lower(),
            "content_kind": str(row.get("content_kind") or "").strip().lower(),
        }

        def outcome(
            local_path: Path,
            path_state: dict[str, Any],
            terminal_code: str = "",
        ) -> dict[str, Any]:
            fingerprint_payload["path_state"] = path_state
            source_fingerprint = hashlib.sha256(
                json.dumps(
                    fingerprint_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            return {
                "local_path": str(local_path),
                "source_fingerprint": source_fingerprint,
                "terminal_code": terminal_code,
            }

        if not raw_path:
            return outcome(Path(), {"kind": "missing"}, "repair_required")

        local_path = self._resolve_file_path(raw_path, download_dir)
        try:
            stat = local_path.stat()
        except OSError:
            return outcome(local_path, {"kind": "missing"}, "repair_required")
        if not local_path.is_file():
            return outcome(
                local_path,
                {
                    "kind": "not_file",
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                },
                "repair_required",
            )
        try:
            with local_path.open("rb") as handle:
                header = handle.read(_MARKDOWN_PREFLIGHT_READ_BYTES)
        except OSError:
            return outcome(
                local_path,
                {
                    "kind": "unreadable",
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                },
                "repair_required",
            )

        path_state = {
            "kind": "file",
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "header_sha256": hashlib.sha256(header).hexdigest(),
        }
        suffixes = {
            Path(str(row.get("original_filename") or "")).suffix.lower(),
            local_path.suffix.lower(),
            Path(urlparse(str(row.get("url") or "")).path).suffix.lower(),
        }
        content_type = str(row.get("content_type") or "").strip().lower()
        content_kind = str(row.get("content_kind") or "").strip().lower()
        normalized_header = header.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")[:512].lower()
        html_magic = bool(
            re.match(
                rb"(?:<!doctype\s+html|<html(?:\s|>)|<head(?:\s|>)|<body(?:\s|>))",
                normalized_header,
            )
        )
        declared_html = content_kind == "web_page" or content_type.startswith(
            ("text/html", "application/xhtml+xml")
        )
        pdf_candidate = ".pdf" in suffixes or "pdf" in content_type
        if pdf_candidate and (declared_html or html_magic):
            return outcome(local_path, path_state, "invalid_source")
        if ".ppt" in suffixes and header.startswith(_OLE_COMPOUND_FILE_HEADER):
            return outcome(local_path, path_state, "unsupported_legacy_ppt")
        return outcome(local_path, path_state)

    @staticmethod
    def _markdown_candidate_row(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "url": row[0],
            "local_path": row[1],
            "original_filename": row[2],
            "content_type": row[3],
            "markdown_content": row[4],
            "sha256": row[5],
            "bytes": row[6],
            "content_kind": row[7],
            "terminal_code": row[8],
            "terminal_source_fingerprint": row[9],
        }

    def _markdown_candidate_files(
        self, storage: Storage, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        explicit_urls = self._explicit_file_urls(data)
        overwrite_existing = bool(data.get("overwrite_existing", False))
        skip_existing = bool(data.get("skip_existing", True)) and not overwrite_existing
        download_dir = str(data.get("_markdown_download_dir") or "")
        conn = storage._conn
        if explicit_urls:
            placeholders = ",".join("?" for _ in explicit_urls)
            rows = conn.execute(
                f"""
                SELECT f.url, f.local_path, f.original_filename, f.content_type,
                       c.markdown_content, f.sha256, f.bytes, f.content_kind,
                       mts.terminal_code, mts.source_fingerprint
                FROM files f
                LEFT JOIN catalog_items c ON c.file_url = f.url
                LEFT JOIN markdown_terminal_source_state mts ON mts.file_url = f.url
                WHERE f.url IN ({placeholders})
                  AND f.deleted_at IS NULL
                """,
                tuple(explicit_urls),
            ).fetchall()
            by_url = {str(row[0]): self._markdown_candidate_row(row) for row in rows}
            return [by_url[url] for url in explicit_urls if url in by_url]

        category_sql, params = self._category_sql(
            str(data.get("category") or "").strip(), alias="c"
        )
        where = _CONVERTIBLE_MARKDOWN_PREDICATE + category_sql
        if skip_existing:
            where += " AND (c.markdown_content IS NULL OR c.markdown_content = '')"
        md_config = load_markdown_conversion_config()
        raw_limits = md_config.get("limits")
        limits = raw_limits if isinstance(raw_limits, dict) else {}
        default_limit = self._positive_int(limits.get("default_scan_count"), 50)
        max_limit = min(
            HARD_MAX_SCAN_COUNT,
            max(default_limit, self._positive_int(limits.get("max_scan_count"), 2000)),
        )
        limit = min(self._positive_int(data.get("scan_count"), default_limit), max_limit)
        offset = max(0, self._positive_int(data.get("scan_start_index"), 1) - 1)
        query = f"""
            SELECT f.url, f.local_path, f.original_filename, f.content_type,
                   c.markdown_content, f.sha256, f.bytes, f.content_kind,
                   mts.terminal_code, mts.source_fingerprint
            FROM files f
            LEFT JOIN catalog_items c ON c.file_url = f.url
            LEFT JOIN markdown_terminal_source_state mts ON mts.file_url = f.url
            WHERE {where}
            ORDER BY f.id DESC
            LIMIT ? OFFSET ?
        """
        selected: list[dict[str, Any]] = []
        logical_index = 0
        raw_offset = 0
        while len(selected) < limit:
            rows = conn.execute(
                query,
                tuple(params + [_MARKDOWN_TERMINAL_SCAN_PAGE_SIZE, raw_offset]),
            ).fetchall()
            if not rows:
                break
            raw_offset += len(rows)
            for raw_row in rows:
                row = self._markdown_candidate_row(raw_row)
                if row.get("terminal_code"):
                    preflight = self._markdown_source_preflight(row, download_dir)
                    if str(preflight["source_fingerprint"]) == str(
                        row.get("terminal_source_fingerprint") or ""
                    ):
                        continue
                    row["_markdown_preflight"] = preflight
                if logical_index < offset:
                    logical_index += 1
                    continue
                selected.append(row)
                if len(selected) >= limit:
                    break
                logical_index += 1
            if len(rows) < _MARKDOWN_TERMINAL_SCAN_PAGE_SIZE:
                break
        return selected

    def _chunk_candidate_file_urls(self, storage: Storage, data: dict[str, Any]) -> list[str]:
        if "files" in data:
            raw_files = data.get("files")
            if not isinstance(raw_files, list):
                raise RuntimeError("chunk files selector must be a list")
            selectors: list[tuple[str, str]] = []
            seen: set[str] = set()
            for raw in raw_files:
                if not isinstance(raw, dict):
                    raise RuntimeError("chunk files selector entries must be objects")
                file_url = str(raw.get("file_url") or "").strip()
                expected_hash = str(raw.get("markdown_hash") or "").strip()
                markdown_version = str(raw.get("markdown_version") or expected_hash).strip()
                if not file_url or not expected_hash or markdown_version != expected_hash:
                    raise RuntimeError(
                        "chunk files selector requires a stable Markdown hash/version"
                    )
                if file_url in seen:
                    raise RuntimeError(f"duplicate chunk file selector: {file_url}")
                seen.add(file_url)
                selectors.append((file_url, expected_hash))
            for file_url, expected_hash in selectors:
                row = storage._conn.execute(
                    """
                    SELECT c.markdown_content
                    FROM files f
                    JOIN catalog_items c ON c.file_url = f.url
                    WHERE f.url = ? AND f.deleted_at IS NULL
                    """,
                    (file_url,),
                ).fetchone()
                markdown_content = str((row or [""])[0] or "")
                current_hash = hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()
                if not markdown_content or current_hash != expected_hash:
                    raise RuntimeError(
                        f"Markdown changed for {file_url}; rerun Markdown conversion"
                    )
            return [file_url for file_url, _expected_hash in selectors]

        explicit_urls = self._explicit_file_urls(data)
        if explicit_urls:
            return [
                str(row[0])
                for row in storage._conn.execute(
                    f"""
                    SELECT f.url
                    FROM files f
                    JOIN catalog_items c ON c.file_url = f.url
                    WHERE f.url IN ({",".join("?" for _ in explicit_urls)})
                      AND f.deleted_at IS NULL
                      AND c.markdown_content IS NOT NULL
                      AND c.markdown_content != ''
                    """,
                    tuple(explicit_urls),
                ).fetchall()
            ]

        category_sql, params = self._category_sql(
            str(data.get("category") or "").strip(), alias="c"
        )
        where = """
            f.deleted_at IS NULL
            AND c.markdown_content IS NOT NULL
            AND c.markdown_content != ''
        """ + category_sql
        limit = self._positive_int(data.get("scan_count"), 50)
        offset = max(0, self._positive_int(data.get("scan_start_index"), 1) - 1)
        rows = storage._conn.execute(
            f"""
            SELECT f.url
            FROM files f
            JOIN catalog_items c ON c.file_url = f.url
            WHERE {where}
            ORDER BY f.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        return [str(row[0]) for row in rows if row and row[0]]

    def _explicit_file_urls(self, data: dict[str, Any]) -> list[str]:
        return [value for value in self._coerce_list(data.get("file_urls")) if value]

    def _resolve_file_path(self, raw_path: Any, download_dir: str) -> Path:
        raw = str(raw_path or "").strip()
        path = Path(raw)
        candidates: list[Path] = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend(
                [
                    Path.cwd() / path,
                    Path(download_dir).parent / path,
                    Path(download_dir) / path,
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return candidates[0].resolve() if candidates else path.resolve()

    def _category_sql(self, category_filter: str, *, alias: str) -> tuple[str, list[Any]]:
        category_name = str(category_filter or "").strip()
        if not category_name:
            return "", []
        return (
            f" AND ({alias}.category = ? OR {alias}.category LIKE ? OR {alias}.category LIKE ? OR {alias}.category LIKE ?)",
            [
                category_name,
                f"{category_name};%",
                f"%; {category_name}",
                f"%; {category_name};%",
            ],
        )

    def _query_with_site_filter(self, query: str, site_filter: str) -> str:
        site = str(site_filter or "").strip()
        if not site or "site:" in query.lower():
            return query
        return f"{query} site:{site}"

    def _dedupe_search_results(self, results: list[Any], *, site_filter: str = "") -> list[Any]:
        seen: set[str] = set()
        out: list[Any] = []
        site = self._normalized_site_host(site_filter)
        for result in results:
            url = str(getattr(result, "url", "") or "").strip()
            if not url or url in seen:
                continue
            if site:
                host = self._normalized_site_host(urlparse(url).netloc)
                if host != site and not host.endswith(f".{site}"):
                    continue
            seen.add(url)
            out.append(result)
        return out

    def _coerce_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [
                part.strip()
                for part in value.replace("\r\n", "\n").replace(",", "\n").split("\n")
                if part.strip()
            ]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _dedupe_list(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(value.strip())
        return out

    def _configured_delay_seconds(self, *values: Any, default: float = 0.5) -> float:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return float(value)
        return float(default)

    def _positive_int(self, value: Any, default: int, *, min_value: int = 1) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, parsed)

    def _stop_requested(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.active_tasks.get(task_id)
            return bool(task and task.get("stop_requested"))

    def _progress_callback(self, task_id: str) -> Callable[[int, int, str], None]:
        def callback(current: int, total: int, message: str) -> None:
            try:
                current_int = int(current or 0)
            except (TypeError, ValueError):
                current_int = 0
            try:
                total_int = int(total or 0)
            except (TypeError, ValueError):
                total_int = 0
            progress = 0
            if total_int > 0:
                progress = min(100, max(0, int((current_int / total_int) * 100)))
            self._update_task(
                task_id,
                progress=progress,
                items_processed=current_int,
                items_total=total_int,
                current_activity=message,
            )
            append_task_log(task_id, "INFO", message)

        return callback

    def _update_task(self, task_id: str, **fields: Any) -> None:
        with self.task_lock:
            task = self.active_tasks.get(task_id)
            if task is not None:
                task.update(fields)

    def _finalize_task_success(
        self, task_id: str, collection_type: str, result: CollectionResult
    ) -> None:
        ready_followup: tuple[str, dict[str, Any]] | None = None
        with self.task_lock:
            task_data = self.active_tasks.pop(task_id, None)
            if task_data is None:
                return
            stopped = bool((result.metadata or {}).get("stopped"))
            items_processed = result.items_found
            items_total = result.items_found
            progress = 100
            if stopped and collection_type == "embedding_generation":
                items_processed = max(
                    0,
                    int((result.metadata or {}).get("items_processed") or 0),
                )
                items_total = max(
                    0,
                    int((result.metadata or {}).get("items_total") or 0),
                )
                if items_total > 0:
                    items_processed = min(items_processed, items_total)
                    progress = int((items_processed / items_total) * 100)
                else:
                    progress = 0
            task_data.update(
                {
                    "status": (
                        "stopped" if stopped else ("completed" if result.success else "error")
                    ),
                    "progress": progress,
                    "completed_at": datetime.now().isoformat(),
                    "current_activity": (
                        "Stopped"
                        if stopped
                        else ("Completed" if result.success else "Completed with errors")
                    ),
                    "items_processed": items_processed,
                    "items_total": items_total,
                    "items_downloaded": result.items_downloaded,
                    "items_skipped": result.items_skipped,
                    "items_terminal_skipped": int(
                        (result.metadata or {}).get("items_terminal_skipped") or 0
                    ),
                    "errors": list(result.errors or []),
                    "metadata": dict(result.metadata or {}),
                }
            )
            canonical_result = (result.metadata or {}).get("result")
            if isinstance(canonical_result, dict):
                task_data["result"] = canonical_result
            if (
                collection_type == "rag_indexing"
                and result.success
                and isinstance(canonical_result, dict)
                and not task_data.get("pipeline_baton_source_task_id")
            ):
                kb_id = str(
                    (result.metadata or {}).get("kb_id") or task_data.get("kb_id") or ""
                ).strip()
                if kb_id:
                    ready_followup = (kb_id, dict(canonical_result))
            if ready_followup is not None:
                kb_id, index_result = ready_followup
                try:
                    ready_payload = self._pipeline_ready_data_input(kb_id, index_result)
                    ready_task_id = self.start_background_task(
                        "ready_data_build",
                        ready_payload,
                        task_name=f"Ready Data: {kb_id}",
                        extra_fields={
                            "kb_id": kb_id,
                            "kb_index_task_id": task_id,
                        },
                    )
                    task_data["ready_data_task_id"] = ready_task_id
                except Exception as exc:  # noqa: BLE001
                    task_data["ready_data_launch_error"] = str(exc)
                    append_task_log(
                        task_id,
                        "ERROR",
                        f"Ready Data task launch failed: {exc}",
                    )
            if collection_type == "weekly_summary" and result.success:
                snapshot_id = str((result.metadata or {}).get("summary_id") or "").strip()
                if snapshot_id:
                    try:
                        explanation_task_id = self.start_background_task(
                            "weekly_explanation",
                            {"snapshot_id": snapshot_id},
                            task_name=f"Weekly explanation: {snapshot_id}",
                            extra_fields={
                                "snapshot_id": snapshot_id,
                                "weekly_snapshot_task_id": task_id,
                            },
                        )
                        task_data["explanation_task_id"] = explanation_task_id
                    except Exception as exc:  # noqa: BLE001
                        task_data["explanation_launch_error"] = str(exc)
                        append_task_log(
                            task_id,
                            "ERROR",
                            f"Weekly explanation task launch failed: {exc}",
                        )
            self.task_history.append(task_data)
        append_task_log(
            task_id, "INFO", f"Task finished (type={collection_type}, success={result.success})"
        )
        self._append_history_to_disk(task_data)

    def _finalize_task_error(
        self,
        task_id: str,
        error: str,
        *,
        error_code: str | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        with self.task_lock:
            task_data = self.active_tasks.pop(task_id, None)
            if task_data is None:
                return
            task_data.update(
                {
                    "status": "error",
                    "progress": 100,
                    "completed_at": datetime.now().isoformat(),
                    "current_activity": "Failed",
                    "errors": [error],
                }
            )
            if error_code:
                task_data["error_code"] = error_code
            if error_details:
                task_data["error_details"] = dict(error_details)
            self.task_history.append(task_data)
        append_task_log(task_id, "ERROR", f"Task failed: {error}")
        self._append_history_to_disk(task_data)

    def _finalize_child_run(
        self,
        data: dict[str, Any],
        *,
        result: CollectionResult | None = None,
        error: str | None = None,
    ) -> None:
        """Persist a search-fallback child task's terminal state to ``child_run``.

        Only runs for children enqueued under a pipeline run (``parent_run_id``
        present). An exception is a hard failure (partial=0); a non-fatal
        unsuccessful result is recorded as partial=1 so the parent can surface
        it without treating it as a refusal.
        """
        child_run_id = str(data.get("child_run_id") or "").strip()
        parent_run_id = str(data.get("parent_run_id") or "").strip()
        if not child_run_id or not parent_run_id:
            return
        db_path = str(data.get("_db_path") or "").strip()
        if not db_path:
            db_path = self._resolve_db_path(self._load_site_config())
        storage = Storage(db_path)
        try:
            if error is not None:
                storage.update_child_run(child_run_id, status="failed", error=error)
                return
            if result is None:
                return
            stopped = bool((result.metadata or {}).get("stopped"))
            if result.success and not stopped:
                storage.update_child_run(child_run_id, status="succeeded", error="")
                return
            message = (
                "stopped"
                if stopped
                else ("; ".join(list(result.errors or [])) or "unsuccessful result")
            )
            storage.update_child_run(child_run_id, status="failed", partial=1, error=message)
        finally:
            storage.close()

    def _wait_and_summarize_child_runs(
        self,
        storage: Storage,
        run_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Bounded wait for pending child runs, then bucket them by terminal state."""
        children = storage.get_child_runs(run_id)
        if not children:
            return {"children": [], "failed": [], "partial": [], "pending": []}

        deadline = time.time() + _CHILD_RUN_WAIT_TIMEOUT_SECONDS
        while True:
            children = storage.get_child_runs(run_id)
            pending = [c for c in children if c.get("status") == "pending"]
            if not pending:
                break
            if self._stop_requested(task_id):
                break
            if time.time() >= deadline:
                break
            time.sleep(_CHILD_RUN_POLL_INTERVAL_SECONDS)

        children = storage.get_child_runs(run_id)
        failed = [c for c in children if c.get("status") == "failed" and not c.get("partial")]
        partial = [c for c in children if c.get("status") == "failed" and c.get("partial")]
        pending = [c for c in children if c.get("status") == "pending"]
        return {"children": children, "failed": failed, "partial": partial, "pending": pending}

    def _append_history_to_disk(self, task_data: dict[str, Any]) -> None:
        path = Path("data/job_history.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(task_data, ensure_ascii=False) + "\n")

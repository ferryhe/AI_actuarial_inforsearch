from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, time as datetime_time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import schedule

from ai_actuarial.ai_runtime import get_search_runtime_credentials, resolve_ocr_runtime
from ai_actuarial.api.services.files_write import generate_file_chunk_sets
from ai_actuarial.catalog_incremental import run_catalog_for_urls, run_incremental_catalog
from ai_actuarial.collectors.base import CollectionConfig, CollectionResult
from ai_actuarial.collectors.file import FileCollector
from ai_actuarial.collectors.scheduled import ScheduledCollector
from ai_actuarial.collectors.url import URLCollector
from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.rag.indexing import IndexingPipeline
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.search import search_all
from ai_actuarial.shared_runtime import append_task_log, get_sites_config_path, load_yaml, task_log_path
from ai_actuarial.storage import Storage

logger = logging.getLogger(__name__)

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
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.pptx'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.png'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.jpg'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.jpeg'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.webp'
        OR LOWER(IFNULL(f.original_filename,'')) LIKE '%.bmp'
    )
"""


def _convert_document_path(path: Path, **kwargs: Any) -> Any:
    from doc_to_md.registry import convert_path

    return convert_path(path, **kwargs)


class _FallbackScheduleJob:
    def __init__(
        self,
        *,
        job_func: Callable[[], None],
        interval: int,
        unit: str,
        at_time: datetime_time | None = None,
        start_day: str | None = None,
    ) -> None:
        self.job_func = job_func
        self.interval = interval
        self.unit = unit
        self.at_time = at_time
        self.start_day = start_day
        self.next_run = None
        self.last_run = None


class _FallbackScheduleBuilder:
    def __init__(self, scheduler: "_FallbackScheduler", interval: int) -> None:
        self.scheduler = scheduler
        self.interval = interval
        self.unit = "days"
        self.at_time: datetime_time | None = None
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

    def at(self, value: str) -> "_FallbackScheduleBuilder":
        parts = str(value or "").split(":")
        if len(parts) >= 2:
            self.at_time = datetime_time(int(parts[0]), int(parts[1]))
        return self

    def do(self, job_func: Callable[[], None]) -> _FallbackScheduleJob:
        job = _FallbackScheduleJob(
            job_func=job_func,
            interval=self.interval,
            unit=self.unit,
            at_time=self.at_time,
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


@dataclass(slots=True)
class RuntimeRefs:
    active_tasks_ref: dict[str, dict[str, Any]]
    task_history_ref: list[dict[str, Any]]
    task_lock: threading.RLock
    schedule_ref: schedule.Scheduler
    start_background_task: Callable[..., str]
    init_scheduler: Callable[[], None]
    set_site_config: Callable[[dict[str, Any]], None]


class NativeTaskRuntime:
    def __init__(self) -> None:
        self.active_tasks: dict[str, dict[str, Any]] = {}
        self.task_history: list[dict[str, Any]] = self._load_history_from_disk()
        self.task_lock = threading.RLock()
        self.scheduler = _new_scheduler()
        self._scheduler_lock = threading.RLock()
        self._scheduler_loop_started = False
        self._site_config_override: dict[str, Any] | None = None

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
                        logger.warning("Skipping malformed job history line %s in %s: %s", line_no, path, exc)
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
        )

    def set_site_config(self, new_config: dict[str, Any]) -> None:
        self._site_config_override = dict(new_config or {})

    def _load_site_config(self) -> dict[str, Any]:
        if self._site_config_override is not None:
            return dict(self._site_config_override)
        return load_yaml(get_sites_config_path(), default={})

    def start_background_task(
        self,
        collection_type: str,
        data: dict[str, Any],
        *,
        task_name: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> str:
        task_id = f"task_{int(time.time() * 1000)}_{secrets.token_hex(2)}"
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

    def init_scheduler(self) -> None:
        site_config = self._load_site_config()
        global_schedule = str((site_config.get("defaults") or {}).get("schedule_interval") or "").strip()
        sites = list(site_config.get("sites") or [])
        generic_tasks = list(site_config.get("scheduled_tasks") or [])

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
                params.setdefault("name", f"Scheduled: {task_name}")
                self.start_background_task(task_type, params, task_name=f"Scheduled: {task_name}")

            return job_wrapper

        with self._scheduler_lock:
            self.scheduler.clear()
            if global_schedule:
                self._register_schedule(global_schedule, global_run)
            for site in sites:
                interval = str(site.get("schedule_interval") or "").strip()
                if interval:
                    self._register_schedule(interval, make_site_job(site))
            for task_cfg in generic_tasks:
                if not task_cfg.get("enabled", True):
                    continue
                interval = str(task_cfg.get("interval") or "").strip()
                if interval:
                    self._register_schedule(interval, make_generic_task_job(task_cfg))

        if not self._scheduler_loop_started:
            thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            thread.start()
            self._scheduler_loop_started = True

    def _scheduler_loop(self) -> None:
        logger.info("Native FastAPI scheduler loop started")
        while True:
            with self._scheduler_lock:
                self.scheduler.run_pending()
            time.sleep(60)

    def _register_schedule(self, interval_str: str, job_func: Callable[[], None]) -> None:
        interval = str(interval_str or "").strip().lower()
        try:
            if interval == "daily":
                self.scheduler.every().day.at("00:30").do(job_func)
            elif interval == "weekly":
                self.scheduler.every().monday.at("00:30").do(job_func)
            elif interval.startswith("daily at "):
                self.scheduler.every().day.at(interval.replace("daily at ", "", 1).strip()).do(job_func)
            elif interval.startswith("every "):
                parts = interval.split()
                if len(parts) >= 3:
                    qty = int(parts[1])
                    unit = parts[2]
                    if "hour" in unit:
                        self.scheduler.every(qty).hours.do(job_func)
                    elif "minute" in unit:
                        self.scheduler.every(qty).minutes.do(job_func)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to parse schedule '%s': %s", interval_str, exc)

    def _execute_collection_task(self, task_id: str, collection_type: str, data: dict[str, Any]) -> None:
        self._update_task(task_id, status="running", current_activity=f"Starting {collection_type} task")
        append_task_log(task_id, "INFO", f"Starting background task (type={collection_type})")
        try:
            result = self._run_collection(task_id, collection_type, data)
            self._finalize_task_success(task_id, collection_type, result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task %s failed", task_id)
            self._finalize_task_error(task_id, str(exc))

    def _run_collection(self, task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        config = self._load_site_config()
        db_path = str((config.get("paths") or {}).get("db") or "data/index.db")
        download_dir = str((config.get("paths") or {}).get("download_dir") or "data/files")
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        if not os.path.isabs(download_dir):
            download_dir = os.path.abspath(download_dir)

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
                crawler = Crawler(
                    storage,
                    download_dir,
                    str((config.get("defaults") or {}).get("user_agent") or "AI-Actuarial/1.0"),
                    stop_check=lambda: self._stop_requested(task_id),
                )
                collector = URLCollector(storage, crawler)
                defaults = dict(config.get("defaults") or {})
                cfg = CollectionConfig(
                    name=str(data.get("name") or "URL Collection"),
                    source_type="url",
                    check_database=bool(data.get("check_database", True)),
                    keywords=self._coerce_list(data.get("keywords")) or list(defaults.get("keywords") or []),
                    file_exts=self._coerce_list(data.get("file_exts")) or list(defaults.get("file_exts") or []),
                    exclude_keywords=self._coerce_list(data.get("exclude_keywords")) or list(defaults.get("exclude_keywords") or []),
                    metadata={"urls": self._coerce_list(data.get("urls"))},
                )
                return collector.collect(cfg, progress_callback=self._progress_callback(task_id))

            if collection_type == "search":
                return self._run_search_task(task_id, storage, config, download_dir, data)

            if collection_type in {"scheduled", "adhoc", "quick_check"}:
                crawler = Crawler(
                    storage,
                    download_dir,
                    str((config.get("defaults") or {}).get("user_agent") or "AI-Actuarial/1.0"),
                    stop_check=lambda: self._stop_requested(task_id),
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
                return collector.collect(cfg, progress_callback=self._progress_callback(task_id))

            if collection_type == "catalog":
                category = str(data.get("category") or "").strip() or None
                catalog_cfg = ((config.get("ai_config") or {}).get("catalog") or {})
                if not isinstance(catalog_cfg, dict):
                    catalog_cfg = {}
                provider = str(data.get("provider") or catalog_cfg.get("provider") or "local").strip().lower() or "local"
                input_source = str(data.get("input_source") or "source").strip() or "source"
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
                try:
                    limit = max(0, int(data.get("scan_count") or data.get("limit") or 0))
                except (TypeError, ValueError):
                    limit = 0
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
                    "catalog_system_prompt": str(catalog_cfg.get("system_prompt") or "").strip() or None,
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
                    success=not int(stats.get("errors", 0)) and not bool(stats.get("stopped", False)),
                    items_found=int(stats.get("scanned", 0)),
                    items_downloaded=int(stats.get("processed", 0)),
                    items_skipped=int(stats.get("skipped_ai", 0)),
                    errors=[] if not int(stats.get("errors", 0)) else [f"Catalog errors: {stats.get('errors', 0)}"],
                    metadata={
                        "category": category,
                        "provider": provider,
                        "input_source": input_source,
                        "catalog_version": catalog_version,
                        "file_urls": file_urls,
                    },
                )

            if collection_type in {"rag_indexing", "kb_index_build"}:
                return self._run_rag_indexing(task_id, storage, data)

            if collection_type == "markdown_conversion":
                return self._run_markdown_conversion(task_id, storage, config, download_dir, data)

            if collection_type == "chunk_generation":
                return self._run_chunk_generation(task_id, storage, db_path, data)

            raise RuntimeError(f"Native runtime does not yet support collection type '{collection_type}'")
        finally:
            storage.close()

    def _run_rag_indexing(self, task_id: str, storage: Storage, data: dict[str, Any]) -> CollectionResult:
        kb_id = str(data.get("kb_id") or "").strip()
        if not kb_id:
            raise RuntimeError("kb_id is required for RAG indexing")

        manager = KnowledgeBaseManager(storage)
        kb = manager.get_kb(kb_id)
        if not kb:
            raise RuntimeError(f"Knowledge base '{kb_id}' not found")

        force_reindex = bool(data.get("force_reindex", False) or data.get("reindex_all", False))
        incremental = bool(data.get("incremental", True))
        file_urls = [
            str(file_url).strip()
            for file_url in list(data.get("file_urls") or [])
            if str(file_url).strip()
        ]
        if not file_urls:
            if force_reindex or not incremental:
                file_urls = [
                    str(row.get("file_url") or "").strip()
                    for row in manager.get_kb_files(kb_id)
                    if str(row.get("file_url") or "").strip()
                ]
            else:
                file_urls = manager.get_files_needing_index(kb_id)

        if not file_urls:
            return CollectionResult(
                success=True,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[],
                metadata={
                    "kb_id": kb_id,
                    "kb_name": kb.name,
                    "force_reindex": force_reindex,
                    "incremental": incremental,
                    "total_chunks": 0,
                },
            )

        progress_callback = self._progress_callback(task_id)

        def rag_progress(message: str, current: int, total: int) -> None:
            progress_callback(current, total, message)

        pipeline = IndexingPipeline(manager, progress_callback=rag_progress)
        stats = pipeline.index_files(kb_id, file_urls, force_reindex=force_reindex)
        errors: list[str] = []
        for item in list(stats.get("errors") or []):
            if isinstance(item, dict):
                file_url = str(item.get("file_url") or "").strip()
                message = str(item.get("error") or "Unknown indexing error").strip()
                errors.append(f"{file_url}: {message}" if file_url else message)
            else:
                errors.append(str(item))

        stopped = bool(stats.get("stopped", False))
        return CollectionResult(
            success=not errors and not stopped,
            items_found=int(stats.get("total_files") or len(file_urls)),
            items_downloaded=int(stats.get("indexed_files") or 0),
            items_skipped=int(stats.get("skipped_files") or 0),
            errors=errors,
            metadata={
                "kb_id": kb_id,
                "kb_name": kb.name,
                "force_reindex": force_reindex,
                "incremental": incremental,
                "total_chunks": int(stats.get("total_chunks") or 0),
                "error_files": int(stats.get("error_files") or 0),
                "stopped": stopped,
            },
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
        user_agent = str(defaults.get("user_agent") or "AI-Actuarial/1.0")
        use_defaults = bool(data.get("use_search_defaults", True))

        site_filter = str(data.get("site") or "").strip()
        search_query = self._query_with_site_filter(query, site_filter)
        max_results = self._positive_int(data.get("count"), self._positive_int(search_cfg.get("max_results"), 5))

        languages = self._coerce_list(data.get("search_lang"))
        if not languages and use_defaults:
            languages = self._coerce_list(search_cfg.get("languages"))
        if not languages:
            languages = ["en"]

        countries = self._coerce_list(data.get("search_country"))
        country = countries[0] if countries else (str(search_cfg.get("country") or "").strip() if use_defaults else "")
        country = country or None

        file_exts = self._coerce_list(data.get("file_exts"))
        if not file_exts and use_defaults:
            file_exts = self._coerce_list(defaults.get("file_exts"))

        keywords = self._coerce_list(data.get("keywords"))
        if not keywords and use_defaults:
            keywords = self._coerce_list(defaults.get("keywords"))

        exclude_keywords = self._coerce_list(data.get("search_exclude_keywords")) or self._coerce_list(data.get("exclude_keywords"))
        if use_defaults:
            exclude_keywords = self._dedupe_list(exclude_keywords + self._coerce_list(search_cfg.get("exclude_keywords")))

        credentials = get_search_runtime_credentials(storage=storage)
        engine = str(data.get("engine") or "auto").strip().lower() or "auto"
        if engine in {"all", "auto"}:
            selected_credentials = dict(credentials)
        else:
            if engine not in {"brave", "google", "serper", "tavily"}:
                raise RuntimeError(f"Unsupported search engine: {engine}")
            if not credentials.get(engine):
                raise RuntimeError(f"Search engine '{engine}' is not configured")
            selected_credentials = {key: value if key == engine else None for key, value in credentials.items()}

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
        unique_results = self._dedupe_search_results(results, site_filter=site_filter)

        crawler = Crawler(storage, download_dir, user_agent, stop_check=lambda: self._stop_requested(task_id))
        errors: list[str] = []
        items_found = 0
        items_downloaded = 0
        items_skipped = 0
        total = len(unique_results)
        progress(0, total, f"Scanning {total} search results")
        for index, result in enumerate(unique_results, start=1):
            if self._stop_requested(task_id):
                errors.append("Task stopped by user")
                break
            try:
                site_config = SiteConfig(
                    name=str(data.get("name") or "Search Result"),
                    url=result.url,
                    max_pages=1,
                    max_depth=1,
                    delay_seconds=float(search_cfg.get("delay_seconds") or defaults.get("delay_seconds") or 0.5),
                    keywords=keywords,
                    file_exts=file_exts,
                    exclude_keywords=exclude_keywords,
                    check_database=True,
                )
                new_items = crawler.scan_page_for_files(result.url, site_config, source_site=result.source)
                items_found += len(new_items)
                for item in new_items:
                    if item.get("local_path"):
                        items_downloaded += 1
                    else:
                        items_skipped += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Error scanning search result {result.url}: {exc}")
            progress(index, total, f"Scanned search result {index}/{total}")

        return CollectionResult(
            success=(not errors or items_found > 0),
            items_found=items_found,
            items_downloaded=items_downloaded,
            items_skipped=items_skipped,
            errors=errors,
            metadata={
                "source_type": "search",
                "engine": engine,
                "query": query,
                "search_results": total,
                "site_filter": site_filter,
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
        file_rows = self._markdown_candidate_files(storage, data)
        if not file_rows:
            return CollectionResult(
                success=True,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[],
                metadata={"source_type": "markdown_conversion"},
            )

        conversion_tool = str(data.get("conversion_tool") or "opendataloader").strip().lower()
        ocr_runtime = resolve_ocr_runtime(storage=storage, yaml_config=config, engine_override=conversion_tool)
        if ocr_runtime.provider != "local" and not ocr_runtime.api_key:
            raise RuntimeError(f"OCR provider '{ocr_runtime.provider}' is not configured")

        overwrite_existing = bool(data.get("overwrite_existing", False))
        skip_existing = bool(data.get("skip_existing", True)) and not overwrite_existing
        progress = self._progress_callback(task_id)
        errors: list[str] = []
        converted = 0
        skipped = 0
        total = len(file_rows)
        progress(0, total, "Starting markdown conversion")

        for index, row in enumerate(file_rows, start=1):
            file_url = str(row.get("url") or "").strip()
            if self._stop_requested(task_id):
                errors.append("Task stopped by user")
                break
            if skip_existing and str(row.get("markdown_content") or "").strip():
                skipped += 1
                progress(index, total, f"Skipped existing markdown {index}/{total}")
                continue
            local_path = self._resolve_file_path(row.get("local_path"), download_dir)
            if not local_path.exists():
                errors.append(f"{file_url}: local file not found ({row.get('local_path')})")
                progress(index, total, f"Missing file {index}/{total}")
                continue
            try:
                output = _convert_document_path(
                    local_path,
                    engine=ocr_runtime.engine,  # type: ignore[arg-type]
                    model=ocr_runtime.model,
                    api_key=ocr_runtime.api_key,
                    base_url=ocr_runtime.base_url,
                )
                ok, reason = storage.update_file_markdown(
                    file_url,
                    output.markdown,
                    markdown_source=f"{output.engine}:{output.model}".strip(":"),
                )
                if ok:
                    converted += 1
                else:
                    errors.append(f"{file_url}: {reason or 'markdown update failed'}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{file_url}: {exc}")
            progress(index, total, f"Converted markdown {index}/{total}")

        return CollectionResult(
            success=(not errors or converted > 0),
            items_found=total,
            items_downloaded=converted,
            items_skipped=skipped,
            errors=errors,
            metadata={
                "source_type": "markdown_conversion",
                "conversion_tool": conversion_tool,
                "resolved_engine": ocr_runtime.engine,
                "provider": ocr_runtime.provider,
            },
        )

    def _run_chunk_generation(
        self,
        task_id: str,
        storage: Storage,
        db_path: str,
        data: dict[str, Any],
    ) -> CollectionResult:
        file_urls = self._chunk_candidate_file_urls(storage, data)
        if not file_urls:
            return CollectionResult(
                success=True,
                items_found=0,
                items_downloaded=0,
                items_skipped=0,
                errors=[],
                metadata={"source_type": "chunk_generation"},
            )

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
            "overwrite_same_profile": bool(data.get("overwrite_same_profile", False)),
        }

        progress = self._progress_callback(task_id)
        errors: list[str] = []
        generated = 0
        skipped = 0
        total_chunks = 0
        total = len(file_urls)
        progress(0, total, "Starting chunk generation")
        for index, file_url in enumerate(file_urls, start=1):
            if self._stop_requested(task_id):
                errors.append("Task stopped by user")
                break
            try:
                result = generate_file_chunk_sets(db_path=db_path, file_url=file_url, payload=payload)
                if result.get("reused_existing") and not result.get("overwrote_existing"):
                    skipped += 1
                else:
                    generated += 1
                total_chunks += int(result.get("chunk_count") or 0)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{file_url}: {exc}")
            progress(index, total, f"Generated chunks {index}/{total}")

        return CollectionResult(
            success=(not errors or generated > 0),
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
            },
        )

    def _collect_file_paths(self, data: dict[str, Any]) -> list[str]:
        directory = Path(str(data.get("directory_path") or "")).resolve()
        recursive = bool(data.get("recursive", False))
        raw_exts = list(data.get("extensions") or [])
        allowed_exts = {str(ext).lower().lstrip('.') for ext in raw_exts if str(ext).strip()}
        pattern_iter = directory.rglob("*") if recursive else directory.glob("*")
        paths: list[str] = []
        for path in pattern_iter:
            if not path.is_file():
                continue
            if allowed_exts and path.suffix.lower().lstrip('.') not in allowed_exts:
                continue
            paths.append(str(path))
        return paths

    def _site_configs_for_run(self, config: dict[str, Any], data: dict[str, Any]) -> list[SiteConfig]:
        defaults = dict(config.get("defaults") or {})
        sites = list(config.get("sites") or [])
        selected_site = str(data.get("site") or "").strip()
        site_rows = [row for row in sites if not selected_site or str(row.get("name") or "") == selected_site]
        default_exclude_keywords = self._coerce_list(defaults.get("exclude_keywords"))
        default_exclude_prefixes = self._coerce_list(defaults.get("exclude_prefixes"))
        return [
            SiteConfig(
                name=str(row.get("name") or "Unnamed Site"),
                url=str(row.get("url") or ""),
                max_pages=self._positive_int(data.get("max_pages"), self._positive_int(row.get("max_pages"), self._positive_int(defaults.get("max_pages"), 200))),
                max_depth=self._positive_int(data.get("max_depth"), self._positive_int(row.get("max_depth"), self._positive_int(defaults.get("max_depth"), 2))),
                delay_seconds=float(row.get("delay_seconds") or defaults.get("delay_seconds") or 0.5),
                keywords=list(row.get("keywords") or defaults.get("keywords") or []),
                file_exts=list(row.get("file_exts") or defaults.get("file_exts") or []),
                exclude_keywords=self._dedupe_list(default_exclude_keywords + self._coerce_list(row.get("exclude_keywords"))),
                exclude_prefixes=self._dedupe_list(default_exclude_prefixes + self._coerce_list(row.get("exclude_prefixes"))),
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
            max_pages=self._positive_int(data.get("max_pages"), self._positive_int(defaults.get("max_pages"), 10)),
            max_depth=self._positive_int(data.get("max_depth"), self._positive_int(defaults.get("max_depth"), 1)),
            delay_seconds=float(data.get("delay_seconds") or defaults.get("delay_seconds") or 0.5),
            keywords=self._coerce_list(data.get("keywords")) or self._coerce_list(defaults.get("keywords")),
            file_exts=self._coerce_list(data.get("file_exts")) or self._coerce_list(defaults.get("file_exts")),
            exclude_keywords=self._dedupe_list(
                self._coerce_list(data.get("exclude_keywords"))
                + self._coerce_list(defaults.get("exclude_keywords"))
                + self._coerce_list(search_cfg.get("exclude_keywords"))
            ),
            exclude_prefixes=self._coerce_list(defaults.get("exclude_prefixes")),
            check_database=bool(data.get("check_database", True)),
        )

    def _markdown_candidate_files(self, storage: Storage, data: dict[str, Any]) -> list[dict[str, Any]]:
        explicit_urls = self._explicit_file_urls(data)
        overwrite_existing = bool(data.get("overwrite_existing", False))
        skip_existing = bool(data.get("skip_existing", True)) and not overwrite_existing
        conn = storage._conn
        if explicit_urls:
            placeholders = ",".join("?" for _ in explicit_urls)
            rows = conn.execute(
                f"""
                SELECT f.url, f.local_path, f.original_filename, f.content_type, c.markdown_content
                FROM files f
                LEFT JOIN catalog_items c ON c.file_url = f.url
                WHERE f.url IN ({placeholders})
                  AND f.deleted_at IS NULL
                """,
                tuple(explicit_urls),
            ).fetchall()
            by_url = {
                str(row[0]): {
                    "url": row[0],
                    "local_path": row[1],
                    "original_filename": row[2],
                    "content_type": row[3],
                    "markdown_content": row[4],
                }
                for row in rows
            }
            return [by_url[url] for url in explicit_urls if url in by_url]

        category_sql, params = self._category_sql(str(data.get("category") or "").strip(), alias="c")
        where = _CONVERTIBLE_MARKDOWN_PREDICATE + category_sql
        if skip_existing:
            where += " AND (c.markdown_content IS NULL OR c.markdown_content = '')"
        limit = self._positive_int(data.get("scan_count"), 50)
        offset = max(0, self._positive_int(data.get("scan_start_index"), 1) - 1)
        rows = conn.execute(
            f"""
            SELECT f.url, f.local_path, f.original_filename, f.content_type, c.markdown_content
            FROM files f
            LEFT JOIN catalog_items c ON c.file_url = f.url
            WHERE {where}
            ORDER BY f.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
        return [
            {
                "url": row[0],
                "local_path": row[1],
                "original_filename": row[2],
                "content_type": row[3],
                "markdown_content": row[4],
            }
            for row in rows
        ]

    def _chunk_candidate_file_urls(self, storage: Storage, data: dict[str, Any]) -> list[str]:
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

        category_sql, params = self._category_sql(str(data.get("category") or "").strip(), alias="c")
        where = """
            f.deleted_at IS NULL
            AND c.markdown_content IS NOT NULL
            AND c.markdown_content != ''
        """ + category_sql
        if not bool(data.get("overwrite_same_profile", False)):
            where += " AND NOT EXISTS (SELECT 1 FROM file_chunk_sets s WHERE s.file_url = f.url)"
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
        site = str(site_filter or "").strip().lower().removeprefix("site:")
        for result in results:
            url = str(getattr(result, "url", "") or "").strip()
            if not url or url in seen:
                continue
            if site:
                host = urlparse(url).netloc.lower()
                if site not in host and not host.endswith(site.lstrip(".")):
                    continue
            seen.add(url)
            out.append(result)
        return out

    def _coerce_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.replace("\r\n", "\n").replace(",", "\n").split("\n") if part.strip()]
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

    def _finalize_task_success(self, task_id: str, collection_type: str, result: CollectionResult) -> None:
        with self.task_lock:
            task_data = self.active_tasks.pop(task_id, None)
        if task_data is None:
            return
        task_data.update(
            {
                "status": "completed" if result.success else "error",
                "progress": 100,
                "completed_at": datetime.now().isoformat(),
                "current_activity": "Completed" if result.success else "Completed with errors",
                "items_processed": result.items_found,
                "items_total": result.items_found,
                "items_downloaded": result.items_downloaded,
                "items_skipped": result.items_skipped,
                "errors": list(result.errors or []),
                "metadata": dict(result.metadata or {}),
            }
        )
        append_task_log(task_id, "INFO", f"Task finished (type={collection_type}, success={result.success})")
        self.task_history.append(task_data)
        self._append_history_to_disk(task_data)

    def _finalize_task_error(self, task_id: str, error: str) -> None:
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
        append_task_log(task_id, "ERROR", f"Task failed: {error}")
        self.task_history.append(task_data)
        self._append_history_to_disk(task_data)

    def _append_history_to_disk(self, task_data: dict[str, Any]) -> None:
        path = Path("data/job_history.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(task_data, ensure_ascii=False) + "\n")

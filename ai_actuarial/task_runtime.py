from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import schedule

from ai_actuarial.catalog_incremental import run_incremental_catalog
from ai_actuarial.collectors.base import CollectionConfig, CollectionResult
from ai_actuarial.collectors.file import FileCollector
from ai_actuarial.collectors.scheduled import ScheduledCollector
from ai_actuarial.collectors.url import URLCollector
from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.shared_runtime import append_task_log, get_sites_config_path, load_yaml, task_log_path
from ai_actuarial.storage import Storage

logger = logging.getLogger(__name__)


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
        self.scheduler = schedule.Scheduler()
        self._scheduler_lock = threading.RLock()
        self._scheduler_loop_started = False
        self._site_config_override: dict[str, Any] | None = None

    def _load_history_from_disk(self) -> list[dict[str, Any]]:
        path = Path("data/job_history.jsonl")
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            return rows[-100:] if len(rows) > 100 else rows
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
                crawler = Crawler(storage, download_dir, str((config.get("defaults") or {}).get("user_agent") or "AI-Actuarial/1.0"))
                collector = URLCollector(storage, crawler)
                cfg = CollectionConfig(
                    name=str(data.get("name") or "URL Collection"),
                    source_type="url",
                    check_database=True,
                    keywords=list((config.get("defaults") or {}).get("keywords") or []),
                    file_exts=list((config.get("defaults") or {}).get("file_exts") or []),
                    metadata={"urls": list(data.get("urls") or [])},
                )
                return collector.collect(cfg, progress_callback=self._progress_callback(task_id))

            if collection_type in {"scheduled", "adhoc", "quick_check"}:
                crawler = Crawler(storage, download_dir, str((config.get("defaults") or {}).get("user_agent") or "AI-Actuarial/1.0"))
                collector = ScheduledCollector(storage, crawler)
                cfg = CollectionConfig(
                    name=str(data.get("name") or f"{collection_type.capitalize()} Run"),
                    source_type=collection_type,
                    check_database=True,
                    metadata={"site_configs": self._site_configs_for_run(config, data)},
                )
                return collector.collect(cfg, progress_callback=self._progress_callback(task_id))

            if collection_type == "catalog":
                category = str(data.get("category") or "").strip() or None
                provider = str(data.get("provider") or "").strip() or None
                input_source = str(data.get("input_source") or "source").strip() or "source"
                version = None
                if provider:
                    version = f"v1:{provider}:{input_source}"
                stats = run_incremental_catalog(
                    db_path=db_path,
                    out_jsonl=Path((config.get("paths") or {}).get("updates_dir") or "data/updates") / "catalog_runtime.jsonl",
                    out_md=Path((config.get("paths") or {}).get("updates_dir") or "data/updates") / "catalog_runtime.md",
                    batch=int(data.get("batch") or 50),
                    site_filter=str(data.get("site") or "").strip() or None,
                    ai_only=False,
                    catalog_version=version,
                    max_chars=int(data.get("max_chars") or 12000),
                    retry_errors=bool(data.get("retry_errors", False)),
                )
                return CollectionResult(
                    success=True,
                    items_found=int(stats.get("scanned", 0)),
                    items_downloaded=int(stats.get("processed", 0)),
                    items_skipped=int(stats.get("skipped_ai", 0)),
                    errors=[] if not int(stats.get("errors", 0)) else [f"Catalog errors: {stats.get('errors', 0)}"],
                    metadata={"category": category},
                )

            raise RuntimeError(f"Native runtime does not yet support collection type '{collection_type}'")
        finally:
            storage.close()

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
        return [
            SiteConfig(
                name=str(row.get("name") or "Unnamed Site"),
                url=str(row.get("url") or ""),
                max_pages=int(row.get("max_pages") or defaults.get("max_pages") or 200),
                max_depth=int(row.get("max_depth") or defaults.get("max_depth") or 2),
                delay_seconds=float(row.get("delay_seconds") or defaults.get("delay_seconds") or 0.5),
                keywords=list(row.get("keywords") or defaults.get("keywords") or []),
                file_exts=list(row.get("file_exts") or defaults.get("file_exts") or []),
                exclude_keywords=list(row.get("exclude_keywords") or defaults.get("exclude_keywords") or []),
                exclude_prefixes=list(row.get("exclude_prefixes") or defaults.get("exclude_prefixes") or []),
                content_selector=str(row.get("content_selector") or "").strip() or None,
                queries=list(row.get("queries") or []),
            )
            for row in site_rows
            if str(row.get("url") or "").strip()
        ]

    def _progress_callback(self, task_id: str) -> Callable[[int, int, str], None]:
        def callback(current: int, total: int, message: str) -> None:
            progress = 0
            if total > 0:
                progress = min(100, max(0, int((current / total) * 100)))
            self._update_task(
                task_id,
                progress=progress,
                items_processed=current,
                items_total=total,
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

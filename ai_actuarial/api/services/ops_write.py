from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ai_actuarial.shared_runtime import (
    append_task_log,
    get_default_catalog_provider,
    get_sites_config_path,
    load_yaml,
    serialize_backend_settings,
)
from ai_actuarial.storage import Storage

_VALID_SCHEDULED_TASK_TYPES = [
    "scheduled",
    "quick_check",
    "url",
    "file",
    "search",
    "catalog",
    "markdown_conversion",
    "chunk_generation",
    "rag_indexing",
    "kb_index_build",
]

_VALID_INTERVALS = ["daily", "weekly"]

_VALID_COLLECTION_TYPES = {
    "scheduled",
    "adhoc",
    "url",
    "file",
    "search",
    "catalog",
    "quick_check",
    "markdown_conversion",
    "chunk_generation",
    "rag_indexing",
    "kb_index_build",
}

_SAMPLE_SITES_YAML = """# AI Actuarial Info Search - Site Configuration Sample
# Import this file to add sites for document crawling.
# Each site requires at minimum: name and url.

sites:
  - name: Society of Actuaries (SOA)
    url: https://www.soa.org/
    max_pages: 200
    max_depth: 3
    keywords:
      - artificial intelligence
      - machine learning
      - actuarial
    exclude_keywords:
      - newsletter
      - curriculum
    exclude_prefixes:
      - /about/
    content_selector: main
    schedule_interval: weekly

  - name: Institute and Faculty of Actuaries (IFoA)
    url: https://www.actuaries.org.uk/
    max_pages: 150
    max_depth: 2
    keywords:
      - AI
      - data science
      - risk management
    exclude_keywords:
      - events
    # schedule_interval is optional; omit to use the global schedule

# Field Reference:
# name (required)          - Unique display name for this site
# url (required)           - Root URL to start crawling from
# max_pages (optional)     - Maximum pages to crawl (default: from global config)
# max_depth (optional)     - Maximum link depth (default: from global config)
# keywords (optional)      - List of keywords to filter relevant pages
# exclude_keywords (opt.)  - List of keywords to exclude pages
# exclude_prefixes (opt.)  - URL path prefixes to skip
# content_selector (opt.)  - CSS selector for main content area
# schedule_interval (opt.) - Per-site schedule: daily, weekly, every N hours
"""


class OpsWriteError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BridgeState:
    def __init__(self, app_state: Any) -> None:
        self.active_tasks_ref = getattr(app_state, "active_tasks_ref", {}) or {}
        self.task_history_ref = getattr(app_state, "task_history_ref", []) or []
        self.task_lock = getattr(app_state, "task_lock", None)
        self.schedule_ref = getattr(app_state, "schedule_ref", None)
        self.start_background_task = (
            getattr(app_state, "legacy_start_background_task", None)
            or getattr(app_state, "start_background_task", None)
        )
        self.init_scheduler = (
            getattr(app_state, "legacy_init_scheduler", None)
            or getattr(app_state, "init_scheduler", None)
        )
        self.set_site_config = (
            getattr(app_state, "legacy_set_site_config", None)
            or getattr(app_state, "set_site_config", None)
        )


def _load_config_data() -> dict[str, Any]:
    return load_yaml(get_sites_config_path(), default={})


def _write_config_data(config_data: dict[str, Any]) -> None:
    config_path = get_sites_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)


def _notify_site_config_updated(bridge: BridgeState | None, config_data: dict[str, Any]) -> None:
    if bridge is None:
        return
    setter = bridge.set_site_config
    if callable(setter):
        setter(config_data)


def _split_csv_or_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _normalize_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("\r\n", "\n").replace(",", "\n").split("\n")
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise OpsWriteError(f"{field_name} must be a list or string")


def _coerce_bool_setting(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    raise OpsWriteError(f"Invalid value for {field_name}; expected boolean (true/false).")


def _coerce_required_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OpsWriteError("Invalid JSON body")
    return dict(payload)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _backups_dir() -> Path:
    return Path(get_sites_config_path()).resolve().parent / "backups"


def _ensure_backup_dir() -> Path:
    path = _backups_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _should_auto_backup() -> bool:
    backups_dir = _ensure_backup_dir()
    backups = sorted(backups_dir.glob("sites_*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return True
    return (time.time() - backups[0].stat().st_mtime) > 300


def _backup_config(label: str = "") -> str:
    backups_dir = _ensure_backup_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    backup_name = f"sites_{ts}{suffix}.yaml"
    backup_path = backups_dir / backup_name
    config_path = Path(get_sites_config_path())
    if config_path.exists():
        backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_name


def _validate_backup_filename(filename: str) -> Path:
    name = str(filename or "").strip()
    if not name or ".." in name or "/" in name or (os.sep != "/" and os.sep in name):
        raise OpsWriteError("Invalid filename")
    backups_dir = _ensure_backup_dir().resolve()
    candidate = (backups_dir / name).resolve()
    try:
        common = os.path.commonpath([str(backups_dir), str(candidate)])
    except ValueError as exc:
        raise OpsWriteError("Invalid filename") from exc
    if common != str(backups_dir):
        raise OpsWriteError("Invalid filename")
    return candidate


def add_site(data: dict[str, Any], *, bridge: BridgeState | None = None) -> dict[str, Any]:
    if not data.get("name") or not data.get("url"):
        raise OpsWriteError("Name and URL are required")
    config_data = _load_config_data()
    sites = list(config_data.get("sites") or [])
    if any(str(site.get("name") or "") == str(data["name"]) for site in sites):
        raise OpsWriteError("Site name already exists")

    new_site: dict[str, Any] = {
        "name": str(data["name"]).strip(),
        "url": str(data["url"]).strip(),
    }
    max_pages = _coerce_optional_int(data.get("max_pages"))
    max_depth = _coerce_optional_int(data.get("max_depth"))
    if max_pages is not None:
        new_site["max_pages"] = max_pages
    if max_depth is not None:
        new_site["max_depth"] = max_depth
    keywords = _split_csv_or_list(data.get("keywords"))
    exclude_keywords = _split_csv_or_list(data.get("exclude_keywords"))
    exclude_prefixes = _split_csv_or_list(data.get("exclude_prefixes"))
    if keywords:
        new_site["keywords"] = keywords
    if exclude_keywords:
        new_site["exclude_keywords"] = exclude_keywords
    if exclude_prefixes:
        new_site["exclude_prefixes"] = exclude_prefixes
    if data.get("schedule_interval"):
        new_site["schedule_interval"] = str(data["schedule_interval"]).strip()
    if data.get("content_selector"):
        new_site["content_selector"] = str(data["content_selector"]).strip()

    if _should_auto_backup():
        _backup_config("before_sites_add")
    sites.append(new_site)
    config_data["sites"] = sites
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def update_site(data: dict[str, Any], *, bridge: BridgeState | None = None) -> dict[str, Any]:
    original_name = str(data.get("original_name") or "").strip()
    new_name = str(data.get("name") or "").strip()
    if not original_name or not new_name:
        raise OpsWriteError("Original name and new name are required")

    config_data = _load_config_data()
    sites = list(config_data.get("sites") or [])
    if original_name != new_name and any(str(site.get("name") or "") == new_name for site in sites):
        raise OpsWriteError("Site name already exists")

    found = False
    for site in sites:
        if str(site.get("name") or "") != original_name:
            continue
        site["name"] = new_name
        site["url"] = str(data.get("url") or "").strip()
        max_pages = _coerce_optional_int(data.get("max_pages"))
        max_depth = _coerce_optional_int(data.get("max_depth"))
        if max_pages is not None:
            site["max_pages"] = max_pages
        else:
            site.pop("max_pages", None)
        if max_depth is not None:
            site["max_depth"] = max_depth
        else:
            site.pop("max_depth", None)
        keywords = _split_csv_or_list(data.get("keywords"))
        exclude_keywords = _split_csv_or_list(data.get("exclude_keywords"))
        exclude_prefixes = _split_csv_or_list(data.get("exclude_prefixes"))
        if keywords:
            site["keywords"] = keywords
        else:
            site.pop("keywords", None)
        if exclude_keywords:
            site["exclude_keywords"] = exclude_keywords
        else:
            site.pop("exclude_keywords", None)
        if exclude_prefixes:
            site["exclude_prefixes"] = exclude_prefixes
        else:
            site.pop("exclude_prefixes", None)
        schedule_interval = str(data.get("schedule_interval") or "").strip()
        if schedule_interval:
            site["schedule_interval"] = schedule_interval
        else:
            site.pop("schedule_interval", None)
        content_selector = str(data.get("content_selector") or "").strip()
        if content_selector:
            site["content_selector"] = content_selector
        else:
            site.pop("content_selector", None)
        found = True
        break

    if not found:
        raise OpsWriteError("Site not found", status_code=404)

    if _should_auto_backup():
        _backup_config("before_sites_update")
    config_data["sites"] = sites
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def delete_site(name: str, *, bridge: BridgeState | None = None) -> dict[str, Any]:
    site_name = str(name or "").strip()
    if not site_name:
        raise OpsWriteError("Site name is required")

    config_data = _load_config_data()
    sites = list(config_data.get("sites") or [])
    filtered = [site for site in sites if str(site.get("name") or "") != site_name]
    if len(filtered) == len(sites):
        raise OpsWriteError("Site not found", status_code=404)

    if _should_auto_backup():
        _backup_config("before_sites_delete")
    config_data["sites"] = filtered
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def import_sites(data: dict[str, Any], *, bridge: BridgeState | None = None) -> dict[str, Any]:
    incoming_sites = data.get("sites")
    yaml_text = data.get("yaml_text")
    mode = str(data.get("mode", "merge")).strip().lower()
    preview_only = bool(data.get("preview"))

    if yaml_text and not incoming_sites:
        try:
            parsed = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as exc:
            raise OpsWriteError(f"Invalid YAML: {exc}") from exc
        if isinstance(parsed, dict):
            incoming_sites = parsed.get("sites", [])
        elif isinstance(parsed, list):
            incoming_sites = parsed
        else:
            raise OpsWriteError("YAML must contain a 'sites' list or be a list of sites")

    if not incoming_sites or not isinstance(incoming_sites, list):
        raise OpsWriteError("sites array is required (provide 'sites' or 'yaml_text')")

    if preview_only:
        valid = [site for site in incoming_sites if isinstance(site, dict) and site.get("name") and site.get("url")]
        return {"success": True, "count": len(valid), "names": [str(site.get("name") or "") for site in valid]}

    _backup_config("before_import")
    config_data = _load_config_data()
    config_data.setdefault("sites", [])

    imported = 0
    skipped = 0
    skipped_names: list[str] = []
    errors: list[str] = []

    if mode == "overwrite":
        valid_sites = []
        for site in incoming_sites:
            if not isinstance(site, dict) or not site.get("name") or not site.get("url"):
                errors.append(f"Invalid site entry: {site}")
                continue
            valid_sites.append(site)
        config_data["sites"] = valid_sites
        imported = len(valid_sites)
    else:
        existing_names = {str(site.get("name") or "") for site in config_data["sites"]}
        for site in incoming_sites:
            if not isinstance(site, dict) or not site.get("name") or not site.get("url"):
                errors.append(f"Invalid site entry: {site}")
                continue
            site_name = str(site["name"])
            if site_name in existing_names:
                skipped += 1
                skipped_names.append(site_name)
                continue
            config_data["sites"].append(site)
            existing_names.add(site_name)
            imported += 1

    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    result: dict[str, Any] = {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "skipped_names": skipped_names,
    }
    if errors:
        result["errors"] = errors
    return result


def export_sites_yaml() -> tuple[str, str]:
    config_data = _load_config_data()
    sites_only = {"sites": config_data.get("sites", [])}
    content = yaml.dump(sites_only, sort_keys=False, allow_unicode=True, default_flow_style=False)
    filename = f"sites_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
    return content, filename


def sample_sites_yaml() -> tuple[str, str]:
    return _SAMPLE_SITES_YAML, "sites_sample.yaml"


def list_backups() -> dict[str, list[dict[str, Any]]]:
    backups_dir = _ensure_backup_dir()
    backups = []
    for path in sorted(backups_dir.glob("sites_*.yaml"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        backups.append(
            {
                "filename": path.name,
                "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_bytes": stat.st_size,
                "size": stat.st_size,
            }
        )
    return {"backups": backups}


def restore_backup(filename: str, *, bridge: BridgeState | None = None) -> dict[str, Any]:
    backup_path = _validate_backup_filename(filename)
    if not backup_path.exists():
        raise OpsWriteError("Backup file not found", status_code=404)

    _backup_config("before_restore")
    backup_data = yaml.safe_load(backup_path.read_text(encoding="utf-8")) or {}
    config_data = _load_config_data()
    if "sites" in backup_data:
        config_data["sites"] = backup_data["sites"]
    if "scheduled_tasks" in backup_data:
        config_data["scheduled_tasks"] = backup_data["scheduled_tasks"]
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def delete_backup(filename: str) -> dict[str, Any]:
    target = _validate_backup_filename(filename)
    if not target.exists():
        raise OpsWriteError("Backup not found", status_code=404)
    target.unlink()
    return {"success": True}


def update_backend_settings(data: dict[str, Any], *, bridge: BridgeState | None = None) -> dict[str, Any]:
    payload = _coerce_required_dict(data)
    config_data = _load_config_data()
    config_data.setdefault("defaults", {})
    config_data.setdefault("paths", {})
    config_data.setdefault("search", {})

    defaults_in = payload.get("defaults")
    if isinstance(defaults_in, dict):
        defaults = config_data["defaults"]
        if "max_pages" in defaults_in:
            defaults["max_pages"] = int(defaults_in.get("max_pages") or 0)
        if "max_depth" in defaults_in:
            defaults["max_depth"] = int(defaults_in.get("max_depth") or 0)
        if "delay_seconds" in defaults_in:
            defaults["delay_seconds"] = float(defaults_in.get("delay_seconds") or 0)
        if "file_exts" in defaults_in:
            defaults["file_exts"] = _normalize_list(defaults_in.get("file_exts"), field_name="defaults.file_exts")
        if "keywords" in defaults_in:
            defaults["keywords"] = _normalize_list(defaults_in.get("keywords"), field_name="defaults.keywords")
        if "exclude_keywords" in defaults_in:
            defaults["exclude_keywords"] = _normalize_list(
                defaults_in.get("exclude_keywords"), field_name="defaults.exclude_keywords"
            )
        if "exclude_prefixes" in defaults_in:
            defaults["exclude_prefixes"] = _normalize_list(
                defaults_in.get("exclude_prefixes"), field_name="defaults.exclude_prefixes"
            )
        if "schedule_interval" in defaults_in:
            defaults["schedule_interval"] = str(defaults_in.get("schedule_interval", "")).strip()

    paths_in = payload.get("paths")
    if isinstance(paths_in, dict):
        paths = config_data["paths"]
        for key in ["download_dir", "updates_dir", "last_run_new"]:
            if key in paths_in:
                paths[key] = str(paths_in.get(key, "")).strip()

    search_in = payload.get("search")
    if isinstance(search_in, dict):
        search = config_data["search"]
        if "enabled" in search_in:
            search["enabled"] = bool(search_in.get("enabled"))
        if "max_results" in search_in:
            search["max_results"] = int(search_in.get("max_results") or 0)
        if "delay_seconds" in search_in:
            search["delay_seconds"] = float(search_in.get("delay_seconds") or 0)
        if "languages" in search_in:
            search["languages"] = _normalize_list(search_in.get("languages"), field_name="search.languages")
        if "country" in search_in:
            search["country"] = str(search_in.get("country", "")).strip()
        if "exclude_keywords" in search_in:
            search["exclude_keywords"] = _normalize_list(
                search_in.get("exclude_keywords"), field_name="search.exclude_keywords"
            )
        if "queries" in search_in:
            search["queries"] = _normalize_list(search_in.get("queries"), field_name="search.queries")

    system_in = payload.get("system")
    if isinstance(system_in, dict):
        config_data.setdefault("system", {})
        system_cfg = config_data["system"]
        if "file_deletion_enabled" in system_in:
            system_cfg["file_deletion_enabled"] = _coerce_bool_setting(
                system_in.get("file_deletion_enabled"), field_name="system.file_deletion_enabled"
            )

    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True, **serialize_backend_settings(config_data)}


def add_scheduled_task(data: dict[str, Any], *, bridge: BridgeState | None = None) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    task_type = str(data.get("type") or "").strip()
    interval = str(data.get("interval") or "").strip()
    if not name:
        raise OpsWriteError("Task name is required")
    if task_type not in _VALID_SCHEDULED_TASK_TYPES:
        raise OpsWriteError(f"Invalid task type: {task_type}")
    if not interval:
        raise OpsWriteError("Schedule interval is required")
    if interval not in _VALID_INTERVALS:
        raise OpsWriteError(f"Invalid schedule interval: {interval}. Valid values: {', '.join(_VALID_INTERVALS)}")

    config_data = _load_config_data()
    tasks = list(config_data.get("scheduled_tasks") or [])
    if any(str(task.get("name") or "") == name for task in tasks):
        raise OpsWriteError("Task name already exists")
    tasks.append(
        {
            "name": name,
            "type": task_type,
            "interval": interval,
            "enabled": bool(data.get("enabled", True)),
            "params": data.get("params") or {},
        }
    )
    config_data["scheduled_tasks"] = tasks
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def update_scheduled_task(data: dict[str, Any], *, bridge: BridgeState | None = None) -> dict[str, Any]:
    original_name = str(data.get("original_name") or "").strip()
    name = str(data.get("name") or "").strip()
    if not original_name or not name:
        raise OpsWriteError("original_name and name are required")

    config_data = _load_config_data()
    tasks = list(config_data.get("scheduled_tasks") or [])
    found = False
    for task in tasks:
        if str(task.get("name") or "") != original_name:
            continue
        task["name"] = name
        if "type" in data:
            new_type = str(data.get("type") or "").strip()
            if new_type not in _VALID_SCHEDULED_TASK_TYPES:
                raise OpsWriteError(f"Invalid task type: {new_type}")
            task["type"] = new_type
        if "interval" in data:
            new_interval = str(data.get("interval") or "").strip()
            if new_interval not in _VALID_INTERVALS:
                raise OpsWriteError(f"Invalid schedule interval: {new_interval}. Valid values: {', '.join(_VALID_INTERVALS)}")
            task["interval"] = new_interval
        if "enabled" in data:
            task["enabled"] = bool(data.get("enabled"))
        if "params" in data:
            task["params"] = data.get("params") or {}
        found = True
        break
    if not found:
        raise OpsWriteError("Task not found", status_code=404)

    config_data["scheduled_tasks"] = tasks
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def delete_scheduled_task(name: str, *, bridge: BridgeState | None = None) -> dict[str, Any]:
    task_name = str(name or "").strip()
    if not task_name:
        raise OpsWriteError("Task name is required")
    config_data = _load_config_data()
    tasks = list(config_data.get("scheduled_tasks") or [])
    filtered = [task for task in tasks if str(task.get("name") or "") != task_name]
    if len(filtered) == len(tasks):
        raise OpsWriteError("Task not found", status_code=404)
    config_data["scheduled_tasks"] = filtered
    _write_config_data(config_data)
    _notify_site_config_updated(bridge, config_data)
    return {"success": True}


def reinitialize_scheduler(bridge: BridgeState) -> dict[str, Any]:
    if not callable(bridge.init_scheduler):
        raise OpsWriteError("Scheduler bridge is unavailable", status_code=503)
    bridge.init_scheduler()
    job_count = len(list(getattr(bridge.schedule_ref, "jobs", []) or []))
    return {"success": True, "job_count": job_count}


def request_task_stop(task_id: str, *, bridge: BridgeState) -> dict[str, Any]:
    if bridge.task_lock is None:
        active_tasks = bridge.active_tasks_ref
        if task_id not in active_tasks:
            raise OpsWriteError("Task not found or not active", status_code=404)
        active_tasks[task_id]["stop_requested"] = True
        active_tasks[task_id]["current_activity"] = "Stop requested"
        return {"success": True, "message": "Stop signal sent"}

    with bridge.task_lock:
        if task_id not in bridge.active_tasks_ref:
            raise OpsWriteError("Task not found or not active", status_code=404)
        bridge.active_tasks_ref[task_id]["stop_requested"] = True
        bridge.active_tasks_ref[task_id]["current_activity"] = "Stop requested"
    return {"success": True, "message": "Stop signal sent"}


def _append_history_to_disk(task_data: dict[str, Any]) -> None:
    path = Path("data/job_history.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(task_data, ensure_ascii=False) + "\n")


def _record_rejected_task(reason: str, *, collection_type: str, data: dict[str, Any], bridge: BridgeState) -> None:
    task_id = f"rejected_{int(datetime.now().timestamp())}"
    task_name = str(data.get("name") or f"{collection_type} (rejected)")
    stamp = datetime.now().isoformat()
    log_file = str(Path("data/task_logs") / f"{task_id}.log")
    append_task_log(task_id, "ERROR", f"Rejected request: {reason}")
    task_data = {
        "id": task_id,
        "name": task_name,
        "type": collection_type,
        "status": "error",
        "progress": 100,
        "started_at": stamp,
        "completed_at": stamp,
        "current_activity": "Rejected",
        "items_processed": 0,
        "items_total": 0,
        "log_file": log_file,
        "errors": [reason],
    }
    if bridge.task_lock is None:
        bridge.task_history_ref.append(task_data)
    else:
        with bridge.task_lock:
            bridge.task_history_ref.append(task_data)
    _append_history_to_disk(task_data)


def _reject_request(reason: str, *, collection_type: str, data: dict[str, Any], bridge: BridgeState) -> None:
    _record_rejected_task(reason, collection_type=collection_type, data=data, bridge=bridge)
    raise OpsWriteError(reason)


def start_collection(data: dict[str, Any], *, bridge: BridgeState) -> dict[str, Any]:
    collection_type = str(data.get("type") or "").strip()
    if not collection_type or collection_type not in _VALID_COLLECTION_TYPES:
        _reject_request("Invalid collection type", collection_type=collection_type or "unknown", data=data, bridge=bridge)

    if collection_type == "url" and not data.get("urls"):
        _reject_request("No URLs provided", collection_type=collection_type, data=data, bridge=bridge)
    if collection_type == "file":
        directory_path = str(data.get("directory_path") or "").strip()
        normalized_directory_path = os.path.abspath(directory_path) if directory_path else ""
        if not normalized_directory_path or not os.path.isdir(normalized_directory_path):
            _reject_request("Invalid directory path", collection_type=collection_type, data=data, bridge=bridge)
        data["directory_path"] = normalized_directory_path
    if collection_type == "catalog":
        scope_mode = str(data.get("scope_mode") or "index").strip().lower()
        if scope_mode == "category" and not str(data.get("category") or "").strip():
            _reject_request("Category is required for category-scoped cataloging", collection_type=collection_type, data=data, bridge=bridge)
    if collection_type == "markdown_conversion":
        scope_mode = str(data.get("scope_mode") or "index").strip().lower()
        if scope_mode == "category" and not str(data.get("category") or "").strip():
            _reject_request("Category is required for category-scoped markdown conversion", collection_type=collection_type, data=data, bridge=bridge)
        has_urls = bool(data.get("file_urls"))
        has_scan = data.get("scan_count") not in (None, "", "null")
        if not has_urls and not has_scan:
            _reject_request("No files selected for markdown conversion", collection_type=collection_type, data=data, bridge=bridge)
    if collection_type == "chunk_generation":
        scope_mode = str(data.get("scope_mode") or "index").strip().lower()
        if scope_mode == "category" and not str(data.get("category") or "").strip():
            _reject_request("Category is required for category-scoped chunk generation", collection_type=collection_type, data=data, bridge=bridge)
        has_urls = bool(data.get("file_urls"))
        has_scan = data.get("scan_count") not in (None, "", "null")
        if not has_urls and not has_scan:
            _reject_request("No files selected for chunk generation", collection_type=collection_type, data=data, bridge=bridge)
    if collection_type in {"rag_indexing", "kb_index_build"} and not str(data.get("kb_id") or "").strip():
        _reject_request(f"kb_id is required for {collection_type}", collection_type=collection_type, data=data, bridge=bridge)

    if not callable(bridge.start_background_task):
        raise OpsWriteError("Task bridge is unavailable", status_code=503)

    task_name = str(data.get("name") or f"{collection_type.capitalize()} Collection")
    task_id = bridge.start_background_task(collection_type, data, task_name=task_name)
    return {"success": True, "message": "Task started in background", "job_id": task_id}


def browse_folder(path: str | None = None) -> dict[str, Any]:
    site_config = _load_config_data()
    data_root = str((site_config.get("paths") or {}).get("download_dir", "data/files"))
    if not os.path.isabs(data_root):
        data_root = os.path.abspath(data_root)
    allowed_root = os.path.abspath(os.path.dirname(data_root) or os.getcwd())

    target = str(path or "").strip() or allowed_root
    target = os.path.abspath(target)
    try:
        target_within_root = os.path.commonpath([allowed_root, target]) == allowed_root
    except ValueError:
        target_within_root = False
    if not target_within_root:
        raise OpsWriteError("Access denied: path outside allowed directory", status_code=403)
    if not os.path.isdir(target):
        raise OpsWriteError("Not a valid directory")

    entries = []
    try:
        for entry in sorted(os.scandir(target), key=lambda item: item.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                entries.append({"name": entry.name, "type": "dir"})
            elif entry.is_file(follow_symlinks=False):
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                entries.append({"name": entry.name, "type": "file", "size": size})
    except PermissionError as exc:
        raise OpsWriteError("Permission denied", status_code=403) from exc

    parent = os.path.dirname(target)
    try:
        parent_within_root = os.path.commonpath([allowed_root, parent]) == allowed_root
    except ValueError:
        parent_within_root = False
    has_parent = parent != target and parent_within_root
    return {"path": target, "parent": parent if has_parent else None, "entries": entries}


def _category_sql(category_filter: str, *, alias: str = "c") -> tuple[str, list[Any]]:
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


def _catalog_candidate_predicate(*, file_alias: str = "f", catalog_alias: str = "c") -> str:
    conditions = [
        f"{catalog_alias}.file_url IS NULL",
        f"IFNULL(IFNULL({catalog_alias}.file_sha256, {catalog_alias}.sha256), '') = ''",
        f"IFNULL({catalog_alias}.file_sha256, {catalog_alias}.sha256) != {file_alias}.sha256",
        f"IFNULL(IFNULL({catalog_alias}.catalog_version, {catalog_alias}.pipeline_version), '') != ?",
        f"TRIM(IFNULL({catalog_alias}.summary, '')) = ''",
    ]
    return "(" + " OR ".join(conditions) + ")"


def get_catalog_stats(*, db_path: str, provider: str | None = None, input_source: str | None = None, category: str | None = None) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        conn = storage._conn
        total_local = conn.execute(
            """
            SELECT COUNT(*)
            FROM files f
            WHERE f.local_path IS NOT NULL AND f.local_path != ''
              AND f.deleted_at IS NULL
            """
        ).fetchone()[0]
        total_ok = conn.execute("SELECT COUNT(*) FROM catalog_items c WHERE c.status = 'ok'").fetchone()[0]

        from ai_actuarial.catalog import CATALOG_VERSION as base_catalog_version

        selected_provider = str(provider or get_default_catalog_provider()).strip().lower()
        selected_input_source = str(input_source or "source").strip().lower()
        category_filter = str(category or "").strip()
        catalog_version = f"{base_catalog_version}:{selected_provider}:{selected_input_source}"
        candidates_where = (
            "f.local_path IS NOT NULL AND f.local_path != '' AND f.deleted_at IS NULL AND "
            + _catalog_candidate_predicate(file_alias="f", catalog_alias="c")
        )
        candidate_params: list[Any] = [catalog_version]
        category_sql, category_params = _category_sql(category_filter, alias="c")
        candidates_where += category_sql
        candidate_params.extend(category_params)

        candidate_total = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM files f
            LEFT JOIN catalog_items c ON c.file_url = f.url
            WHERE {candidates_where}
            """,
            tuple(candidate_params),
        ).fetchone()[0]

        first_candidate_index = None
        try:
            first_candidate_params: list[Any] = []
            if category_filter:
                first_candidate_params.extend(category_params)
            first_candidate_params.append(catalog_version)
            row = conn.execute(
                f"""
                WITH ordered AS (
                    SELECT
                        ROW_NUMBER() OVER (ORDER BY f.id DESC) AS rn,
                        c.file_url AS c_url,
                        f.sha256 AS f_sha,
                        IFNULL(c.file_sha256, c.sha256) AS c_sha,
                        IFNULL(c.catalog_version, c.pipeline_version) AS c_ver,
                        c.summary AS c_summary
                    FROM files f
                    LEFT JOIN catalog_items c ON c.file_url = f.url
                    WHERE f.local_path IS NOT NULL AND f.local_path != ''
                      AND f.deleted_at IS NULL
                      {category_sql if category_filter else ''}
                )
                SELECT rn
                FROM ordered
                WHERE c_url IS NULL
                   OR IFNULL(c_sha,'') = ''
                   OR c_sha != f_sha
                   OR IFNULL(c_ver,'') != ?
                   OR TRIM(IFNULL(c_summary, '')) = ''
                ORDER BY rn
                LIMIT 1
                """,
                tuple(first_candidate_params),
            ).fetchone()
            if row:
                first_candidate_index = int(row[0])
        except Exception:
            first_candidate_index = None

        return {
            "success": True,
            "order": "id_desc",
            "total_local_files": int(total_local),
            "total_catalog_ok": int(total_ok),
            "candidate_total": int(candidate_total),
            "first_candidate_index": first_candidate_index,
            "catalog_version": catalog_version,
            "category": category_filter or "",
        }
    finally:
        storage.close()


def get_markdown_conversion_stats(*, db_path: str, category: str | None = None) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        conn = storage._conn
        category_filter = str(category or "").strip()
        where = """
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
        params: list[Any] = []
        category_sql, category_params = _category_sql(category_filter, alias="c")
        where += category_sql
        params.extend(category_params)

        total = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM files f
            LEFT JOIN catalog_items c ON c.file_url = f.url
            WHERE {where}
            """,
            tuple(params),
        ).fetchone()[0]
        with_markdown = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM files f
            LEFT JOIN catalog_items c ON c.file_url = f.url
            WHERE {where}
              AND c.markdown_content IS NOT NULL
              AND c.markdown_content != ''
            """,
            tuple(params),
        ).fetchone()[0]

        first_missing = None
        try:
            row = conn.execute(
                f"""
                WITH ordered AS (
                    SELECT ROW_NUMBER() OVER (ORDER BY f.id DESC) AS rn, c.markdown_content AS md
                    FROM files f
                    LEFT JOIN catalog_items c ON c.file_url = f.url
                    WHERE {where}
                )
                SELECT rn
                FROM ordered
                WHERE md IS NULL OR md = ''
                ORDER BY rn
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
            if row:
                first_missing = int(row[0])
        except Exception:
            first_missing = None

        return {
            "success": True,
            "order": "id_desc",
            "category": category_filter or "",
            "total_convertible": int(total),
            "total_with_markdown": int(with_markdown),
            "first_without_markdown_index": first_missing,
        }
    finally:
        storage.close()


def get_chunk_generation_stats(*, db_path: str, category: str | None = None) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        conn = storage._conn
        category_filter = str(category or "").strip()
        where = """
            f.deleted_at IS NULL
            AND c.markdown_content IS NOT NULL
            AND c.markdown_content != ''
        """
        params: list[Any] = []
        category_sql, category_params = _category_sql(category_filter, alias="c")
        where += category_sql
        params.extend(category_params)

        total_with_markdown = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM files f
            JOIN catalog_items c ON c.file_url = f.url
            WHERE {where}
            """,
            tuple(params),
        ).fetchone()[0]
        total_with_chunks = conn.execute(
            f"""
            SELECT COUNT(DISTINCT f.url)
            FROM files f
            JOIN catalog_items c ON c.file_url = f.url
            WHERE {where}
              AND EXISTS (SELECT 1 FROM file_chunk_sets s WHERE s.file_url = f.url)
            """,
            tuple(params),
        ).fetchone()[0]

        first_without_chunks = None
        try:
            row = conn.execute(
                f"""
                WITH ordered AS (
                    SELECT ROW_NUMBER() OVER (ORDER BY f.id DESC) AS rn, f.url AS file_url
                    FROM files f
                    JOIN catalog_items c ON c.file_url = f.url
                    WHERE {where}
                )
                SELECT rn
                FROM ordered o
                WHERE NOT EXISTS (SELECT 1 FROM file_chunk_sets s WHERE s.file_url = o.file_url)
                ORDER BY rn
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
            if row:
                first_without_chunks = int(row[0])
        except Exception:
            first_without_chunks = None

        return {
            "success": True,
            "order": "id_desc",
            "category": category_filter or "",
            "total_with_markdown": int(total_with_markdown),
            "total_with_chunks": int(total_with_chunks),
            "first_without_chunks_index": first_without_chunks,
        }
    finally:
        storage.close()

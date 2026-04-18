from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import ai_actuarial.llm_models as llm_models
from ai_actuarial.ai_runtime import (
    KNOWN_LLM_PROVIDERS,
    PROVIDER_BASE_URL_ENV_VARS,
    PROVIDER_ENV_VARS,
)
from ai_actuarial.config import settings
from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.shared_runtime import (
    get_categories_config_path,
    get_sites_config_path,
    load_yaml,
    parse_int_clamped,
    serialize_backend_settings,
    tail_text_file,
    task_log_path,
)
from ai_actuarial.storage import Storage

_SEARCH_ENGINE_DISPLAY = {
    "brave": "Brave Search",
    "google": "Google (SerpAPI)",
    "serper": "Google (Serper.dev)",
    "tavily": "Tavily",
}


def get_config_categories() -> dict[str, object]:
    config_data = load_yaml(
        get_categories_config_path(),
        default={"categories": {}, "ai_filter_keywords": [], "ai_keywords": []},
    )
    categories = config_data.get("categories") or {}
    if not isinstance(categories, dict):
        categories = {}
    ai_filter_keywords = config_data.get("ai_filter_keywords") or []
    ai_keywords = config_data.get("ai_keywords") or []
    return {
        "categories": categories,
        "ai_filter_keywords": ai_filter_keywords if isinstance(ai_filter_keywords, list) else [],
        "ai_keywords": ai_keywords if isinstance(ai_keywords, list) else [],
    }


def get_backend_settings() -> dict[str, Any]:
    config_data = load_yaml(get_sites_config_path(), default={})
    settings = serialize_backend_settings(config_data)
    runtime = settings.get("runtime")
    if isinstance(runtime, dict):
        if "config_path" in runtime:
            runtime["config_path_set"] = bool(runtime.pop("config_path", None))
        if "categories_config_path" in runtime:
            runtime["categories_config_path_set"] = bool(runtime.pop("categories_config_path", None))
    return settings


def get_global_logs() -> dict[str, str]:
    if not settings.ENABLE_GLOBAL_LOGS_API:
        return {"error": "Forbidden"}

    log_file = Path("data") / "app.log"
    if not log_file.exists():
        return {"logs": "No logs found."}

    lines = tail_text_file(log_file, max_lines=500).splitlines(keepends=True)
    lines.reverse()
    return {"logs": "".join(lines)}


def get_search_engines() -> dict[str, list[dict[str, object]]]:
    engines = []
    for engine_id, display_name in _SEARCH_ENGINE_DISPLAY.items():
        engines.append(
            {
                "id": engine_id,
                "name": display_name,
                "configured": settings.is_search_engine_configured(engine_id),
            }
        )
    return {"engines": engines}


def get_config_sites() -> dict[str, object]:
    config_path = get_sites_config_path()
    current_config = load_yaml(config_path, default={})
    sites = []
    site_defaults = current_config.get("defaults", {})
    for site in current_config.get("sites", []):
        sites.append(
            {
                "name": site["name"],
                "url": site["url"],
                "max_pages": site.get("max_pages", site_defaults.get("max_pages")),
                "max_depth": site.get("max_depth", site_defaults.get("max_depth")),
                "keywords": site.get("keywords", site_defaults.get("keywords", [])),
                "exclude_keywords": site.get("exclude_keywords", []),
                "exclude_prefixes": site.get("exclude_prefixes", []),
                "schedule_interval": site.get("schedule_interval"),
                "content_selector": site.get("content_selector", ""),
            }
        )
    global_schedule = site_defaults.get("schedule_interval")
    return {"sites": sites, "global_schedule": global_schedule}


def get_schedule_status(schedule_ref: Any) -> dict[str, object]:
    jobs = []
    for job in list(getattr(schedule_ref, "jobs", []) or []):
        next_run = job.next_run.isoformat() if getattr(job, "next_run", None) else None
        last_run = job.last_run.isoformat() if getattr(job, "last_run", None) else None
        unit = getattr(job, "unit", None) or ""
        interval = getattr(job, "interval", None)
        at_time = getattr(job, "at_time", None)
        at_str = at_time.strftime("%H:%M") if at_time else None
        if unit == "days" and interval == 1 and at_str:
            label = f"daily at {at_str}"
        elif unit == "weeks" and interval == 1 and at_str:
            label = f"weekly on {getattr(job, 'start_day', 'monday')} at {at_str}"
        elif interval and unit:
            label = f"every {interval} {unit}"
            if at_str:
                label += f" at {at_str}"
        else:
            label = str(job)
        jobs.append({"label": label, "next_run": next_run, "last_run": last_run})
    return {"jobs": jobs, "count": len(jobs)}


def get_scheduled_tasks() -> dict[str, list[dict[str, Any]]]:
    config_path = get_sites_config_path()
    config_data = load_yaml(config_path, default={})
    tasks = config_data.get("scheduled_tasks") or []
    return {"tasks": tasks if isinstance(tasks, list) else []}


def _task_error_count(task_data: dict[str, Any]) -> int:
    errors = task_data.get("errors")
    if isinstance(errors, list):
        return len(errors)
    count = task_data.get("error_count")
    try:
        return int(count or 0)
    except Exception:
        return 0


def _task_metric(label_key: str, label_fallback: str, value: Any) -> dict[str, Any]:
    return {"label_key": label_key, "label_fallback": label_fallback, "value": value}


def _build_task_display_summary(task_data: dict[str, Any]) -> dict[str, Any]:
    task_type = str(task_data.get("type") or "")
    items_processed = int(task_data.get("items_processed") or 0)
    items_downloaded = int(task_data.get("items_downloaded") or 0)
    items_skipped = int(task_data.get("items_skipped") or 0)
    error_count = _task_error_count(task_data)

    if task_type == "catalog":
        primary = _task_metric("tasks.metric_cataloged", "Cataloged", task_data.get("catalog_ok", items_processed))
        secondary = [
            _task_metric("tasks.metric_errors", "Errors", error_count),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
        ]
    elif task_type in {"markdown", "markdown_conversion"}:
        primary = _task_metric("tasks.metric_converted", "Converted", items_downloaded or items_processed)
        secondary = [
            _task_metric("tasks.metric_errors", "Errors", error_count),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
        ]
    elif task_type in {"chunk", "chunk_generation"}:
        primary = _task_metric("tasks.metric_chunked", "Chunked", items_downloaded or items_processed)
        secondary = [
            _task_metric("tasks.metric_errors", "Errors", error_count),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
        ]
    elif task_type in {"search", "url", "file", "scheduled", "adhoc", "quick_check"}:
        primary = _task_metric("tasks.metric_found", "Found", items_processed)
        secondary = [
            _task_metric("tasks.metric_downloaded", "Downloaded", items_downloaded),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
            _task_metric("tasks.metric_errors", "Errors", error_count),
        ]
    else:
        primary = _task_metric("tasks.metric_processed", "Processed", items_processed)
        secondary = [
            _task_metric("tasks.metric_completed", "Completed", items_downloaded),
            _task_metric("tasks.metric_skipped", "Skipped", items_skipped),
            _task_metric("tasks.metric_errors", "Errors", error_count),
        ]
    return {"primary": primary, "secondary": secondary, "error_count": error_count}


def _serialize_task_for_api(task_data: dict[str, Any]) -> dict[str, Any]:
    row = dict(task_data)
    row["error_count"] = _task_error_count(row)
    row["display_summary"] = _build_task_display_summary(row)
    return row


def list_active_tasks(active_tasks_ref: dict[str, dict[str, Any]], task_lock: Any) -> dict[str, list[dict[str, Any]]]:
    if task_lock is None:
        tasks = [_serialize_task_for_api(task) for task in active_tasks_ref.values()]
    else:
        with task_lock:
            tasks = [_serialize_task_for_api(task) for task in active_tasks_ref.values()]
    return {"tasks": tasks}


def list_task_history(task_history_ref: list[dict[str, Any]], limit: int) -> dict[str, list[dict[str, Any]]]:
    tasks = [
        _serialize_task_for_api(task)
        for task in sorted(task_history_ref, key=lambda x: x.get("started_at", ""), reverse=True)[:limit]
    ]
    return {"tasks": tasks}


def get_task_log(task_id: str, tail: int) -> dict[str, Any]:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", task_id or "")
    if not safe_id:
        raise ValueError("Invalid task id")
    path = task_log_path(safe_id)
    content = tail_text_file(path, max_lines=tail)
    if not content:
        return {"success": True, "log": "", "log_file": str(path)}
    return {"success": True, "log": content, "log_file": str(path)}


def get_llm_providers(*, db_path: str) -> dict[str, object]:
    storage = Storage(db_path)
    try:
        db_providers = storage.list_llm_providers()
        db_provider_keys = {p["provider"] for p in db_providers}
        result = []
        encryption = TokenEncryption()
        for p in db_providers:
            pinfo = KNOWN_LLM_PROVIDERS.get(p["provider"], {})
            try:
                encryption.decrypt(p["api_key_encrypted"])
                decrypt_ok = True
            except Exception:
                decrypt_ok = False
            result.append(
                {
                    "provider": p["provider"],
                    "display_name": pinfo.get("display_name", p["provider"]),
                    "api_base_url": p["api_base_url"],
                    "api_key_masked": "****",
                    "status": p["status"],
                    "source": "db",
                    "decrypt_ok": decrypt_ok,
                    "created_at": p["created_at"],
                    "updated_at": p["updated_at"],
                }
            )

        for provider, env_var in PROVIDER_ENV_VARS.items():
            if provider in db_provider_keys:
                continue
            api_key = os.getenv(env_var)
            if api_key:
                pinfo = KNOWN_LLM_PROVIDERS.get(provider, {})
                base_url_var = PROVIDER_BASE_URL_ENV_VARS.get(provider)
                base_url = os.getenv(base_url_var) if base_url_var else None
                result.append(
                    {
                        "provider": provider,
                        "display_name": pinfo.get("display_name", provider),
                        "api_base_url": base_url or None,
                        "api_key_masked": "****",
                        "status": "active",
                        "source": "env",
                        "created_at": None,
                        "updated_at": None,
                    }
                )
        return {"providers": result, "known": KNOWN_LLM_PROVIDERS}
    finally:
        storage.close()


def get_ai_models() -> dict[str, object]:
    config_data = load_yaml(get_sites_config_path(), default={})
    ai_config = config_data.get("ai_config") or {}
    chatbot_cfg = ai_config.get("chatbot", {})
    chatbot_prompts = chatbot_cfg.get("prompts", {})
    current_config = {
        "catalog": {
            "provider": ai_config.get("catalog", {}).get("provider", "openai"),
            "model": ai_config.get("catalog", {}).get("model", "gpt-4o-mini"),
            "system_prompt": ai_config.get("catalog", {}).get("system_prompt", ""),
        },
        "embeddings": {
            "provider": ai_config.get("embeddings", {}).get("provider", "openai"),
            "model": ai_config.get("embeddings", {}).get("model", "text-embedding-3-large"),
        },
        "chatbot": {
            "provider": chatbot_cfg.get("provider", "openai"),
            "model": chatbot_cfg.get("model", "gpt-4-turbo"),
            "prompts": {
                "base": chatbot_prompts.get("base", ""),
                "expert": chatbot_prompts.get("expert", ""),
                "summary": chatbot_prompts.get("summary", ""),
                "tutorial": chatbot_prompts.get("tutorial", ""),
                "comparison": chatbot_prompts.get("comparison", ""),
            },
            "summarization_prompt": chatbot_cfg.get("summarization_prompt", ""),
        },
        "ocr": {
            "provider": ai_config.get("ocr", {}).get("provider", "local"),
            "model": ai_config.get("ocr", {}).get("model", "docling"),
        },
    }
    return {"current": current_config, "available": llm_models.get_available_models()}


def parse_task_history_limit(raw_value: str | None) -> int:
    return parse_int_clamped(raw_value or 10, default=10, min_value=1, max_value=200)


def parse_task_log_tail(raw_value: str | None) -> int:
    return parse_int_clamped(raw_value or 400, default=400, min_value=1, max_value=5000)

"""Markdown conversion configuration loading and normalization.

The markdown conversion surface is intentionally separate from ``ai_config``:
AI routing chooses model providers, while this module owns document-conversion
engine ordering, format routing, API/paid auto-run switches, and engine tuning
knobs.  Missing config is compatible and falls back to conservative local-only
auto chains.
"""

from __future__ import annotations

import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

ENGINE_PROVIDERS: dict[str, str] = {
    "auto": "auto",
    "opendataloader": "local",
    "markitdown": "local",
    "docling": "local",
    "marker": "local",
    "local": "local",
    "mistral": "mistral",
    "deepseekocr": "siliconflow",
    "mathpix": "mathpix",
}

PAID_OR_API_ENGINES = {"mistral", "deepseekocr", "mathpix"}
LOCAL_ENGINES = {engine for engine, provider in ENGINE_PROVIDERS.items() if provider == "local"}
HARD_MAX_SCAN_COUNT = 10000

DEFAULT_MARKDOWN_CONVERSION_CONFIG: dict[str, Any] = {
    "version": 1,
    "default_tool": "auto",
    "tools": {
        "auto": {
            "display_name": "Auto (configured chain)",
            "provider": "auto",
            "enabled": True,
            "auto_enabled": True,
            "paid_or_api": False,
        },
        "opendataloader": {
            "display_name": "OpenDataLoader",
            "provider": "local",
            "enabled": True,
            "auto_enabled": True,
            "paid_or_api": False,
            "tuning": {
                "hybrid": None,
                "use_struct_tree": False,
            },
        },
        "markitdown": {
            "display_name": "MarkItDown",
            "provider": "local",
            "enabled": True,
            "auto_enabled": True,
            "paid_or_api": False,
            "tuning": {
                "enable_plugins": True,
                "enable_builtins": True,
            },
        },
        "docling": {
            "display_name": "Docling",
            "provider": "local",
            "enabled": True,
            "auto_enabled": True,
            "paid_or_api": False,
            "tuning": {
                "max_pages": None,
                "raise_on_error": True,
            },
        },
        "marker": {
            "display_name": "Marker",
            "provider": "local",
            "enabled": True,
            "auto_enabled": False,
            "paid_or_api": False,
            "tuning": {
                "use_llm": False,
                "processors": None,
                "page_range": None,
                "extract_images": False,
                "llm_service": None,
            },
        },
        "local": {
            "display_name": "Local (Basic)",
            "provider": "local",
            "enabled": True,
            "auto_enabled": True,
            "paid_or_api": False,
            "tuning": {},
        },
        "mistral": {
            "display_name": "Mistral OCR",
            "provider": "mistral",
            "enabled": True,
            "auto_enabled": False,
            "paid_or_api": True,
            "model": "mistral-ocr-latest",
            "tuning": {
                "max_pdf_tokens": 9000,
                "max_pages_per_chunk": 10,
                "timeout_seconds": 60,
                "retry_attempts": 3,
                "extract_header": True,
                "extract_footer": True,
            },
        },
        "deepseekocr": {
            "display_name": "DeepSeek OCR",
            "provider": "siliconflow",
            "enabled": True,
            "auto_enabled": False,
            "paid_or_api": True,
            "model": "deepseek-ai/DeepSeek-OCR",
            "tuning": {
                "max_input_tokens": 3500,
                "chunk_overlap_tokens": 200,
                "timeout_seconds": 60,
                "retry_attempts": 3,
            },
        },
        "mathpix": {
            "display_name": "Mathpix",
            "provider": "mathpix",
            "enabled": True,
            "auto_enabled": False,
            "paid_or_api": True,
            "model": "mathpix",
            "tuning": {
                "timeout_seconds": 120,
                "retry_attempts": 3,
                "poll_interval_seconds": 5,
                "output_format": "md",
                "base_url": "https://api.mathpix.com/v3",
            },
        },
    },
    "formats": {
        "pdf": {
            "extensions": [".pdf"],
            "candidate_chain": ["opendataloader", "markitdown", "docling", "local"],
        },
        "office": {
            "extensions": [".docx", ".pptx"],
            "candidate_chain": ["markitdown", "docling", "local"],
        },
        "image": {
            "extensions": [".png", ".jpg", ".jpeg", ".webp", ".bmp"],
            "candidate_chain": ["local"],
        },
        "default": {
            "extensions": [],
            "candidate_chain": ["markitdown", "docling", "local"],
        },
    },
    "limits": {
        "default_scan_count": 50,
        "max_scan_count": 2000,
    },
}


def get_markdown_conversion_config_path() -> str:
    return os.getenv("MARKDOWN_CONVERSION_CONFIG_PATH", "config/markdown_conversion.yaml")


def markdown_conversion_config_file_exists(path: str | None = None) -> bool:
    return Path(path or get_markdown_conversion_config_path()).exists()


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _read_yaml(path: str) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    if value is None:
        return default
    return bool(value)


def _normalize_tools(config: dict[str, Any]) -> None:
    raw_tools = config.get("tools") if isinstance(config.get("tools"), dict) else {}
    tools: dict[str, dict[str, Any]] = {}
    for name, default_tool in DEFAULT_MARKDOWN_CONVERSION_CONFIG["tools"].items():
        raw_tool = raw_tools.get(name) if isinstance(raw_tools.get(name), dict) else {}
        tool = _deep_merge(default_tool, raw_tool)
        engine = str(name).strip().lower()
        provider = str(tool.get("provider") or ENGINE_PROVIDERS.get(engine) or "local").strip().lower()
        tool["name"] = engine
        tool["provider"] = provider
        tool["enabled"] = _bool(tool.get("enabled"), True)
        tool["paid_or_api"] = _bool(tool.get("paid_or_api"), engine in PAID_OR_API_ENGINES)
        # Conservative default: paid/API tools never join auto mode unless explicitly enabled.
        tool["auto_enabled"] = _bool(tool.get("auto_enabled"), False if tool["paid_or_api"] else bool(tool["enabled"]))
        tool["display_name"] = str(tool.get("display_name") or engine).strip() or engine
        if not isinstance(tool.get("tuning"), dict):
            tool["tuning"] = {}
        tools[engine] = tool

    # Preserve any future custom engines from config, but normalize safe defaults.
    for raw_name, raw_tool in raw_tools.items():
        engine = str(raw_name or "").strip().lower()
        if not engine or engine in tools or not isinstance(raw_tool, dict):
            continue
        provider = str(raw_tool.get("provider") or ENGINE_PROVIDERS.get(engine) or "local").strip().lower()
        paid_or_api = _bool(raw_tool.get("paid_or_api"), provider != "local")
        tools[engine] = {
            **deepcopy(raw_tool),
            "name": engine,
            "provider": provider,
            "display_name": str(raw_tool.get("display_name") or engine).strip() or engine,
            "enabled": _bool(raw_tool.get("enabled"), True),
            "paid_or_api": paid_or_api,
            "auto_enabled": _bool(raw_tool.get("auto_enabled"), False if paid_or_api else True),
            "tuning": raw_tool.get("tuning") if isinstance(raw_tool.get("tuning"), dict) else {},
        }
    config["tools"] = tools


def _normalize_formats(config: dict[str, Any]) -> None:
    tools = config["tools"]
    raw_formats = config.get("formats") if isinstance(config.get("formats"), dict) else {}
    formats: dict[str, dict[str, Any]] = {}
    for fmt, default_fmt in DEFAULT_MARKDOWN_CONVERSION_CONFIG["formats"].items():
        raw_fmt = raw_formats.get(fmt) if isinstance(raw_formats.get(fmt), dict) else {}
        entry = _deep_merge(default_fmt, raw_fmt)
        extensions = entry.get("extensions") if isinstance(entry.get("extensions"), list) else []
        chain = entry.get("candidate_chain") if isinstance(entry.get("candidate_chain"), list) else []
        entry["extensions"] = [str(ext).strip().lower() for ext in extensions if str(ext).strip()]
        entry["candidate_chain"] = [
            str(engine).strip().lower()
            for engine in chain
            if str(engine).strip().lower() in tools
            and tools[str(engine).strip().lower()].get("enabled", True)
        ]
        formats[fmt] = entry
    config["formats"] = formats


def normalize_markdown_conversion_config(raw_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = _deep_merge(DEFAULT_MARKDOWN_CONVERSION_CONFIG, raw_config or {})
    default_tool = str(config.get("default_tool") or "auto").strip().lower()
    config["default_tool"] = default_tool or "auto"
    _normalize_tools(config)
    tools_raw = config.get("tools")
    tools: dict[str, dict[str, Any]] = tools_raw if isinstance(tools_raw, dict) else {}
    if config["default_tool"] not in tools or not tools[config["default_tool"]].get("enabled", True):
        config["default_tool"] = "auto" if tools.get("auto", {}).get("enabled", True) else next(
            (name for name, tool in tools.items() if isinstance(tool, dict) and tool.get("enabled", True)),
            "auto",
        )
    _normalize_formats(config)
    raw_limits = config.get("limits")
    limits: dict[str, Any] = raw_limits if isinstance(raw_limits, dict) else {}
    try:
        limits["default_scan_count"] = min(HARD_MAX_SCAN_COUNT, max(1, int(limits.get("default_scan_count") or 50)))
    except Exception:
        limits["default_scan_count"] = 50
    try:
        limits["max_scan_count"] = min(
            HARD_MAX_SCAN_COUNT,
            max(limits["default_scan_count"], int(limits.get("max_scan_count") or 2000)),
        )
    except Exception:
        limits["max_scan_count"] = min(HARD_MAX_SCAN_COUNT, max(limits["default_scan_count"], 2000))
    config["limits"] = limits
    return config


def load_markdown_conversion_config(path: str | None = None) -> dict[str, Any]:
    return normalize_markdown_conversion_config(_read_yaml(path or get_markdown_conversion_config_path()))


def write_markdown_conversion_config(config: Mapping[str, Any], path: str | None = None) -> dict[str, Any]:
    normalized = normalize_markdown_conversion_config(config)
    target = Path(path or get_markdown_conversion_config_path())
    target.parent.mkdir(parents=True, exist_ok=True)

    backup = target.with_suffix(target.suffix + ".bak")
    if target.exists():
        backup.write_bytes(target.read_bytes())

    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(normalized, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return normalized


def format_key_for_path(path: str | Path, config: Mapping[str, Any] | None = None) -> str:
    cfg = normalize_markdown_conversion_config(config) if config is not None else load_markdown_conversion_config()
    suffix = Path(path).suffix.lower()
    for name, fmt in (cfg.get("formats") or {}).items():
        if name == "default":
            continue
        extensions = fmt.get("extensions") if isinstance(fmt, dict) else []
        if suffix in set(extensions or []):
            return str(name)
    return "default"


def candidate_chain_for_path(path: str | Path, config: Mapping[str, Any] | None = None, *, auto_only: bool = True) -> list[str]:
    cfg = normalize_markdown_conversion_config(config) if config is not None else load_markdown_conversion_config()
    fmt = (cfg.get("formats") or {}).get(format_key_for_path(path, cfg), {})
    tools = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
    chain = fmt.get("candidate_chain") if isinstance(fmt, dict) and isinstance(fmt.get("candidate_chain"), list) else []
    result: list[str] = []
    for raw_engine in chain:
        engine = str(raw_engine).strip().lower()
        tool = tools.get(engine) if isinstance(tools.get(engine), dict) else {}
        if not tool or not tool.get("enabled", True):
            continue
        if auto_only and not tool.get("auto_enabled", False):
            continue
        result.append(engine)
    return result


def list_conversion_tools(config: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = normalize_markdown_conversion_config(config) if config is not None else load_markdown_conversion_config()
    tools = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
    ordered: list[str] = []
    default_tool = str(cfg.get("default_tool") or "auto").strip().lower()
    if default_tool in tools:
        ordered.append(default_tool)
    for fmt in (cfg.get("formats") or {}).values():
        chain = fmt.get("candidate_chain") if isinstance(fmt, dict) else []
        for raw_engine in chain or []:
            engine = str(raw_engine).strip().lower()
            if engine in tools and engine not in ordered:
                ordered.append(engine)
    for engine in tools:
        if engine not in ordered:
            ordered.append(engine)
    return [
        {
            "name": engine,
            "provider": str(tools[engine].get("provider") or ENGINE_PROVIDERS.get(engine) or "local"),
            "displayName": str(tools[engine].get("display_name") or engine),
            "display_name": str(tools[engine].get("display_name") or engine),
            "enabled": bool(tools[engine].get("enabled", True)),
            "auto_enabled": bool(tools[engine].get("auto_enabled", False)),
            "paid_or_api": bool(tools[engine].get("paid_or_api", False)),
        }
        for engine in ordered
        if tools[engine].get("enabled", True)
    ]


def get_markdown_conversion_options() -> dict[str, Any]:
    cfg = load_markdown_conversion_config()
    return {
        "config": cfg,
        "tools": list_conversion_tools(cfg),
        "default_tool": cfg.get("default_tool", "auto"),
        "formats": cfg.get("formats", {}),
        "limits": cfg.get("limits", {}),
        "config_path_set": bool(os.getenv("MARKDOWN_CONVERSION_CONFIG_PATH")),
    }

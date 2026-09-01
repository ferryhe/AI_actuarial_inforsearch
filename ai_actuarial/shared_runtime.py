from __future__ import annotations

import os
import stat
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

import yaml

TRACKED_SITES_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "sites.yaml"
PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})


class SitesConfigError(RuntimeError):
    """Raised when the authoritative runtime configuration cannot be used safely."""


def _env_flag_override(*names: str) -> bool | None:
    for name in names:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            continue
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return None


def coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _coerce_bool(value: object, default: bool = False) -> bool:
    return coerce_bool(value, default)


def _feature_bool(
    features: dict[str, Any],
    key: str,
    *,
    default: bool,
    env_names: tuple[str, ...] = (),
    fallback_value: object = None,
    fallback_present: bool = False,
) -> tuple[bool, str]:
    env_value = _env_flag_override(*env_names)
    if env_value is not None:
        return env_value, "env"
    if key in features:
        return _coerce_bool(features.get(key), default), "yaml"
    if fallback_present:
        return _coerce_bool(fallback_value, default), "yaml"
    return default, "default"


def resolve_runtime_features(config_data: dict[str, Any]) -> dict[str, Any]:
    """Resolve non-secret runtime feature switches from sites.yaml with env overrides."""
    raw_features = config_data.get("features") or {}
    features = raw_features if isinstance(raw_features, dict) else {}
    raw_system = config_data.get("system") or {}
    system_cfg = raw_system if isinstance(raw_system, dict) else {}

    resolved: dict[str, Any] = {}
    sources: dict[str, str] = {}

    specs: dict[str, tuple[bool, tuple[str, ...]]] = {
        "require_auth": (False, ("REQUIRE_AUTH",)),
        "enable_global_logs_api": (False, ("ENABLE_GLOBAL_LOGS_API",)),
        "enable_rate_limiting": (False, ("ENABLE_RATE_LIMITING", "RATE_LIMIT_ENABLED")),
        "enable_csrf": (False, ("ENABLE_CSRF",)),
        "enable_security_headers": (True, ("ENABLE_SECURITY_HEADERS",)),
        "expose_error_details": (False, ("EXPOSE_ERROR_DETAILS",)),
    }

    for key, (default, env_names) in specs.items():
        value, source = _feature_bool(features, key, default=default, env_names=env_names)
        resolved[key] = value
        sources[key] = source

    file_deletion, file_deletion_source = _feature_bool(
        features,
        "enable_file_deletion",
        default=False,
        env_names=("ENABLE_FILE_DELETION",),
        fallback_value=system_cfg.get("file_deletion_enabled"),
        fallback_present="file_deletion_enabled" in system_cfg,
    )
    resolved["enable_file_deletion"] = file_deletion
    resolved["file_deletion_enabled"] = file_deletion
    sources["enable_file_deletion"] = file_deletion_source
    sources["file_deletion_enabled"] = file_deletion_source

    string_specs: dict[str, tuple[str, str]] = {
        "rate_limit_defaults": ("RATE_LIMIT_DEFAULTS", "200 per hour, 50 per minute"),
        "rate_limit_storage_uri": ("RATE_LIMIT_STORAGE_URI", "memory://"),
        "content_security_policy": ("CONTENT_SECURITY_POLICY", ""),
    }
    for key, (env_name, default) in string_specs.items():
        raw_env = os.getenv(env_name)
        if raw_env is not None and raw_env.strip() != "":
            resolved[key] = raw_env.strip()
            sources[key] = "env"
        elif key in features:
            resolved[key] = str(features.get(key) or "").strip()
            sources[key] = "yaml"
        else:
            resolved[key] = default
            sources[key] = "default"

    resolved["feature_sources"] = sources
    return resolved


def resolve_fastapi_env(config_data: dict[str, Any]) -> tuple[str, str]:
    """Resolve FastAPI environment from env override, then sites.yaml server config."""
    raw_env = os.getenv("FASTAPI_ENV")
    if raw_env is not None and raw_env.strip():
        return raw_env.strip().lower(), "env"

    raw_server = config_data.get("server") or {}
    server_cfg = raw_server if isinstance(raw_server, dict) else {}
    yaml_value = str(server_cfg.get("fastapi_env") or "").strip().lower()
    if yaml_value:
        return yaml_value, "yaml"

    return "", "default"


def parse_int_clamped(
    value: object,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except Exception:
        number = default
    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number


def get_sites_config_path() -> str:
    explicit = os.getenv("CONFIG_PATH", "").strip()
    return explicit or "config/sites.yaml"


def get_categories_config_path() -> str:
    return os.getenv("CATEGORIES_CONFIG_PATH", "config/categories.yaml")


def _is_production_environment() -> bool:
    return os.getenv("FASTAPI_ENV", "").strip().lower() in PRODUCTION_ENVIRONMENTS


def _paths_match(first: str | Path, second: str | Path) -> bool:
    try:
        return Path(first).expanduser().resolve() == Path(second).expanduser().resolve()
    except (OSError, RuntimeError):
        return os.path.abspath(os.fspath(first)) == os.path.abspath(os.fspath(second))


def _require_writable_config(path: Path) -> None:
    try:
        file_mode = stat.S_IMODE(path.stat().st_mode)
        parent_mode = stat.S_IMODE(path.parent.stat().st_mode)
    except OSError as exc:
        raise SitesConfigError(
            f"Cannot inspect runtime configuration permissions: {path}: {exc}"
        ) from exc
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if not file_mode & write_bits or not os.access(path, os.W_OK):
        raise SitesConfigError(f"Runtime configuration is not writable: {path}")
    if not parent_mode & write_bits or not os.access(path.parent, os.W_OK):
        raise SitesConfigError(
            f"Runtime configuration directory is not writable for atomic replacement: {path.parent}"
        )


def load_sites_config(
    path: str | Path | None = None,
    *,
    default: dict[str, Any] | None = None,
    require_writable: bool = False,
) -> dict[str, Any]:
    """Load the single authoritative sites config, failing closed outside development."""
    explicit = os.getenv("CONFIG_PATH", "").strip()
    production = _is_production_environment()
    if production and not explicit:
        raise SitesConfigError(
            "CONFIG_PATH is required in production and must point to runtime config outside the Git checkout"
        )

    config_path = Path(path or get_sites_config_path()).expanduser()
    if explicit and path is not None and not _paths_match(config_path, explicit):
        raise SitesConfigError(
            f"Requested sites config does not match authoritative CONFIG_PATH: {config_path}"
        )
    if production and _paths_match(config_path, TRACKED_SITES_CONFIG_PATH):
        raise SitesConfigError(
            "Production CONFIG_PATH must not point to the tracked config/sites.yaml template"
        )
    strict = bool(explicit) or production
    fallback = default.copy() if isinstance(default, dict) else {}
    if not config_path.exists():
        if strict:
            raise SitesConfigError(
                f"Authoritative runtime configuration does not exist: {config_path}"
            )
        return fallback
    if not config_path.is_file():
        raise SitesConfigError(f"Authoritative runtime configuration is not a file: {config_path}")
    try:
        file_mode = stat.S_IMODE(config_path.stat().st_mode)
    except OSError as exc:
        raise SitesConfigError(
            f"Cannot inspect runtime configuration permissions: {config_path}: {exc}"
        ) from exc
    read_bits = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    if not file_mode & read_bits or not os.access(config_path, os.R_OK):
        raise SitesConfigError(
            f"Authoritative runtime configuration is not readable: {config_path}"
        )

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        if strict:
            raise SitesConfigError(
                f"Authoritative runtime configuration is not a valid YAML mapping: {config_path}: {exc}"
            ) from exc
        return fallback
    if not isinstance(data, dict):
        if strict:
            raise SitesConfigError(
                f"Authoritative runtime configuration is not a valid YAML mapping: {config_path}"
            )
        return fallback

    server = data.get("server") or {}
    yaml_environment = (
        str(server.get("fastapi_env") or "").strip().lower() if isinstance(server, dict) else ""
    )
    if yaml_environment in PRODUCTION_ENVIRONMENTS and not explicit:
        raise SitesConfigError(
            "CONFIG_PATH is required when server.fastapi_env is production; "
            "the tracked config/sites.yaml is only a development/bootstrap template"
        )
    if require_writable or strict:
        _require_writable_config(config_path)
    return data


def atomic_write_yaml(
    path: str | Path,
    data: dict[str, Any],
    *,
    overwrite: bool = True,
) -> Path:
    """Durably write YAML in the target directory, then publish it atomically."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target_stat = target.stat() if overwrite and target.exists() else None
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
            if target_stat is not None:
                if hasattr(os, "fchown"):
                    os.fchown(handle.fileno(), target_stat.st_uid, target_stat.st_gid)
                if hasattr(os, "fchmod"):
                    os.fchmod(handle.fileno(), stat.S_IMODE(target_stat.st_mode))
                handle.flush()
                os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise FileExistsError(f"Runtime configuration already exists: {target}") from exc
            temporary.unlink()
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return target
    finally:
        if temporary.exists():
            temporary.unlink()


def bootstrap_sites_config(source: str | Path, target: str | Path | None = None) -> Path:
    """Create the external runtime config once from a valid tracked template."""
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Bootstrap source does not exist: {source_path}")
    try:
        with source_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SitesConfigError(f"Bootstrap source is not valid YAML: {source_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SitesConfigError(f"Bootstrap source is not a YAML mapping: {source_path}")
    target_path = Path(target or get_sites_config_path()).expanduser().resolve()
    if target_path.exists():
        raise FileExistsError(f"Runtime configuration already exists: {target_path}")
    return atomic_write_yaml(target_path, data, overwrite=False)


def load_yaml(path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if _paths_match(path, get_sites_config_path()):
        return load_sites_config(path, default=default)
    fallback = default.copy() if isinstance(default, dict) else {}
    if not path or not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else fallback


def get_default_catalog_provider() -> str:
    config = load_yaml(get_sites_config_path(), default={})
    ai_cfg = config.get("ai_config") or {}
    if not isinstance(ai_cfg, dict):
        ai_cfg = {}
    catalog_cfg = ai_cfg.get("catalog") or {}
    if not isinstance(catalog_cfg, dict):
        catalog_cfg = {}
    provider = (
        str(catalog_cfg.get("provider") or ai_cfg.get("catalog_provider") or "").strip().lower()
    )
    return provider or "openai"


def task_log_path(task_id: str) -> Path:
    return Path("data/task_logs") / f"{task_id}.log"


def append_task_log(task_id: str, level: str, message: str) -> None:
    path = task_log_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{level}] {message}\n")


def tail_text_file(path: Path, max_lines: int = 400) -> str:
    if max_lines <= 0 or not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = deque(handle, maxlen=max_lines)
    return "".join(lines)


def serialize_backend_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    defaults = config_data.get("defaults") or {}
    paths = config_data.get("paths") or {}
    search = config_data.get("search") or {}
    features = resolve_runtime_features(config_data)
    fastapi_env, fastapi_env_source = resolve_fastapi_env(config_data)
    return {
        "defaults": {
            "user_agent": defaults.get("user_agent", ""),
            "max_pages": defaults.get("max_pages", 200),
            "max_depth": defaults.get("max_depth", 2),
            "delay_seconds": defaults.get("delay_seconds", 0.5),
            "file_exts": defaults.get("file_exts", []),
            "keywords": defaults.get("keywords", []),
            "exclude_keywords": defaults.get("exclude_keywords", []),
            "exclude_prefixes": defaults.get("exclude_prefixes", []),
            "schedule_interval": defaults.get("schedule_interval", ""),
        },
        "paths": {
            "db": paths.get("db", "data/index.db"),
            "download_dir": paths.get("download_dir", "data/files"),
            "updates_dir": paths.get("updates_dir", "data/updates"),
            "last_run_new": paths.get("last_run_new", "data/last_run_new.json"),
        },
        "search": {
            "enabled": bool(search.get("enabled", True)),
            "max_results": search.get("max_results", 5),
            "delay_seconds": search.get("delay_seconds", 0.5),
            "languages": search.get("languages", ["en"]),
            "country": search.get("country", "us"),
            "exclude_keywords": search.get("exclude_keywords", []),
            "queries": search.get("queries", []),
        },
        "features": {
            "enable_file_deletion": bool(features["enable_file_deletion"]),
            "require_auth": bool(features["require_auth"]),
            "enable_global_logs_api": bool(features["enable_global_logs_api"]),
            "enable_rate_limiting": bool(features["enable_rate_limiting"]),
            "enable_csrf": bool(features["enable_csrf"]),
            "enable_security_headers": bool(features["enable_security_headers"]),
            "expose_error_details": bool(features["expose_error_details"]),
            "rate_limit_defaults": features["rate_limit_defaults"],
            "rate_limit_storage_uri": features["rate_limit_storage_uri"],
            "content_security_policy": features["content_security_policy"],
            "sources": dict(features["feature_sources"]),
        },
        "runtime": {
            "config_path": get_sites_config_path(),
            "categories_config_path": get_categories_config_path(),
            "require_auth": bool(features["require_auth"]),
            "session_secret_key_set": bool(os.getenv("FASTAPI_SESSION_SECRET")),
            "bootstrap_admin_token_set": bool(os.getenv("BOOTSTRAP_ADMIN_TOKEN")),
            "file_deletion_enabled": bool(features["enable_file_deletion"]),
            "config_write_auth_required": bool(os.getenv("CONFIG_WRITE_AUTH_TOKEN")),
            "enable_global_logs_api": bool(features["enable_global_logs_api"]),
            "enable_rate_limiting": bool(features["enable_rate_limiting"]),
            "enable_csrf": bool(features["enable_csrf"]),
            "enable_security_headers": bool(features["enable_security_headers"]),
            "expose_error_details": bool(features["expose_error_details"]),
            "rate_limit_defaults": features["rate_limit_defaults"],
            "rate_limit_storage_uri": features["rate_limit_storage_uri"],
            "content_security_policy": features["content_security_policy"],
            "feature_sources": dict(features["feature_sources"]),
            "fastapi_env": fastapi_env,
            "fastapi_env_source": fastapi_env_source,
        },
    }

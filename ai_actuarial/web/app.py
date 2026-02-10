"""Flask web application for managing collections."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from datetime import datetime

# Flask will be an optional dependency for now
try:
    from flask import Flask, render_template, request, jsonify, send_file, Response
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

import csv
import io
import yaml
import schedule
logger = logging.getLogger(__name__)

# Global state for task tracking
_active_tasks = {}
_task_history = []
_task_lock = threading.Lock()


def convert_file_to_markdown(file_path: str, conversion_tool: str, content_type: str) -> dict[str, str]:
    """Convert a local file to markdown using `doc_to_md` engines.

    Args:
        file_path: Local path to the file to convert.
        conversion_tool: Engine name ('marker', 'docling', 'mistral', 'deepseekocr', 'auto').
        content_type: MIME type (kept for logging/diagnostics).

    Returns:
        Dict with: markdown, engine, model

    Raises:
        RuntimeError: If conversion fails or engine dependencies are missing.
    """
    logger.info("Converting %s using %s (content_type=%s)", file_path, conversion_tool, content_type)

    try:
        from doc_to_md.registry import convert_path
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"doc_to_md package not available: {exc}") from exc

    output = convert_path(Path(file_path), engine=conversion_tool)  # type: ignore[arg-type]
    markdown = (output.markdown or "").strip()
    if not markdown:
        raise RuntimeError("Engine returned empty markdown")

    return {"markdown": markdown, "engine": output.engine, "model": output.model}


def _get_sites_config_path() -> str:
    return os.getenv("CONFIG_PATH", "config/sites.yaml")


def _get_categories_config_path() -> str:
    return os.getenv("CATEGORIES_CONFIG_PATH", "config/categories.yaml")


def _load_yaml(path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is None:
        default = {}
    if not os.path.exists(path):
        return dict(default)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return dict(default)
    return data


def _write_yaml(path: str, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)


def _normalize_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("\r\n", "\n").replace(",", "\n").split("\n")
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            s = str(item).strip()
            if s:
                normalized.append(s)
        return normalized
    raise ValueError(f"{field_name} must be a list or string")


def _serialize_backend_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    defaults = config_data.get("defaults") or {}
    paths = config_data.get("paths") or {}
    search = config_data.get("search") or {}
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
        "runtime": {
            "file_deletion_enabled": os.getenv("ENABLE_FILE_DELETION") == "true",
            "file_deletion_auth_required": bool(os.getenv("FILE_DELETION_AUTH_TOKEN")),
            "config_write_auth_required": bool(os.getenv("CONFIG_WRITE_AUTH_TOKEN")),
        },
    }


def create_app(config: dict[str, Any] | None = None) -> Any:
    """Create and configure the Flask application.
    
    Args:
        config: Application configuration dictionary
        
    Returns:
        Flask application instance
        
    Raises:
        ImportError: If Flask is not installed
    """
    if not FLASK_AVAILABLE:
        raise ImportError(
            "Flask is required for the web interface. "
            "Install it with: pip install flask"
        )
    
    app = Flask(__name__, template_folder="templates", static_folder="static")
    
    if config:
        app.config.update(config)
    
    # Load configuration
    config_path = _get_sites_config_path()
    with open(config_path, 'r', encoding='utf-8') as f:
        site_config = yaml.safe_load(f)
    
    # Get database path from config
    db_path = site_config.get('paths', {}).get('db', 'data/index.db')
    download_dir = site_config.get('paths', {}).get('download_dir', 'data/files')
    
    # Convert to absolute paths to handle relative paths
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    if not os.path.isabs(download_dir):
        download_dir = os.path.abspath(download_dir)
    
    # Import storage and collectors here to avoid circular imports
    from ..storage import Storage
    from ..crawler import Crawler, SiteConfig
    from ..collectors import CollectionConfig
    from ..collectors.url import URLCollector
    from ..collectors.file import FileCollector
    from ..collectors.scheduled import ScheduledCollector
    
    # Load task history from disk
    history_file = Path('data/job_history.jsonl')
    if history_file.exists():
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                loaded_history = [json.loads(line) for line in f if line.strip()]
            # Keep only last 100 entries in memory
            if len(loaded_history) > 100:
                loaded_history = loaded_history[-100:]
            global _task_history
            with _task_lock:
                _task_history = loaded_history
        except Exception as e:
            logger.error(f"Failed to load job history: {e}")

    # Register routes
    @app.route("/")
    def index():
        """Main dashboard page."""
        return render_template("index.html")
    
    @app.route("/database")
    def database():
        """Database search and management page."""
        return render_template("database.html")
    
    @app.route("/tasks")
    def tasks():
        """Task progress monitoring page."""
        return render_template("tasks.html")
    
    @app.route("/scheduled_tasks")
    def scheduled_tasks():
        """Scheduled task management page."""
        return render_template("scheduled_tasks.html")

    @app.route("/settings")
    def settings():
        """Backend settings management page."""
        return render_template("settings.html")
    
    @app.route("/collection/url")
    def collection_url():
        """URL collection form."""
        return render_template("collection_url.html")

    @app.route("/collection/file")
    def collection_file():
        """File import form."""
        return render_template("collection_file.html")
    
    @app.route("/api/stats")
    def api_stats():
        """Get dashboard statistics."""
        try:
            storage = Storage(db_path)
            
            # Use abstraction methods instead of direct _conn access
            total_files = storage.get_file_count(require_local=True)
            cataloged_files = storage.get_cataloged_count()
            total_sources = storage.get_sources_count()
            
            storage.close()
            
            with _task_lock:
                active_tasks = len(_active_tasks)
            
            return jsonify({
                "total_files": total_files,
                "cataloged_files": cataloged_files,
                "total_sources": total_sources,
                "active_tasks": active_tasks
            })
        except Exception as e:
            logger.exception("Error getting stats")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/files")
    def api_files():
        """List collected files with filtering and pagination."""
        try:
            storage = Storage(db_path)
            
            # Get query parameters
            limit = int(request.args.get('limit', 20))
            offset = int(request.args.get('offset', 0))
            order_by = request.args.get('order_by', 'last_seen')
            order_dir = request.args.get('order_dir', 'desc')
            query = request.args.get('query', '')
            source = request.args.get('source', '')
            category = request.args.get('category', '')
            include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
            
            # Use abstraction method instead of direct _conn access
            files, total = storage.query_files_with_catalog(
                limit=limit,
                offset=offset,
                order_by=order_by,
                order_dir=order_dir,
                query=query,
                source=source,
                category=category,
                include_deleted=include_deleted,
            )
            
            storage.close()
            
            return jsonify({
                "files": files,
                "total": total,
                "limit": limit,
                "offset": offset
            })
        except Exception as e:
            logger.exception("Error listing files")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/sources")
    def api_sources():
        """Get list of unique sources."""
        try:
            storage = Storage(db_path)
            sources = storage.get_unique_sources()
            storage.close()
            return jsonify({"sources": sources})
        except Exception as e:
            logger.exception("Error getting sources")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/categories")
    def api_categories():
        """Get list of available categories."""
        try:
            mode = request.args.get("mode", "").strip().lower()
            if mode == "used":
                storage = Storage(db_path)
                categories = storage.get_unique_categories()
                storage.close()
                return jsonify({"categories": categories})

            # Load categories from config
            category_config_path = _get_categories_config_path()
            if os.path.exists(category_config_path):
                with open(category_config_path, 'r', encoding='utf-8') as f:
                    cat_config = yaml.safe_load(f) or {}
                    categories = list(cat_config.get('categories', {}).keys())
            else:
                # Fallback to database using abstraction method
                storage = Storage(db_path)
                categories = storage.get_unique_categories()
                storage.close()
            
            return jsonify({"categories": categories})
        except Exception as e:
            logger.exception("Error getting categories")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/categories")
    def api_config_categories():
        """Get full category configuration."""
        try:
            config_data = _load_yaml(
                _get_categories_config_path(),
                default={"categories": {}, "ai_filter_keywords": [], "ai_keywords": []},
            )
            categories = config_data.get("categories") or {}
            if not isinstance(categories, dict):
                categories = {}
            ai_filter_keywords = _normalize_list(
                config_data.get("ai_filter_keywords"), field_name="ai_filter_keywords"
            )
            ai_keywords = _normalize_list(
                config_data.get("ai_keywords"), field_name="ai_keywords"
            )
            return jsonify(
                {
                    "categories": categories,
                    "ai_filter_keywords": ai_filter_keywords,
                    "ai_keywords": ai_keywords,
                }
            )
        except Exception as e:
            logger.exception("Error loading categories config")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/categories", methods=["POST"])
    def api_config_categories_update():
        """Update category configuration in categories.yaml.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN environment variable to be set.
        Requests must include matching X-Auth-Token header.
        """
        try:
            # Authentication check
            expected_token = app.config.get("CONFIG_WRITE_AUTH_TOKEN") or os.getenv(
                "CONFIG_WRITE_AUTH_TOKEN"
            )
            if expected_token:
                provided_token = request.headers.get("X-Auth-Token")
                if not provided_token or provided_token != expected_token:
                    logger.warning("Config write attempt rejected: authentication failed")
                    return jsonify({"error": "Forbidden"}), 403
            
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "Invalid JSON body"}), 400

            raw_categories = data.get("categories")
            if not isinstance(raw_categories, dict):
                return jsonify({"error": "categories must be an object"}), 400

            normalized_categories: dict[str, list[str]] = {}
            for raw_name, raw_keywords in raw_categories.items():
                name = str(raw_name).strip()
                if not name:
                    continue
                normalized_categories[name] = _normalize_list(
                    raw_keywords, field_name=f"categories.{name}"
                )

            existing = _load_yaml(_get_categories_config_path(), default={})
            existing["categories"] = normalized_categories
            existing["ai_filter_keywords"] = _normalize_list(
                data.get("ai_filter_keywords"), field_name="ai_filter_keywords"
            )
            existing["ai_keywords"] = _normalize_list(
                data.get("ai_keywords"), field_name="ai_keywords"
            )
            _write_yaml(_get_categories_config_path(), existing)
            return jsonify({"success": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.exception("Error updating categories config")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/backend-settings")
    def api_config_backend_settings():
        """Get backend settings from sites.yaml and runtime environment."""
        try:
            config_data = _load_yaml(_get_sites_config_path(), default={})
            return jsonify(_serialize_backend_settings(config_data))
        except Exception as e:
            logger.exception("Error getting backend settings")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/search-defaults")
    def api_config_search_defaults():
        """Get search defaults used by Task Center web-search module."""
        try:
            config_data = _load_yaml(_get_sites_config_path(), default={})
            search = (config_data.get("search") or {})
            return jsonify(
                {
                    "enabled": bool(search.get("enabled", True)),
                    "max_results": int(search.get("max_results", 5)),
                    "delay_seconds": float(search.get("delay_seconds", 0.5)),
                    "languages": _normalize_list(search.get("languages"), field_name="search.languages"),
                    "country": str(search.get("country", "us")),
                    "exclude_keywords": _normalize_list(
                        search.get("exclude_keywords"),
                        field_name="search.exclude_keywords",
                    ),
                    "queries": _normalize_list(search.get("queries"), field_name="search.queries"),
                }
            )
        except Exception as e:
            logger.exception("Error getting search defaults")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/backend-settings", methods=["POST"])
    def api_config_backend_settings_update():
        """Update editable backend settings in sites.yaml.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN environment variable to be set.
        Requests must include matching X-Auth-Token header.
        """
        nonlocal site_config
        try:
            # Authentication check
            expected_token = app.config.get("CONFIG_WRITE_AUTH_TOKEN") or os.getenv(
                "CONFIG_WRITE_AUTH_TOKEN"
            )
            if expected_token:
                provided_token = request.headers.get("X-Auth-Token")
                if not provided_token or provided_token != expected_token:
                    logger.warning("Config write attempt rejected: authentication failed")
                    return jsonify({"error": "Forbidden"}), 403
            
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "Invalid JSON body"}), 400

            config_data = _load_yaml(_get_sites_config_path(), default={})
            config_data.setdefault("defaults", {})
            config_data.setdefault("paths", {})
            config_data.setdefault("search", {})

            defaults_in = data.get("defaults")
            if isinstance(defaults_in, dict):
                defaults = config_data["defaults"]
                # user_agent is intentionally locked in UI/API to avoid accidental
                # crawler identity drift across environments.
                if "max_pages" in defaults_in:
                    defaults["max_pages"] = int(defaults_in.get("max_pages") or 0)
                if "max_depth" in defaults_in:
                    defaults["max_depth"] = int(defaults_in.get("max_depth") or 0)
                if "delay_seconds" in defaults_in:
                    defaults["delay_seconds"] = float(defaults_in.get("delay_seconds") or 0)
                if "file_exts" in defaults_in:
                    defaults["file_exts"] = _normalize_list(
                        defaults_in.get("file_exts"), field_name="defaults.file_exts"
                    )
                if "keywords" in defaults_in:
                    defaults["keywords"] = _normalize_list(
                        defaults_in.get("keywords"), field_name="defaults.keywords"
                    )
                if "exclude_keywords" in defaults_in:
                    defaults["exclude_keywords"] = _normalize_list(
                        defaults_in.get("exclude_keywords"),
                        field_name="defaults.exclude_keywords",
                    )
                if "exclude_prefixes" in defaults_in:
                    defaults["exclude_prefixes"] = _normalize_list(
                        defaults_in.get("exclude_prefixes"),
                        field_name="defaults.exclude_prefixes",
                    )
                if "schedule_interval" in defaults_in:
                    defaults["schedule_interval"] = str(
                        defaults_in.get("schedule_interval", "")
                    ).strip()

            paths_in = data.get("paths")
            if isinstance(paths_in, dict):
                paths = config_data["paths"]
                # db path is intentionally locked to prevent runtime/storage split.
                for key in ["download_dir", "updates_dir", "last_run_new"]:
                    if key in paths_in:
                        paths[key] = str(paths_in.get(key, "")).strip()

            search_in = data.get("search")
            if isinstance(search_in, dict):
                search = config_data["search"]
                if "enabled" in search_in:
                    search["enabled"] = bool(search_in.get("enabled"))
                if "max_results" in search_in:
                    search["max_results"] = int(search_in.get("max_results") or 0)
                if "delay_seconds" in search_in:
                    search["delay_seconds"] = float(search_in.get("delay_seconds") or 0)
                if "languages" in search_in:
                    search["languages"] = _normalize_list(
                        search_in.get("languages"), field_name="search.languages"
                    )
                if "country" in search_in:
                    search["country"] = str(search_in.get("country", "")).strip()
                if "exclude_keywords" in search_in:
                    search["exclude_keywords"] = _normalize_list(
                        search_in.get("exclude_keywords"),
                        field_name="search.exclude_keywords",
                    )
                if "queries" in search_in:
                    search["queries"] = _normalize_list(
                        search_in.get("queries"), field_name="search.queries"
                    )

            _write_yaml(_get_sites_config_path(), config_data)
            site_config = config_data
            return jsonify({"success": True, **_serialize_backend_settings(config_data)})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.exception("Error updating backend settings")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/config/sites")
    def api_config_sites():
        """Get configured sites."""
        try:
            # Re-load config to ensure fresh data
            config_path = _get_sites_config_path()
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)
            
            sites = []
            site_defaults = current_config.get('defaults', {})
            for site in current_config.get('sites', []):
                sites.append({
                    'name': site['name'],
                    'url': site['url'],
                    'max_pages': site.get('max_pages', site_defaults.get('max_pages')),
                    'max_depth': site.get('max_depth', site_defaults.get('max_depth')),
                    'keywords': site.get('keywords', site_defaults.get('keywords', [])),
                    'exclude_keywords': site.get('exclude_keywords', []),
                    'exclude_prefixes': site.get('exclude_prefixes', []),
                    'schedule_interval': site.get('schedule_interval')
                })
            return jsonify({"sites": sites})
        except Exception as e:
            logger.exception("Error getting sites config")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/sites/add", methods=["POST"])
    def api_config_sites_add():
        """Add a new site to configuration."""
        nonlocal site_config
        try:
            data = request.get_json()
            if not data or not data.get('name') or not data.get('url'):
                return jsonify({"error": "Name and URL are required"}), 400
            
            config_path = _get_sites_config_path()
            
            # Read current config
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if 'sites' not in config_data:
                config_data['sites'] = []
            
            # Check duplicates
            for s in config_data['sites']:
                if s['name'] == data['name']:
                    return jsonify({"error": "Site name already exists"}), 400
            
            new_site = {
                'name': data['name'],
                'url': data['url']
            }
            if data.get('max_pages'): new_site['max_pages'] = int(data['max_pages'])
            if data.get('max_depth'): new_site['max_depth'] = int(data['max_depth'])
            if data.get('keywords'): new_site['keywords'] = [k.strip() for k in data['keywords'].split(',')]
            if data.get('exclude_keywords'): new_site['exclude_keywords'] = [k.strip() for k in data['exclude_keywords'].split(',')]
            if data.get('exclude_prefixes'): new_site['exclude_prefixes'] = [k.strip() for k in data['exclude_prefixes'].split(',')]
            if data.get('schedule_interval'): new_site['schedule_interval'] = data['schedule_interval'].strip()
            
            config_data['sites'].append(new_site)
            
            # Save back
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)
            
            # Update in-memory config copy
            site_config = config_data
            
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("Error adding site")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/sites/update", methods=["POST"])
    def api_config_sites_update():
        """Update an existing site in configuration."""
        nonlocal site_config
        try:
            data = request.get_json()
            if not data or not data.get('original_name') or not data.get('name'):
                return jsonify({"error": "Original name and new name are required"}), 400
            
            config_path = _get_sites_config_path()
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            found = False
            for s in config_data.get('sites', []):
                if s['name'] == data['original_name']:
                    s['name'] = data['name']
                    s['url'] = data['url']
                    if data.get('max_pages'): s['max_pages'] = int(data['max_pages'])
                    elif 'max_pages' in s: del s['max_pages']
                    
                    if data.get('max_depth'): s['max_depth'] = int(data['max_depth'])
                    elif 'max_depth' in s: del s['max_depth']
                    
                    if data.get('keywords'): 
                        s['keywords'] = [k.strip() for k in data['keywords'].split(',') if k.strip()]
                    elif 'keywords' in s: del s['keywords']
                    
                    if data.get('exclude_keywords'): 
                        s['exclude_keywords'] = [k.strip() for k in data['exclude_keywords'].split(',') if k.strip()]
                    elif 'exclude_keywords' in s: del s['exclude_keywords']

                    if data.get('exclude_prefixes'): 
                        s['exclude_prefixes'] = [k.strip() for k in data['exclude_prefixes'].split(',') if k.strip()]
                    elif 'exclude_prefixes' in s: del s['exclude_prefixes']

                    if data.get('schedule_interval'): 
                        s['schedule_interval'] = data.get('schedule_interval').strip()
                    elif 'schedule_interval' in s: del s['schedule_interval']

                    found = True
                    break
            
            if not found:
                return jsonify({"error": "Site not found"}), 404
                
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)
                
            site_config = config_data
            
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("Error updating site")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/utils/browse-folder")
    def api_browse_folder():
        """Open system dialog to select a folder (Local usage only)."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # Create a hidden root window
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)  # Make it appear on top
            
            folder_path = filedialog.askdirectory(title="Select Folder to Import")
            root.destroy()
            
            if folder_path:
                return jsonify({"path": folder_path.replace('/', os.sep)})
            return jsonify({"path": ""})
        except Exception as e:
            logger.error(f"Error opening file dialog: {e}")
            return jsonify({"error": "Failed to open dialog. Please enter path manually."}), 500

    @app.route("/file/<path:file_url>")
    def file_view(file_url):
        """File details page."""
        try:
            # Flask's path converter unquotes the URL, but we might need to be careful
            # The database stores the full URL
            
            storage = Storage(db_path)
            
            # Use a JOIN to get file info + catalog info in one go
            # Use abstraction method
            file_data = storage.get_file_with_catalog(file_url)
            storage.close()
            
            if not file_data:
                # Try simple matching if exact match failed (e.g. trailing slash issues)
                # or maybe the URL in DB is http but request is https or vice versa if proxied?
                # For now, just return 404
                return f"File not found: {file_url}", 404
            
            return render_template("file_view.html", file=file_data)
            
        except Exception as e:
            logger.exception("Error viewing file")
            return f"Error: {str(e)}", 500
    
    def execute_collection_task(task_id, collection_type, data):
        """Background task execution logic."""
        logger.info(f"Starting background task {task_id} type={collection_type}")
        
        with _task_lock:
             if task_id in _active_tasks:
                 _active_tasks[task_id]["status"] = "running"
                 _active_tasks[task_id]["started_at"] = datetime.now().isoformat()

        # Stop check callback
        def stop_check():
            with _task_lock:
                 return _active_tasks.get(task_id, {}).get("stop_requested", False)
        
        # Progress callback
        def progress_callback(current, total, message):
            with _task_lock:
                if task_id in _active_tasks:
                    task = _active_tasks[task_id]
                    task["current_activity"] = message
                    if total and total > 0 and current is not None:
                        # Ensure progress doesn't go backward from 100 or exceed 100 erroneously
                        p = int((current / total) * 100)
                        task["progress"] = min(max(p, 0), 99) # Cap at 99 until finished
                        task["items_processed"] = current
                        task["items_total"] = total
                    
                    # Log significant events to task logs if we had them
                    # logger.debug(f"Task {task_id} progress: {message}")

        try:
            storage = Storage(db_path)
            result = None
            
            if collection_type == "url":
                urls = data.get("urls", [])
                user_agent = site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1')
                # Pass stop_check to Crawler
                crawler = Crawler(storage, download_dir, user_agent, stop_check=stop_check)
                collector = URLCollector(storage, crawler)
                
                # 获取前端传来的格式，如果为None或空列表则使用默认值
                user_formats = data.get("file_exts")
                if user_formats:  # 确保不是None也不是空列表
                    file_exts = user_formats
                else:
                    file_exts = site_config['defaults'].get('file_exts', [])
                
                # 额外校验：确保file_exts不为空
                if not file_exts:
                    file_exts = ['.pdf', '.docx']  # 最小默认值
                
                config_obj = CollectionConfig(
                    name=data.get("name", "URL Collection"),
                    source_type="url",
                    check_database=data.get("check_database", True),
                    keywords=site_config['defaults'].get('keywords', []),
                    file_exts=file_exts,  # 使用用户选择或默认值
                    exclude_keywords=site_config['defaults'].get('exclude_keywords', []),
                    metadata={"urls": urls}
                )
                result = collector.collect(config_obj, progress_callback=progress_callback)
                
            elif collection_type == "file":
                directory_path = data.get("directory_path")
                # 支持新旧两种字段名：extensions (旧) 和 file_exts (新)
                extensions = data.get("extensions") or data.get("file_exts") or []
                recursive = data.get("recursive", True)
                
                found_files = []
                base_path = Path(directory_path)
                exts = {e.strip().lstrip('.').lower() for e in extensions if e.strip()}
                exclude_kws = site_config['defaults'].get('exclude_keywords', [])
                
                if recursive:
                    iterator = base_path.rglob("*")
                else:
                    iterator = base_path.glob("*")
                    
                for path in iterator:
                    if path.is_file():
                        # Pre-check exclusion to avoid adding unwanted files
                        if exclude_kws and any(k.lower() in path.name.lower() for k in exclude_kws):
                            continue
                        if not exts or path.suffix.lstrip('.').lower() in exts:
                            found_files.append(str(path))
                
                collector = FileCollector(storage, download_dir)
                config_obj = CollectionConfig(
                    name=data.get("name", "File Import"),
                    source_type="file",
                    check_database=True,
                    exclude_keywords=exclude_kws,
                    metadata={"file_paths": found_files}
                )
                result = collector.collect(config_obj, progress_callback=progress_callback)

            elif collection_type == "search":
                from ..search import brave_search, serpapi_search
                
                query = data.get("query")
                site = data.get("site")
                engine = data.get("engine")
                search_defaults = site_config.get("search", {}) or {}
                use_search_defaults = bool(data.get("use_search_defaults", True))

                if use_search_defaults and not search_defaults.get("enabled", True):
                    raise ValueError("Search is disabled in sites.yaml (search.enabled=false)")

                default_count = int(search_defaults.get("max_results", 20))
                raw_count = data.get("count")
                count = int(raw_count) if raw_count not in (None, "", "null") else default_count
                if count <= 0:
                    count = default_count
                api_key = data.get("api_key")
                search_lang = (data.get("search_lang") or "").strip()
                if not search_lang and use_search_defaults:
                    langs = search_defaults.get("languages") or []
                    search_lang = str(langs[0]).strip() if langs else ""
                search_country = (data.get("search_country") or "").strip()
                if not search_country and use_search_defaults:
                    search_country = str(search_defaults.get("country") or "").strip()
                search_exclude_keywords = data.get("search_exclude_keywords") or []
                if isinstance(search_exclude_keywords, str):
                    search_exclude_keywords = [
                        k.strip().lower()
                        for k in search_exclude_keywords.split(",")
                        if k.strip()
                    ]
                elif isinstance(search_exclude_keywords, list):
                    search_exclude_keywords = [
                        str(k).strip().lower() for k in search_exclude_keywords if str(k).strip()
                    ]
                else:
                    search_exclude_keywords = []
                if not search_exclude_keywords and use_search_defaults:
                    search_exclude_keywords = [
                        str(k).strip().lower()
                        for k in (search_defaults.get("exclude_keywords") or [])
                        if str(k).strip()
                    ]
                
                progress_callback(0, count, f"Searching {engine} for '{query}'...")
                
                if site:
                    query = f"site:{site} {query}"
                
                logger.info(f"Performing web search: {query} using {engine}")
                urls = []
                
                if engine == "brave":
                    if not api_key:
                        api_key = os.getenv("BRAVE_API_KEY")
                    if not api_key:
                        raise ValueError("Brave API Key is missing")
                        
                    results = brave_search(
                        query,
                        count,
                        api_key,
                        site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'),
                        lang=search_lang or None,
                        country=search_country or None,
                    )
                    urls = [r.url for r in results]
                
                elif engine == "google":
                    if not api_key:
                        api_key = os.getenv("SERPAPI_API_KEY")
                    if not api_key:
                        raise ValueError("Google SerpAPI Key is missing (SERPAPI_API_KEY not found)")
                    
                    results = serpapi_search(
                        query, 
                        count, 
                        api_key, 
                        site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'),
                        lang=search_lang or None,
                        country=search_country or None,
                        engine="google"
                    )
                    urls = [r.url for r in results]

                if search_exclude_keywords:
                    urls = [
                        u for u in urls
                        if not any(ex_kw in u.lower() for ex_kw in search_exclude_keywords)
                    ]
                
                logger.info(f"Search found {len(urls)} URLs")
                progress_callback(0, len(urls), f"Found {len(urls)} URLs. Starting processing...")
                
                if urls:
                    crawler = Crawler(
                        storage, 
                        download_dir, 
                        site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'),
                        stop_check=stop_check
                    )
                    collector = URLCollector(storage, crawler)
                    
                    # 获取前端传来的格式，如果为None或空列表则使用默认值
                    user_formats = data.get("file_exts")
                    if user_formats:
                        file_exts = user_formats
                    else:
                        file_exts = site_config['defaults'].get('file_exts', [])
                    
                    # 额外校验：确保file_exts不为空
                    if not file_exts:
                        file_exts = ['.pdf', '.docx']
                    
                    config_obj = CollectionConfig(
                        name=f"Search: {query[:30]}...",
                        source_type="url",
                        check_database=True,
                        file_exts=file_exts,  # 添加文件格式参数
                        keywords=site_config['defaults'].get('keywords', []),
                        exclude_keywords=site_config['defaults'].get('exclude_keywords', []),
                        metadata={"urls": urls}
                    )
                    # Pass callback here too
                    result = collector.collect(config_obj, progress_callback=progress_callback)

            elif collection_type == "scheduled":
                crawler = Crawler(
                    storage, 
                    download_dir, 
                    site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'),
                    stop_check=stop_check
                )
                collector = ScheduledCollector(storage, crawler)
                
                target_site_name = data.get("site")
                sites_to_process = []
                default_max_pages = data.get("max_pages") or site_config['defaults'].get('max_pages', 200)
                default_max_depth = data.get("max_depth") or site_config['defaults'].get('max_depth', 2)
                
                for s in site_config.get('sites', []):
                    if target_site_name and s['name'] != target_site_name:
                        continue
                    
                    # Merge defaults and site-specific exclusions
                    def merge_lists(key):
                        defaults = site_config['defaults'].get(key) or []
                        site_vals = s.get(key) or []
                        return list(set(defaults + site_vals))

                    sc = SiteConfig(
                        name=s['name'],
                        url=s['url'],
                        max_pages=data.get("max_pages") or s.get('max_pages') or default_max_pages,
                        max_depth=data.get("max_depth") or s.get('max_depth') or default_max_depth,
                        keywords=s.get('keywords') or site_config['defaults'].get('keywords'),
                        file_exts=site_config['defaults'].get('file_exts'),
                        exclude_keywords=merge_lists('exclude_keywords'),
                        exclude_prefixes=merge_lists('exclude_prefixes')
                    )
                    sites_to_process.append(sc)
                
                config_obj = CollectionConfig(
                    name=data.get("name", "Scheduled Collection"),
                    source_type="scheduled",
                    check_database=True,
                    metadata={"site_configs": sites_to_process}
                )
                result = collector.collect(config_obj, progress_callback=progress_callback)
            
            elif collection_type == "quick_check":
                from ..collectors.adhoc import AdhocCollector
                crawler = Crawler(
                    storage, 
                    download_dir, 
                    site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'),
                    stop_check=stop_check
                )
                collector = AdhocCollector(storage, crawler)
                
                # Create a temporary site config
                site_name = data.get("name") or "Quick Check"
                site_url = data.get("url")
                
                if not site_url:
                    raise ValueError("URL is required for Quick Check")

                # 获取前端传来的格式，如果为None或空列表则使用默认值
                user_formats = data.get("file_exts")
                if user_formats:
                    file_exts = user_formats
                else:
                    file_exts = site_config['defaults'].get('file_exts', [])
                
                # 额外校验：确保file_exts不为空
                if not file_exts:
                    file_exts = ['.pdf', '.docx']

                sc = SiteConfig(
                    name=site_name,
                    url=site_url,
                    max_pages=data.get("max_pages", 10), # Default to small number
                    max_depth=data.get("max_depth", 1),  # Default to 1
                    keywords=data.get("keywords", []),
                    file_exts=file_exts,  # 使用用户选择或默认值
                    exclude_keywords=site_config['defaults'].get('exclude_keywords', []),
                    exclude_prefixes=site_config['defaults'].get('exclude_prefixes', [])
                )
                
                config_obj = CollectionConfig(
                    name=f"Quick Check: {site_name}",
                    source_type="adhoc",
                    check_database=data.get("check_database", False), # Usually distinct
                    metadata={"site_configs": [sc]}
                )
                result = collector.collect(config_obj, progress_callback=progress_callback)
            
            elif collection_type == "catalog":
                # New Catalog Task
                from ..catalog_incremental import run_incremental_catalog
                
                stats = run_incremental_catalog(
                    db_path=db_path,
                    out_jsonl=Path("data/catalog.jsonl"),
                    out_md=Path("data/catalog.md"),
                    limit=int(data.get("max_items", 100)),
                    retry_errors=data.get("retry_errors", False),
                    progress_callback=progress_callback,
                )
                
                # Mock result for catalog
                class CatalogResult:
                    def __init__(self, s):
                        self.success = s
                        self.errors = stats.get('error_samples', [])
                        self.catalog_scanned = stats.get('scanned', 0)
                        self.catalog_ok = stats.get('processed', 0)
                        self.catalog_skipped = stats.get('skipped_ai', 0)
                        self.catalog_errors = stats.get('errors', 0)
                        self.items_found = self.catalog_scanned
                        self.items_downloaded = self.catalog_ok
                        self.items_skipped = self.catalog_skipped
                
                result = CatalogResult(True)
                progress_callback(100, 100, f"Cataloging complete. Processed {stats.get('processed')} items.")

            elif collection_type == "markdown_conversion":
                # Markdown conversion task
                file_urls = data.get("file_urls", [])
                conversion_tool = data.get("conversion_tool", "auto")
                overwrite_existing = data.get("overwrite_existing", False)
                
                logger.info(f"Starting markdown conversion for {len(file_urls)} files")
                
                converted_count = 0
                error_count = 0
                skipped_count = 0
                errors = []
                
                for idx, file_url in enumerate(file_urls):
                    if stop_check():
                        logger.info("Markdown conversion stopped by user")
                        break
                    
                    progress_callback(idx, len(file_urls), f"Converting file {idx+1}/{len(file_urls)}")
                    
                    try:
                        # Get file info
                        file_info = storage.get_file_with_catalog(file_url)
                        if not file_info:
                            logger.warning(f"File not found: {file_url}")
                            error_count += 1
                            errors.append(f"File not found: {file_url}")
                            continue
                        
                        # Skip if markdown already exists and not overwriting
                        if not overwrite_existing and file_info.get('markdown_content'):
                            logger.info(f"Skipping file with existing markdown: {file_url}")
                            skipped_count += 1
                            continue
                        
                        # Check if file has local_path
                        local_path = file_info.get('local_path')
                        if not local_path:
                            logger.warning(f"File has no local_path: {file_url}")
                            error_count += 1
                            errors.append(f"File not available locally: {file_url}")
                            continue
                        
                        # Resolve relative paths to absolute paths (same as /api/download)
                        # Local Import stores files with local_path relative to download_dir.parent
                        # (the data directory), not relative to download_dir itself
                        if not os.path.isabs(local_path):
                            relative_path = Path(local_path)
                            # Use the parent of download_dir as base (e.g., data/) for relative paths
                            base_dir = Path(download_dir).parent.resolve()
                            candidate = (base_dir / relative_path).resolve()
                            
                            if candidate.exists():
                                local_path = str(candidate)
                            else:
                                # Fallback: try resolving relative to download_dir itself
                                fallback_base = Path(download_dir).resolve()
                                fallback_candidate = (fallback_base / relative_path).resolve()
                                if fallback_candidate.exists():
                                    local_path = str(fallback_candidate)
                                else:
                                    logger.warning(f"Failed to resolve local_path for {file_url}")
                                    error_count += 1
                                    errors.append(f"File not found on disk: {file_url}")
                                    continue
                        
                        # Check if resolved path exists
                        if not os.path.exists(local_path):
                            logger.warning(f"File not available locally: {file_url}")
                            error_count += 1
                            errors.append(f"File not available locally: {file_url}")
                            continue
                        
                        # Convert file to markdown using doc_to_md engines.
                        try:
                            conversion = convert_file_to_markdown(
                                local_path,
                                conversion_tool,
                                file_info.get("content_type", ""),
                            )
                        except Exception as exc:  # noqa: BLE001
                            error_count += 1
                            errors.append(f"{file_url}: conversion failed ({conversion_tool}): {exc}")
                            continue

                        markdown_content = conversion["markdown"]
                        used_engine = conversion.get("engine") or conversion_tool

                        # Save markdown to database
                        success, error = storage.update_file_markdown(
                            url=file_url,
                            markdown_content=markdown_content,
                            markdown_source=f"converted_{used_engine}",
                        )

                        if success:
                            converted_count += 1
                            logger.info("Converted file to markdown: %s (engine=%s)", file_url, used_engine)
                        else:
                            error_count += 1
                            errors.append(f"Failed to save markdown for {file_url}: {error}")
                    
                    except Exception as e:
                        logger.exception(f"Error converting {file_url}")
                        error_count += 1
                        errors.append(f"{file_url}: {str(e)}")
                
                # Create result object
                class MarkdownConversionResult:
                    def __init__(self):
                        self.success = True
                        self.items_found = len(file_urls)
                        self.items_downloaded = converted_count
                        self.items_skipped = skipped_count
                        self.errors = errors[:10]  # Limit to first 10 errors
                
                result = MarkdownConversionResult()
                progress_callback(100, 100, f"Conversion complete. Converted: {converted_count}, Skipped: {skipped_count}, Errors: {error_count}")

            storage.close()
            
            # Update status
            completed_at = datetime.now().isoformat()
            with _task_lock:
                if task_id in _active_tasks:
                    task_data = _active_tasks.pop(task_id)
                    task_data.update({
                        "status": "completed" if result and result.success else "failed",
                        "completed_at": completed_at,
                        "progress": 100,
                        "current_activity": "Finished",
                        "items_processed": result.items_found if result else 0,
                        "items_downloaded": result.items_downloaded if result else 0,
                        "items_skipped": getattr(result, "items_skipped", 0),
                        "errors": result.errors if result else [],
                        "catalog_scanned": getattr(result, "catalog_scanned", None),
                        "catalog_ok": getattr(result, "catalog_ok", None),
                        "catalog_skipped": getattr(result, "catalog_skipped", None),
                        "catalog_errors": getattr(result, "catalog_errors", None),
                    })
                    # Check if stopped
                    if task_data.get("stop_requested"):
                         task_data["status"] = "stopped"
                         
                    _task_history.append(task_data)
                    _append_history_to_disk(task_data)
                    
        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            with _task_lock:
                if task_id in _active_tasks:
                    task_data = _active_tasks.pop(task_id)
                    task_data.update({
                        "status": "error",
                        "completed_at": datetime.now().isoformat(),
                        "progress": 100,
                        "errors": [str(e)]
                    })
                    _task_history.append(task_data)
                    _append_history_to_disk(task_data)

    @app.route("/api/export")
    def export_data():
        """Export catalog data as CSV/JSON."""
        format_type = request.args.get('format', 'csv')
        
        # Connect to DB
        try:
            storage = Storage(db_path)

            # Use Storage abstraction to query files with catalog information
            rows = storage.query_files_with_catalog()

            # Normalize rows to a list of dictionaries
            data = []
            for row in rows:
                if isinstance(row, dict):
                    data.append(dict(row))
                else:
                    # Fallback for row objects with keys() / mapping interface
                    try:
                        data.append({k: row[k] for k in row.keys()})  # type: ignore[attr-defined]
                    except Exception:
                        # As a last resort, attempt to use _mapping (e.g., sqlite Row)
                        mapping = getattr(row, "_mapping", None)
                        if mapping is not None:
                            data.append(dict(mapping))
                        else:
                            # If we cannot interpret the row, skip it
                            continue
            
            # Format keywords
            for d in data:
                # Process keywords
                raw_kws = d.get('keywords_json')
                d['keywords'] = ""
                if raw_kws:
                    try:
                        keywords_list = json.loads(raw_kws)
                        if isinstance(keywords_list, list):
                            d['keywords'] = ", ".join(keywords_list)
                        else:
                            d['keywords'] = str(keywords_list)
                    except Exception as e:
                        logger.warning(
                            "Failed to parse keywords_json for catalog export: %r (%s)",
                            raw_kws,
                            e,
                        )
                
                # Cleanup internal fields
                if 'keywords_json' in d:
                    del d['keywords_json']

            storage.close()

            if format_type == 'json':
                return jsonify(data)
            
            # CSV export
            si = io.StringIO()
            cw = csv.DictWriter(si, fieldnames=data[0].keys() if data else [])
            cw.writeheader()
            cw.writerows(data)
            output = si.getvalue()
            
            # Use Latin-1 or UTF-8-SIG for Excel compatibility
            return Response(
                output.encode('utf-8-sig'),
                mimetype="text/csv",
                headers={"Content-disposition": "attachment; filename=catalog_export.csv"}
            )
            
        except Exception as e:
            logger.exception("Export failed")
            return f"Export failed: {str(e)}", 500

    @app.route("/api/collections/run", methods=["POST"])
    def run_collection():
        """Start a collection operation."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            
            collection_type = data.get("type")
            valid_types = ["scheduled", "adhoc", "url", "file", "search", "catalog", "quick_check"]
            if not collection_type or collection_type not in valid_types:
                return jsonify({"error": f"Invalid collection type"}), 400

            # Quick validation before starting background task
            if collection_type == "url" and not data.get("urls"):
                 return jsonify({"error": "No URLs provided"}), 400
            if collection_type == "file":
                 path = data.get("directory_path")
                 if not path or not os.path.exists(path):
                     return jsonify({"error": "Invalid directory path"}), 400

            task_id = f"task_{int(datetime.now().timestamp())}"
            task_name = data.get("name", f"{collection_type.capitalize()} Collection")
            
            with _task_lock:
                _active_tasks[task_id] = {
                    "id": task_id,
                    "name": task_name,
                    "type": collection_type,
                    "status": "pending",
                    "progress": 0,
                    "started_at": datetime.now().isoformat(),
                    "items_processed": 0,
                    "items_total": 0 
                }
            
            # Start background thread
            thread = threading.Thread(
                target=execute_collection_task,
                args=(task_id, collection_type, data)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "success": True, 
                "message": "Task started in background",
                "job_id": task_id
            })

        except Exception as e:
            logger.exception("Error starting collection")
            return jsonify({"error": str(e)}), 500
    
    def _append_history_to_disk(task_data):
        """Append a task record to the persistent history file."""
        try:
            p = Path('data/job_history.jsonl')
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, 'a', encoding='utf-8') as f:
                f.write(json.dumps(task_data) + "\n")
        except Exception as e:
            logger.error(f"Failed to save task history: {e}")

    @app.route("/api/tasks/stop/<task_id>", methods=["POST"])
    def api_tasks_stop(task_id):
        """Request to stop a running task."""
        with _task_lock:
            if task_id in _active_tasks:
                _active_tasks[task_id]["stop_requested"] = True
                logger.info(f"Stop requested for task {task_id}")
                return jsonify({"success": True, "message": "Stop signal sent"})
            return jsonify({"error": "Task not found or not active"}), 404

    @app.route("/api/tasks/active")
    def api_tasks_active():
        """Get active tasks."""
        with _task_lock:
            tasks = list(_active_tasks.values())
        return jsonify({"tasks": tasks})
    
    @app.route("/api/tasks/history")
    def api_tasks_history():
        """Get task history."""
        limit = int(request.args.get('limit', 10))
        with _task_lock:
            # Sort by started_at desc
            tasks = sorted(_task_history, key=lambda x: x.get('started_at', ''), reverse=True)[:limit]
        return jsonify({"tasks": tasks})
    
    @app.route("/api/collections/history")
    def api_collections_history():
        """Get collection history."""
        try:
            # Read from updates directory
            updates_dir = site_config.get('paths', {}).get('updates_dir', 'data/updates')
            history = []
            
            if os.path.exists(updates_dir):
                import re
                # Pattern to match update_YYYYMMDD_HHMMSSZ.json
                timestamp_pattern = re.compile(r'update_(\d{8}_\d{6}Z)\.json$')
                
                for filename in sorted(os.listdir(updates_dir), reverse=True)[:10]:
                    match = timestamp_pattern.match(filename)
                    if match:
                        filepath = os.path.join(updates_dir, filename)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                # Extract timestamp from regex match
                                timestamp = match.group(1)
                                history.append({
                                    'timestamp': timestamp,
                                    'type': 'scheduled',
                                    'items_found': len(data),
                                    'items_downloaded': len(data),
                                    'status': 'completed'
                                })
                        except Exception:
                            continue
            
            return jsonify({"history": history})
        except Exception as e:
            logger.exception("Error getting collection history")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/download")
    def api_download():
        """Download a file."""
        try:
            url = request.args.get('url')
            if not url:
                return jsonify({"error": "URL parameter required"}), 400
            
            storage = Storage(db_path)
            file_record = storage.get_file_by_url(url)
            storage.close()
            
            if not file_record or not file_record.get('local_path'):
                return jsonify({"error": "File not found"}), 404
            
            local_path = file_record['local_path']
            # Resolve relative paths to absolute paths stored in the database
            if not os.path.isabs(local_path):
                relative_path = Path(local_path)
                # Use the parent of download_dir as base to resolve relative paths from the database
                base_dir = Path(download_dir).parent.resolve()
                candidate = (base_dir / relative_path).resolve()
                
                if candidate.exists():
                    local_path = str(candidate)
                else:
                    # Fallback: try resolving relative to download_dir itself
                    fallback_base = Path(download_dir).resolve()
                    fallback_candidate = (fallback_base / relative_path).resolve()
                    if fallback_candidate.exists():
                        local_path = str(fallback_candidate)
                    else:
                        logger.warning(
                            "Failed to resolve local_path '%s' for URL '%s' using bases '%s' and '%s'. "
                            "This may indicate that files were imported with a different download_dir "
                            "configuration or working directory.",
                            local_path,
                            url,
                            base_dir,
                            fallback_base,
                        )
                        return jsonify({"error": "File not found on disk (path resolution failed)"}), 404
            
            # Security: Validate that resolved path is within expected directory tree
            resolved_path = Path(local_path).resolve()
            data_dir = Path(download_dir).parent.resolve()
            try:
                resolved_path.relative_to(data_dir)
            except ValueError:
                logger.warning(
                    "Security: Attempted to access file outside data directory. "
                    "Path: '%s', Data dir: '%s'",
                    resolved_path,
                    data_dir
                )
                return jsonify({"error": "Invalid file path"}), 403
            
            if not os.path.exists(local_path):
                return jsonify({"error": "File not found on disk"}), 404
            
            filename = file_record.get('original_filename') or os.path.basename(local_path)
            return send_file(local_path, as_attachment=True, download_name=filename)
        except Exception as e:
            logger.exception("Error downloading file")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/files/delete", methods=["POST"])
    def api_files_delete():
        """Soft delete a file and optionally delete its stored copy.
        
        Security controls:
        - Feature flag: ENABLE_FILE_DELETION=true must be set in the environment.
        - Optional authentication: if FILE_DELETION_AUTH_TOKEN is configured in
          app.config or the environment, requests must supply a matching
          X-Auth-Token header.
        - Explicit confirmation: request JSON must include {"confirm": "DELETE"}.
        - Path validation: only delete files within the configured download_dir.
        """
        try:
            # Feature flag check
            if os.getenv("ENABLE_FILE_DELETION") != "true":
                logger.warning("File deletion attempt rejected: ENABLE_FILE_DELETION not set to 'true'")
                return jsonify({"error": "File deletion is disabled. Set ENABLE_FILE_DELETION=true in environment."}), 403

            # Optional authentication check
            expected_token = app.config.get("FILE_DELETION_AUTH_TOKEN") or os.getenv(
                "FILE_DELETION_AUTH_TOKEN"
            )
            if expected_token:
                provided_token = request.headers.get("X-Auth-Token")
                if not provided_token or provided_token != expected_token:
                    logger.warning("File deletion attempt rejected: authentication failed")
                    return jsonify({"error": "Forbidden"}), 403

            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                logger.error("File deletion request has invalid JSON body")
                return jsonify({"error": "Invalid or missing JSON body"}), 400

            url = data.get("url")
            if not url:
                logger.error("File deletion request missing URL")
                return jsonify({"error": "No URL provided"}), 400

            # Require explicit confirmation to reduce accidental deletions
            confirmation = data.get("confirm")
            if confirmation != "DELETE":
                logger.warning(f"File deletion attempt for {url} rejected: missing confirmation")
                return (
                    jsonify(
                        {
                            "error": (
                                "Explicit confirmation required. "
                                'Include {"confirm": "DELETE"} in the request body.'
                            )
                        }
                    ),
                    400,
                )

            logger.info(f"Starting file deletion for URL: {url}")
            storage = Storage(db_path)
            deletion_details = {
                "url": url,
                "database_marked": False,
                "physical_file_deleted": False,
                "errors": []
            }
            
            try:
                # Mark as deleted using abstraction method
                deleted_time = datetime.now().isoformat()
                storage.mark_file_deleted(url, deleted_time)
                deletion_details["database_marked"] = True
                logger.info(f"Database marked file as deleted: {url} at {deleted_time}")

                # Delete physical file
                file_record = storage.get_file_by_url(url)
                if file_record and file_record.get("local_path"):
                    local_path = file_record["local_path"]
                    try:
                        # Path traversal protection: only delete within download_dir
                        base_dir = Path(download_dir).resolve()
                        
                        # Handle relative paths
                        if not os.path.isabs(local_path):
                            candidate_path = (base_dir.parent / local_path).resolve()
                        else:
                            candidate_path = Path(local_path).resolve()

                        # Ensure candidate_path is within base_dir
                        try:
                            # Python 3.9+ has is_relative_to; fall back otherwise
                            is_within = candidate_path.is_relative_to(base_dir.parent)  # type: ignore[attr-defined]
                        except AttributeError:
                            is_within = os.path.commonpath(
                                [str(base_dir.parent), str(candidate_path)]
                            ) == str(base_dir.parent)

                        if not is_within:
                            error_msg = f"Security: File outside allowed directory: {candidate_path}"
                            logger.error(error_msg)
                            deletion_details["errors"].append(error_msg)
                        elif candidate_path.exists():
                            os.remove(candidate_path)
                            deletion_details["physical_file_deleted"] = True
                            logger.info(f"Physical file deleted successfully: {candidate_path}")
                            # Clear local path in DB to indicate it's gone
                            storage.clear_local_path(url)
                            logger.info(f"Database local_path cleared for: {url}")
                        else:
                            warning_msg = f"Physical file not found (already deleted?): {candidate_path}"
                            logger.warning(warning_msg)
                            deletion_details["errors"].append(warning_msg)
                            # Still clear the path since file doesn't exist
                            storage.clear_local_path(url)
                    except Exception as ex:
                        error_msg = f"Failed to delete physical file {local_path}: {str(ex)}"
                        logger.error(error_msg, exc_info=True)
                        deletion_details["errors"].append(error_msg)
                else:
                    warning_msg = "No local_path found in database for this file"
                    logger.warning(f"{warning_msg}: {url}")
                    deletion_details["errors"].append(warning_msg)

            finally:
                storage.close()

            # Log final status
            if deletion_details["database_marked"] and deletion_details["physical_file_deleted"]:
                logger.info(f"File deletion completed successfully: {url}")
            elif deletion_details["database_marked"]:
                logger.warning(f"File deletion partial: database marked but physical file not deleted: {url}")
            else:
                logger.error(f"File deletion failed: {url}")

            return jsonify({
                "success": True,
                "details": deletion_details
            })
        except Exception as e:
            logger.exception(f"Error deleting file: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/update", methods=["POST"])
    def api_files_update():
        """Update file catalog information (category, summary, keywords)."""
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                logger.error("File update request has invalid JSON body")
                return jsonify({"error": "Invalid or missing JSON body"}), 400

            url = data.get("url")
            if not url:
                logger.error("File update request missing URL")
                return jsonify({"error": "No URL provided"}), 400

            # Extract update fields
            category = data.get("category")
            summary = data.get("summary")
            keywords = data.get("keywords")

            # Accept category as list (multi-select) and store as semicolon-separated text.
            if isinstance(category, list):
                category = "; ".join(
                    [str(c).strip() for c in category if str(c).strip()]
                )
            elif category is not None:
                category = str(category).strip()

            # Validate keywords is a list if provided
            if keywords is not None and not isinstance(keywords, list):
                return jsonify({"error": "Keywords must be a list"}), 400

            logger.info(f"Updating file catalog for URL: {url}")
            storage = Storage(db_path)
            
            try:
                success, error_reason = storage.update_file_catalog(
                    url=url,
                    category=category,
                    summary=summary,
                    keywords=keywords
                )
                
                if success:
                    logger.info(f"File catalog updated successfully: {url}")
                    # Fetch updated data to return
                    file_data = storage.get_file_with_catalog(url)
                    return jsonify({
                        "success": True,
                        "file": file_data
                    })
                else:
                    # Handle different failure reasons
                    if error_reason == "file_not_found":
                        logger.warning(f"File catalog update failed - file not found: {url}")
                        return jsonify({"error": "File not found"}), 404
                    elif error_reason == "no_updates":
                        logger.warning(f"File catalog update had no changes: {url}")
                        return jsonify({"error": "No updates provided"}), 400
                    else:
                        logger.error(f"File catalog update failed with unknown reason: {url}")
                        return jsonify({"error": "Update failed"}), 500
                    
            finally:
                storage.close()

        except Exception as e:
            logger.exception(f"Error updating file: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/<path:file_url>/markdown", methods=["GET"])
    def api_files_get_markdown(file_url):
        """Get markdown content for a file."""
        try:
            url = file_url
            
            logger.info(f"Fetching markdown content for URL: {url}")
            storage = Storage(db_path)
            
            try:
                markdown_data = storage.get_file_markdown(url)
                
                if markdown_data and markdown_data.get("markdown_content"):
                    logger.info(f"Markdown content found for: {url}")
                    return jsonify({
                        "success": True,
                        "markdown": markdown_data
                    })
                else:
                    logger.info(f"No markdown content found for: {url}")
                    return jsonify({
                        "success": True,
                        "markdown": None
                    })
                    
            finally:
                storage.close()
                
        except Exception as e:
            logger.exception(f"Error fetching markdown content: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/<path:file_url>/markdown", methods=["POST"])
    def api_files_update_markdown(file_url):
        """Update markdown content for a file."""
        try:
            from urllib.parse import unquote
            url = unquote(file_url)
            
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                logger.error("Markdown update request has invalid JSON body")
                return jsonify({"error": "Invalid or missing JSON body"}), 400
            
            markdown_content = data.get("markdown_content")
            if markdown_content is None:
                logger.error("Markdown update request missing content")
                return jsonify({"error": "No markdown_content provided"}), 400
            
            markdown_source = data.get("markdown_source", "manual")
            
            logger.info(f"Updating markdown content for URL: {url}")
            storage = Storage(db_path)
            
            try:
                success, error_reason = storage.update_file_markdown(
                    url=url,
                    markdown_content=markdown_content,
                    markdown_source=markdown_source
                )
                
                if success:
                    logger.info(f"Markdown content updated successfully: {url}")
                    # Fetch updated data to return
                    markdown_data = storage.get_file_markdown(url)
                    return jsonify({
                        "success": True,
                        "markdown": markdown_data
                    })
                else:
                    if error_reason == "file_not_found":
                        logger.warning(f"Markdown update failed - file not found: {url}")
                        return jsonify({"error": "File not found"}), 404
                    else:
                        logger.error(f"Markdown update failed: {url}")
                        return jsonify({"error": "Update failed"}), 500
                        
            finally:
                storage.close()
                
        except Exception as e:
            logger.exception(f"Error updating markdown: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/logs/global")
    def api_logs_global():
        """Get global application logs."""
        try:
            log_dir = Path("data")
            log_file = log_dir / "app.log"
            
            if not log_file.exists():
                return jsonify({"logs": "No logs found."})
            
            # Read last 500 lines efficiently
            lines = []
            
            # Simple approach for reasonable log sizes
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                # Read all lines and get last 500
                all_lines = f.readlines()
                lines = all_lines[-500:]
                
            # Reverse to show newest first
            lines.reverse()
                
            return jsonify({"logs": "".join(lines)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Scheduler Initialization
    def init_scheduler():
        try:
            logger.info("Initializing scheduler...")
            schedule.clear()
            
            # Check for global schedule in defaults or root
            global_schedule = site_config.get('defaults', {}).get('schedule_interval') 
            # Or dedicated key if user adds it
            
            # Helper to add job
            def add_job(interval_str, job_func, job_id_suffix):
                try:
                    logger.info(f"Adding schedule: {interval_str}")
                    if interval_str == "daily":
                        # Default to 00:30 server time (approx "night")
                        schedule.every().day.at("00:30").do(job_func)
                    elif interval_str == "weekly":
                        schedule.every().monday.at("00:30").do(job_func)
                    elif interval_str.startswith("daily at "):
                         t = interval_str.replace("daily at ", "").strip()
                         schedule.every().day.at(t).do(job_func)
                    elif interval_str.startswith("every "):
                        parts = interval_str.split()
                        if len(parts) >= 3:
                            qty = int(parts[1])
                            unit = parts[2]
                            if "hour" in unit:
                                schedule.every(qty).hours.do(job_func)
                            elif "minute" in unit:
                                schedule.every(qty).minutes.do(job_func)
                except Exception as ex:
                    logger.error(f"Failed to parse schedule '{interval_str}': {ex}")

            # 1. Global Schedule (All Sites)
            if global_schedule:
                def global_run():
                    logger.info("Triggering GLOBAL scheduled job")
                    task_id = f"sched_global_{int(datetime.now().timestamp())}"
                    with _task_lock:
                        _active_tasks[task_id] = {
                            "id": task_id,
                            "name": f"Scheduled: All Sites",
                            "type": "scheduled",
                            "status": "pending",
                            "progress": 0,
                            "started_at": datetime.now().isoformat()
                        }
                    data = {
                        "site": None, # Indicates ALL sites
                        "name": "Scheduled Run (All)",
                        "max_pages": site_config['defaults'].get('max_pages'),
                        "max_depth": site_config['defaults'].get('max_depth')
                    }
                    threading.Thread(target=execute_collection_task, 
                                     args=(task_id, "scheduled", data)).start()
                
                add_job(global_schedule, global_run, "global")

            # 2. Per-site overrides (keep for backward compat or specific needs)
            sites = site_config.get('sites', [])
            for site in sites:
                interval = site.get('schedule_interval')
                if not interval:
                    continue
                # If global schedule exists, maybe warn or ignore? 
                # Let's allow specific sites to run EXTRA times if they define their own.
                
                def job_wrapper(s=site):
                    logger.info(f"Triggering scheduled job for {s['name']}")
                    task_id = f"sched_{s['name']}_{int(datetime.now().timestamp())}"
                    
                    with _task_lock:
                        _active_tasks[task_id] = {
                            "id": task_id,
                            "name": f"Scheduled: {s['name']}",
                            "type": "scheduled",
                            "status": "pending",
                            "progress": 0,
                            "started_at": datetime.now().isoformat()
                        }
                    
                    data = {
                        "site": s['name'],
                        "name": f"Scheduled: {s['name']}",
                        "max_pages": s.get('max_pages'),
                        "max_depth": s.get('max_depth')
                    }
                    threading.Thread(target=execute_collection_task, 
                                     args=(task_id, "scheduled", data)).start()

                add_job(interval, job_wrapper, site['name'])

            def scheduler_loop():
                logger.info("Scheduler loop started")
                while True:
                    schedule.run_pending()
                    time.sleep(60)
            
            st = threading.Thread(target=scheduler_loop, daemon=True)
            st.start()

        except Exception as e:
            logger.error(f"Scheduler init failed: {e}")

    # Only start scheduler if not in reloader or if main instance
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduler()

    return app


def run_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Run the web server.
    
    Args:
        host: Host address to bind to. 
              WARNING: Use '0.0.0.0' only in trusted networks or with authentication!
        port: Port number to bind to
        debug: Enable debug mode
    """
    if not FLASK_AVAILABLE:
        raise ImportError(
            "Flask is required for the web interface. "
            "Install it with: pip install flask"
        )
    
    # Configure logging
    log_dir = Path("data")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ],
        force=True  # Force reconfiguration
    )
    
    app = create_app()
    logger.info("Starting web server on %s:%d", host, port)
    app.run(host=host, port=port, debug=debug)

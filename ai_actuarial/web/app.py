"""Flask web application for managing collections."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any
from datetime import datetime

# Flask will be an optional dependency for now
try:
    from flask import Flask, render_template, request, jsonify, send_file
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

import yaml

logger = logging.getLogger(__name__)

# Global state for task tracking
_active_tasks = {}
_task_history = []
_task_lock = threading.Lock()


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
    config_path = os.getenv('CONFIG_PATH', 'config/sites.yaml')
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
    from ..crawler import Crawler
    from ..collectors import CollectionConfig
    from ..collectors.url import URLCollector
    from ..collectors.file import FileCollector
    
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
    
    @app.route("/collection/url")
    def collection_url():
        """URL collection form."""
        return render_template("collection_url.html")
    
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
            
            # Use abstraction method instead of direct _conn access
            files, total = storage.query_files_with_catalog(
                limit=limit,
                offset=offset,
                order_by=order_by,
                order_dir=order_dir,
                query=query,
                source=source,
                category=category,
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
            # Load categories from config
            category_config_path = 'config/categories.yaml'
            if os.path.exists(category_config_path):
                with open(category_config_path, 'r', encoding='utf-8') as f:
                    cat_config = yaml.safe_load(f)
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
    
    @app.route("/api/config/sites")
    def api_config_sites():
        """Get configured sites."""
        try:
            sites = []
            for site in site_config.get('sites', []):
                sites.append({
                    'name': site['name'],
                    'url': site['url'],
                    'max_pages': site.get('max_pages', site_config['defaults'].get('max_pages')),
                    'max_depth': site.get('max_depth', site_config['defaults'].get('max_depth')),
                    'keywords': site.get('keywords', site_config['defaults'].get('keywords', []))
                })
            return jsonify({"sites": sites})
        except Exception as e:
            logger.exception("Error getting sites config")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/collections/run", methods=["POST"])
    def run_collection():
        """Start a collection operation."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            
            collection_type = data.get("type")
            
            # Validate collection type
            valid_types = ["scheduled", "adhoc", "url", "file"]
            if not collection_type or collection_type not in valid_types:
                return jsonify({
                    "error": f"Invalid collection type. Must be one of: {', '.join(valid_types)}"
                }), 400
            
            # Handle URL collection
            if collection_type == "url":
                urls = data.get("urls", [])
                if not urls:
                    return jsonify({"error": "No URLs provided"}), 400
                
                storage = Storage(db_path)
                user_agent = site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1')
                crawler = Crawler(storage, download_dir, user_agent)
                collector = URLCollector(storage, crawler)
                
                config_obj = CollectionConfig(
                    name=data.get("name", "URL Collection"),
                    source_type="url",
                    check_database=data.get("check_database", True),
                    keywords=site_config['defaults'].get('keywords', []),
                    file_exts=site_config['defaults'].get('file_exts', []),
                    metadata={"urls": urls}
                )
                
                result = collector.collect(config_obj)
                storage.close()
                
                return jsonify({
                    "success": result.success,
                    "message": f"Collection completed",
                    "items_found": result.items_found,
                    "items_downloaded": result.items_downloaded,
                    "items_skipped": result.items_skipped,
                    "errors": result.errors[:5] if result.errors else []
                })
            
            # For other types, return placeholder response
            return jsonify({
                "success": True,
                "message": f"Collection {collection_type} started",
                "job_id": f"task_{datetime.now().timestamp()}"
            })
        except Exception as e:
            logger.exception("Error starting collection")
            return jsonify({"error": str(e)}), 500
    
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
        # Protect _task_history list access with lock to prevent race conditions
        # when tasks are being added/removed concurrently by background threads
        with _task_lock:
            tasks = _task_history[-limit:]
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
    
    @app.route("/api/delete_file", methods=["POST"])
    def api_delete_file():
        """Delete a file with backend confirmation.
        
        SECURITY WARNING: This endpoint is currently disabled by default.
        Set ENABLE_FILE_DELETION=true in environment to enable.
        Authentication should be implemented before enabling in production.
        """
        # Feature flag to disable endpoint until authentication is implemented
        if not os.getenv('ENABLE_FILE_DELETION', '').lower() in ('true', '1', 'yes'):
            return jsonify({
                "error": "File deletion endpoint is disabled. "
                        "Set ENABLE_FILE_DELETION=true to enable."
            }), 403
        
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            
            url = data.get('url')
            confirm = data.get('confirm', False)
            
            if not url:
                return jsonify({"error": "URL parameter required"}), 400
            
            if not confirm:
                return jsonify({"error": "Confirmation required for file deletion"}), 400
            
            # TODO: Add proper authentication check here before enabling by default
            # Example:
            # auth_token = request.headers.get('Authorization')
            # if not verify_auth_token(auth_token):
            #     return jsonify({"error": "Authentication required"}), 401
            
            storage = Storage(db_path)
            file_record = storage.get_file_by_url(url)
            
            if not file_record or not file_record.get('local_path'):
                storage.close()
                return jsonify({"error": "File not found"}), 404
            
            local_path = file_record['local_path']
            
            # Resolve and validate path (same security checks as download)
            if not os.path.isabs(local_path):
                relative_path = Path(local_path)
                base_dir = Path(download_dir).parent.resolve()
                candidate = (base_dir / relative_path).resolve()
                
                if candidate.exists():
                    local_path = str(candidate)
                else:
                    fallback_base = Path(download_dir).resolve()
                    fallback_candidate = (fallback_base / relative_path).resolve()
                    if fallback_candidate.exists():
                        local_path = str(fallback_candidate)
                    else:
                        storage.close()
                        return jsonify({"error": "File not found on disk"}), 404
            
            # Security: Validate that resolved path is within expected directory tree
            resolved_path = Path(local_path).resolve()
            data_dir = Path(download_dir).parent.resolve()
            try:
                resolved_path.relative_to(data_dir)
            except ValueError:
                logger.warning(
                    "Security: Attempted to delete file outside data directory. "
                    "Path: '%s', Data dir: '%s'",
                    resolved_path,
                    data_dir
                )
                storage.close()
                return jsonify({"error": "Invalid file path"}), 403
            
            # Delete physical file
            if os.path.exists(local_path):
                os.unlink(local_path)
                logger.info("Deleted file: %s", local_path)
            
            # Update database record to clear local_path using abstraction method
            storage.clear_local_path(url)
            
            storage.close()
            
            return jsonify({"success": True, "message": "File deleted successfully"})
        except Exception as e:
            logger.exception("Error deleting file")
            return jsonify({"error": str(e)}), 500
    
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
    
    app = create_app()
    logger.info("Starting web server on %s:%d", host, port)
    app.run(host=host, port=port, debug=debug)

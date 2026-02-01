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
    
    # Convert to absolute paths to handle relative imports
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
            
            # Get total files - using direct SQL for now
            # TODO: Consider adding get_file_count() method to Storage class
            cur = storage._conn.execute("SELECT COUNT(*) FROM files WHERE local_path IS NOT NULL AND local_path != ''")
            total_files = cur.fetchone()[0]
            
            # Get cataloged files
            cur = storage._conn.execute("SELECT COUNT(*) FROM catalog_items WHERE status = 'ok'")
            cataloged_files = cur.fetchone()[0]
            
            # Get unique sources
            cur = storage._conn.execute("SELECT COUNT(DISTINCT source_site) FROM files")
            total_sources = cur.fetchone()[0]
            
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
            
            # Validate order_by
            allowed_order_by = ['id', 'url', 'title', 'source_site', 'bytes', 'last_seen', 'crawl_time']
            if order_by not in allowed_order_by:
                order_by = 'last_seen'
            
            # Validate order_dir to prevent SQL injection
            if order_dir.lower() not in ['asc', 'desc']:
                order_dir = 'desc'
            
            # Build query
            filters = ["f.local_path IS NOT NULL AND f.local_path != ''"]
            params = []
            
            if query:
                filters.append("(LOWER(f.title) LIKE ? OR LOWER(f.original_filename) LIKE ? OR LOWER(f.url) LIKE ?)")
                search_term = f"%{query.lower()}%"
                params.extend([search_term, search_term, search_term])
            
            if source:
                filters.append("LOWER(f.source_site) LIKE ?")
                params.append(f"%{source.lower()}%")
            
            if category:
                filters.append("c.category = ?")
                params.append(category)
            
            where_clause = " AND ".join(filters)
            
            # Join with catalog_items if filtering by category
            join_clause = ""
            if category:
                join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*)
                FROM files f
                {join_clause}
                WHERE {where_clause}
            """
            cur = storage._conn.execute(count_query, tuple(params))
            total = cur.fetchone()[0]
            
            # Get files with catalog data
            order_clause = f"f.{order_by} {order_dir.upper()}"
            query_sql = f"""
                SELECT f.url, f.sha256, f.title, f.source_site, f.source_page_url,
                       f.original_filename, f.local_path, f.bytes, f.content_type,
                       f.last_modified, f.etag, f.published_time, f.first_seen,
                       f.last_seen, f.crawl_time,
                       c.category, c.summary, c.keywords
                FROM files f
                LEFT JOIN catalog_items c ON c.file_url = f.url
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cur = storage._conn.execute(query_sql, tuple(params))
            
            files = []
            for row in cur.fetchall():
                file_dict = {
                    "url": row[0],
                    "sha256": row[1],
                    "title": row[2],
                    "source_site": row[3],
                    "source_page_url": row[4],
                    "original_filename": row[5],
                    "local_path": row[6],
                    "bytes": row[7],
                    "content_type": row[8],
                    "last_modified": row[9],
                    "etag": row[10],
                    "published_time": row[11],
                    "first_seen": row[12],
                    "last_seen": row[13],
                    "crawl_time": row[14],
                    "category": row[15],
                    "summary": row[16],
                    "keywords": json.loads(row[17]) if row[17] else []
                }
                files.append(file_dict)
            
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
            cur = storage._conn.execute("""
                SELECT DISTINCT source_site 
                FROM files 
                WHERE source_site IS NOT NULL 
                ORDER BY source_site
            """)
            sources = [row[0] for row in cur.fetchall()]
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
                # Fallback to database
                storage = Storage(db_path)
                cur = storage._conn.execute("""
                    SELECT DISTINCT category 
                    FROM catalog_items 
                    WHERE category IS NOT NULL AND category != ''
                    ORDER BY category
                """)
                categories = [row[0] for row in cur.fetchall()]
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
            # Convert relative paths to absolute using data directory as base
            if not os.path.isabs(local_path):
                # Get the data directory (parent of download_dir which is data/files)
                data_dir = os.path.dirname(download_dir)
                local_path = os.path.join(data_dir, local_path)
            
            if not os.path.exists(local_path):
                return jsonify({"error": "File not found on disk"}), 404
            
            filename = file_record.get('original_filename') or os.path.basename(local_path)
            return send_file(local_path, as_attachment=True, download_name=filename)
        except Exception as e:
            logger.exception("Error downloading file")
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

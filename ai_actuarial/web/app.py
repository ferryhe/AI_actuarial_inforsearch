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
                global _task_history
                _task_history = [json.loads(line) for line in f if line.strip()]
                # Keep only last 100 entries in memory
                if len(_task_history) > 100:
                    _task_history = _task_history[-100:]
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
            
            # Join with catalog_items if filtering by category (or checking uncategorized)
            join_clause = ""
            if category:
                join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
                if category == '__uncategorized__':
                    filters.append("(c.category IS NULL OR c.category = '')")
                else:
                    # Precise matching for comma-separated categories
                    # Match exact string, OR start of CSV, OR end of CSV, OR middle of CSV
                    filters.append("(c.category = ? OR c.category LIKE ? OR c.category LIKE ? OR c.category LIKE ?)")
                    params.extend([category, f"{category},%", f"%,{category}", f"%,{category},%"])
            
            where_clause = " AND ".join(filters)
            
            # Get total count (using same joins/where)
            count_query = f"""
                SELECT COUNT(*)
                FROM files f
                {join_clause}
                WHERE {where_clause}
            """
            cur = storage._conn.execute(count_query, tuple(params))
            total = cur.fetchone()[0]
            
            # Get files with catalog data
            # Use LEFT JOIN always for the main query to ensure we get category data even if not filtering
            # Optimization: If we already filtered by category, we have the JOIN.
            # If not, we still need JOIN to return category columns.
            if not join_clause:
                join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            
            order_clause = f"f.{order_by} {order_dir.upper()}"
            query_sql = f"""
                SELECT f.url, f.sha256, f.title, f.source_site, f.source_page_url,
                       f.original_filename, f.local_path, f.bytes, f.content_type,
                       f.last_modified, f.etag, f.published_time, f.first_seen,
                       f.last_seen, f.crawl_time,
                       c.category, c.summary, c.keywords
                FROM files f
                {join_clause}
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
            # Re-load config to ensure fresh data
            config_path = os.getenv('CONFIG_PATH', 'config/sites.yaml')
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
                    'exclude_prefixes': site.get('exclude_prefixes', [])
                })
            return jsonify({"sites": sites})
        except Exception as e:
            logger.exception("Error getting sites config")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/sites/add", methods=["POST"])
    def api_config_sites_add():
        """Add a new site to configuration."""
        try:
            data = request.get_json()
            if not data or not data.get('name') or not data.get('url'):
                return jsonify({"error": "Name and URL are required"}), 400
            
            config_path = os.getenv('CONFIG_PATH', 'config/sites.yaml')
            
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
            
            config_data['sites'].append(new_site)
            
            # Save back
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)
            
            # Update global config copy
            global site_config
            site_config = config_data
            
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("Error adding site")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/sites/update", methods=["POST"])
    def api_config_sites_update():
        """Update an existing site in configuration."""
        try:
            data = request.get_json()
            if not data or not data.get('original_name') or not data.get('name'):
                return jsonify({"error": "Original name and new name are required"}), 400
            
            config_path = os.getenv('CONFIG_PATH', 'config/sites.yaml')
            
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

                    found = True
                    break
            
            if not found:
                return jsonify({"error": "Site not found"}), 404
                
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, sort_keys=False, allow_unicode=True)
                
            global site_config
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
            query = """
                SELECT f.url, f.sha256, f.title, f.source_site, f.source_page_url,
                       f.original_filename, f.local_path, f.bytes, f.content_type,
                       f.last_modified, f.etag, f.published_time, f.first_seen,
                       f.last_seen, f.crawl_time,
                       c.category, c.summary, c.keywords, c.status
                FROM files f
                LEFT JOIN catalog_items c ON c.file_url = f.url
                WHERE f.url = ?
            """
            cur = storage._conn.execute(query, (file_url,))
            row = cur.fetchone()
            storage.close()
            
            if not row:
                # Try simple matching if exact match failed (e.g. trailing slash issues)
                # or maybe the URL in DB is http but request is https or vice versa if proxied?
                # For now, just return 404
                return f"File not found: {file_url}", 404
            
            file_data = {
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
                "keywords": json.loads(row[17]) if row[17] else [],
                "catalog_status": row[18]
            }
            
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

        try:
            storage = Storage(db_path)
            result = None
            
            if collection_type == "url":
                urls = data.get("urls", [])
                user_agent = site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1')
                # Pass stop_check to Crawler
                crawler = Crawler(storage, download_dir, user_agent, stop_check=stop_check)
                collector = URLCollector(storage, crawler)
                
                config_obj = CollectionConfig(
                    name=data.get("name", "URL Collection"),
                    source_type="url",
                    check_database=data.get("check_database", True),
                    keywords=site_config['defaults'].get('keywords', []),
                    file_exts=site_config['defaults'].get('file_exts', []),
                    exclude_keywords=site_config['defaults'].get('exclude_keywords', []),
                    metadata={"urls": urls}
                )
                result = collector.collect(config_obj)
                
            elif collection_type == "file":
                directory_path = data.get("directory_path")
                extensions = data.get("extensions", [])
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
                result = collector.collect(config_obj)

            elif collection_type == "search":
                from ..search import brave_search
                
                query = data.get("query")
                site = data.get("site")
                engine = data.get("engine")
                count = int(data.get("count", 20))
                api_key = data.get("api_key")
                
                if site:
                    query = f"site:{site} {query}"
                
                logger.info(f"Performing web search: {query} using {engine}")
                urls = []
                
                if engine == "brave":
                    if not api_key:
                        api_key = os.getenv("BRAVE_API_KEY")
                    if not api_key:
                        raise ValueError("Brave API Key is missing")
                        
                    results = brave_search(query, count, api_key, site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'))
                    urls = [r.url for r in results]
                
                # If Google, implement or fail
                
                logger.info(f"Search found {len(urls)} URLs")
                
                if urls:
                    crawler = Crawler(
                        storage, 
                        download_dir, 
                        site_config['defaults'].get('user_agent', 'AI-Actuarial-InfoSearch/0.1'),
                        stop_check=stop_check
                    )
                    collector = URLCollector(storage, crawler)
                    config_obj = CollectionConfig(
                        name=f"Search: {query[:30]}...",
                        source_type="url",
                        check_database=True,
                        metadata={"urls": urls}
                    )
                    result = collector.collect(config_obj)

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
                result = collector.collect(config_obj)

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
                        "items_processed": result.items_found if result else 0,
                        "items_downloaded": result.items_downloaded if result else 0,
                        "errors": result.errors if result else []
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

    @app.route("/api/collections/run", methods=["POST"])
    def run_collection():
        """Start a collection operation."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            
            collection_type = data.get("type")
            valid_types = ["scheduled", "adhoc", "url", "file", "search"]
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
                # Seek to end and read backwards if needed, or just read all and slice
                # For simplicity, read all lines (assuming log isn't massive yet)
                # In production, use file seeking
                all_lines = f.readlines()
                lines = all_lines[-500:]
                
            return jsonify({"logs": "".join(lines)})
        except Exception as e:
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

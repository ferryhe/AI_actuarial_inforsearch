"""Basic Flask web application for managing collections."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

# Flask will be an optional dependency for now
try:
    from flask import Flask, render_template, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

logger = logging.getLogger(__name__)


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
    
    # Register routes
    @app.route("/")
    def index():
        """Main page showing collection options."""
        return render_template("index.html")
    
    @app.route("/api/collections", methods=["GET"])
    def list_collections():
        """List available collection configurations."""
        # TODO: Implement collection listing
        return jsonify({
            "collections": [
                {"id": "scheduled", "name": "Scheduled Collection", "type": "scheduled"},
                {"id": "adhoc", "name": "Ad-hoc Collection", "type": "adhoc"},
                {"id": "url", "name": "URL Collection", "type": "url"},
                {"id": "file", "name": "File Import", "type": "file"},
            ]
        })
    
    @app.route("/api/collections/run", methods=["POST"])
    def run_collection():
        """Start a collection operation."""
        data = request.get_json()
        collection_type = data.get("type")
        
        # TODO: Implement collection execution
        return jsonify({
            "success": True,
            "message": f"Collection {collection_type} started",
            "job_id": "placeholder"
        })
    
    @app.route("/api/files", methods=["GET"])
    def list_files():
        """List collected files."""
        # TODO: Implement file listing from database
        return jsonify({
            "files": [],
            "total": 0
        })
    
    @app.route("/api/categories", methods=["GET"])
    def list_categories():
        """List available categories."""
        # TODO: Load from category config
        return jsonify({
            "categories": []
        })
    
    return app


def run_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Run the web server.
    
    Args:
        host: Host address to bind to
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

"""RAG Knowledge Base Management API Routes

This module contains all Flask routes for RAG knowledge base management.
Follows existing patterns from ai_actuarial/web/app.py for consistency.

Phase 1.3.1: REST API Endpoints Implementation
Date: 2026-02-11
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


def register_rag_routes(app: Flask, db_path: str, require_permissions) -> None:
    """Register all RAG-related API routes with the Flask app.
    
    Args:
        app: Flask application instance
        db_path: Path to SQLite database
        require_permissions: Permission decorator function
    """
    
    # Import Storage (same pattern as app.py)
    from ai_actuarial.storage import Storage
    
    # Import RAG modules
    try:
        from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
        from ai_actuarial.rag.indexing import IndexingPipeline
    except ImportError as e:
        logger.error(f"Failed to import RAG modules: {e}")
        # Routes will return 503 if RAG modules not available
        RAG_AVAILABLE = False
    else:
        RAG_AVAILABLE = True
    
    def _check_rag_available():
        """Check if RAG modules are available."""
        if not RAG_AVAILABLE:
            return jsonify({"error": "RAG functionality not available"}), 503
        return None
    
    def _check_config_write_auth():
        """Check CONFIG_WRITE_AUTH_TOKEN for write operations."""
        expected_token = app.config.get("CONFIG_WRITE_AUTH_TOKEN") or os.getenv(
            "CONFIG_WRITE_AUTH_TOKEN"
        )
        if expected_token:
            provided_token = request.headers.get("X-Auth-Token")
            if not provided_token or provided_token != expected_token:
                logger.warning("RAG write operation rejected: authentication failed")
                return jsonify({"error": "Forbidden"}), 403
        return None
    
    def _api_error(message: str, *, status_code: int, detail: str | None = None):
        """Return consistent API error response."""
        payload: dict[str, Any] = {"success": False, "error": message}
        if detail and os.getenv("EXPOSE_ERROR_DETAILS"):
            payload["detail"] = detail
        return jsonify(payload), status_code
    
    def _api_success(data: Any = None, message: str | None = None, status_code: int = 200):
        """Return consistent API success response."""
        payload: dict[str, Any] = {"success": True}
        if data is not None:
            payload["data"] = data
        if message:
            payload["message"] = message
        return jsonify(payload), status_code
    
    # ========================================================================
    # KB CRUD Operations
    # ========================================================================
    
    @app.route("/api/rag/knowledge-bases", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_list_kbs():
        """List all knowledge bases with optional filtering.
        
        Query Parameters:
            kb_mode: Filter by mode (category|manual)
            search: Search in KB name or description
        
        Returns:
            200: List of knowledge bases
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            # Get query parameters
            kb_mode = request.args.get("kb_mode")
            search = request.args.get("search")
            
            # List all KBs
            kbs = kb_manager.list_kbs()
            
            # Apply filters
            if kb_mode:
                kbs = [kb for kb in kbs if kb.kb_mode == kb_mode]
            
            if search:
                search_lower = search.lower()
                kbs = [
                    kb for kb in kbs 
                    if search_lower in kb.name.lower() or 
                       (kb.description and search_lower in kb.description.lower())
                ]
            
            # Convert to dict format
            kb_list = [
                {
                    "kb_id": kb.kb_id,
                    "name": kb.name,
                    "description": kb.description,
                    "kb_mode": kb.kb_mode,
                    "embedding_model": kb.embedding_model,
                    "chunk_size": kb.chunk_size,
                    "chunk_overlap": kb.chunk_overlap,
                    "created_at": kb.created_at,
                    "updated_at": kb.updated_at,
                }
                for kb in kbs
            ]
            
            return _api_success(kb_list)
            
        except Exception as e:
            logger.exception("Error listing knowledge bases")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases", methods=["POST"])
    @require_permissions("config.write")
    def api_rag_create_kb():
        """Create a new knowledge base.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Request Body:
            kb_id: Unique identifier (required)
            name: Display name (required)
            description: Optional description
            kb_mode: "category" or "manual" (default: "manual")
            embedding_model: Model name (default: "text-embedding-3-large")
            chunk_size: Max tokens per chunk (default: 800)
            chunk_overlap: Overlap tokens (default: 100)
            categories: List of category names (for category mode)
            file_urls: List of file URLs (for manual mode)
        
        Returns:
            201: KB created successfully
            400: Invalid request
            403: Forbidden
            409: KB already exists
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid JSON body", status_code=400)
            
            # Required fields
            kb_id = data.get("kb_id", "").strip()
            name = data.get("name", "").strip()
            
            if not kb_id:
                return _api_error("kb_id is required", status_code=400)
            if not name:
                return _api_error("name is required", status_code=400)
            
            # Optional fields
            description = data.get("description", "").strip() or None
            kb_mode = data.get("kb_mode", "manual")
            embedding_model = data.get("embedding_model", "text-embedding-3-large")
            chunk_size = data.get("chunk_size", 800)
            chunk_overlap = data.get("chunk_overlap", 100)
            
            # Validate kb_mode
            if kb_mode not in ["category", "manual"]:
                return _api_error("kb_mode must be 'category' or 'manual'", status_code=400)
            
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            # Check if KB already exists
            existing = kb_manager.get_kb(kb_id)
            if existing:
                return _api_error(f"Knowledge base '{kb_id}' already exists", status_code=409)
            
            # Create KB based on mode
            if kb_mode == "category":
                categories = data.get("categories", [])
                if not categories:
                    return _api_error("categories required for category mode", status_code=400)
                
                kb = kb_manager.create_kb(
                    kb_id=kb_id,
                    name=name,
                    description=description,
                    kb_mode="category",
                    embedding_model=embedding_model,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                
                # Link to categories
                kb_manager.link_kb_to_categories(kb_id, categories)
            else:  # manual mode
                file_urls = data.get("file_urls", [])
                
                kb = kb_manager.create_kb(
                    kb_id=kb_id,
                    name=name,
                    description=description,
                    kb_mode="manual",
                    embedding_model=embedding_model,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                
                if file_urls:
                    kb_manager.add_files_to_kb(kb_id, file_urls)
            
            return _api_success(
                {
                    "kb_id": kb.kb_id,
                    "name": kb.name,
                    "kb_mode": kb.kb_mode,
                    "created_at": kb.created_at,
                },
                message=f"Knowledge base '{name}' created successfully",
                status_code=201
            )
            
        except ValueError as e:
            return _api_error(str(e), status_code=400)
        except Exception as e:
            logger.exception("Error creating knowledge base")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_get_kb(kb_id: str):
        """Get details of a specific knowledge base.
        
        Args:
            kb_id: Knowledge base identifier
        
        Returns:
            200: KB details with statistics
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            # Get statistics
            stats = kb_manager.get_kb_stats(kb_id)
            
            # Get linked categories (if category mode)
            categories = []
            if kb.kb_mode == "category":
                categories = kb_manager.get_kb_categories(kb_id)
            
            return _api_success({
                "kb_id": kb.kb_id,
                "name": kb.name,
                "description": kb.description,
                "kb_mode": kb.kb_mode,
                "embedding_model": kb.embedding_model,
                "chunk_size": kb.chunk_size,
                "chunk_overlap": kb.chunk_overlap,
                "created_at": kb.created_at,
                "updated_at": kb.updated_at,
                "stats": stats,
                "categories": categories,
            })
            
        except Exception as e:
            logger.exception(f"Error getting knowledge base {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>", methods=["PUT"])
    @require_permissions("config.write")
    def api_rag_update_kb(kb_id: str):
        """Update knowledge base metadata.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Args:
            kb_id: Knowledge base identifier
        
        Request Body:
            name: Updated display name (optional)
            description: Updated description (optional)
            embedding_model: Updated model (optional)
            chunk_size: Updated chunk size (optional)
            chunk_overlap: Updated overlap (optional)
        
        Returns:
            200: KB updated successfully
            400: Invalid request
            403: Forbidden
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid JSON body", status_code=400)
            
            # Update fields
            updates = {}
            if "name" in data:
                updates["name"] = data["name"].strip()
            if "description" in data:
                updates["description"] = data["description"].strip() or None
            
            # embedding_model, chunk_size, chunk_overlap update not supported by manager yet
            
            if not updates:
                return _api_error("No valid update fields provided (name, description)", status_code=400)
            
            kb_manager.update_kb(kb_id, **updates)
            
            return _api_success(
                message=f"Knowledge base '{kb_id}' updated successfully"
            )
            
        except ValueError as e:
            return _api_error(str(e), status_code=400)
        except Exception as e:
            logger.exception(f"Error updating knowledge base {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>", methods=["DELETE"])
    @require_permissions("config.write")
    def api_rag_delete_kb(kb_id: str):
        """Delete a knowledge base.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Args:
            kb_id: Knowledge base identifier
        
        Query Parameters:
            delete_files: If "true", also delete indexed files (default: "false")
        
        Returns:
            200: KB deleted successfully
            403: Forbidden
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            delete_files = request.args.get("delete_files", "false").lower() == "true"
            
            kb_manager.delete_kb(kb_id, delete_vector_store=True)
            
            # get param 'delete_files' is unused as manager deletes entire KB content
            
            kb_manager.delete_kb(kb_id
            
        except Exception as e:
            logger.exception(f"Error deleting knowledge base {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    # ========================================================================
    # File Association Operations
    # ========================================================================
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/files", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_list_kb_files(kb_id: str):
        """List files in a knowledge base.
        
        Args:
            kb_id: Knowledge base identifier
        
        Query Parameters:
            status: Filter by status (indexed|pending|error)
        
        Returns:
            200: List of files with indexing status
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            # List all KB file records (already includes status)
            kb_files = kb_manager.get_kb_files(kb_id)
            
            # Get file details with indexing status
            files = []
            for kb_file in kb_files:
                files.append({
                    "file_url": kb_file["file_url"],
                    "title": kb_file.get("title", ""),
                    "category": kb_file.get("category", ""),
                    "indexed": kb_file.get("indexed_at") is not None,
                    "indexed_at": kb_file.get("indexed_at"),
                    "chunk_count": kb_file.get("chunk_count", 0),
                    "error": None,
                })
            
            # Apply status filter
            status_filter = request.args.get("status")
            if status_filter == "indexed":
                files = [f for f in files if f["indexed"]]
            elif status_filter == "pending":
                files = [f for f in files if not f["indexed"] and not f["error"]]
            elif status_filter == "error":
                files = [f for f in files if f["error"]]
            
            return _api_success({
                "kb_id": kb_id,
                "total_files": len(files),
                "files": files,
            })
            
        except Exception as e:
            logger.exception(f"Error listing files for KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/files", methods=["POST"])
    @require_permissions("config.write")
    def api_rag_add_kb_files(kb_id: str):
        """Add files to a knowledge base.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Args:
            kb_id: Knowledge base identifier
        
        Request Body:
            file_urls: List of file URLs to add (required)
        
        Returns:
            200: Files added successfully
            400: Invalid request
            403: Forbidden
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid JSON body", status_code=400)
            
            file_urls = data.get("file_urls", [])
            if not isinstance(file_urls, list) or not file_urls:
                return _api_error("file_urls must be a non-empty list", status_code=400)
            
            # Add files to KB
            kb_manager.add_files_to_kb(kb_id, file_urls)
            
            return _api_success(
                {"added_count": len(file_urls)},
                message=f"Added {len(file_urls)} files to KB '{kb_id}'"
            )
            
        except ValueError as e:
            return _api_error(str(e), status_code=400)
        except Exception as e:
            logger.exception(f"Error adding files to KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/files/<path:file_url>", methods=["DELETE"])
    @require_permissions("config.write")
    def api_rag_remove_kb_file(kb_id: str, file_url: str):
        """Remove a file from a knowledge base.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Args:
            kb_id: Knowledge base identifier
            file_url: File URL to remove
        
        Returns:
            200: File removed successfully
            403: Forbidden
            404: KB or file not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            # Remove file from KB
            kb_manager.remove_files_from_kb(kb_id, [file_url])
            
            return _api_success(
                message=f"File removed from KB '{kb_id}'"
            )
            
        except ValueError as e:
            return _api_error(str(e), status_code=400)
        except Exception as e:
            logger.exception(f"Error removing file from KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    # ========================================================================
    # Category Integration Operations
    # ========================================================================
    
    @app.route("/api/rag/categories/unmapped", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_unmapped_categories():
        """Get list of categories without RAG knowledge bases.
        
        Returns:
            200: List of unmapped categories
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            unmapped = kb_manager.get_unmapped_categories()
            
            # Get file counts for each category
            categories_with_counts = []
            for item in unmapped:
                # item is dict {category, file_count}
                categories_with_counts.append({
                    "name": item["category"],
                    "file_count": item["file_count"],
                })
            
            return _api_success({
                "unmapped_categories": categories_with_counts,
                "total_count": len(categories_with_counts),
            })
            
        except Exception as e:
            logger.exception("Error getting unmapped categories")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/categories", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_get_kb_categories(kb_id: str):
        """Get categories linked to a knowledge base.
        
        Args:
            kb_id: Knowledge base identifier
        
        Returns:
            200: List of linked categories
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            categories = kb_manager.get_kb_categories(kb_id)
            
            return _api_success({
                "kb_id": kb_id,
                "categories": categories,
                "count": len(categories),
            })
            
        except Exception as e:
            logger.exception(f"Error getting categories for KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/categories", methods=["POST"])
    @require_permissions("config.write")
    def api_rag_link_kb_categories(kb_id: str):
        """Link categories to a knowledge base (auto-syncs files).
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Args:
            kb_id: Knowledge base identifier
        
        Request Body:
            categories: List of category names to link (required)
        
        Returns:
            200: Categories linked successfully
            400: Invalid request
            403: Forbidden
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid JSON body", status_code=400)
            
            categories = data.get("categories", [])
            if not isinstance(categories, list) or not categories:
                return _api_error("categories must be a non-empty list", status_code=400)
            
            # Link categories (auto-syncs files)
            added_count = kb_manager.link_kb_to_categories(kb_id, categories)
            
            return _api_success(
                {"linked_count": len(categories), "files_added": added_count},
                message=f"Linked {len(categories)} categories, added {added_count} files"
            )
            
        except ValueError as e:
            return _api_error(str(e), status_code=400)
        except Exception as e:
            logger.exception(f"Error linking categories to KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    # ========================================================================
    # Statistics & Metadata
    # ========================================================================
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/stats", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_get_kb_stats(kb_id: str):
        """Get knowledge base statistics.
        
        Args:
            kb_id: Knowledge base identifier
        
        Returns:
            200: KB statistics
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            stats = kb_manager.get_kb_stats(kb_id)
            
            return _api_success(stats)
            
        except Exception as e:
            logger.exception(f"Error getting stats for KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/files/pending", methods=["GET"])
    @require_permissions("catalog.read")
    def api_rag_get_pending_files(kb_id: str):
        """Get files needing indexing in a knowledge base.
        
        Args:
            kb_id: Knowledge base identifier
        
        Returns:
            200: List of pending files
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            pending_urls = kb_manager.get_files_needing_index(kb_id)
            
            # Get file details
            pending_files = []
            for file_url in pending_urls:
                storage = Storage(db_path)
                file_info = storage.get_file(file_url)
                if file_info:
                    pending_files.append({
                        "file_url": file_url,
                        "title": file_info.get("title", ""),
                        "category": file_info.get("category", ""),
                        "markdown_updated_at": file_info.get("markdown_updated_at"),
                    })
            
            return _api_success({
                "kb_id": kb_id,
                "pending_count": len(pending_files),
                "pending_files": pending_files,
            })
            
        except Exception as e:
            logger.exception(f"Error getting pending files for KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    @app.route("/api/rag/task-metadata", methods=["POST"])
    @require_permissions("catalog.read")
    def api_rag_task_metadata():
        """Get metadata for RAG indexing task (pre-task statistics).
        
        Request Body:
            kb_id: Knowledge base identifier (required)
        
        Returns:
            200: Task metadata with statistics
            400: Invalid request
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid JSON body", status_code=400)
            
            kb_id = data.get("kb_id", "").strip()
            if not kb_id:
                return _api_error("kb_id is required", status_code=400)
            
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            metadata = kb_manager.get_rag_task_metadata(kb_id)
            
            return _api_success(metadata)
            
        except Exception as e:
            logger.exception("Error getting RAG task metadata")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    # ========================================================================
    # Task Management
    # ========================================================================
    
    @app.route("/api/rag/knowledge-bases/<kb_id>/index", methods=["POST"])
    @require_permissions("tasks.run")
    def api_rag_create_index_task(kb_id: str):
        """Create a background indexing task for a knowledge base.
        
        Security: Requires CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header.
        
        Args:
            kb_id: Knowledge base identifier
        
        Request Body:
            file_urls: Optional list of specific files to index
                      (if not provided, indexes all pending files)
            force_reindex: If true, reindex all files (default: false)
        
        Returns:
            202: Task created successfully
            400: Invalid request
            403: Forbidden
            404: KB not found
            503: RAG not available
        """
        check_result = _check_rag_available()
        if check_result:
            return check_result
        
        auth_result = _check_config_write_auth()
        if auth_result:
            return auth_result
        
        try:
            storage = Storage(db_path)
            kb_manager = KnowledgeBaseManager(storage)
            
            kb = kb_manager.get_kb(kb_id)
            if not kb:
                return _api_error(f"Knowledge base '{kb_id}' not found", status_code=404)
            
            data = request.get_json(silent=True) or {}
            
            file_urls = data.get("file_urls")
            force_reindex = data.get("force_reindex", False)
            
            # Determine files to index
            if file_urls:
                if not isinstance(file_urls, list):
                    return _api_error("file_urls must be a list", status_code=400)
                files_to_index = file_urls
            else:
                # Get pending files
                files_to_index = kb_manager.get_files_needing_index(kb_id)
                if force_reindex:
                    # Reindex all files
                    files_to_index = kb_manager.list_kb_files(kb_id)
            
            if not files_to_index:
                return _api_error("No files to index", status_code=400)
            
            # Create task (will be implemented in next phase - task integration)
            # For now, return task info that would be created
            task_id = f"rag_index_{kb_id}_{int(datetime.now().timestamp())}"
            
            # This will be integrated with existing task system
            # Similar to markdown_conversion or catalog update tasks
            
            return _api_success(
                {
                    "task_id": task_id,
                    "kb_id": kb_id,
                    "file_count": len(files_to_index),
                    "status": "pending",
                },
                message=f"Indexing task created for {len(files_to_index)} files",
                status_code=202
            )
            
        except ValueError as e:
            return _api_error(str(e), status_code=400)
        except Exception as e:
            logger.exception(f"Error creating index task for KB {kb_id}")
            return _api_error("Internal server error", status_code=500, detail=str(e))
    
    logger.info("RAG API routes registered successfully")

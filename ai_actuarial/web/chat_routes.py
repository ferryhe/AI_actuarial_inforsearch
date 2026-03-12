"""Chat API routes for AI chatbot interface."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

from flask import Flask, jsonify, request, render_template, g

logger = logging.getLogger(__name__)


def register_chat_routes(
    app: Flask,
    db_path: str,
    require_permissions: Callable,
) -> None:
    """
    Register chat-related API routes.
    
    Args:
        app: Flask application instance
        db_path: Path to database file
        require_permissions: Decorator for permission checks
    """
    from ai_actuarial.storage import Storage
    
    # Check if chatbot functionality is available
    try:
        from ai_actuarial.chatbot import retrieval as chatbot_retrieval
        from ai_actuarial.chatbot import llm as chatbot_llm
        from ai_actuarial.chatbot import conversation as chatbot_conversation
        from ai_actuarial.chatbot import router as chatbot_router
        from ai_actuarial.chatbot import config as chatbot_config
        from ai_actuarial.chatbot import exceptions as chatbot_exceptions
        from ai_actuarial.rag import knowledge_base as rag_knowledge_base
        chatbot_available = True
    except ImportError as e:
        logger.warning(f"Chatbot functionality not available: {e}")
        chatbot_available = False
    
    def _api_error(message: str, *, status_code: int, detail: str | None = None):
        """Return API error response."""
        payload: dict[str, Any] = {"success": False, "error": message}
        if detail and os.getenv("EXPOSE_ERROR_DETAILS"):
            payload["detail"] = detail
        return jsonify(payload), status_code
    
    def _api_success(data: Any = None, message: str | None = None, status_code: int = 200):
        """Return API success response."""
        payload: dict[str, Any] = {"success": True}
        if data is not None:
            payload["data"] = data
        if message:
            payload["message"] = message
        return jsonify(payload), status_code
    
    def _check_chatbot_available():
        """Check if chatbot functionality is available."""
        if not chatbot_available:
            return _api_error("Chatbot functionality not available", status_code=503)
        return None

    def _build_file_links(raw_file_url: str, *, return_to: str = "/chat") -> dict[str, str]:
        """Build stable links for file detail and file preview."""
        source_url = str(raw_file_url or "").strip()
        if not source_url:
            return {
                "source_url": "",
                "file_detail_url": "",
                "file_preview_url": "",
            }

        if source_url.startswith("/file/"):
            return {
                "source_url": source_url,
                "file_detail_url": source_url,
                "file_preview_url": "",
            }
        if source_url.startswith("/file_preview"):
            return {
                "source_url": source_url,
                "file_detail_url": "",
                "file_preview_url": source_url,
            }
        if source_url.startswith("/database/"):
            return {
                "source_url": source_url,
                "file_detail_url": source_url,
                "file_preview_url": "",
            }

        encoded_source = quote(source_url, safe="")
        return {
            "source_url": source_url,
            "file_detail_url": f"/file/{encoded_source}?return_to={quote(return_to, safe='')}",
            "file_preview_url": f"/file_preview?file_url={encoded_source}",
        }
    
    def _get_user_id() -> str:
        """Get user ID from session or request."""
        from flask import session, g

        # Authenticated token from app auth middleware.
        token = getattr(g, "_auth_token", None) or {}
        subject = str(token.get("subject") or "").strip()
        if subject:
            return f"user:{subject}"

        token_id = token.get("id")
        if token_id is not None:
            return f"token:{token_id}"

        # Backward-compatible session keys (if present).
        legacy_subject = str(session.get("auth_subject") or "").strip()
        if legacy_subject:
            return f"user:{legacy_subject}"

        # Anonymous users should be isolated per browser session.
        guest_id = str(session.get("guest_chat_user_id") or "").strip()
        if not guest_id:
            guest_id = f"guest:{uuid.uuid4().hex[:16]}"
            session["guest_chat_user_id"] = guest_id
        return guest_id
    
    # ========================================================================
    # Chat Page Route
    # ========================================================================
    
    @app.route("/chat")
    @require_permissions("chat.view")
    def chat():
        """Render chat interface page."""
        error = _check_chatbot_available()
        if error:
            return render_template("error.html", 
                                 error="Chatbot functionality is not available",
                                 detail="Please contact your administrator"), 503
        
        return render_template("chat.html")
    
    # ========================================================================
    # Chat API Routes
    # ========================================================================
    
    @app.route("/api/chat/query", methods=["POST"])
    @require_permissions("chat.query")
    def api_chat_query():
        """
        Submit a chat query and get response.
        
        Request JSON:
            {
                "conversation_id": "conv_123" | null,  // null for new conversation
                "message": "What is Solvency II?",
                "kb_ids": ["kb1", "kb2"] | "auto" | null,
                "mode": "expert" | "summary" | "tutorial" | "comparison",
                "stream": false
            }
        
        Response JSON:
            {
                "success": true,
                "data": {
                    "conversation_id": "conv_123",
                    "message_id": "msg_456",
                    "response": "Solvency II is...",
                    "citations": [
                        {
                            "filename": "regulation_2023.pdf",
                            "kb_id": "kb1",
                            "kb_name": "General",
                            "chunk_id": "chunk_789",
                            "similarity_score": 0.89,
                            "file_url": "/database/regulation_2023.pdf"
                        }
                    ],
                    "metadata": {
                        "retrieval_time_ms": 450,
                        "generation_time_ms": 1200,
                        "model": "gpt-4",
                        "mode": "expert"
                    }
                }
            }
        """
        error = _check_chatbot_available()
        if error:
            return error

        # --- AI Chat quota enforcement ---
        try:
            from ai_actuarial.web.app import (
                _AI_CHAT_QUOTA,
                _get_client_ip,
                _get_today_date,
            )
            from ai_actuarial.storage import Storage as _Storage
            _token = getattr(g, "_auth_token", None)
            _today = _get_today_date()
            _ip = _get_client_ip()
            _email_user = (_token or {}).get("_email_user") if _token else None
            _role = ((_token or {}).get("group_name") or "anonymous").lower()
            _limit = _AI_CHAT_QUOTA.get(_role, _AI_CHAT_QUOTA.get("anonymous", 1))

            _quota_storage = _Storage(db_path)
            try:
                if _email_user:
                    _allowed, _count = _quota_storage.check_and_increment_ai_chat_quota(
                        _today, _limit, user_id=_email_user["id"]
                    )
                else:
                    _allowed, _count = _quota_storage.check_and_increment_ai_chat_quota(
                        _today, _limit, ip_address=_ip
                    )
            finally:
                try:
                    _quota_storage.close()
                except Exception:
                    pass

            if not _allowed:
                _upgrade_hint = (
                    "Please register to get more queries." if _role == "anonymous"
                    else "Please upgrade to Premium for higher limits." if _role == "registered"
                    else "Daily quota exceeded."
                )
                return _api_error(
                    f"Daily AI chat limit reached ({_limit}/day). {_upgrade_hint}",
                    status_code=429,
                )
        except Exception:
            logger.exception(
                "Quota check failed; blocking request to prevent metered resource bypass"
            )
            return _api_error("Service temporarily unavailable; please try again.", status_code=503)
        # --- End quota enforcement ---

        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid or missing JSON body", status_code=400)
            
            # Extract parameters
            message = data.get("message", "").strip()
            if not message:
                return _api_error("Message is required", status_code=400)
            
            conversation_id = data.get("conversation_id")
            kb_ids = data.get("kb_ids")
            mode = data.get("mode", "expert")
            stream = data.get("stream", False)
            
            # Document explanation parameters
            document_content = data.get("document_content", "").strip()
            document_filename = data.get("document_filename", "document").strip()
            document_file_url = data.get("document_file_url", "").strip()
            document_sources = []
            raw_document_sources = data.get("document_sources")
            if isinstance(raw_document_sources, list):
                for idx, item in enumerate(raw_document_sources, start=1):
                    if not isinstance(item, dict):
                        continue
                    source_content = str(item.get("content", "")).strip()
                    if not source_content:
                        continue
                    source_filename = (
                        str(item.get("filename") or item.get("title") or f"document_{idx}").strip()
                        or f"document_{idx}"
                    )
                    source_file_url = str(item.get("file_url", "")).strip()
                    document_sources.append(
                        {
                            "content": source_content,
                            "filename": source_filename,
                            "file_url": source_file_url,
                        }
                    )
            
            # Validate mode
            valid_modes = ["expert", "summary", "tutorial", "comparison"]
            if mode not in valid_modes:
                return _api_error(
                    f"Invalid mode. Must be one of: {', '.join(valid_modes)}", 
                    status_code=400
                )
            
            # Get user ID
            user_id = _get_user_id()
            
            # Initialize components
            storage = Storage(db_path)
            config = chatbot_config.ChatbotConfig.from_config(
                storage=storage,
                default_mode=mode,
            )
            
            try:
                retriever = chatbot_retrieval.RAGRetriever(storage, config)
                llm_client = chatbot_llm.LLMClient(config)
                conv_manager = chatbot_conversation.ConversationManager(storage, config)
                
                # Handle conversation
                if conversation_id:
                    # Verify conversation exists and belongs to user
                    conv = conv_manager.get_conversation(conversation_id)
                    if not conv:
                        return _api_error("Conversation not found", status_code=404)
                    if conv.get("user_id") != user_id:
                        return _api_error("Access denied", status_code=403)
                else:
                    # Create new conversation
                    # Determine primary KB
                    primary_kb = None
                    if kb_ids and isinstance(kb_ids, list) and len(kb_ids) > 0:
                        primary_kb = kb_ids[0]
                    elif kb_ids and isinstance(kb_ids, str) and kb_ids != "auto":
                        primary_kb = kb_ids
                    
                    conversation_id = conv_manager.create_conversation(
                        user_id=user_id,
                        kb_id=primary_kb,
                        mode=mode,
                        metadata={
                            "kb_ids": kb_ids,
                            "mode": mode
                        }
                    )
                
                # Add user message
                start_time = time.time()
                user_msg_id = conv_manager.add_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=message
                )
                
                # Retrieve relevant chunks
                retrieval_start = time.time()
                
                # If document content is provided, use it instead of RAG retrieval
                if document_content:
                    # Truncate each document if too long (max ~15K characters, ~4K tokens).
                    MAX_DOC_LENGTH = 15000
                    chunks = []
                    if document_sources:
                        for idx, source in enumerate(document_sources, start=1):
                            source_content = source["content"]
                            truncated = False
                            if len(source_content) > MAX_DOC_LENGTH:
                                source_content = source_content[:MAX_DOC_LENGTH]
                                truncated = True
                            chunks.append({
                                "content": source_content,
                                "metadata": {
                                    "filename": source["filename"],
                                    "file_url": source["file_url"],
                                    "kb_id": "document_explanation",
                                    "kb_name": "Full Document",
                                    "chunk_id": f"full_document_{idx}",
                                    "similarity_score": 1.0,
                                    "is_full_document": True,
                                    "truncated": truncated,
                                }
                            })
                    else:
                        truncated = False
                        if len(document_content) > MAX_DOC_LENGTH:
                            document_content = document_content[:MAX_DOC_LENGTH]
                            truncated = True

                        chunks = [{
                            "content": document_content,
                            "metadata": {
                                "filename": document_filename,
                                "file_url": document_file_url,
                                "kb_id": "document_explanation",
                                "kb_name": "Full Document",
                                "chunk_id": "full_document",
                                "similarity_score": 1.0,
                                "is_full_document": True,
                                "truncated": truncated
                            }
                        }]
                    no_results = False
                    used_threshold = 1.0
                else:
                    # Normal RAG retrieval
                    # Handle KB selection
                    if kb_ids == "auto":
                        # Use query router for automatic KB selection
                        router = chatbot_router.QueryRouter(storage, config)
                        kb_ids = router.select_kb(message)
                    elif kb_ids is None or kb_ids == "all":
                        # Query all available KBs
                        kb_ids = None
                    elif isinstance(kb_ids, str):
                        # Single KB ID
                        kb_ids = [kb_ids]
                    
                    # Retrieve chunks
                    no_results = False
                    used_threshold = config.similarity_threshold
                    try:
                        chunks = retriever.retrieve(
                            query=message,
                            kb_ids=kb_ids,
                            top_k=config.top_k,
                            threshold=used_threshold
                        )
                    except chatbot_exceptions.NoResultsException:
                        # Retry once with a lower threshold before giving up.
                        fallback_threshold = 0.1
                        if used_threshold > fallback_threshold:
                            try:
                                chunks = retriever.retrieve(
                                    query=message,
                                    kb_ids=kb_ids,
                                    top_k=config.top_k,
                                    threshold=fallback_threshold,
                                )
                                used_threshold = fallback_threshold
                                logger.info(
                                    "No hits at threshold %.3f; recovered with fallback threshold %.3f (conversation %s)",
                                    config.similarity_threshold,
                                    fallback_threshold,
                                    conversation_id,
                                )
                            except chatbot_exceptions.NoResultsException:
                                chunks = []
                                no_results = True
                        else:
                            chunks = []
                            no_results = True

                        if no_results:
                            # No relevant chunks is a valid user-facing outcome, not a server error.
                            logger.info(
                                "No retrieval results for conversation %s (query=%s...)",
                                conversation_id,
                                message[:80],
                            )
                
                retrieval_time_ms = int((time.time() - retrieval_start) * 1000)
                
                # Get conversation history for context
                history = conv_manager.get_messages(conversation_id, limit=10)
                
                # Generate response
                if no_results:
                    response_text = (
                        "I don't have enough information in the knowledge base to answer "
                        "this question. Please try a different knowledge base, ask a more "
                        "specific question, or lower the retrieval threshold."
                    )
                    generation_time_ms = 0
                else:
                    generation_start = time.time()
                    # Load chatbot prompt overrides from config
                    _chatbot_prompts_override: dict | None = None
                    try:
                        from config.yaml_config import load_yaml_config
                        _chatbot_prompts_override = (
                            load_yaml_config()
                            .get("ai_config", {})
                            .get("chatbot", {})
                            .get("prompts") or None
                        )
                    except Exception:
                        pass
                    response_text = llm_client.generate_response(
                        query=message,
                        chunks=chunks,
                        mode=mode,
                        conversation_history=history[:-1],  # Exclude the message we just added
                        prompts_override=_chatbot_prompts_override,
                    )
                    generation_time_ms = int((time.time() - generation_start) * 1000)
                
                # Extract citations from chunks
                citations = []
                seen_files = set()
                retrieved_blocks = []
                for chunk in chunks:
                    metadata = chunk.get("metadata", {})
                    filename = metadata.get("filename", "unknown")
                    score = float(metadata.get("similarity_score", 0.0) or 0.0)
                    links = _build_file_links(metadata.get("file_url", ""))
                    chunk_text = str(chunk.get("content", "") or "").strip()
                    quote_text = chunk_text[:280].rstrip()
                    if chunk_text and len(chunk_text) > 280:
                        quote_text += "..."

                    retrieved_blocks.append({
                        "filename": filename,
                        "kb_id": metadata.get("kb_id", ""),
                        "kb_name": metadata.get("kb_name", ""),
                        "chunk_id": metadata.get("chunk_id", ""),
                        "similarity_score": score,
                        "content": chunk.get("content", ""),
                        "source_url": links["source_url"],
                        "file_detail_url": links["file_detail_url"],
                        "file_preview_url": links["file_preview_url"],
                        "quote": quote_text,
                    })
                    
                    # Avoid duplicate citations
                    citation_key = links["source_url"] or filename
                    if citation_key in seen_files:
                        continue
                    seen_files.add(citation_key)
                    
                    citations.append({
                        "filename": filename,
                        "kb_id": metadata.get("kb_id", ""),
                        "kb_name": metadata.get("kb_name", ""),
                        "chunk_id": metadata.get("chunk_id", ""),
                        "similarity_score": score,
                        "source_url": links["source_url"],
                        # Keep legacy key for old frontend behavior.
                        "file_url": links["file_detail_url"],
                        "file_detail_url": links["file_detail_url"],
                        "file_preview_url": links["file_preview_url"],
                        "quote": quote_text,
                    })
                
                # Add assistant message
                assistant_msg_id = conv_manager.add_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response_text,
                    citations=citations,
                    metadata={
                        "model": config.model,
                        "mode": mode,
                        "retrieval_time_ms": retrieval_time_ms,
                        "generation_time_ms": generation_time_ms,
                        "num_chunks": len(chunks),
                        "no_results": no_results,
                        "used_threshold": used_threshold,
                        "retrieved_blocks": retrieved_blocks,
                    }
                )
                
                # Update conversation title if this is the first message
                if len(history) == 1:  # Only user message exists
                    # Generate title from first query (simple truncation for now)
                    title = message[:50] + ("..." if len(message) > 50 else "")
                    conv_manager.update_conversation_title(conversation_id, title)
                
                # Return response
                return _api_success({
                    "conversation_id": conversation_id,
                    "message_id": assistant_msg_id,
                    "response": response_text,
                    "citations": citations,
                    "retrieved_blocks": retrieved_blocks,
                    "metadata": {
                        "retrieval_time_ms": retrieval_time_ms,
                        "generation_time_ms": generation_time_ms,
                        "model": config.model,
                        "mode": mode,
                        "num_chunks": len(chunks),
                        "no_results": no_results,
                        "used_threshold": used_threshold,
                    }
                })
                
            finally:
                storage.close()
        
        except chatbot_exceptions.EmbeddingConfigurationMismatchException as e:
            logger.warning(
                "Chat query blocked by embedding mismatch for KB %s: current=%s/%s/%s index=%s/%s/%s",
                e.kb_id,
                e.current_provider,
                e.current_model,
                e.current_dimension,
                e.index_provider,
                e.index_model,
                e.index_dimension,
            )
            return jsonify(
                {
                    "success": False,
                    "code": "KB_EMBEDDING_MISMATCH",
                    "error": "Knowledge base index is incompatible with the current embedding configuration. Rebuild the index first.",
                    "data": {
                        "kb_id": e.kb_id,
                        "current_embedding": {
                            "provider": e.current_provider,
                            "model": e.current_model,
                            "dimension": e.current_dimension,
                        },
                        "index_embedding": {
                            "provider": e.index_provider,
                            "model": e.index_model,
                            "dimension": e.index_dimension,
                        },
                        "needs_reindex": e.needs_reindex,
                    },
                }
            ), 409
        except Exception as e:
            logger.exception("Error processing chat query")
            return _api_error(
                "Internal server error",
                status_code=500,
                detail=str(e)
            )
    
    @app.route("/api/chat/conversations", methods=["GET", "POST"])
    @require_permissions("chat.conversations")
    def api_chat_conversations():
        """
        GET: List user conversations
        POST: Create new conversation
        """
        error = _check_chatbot_available()
        if error:
            return error
        
        user_id = _get_user_id()
        
        if request.method == "GET":
            try:
                storage = Storage(db_path)
                config = chatbot_config.ChatbotConfig.from_config(storage=storage)
                
                try:
                    conv_manager = chatbot_conversation.ConversationManager(storage, config)
                    conversations = conv_manager.list_conversations(user_id)
                    
                    return _api_success({"conversations": conversations})
                    
                finally:
                    storage.close()
            
            except Exception as e:
                logger.exception("Error listing conversations")
                return _api_error(
                    "Internal server error",
                    status_code=500,
                    detail=str(e)
                )
        
        elif request.method == "POST":
            try:
                data = request.get_json(silent=True) or {}
                
                kb_id = data.get("kb_id")
                mode = data.get("mode", "expert")
                
                storage = Storage(db_path)
                config = chatbot_config.ChatbotConfig.from_config(storage=storage)
                
                try:
                    conv_manager = chatbot_conversation.ConversationManager(storage, config)
                    
                    conversation_id = conv_manager.create_conversation(
                        user_id=user_id,
                        kb_id=kb_id,
                        mode=mode,
                        metadata=data.get("metadata", {})
                    )
                    
                    return _api_success({
                        "conversation_id": conversation_id
                    }, status_code=201)
                    
                finally:
                    storage.close()
            
            except Exception as e:
                logger.exception("Error creating conversation")
                return _api_error(
                    "Internal server error",
                    status_code=500,
                    detail=str(e)
                )
    
    @app.route("/api/chat/conversations/<conversation_id>", methods=["GET", "DELETE"])
    @require_permissions("chat.conversations")
    def api_chat_conversation_detail(conversation_id: str):
        """
        GET: Get conversation history
        DELETE: Delete conversation
        """
        error = _check_chatbot_available()
        if error:
            return error
        
        user_id = _get_user_id()
        
        try:
            storage = Storage(db_path)
            config = chatbot_config.ChatbotConfig.from_config(storage=storage)
            
            try:
                conv_manager = chatbot_conversation.ConversationManager(storage, config)
                
                # Verify conversation exists and belongs to user
                conv = conv_manager.get_conversation(conversation_id)
                if not conv:
                    return _api_error("Conversation not found", status_code=404)
                if conv.get("user_id") != user_id:
                    return _api_error("Access denied", status_code=403)
                
                if request.method == "GET":
                    # Get messages
                    messages = conv_manager.get_messages(conversation_id, include_metadata=True)
                    
                    return _api_success({
                        "conversation": conv,
                        "messages": messages
                    })
                
                elif request.method == "DELETE":
                    # Delete conversation
                    conv_manager.delete_conversation(conversation_id)
                    
                    return _api_success(message="Conversation deleted")
            
            finally:
                storage.close()
        
        except Exception as e:
            logger.exception(f"Error handling conversation {conversation_id}")
            return _api_error(
                "Internal server error",
                status_code=500,
                detail=str(e)
            )
    
    @app.route("/api/chat/available-documents", methods=["GET"])
    @require_permissions("chat.view")
    def api_chat_available_documents():
        """
        Get list of documents that have markdown content available.
        These documents can be explained via the document explorer.
        
        Query parameters:
            category: Filter by category (optional)
            keywords: Comma-separated keywords to search (optional)
        
        Response JSON:
            {
                "success": true,
                "data": {
                    "documents": [
                        {
                            "file_url": "/database/...",
                            "filename": "document.pdf",
                            "title": "Document Title",
                            "category": "SOA",
                            "keywords": ["keyword1", "keyword2"]
                        }
                    ]
                }
            }
        """
        error = _check_chatbot_available()
        if error:
            return error
        
        try:
            storage = Storage(db_path)
            
            try:
                # Get query parameters
                category_filter = request.args.get("category", "").strip()
                keywords_filter = request.args.get("keywords", "").strip()
                
                # Query files with markdown content
                query = """
                    SELECT DISTINCT 
                        f.url,
                        f.original_filename,
                        f.title,
                        c.category,
                        c.keywords
                    FROM files f
                    INNER JOIN catalog_items c ON f.url = c.file_url
                    WHERE c.markdown_content IS NOT NULL
                        AND c.markdown_content != ''
                """
                params = []
                
                # Apply category filter
                if category_filter:
                    if category_filter == '__uncategorized__':
                        # Show only documents without a category
                        query += " AND (c.category IS NULL OR c.category = '')"
                    else:
                        # Use LIKE for partial match (supports multiple categories per document)
                        query += " AND c.category LIKE ?"
                        params.append(f"%{category_filter}%")
                
                # Apply keywords filter
                if keywords_filter:
                    keyword_list = [k.strip() for k in keywords_filter.split(",") if k.strip()]
                    if keyword_list:
                        # Search in title, filename, or keywords
                        keyword_conditions = []
                        for kw in keyword_list:
                            keyword_conditions.append("(f.title LIKE ? OR f.original_filename LIKE ? OR c.keywords LIKE ?)")
                            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
                        
                        query += " AND (" + " OR ".join(keyword_conditions) + ")"
                
                query += " ORDER BY f.title, f.original_filename LIMIT 1000"
                
                # Execute query using storage's internal connection
                cursor = storage._conn.execute(query, params)
                rows = cursor.fetchall()
                
                # Format results
                documents = []
                for row in rows:
                    file_url, filename, title, category, keywords_str = row
                    
                    # Parse keywords from either JSON arrays or legacy comma-separated strings.
                    keywords = []
                    if keywords_str:
                        raw_keywords = str(keywords_str).strip()
                        if raw_keywords.startswith("["):
                            try:
                                parsed_keywords = json.loads(raw_keywords)
                            except json.JSONDecodeError:
                                parsed_keywords = []
                            if isinstance(parsed_keywords, list):
                                keywords = [str(k).strip() for k in parsed_keywords if str(k).strip()]
                        if not keywords:
                            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
                    
                    documents.append({
                        "file_url": file_url or "",
                        "filename": filename or "",
                        "title": title or filename or "Untitled",
                        "category": category or "",
                        "keywords": keywords
                    })
                
                return _api_success({"documents": documents})
                
            finally:
                storage.close()
        
        except Exception as e:
            logger.exception("Error listing available documents")
            return _api_error(
                "Internal server error",
                status_code=500,
                detail=str(e)
            )
    
    @app.route("/api/chat/summarize-document", methods=["POST"])
    @require_permissions("chat.query")
    def api_chat_summarize_document():
        """
        Generate a summary or explanation of a full document.
        
        This endpoint is optimized for document summarization using the
        complete markdown content rather than RAG chunks.
        
        Request JSON:
            {
                "document_content": "Full markdown content...",
                "document_title": "Document Title",
                "mode": "summary" | "detailed" | "tutorial",
                "user_prompt": "Optional custom instructions"
            }
        
        Response JSON:
            {
                "success": true,
                "data": {
                    "summary": "Generated summary text...",
                    "metadata": {
                        "mode": "summary",
                        "content_length": 12345,
                        "truncated": false,
                        "generation_time_ms": 1500,
                        "model": "gpt-4"
                    }
                }
            }
        """
        error = _check_chatbot_available()
        if error:
            return error
        
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _api_error("Invalid or missing JSON body", status_code=400)
            
            # Extract parameters
            document_content = data.get("document_content", "").strip()
            if not document_content:
                return _api_error("document_content is required", status_code=400)
            
            document_title = data.get("document_title", "").strip() or "Document"
            mode = data.get("mode", "summary")
            user_prompt = data.get("user_prompt", "").strip()
            
            # Validate mode
            valid_modes = ["summary", "detailed", "tutorial"]
            if mode not in valid_modes:
                return _api_error(
                    f"Invalid mode. Must be one of: {', '.join(valid_modes)}", 
                    status_code=400
                )
            
            # Truncate document if too long (max ~15K characters, ~4K tokens)
            MAX_DOC_LENGTH = 15000
            truncated = False
            original_length = len(document_content)
            if original_length > MAX_DOC_LENGTH:
                document_content = document_content[:MAX_DOC_LENGTH]
                truncated = True
                logger.info(f"Document truncated from {original_length} to {MAX_DOC_LENGTH} chars")
            
            # Initialize LLM client
            storage = Storage(db_path)
            try:
                config = chatbot_config.ChatbotConfig.from_config(storage=storage)
            finally:
                storage.close()
            llm_client = chatbot_llm.LLMClient(config)
            
            # Build summarization prompt based on mode (load optional override from config)
            _custom_sum_prompt: str | None = None
            try:
                from config.yaml_config import load_yaml_config
                _custom_sum_prompt = (
                    load_yaml_config()
                    .get("ai_config", {})
                    .get("chatbot", {})
                    .get("summarization_prompt") or None
                )
            except Exception:
                pass
            system_prompt = _build_summarization_system_prompt(mode, _custom_sum_prompt)
            
            # Build user message
            user_message_parts = []
            
            if user_prompt:
                user_message_parts.append(f"User Instructions: {user_prompt}\n")
            
            user_message_parts.append(f"Document Title: {document_title}\n")
            
            if truncated:
                user_message_parts.append(f"Note: Document was truncated to {MAX_DOC_LENGTH} characters from {original_length} characters.\n")
            
            user_message_parts.append(f"\n--- DOCUMENT CONTENT ---\n{document_content}\n--- END DOCUMENT ---\n")
            
            # Add mode-specific instructions
            if mode == "summary":
                user_message_parts.append("\nProvide a concise summary highlighting the key points and main takeaways.")
            elif mode == "detailed":
                user_message_parts.append("\nProvide a comprehensive explanation of this document, covering all major sections and important details.")
            elif mode == "tutorial":
                user_message_parts.append("\nExplain this document in a tutorial format, breaking down concepts step-by-step for someone learning the topic.")
            
            user_message = "".join(user_message_parts)
            
            # Generate response
            generation_start = time.time()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            response_text = llm_client.generate(messages=messages)
            generation_time_ms = int((time.time() - generation_start) * 1000)
            
            return _api_success({
                "summary": response_text,
                "metadata": {
                    "mode": mode,
                    "content_length": len(document_content),
                    "original_length": original_length,
                    "truncated": truncated,
                    "generation_time_ms": generation_time_ms,
                    "model": config.model
                }
            })
        
        except Exception as e:
            logger.exception("Error generating document summary")
            return _api_error(
                "Internal server error",
                status_code=500,
                detail=str(e)
            )
    
    def _build_summarization_system_prompt(mode: str, custom_prompt: str | None = None) -> str:
        """Build system prompt for document summarization.

        Args:
            mode: One of ``summary``, ``detailed``, ``tutorial``.
            custom_prompt: Optional full prompt override loaded from
                ``ai_config.chatbot.summarization_prompt`` in sites.yaml.
                When provided, it completely replaces the built-in prompt.
        """
        if custom_prompt and custom_prompt.strip():
            return custom_prompt.strip()

        base_prompt = (
            "You are a precise AI assistant specialized in analyzing documents related to "
            "actuarial science, insurance regulations, and related topics.\n\n"
            "RULES:\n"
            "1. Base your response ONLY on the content provided in the document.\n"
            "2. Do not invent facts, figures, or information not present in the document.\n"
            "3. Respond in the same language as the document content unless the user requests otherwise.\n"
            "4. If the document doesn't contain enough information to fully answer, acknowledge what's missing.\n"
            "5. Cite specific sections or figures when referencing details.\n"
            "6. Use clear, professional language appropriate for the insurance/actuarial field.\n"
        )

        mode_prompts = {
            "summary": (
                "\nSUMMARY MODE: Provide a concise summary (200-400 words) that captures:\n"
                "- The main purpose and scope of the document\n"
                "- Key findings, recommendations, or conclusions\n"
                "- Critical numbers, dates, thresholds, or regulatory references mentioned\n"
                "- Primary stakeholders or intended audience\n\n"
                "Focus on what a busy professional needs to know at a glance.\n"
            ),
            "detailed": (
                "\nDETAILED MODE: Provide a comprehensive explanation that covers:\n"
                "- Document structure and organization\n"
                "- All major sections and their key points\n"
                "- Important definitions, formulas, or technical content\n"
                "- Supporting evidence, data, and examples\n"
                "- Relationships between different sections\n"
                "- Practical implications and applications\n\n"
                "Be thorough while maintaining clarity. This is for someone who wants to "
                "understand the document deeply without reading the full text.\n"
            ),
            "tutorial": (
                "\nTUTORIAL MODE: Explain the document in an educational, step-by-step manner:\n"
                "- Start with the basics and build up progressively\n"
                "- Define technical terms before using them\n"
                "- Break down complex concepts into digestible parts\n"
                "- Use analogies or examples to clarify difficult points\n"
                "- Organize information logically for learning\n"
                "- Include a brief recap of key takeaways\n\n"
                "Write as if teaching someone new to this specific topic but with general "
                "knowledge of the insurance/actuarial field.\n"
            ),
        }

        return base_prompt + mode_prompts.get(mode, mode_prompts["summary"])
    
    @app.route("/api/chat/knowledge-bases", methods=["GET"])

    @require_permissions("chat.view")
    def api_chat_knowledge_bases():
        """Get list of available knowledge bases for chat."""
        error = _check_chatbot_available()
        if error:
            return error
        
        try:
            storage = Storage(db_path)
            
            try:
                kb_manager = rag_knowledge_base.KnowledgeBaseManager(storage)
                kbs = kb_manager.list_kbs()
                current_embedding = kb_manager.get_current_embedding_metadata()
                
                # Format for frontend
                kb_list = []
                for kb in kbs:
                    composition = storage.get_kb_composition_status(kb.kb_id)
                    latest_index = composition.get("latest_index") if isinstance(composition, dict) else None
                    index_provider = kb.embedding_provider
                    index_model = kb.embedding_model
                    index_dimension = kb.embedding_dimension
                    index_status = ""
                    index_built_at = None
                    if isinstance(latest_index, dict):
                        index_provider = latest_index.get("embedding_provider") or index_provider
                        index_model = latest_index.get("embedding_model") or index_model
                        index_dimension = latest_index.get("embedding_dimension")
                        index_status = latest_index.get("status") or ""
                        index_built_at = latest_index.get("built_at")

                    embedding_compatible = True
                    if index_provider and current_embedding.get("provider"):
                        embedding_compatible = (
                            str(index_provider).strip().lower()
                            == str(current_embedding["provider"]).strip().lower()
                        )
                    if embedding_compatible and index_model and current_embedding.get("model"):
                        embedding_compatible = (
                            str(index_model).strip() == str(current_embedding["model"]).strip()
                        )
                    if (
                        embedding_compatible
                        and index_dimension not in (None, "")
                        and current_embedding.get("dimension") not in (None, "")
                    ):
                        embedding_compatible = int(index_dimension) == int(current_embedding["dimension"])

                    kb_list.append({
                        "kb_id": kb.kb_id,
                        "name": kb.name,
                        "description": kb.description,
                        "file_count": kb.file_count,
                        "chunk_count": kb.chunk_count,
                        "embedding_provider": kb.embedding_provider,
                        "embedding_model": kb.embedding_model,
                        "embedding_dimension": kb.embedding_dimension,
                        "index_embedding_provider": index_provider,
                        "index_embedding_model": index_model,
                        "index_embedding_dimension": index_dimension,
                        "index_status": index_status,
                        "index_built_at": index_built_at,
                        "needs_reindex": bool(composition.get("needs_reindex")) or not embedding_compatible,
                        "embedding_compatible": embedding_compatible,
                    })
                
                return _api_success(
                    {
                        "knowledge_bases": kb_list,
                        "current_embeddings": current_embedding,
                    }
                )
                
            finally:
                storage.close()
        
        except Exception as e:
            logger.exception("Error listing knowledge bases")
            return _api_error(
                "Internal server error",
                status_code=500,
                detail=str(e)
            )
    
    logger.info("Chat routes registered")

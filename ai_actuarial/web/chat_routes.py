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
        from ai_actuarial.chatbot.retrieval import RAGRetriever
        from ai_actuarial.chatbot.llm import LLMClient
        from ai_actuarial.chatbot.conversation import ConversationManager
        from ai_actuarial.chatbot.router import QueryRouter
        from ai_actuarial.chatbot.config import ChatbotConfig
        from ai_actuarial.chatbot.exceptions import NoResultsException
        from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
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
        except Exception as _qe:
            logger.warning("Quota check failed (non-fatal): %s", _qe)
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
            config = ChatbotConfig(default_mode=mode)
            
            try:
                retriever = RAGRetriever(storage, config)
                llm_client = LLMClient(config)
                conv_manager = ConversationManager(storage, config)
                
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
                    # Truncate document if too long (max ~15K characters, ~4K tokens)
                    MAX_DOC_LENGTH = 15000
                    truncated = False
                    if len(document_content) > MAX_DOC_LENGTH:
                        document_content = document_content[:MAX_DOC_LENGTH]
                        truncated = True
                    
                    # Create a special chunk with the full document content
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
                        router = QueryRouter(storage, config)
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
                    except NoResultsException:
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
                            except NoResultsException:
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
                    response_text = llm_client.generate_response(
                        query=message,
                        chunks=chunks,
                        mode=mode,
                        conversation_history=history[:-1]  # Exclude the message we just added
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
                    })
                    
                    # Avoid duplicate citations
                    if filename in seen_files:
                        continue
                    seen_files.add(filename)
                    
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
                config = ChatbotConfig()
                
                try:
                    conv_manager = ConversationManager(storage, config)
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
                config = ChatbotConfig()
                
                try:
                    conv_manager = ConversationManager(storage, config)
                    
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
            config = ChatbotConfig()
            
            try:
                conv_manager = ConversationManager(storage, config)
                
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
                    
                    # Parse keywords (stored as comma-separated string)
                    keywords = []
                    if keywords_str:
                        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
                    
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
            config = ChatbotConfig()
            llm_client = LLMClient(config)
            
            # Build summarization prompt based on mode
            system_prompt = _build_summarization_system_prompt(mode)
            
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
    
    def _build_summarization_system_prompt(mode: str) -> str:
        """Build system prompt for document summarization."""
        base_prompt = """You are an AI assistant specialized in analyzing and explaining documents related to actuarial science, insurance, and related topics.

Your task is to analyze the provided document and generate a clear, accurate response based on the document's content.

RULES:
1. Base your response ONLY on the content provided in the document.
2. Do not invent facts, figures, or information not present in the document.
3. If the document doesn't contain enough information to fully answer, acknowledge what's missing.
4. Maintain accuracy and cite specific sections when referencing details.
5. Use clear, professional language appropriate for the insurance/actuarial field.
"""
        
        mode_prompts = {
            "summary": """
SUMMARY MODE: Provide a concise summary (200-400 words) that captures:
- The main purpose and scope of the document
- Key findings, recommendations, or conclusions
- Critical numbers, dates, or thresholds mentioned
- Primary stakeholders or audience

Focus on what a busy professional needs to know at a glance.
""",
            "detailed": """
DETAILED MODE: Provide a comprehensive explanation that covers:
- Document structure and organization
- All major sections and their key points
- Important definitions, formulas, or technical content
- Supporting evidence, data, and examples
- Relationships between different sections
- Implications and practical applications

Be thorough while maintaining clarity. This is for someone who wants to understand the document deeply without reading the full text.
""",
            "tutorial": """
TUTORIAL MODE: Explain the document in an educational, step-by-step manner:
- Start with the basics and build up progressively
- Define technical terms before using them
- Break down complex concepts into digestible parts
- Use analogies or examples to clarify difficult points
- Organize information logically for learning
- Include a brief recap of key takeaways

Write as if teaching someone who is new to this specific topic but has general knowledge of the field.
"""
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
                kb_manager = KnowledgeBaseManager(storage)
                kbs = kb_manager.list_kbs()
                
                # Format for frontend
                kb_list = [{
                    "kb_id": kb.kb_id,
                    "name": kb.name,
                    "description": kb.description,
                    "file_count": kb.file_count,
                    "chunk_count": kb.chunk_count
                } for kb in kbs]
                
                return _api_success({"knowledge_bases": kb_list})
                
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

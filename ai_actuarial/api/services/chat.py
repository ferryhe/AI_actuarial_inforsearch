from __future__ import annotations

import importlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse

from itsdangerous import URLSafeSerializer
from ai_actuarial.api.deps import _decode_signed_session, AuthContext
from ai_actuarial.ai_runtime import infer_embedding_dimension, resolve_ai_function_runtime
from ai_actuarial.config import settings
from ai_actuarial.storage import Storage
from ai_actuarial.shared_auth import AI_CHAT_QUOTA

logger = logging.getLogger(__name__)


class ChatApiError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {"success": False, "error": message}


class SessionUpdate(dict):
    pass


class ChatModules(dict):
    pass


VALID_CHAT_MODES = {"expert", "summary", "tutorial", "comparison"}
MAX_DOCUMENT_SOURCES = 3
MAX_DOCUMENT_SOURCE_CONTENT_CHARS = 15000
MAX_DOCUMENT_CONTEXT_CHARS = 45000
MAX_DOCUMENT_FIELD_CHARS = 512


def _ensure_conversation_schema(storage: Storage) -> None:
    conn = storage._conn
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            kb_id TEXT,
            mode TEXT DEFAULT 'expert',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            metadata TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations TEXT,
            created_at TEXT NOT NULL,
            token_count INTEGER,
            metadata TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_conversation
        ON messages(conversation_id, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user
        ON conversations(user_id, updated_at DESC)
        """
    )
    conn.commit()


def _default_conversation_title() -> str:
    return f"New Conversation - {datetime.now(timezone.utc).strftime('%b %d')}"


def _base_chat_modules() -> ChatModules:
    try:
        return ChatModules(
            config=importlib.import_module("ai_actuarial.chatbot.config"),
            conversation=importlib.import_module("ai_actuarial.chatbot.conversation"),
            exceptions=importlib.import_module("ai_actuarial.chatbot.exceptions"),
            knowledge_base=importlib.import_module("ai_actuarial.rag.knowledge_base"),
        )
    except ImportError as exc:  # noqa: BLE001
        raise ChatApiError(
            "Chatbot functionality not available",
            status_code=503,
            payload={"success": False, "error": "Chatbot functionality not available"},
        ) from exc


def _full_chat_modules() -> ChatModules:
    modules = _base_chat_modules()
    try:
        modules.update(
            retrieval=importlib.import_module("ai_actuarial.chatbot.retrieval"),
            llm=importlib.import_module("ai_actuarial.chatbot.llm"),
            router=importlib.import_module("ai_actuarial.chatbot.router"),
        )
        return modules
    except ImportError as exc:  # noqa: BLE001
        raise ChatApiError(
            "Chatbot functionality not available",
            status_code=503,
            payload={"success": False, "error": "Chatbot functionality not available"},
        ) from exc


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _query_values(query: Mapping[str, Any], key: str) -> list[str]:
    getlist = getattr(query, "getlist", None)
    if callable(getlist):
        raw_values = getlist(key)
    else:
        value = query.get(key)
        if isinstance(value, (list, tuple)):
            raw_values = list(value)
        elif value is None:
            raw_values = []
        else:
            raw_values = [value]

    values: list[str] = []
    for raw_value in raw_values:
        for part in str(raw_value or "").split(","):
            normalized = part.strip()
            if normalized and normalized not in values:
                values.append(normalized)
    return values


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_file_links(raw_file_url: str, *, return_to: str = "/chat") -> dict[str, str]:
    source_url = str(raw_file_url or "").strip()
    if not source_url:
        return {"source_url": "", "file_detail_url": "", "file_preview_url": ""}
    if source_url.startswith("/file-detail"):
        return {"source_url": source_url, "file_detail_url": source_url, "file_preview_url": ""}
    if source_url.startswith("/file-preview"):
        return {"source_url": source_url, "file_detail_url": "", "file_preview_url": source_url}
    if source_url.startswith("/file/"):
        encoded_source = source_url[len("/file/") :].split("?", 1)[0]
        try:
            source_url = unquote(encoded_source)
        except Exception:
            source_url = encoded_source
    elif source_url.startswith("/file_preview"):
        parsed_file_url = parse_qs(urlparse(source_url).query).get("file_url", [""])[0]
        source_url = parsed_file_url or source_url
    elif source_url.startswith("/database/"):
        return {"source_url": source_url, "file_detail_url": source_url, "file_preview_url": ""}

    encoded_source = quote(source_url, safe="")
    encoded_return_to = quote(return_to, safe="")
    return {
        "source_url": source_url,
        "file_detail_url": f"/file-detail?url={encoded_source}&from={encoded_return_to}",
        "file_preview_url": f"/file-preview?file_url={encoded_source}&from={encoded_return_to}",
    }


def _resolve_chat_user(request, auth: AuthContext) -> tuple[str, SessionUpdate | None]:
    token = auth.token or {}
    subject = _normalize_text(token.get("subject"))
    if subject:
        return f"user:{subject}", None

    token_id = token.get("id")
    if token_id is not None:
        return f"token:{token_id}", None

    session_data = _decode_signed_session(request)
    session_subject = _normalize_text(session_data.get("auth_subject"))
    if session_subject:
        return f"user:{session_subject}", None

    guest_id = _normalize_text(session_data.get("guest_chat_user_id"))
    if guest_id:
        return guest_id, None

    guest_id = f"guest:{uuid.uuid4().hex[:16]}"
    session_data["guest_chat_user_id"] = guest_id
    return guest_id, SessionUpdate(session_data)


def apply_session_update(response, request, session_update: SessionUpdate | None) -> None:
    if not session_update:
        return
    secret = str(getattr(request.app.state, "fastapi_session_secret", "") or "")
    if not secret:
        logger.debug("Skipping chat session update because no FastAPI session secret is configured")
        return
    cookie_name = str(getattr(request.app.state, "fastapi_session_cookie_name", "session") or "session")
    serializer = URLSafeSerializer(secret, salt="fastapi-session")
    response.set_cookie(
        key=cookie_name,
        value=serializer.dumps(dict(session_update)),
        httponly=bool(getattr(request.app.state, "fastapi_session_cookie_httponly", True)),
        secure=bool(getattr(request.app.state, "fastapi_session_cookie_secure", False)),
        samesite=getattr(request.app.state, "fastapi_session_cookie_samesite", "Lax") or "Lax",
        path=getattr(request.app.state, "fastapi_session_cookie_path", "/") or "/",
        domain=getattr(request.app.state, "fastapi_session_cookie_domain", None) or None,
    )


def list_conversations(*, db_path: str, request, auth: AuthContext) -> tuple[dict[str, Any], SessionUpdate | None]:
    user_id, session_update = _resolve_chat_user(request, auth)
    storage = Storage(db_path)
    try:
        _ensure_conversation_schema(storage)
        rows = storage._conn.execute(
            """
            SELECT conversation_id, user_id, title, kb_id, mode, created_at,
                   updated_at, message_count, metadata
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT 50 OFFSET 0
            """,
            (user_id,),
        ).fetchall()
        conversations = [
            {
                "conversation_id": row[0],
                "user_id": row[1],
                "title": row[2],
                "kb_id": row[3],
                "mode": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "message_count": row[7],
                "metadata": json.loads(row[8]) if row[8] else None,
            }
            for row in rows
        ]
        return {"success": True, "data": {"conversations": conversations}}, session_update
    finally:
        storage.close()


def create_conversation(*, db_path: str, request, auth: AuthContext, payload: dict[str, Any]) -> tuple[dict[str, Any], SessionUpdate | None]:
    if not isinstance(payload, dict):
        raise ChatApiError("Invalid JSON body", status_code=400)
    mode = _normalize_text(payload.get("mode") or "expert").lower()
    if mode not in VALID_CHAT_MODES:
        raise ChatApiError(f"Invalid mode '{mode}'", status_code=400)
    kb_id = _normalize_text(payload.get("kb_id")) or None
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None

    user_id, session_update = _resolve_chat_user(request, auth)
    storage = Storage(db_path)
    try:
        _ensure_conversation_schema(storage)
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"
        now = _current_timestamp()
        storage._conn.execute(
            """
            INSERT INTO conversations
            (conversation_id, user_id, title, kb_id, mode, created_at, updated_at, message_count, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                user_id,
                _default_conversation_title(),
                kb_id,
                mode,
                now,
                now,
                0,
                json.dumps(metadata) if metadata else None,
            ),
        )
        storage._conn.commit()
        return {"success": True, "data": {"conversation_id": conversation_id}}, session_update
    finally:
        storage.close()


def get_conversation_detail(*, db_path: str, request, auth: AuthContext, conversation_id: str) -> tuple[dict[str, Any], SessionUpdate | None]:
    user_id, session_update = _resolve_chat_user(request, auth)
    storage = Storage(db_path)
    try:
        _ensure_conversation_schema(storage)
        row = storage._conn.execute(
            """
            SELECT conversation_id, user_id, title, kb_id, mode, created_at,
                   updated_at, message_count, metadata
            FROM conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        conversation = None if not row else {
            "conversation_id": row[0],
            "user_id": row[1],
            "title": row[2],
            "kb_id": row[3],
            "mode": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "message_count": row[7],
            "metadata": json.loads(row[8]) if row[8] else None,
        }
        if not conversation:
            raise ChatApiError("Conversation not found", status_code=404)
        if conversation.get("user_id") != user_id:
            raise ChatApiError("Access denied", status_code=403)
        message_rows = storage._conn.execute(
            """
            SELECT message_id, conversation_id, role, content, citations, created_at, token_count, metadata
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
        messages = [
            {
                "message_id": row[0],
                "conversation_id": row[1],
                "role": row[2],
                "content": row[3],
                "citations": json.loads(row[4]) if row[4] else None,
                "created_at": row[5],
                "token_count": row[6],
                "metadata": json.loads(row[7]) if row[7] else None,
            }
            for row in message_rows
        ]
        return {"success": True, "data": {"conversation": conversation, "messages": messages}}, session_update
    finally:
        storage.close()


def delete_conversation(*, db_path: str, request, auth: AuthContext, conversation_id: str) -> tuple[dict[str, Any], SessionUpdate | None]:
    user_id, session_update = _resolve_chat_user(request, auth)
    storage = Storage(db_path)
    try:
        _ensure_conversation_schema(storage)
        row = storage._conn.execute(
            "SELECT conversation_id, user_id FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        conversation = None if not row else {"conversation_id": row[0], "user_id": row[1]}
        if not conversation:
            raise ChatApiError("Conversation not found", status_code=404)
        if conversation.get("user_id") != user_id:
            raise ChatApiError("Access denied", status_code=403)
        storage._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        storage._conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
        storage._conn.commit()
        return {"success": True, "message": "Conversation deleted"}, session_update
    finally:
        storage.close()


def _embedding_metadata_matches(
    current: Mapping[str, Any],
    *,
    provider: Any,
    model: Any,
    dimension: Any,
) -> bool:
    current_provider = str(current.get("provider") or "").strip().lower()
    current_model = str(current.get("model") or "").strip()
    current_dimension = current.get("dimension")

    index_provider = str(provider or "").strip().lower()
    index_model = str(model or "").strip()
    index_dimension = dimension

    if index_provider and current_provider and index_provider != current_provider:
        return False
    if index_model and current_model and index_model != current_model:
        return False
    if index_dimension not in (None, "") and current_dimension not in (None, ""):
        try:
            if int(index_dimension) != int(current_dimension):
                return False
        except (TypeError, ValueError):
            return False
    return True



def list_knowledge_bases(*, db_path: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        embeddings_runtime = resolve_ai_function_runtime("embeddings", storage=storage)
        current_embeddings = {
            "provider": embeddings_runtime.provider,
            "model": embeddings_runtime.model,
            "dimension": infer_embedding_dimension(embeddings_runtime.model),
            "credential_source": embeddings_runtime.credential_source,
            "credential_id": embeddings_runtime.credential_id,
            "stable_credential_id": embeddings_runtime.stable_credential_id,
            "credential_label": embeddings_runtime.credential_label,
            "configured": embeddings_runtime.configured,
            "credential_error": embeddings_runtime.credential_error,
        }
        knowledge_bases: list[dict[str, Any]] = []
        rows = storage._conn.execute(
            """
            SELECT kb_id, name, description, embedding_provider, embedding_model, embedding_dimension,
                   file_count, chunk_count
            FROM rag_knowledge_bases
            ORDER BY created_at DESC
            """
        ).fetchall()
        for row in rows:
            kb_id = row[0]
            composition = storage.get_kb_composition_status(kb_id)
            latest_index = composition.get("latest_index") or {}
            has_index = bool(composition.get("has_index"))
            kb_provider = row[3] or "openai"
            kb_model = row[4]
            kb_dimension = row[5]
            effective_index_provider = latest_index.get("embedding_provider") or kb_provider
            effective_index_model = latest_index.get("embedding_model") or kb_model
            effective_index_dimension = latest_index.get("embedding_dimension")
            if effective_index_dimension in (None, ""):
                effective_index_dimension = kb_dimension
            embedding_compatible = _embedding_metadata_matches(
                current_embeddings,
                provider=effective_index_provider,
                model=effective_index_model,
                dimension=effective_index_dimension,
            )
            needs_reindex = bool(composition.get("needs_reindex")) or (has_index and not embedding_compatible)
            index_status = str(latest_index.get("status") or "").strip().lower()
            if not has_index or index_status in {"pending", "queued", "running", "building", "indexing"}:
                availability = "building"
                usable = False
            elif needs_reindex:
                availability = "needs_reindex"
                usable = False
            else:
                availability = "ready"
                usable = True
            knowledge_bases.append(
                {
                    "kb_id": kb_id,
                    "name": row[1],
                    "description": row[2],
                    "file_count": row[6],
                    "chunk_count": row[7],
                    "embedding_provider": kb_provider,
                    "embedding_model": kb_model,
                    "embedding_dimension": kb_dimension,
                    "index_embedding_provider": effective_index_provider,
                    "index_embedding_model": effective_index_model,
                    "index_embedding_dimension": effective_index_dimension,
                    "index_status": latest_index.get("status") or ("ready" if has_index and effective_index_model else None),
                    "index_built_at": latest_index.get("built_at"),
                    "needs_reindex": needs_reindex,
                    "embedding_compatible": embedding_compatible,
                    "availability": availability,
                    "usable": usable,
                }
            )
        return {"success": True, "data": {"knowledge_bases": knowledge_bases, "current_embeddings": current_embeddings}}
    finally:
        storage.close()


def list_available_documents(*, db_path: str, query: Mapping[str, Any]) -> dict[str, Any]:
    categories = _query_values(query, "category")
    categories.extend(category for category in _query_values(query, "categories") if category not in categories)
    keywords_raw = _normalize_text(query.get("keywords"))
    keywords = [item.strip() for item in keywords_raw.split(",") if item.strip()]

    storage = Storage(db_path)
    try:
        where_parts = [
            "f.deleted_at IS NULL",
            "c.markdown_content IS NOT NULL",
            "c.markdown_content != ''",
        ]
        params: list[Any] = []
        if categories:
            category_clauses = []
            for category in categories:
                if category == "__uncategorized__":
                    category_clauses.append("(c.category IS NULL OR TRIM(c.category) = '')")
                else:
                    category_clauses.append(
                        "(c.category = ? OR c.category LIKE ? OR c.category LIKE ? OR c.category LIKE ?)"
                    )
                    params.extend([category, f"{category};%", f"%; {category}", f"%; {category};%"])
            where_parts.append(f"({' OR '.join(category_clauses)})")
        if keywords:
            keyword_clauses = []
            for keyword in keywords:
                keyword_clauses.append("(LOWER(f.title) LIKE ? OR LOWER(f.original_filename) LIKE ? OR LOWER(c.keywords) LIKE ?)")
                wildcard = f"%{keyword.lower()}%"
                params.extend([wildcard, wildcard, wildcard])
            where_parts.append(f"({' OR '.join(keyword_clauses)})")
        where_sql = " AND ".join(where_parts)
        rows = storage._conn.execute(
            f"""
            SELECT f.url, f.original_filename, f.title, c.category, c.keywords
            FROM files f
            JOIN catalog_items c ON c.file_url = f.url
            WHERE {where_sql}
            ORDER BY f.title, f.original_filename
            LIMIT 1000
            """,
            params,
        ).fetchall()
        documents = []
        for row in rows:
            raw_keywords = row[4]
            parsed_keywords: list[str]
            if isinstance(raw_keywords, str) and raw_keywords.strip().startswith("["):
                try:
                    loaded = json.loads(raw_keywords)
                    parsed_keywords = [str(item).strip() for item in loaded if str(item).strip()]
                except Exception:
                    parsed_keywords = [item.strip() for item in raw_keywords.split(",") if item.strip()]
            else:
                parsed_keywords = [item.strip() for item in str(raw_keywords or "").split(",") if item.strip()]
            documents.append(
                {
                    "file_url": row[0],
                    "filename": row[1] or "",
                    "title": row[2] or row[1] or "",
                    "category": row[3] or "",
                    "keywords": parsed_keywords,
                }
            )
        return {"success": True, "data": {"documents": documents}}
    finally:
        storage.close()


def _friendly_no_results_message() -> str:
    return (
        "I couldn't find relevant source material for that question in the selected knowledge bases. "
        "Try broadening the question, selecting a different knowledge base, or asking about a document directly."
    )


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _client_ip(request) -> str:
    trust_proxy = settings.TRUST_PROXY
    if trust_proxy:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def _chat_quota_role(token: dict[str, Any]) -> str:
    role = _normalize_text(token.get("group_name")).lower()
    email_user = token.get("_email_user")
    if not role and isinstance(email_user, dict):
        role = _normalize_text(email_user.get("role")).lower()
    if not role and token.get("_email_user_id") is not None:
        role = "registered"
    return role or "anonymous"


def _enforce_chat_quota(*, storage: Storage, request, auth: AuthContext) -> None:
    token = auth.token or {}
    email_user = token.get("_email_user") if isinstance(token, dict) else None
    role = _chat_quota_role(token) if isinstance(token, dict) else "anonymous"
    if role == "admin":
        return
    limit = AI_CHAT_QUOTA.get(role, AI_CHAT_QUOTA.get("anonymous", 2))
    today = _today_utc()

    if email_user:
        allowed, _count = storage.check_and_increment_ai_chat_quota(today, limit, user_id=int(email_user["id"]))
    else:
        allowed, _count = storage.check_and_increment_ai_chat_quota(today, limit, ip_address=_client_ip(request))

    if not allowed:
        upgrade_hint = (
            "Please register to get more queries." if role == "anonymous"
            else "Please upgrade to Premium for higher limits." if role == "registered"
            else "Daily quota exceeded."
        )
        raise ChatApiError(
            f"Daily AI chat limit reached ({limit}/day). {upgrade_hint}",
            status_code=429,
        )


def _serialize_citations(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    citations: list[dict[str, Any]] = []
    retrieved_blocks: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        content = str(chunk.get("content") or "")
        links = _build_file_links(str(metadata.get("file_url") or ""))
        block = {
            "filename": metadata.get("filename") or "",
            "kb_id": metadata.get("kb_id") or "",
            "kb_name": metadata.get("kb_name") or "",
            "chunk_id": metadata.get("chunk_id") or "",
            "similarity_score": metadata.get("similarity_score"),
            "content": content,
            "source_url": links["source_url"],
            "file_detail_url": links["file_detail_url"],
            "file_preview_url": links["file_preview_url"],
            "quote": content[:280].strip(),
        }
        retrieved_blocks.append(block)
        dedupe_key = links["source_url"] or str(metadata.get("filename") or metadata.get("chunk_id") or len(citations))
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        citations.append(
            {
                "filename": metadata.get("filename") or "",
                "kb_id": metadata.get("kb_id") or "",
                "kb_name": metadata.get("kb_name") or "",
                "chunk_id": metadata.get("chunk_id") or "",
                "similarity_score": metadata.get("similarity_score"),
                "source_url": links["source_url"],
                "file_url": links["source_url"],
                "file_detail_url": links["file_detail_url"],
                "file_preview_url": links["file_preview_url"],
                "quote": content[:280].strip(),
            }
        )
    return citations, retrieved_blocks


def _bounded_source_text(value: Any, *, fallback: str = "", max_chars: int = MAX_DOCUMENT_FIELD_CHARS) -> str:
    text = _normalize_text(value) or fallback
    return text[:max_chars]


def _prepare_document_source_chunks(
    *,
    document_content: str,
    document_filename: str,
    document_file_url: str,
    document_sources: list[Any],
    max_total_chars: int = MAX_DOCUMENT_CONTEXT_CHARS,
    max_content_chars: int = MAX_DOCUMENT_SOURCE_CONTENT_CHARS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources = document_sources or [
        {
            "file_url": document_file_url,
            "filename": document_filename,
            "content": document_content,
        }
    ]
    chunks: list[dict[str, Any]] = []
    original_chars = 0
    used_chars = 0
    truncated_sources: list[str] = []

    for index, source in enumerate(sources, start=1):
        source_dict = source if isinstance(source, dict) else {}
        filename = _bounded_source_text(source_dict.get("filename"), fallback=f"Document {index}") or f"Document {index}"
        file_url = _bounded_source_text(source_dict.get("file_url"))
        raw_content = _normalize_text(source_dict.get("content")) or document_content
        original_chars += len(raw_content)

        remaining_chars = max(0, max_total_chars - used_chars)
        content_limit = min(max_content_chars, remaining_chars)
        content = raw_content[:content_limit]
        used_chars += len(content)
        if len(content) < len(raw_content):
            truncated_sources.append(filename)

        chunks.append(
            {
                "content": content,
                "metadata": {
                    "filename": filename,
                    "kb_id": "document_explanation",
                    "kb_name": "Full Document",
                    "similarity_score": 1.0,
                    "chunk_id": f"document_{index}",
                    "file_url": file_url,
                    "untrusted_context": True,
                },
            }
        )

    context_notice = {
        "context_truncated": bool(truncated_sources),
        "original_chars": original_chars,
        "used_chars": used_chars,
        "max_chars": max_total_chars,
        "truncated_sources": truncated_sources,
    }
    return chunks, context_notice


def query_chat(*, db_path: str, request, auth: AuthContext, payload: dict[str, Any]) -> tuple[dict[str, Any], SessionUpdate | None]:
    modules = _full_chat_modules()
    if not isinstance(payload, dict):
        raise ChatApiError("Invalid or missing JSON body", status_code=400)

    message = _normalize_text(payload.get("message"))
    if not message:
        raise ChatApiError("Message is required", status_code=400)
    mode = _normalize_text(payload.get("mode") or "expert").lower()
    if mode not in VALID_CHAT_MODES:
        raise ChatApiError(f"Invalid mode '{mode}'", status_code=400)

    kb_ids = payload.get("kb_ids")
    conversation_id = _normalize_text(payload.get("conversation_id")) or None
    document_content = _normalize_text(payload.get("document_content"))
    document_filename = _normalize_text(payload.get("document_filename")) or "Document"
    document_file_url = _normalize_text(payload.get("document_file_url"))
    raw_document_sources = payload.get("document_sources")
    document_sources = raw_document_sources if isinstance(raw_document_sources, list) else []
    if len(document_sources) > MAX_DOCUMENT_SOURCES:
        raise ChatApiError("Too many files selected; choose up to 3.", status_code=400)

    user_id, session_update = _resolve_chat_user(request, auth)
    storage = Storage(db_path)
    try:
        _enforce_chat_quota(storage=storage, request=request, auth=auth)
        config = modules["config"].ChatbotConfig.from_config(storage=storage, default_mode=mode)
        conversation_manager = modules["conversation"].ConversationManager(storage, config)
        exceptions = modules["exceptions"]

        if conversation_id:
            conversation = conversation_manager.get_conversation(conversation_id)
            if not conversation:
                raise ChatApiError("Conversation not found", status_code=404)
            if conversation.get("user_id") != user_id:
                raise ChatApiError("Access denied", status_code=403)
        else:
            primary_kb = None
            if isinstance(kb_ids, list) and kb_ids:
                primary_kb = _normalize_text(kb_ids[0]) or None
            elif isinstance(kb_ids, str) and kb_ids not in {"auto", "all"}:
                primary_kb = _normalize_text(kb_ids) or None
            conversation_id = conversation_manager.create_conversation(
                user_id=user_id,
                kb_id=primary_kb,
                mode=mode,
                metadata={"kb_ids": kb_ids, "mode": mode},
            )

        conversation_manager.add_message(conversation_id, "user", message)
        conversation_history = conversation_manager.get_context(conversation_id)

        chunks: list[dict[str, Any]] = []
        context_notice: dict[str, Any] = {
            "context_truncated": False,
            "original_chars": 0,
            "used_chars": 0,
            "max_chars": MAX_DOCUMENT_CONTEXT_CHARS,
            "truncated_sources": [],
        }
        no_results = False
        used_threshold = getattr(config, "similarity_threshold", None)

        if document_content:
            chunks, context_notice = _prepare_document_source_chunks(
                document_content=document_content,
                document_filename=document_filename,
                document_file_url=document_file_url,
                document_sources=document_sources,
            )
        else:
            retriever = modules["retrieval"].RAGRetriever(storage, config)
            normalized_kb_ids: Any = kb_ids
            if kb_ids in (None, "", "all"):
                normalized_kb_ids = None
            elif kb_ids == "auto":
                normalized_kb_ids = modules["router"].QueryRouter(storage, config).select_kb(message)
            try:
                chunks = retriever.retrieve(message, normalized_kb_ids)
            except exceptions.NoResultsException:
                no_results = True
                chunks = []
            except exceptions.EmbeddingConfigurationMismatchException as exc:
                raise ChatApiError(
                    str(exc),
                    status_code=409,
                    payload={
                        "success": False,
                        "code": "KB_EMBEDDING_MISMATCH",
                        "error": str(exc),
                        "data": {
                            "kb_id": exc.kb_id,
                            "current_embedding": {
                                "provider": exc.current_provider,
                                "model": exc.current_model,
                                "dimension": exc.current_dimension,
                            },
                            "index_embedding": {
                                "provider": exc.index_provider,
                                "model": exc.index_model,
                                "dimension": exc.index_dimension,
                            },
                            "needs_reindex": exc.needs_reindex,
                        },
                    },
                ) from exc

        if no_results:
            response_text = _friendly_no_results_message()
            citations: list[dict[str, Any]] = []
            retrieved_blocks: list[dict[str, Any]] = []
        else:
            llm_client = modules["llm"].LLMClient(config, storage=storage)
            response_text = llm_client.generate_response(
                query=message,
                chunks=chunks,
                mode=mode,
                conversation_history=conversation_history,
            )
            citations, retrieved_blocks = _serialize_citations(chunks)

        assistant_metadata = {
            "model": getattr(config, "model", None),
            "mode": mode,
            "retrieval_time_ms": 0,
            "generation_time_ms": 0,
            "num_chunks": len(chunks),
            "no_results": no_results,
            "used_threshold": used_threshold,
            "retrieved_blocks": retrieved_blocks,
            "context_truncated": context_notice["context_truncated"],
            "context_notice": context_notice,
        }
        message_id = conversation_manager.add_message(
            conversation_id,
            "assistant",
            response_text,
            citations=citations,
            metadata=assistant_metadata,
        )

        return {
            "success": True,
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "response": response_text,
                "citations": citations,
                "retrieved_blocks": retrieved_blocks,
                "metadata": {
                    "retrieval_time_ms": 0,
                    "generation_time_ms": 0,
                    "model": getattr(config, "model", None),
                    "mode": mode,
                    "num_chunks": len(chunks),
                    "no_results": no_results,
                    "used_threshold": used_threshold,
                    "context_truncated": context_notice["context_truncated"],
                    "context_notice": context_notice,
                },
            },
        }, session_update
    except ChatApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        conversation_exc = getattr(exceptions, "ConversationException", None)
        llm_exc = getattr(exceptions, "LLMException", None)
        retrieval_exc = getattr(exceptions, "RetrievalException", None)
        expose_detail = bool(getattr(request.app.state, "expose_error_details", settings.EXPOSE_ERROR_DETAILS))
        if conversation_exc and isinstance(exc, conversation_exc):
            detail = f": {exc}" if expose_detail else ""
            raise ChatApiError(f"Conversation error{detail}", status_code=400) from exc
        if llm_exc and isinstance(exc, llm_exc):
            detail = f": {exc}" if expose_detail else ""
            raise ChatApiError(f"LLM generation failed{detail}", status_code=502) from exc
        if retrieval_exc and isinstance(exc, retrieval_exc):
            detail = f": {exc}" if expose_detail else ""
            raise ChatApiError(f"Retrieval failed{detail}", status_code=502) from exc
        raise
    finally:
        storage.close()

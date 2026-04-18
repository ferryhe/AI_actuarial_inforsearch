"""
Chat/conversation service layer.

Contains conversation and chat-related operations extracted from chat.py
for better code organization and reduced duplication.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_actuarial.storage import Storage

__all__ = [
    "add_message",
    "delete_conversation",
    "ensure_conversation_schema",
    "get_conversation_messages",
    "get_or_create_conversation",
    "list_conversations",
    "update_conversation_title",
]


# ---------------------------------------------------------------------------
# Conversation schema helpers
# ---------------------------------------------------------------------------


def ensure_conversation_schema(storage: Storage) -> None:
    """Create the conversations and messages tables if they don't exist."""
    conn = storage._conn
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            kb_id TEXT,
            mode TEXT DEFAULT 'expert',
            created_at TEXT,
            updated_at TEXT
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
            metadata TEXT,
            created_at TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)"
    )
    storage._maybe_commit()


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


def get_or_create_conversation(
    storage: Storage,
    conversation_id: str | None,
    user_id: str,
    kb_id: str | None = None,
    mode: str = "expert",
    title: str | None = None,
) -> dict[str, Any]:
    """Get an existing conversation or create a new one."""
    if conversation_id:
        row = storage._conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row:
            cols = [d[0] for d in storage._conn.execute("SELECT * FROM conversations WHERE 1=0").description]
            return dict(zip(cols, row))

    new_id = conversation_id or _generate_conversation_id()
    now = _utcnow_iso()
    storage._conn.execute(
        """
        INSERT INTO conversations (conversation_id, user_id, title, kb_id, mode, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id, user_id, title or "New Chat", kb_id, mode, now, now),
    )
    storage._maybe_commit()
    return {
        "conversation_id": new_id,
        "user_id": user_id,
        "title": title or "New Chat",
        "kb_id": kb_id,
        "mode": mode,
        "created_at": now,
        "updated_at": now,
    }


def list_conversations(
    storage: Storage,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List recent conversations for a user."""
    cursor = storage._conn.execute(
        """
        SELECT conversation_id, user_id, title, kb_id, mode, created_at, updated_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    )
    cols = [d[0] for d in storage._conn.execute("SELECT * FROM conversations WHERE 1=0").description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def delete_conversation(storage: Storage, conversation_id: str, user_id: str) -> bool:
    """Delete a conversation and its messages."""
    cur = storage._conn.execute(
        "DELETE FROM conversations WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id),
    )
    storage._maybe_commit()
    return cur.rowcount > 0


def update_conversation_title(
    storage: Storage,
    conversation_id: str,
    user_id: str,
    title: str,
) -> bool:
    """Update the title of a conversation."""
    cur = storage._conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE conversation_id = ? AND user_id = ?",
        (title, _utcnow_iso(), conversation_id, user_id),
    )
    storage._maybe_commit()
    return cur.rowcount > 0


def add_message(
    storage: Storage,
    conversation_id: str,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add a message to a conversation."""
    import uuid

    message_id = f"msg_{uuid.uuid4().hex}"
    now = _utcnow_iso()
    import json

    citations_json = json.dumps(citations) if citations else None
    metadata_json = json.dumps(metadata) if metadata else None

    storage._conn.execute(
        """
        INSERT INTO messages (message_id, conversation_id, role, content, citations, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, conversation_id, role, content, citations_json, metadata_json, now),
    )
    storage._conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
        (now, conversation_id),
    )
    storage._maybe_commit()
    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "citations": citations,
        "metadata": metadata,
        "created_at": now,
    }


def get_conversation_messages(
    storage: Storage,
    conversation_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get messages for a conversation."""
    import json

    cursor = storage._conn.execute(
        """
        SELECT message_id, conversation_id, role, content, citations, metadata, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (conversation_id, limit),
    )
    cols = [d[0] for d in storage._conn.execute("SELECT * FROM messages WHERE 1=0").description]
    results = []
    for row in cursor.fetchall():
        d = dict(zip(cols, row))
        if d.get("citations"):
            try:
                d["citations"] = json.loads(d["citations"])
            except Exception:
                d["citations"] = []
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                d["metadata"] = {}
        results.append(d)
    return results


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _generate_conversation_id() -> str:
    import uuid
    return f"conv_{uuid.uuid4().hex}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

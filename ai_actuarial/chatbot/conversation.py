"""
Conversation state management for chatbot.

Manages conversation history, context windows, and database persistence.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from ai_actuarial.storage import Storage
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import ConversationException

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation state and history.
    
    Features:
    - Create and manage conversations
    - Add and retrieve messages
    - Context window management
    - Database persistence
    """
    
    def __init__(
        self,
        storage: Storage,
        config: Optional[ChatbotConfig] = None
    ):
        """
        Initialize conversation manager.
        
        Args:
            storage: Storage instance for database access
            config: Chatbot configuration
        """
        self.storage = storage
        self.config = config or ChatbotConfig.from_config(storage=storage)
        
        # Initialize database schema
        self._init_schema()
        
        logger.info("Initialized conversation manager")
    
    def _init_schema(self):
        """Initialize database schema for conversations and messages."""
        conn = self.storage._conn
        
        # Conversations table
        conn.execute("""
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
        """)
        
        # Messages table
        conn.execute("""
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
        """)
        
        # Indexes for performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation 
            ON messages(conversation_id, created_at)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user 
            ON conversations(user_id, updated_at DESC)
        """)
        
        conn.commit()
        
        logger.info("Database schema initialized")
    
    def create_conversation(
        self,
        user_id: str,
        kb_id: Optional[str] = None,
        mode: str = "expert",
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new conversation.
        
        Args:
            user_id: User identifier
            kb_id: Primary knowledge base ID (optional)
            mode: Chatbot mode (expert, summary, tutorial, comparison)
            title: Optional conversation title (auto-generated from first message if None)
            metadata: Optional metadata dict (e.g., kb_ids for multi-KB, settings)
        
        Returns:
            Conversation ID
        
        Raises:
            ConversationException: If creation fails
        """
        # Validate mode
        if mode not in self.config.available_modes:
            raise ConversationException(
                f"Invalid mode '{mode}'. Available: {self.config.available_modes}"
            )
        
        # Generate conversation ID
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"
        
        # Current timestamp
        now = datetime.now(timezone.utc).isoformat()
        
        # Default title
        if title is None:
            title = f"New Conversation - {datetime.now(timezone.utc).strftime('%b %d')}"
        
        # Serialize metadata
        metadata_json = json.dumps(metadata) if metadata else None
        
        try:
            conn = self.storage._conn
            conn.execute("""
                INSERT INTO conversations 
                (conversation_id, user_id, title, kb_id, mode, created_at, updated_at, 
                 message_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conversation_id, user_id, title, kb_id, mode, now, now, 0, metadata_json
            ))
            conn.commit()
            
            logger.info(
                f"Created conversation {conversation_id} for user {user_id}, "
                f"mode={mode}, kb_id={kb_id}"
            )
            
            return conversation_id
            
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            raise ConversationException(f"Failed to create conversation: {e}")
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        token_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a message to a conversation.
        
        Args:
            conversation_id: Conversation ID
            role: Message role ('user' or 'assistant')
            content: Message content
            citations: Optional list of citation dicts
            token_count: Optional token count for message
            metadata: Optional metadata dict (model, mode, retrieval_time, etc.)
        
        Returns:
            Message ID
        
        Raises:
            ConversationException: If conversation not found or add fails
        """
        # Validate role
        if role not in ['user', 'assistant']:
            raise ConversationException(
                f"Invalid role '{role}'. Must be 'user' or 'assistant'"
            )
        
        # Check conversation exists
        if not self.get_conversation(conversation_id):
            raise ConversationException(
                f"Conversation '{conversation_id}' not found"
            )
        
        # Generate message ID
        message_id = f"msg_{uuid.uuid4().hex[:16]}"
        
        # Current timestamp
        now = datetime.now(timezone.utc).isoformat()
        
        # Serialize citations and metadata
        citations_json = json.dumps(citations) if citations else None
        metadata_json = json.dumps(metadata) if metadata else None
        
        try:
            conn = self.storage._conn
            
            # Insert message
            conn.execute("""
                INSERT INTO messages 
                (message_id, conversation_id, role, content, citations, created_at, 
                 token_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, conversation_id, role, content, citations_json, now,
                token_count, metadata_json
            ))
            
            # Update conversation
            conn.execute("""
                UPDATE conversations 
                SET updated_at = ?, message_count = message_count + 1
                WHERE conversation_id = ?
            """, (now, conversation_id))
            
            # Auto-generate title from first user message
            if role == 'user':
                cursor = conn.execute("""
                    SELECT message_count, title FROM conversations 
                    WHERE conversation_id = ?
                """, (conversation_id,))
                row = cursor.fetchone()
                
                if row and row[0] == 1:  # First message
                    # Generate title from message content
                    title = self._generate_title(content)
                    conn.execute("""
                        UPDATE conversations SET title = ? WHERE conversation_id = ?
                    """, (title, conversation_id))
            
            conn.commit()
            
            logger.info(
                f"Added {role} message {message_id} to conversation {conversation_id}"
            )
            
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            raise ConversationException(f"Failed to add message: {e}")
    
    def get_conversation(
        self,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get conversation metadata.
        
        Args:
            conversation_id: Conversation ID
        
        Returns:
            Conversation dict or None if not found
        """
        try:
            conn = self.storage._conn
            cursor = conn.execute("""
                SELECT conversation_id, user_id, title, kb_id, mode, created_at, 
                       updated_at, message_count, metadata
                FROM conversations
                WHERE conversation_id = ?
            """, (conversation_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'conversation_id': row[0],
                'user_id': row[1],
                'title': row[2],
                'kb_id': row[3],
                'mode': row[4],
                'created_at': row[5],
                'updated_at': row[6],
                'message_count': row[7],
                'metadata': json.loads(row[8]) if row[8] else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
            return None
    
    def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
        include_metadata: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a conversation.
        
        Args:
            conversation_id: Conversation ID
            limit: Optional limit on number of messages (most recent)
            include_metadata: Whether to include message metadata
        
        Returns:
            List of message dicts ordered by created_at
        """
        try:
            conn = self.storage._conn
            
            query = """
                SELECT message_id, conversation_id, role, content, citations, 
                       created_at, token_count, metadata
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
            """
            
            if limit:
                query += f" LIMIT {int(limit)}"
            
            cursor = conn.execute(query, (conversation_id,))
            
            messages = []
            for row in cursor.fetchall():
                msg = {
                    'message_id': row[0],
                    'conversation_id': row[1],
                    'role': row[2],
                    'content': row[3],
                    'citations': json.loads(row[4]) if row[4] else None,
                    'created_at': row[5],
                    'token_count': row[6]
                }
                
                if include_metadata:
                    msg['metadata'] = json.loads(row[7]) if row[7] else None
                
                messages.append(msg)
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []
    
    def get_context(
        self,
        conversation_id: str,
        max_messages: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation context for LLM.
        
        Returns recent messages formatted for LLM input,
        respecting max_messages and max_tokens limits.
        
        Args:
            conversation_id: Conversation ID
            max_messages: Maximum number of messages (default: config.max_messages)
            max_tokens: Maximum total tokens (default: config.max_context_tokens)
        
        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        max_messages = max_messages or self.config.max_messages
        max_tokens = max_tokens or self.config.max_context_tokens
        
        # Get recent messages
        messages = self.get_messages(conversation_id, limit=max_messages)
        
        # Format for LLM (only role and content)
        context = []
        total_tokens = 0
        
        # Process in reverse to prioritize recent messages
        for msg in reversed(messages):
            # Skip if we'd exceed token limit
            msg_tokens = msg.get('token_count')
            if not isinstance(msg_tokens, int) or msg_tokens < 0:
                msg_tokens = max(1, len(msg.get('content') or "") // 4)
            
            if total_tokens + msg_tokens > max_tokens:
                logger.info(
                    f"Context token limit reached ({total_tokens}/{max_tokens}), "
                    f"truncating older messages"
                )
                break
            
            context.insert(0, {
                'role': msg['role'],
                'content': msg['content']
            })
            
            total_tokens += msg_tokens
        
        logger.info(
            f"Built context with {len(context)} messages "
            f"(~{total_tokens} tokens) for conversation {conversation_id}"
        )
        
        return context
    
    def list_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List conversations for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of conversations to return
            offset: Offset for pagination
        
        Returns:
            List of conversation dicts (without messages)
        """
        try:
            conn = self.storage._conn
            cursor = conn.execute("""
                SELECT conversation_id, user_id, title, kb_id, mode, created_at, 
                       updated_at, message_count, metadata
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
            
            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'conversation_id': row[0],
                    'user_id': row[1],
                    'title': row[2],
                    'kb_id': row[3],
                    'mode': row[4],
                    'created_at': row[5],
                    'updated_at': row[6],
                    'message_count': row[7],
                    'metadata': json.loads(row[8]) if row[8] else None
                })
            
            return conversations
            
        except Exception as e:
            logger.error(f"Failed to list conversations: {e}")
            return []
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation and all its messages.
        
        Args:
            conversation_id: Conversation ID
        
        Returns:
            True if deleted, False if not found
        """
        try:
            conn = self.storage._conn
            
            # Delete messages first
            conn.execute("""
                DELETE FROM messages WHERE conversation_id = ?
            """, (conversation_id,))
            
            # Delete conversation
            cursor = conn.execute("""
                DELETE FROM conversations WHERE conversation_id = ?
            """, (conversation_id,))
            
            conn.commit()
            
            deleted = cursor.rowcount > 0
            
            if deleted:
                logger.info(f"Deleted conversation {conversation_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
            return False
    
    def update_conversation_title(
        self,
        conversation_id: str,
        title: str
    ) -> bool:
        """
        Update conversation title.
        
        Args:
            conversation_id: Conversation ID
            title: New title
        
        Returns:
            True if updated, False if not found
        """
        try:
            conn = self.storage._conn
            cursor = conn.execute("""
                UPDATE conversations SET title = ? WHERE conversation_id = ?
            """, (title, conversation_id))
            conn.commit()
            
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to update conversation title: {e}")
            return False
    
    def _generate_title(self, first_message: str, max_length: int = 50) -> str:
        """
        Generate conversation title from first message.
        
        Args:
            first_message: First user message
            max_length: Maximum title length
        
        Returns:
            Generated title
        """
        # Simple approach: use first N characters
        # In production, could use LLM to extract key topic
        
        # Clean the message
        message = first_message.strip()
        
        # Remove newlines
        message = message.replace('\n', ' ')
        
        # Truncate if too long
        if len(message) > max_length:
            message = message[:max_length-3] + "..."
        
        # Add date suffix
        date_str = datetime.now(timezone.utc).strftime('%b %d')
        
        return f"{message} - {date_str}"
    
    def get_conversation_stats(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get statistics for a conversation.
        
        Args:
            conversation_id: Conversation ID
        
        Returns:
            Statistics dict with message counts, token counts, etc.
        """
        try:
            conn = self.storage._conn
            
            # Get message counts by role
            cursor = conn.execute("""
                SELECT role, COUNT(*), SUM(COALESCE(token_count, 0))
                FROM messages
                WHERE conversation_id = ?
                GROUP BY role
            """, (conversation_id,))
            
            stats = {
                'user_messages': 0,
                'assistant_messages': 0,
                'total_tokens': 0
            }
            
            for row in cursor.fetchall():
                role, count, tokens = row
                if role == 'user':
                    stats['user_messages'] = count
                elif role == 'assistant':
                    stats['assistant_messages'] = count
                stats['total_tokens'] += tokens or 0
            
            stats['total_messages'] = stats['user_messages'] + stats['assistant_messages']
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get conversation stats: {e}")
            return {}

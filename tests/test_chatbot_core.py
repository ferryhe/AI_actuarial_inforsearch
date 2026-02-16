#!/usr/bin/env python3
"""
Unit tests for chatbot core components.

Tests ChatbotConfig, prompts, QueryRouter, and ConversationManager
with mocked external dependencies.
"""

import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Mock schedule module
if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.conversation import ConversationManager
from ai_actuarial.chatbot.exceptions import (
    ChatbotException,
    ConversationException,
    InvalidKBException,
    InvalidModeException,
)
from ai_actuarial.chatbot.prompts import (
    BASE_INSTRUCTIONS,
    MODE_PROMPTS,
    build_full_prompt,
    format_context_prompt,
    format_user_query,
    get_system_prompt,
)
from ai_actuarial.chatbot.router import QueryRouter
from ai_actuarial.storage import Storage


class TestChatbotConfig(unittest.TestCase):
    """Test ChatbotConfig initialization and validation."""
    
    def setUp(self):
        """Set up test environment."""
        # Save original env vars
        self.original_env = dict(os.environ)
        
        # Clear chatbot-related env vars
        for key in list(os.environ.keys()):
            if key.startswith(('CHATBOT_', 'OPENAI_', 'RAG_')):
                del os.environ[key]
    
    def tearDown(self):
        """Restore original environment."""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_default_initialization(self):
        """Test default configuration initialization."""
        config = ChatbotConfig()
        
        self.assertEqual(config.llm_provider, "openai")
        self.assertEqual(config.model, "gpt-4")
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.max_tokens, 1000)
        self.assertEqual(config.top_k, 5)
        self.assertEqual(config.similarity_threshold, 0.4)
        self.assertEqual(config.default_mode, "expert")
        self.assertIn("expert", config.available_modes)
    
    def test_env_override(self):
        """Test environment variable overrides."""
        os.environ["OPENAI_API_KEY"] = "test-key-123"
        os.environ["CHATBOT_MODEL"] = "gpt-3.5-turbo"
        os.environ["CHATBOT_TEMPERATURE"] = "0.5"
        os.environ["CHATBOT_MAX_TOKENS"] = "500"
        os.environ["CHATBOT_TOP_K"] = "3"
        os.environ["RAG_SIMILARITY_THRESHOLD"] = "0.6"
        
        config = ChatbotConfig()
        
        self.assertEqual(config.api_key, "test-key-123")
        self.assertEqual(config.model, "gpt-3.5-turbo")
        self.assertEqual(config.temperature, 0.5)
        self.assertEqual(config.max_tokens, 500)
        self.assertEqual(config.top_k, 3)
        self.assertEqual(config.similarity_threshold, 0.6)
    
    def test_validation_success(self):
        """Test successful configuration validation."""
        config = ChatbotConfig(api_key="test-key")
        
        result = config.validate()
        self.assertTrue(result)
    
    def test_validation_missing_api_key(self):
        """Test validation fails with missing API key."""
        config = ChatbotConfig(api_key=None)
        
        with self.assertRaises(ValueError) as ctx:
            config.validate()
        
        self.assertIn("API key is required", str(ctx.exception))
    
    def test_validation_invalid_temperature(self):
        """Test validation fails with invalid temperature."""
        config = ChatbotConfig(api_key="test", temperature=3.0)
        
        with self.assertRaises(ValueError) as ctx:
            config.validate()
        
        self.assertIn("Temperature must be between 0 and 2", str(ctx.exception))
    
    def test_validation_invalid_top_k(self):
        """Test validation fails with invalid top_k."""
        config = ChatbotConfig(api_key="test", top_k=0)
        
        with self.assertRaises(ValueError) as ctx:
            config.validate()
        
        self.assertIn("top_k must be positive", str(ctx.exception))
    
    def test_validation_invalid_threshold(self):
        """Test validation fails with invalid similarity threshold."""
        config = ChatbotConfig(api_key="test", similarity_threshold=1.5)
        
        with self.assertRaises(ValueError) as ctx:
            config.validate()
        
        self.assertIn("similarity_threshold must be between 0 and 1", str(ctx.exception))
    
    def test_validation_invalid_mode(self):
        """Test validation fails with invalid default mode."""
        config = ChatbotConfig(api_key="test", default_mode="invalid_mode")
        
        with self.assertRaises(ValueError) as ctx:
            config.validate()
        
        self.assertIn("default_mode", str(ctx.exception))


class TestPrompts(unittest.TestCase):
    """Test prompt generation functions."""
    
    def test_get_system_prompt_expert(self):
        """Test getting expert mode system prompt."""
        prompt = get_system_prompt("expert")
        
        self.assertIn("EXPERT MODE", prompt)
        self.assertIn(BASE_INSTRUCTIONS, prompt)
        self.assertIn("technical", prompt.lower())
    
    def test_get_system_prompt_summary(self):
        """Test getting summary mode system prompt."""
        prompt = get_system_prompt("summary")
        
        self.assertIn("SUMMARY MODE", prompt)
        self.assertIn(BASE_INSTRUCTIONS, prompt)
        self.assertIn("concise", prompt.lower())
    
    def test_get_system_prompt_tutorial(self):
        """Test getting tutorial mode system prompt."""
        prompt = get_system_prompt("tutorial")
        
        self.assertIn("TUTORIAL MODE", prompt)
        self.assertIn(BASE_INSTRUCTIONS, prompt)
        self.assertIn("step-by-step", prompt.lower())
    
    def test_get_system_prompt_comparison(self):
        """Test getting comparison mode system prompt."""
        prompt = get_system_prompt("comparison")
        
        self.assertIn("COMPARISON MODE", prompt)
        self.assertIn(BASE_INSTRUCTIONS, prompt)
        self.assertIn("comparison", prompt.lower())
    
    def test_get_system_prompt_base_only(self):
        """Test getting base instructions only."""
        prompt = get_system_prompt("expert", base_only=True)
        
        self.assertEqual(prompt, BASE_INSTRUCTIONS)
        self.assertNotIn("EXPERT MODE", prompt)
    
    def test_get_system_prompt_invalid_mode(self):
        """Test invalid mode raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            get_system_prompt("invalid_mode")
        
        self.assertIn("Unknown chatbot mode", str(ctx.exception))
    
    def test_format_context_prompt_with_chunks(self):
        """Test formatting context prompt with retrieved chunks."""
        chunks = [
            {
                "content": "Test content 1",
                "metadata": {
                    "filename": "test1.pdf",
                    "kb_name": "General",
                    "similarity_score": 0.9
                }
            },
            {
                "content": "Test content 2",
                "metadata": {
                    "filename": "test2.pdf",
                    "kb_name": "Specific",
                    "similarity_score": 0.8
                }
            }
        ]
        
        prompt = format_context_prompt(chunks)
        
        self.assertIn("RETRIEVED INFORMATION", prompt)
        self.assertIn("test1.pdf", prompt)
        self.assertIn("test2.pdf", prompt)
        self.assertIn("Test content 1", prompt)
        self.assertIn("Test content 2", prompt)
        self.assertIn("0.90", prompt)
        self.assertIn("0.80", prompt)
    
    def test_format_context_prompt_with_history(self):
        """Test formatting context prompt with conversation history."""
        history = [
            {"role": "user", "content": "What is Solvency II?"},
            {"role": "assistant", "content": "Solvency II is..."}
        ]
        
        prompt = format_context_prompt([], history)
        
        self.assertIn("CONVERSATION HISTORY", prompt)
        self.assertIn("User: What is Solvency II?", prompt)
        self.assertIn("Assistant: Solvency II is...", prompt)
    
    def test_format_context_prompt_empty(self):
        """Test formatting empty context prompt."""
        prompt = format_context_prompt([])
        
        self.assertEqual(prompt, "")
    
    def test_format_user_query(self):
        """Test formatting user query."""
        query = "What is the capital requirement?"
        formatted = format_user_query(query)
        
        self.assertIn("USER QUERY", formatted)
        self.assertIn(query, formatted)
    
    def test_build_full_prompt(self):
        """Test building full prompt for LLM."""
        chunks = [
            {
                "content": "Capital requirements are...",
                "metadata": {
                    "filename": "regulation.pdf",
                    "kb_name": "General",
                    "similarity_score": 0.85
                }
            }
        ]
        
        messages = build_full_prompt(
            mode="expert",
            retrieved_chunks=chunks,
            query="What are capital requirements?",
            conversation_history=[]
        )
        
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        
        # System message should contain mode-specific prompt
        self.assertIn("EXPERT MODE", messages[0]["content"])
        
        # User message should contain context and query
        self.assertIn("Capital requirements are...", messages[1]["content"])
        self.assertIn("What are capital requirements?", messages[1]["content"])


class TestConversationManager(unittest.TestCase):
    """Test ConversationManager functionality."""
    
    def setUp(self):
        """Set up test database and manager."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)
        self.config = ChatbotConfig(api_key="test-key")
        self.manager = ConversationManager(self.storage, self.config)
    
    def tearDown(self):
        """Clean up test database."""
        self.storage.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_conversation(self):
        """Test creating a new conversation."""
        conv_id = self.manager.create_conversation(
            user_id="test_user",
            kb_id="test_kb",
            mode="expert"
        )
        
        self.assertTrue(conv_id.startswith("conv_"))
        
        # Verify conversation was created
        conv = self.manager.get_conversation(conv_id)
        self.assertIsNotNone(conv)
        self.assertEqual(conv["user_id"], "test_user")
        self.assertEqual(conv["kb_id"], "test_kb")
        self.assertEqual(conv["mode"], "expert")
        self.assertEqual(conv["message_count"], 0)
    
    def test_create_conversation_invalid_mode(self):
        """Test creating conversation with invalid mode."""
        with self.assertRaises(ConversationException) as ctx:
            self.manager.create_conversation(
                user_id="test_user",
                mode="invalid_mode"
            )
        
        self.assertIn("Invalid mode", str(ctx.exception))
    
    def test_create_conversation_with_metadata(self):
        """Test creating conversation with metadata."""
        metadata = {"source": "web", "kb_ids": ["kb1", "kb2"]}
        
        conv_id = self.manager.create_conversation(
            user_id="test_user",
            metadata=metadata
        )
        
        conv = self.manager.get_conversation(conv_id)
        self.assertEqual(conv["metadata"], metadata)
    
    def test_add_message(self):
        """Test adding messages to conversation."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        # Add user message
        msg_id = self.manager.add_message(
            conversation_id=conv_id,
            role="user",
            content="What is Solvency II?"
        )
        
        self.assertTrue(msg_id.startswith("msg_"))
        
        # Verify message was added
        messages = self.manager.get_messages(conv_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "What is Solvency II?")
    
    def test_add_message_invalid_role(self):
        """Test adding message with invalid role."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        with self.assertRaises(ConversationException) as ctx:
            self.manager.add_message(
                conversation_id=conv_id,
                role="invalid_role",
                content="test"
            )
        
        self.assertIn("Invalid role", str(ctx.exception))
    
    def test_add_message_nonexistent_conversation(self):
        """Test adding message to nonexistent conversation."""
        with self.assertRaises(ConversationException) as ctx:
            self.manager.add_message(
                conversation_id="nonexistent",
                role="user",
                content="test"
            )
        
        self.assertIn("not found", str(ctx.exception))
    
    def test_add_message_with_citations(self):
        """Test adding message with citations."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        citations = [
            {
                "filename": "test.pdf",
                "kb_id": "test_kb",
                "similarity_score": 0.9
            }
        ]
        
        msg_id = self.manager.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="Response...",
            citations=citations
        )
        
        messages = self.manager.get_messages(conv_id)
        self.assertEqual(len(messages[0]["citations"]), 1)
        self.assertEqual(messages[0]["citations"][0]["filename"], "test.pdf")
    
    def test_get_conversation_nonexistent(self):
        """Test getting nonexistent conversation returns None."""
        result = self.manager.get_conversation("nonexistent")
        self.assertIsNone(result)
    
    def test_get_messages_empty(self):
        """Test getting messages for empty conversation."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        messages = self.manager.get_messages(conv_id)
        self.assertEqual(len(messages), 0)
    
    def test_get_messages_with_limit(self):
        """Test getting messages with limit."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        # Add multiple messages
        for i in range(5):
            self.manager.add_message(
                conversation_id=conv_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}"
            )
        
        # Get only last 3 messages
        messages = self.manager.get_messages(conv_id, limit=3)
        self.assertEqual(len(messages), 3)
    
    def test_get_context(self):
        """Test getting conversation context for LLM."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        # Add messages with token counts
        self.manager.add_message(conv_id, "user", "Question 1", token_count=10)
        self.manager.add_message(conv_id, "assistant", "Answer 1", token_count=20)
        self.manager.add_message(conv_id, "user", "Question 2", token_count=10)
        
        context = self.manager.get_context(conv_id)
        
        self.assertEqual(len(context), 3)
        self.assertEqual(context[0]["role"], "user")
        self.assertEqual(context[0]["content"], "Question 1")
        self.assertEqual(context[1]["role"], "assistant")
        self.assertEqual(context[2]["role"], "user")
    
    def test_list_conversations(self):
        """Test listing user conversations."""
        # Create multiple conversations
        conv1 = self.manager.create_conversation(user_id="user1")
        conv2 = self.manager.create_conversation(user_id="user1")
        conv3 = self.manager.create_conversation(user_id="user2")
        
        # List conversations for user1
        conversations = self.manager.list_conversations("user1")
        
        self.assertEqual(len(conversations), 2)
        conv_ids = [c["conversation_id"] for c in conversations]
        self.assertIn(conv1, conv_ids)
        self.assertIn(conv2, conv_ids)
        self.assertNotIn(conv3, conv_ids)
    
    def test_delete_conversation(self):
        """Test deleting conversation."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        self.manager.add_message(conv_id, "user", "Test message")
        
        # Delete conversation
        result = self.manager.delete_conversation(conv_id)
        self.assertTrue(result)
        
        # Verify deleted
        conv = self.manager.get_conversation(conv_id)
        self.assertIsNone(conv)
        
        messages = self.manager.get_messages(conv_id)
        self.assertEqual(len(messages), 0)
    
    def test_delete_nonexistent_conversation(self):
        """Test deleting nonexistent conversation returns False."""
        result = self.manager.delete_conversation("nonexistent")
        self.assertFalse(result)
    
    def test_update_conversation_title(self):
        """Test updating conversation title."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        result = self.manager.update_conversation_title(conv_id, "New Title")
        self.assertTrue(result)
        
        conv = self.manager.get_conversation(conv_id)
        self.assertEqual(conv["title"], "New Title")
    
    def test_get_conversation_stats(self):
        """Test getting conversation statistics."""
        conv_id = self.manager.create_conversation(user_id="test_user")
        
        # Add messages
        self.manager.add_message(conv_id, "user", "Q1", token_count=10)
        self.manager.add_message(conv_id, "assistant", "A1", token_count=50)
        self.manager.add_message(conv_id, "user", "Q2", token_count=15)
        
        stats = self.manager.get_conversation_stats(conv_id)
        
        self.assertEqual(stats["user_messages"], 2)
        self.assertEqual(stats["assistant_messages"], 1)
        self.assertEqual(stats["total_messages"], 3)
        self.assertEqual(stats["total_tokens"], 75)


class TestQueryRouter(unittest.TestCase):
    """Test QueryRouter KB selection logic."""
    
    def setUp(self):
        """Set up test database and router."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)
        self.config = ChatbotConfig(api_key="test-key")
        
        # Initialize RAG schema
        self._init_rag_schema()
        
        # Create mock KBs
        self._create_mock_kbs()
        
        # Mock KnowledgeBaseManager to avoid tiktoken initialization
        with patch('ai_actuarial.chatbot.router.KnowledgeBaseManager'):
            self.router = QueryRouter(self.storage, self.config)
            # Manually set kb_manager as we need to mock its methods
            self.router.kb_manager = Mock()
    
    def tearDown(self):
        """Clean up test database."""
        self.storage.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _init_rag_schema(self):
        """Initialize RAG database schema."""
        conn = self.storage._conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                embedding_model TEXT DEFAULT 'text-embedding-3-small',
                chunk_size INTEGER DEFAULT 512,
                chunk_overlap INTEGER DEFAULT 50,
                kb_mode TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_path TEXT
            )
        """)
        conn.commit()
    
    def _create_mock_kbs(self):
        """Create mock knowledge bases."""
        conn = self.storage._conn
        now = datetime.now(timezone.utc).isoformat()
        
        kbs = [
            ("kb_regulation", "Regulatory Documents", "Solvency II and IFRS 17 regulations"),
            ("kb_products", "Insurance Products", "Life insurance and annuity products"),
            ("kb_math", "Actuarial Mathematics", "Formulas and calculations")
        ]
        
        for kb_id, name, desc in kbs:
            conn.execute("""
                INSERT INTO rag_knowledge_bases 
                (kb_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (kb_id, name, desc, now, now))
        
        conn.commit()
    
    def test_analyze_query_factual(self):
        """Test analyzing factual query."""
        query = "What is the Solvency II capital requirement?"
        
        analysis = self.router.analyze_query(query)
        
        # "What is" matches explanatory intent, which is correct
        self.assertEqual(analysis["intent"], "explanatory")
        self.assertIn("regulation", analysis["categories"])
        self.assertTrue(analysis["has_question_mark"])
    
    def test_analyze_query_comparative(self):
        """Test analyzing comparative query."""
        query = "Compare term life and whole life insurance"
        
        analysis = self.router.analyze_query(query)
        
        self.assertEqual(analysis["intent"], "comparative")
        self.assertIn("products", analysis["categories"])
    
    def test_analyze_query_procedural(self):
        """Test analyzing procedural query."""
        query = "How to calculate present value of annuity?"
        
        analysis = self.router.analyze_query(query)
        
        self.assertEqual(analysis["intent"], "procedural")
        self.assertIn("mathematics", analysis["categories"])
    
    def test_extract_keywords(self):
        """Test keyword extraction."""
        query = "What is the capital requirement for life insurance companies?"
        
        keywords = self.router._extract_keywords(query)
        
        self.assertIn("capital", keywords)
        self.assertIn("requirement", keywords)
        self.assertIn("life", keywords)
        self.assertIn("insurance", keywords)
        # Stopwords should be removed
        self.assertNotIn("the", keywords)
        self.assertNotIn("for", keywords)
    
    def test_extract_entities(self):
        """Test entity extraction."""
        query = "What are the requirements under Solvency II and IFRS 17?"
        
        entities = self.router._extract_entities(query)
        
        self.assertIn("solvency ii", entities)
        self.assertIn("ifrs 17", entities)
    
    def test_classify_categories(self):
        """Test category classification."""
        query = "What is the mortality rate used in premium calculation?"
        
        categories = self.router._classify_categories(query)
        
        self.assertIn("mathematics", categories)
    
    def test_recommend_mode_comparison(self):
        """Test mode recommendation for comparative queries."""
        analysis = {"intent": "comparative", "complexity": "medium"}
        
        mode = self.router.recommend_mode(analysis)
        
        self.assertEqual(mode, "comparison")
    
    def test_recommend_mode_tutorial(self):
        """Test mode recommendation for procedural queries."""
        analysis = {"intent": "procedural", "complexity": "low"}
        
        mode = self.router.recommend_mode(analysis)
        
        self.assertEqual(mode, "tutorial")
    
    def test_recommend_mode_expert(self):
        """Test mode recommendation for complex queries."""
        analysis = {"intent": "explanatory", "complexity": "high"}
        
        mode = self.router.recommend_mode(analysis)
        
        self.assertEqual(mode, "expert")


if __name__ == "__main__":
    unittest.main()

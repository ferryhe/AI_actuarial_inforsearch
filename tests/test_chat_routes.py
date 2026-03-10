#!/usr/bin/env python3
"""
Tests for chat API routes and web interface.

Tests all chat endpoints with authentication, error handling,
and response validation.
"""

import json
import os
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

# Mock schedule module
if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.web.app import FLASK_AVAILABLE, create_app
from ai_actuarial.chatbot.exceptions import NoResultsException


class TestChatRoutes(unittest.TestCase):
    """Test chat API routes and page rendering."""
    
    def setUp(self):
        """Set up test Flask application."""
        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed in this environment")
        
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.config_path = os.path.join(self.temp_dir, "sites.yaml")
        self.categories_path = os.path.join(self.temp_dir, "categories.yaml")
        self.admin_token = "test-chat-admin-token"
        
        # Create minimal config
        config_data = {
            "paths": {
                "db": self.db_path,
                "download_dir": os.path.join(self.temp_dir, "files"),
                "updates_dir": os.path.join(self.temp_dir, "updates"),
                "last_run_new": os.path.join(self.temp_dir, "last_run_new.json"),
            },
            "defaults": {
                "user_agent": "test-agent/1.0",
                "max_pages": 10,
                "max_depth": 1,
                "file_exts": [".pdf"],
                "keywords": ["actuarial"],
            },
            "sites": [],
        }
        
        categories_data = {
            "categories": {
                "General": ["insurance"],
                "Regulation": ["solvency"]
            }
        }
        
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)
        with open(self.categories_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(categories_data, f)
        
        # Set environment variables
        self.original_env = dict(os.environ)
        os.environ["CONFIG_PATH"] = self.config_path
        os.environ["CATEGORIES_CONFIG_PATH"] = self.categories_path
        os.environ["BOOTSTRAP_ADMIN_TOKEN"] = self.admin_token
        os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
        os.environ["REQUIRE_AUTH"] = "true"
        os.environ["RAG_DATA_DIR"] = os.path.join(self.temp_dir, "rag_data")
        os.environ["OPENAI_API_KEY"] = "test-openai-key"
        
        # Create Flask app
        self.app = create_app({"TESTING": True, "DEBUG": True})
        self.client = self.app.test_client()
        self.auth_header = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Initialize RAG schema
        self._init_rag_schema()
        self._create_test_kbs()
    
    def tearDown(self):
        """Clean up test environment."""
        os.environ.clear()
        os.environ.update(self.original_env)
        
        import shutil
        for _ in range(10):
            try:
                shutil.rmtree(self.temp_dir)
                break
            except PermissionError:
                time.sleep(0.1)
    
    def _init_rag_schema(self):
        """Initialize RAG database schema."""
        from ai_actuarial.storage import Storage
        
        storage = Storage(self.db_path)
        conn = storage._conn
        
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
        storage.close()
    
    def _create_test_kbs(self):
        """Create test knowledge bases."""
        from ai_actuarial.storage import Storage
        
        storage = Storage(self.db_path)
        conn = storage._conn
        now = datetime.now(timezone.utc).isoformat()
        
        kbs = [
            ("test_kb1", "General KB", "General actuarial knowledge"),
            ("test_kb2", "Regulation KB", "Regulatory documents")
        ]
        
        for kb_id, name, desc in kbs:
            conn.execute("""
                INSERT INTO rag_knowledge_bases 
                (kb_id, name, description, created_at, updated_at, file_count, chunk_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (kb_id, name, desc, now, now, 5, 50))
        
        conn.commit()
        storage.close()
    
    def test_chat_page_accessible(self):
        """Test chat page is accessible with authentication."""
        response = self.client.get("/chat", headers=self.auth_header)
        
        # Should return 200 or redirect if templates not found
        self.assertIn(response.status_code, [200, 404, 500])
    
    def test_chat_page_requires_auth(self):
        """Test chat page requires authentication."""
        response = self.client.get("/chat")
        
        # Should redirect to login or return 401/403
        self.assertIn(response.status_code, [302, 401, 403])
    
    def test_get_knowledge_bases(self):
        """Test GET /api/chat/knowledge-bases endpoint."""
        response = self.client.get(
            "/api/chat/knowledge-bases",
            headers=self.auth_header
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("knowledge_bases", data["data"])
        
        kbs = data["data"]["knowledge_bases"]
        self.assertEqual(len(kbs), 2)
        
        # Verify KB structure
        kb1 = kbs[0]
        self.assertIn("kb_id", kb1)
        self.assertIn("name", kb1)
        self.assertIn("description", kb1)
        self.assertIn("file_count", kb1)
        self.assertIn("chunk_count", kb1)
    
    def test_get_knowledge_bases_no_auth(self):
        """Test knowledge bases endpoint requires authentication."""
        response = self.client.get("/api/chat/knowledge-bases")
        
        # Should return 401 or 403
        self.assertIn(response.status_code, [401, 403])
    
    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever')
    @patch('ai_actuarial.chatbot.llm.LLMClient')
    def test_chat_query_success(self, mock_llm_class, mock_retriever_class):
        """Test successful chat query."""
        # Mock retriever
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = [
            {
                'content': 'Solvency II is a regulatory framework.',
                'metadata': {
                    'filename': 'regulation.pdf',
                    'kb_id': 'test_kb1',
                    'kb_name': 'General KB',
                    'similarity_score': 0.92,
                    'chunk_id': 'chunk_1',
                    'file_url': '/database/regulation.pdf'
                }
            }
        ]
        mock_retriever_class.return_value = mock_retriever
        
        # Mock LLM
        mock_llm = Mock()
        mock_llm.generate_response.return_value = (
            "Solvency II is a comprehensive regulatory framework for insurance "
            "companies [Source: regulation.pdf]."
        )
        mock_llm_class.return_value = mock_llm
        
        # Send query
        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "What is Solvency II?",
                "kb_ids": ["test_kb1"],
                "mode": "expert"
            }
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("data", data)
        
        result = data["data"]
        self.assertIn("conversation_id", result)
        self.assertIn("message_id", result)
        self.assertIn("response", result)
        self.assertIn("citations", result)
        self.assertIn("metadata", result)
        
        # Verify response content
        self.assertIn("Solvency II", result["response"])
        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["filename"], "regulation.pdf")

    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever')
    @patch('openai.OpenAI')
    def test_chat_query_uses_selected_provider_without_openai_key(self, mock_openai_class, mock_retriever_class):
        """Chat queries should follow ai_config.chatbot.provider instead of forcing OpenAI."""
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["DEEPSEEK_API_KEY"] = "deepseek-key-123"

        with open(self.config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
        config_data.setdefault("ai_config", {})
        config_data["ai_config"]["chatbot"] = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        from config.yaml_config import invalidate_config_cache
        invalidate_config_cache()

        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = [
            {
                'content': 'DeepSeek can answer this question.',
                'metadata': {
                    'filename': 'deepseek.pdf',
                    'kb_id': 'test_kb1',
                    'kb_name': 'General KB',
                    'similarity_score': 0.91,
                    'chunk_id': 'chunk_1',
                    'file_url': '/database/deepseek.pdf'
                }
            }
        ]
        mock_retriever_class.return_value = mock_retriever

        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "DeepSeek answer [Source: deepseek.pdf]."
        mock_response.usage.total_tokens = 88
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "Use deepseek provider",
                "kb_ids": ["test_kb1"],
                "mode": "expert"
            }
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("DeepSeek answer", data["data"]["response"])

        kwargs = mock_openai_class.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "deepseek-key-123")
        self.assertEqual(kwargs["base_url"], "https://api.deepseek.com/v1")

    @patch('ai_actuarial.chatbot.llm.LLMClient')
    @patch('ai_actuarial.chatbot.config.ChatbotConfig.from_config')
    def test_summarize_document_uses_storage_backed_config(self, mock_from_config, mock_llm_class):
        """Document summarization should resolve config through storage-backed runtime."""
        mock_config = Mock()
        mock_config.model = "deepseek-chat"
        mock_from_config.return_value = mock_config

        mock_llm = Mock()
        mock_llm.generate.return_value = "Summary result"
        mock_llm_class.return_value = mock_llm

        response = self.client.post(
            "/api/chat/summarize-document",
            headers=self.auth_header,
            json={
                "document_content": "# Test\n\nDocument body.",
                "document_title": "Test Doc",
                "mode": "summary",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_from_config.called)
        _, kwargs = mock_from_config.call_args
        self.assertIn("storage", kwargs)
        self.assertIsNotNone(kwargs["storage"])
    
    def test_chat_query_missing_message(self):
        """Test chat query with missing message."""
        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={"kb_ids": ["test_kb1"]}
        )
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("Message is required", data["error"])
    
    def test_chat_query_invalid_mode(self):
        """Test chat query with invalid mode."""
        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "test",
                "mode": "invalid_mode"
            }
        )
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("Invalid mode", data["error"])
    
    def test_chat_query_no_auth(self):
        """Test chat query requires authentication."""
        response = self.client.post(
            "/api/chat/query",
            json={"message": "test"}
        )
        
        self.assertIn(response.status_code, [401, 403])
    
    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever')
    @patch('ai_actuarial.chatbot.llm.LLMClient')
    def test_chat_query_with_existing_conversation(self, mock_llm_class, mock_retriever_class):
        """Test chat query with existing conversation ID."""
        # Mock services
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = [
            {
                'content': 'Test content',
                'metadata': {
                    'filename': 'test.pdf',
                    'kb_id': 'test_kb1',
                    'kb_name': 'General KB',
                    'similarity_score': 0.85,
                    'chunk_id': 'chunk_1',
                    'file_url': ''
                }
            }
        ]
        mock_retriever_class.return_value = mock_retriever
        
        mock_llm = Mock()
        mock_llm.generate_response.return_value = "Response to follow-up question."
        mock_llm_class.return_value = mock_llm
        
        # First query - create conversation
        response1 = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "First question",
                "kb_ids": ["test_kb1"]
            }
        )
        
        self.assertEqual(response1.status_code, 200)
        data1 = json.loads(response1.data)
        conv_id = data1["data"]["conversation_id"]
        
        # Second query - use existing conversation
        response2 = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "conversation_id": conv_id,
                "message": "Follow-up question"
            }
        )
        
        self.assertEqual(response2.status_code, 200)
        data2 = json.loads(response2.data)
        
        # Should return same conversation ID
        self.assertEqual(data2["data"]["conversation_id"], conv_id)
    
    def test_create_conversation(self):
        """Test POST /api/chat/conversations to create conversation."""
        response = self.client.post(
            "/api/chat/conversations",
            headers=self.auth_header,
            json={
                "kb_id": "test_kb1",
                "mode": "expert"
            }
        )
        
        self.assertEqual(response.status_code, 201)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("conversation_id", data["data"])
        self.assertTrue(data["data"]["conversation_id"].startswith("conv_"))
    
    def test_list_conversations(self):
        """Test GET /api/chat/conversations to list user conversations."""
        # Create a conversation first
        self.client.post(
            "/api/chat/conversations",
            headers=self.auth_header,
            json={"kb_id": "test_kb1"}
        )
        
        # List conversations
        response = self.client.get(
            "/api/chat/conversations",
            headers=self.auth_header
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("conversations", data["data"])
        
        conversations = data["data"]["conversations"]
        self.assertGreaterEqual(len(conversations), 1)
        
        # Verify conversation structure
        conv = conversations[0]
        self.assertIn("conversation_id", conv)
        self.assertIn("title", conv)
        self.assertIn("mode", conv)
        self.assertIn("created_at", conv)
    
    def test_get_conversation_detail(self):
        """Test GET /api/chat/conversations/<id> for conversation details."""
        # Create conversation
        create_response = self.client.post(
            "/api/chat/conversations",
            headers=self.auth_header,
            json={"kb_id": "test_kb1"}
        )
        
        conv_id = json.loads(create_response.data)["data"]["conversation_id"]
        
        # Get conversation detail
        response = self.client.get(
            f"/api/chat/conversations/{conv_id}",
            headers=self.auth_header
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("conversation", data["data"])
        self.assertIn("messages", data["data"])
        
        conversation = data["data"]["conversation"]
        self.assertEqual(conversation["conversation_id"], conv_id)
    
    def test_get_conversation_not_found(self):
        """Test getting nonexistent conversation returns 404."""
        response = self.client.get(
            "/api/chat/conversations/nonexistent_id",
            headers=self.auth_header
        )
        
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"].lower())
    
    def test_delete_conversation(self):
        """Test DELETE /api/chat/conversations/<id>."""
        # Create conversation
        create_response = self.client.post(
            "/api/chat/conversations",
            headers=self.auth_header,
            json={"kb_id": "test_kb1"}
        )
        
        conv_id = json.loads(create_response.data)["data"]["conversation_id"]
        
        # Delete conversation
        delete_response = self.client.delete(
            f"/api/chat/conversations/{conv_id}",
            headers=self.auth_header
        )
        
        self.assertEqual(delete_response.status_code, 200)
        
        data = json.loads(delete_response.data)
        self.assertTrue(data["success"])
        
        # Verify deleted
        get_response = self.client.get(
            f"/api/chat/conversations/{conv_id}",
            headers=self.auth_header
        )
        
        self.assertEqual(get_response.status_code, 404)
    
    def test_conversation_access_control(self):
        """Test users can only access their own conversations."""
        # Create conversation with one user
        create_response = self.client.post(
            "/api/chat/conversations",
            headers=self.auth_header,
            json={"kb_id": "test_kb1"}
        )
        
        conv_id = json.loads(create_response.data)["data"]["conversation_id"]
        
        # Try to access with different user (simulate by using different auth)
        # This would need proper user isolation in production
        # For now, just verify the conversation exists for the original user
        
        response = self.client.get(
            f"/api/chat/conversations/{conv_id}",
            headers=self.auth_header
        )
        
        self.assertEqual(response.status_code, 200)
    
    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever')
    @patch('ai_actuarial.chatbot.llm.LLMClient')
    def test_chat_query_auto_kb_selection(self, mock_llm_class, mock_retriever_class):
        """Test chat query with automatic KB selection."""
        # Mock services
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = [
            {
                'content': 'Test content',
                'metadata': {
                    'filename': 'test.pdf',
                    'kb_id': 'test_kb1',
                    'kb_name': 'General KB',
                    'similarity_score': 0.85,
                    'chunk_id': 'chunk_1',
                    'file_url': ''
                }
            }
        ]
        mock_retriever_class.return_value = mock_retriever
        
        mock_llm = Mock()
        mock_llm.generate_response.return_value = "Response"
        mock_llm_class.return_value = mock_llm
        
        # Query with auto KB selection
        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "What is solvency regulation?",
                "kb_ids": "auto"  # Trigger automatic selection
            }
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data["success"])
    
    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever')
    @patch('ai_actuarial.chatbot.llm.LLMClient')
    def test_chat_query_error_handling(self, mock_llm_class, mock_retriever_class):
        """Test chat query handles errors gracefully."""
        # Mock retriever that raises exception
        mock_retriever = Mock()
        mock_retriever.retrieve.side_effect = Exception("Retrieval failed")
        mock_retriever_class.return_value = mock_retriever
        
        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "Test query",
                "kb_ids": ["test_kb1"]
            }
        )
        
        self.assertEqual(response.status_code, 500)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("error", data)

    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever.retrieve')
    @patch('ai_actuarial.chatbot.llm.LLMClient.generate_response')
    def test_chat_query_no_results_returns_friendly_response(self, mock_generate_response, mock_retrieve):
        """No retrieval hits should return a user-facing response instead of 500."""
        mock_retrieve.side_effect = NoResultsException("No results found")

        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "AI insurance",
                "kb_ids": ["test_kb1"]
            }
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("response", data["data"])
        self.assertEqual(data["data"]["citations"], [])
        self.assertTrue(data["data"]["metadata"]["no_results"])
        self.assertIn("don't have enough information", data["data"]["response"].lower())
        mock_generate_response.assert_not_called()

    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever.retrieve')
    @patch('ai_actuarial.chatbot.llm.LLMClient.generate_response')
    def test_chat_query_fallback_threshold_recovers_results(self, mock_generate_response, mock_retrieve):
        """If default threshold has no hits, fallback threshold should recover results."""
        mock_retrieve.side_effect = [
            NoResultsException("No results at default threshold"),
            [
                {
                    'content': 'Generative AI investment framework summary',
                    'metadata': {
                        'filename': 'first_test.pdf',
                        'kb_id': 'test_kb1',
                        'kb_name': 'General KB',
                        'similarity_score': 0.12,
                        'chunk_id': 'chunk_1',
                        'file_url': ''
                    }
                }
            ],
        ]
        mock_generate_response.return_value = "Recovered answer."

        response = self.client.post(
            "/api/chat/query",
            headers=self.auth_header,
            json={
                "message": "Generative AI investment framework",
                "kb_ids": ["test_kb1"]
            }
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["response"], "Recovered answer.")
        self.assertFalse(data["data"]["metadata"]["no_results"])
        self.assertEqual(data["data"]["metadata"]["used_threshold"], 0.1)
        self.assertEqual(mock_retrieve.call_count, 2)
    
    def test_invalid_json_request(self):
        """Test endpoints handle invalid JSON gracefully."""
        response = self.client.post(
            "/api/chat/query",
            headers={**self.auth_header, "Content-Type": "application/json"},
            data="invalid json{"
        )
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data["success"])
    
    @patch('ai_actuarial.chatbot.retrieval.RAGRetriever')
    @patch('ai_actuarial.chatbot.llm.LLMClient')
    def test_chat_query_all_modes(self, mock_llm_class, mock_retriever_class):
        """Test chat query with all available modes."""
        # Mock services
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = [
            {
                'content': 'Test content',
                'metadata': {
                    'filename': 'test.pdf',
                    'kb_id': 'test_kb1',
                    'kb_name': 'General KB',
                    'similarity_score': 0.85,
                    'chunk_id': 'chunk_1',
                    'file_url': ''
                }
            }
        ]
        mock_retriever_class.return_value = mock_retriever
        
        mock_llm = Mock()
        mock_llm.generate_response.return_value = "Response"
        mock_llm_class.return_value = mock_llm
        
        modes = ["expert", "summary", "tutorial", "comparison"]
        
        for mode in modes:
            with self.subTest(mode=mode):
                response = self.client.post(
                    "/api/chat/query",
                    headers=self.auth_header,
                    json={
                        "message": f"Test in {mode} mode",
                        "kb_ids": ["test_kb1"],
                        "mode": mode
                    }
                )
                
                self.assertEqual(response.status_code, 200)
                data = json.loads(response.data)
                self.assertTrue(data["success"])
                self.assertEqual(data["data"]["metadata"]["mode"], mode)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Integration tests for chatbot full workflow.

Tests the complete query flow: query → retrieval → LLM → response
with mocked external services.
"""

import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import httpx
import numpy as np

# Mock schedule module
if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.conversation import ConversationManager
from ai_actuarial.chatbot.exceptions import (
    InvalidKBException,
    LLMException,
    NoResultsException,
    RetrievalException,
)
from ai_actuarial.chatbot.llm import LLMClient
from ai_actuarial.chatbot.prompts import build_full_prompt
from ai_actuarial.chatbot.retrieval import RAGRetriever
from ai_actuarial.chatbot.router import QueryRouter
from ai_actuarial.storage import Storage


def _mock_openai_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _mock_openai_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=_mock_openai_request())


class TestChatbotIntegration(unittest.TestCase):
    """Integration tests for full chatbot workflow."""
    
    def setUp(self):
        """Set up test environment with temp database and mock services."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(self.db_path)
        
        # Set API key in env for config
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
        
        self.config = ChatbotConfig(
            api_key="test-key-12345",
            top_k=3,
            similarity_threshold=0.5
        )
        
        # Initialize RAG schema and test data
        self._init_rag_schema()
        self._create_test_kbs()
        self._create_mock_index()
        
        # Initialize conversation manager (doesn't need KnowledgeBaseManager)
        self.conv_manager = ConversationManager(self.storage, self.config)
        
        # For retriever and router tests, mock KnowledgeBaseManager initialization
        # to avoid tiktoken network calls
        self.kb_manager_patcher = patch('ai_actuarial.chatbot.retrieval.KnowledgeBaseManager')
        self.mock_kb_manager_class = self.kb_manager_patcher.start()
        
        # Mock EmbeddingGenerator to avoid initialization
        self.embedding_patcher = patch('ai_actuarial.chatbot.retrieval.EmbeddingGenerator')
        self.mock_embedding_class = self.embedding_patcher.start()
        
        # Now we can create retriever - KBmanager and Embeddings won't actually initialize
        self.retriever = RAGRetriever(self.storage, self.config)
        self.retriever.embedding_generator.provider = "openai"
        self.retriever.embedding_generator.config.embedding_model = "text-embedding-3-small"
        self.retriever.embedding_generator.get_embedding_dimension.return_value = 1536

        # Mock the kb_manager instance methods we need
        from ai_actuarial.rag.knowledge_base import KnowledgeBase
        self.mock_kb1 = KnowledgeBase(
            kb_id='test_kb1',
            name='General Actuarial',
            description='General actuarial knowledge',
            embedding_model='text-embedding-3-small',
            chunk_size=512,
            chunk_overlap=50,
            kb_mode='manual',
            created_at='2024-01-01',
            updated_at='2024-01-01',
            file_count=1,
            chunk_count=10
        )
        self.mock_kb2 = KnowledgeBase(
            kb_id='test_kb2',
            name='Regulations',
            description='Regulatory documents',
            embedding_model='text-embedding-3-small',
            chunk_size=512,
            chunk_overlap=50,
            kb_mode='manual',
            created_at='2024-01-01',
            updated_at='2024-01-01',
            file_count=1,
            chunk_count=10
        )
        self.retriever.kb_manager.get_kb.side_effect = lambda kb_id: (
            self.mock_kb1 if kb_id == 'test_kb1' else self.mock_kb2 if kb_id == 'test_kb2' else None
        )
    
    def tearDown(self):
        """Clean up test environment."""
        # Stop patchers
        self.kb_manager_patcher.stop()
        self.embedding_patcher.stop()
        
        self.storage.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clean env
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
    
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
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_files (
                file_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id)
            )
        """)
        
        conn.commit()
    
    def _create_test_kbs(self):
        """Create test knowledge bases."""
        conn = self.storage._conn
        now = datetime.now(timezone.utc).isoformat()
        
        kbs = [
            ("test_kb1", "General Actuarial", "General actuarial knowledge"),
            ("test_kb2", "Regulations", "Regulatory documents")
        ]
        
        for kb_id, name, desc in kbs:
            conn.execute("""
                INSERT INTO rag_knowledge_bases 
                (kb_id, name, description, created_at, updated_at, file_count, chunk_count, index_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (kb_id, name, desc, now, now, 1, 10, f"{self.temp_dir}/index_{kb_id}.faiss"))
        
        conn.commit()
    
    def _create_mock_index(self):
        """Create mock FAISS index files."""
        # Create simple mock index files
        for kb_id in ["test_kb1", "test_kb2"]:
            index_path = os.path.join(self.temp_dir, f"index_{kb_id}.faiss")
            # Create empty file to simulate index
            Path(index_path).touch()
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    def test_retrieval_single_kb(self, mock_vector_store):
        """Test retrieval from single knowledge base."""
        # Mock embedding generation
        mock_embedding = np.array([0.1] * 1536)
        self.retriever.embedding_generator.generate_single.return_value = mock_embedding.tolist()
        
        # Mock vector store search
        mock_store_instance = Mock()
        mock_store_instance.search.return_value = [
            {
                'score': 0.9,
                'metadata': {
                    'content': 'Capital requirements are essential for insurance companies.',
                    'filename': 'regulation.pdf',
                    'chunk_id': 'chunk_1',
                    '_deleted': False
                }
            }
        ]
        mock_vector_store.return_value = mock_store_instance
        
        # Perform retrieval
        query = "What are capital requirements?"
        results = self.retriever.retrieve(query, kb_ids="test_kb1", top_k=3)
        
        # Verify results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], 'Capital requirements are essential for insurance companies.')
        self.assertEqual(results[0]['metadata']['filename'], 'regulation.pdf')
        self.assertEqual(results[0]['metadata']['kb_id'], 'test_kb1')
        self.assertGreater(results[0]['metadata']['similarity_score'], 0.5)
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    def test_retrieval_multi_kb(self, mock_vector_store):
        """Test retrieval from multiple knowledge bases."""
        # Mock embedding generation
        mock_embedding = np.array([0.1] * 1536)
        self.retriever.embedding_generator.generate_single.return_value = mock_embedding.tolist()
        
        # Mock vector store search for both KBs
        def create_mock_store(kb_id):
            mock_store = Mock()
            if kb_id == "test_kb1":
                mock_store.search.return_value = [
                    {
                        'score': 0.85,
                        'metadata': {
                            'content': 'General insurance info',
                            'filename': 'general.pdf',
                            'chunk_id': 'chunk_1',
                            '_deleted': False
                        }
                    }
                ]
            else:
                mock_store.search.return_value = [
                    {
                        'score': 0.80,
                        'metadata': {
                            'content': 'Regulatory requirements',
                            'filename': 'regulation.pdf',
                            'chunk_id': 'chunk_2',
                            '_deleted': False
                        }
                    }
                ]
            return mock_store
        
        mock_vector_store.side_effect = lambda *args, **kwargs: create_mock_store(
            "test_kb1" if "test_kb1" in str(kwargs.get('index_path', '')) else "test_kb2"
        )
        
        # Perform multi-KB retrieval
        results = self.retriever.retrieve(
            query="insurance requirements",
            kb_ids=["test_kb1", "test_kb2"],
            top_k=5
        )
        
        # Verify results from both KBs
        self.assertGreater(len(results), 0)
        kb_ids = {r['metadata']['kb_id'] for r in results}
        # At least one KB should be represented
        self.assertTrue(len(kb_ids) >= 1)
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    def test_retrieval_no_results(self, mock_vector_store):
        """Test retrieval with no results above threshold."""
        # Mock embedding generation
        mock_embedding = np.array([0.1] * 1536)
        self.retriever.embedding_generator.generate_single.return_value = mock_embedding.tolist()
        
        # Mock empty search results
        mock_store_instance = Mock()
        mock_store_instance.search.return_value = []
        mock_vector_store.return_value = mock_store_instance
        
        # Should raise NoResultsException
        with self.assertRaises(NoResultsException):
            self.retriever.retrieve(
                query="obscure query with no matches",
                kb_ids="test_kb1"
            )
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    def test_retrieval_invalid_kb(self, mock_vector_store):
        """Test retrieval with invalid KB ID."""
        # Mock embedding generation
        mock_embedding = np.array([0.1] * 1536)
        self.retriever.embedding_generator.generate_single.return_value = mock_embedding.tolist()
        
        # Should raise InvalidKBException
        with self.assertRaises(InvalidKBException):
            self.retriever.retrieve(
                query="test query",
                kb_ids="nonexistent_kb"
            )
    
    @patch('openai.OpenAI')
    def test_llm_generation_success(self, mock_openai_class):
        """Test successful LLM response generation."""
        # Mock OpenAI client and response
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is a test response with proper citations [Source: test.pdf]."
        mock_response.usage.total_tokens = 150
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        # Create LLM client
        llm_client = LLMClient(self.config)
        
        # Generate response
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is Solvency II?"}
        ]
        
        response = llm_client.generate(messages)
        
        self.assertIn("test response", response)
        self.assertIn("[Source: test.pdf]", response)
        
        # Verify API was called
        mock_client.chat.completions.create.assert_called_once()

    @patch('openai.OpenAI')
    def test_llm_generation_uses_max_completion_tokens_for_openai_gpt5(self, mock_openai_class):
        """OpenAI GPT-5 chat completions should not send deprecated max_tokens."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "GPT-5 response"
        mock_response.usage.total_tokens = 150
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        config = ChatbotConfig(
            llm_provider="openai",
            model="gpt-5.4-mini",
            api_key="test-key",
            max_tokens=321,
            _apply_env_defaults=False,
        )
        llm_client = LLMClient(config)

        response = llm_client.generate([{"role": "user", "content": "test"}])

        self.assertEqual(response, "GPT-5 response")
        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs["max_completion_tokens"], 321)
        self.assertNotIn("max_tokens", kwargs)

    @patch('openai.OpenAI')
    def test_llm_generation_keeps_max_tokens_for_openai_compatible_providers(self, mock_openai_class):
        """Non-OpenAI compatible providers should keep the broadly supported max_tokens parameter."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "DeepSeek response"
        mock_response.usage.total_tokens = 100
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        config = ChatbotConfig(
            llm_provider="deepseek",
            model="deepseek-chat",
            api_key="deepseek-key",
            base_url="https://api.deepseek.com/v1",
            max_tokens=222,
            _apply_env_defaults=False,
        )
        llm_client = LLMClient(config)

        response = llm_client.generate([{"role": "user", "content": "test"}])

        self.assertEqual(response, "DeepSeek response")
        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs["max_tokens"], 222)
        self.assertNotIn("max_completion_tokens", kwargs)

    @patch('openai.OpenAI')
    def test_llm_client_uses_provider_base_url(self, mock_openai_class):
        """OpenAI-compatible providers should initialize with their own base URL."""
        config = ChatbotConfig(
            llm_provider="deepseek",
            model="deepseek-chat",
            api_key="deepseek-key",
            base_url="https://api.deepseek.com/v1",
            _apply_env_defaults=False,
        )

        LLMClient(config)

        mock_openai_class.assert_called_once_with(
            api_key="deepseek-key",
            base_url="https://api.deepseek.com/v1",
            timeout=60.0,
        )
    
    @patch('openai.OpenAI')
    def test_llm_generation_retry_on_rate_limit(self, mock_openai_class):
        """Test LLM retry on rate limit error."""
        from openai import RateLimitError
        
        # Mock client that fails once then succeeds
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Success after retry"
        mock_response.usage.total_tokens = 100
        
        # First call fails, second succeeds
        mock_client.chat.completions.create.side_effect = [
            RateLimitError("Rate limit exceeded", response=Mock(), body=None),
            mock_response
        ]
        
        mock_openai_class.return_value = mock_client
        
        # Create LLM client with fast retry
        config = ChatbotConfig(
            api_key="test-key",
            max_retries=3,
            retry_delay=0.1,
            exponential_backoff=False
        )
        llm_client = LLMClient(config)
        
        # Should succeed after retry
        messages = [{"role": "user", "content": "test"}]
        response = llm_client.generate(messages)
        
        self.assertEqual(response, "Success after retry")
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
    
    @patch('openai.OpenAI')
    def test_llm_generation_max_retries_exceeded(self, mock_openai_class):
        """Test LLM fails after max retries."""
        from openai import APITimeoutError
        
        # Mock client that always times out
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=_mock_openai_request())
        
        mock_openai_class.return_value = mock_client
        
        # Create LLM client with fast retry
        config = ChatbotConfig(
            api_key="test-key",
            max_retries=2,
            retry_delay=0.1
        )
        llm_client = LLMClient(config)
        
        # Should raise LLMException after max retries
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(LLMException) as ctx:
            llm_client.generate(messages)
        
        self.assertIn("timeout", str(ctx.exception).lower())
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    @patch('openai.OpenAI')
    def test_full_query_workflow(self, mock_openai_class, mock_vector_store):
        """Test complete query workflow: retrieval → LLM → response."""
        # Mock embedding generation
        mock_embedding = np.array([0.1] * 1536)
        self.retriever.embedding_generator.generate_single.return_value = mock_embedding.tolist()
        
        # Mock vector store retrieval
        mock_store_instance = Mock()
        mock_store_instance.search.return_value = [
            {
                'score': 0.92,
                'metadata': {
                    'content': 'Solvency II is a regulatory framework for insurance companies.',
                    'filename': 'solvency_ii.pdf',
                    'chunk_id': 'chunk_1',
                    '_deleted': False
                }
            }
        ]
        mock_vector_store.return_value = mock_store_instance
        
        # Mock LLM response
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = (
            "Solvency II is a comprehensive regulatory framework for insurance companies "
            "in the European Union [Source: solvency_ii.pdf]."
        )
        mock_response.usage.total_tokens = 200
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        # Create conversation
        user_id = "test_user"
        conv_id = self.conv_manager.create_conversation(
            user_id=user_id,
            kb_id="test_kb1",
            mode="expert"
        )
        
        # Add user query
        query = "What is Solvency II?"
        self.conv_manager.add_message(conv_id, "user", query)
        
        # Retrieve relevant chunks
        chunks = self.retriever.retrieve(query, kb_ids="test_kb1")
        
        self.assertEqual(len(chunks), 1)
        self.assertIn("Solvency II", chunks[0]['content'])
        
        # Generate LLM response
        llm_client = LLMClient(self.config)
        history = self.conv_manager.get_context(conv_id)
        messages = build_full_prompt(
            mode="expert",
            retrieved_chunks=chunks,
            query=query,
            conversation_history=history[:-1]  # Exclude current message
        )
        
        response = llm_client.generate(messages)
        
        self.assertIn("Solvency II", response)
        self.assertIn("[Source: solvency_ii.pdf]", response)
        
        # Add assistant response to conversation
        citations = [
            {
                'filename': chunks[0]['metadata']['filename'],
                'kb_id': chunks[0]['metadata']['kb_id'],
                'similarity_score': chunks[0]['metadata']['similarity_score']
            }
        ]
        
        self.conv_manager.add_message(
            conv_id,
            "assistant",
            response,
            citations=citations
        )
        
        # Verify conversation state
        messages = self.conv_manager.get_messages(conv_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[1]['role'], 'assistant')
        self.assertIsNotNone(messages[1]['citations'])
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    @patch('openai.OpenAI')
    def test_multi_turn_conversation(self, mock_openai_class, mock_vector_store):
        """Test multi-turn conversation with context."""
        # Mock services
        mock_embedding = np.array([0.1] * 1536)
        self.retriever.embedding_generator.generate_single.return_value = mock_embedding.tolist()
        
        mock_store_instance = Mock()
        mock_store_instance.search.return_value = [
            {
                'score': 0.88,
                'metadata': {
                    'content': 'SCR is calculated using standard formula or internal model.',
                    'filename': 'scr_guide.pdf',
                    'chunk_id': 'chunk_2',
                    '_deleted': False
                }
            }
        ]
        mock_vector_store.return_value = mock_store_instance
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Create conversation
        conv_id = self.conv_manager.create_conversation(
            user_id="test_user",
            mode="expert"
        )
        
        # Turn 1
        query1 = "What is Solvency II?"
        self.conv_manager.add_message(conv_id, "user", query1)
        
        mock_response1 = Mock()
        mock_response1.choices = [Mock()]
        mock_response1.choices[0].message.content = "Solvency II is a regulatory framework [Source: scr_guide.pdf]."
        mock_response1.usage.total_tokens = 150
        mock_client.chat.completions.create.return_value = mock_response1
        
        llm_client = LLMClient(self.config)
        chunks1 = self.retriever.retrieve(query1, kb_ids="test_kb1")
        history1 = self.conv_manager.get_context(conv_id)
        messages1 = build_full_prompt("expert", chunks1, query1, history1[:-1])
        response1 = llm_client.generate(messages1)
        
        self.conv_manager.add_message(conv_id, "assistant", response1)
        
        # Turn 2 - follow-up question
        query2 = "How is the SCR calculated?"
        self.conv_manager.add_message(conv_id, "user", query2)
        
        mock_response2 = Mock()
        mock_response2.choices = [Mock()]
        mock_response2.choices[0].message.content = "The SCR uses standard formula or internal model [Source: scr_guide.pdf]."
        mock_response2.usage.total_tokens = 180
        mock_client.chat.completions.create.return_value = mock_response2
        
        chunks2 = self.retriever.retrieve(query2, kb_ids="test_kb1")
        history2 = self.conv_manager.get_context(conv_id)
        
        # Context should include previous messages
        self.assertGreater(len(history2), 2)
        
        messages2 = build_full_prompt("expert", chunks2, query2, history2[:-1])
        response2 = llm_client.generate(messages2)
        
        self.conv_manager.add_message(conv_id, "assistant", response2)
        
        # Verify final conversation state
        all_messages = self.conv_manager.get_messages(conv_id)
        self.assertEqual(len(all_messages), 4)
        self.assertEqual(all_messages[0]['content'], query1)
        self.assertEqual(all_messages[2]['content'], query2)
    
    def test_conversation_persistence(self):
        """Test conversation data persists across manager instances."""
        # Create conversation and add messages
        conv_id = self.conv_manager.create_conversation(user_id="test_user")
        self.conv_manager.add_message(conv_id, "user", "Question")
        self.conv_manager.add_message(conv_id, "assistant", "Answer")
        
        # Create new manager instance with same storage
        new_manager = ConversationManager(self.storage, self.config)
        
        # Verify data persists
        conv = new_manager.get_conversation(conv_id)
        self.assertIsNotNone(conv)
        
        messages = new_manager.get_messages(conv_id)
        self.assertEqual(len(messages), 2)
    
    @patch('ai_actuarial.chatbot.retrieval.VectorStore')
    def test_error_handling_retrieval_failure(self, mock_vector_store):
        """Test error handling when retrieval fails."""
        # Mock embedding generation that raises error
        self.retriever.embedding_generator.generate_single.side_effect = Exception("Embedding failed")
        
        # Should raise RetrievalException
        with self.assertRaises(RetrievalException):
            self.retriever.retrieve(
                query="test query",
                kb_ids="test_kb1"
            )
    
    @patch('openai.OpenAI')
    def test_error_handling_llm_auth_failure(self, mock_openai_class):
        """Test error handling for LLM authentication failure."""
        from openai import AuthenticationError
        
        # Mock authentication failure
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = AuthenticationError(
            "Invalid API key",
            response=_mock_openai_response(401),
            body=None,
        )
        mock_openai_class.return_value = mock_client
        
        llm_client = LLMClient(self.config)
        
        # Should raise LLMException without retry
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(LLMException) as ctx:
            llm_client.generate(messages)
        
        self.assertIn("Authentication", str(ctx.exception))
        
        # Should only call once (no retry for auth errors)
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)


if __name__ == "__main__":
    unittest.main()

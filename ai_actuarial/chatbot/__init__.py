"""
AI Chatbot module for AI Actuarial Info Search.

This module provides an intelligent chatbot with RAG (Retrieval-Augmented Generation)
capabilities for answering questions from actuarial knowledge bases.

Key components:
- config: Chatbot configuration and settings
- retrieval: RAG retrieval integration for knowledge base queries
- llm: LLM integration (OpenAI GPT-4) with retry logic
- prompts: System prompts for different chatbot modes
- conversation: Conversation state management and history
- router: Query routing and KB selection logic
"""

from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import (
    ChatbotException,
    RetrievalException,
    LLMException,
    ConversationException,
)
from ai_actuarial.chatbot.retrieval import RAGRetriever
from ai_actuarial.chatbot.llm import LLMClient
from ai_actuarial.chatbot.conversation import ConversationManager
from ai_actuarial.chatbot.router import QueryRouter

__all__ = [
    "ChatbotConfig",
    "ChatbotException",
    "RetrievalException",
    "LLMException",
    "ConversationException",
    "RAGRetriever",
    "LLMClient",
    "ConversationManager",
    "QueryRouter",
]

__version__ = "0.1.0"

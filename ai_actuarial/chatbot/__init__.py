"""
AI Chatbot module for AI Actuarial Info Search.

This module provides functionality for intelligent question-answering with
Retrieval-Augmented Generation (RAG) capabilities.

Key components:
- config: Chatbot configuration and settings management
- (Future) conversation: Conversation management and history
- (Future) llm: Large language model integration
- (Future) router: Query routing and knowledge base selection
"""

from ai_actuarial.chatbot.config import ChatbotConfig

__all__ = [
    "ChatbotConfig",
]

__version__ = "0.1.0"

"""
Configuration for AI Chatbot module.

Provides centralized configuration management for chatbot components with
environment variable support and sensible defaults.
"""

import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class ChatbotConfig:
    """Configuration for AI chatbot system."""
    
    # LLM configuration
    model: str = "gpt-4-turbo"  # OpenAI model to use
    temperature: float = 0.7  # Sampling temperature (0.0-2.0)
    max_tokens: int = 1000  # Maximum tokens in response
    streaming_enabled: bool = True  # Enable streaming responses
    
    # Conversation configuration
    max_context_messages: int = 10  # Maximum messages to include in context
    default_mode: Literal["expert", "summary", "tutorial", "comparison"] = "expert"
    
    # API configuration
    openai_api_key: str = ""  # OpenAI API key (shared with RAG)
    openai_base_url: str = "https://api.openai.com/v1"  # OpenAI API base URL
    openai_timeout: int = 60  # Request timeout in seconds
    openai_max_retries: int = 3  # Maximum retry attempts
    
    # Response quality configuration
    enable_citation: bool = True  # Include citations in responses
    min_citation_score: float = 0.4  # Minimum similarity score for citations
    max_citations_per_response: int = 5  # Maximum number of citations
    
    # Safety and validation
    enable_query_validation: bool = True  # Validate queries before processing
    enable_response_validation: bool = True  # Validate responses before returning
    max_query_length: int = 1000  # Maximum query length in characters
    
    @classmethod
    def from_env(cls) -> "ChatbotConfig":
        """Create configuration from environment variables."""
        return cls(
            # LLM configuration
            model=os.getenv("CHATBOT_MODEL", "gpt-4-turbo"),
            temperature=float(os.getenv("CHATBOT_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("CHATBOT_MAX_TOKENS", "1000")),
            streaming_enabled=os.getenv("CHATBOT_STREAMING_ENABLED", "true").lower() == "true",
            
            # Conversation configuration
            max_context_messages=int(os.getenv("CHATBOT_MAX_CONTEXT_MESSAGES", "10")),
            default_mode=os.getenv("CHATBOT_DEFAULT_MODE", "expert"),
            
            # API configuration (reuse from main settings)
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_timeout=int(os.getenv("OPENAI_TIMEOUT", "60")),
            openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
            
            # Response quality configuration
            enable_citation=os.getenv("CHATBOT_ENABLE_CITATION", "true").lower() == "true",
            min_citation_score=float(os.getenv("CHATBOT_MIN_CITATION_SCORE", "0.4")),
            max_citations_per_response=int(os.getenv("CHATBOT_MAX_CITATIONS_PER_RESPONSE", "5")),
            
            # Safety and validation
            enable_query_validation=os.getenv("CHATBOT_ENABLE_QUERY_VALIDATION", "true").lower() == "true",
            enable_response_validation=os.getenv("CHATBOT_ENABLE_RESPONSE_VALIDATION", "true").lower() == "true",
            max_query_length=int(os.getenv("CHATBOT_MAX_QUERY_LENGTH", "1000")),
        )
    
    def validate(self) -> None:
        """Validate configuration."""
        # Validate API key
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for chatbot functionality")
        
        # Validate temperature
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        
        # Validate max_tokens
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        
        # Validate max_context_messages
        if self.max_context_messages <= 0:
            raise ValueError("max_context_messages must be positive")
        
        # Validate citation score
        if not 0.0 <= self.min_citation_score <= 1.0:
            raise ValueError("min_citation_score must be between 0.0 and 1.0")
        
        # Validate max_citations_per_response
        if self.max_citations_per_response <= 0:
            raise ValueError("max_citations_per_response must be positive")
        
        # Validate max_query_length
        if self.max_query_length <= 0:
            raise ValueError("max_query_length must be positive")
        
        # Validate default_mode
        valid_modes = ["expert", "summary", "tutorial", "comparison"]
        if self.default_mode not in valid_modes:
            raise ValueError(f"default_mode must be one of {valid_modes}")

"""
Configuration for the AI chatbot module.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ChatbotConfig:
    """Configuration for the chatbot system."""
    
    # LLM Settings
    llm_provider: str = "openai"  # openai, anthropic, ollama
    model: str = "gpt-4"  # gpt-4, gpt-4-turbo, gpt-3.5-turbo
    temperature: float = 0.7
    max_tokens: int = 1000
    api_key: Optional[str] = None
    
    # Retrieval Settings
    top_k: int = 5  # Number of chunks to retrieve
    similarity_threshold: float = 0.4
    min_results: int = 1  # Minimum results required
    
    # Conversation Settings
    max_messages: int = 20  # Maximum messages to keep in context
    max_context_tokens: int = 8000  # Maximum tokens in context window
    summarization_threshold: int = 15  # When to start summarizing old messages
    
    # Mode Settings
    default_mode: str = "expert"
    available_modes: List[str] = field(default_factory=lambda: [
        "expert", "summary", "tutorial", "comparison"
    ])
    
    # Retry & Rate Limiting
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds
    exponential_backoff: bool = True
    rate_limit_rpm: int = 60  # requests per minute
    
    # Quality & Validation
    require_citations: bool = True
    validate_citations: bool = True
    hallucination_check: bool = True
    
    # Multi-KB Query Settings
    multi_kb_enabled: bool = True
    min_results_per_kb: int = 2  # Minimum results from each KB in multi-KB query
    kb_diversity_weight: float = 0.3  # Weight for diversity in ranking
    
    def __post_init__(self):
        """Load configuration from environment variables."""
        # Load API key from environment if not provided
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY")
        
        # Load other settings from environment
        self.model = os.getenv("CHATBOT_MODEL", self.model)
        self.temperature = float(os.getenv("CHATBOT_TEMPERATURE", str(self.temperature)))
        self.max_tokens = int(os.getenv("CHATBOT_MAX_TOKENS", str(self.max_tokens)))
        self.top_k = int(os.getenv("CHATBOT_TOP_K", str(self.top_k)))
        self.similarity_threshold = float(os.getenv("RAG_SIMILARITY_THRESHOLD", str(self.similarity_threshold)))
    
    def validate(self):
        """Validate configuration parameters."""
        errors = []
        
        if not self.api_key:
            errors.append("API key is required (OPENAI_API_KEY environment variable)")
        
        if self.temperature < 0 or self.temperature > 2:
            errors.append(f"Temperature must be between 0 and 2, got {self.temperature}")
        
        if self.max_tokens < 1:
            errors.append(f"max_tokens must be positive, got {self.max_tokens}")
        
        if self.top_k < 1:
            errors.append(f"top_k must be positive, got {self.top_k}")
        
        if self.similarity_threshold < 0 or self.similarity_threshold > 1:
            errors.append(f"similarity_threshold must be between 0 and 1, got {self.similarity_threshold}")
        
        if self.default_mode not in self.available_modes:
            errors.append(f"default_mode '{self.default_mode}' not in available_modes")
        
        if errors:
            raise ValueError(f"Invalid chatbot configuration: {'; '.join(errors)}")
        
        return True


# Default configuration instance
default_config = ChatbotConfig()

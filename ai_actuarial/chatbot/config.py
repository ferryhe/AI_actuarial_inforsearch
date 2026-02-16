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
    
    @classmethod
    def from_env(cls) -> "ChatbotConfig":
        """
        Create configuration from environment variables.
        
        This method explicitly loads all configuration from environment variables,
        providing clear error messages for invalid values.
        """
        def safe_int(var_name: str, default: int) -> int:
            """Get integer from environment with error handling."""
            value = os.getenv(var_name)
            if not value:
                return default
            try:
                return int(value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid value for {var_name}: {value!r}. Expected an integer."
                ) from e
        
        def safe_float(var_name: str, default: float) -> float:
            """Get float from environment with error handling."""
            value = os.getenv(var_name)
            if not value:
                return default
            try:
                return float(value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid value for {var_name}: {value!r}. Expected a float."
                ) from e
        
        return cls(
            # LLM Settings
            llm_provider=os.getenv("CHATBOT_LLM_PROVIDER", "openai"),
            model=os.getenv("CHATBOT_MODEL", "gpt-4"),
            temperature=safe_float("CHATBOT_TEMPERATURE", 0.7),
            max_tokens=safe_int("CHATBOT_MAX_TOKENS", 1000),
            api_key=os.getenv("OPENAI_API_KEY"),
            
            # Retrieval Settings
            top_k=safe_int("CHATBOT_TOP_K", 5),
            similarity_threshold=safe_float("RAG_SIMILARITY_THRESHOLD", 0.4),
            min_results=safe_int("CHATBOT_MIN_RESULTS", 1),
            
            # Conversation Settings
            max_messages=safe_int("CHATBOT_MAX_MESSAGES", 20),
            max_context_tokens=safe_int("CHATBOT_MAX_CONTEXT_TOKENS", 8000),
            summarization_threshold=safe_int("CHATBOT_SUMMARIZATION_THRESHOLD", 15),
            
            # Mode Settings
            default_mode=os.getenv("CHATBOT_DEFAULT_MODE", "expert"),
            
            # Retry & Rate Limiting
            max_retries=safe_int("CHATBOT_MAX_RETRIES", 3),
            retry_delay=safe_float("CHATBOT_RETRY_DELAY", 1.0),
            exponential_backoff=os.getenv("CHATBOT_EXPONENTIAL_BACKOFF", "true").lower() == "true",
            rate_limit_rpm=safe_int("CHATBOT_RATE_LIMIT_RPM", 60),
            
            # Quality & Validation
            require_citations=os.getenv("CHATBOT_REQUIRE_CITATIONS", "true").lower() == "true",
            validate_citations=os.getenv("CHATBOT_VALIDATE_CITATIONS", "true").lower() == "true",
            hallucination_check=os.getenv("CHATBOT_HALLUCINATION_CHECK", "true").lower() == "true",
            
            # Multi-KB Query Settings
            multi_kb_enabled=os.getenv("CHATBOT_MULTI_KB_ENABLED", "true").lower() == "true",
            min_results_per_kb=safe_int("CHATBOT_MIN_RESULTS_PER_KB", 2),
            kb_diversity_weight=safe_float("CHATBOT_KB_DIVERSITY_WEIGHT", 0.3),
        )
    
    @classmethod
    def from_yaml(cls, yaml_config: dict) -> "ChatbotConfig":
        """
        Create configuration from sites.yaml ai_config section.
        
        Args:
            yaml_config: The full YAML configuration dictionary
            
        Returns:
            ChatbotConfig instance
            
        Raises:
            ValueError: If configuration values are invalid
        """
        chatbot = yaml_config.get("ai_config", {}).get("chatbot", {})
        
        # Helper to get nested values with defaults and type conversion
        def get_val(key: str, default, converter=None):
            value = chatbot.get(key)
            if value is None:
                return default
            if converter:
                try:
                    return converter(value)
                except (ValueError, TypeError) as e:
                    raise ValueError(
                        f"Invalid value for chatbot.{key} in sites.yaml: {value!r}. "
                        f"Expected {converter.__name__} type."
                    ) from e
            return value
        
        try:
            return cls(
                # LLM Settings
                llm_provider=get_val("llm_provider", "openai"),
                model=get_val("model", "gpt-4"),
                temperature=get_val("temperature", 0.7, float),
                max_tokens=get_val("max_tokens", 1000, int),
                api_key=os.getenv("OPENAI_API_KEY"),  # Always from environment
                
                # Retrieval Settings
                top_k=get_val("top_k", 5, int),
                similarity_threshold=get_val("similarity_threshold", 0.4, float),
                min_results=get_val("min_results", 1, int),
                
                # Conversation Settings
                max_messages=get_val("max_messages", 20, int),
                max_context_tokens=get_val("max_context_tokens", 8000, int),
                summarization_threshold=get_val("summarization_threshold", 15, int),
                
                # Mode Settings
                default_mode=get_val("default_mode", "expert"),
                
                # Retry & Rate Limiting
                max_retries=get_val("max_retries", 3, int),
                retry_delay=get_val("retry_delay", 1.0, float),
                exponential_backoff=get_val("exponential_backoff", True, bool),
                rate_limit_rpm=get_val("rate_limit_rpm", 60, int),
                
                # Quality & Validation
                require_citations=get_val("require_citations", True, bool),
                validate_citations=get_val("validate_citations", True, bool),
                hallucination_check=get_val("hallucination_check", True, bool),
                
                # Multi-KB Query Settings
                multi_kb_enabled=get_val("multi_kb_enabled", True, bool),
                min_results_per_kb=get_val("min_results_per_kb", 2, int),
                kb_diversity_weight=get_val("kb_diversity_weight", 0.3, float),
            )
        except ValueError:
            # Re-raise configuration errors with context
            raise
        except Exception as e:
            raise ValueError(f"Error loading chatbot configuration from sites.yaml: {e}") from e
    
    @classmethod
    def from_config(cls) -> "ChatbotConfig":
        """
        Create configuration from sites.yaml with .env fallback.
        
        This is the recommended method for loading configuration. It will:
        1. Try to load from sites.yaml ai_config.chatbot section
        2. Fall back to environment variables if not found
        
        Returns:
            ChatbotConfig instance
            
        Raises:
            ValueError: If configuration values are invalid in sites.yaml
        """
        try:
            from config.yaml_config import load_yaml_config
        except (ImportError, ModuleNotFoundError):
            # If the YAML config loader is not available, fall back to env
            return cls.from_env()
        
        try:
            yaml_config = load_yaml_config()
        except (FileNotFoundError, OSError):
            # If the YAML file is missing or inaccessible, fall back to env
            return cls.from_env()
        
        if "ai_config" in yaml_config and "chatbot" in yaml_config.get("ai_config", {}):
            # This may raise ValueError if configuration is invalid
            return cls.from_yaml(yaml_config)
        
        # Fallback to environment variables if ai_config.chatbot section is not present
        return cls.from_env()
    
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

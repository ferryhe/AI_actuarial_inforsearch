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
    
    @staticmethod
    def _get_int_env(var_name: str, default: int) -> int:
        """Get integer from environment with clear error messages."""
        value = os.getenv(var_name)
        if not value:
            return default
        try:
            return int(value)
        except ValueError as e:
            raise ValueError(f"Invalid value for {var_name}: {value!r}. Expected an integer.") from e
    
    @staticmethod
    def _get_float_env(var_name: str, default: float) -> float:
        """Get float from environment with clear error messages."""
        value = os.getenv(var_name)
        if not value:
            return default
        try:
            return float(value)
        except ValueError as e:
            raise ValueError(f"Invalid value for {var_name}: {value!r}. Expected a float.") from e
    
    @classmethod
    def from_env(cls) -> "ChatbotConfig":
        """Create configuration from environment variables."""
        return cls(
            # LLM configuration
            model=os.getenv("CHATBOT_MODEL", "gpt-4-turbo"),
            temperature=cls._get_float_env("CHATBOT_TEMPERATURE", 0.7),
            max_tokens=cls._get_int_env("CHATBOT_MAX_TOKENS", 1000),
            streaming_enabled=os.getenv("CHATBOT_STREAMING_ENABLED", "true").lower() == "true",
            
            # Conversation configuration
            max_context_messages=cls._get_int_env("CHATBOT_MAX_CONTEXT_MESSAGES", 10),
            default_mode=os.getenv("CHATBOT_DEFAULT_MODE", "expert"),
            
            # API configuration (reuse from main settings)
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_timeout=cls._get_int_env("OPENAI_TIMEOUT", 60),
            openai_max_retries=cls._get_int_env("OPENAI_MAX_RETRIES", 3),
            
            # Response quality configuration
            enable_citation=os.getenv("CHATBOT_ENABLE_CITATION", "true").lower() == "true",
            min_citation_score=cls._get_float_env("CHATBOT_MIN_CITATION_SCORE", 0.4),
            max_citations_per_response=cls._get_int_env("CHATBOT_MAX_CITATIONS_PER_RESPONSE", 5),
            
            # Safety and validation
            enable_query_validation=os.getenv("CHATBOT_ENABLE_QUERY_VALIDATION", "true").lower() == "true",
            enable_response_validation=os.getenv("CHATBOT_ENABLE_RESPONSE_VALIDATION", "true").lower() == "true",
            max_query_length=cls._get_int_env("CHATBOT_MAX_QUERY_LENGTH", 1000),
        )
    
    @classmethod
    def from_yaml(cls, yaml_config: dict) -> "ChatbotConfig":
        """Create configuration from sites.yaml ai_config section."""
        chatbot = yaml_config.get("ai_config", {}).get("chatbot", {})
        
        # Helper to get nested values with defaults and type conversion
        def get_val(key: str, default, converter=None):
            value = chatbot.get(key, default)
            if converter and value != default:
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
                # LLM configuration
                model=get_val("model", "gpt-4-turbo"),
                temperature=get_val("temperature", 0.7, float),
                max_tokens=get_val("max_tokens", 1000, int),
                streaming_enabled=get_val("streaming_enabled", True, bool),
                
                # Conversation configuration
                max_context_messages=get_val("max_context_messages", 10, int),
                default_mode=get_val("default_mode", "expert"),
                
                # API configuration (still from environment for sensitive data)
                openai_api_key=os.getenv("OPENAI_API_KEY", ""),
                openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                openai_timeout=get_val("timeout_seconds", 60, int),
                openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
                
                # Response quality configuration
                enable_citation=get_val("enable_citation", True, bool),
                min_citation_score=get_val("min_citation_score", 0.4, float),
                max_citations_per_response=get_val("max_citations_per_response", 5, int),
                
                # Safety and validation
                enable_query_validation=get_val("enable_query_validation", True, bool),
                enable_response_validation=get_val("enable_response_validation", True, bool),
                max_query_length=get_val("max_query_length", 1000, int),
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

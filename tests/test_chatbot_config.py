"""
Unit tests for AI Chatbot configuration module.

Tests configuration loading, validation, and integration with environment variables.
"""

import os
import pytest
from ai_actuarial.chatbot.config import ChatbotConfig


class TestChatbotConfigDefaults:
    """Test default configuration values."""
    
    def test_default_values(self):
        """Test that default values are set correctly."""
        config = ChatbotConfig()
        
        assert config.model == "gpt-4-turbo"
        assert config.temperature == 0.7
        assert config.max_tokens == 1000
        assert config.streaming_enabled is True
        assert config.max_context_messages == 10
        assert config.default_mode == "expert"
        assert config.enable_citation is True
        assert config.min_citation_score == 0.4
        assert config.max_citations_per_response == 5
        assert config.enable_query_validation is True
        assert config.enable_response_validation is True
        assert config.max_query_length == 1000
    
    def test_api_defaults(self):
        """Test API configuration defaults."""
        config = ChatbotConfig()
        
        assert config.openai_api_key == ""
        assert config.openai_base_url == "https://api.openai.com/v1"
        assert config.openai_timeout == 60
        assert config.openai_max_retries == 3


class TestChatbotConfigFromEnv:
    """Test configuration loading from environment variables."""
    
    def setup_method(self):
        """Clear environment before each test."""
        # Store original env vars
        self.original_env = {}
        chatbot_vars = [
            "CHATBOT_MODEL", "CHATBOT_TEMPERATURE", "CHATBOT_MAX_TOKENS",
            "CHATBOT_STREAMING_ENABLED", "CHATBOT_MAX_CONTEXT_MESSAGES",
            "CHATBOT_DEFAULT_MODE", "CHATBOT_ENABLE_CITATION",
            "CHATBOT_MIN_CITATION_SCORE", "CHATBOT_MAX_CITATIONS_PER_RESPONSE",
            "CHATBOT_ENABLE_QUERY_VALIDATION", "CHATBOT_ENABLE_RESPONSE_VALIDATION",
            "CHATBOT_MAX_QUERY_LENGTH", "OPENAI_API_KEY", "OPENAI_BASE_URL",
            "OPENAI_TIMEOUT", "OPENAI_MAX_RETRIES"
        ]
        for var in chatbot_vars:
            if var in os.environ:
                self.original_env[var] = os.environ[var]
                del os.environ[var]
    
    def teardown_method(self):
        """Restore original environment after each test."""
        # Remove test vars
        chatbot_vars = [
            "CHATBOT_MODEL", "CHATBOT_TEMPERATURE", "CHATBOT_MAX_TOKENS",
            "CHATBOT_STREAMING_ENABLED", "CHATBOT_MAX_CONTEXT_MESSAGES",
            "CHATBOT_DEFAULT_MODE", "CHATBOT_ENABLE_CITATION",
            "CHATBOT_MIN_CITATION_SCORE", "CHATBOT_MAX_CITATIONS_PER_RESPONSE",
            "CHATBOT_ENABLE_QUERY_VALIDATION", "CHATBOT_ENABLE_RESPONSE_VALIDATION",
            "CHATBOT_MAX_QUERY_LENGTH", "OPENAI_API_KEY", "OPENAI_BASE_URL",
            "OPENAI_TIMEOUT", "OPENAI_MAX_RETRIES"
        ]
        for var in chatbot_vars:
            if var in os.environ:
                del os.environ[var]
        
        # Restore original
        for var, value in self.original_env.items():
            os.environ[var] = value
    
    def test_from_env_with_custom_values(self):
        """Test loading custom values from environment."""
        os.environ["CHATBOT_MODEL"] = "gpt-4"
        os.environ["CHATBOT_TEMPERATURE"] = "0.5"
        os.environ["CHATBOT_MAX_TOKENS"] = "2000"
        os.environ["CHATBOT_STREAMING_ENABLED"] = "false"
        os.environ["CHATBOT_MAX_CONTEXT_MESSAGES"] = "20"
        os.environ["CHATBOT_DEFAULT_MODE"] = "summary"
        os.environ["OPENAI_API_KEY"] = "test-key-123"
        
        config = ChatbotConfig.from_env()
        
        assert config.model == "gpt-4"
        assert config.temperature == 0.5
        assert config.max_tokens == 2000
        assert config.streaming_enabled is False
        assert config.max_context_messages == 20
        assert config.default_mode == "summary"
        assert config.openai_api_key == "test-key-123"
    
    def test_from_env_boolean_parsing(self):
        """Test boolean parsing from environment strings."""
        os.environ["CHATBOT_STREAMING_ENABLED"] = "true"
        config1 = ChatbotConfig.from_env()
        assert config1.streaming_enabled is True
        
        os.environ["CHATBOT_STREAMING_ENABLED"] = "false"
        config2 = ChatbotConfig.from_env()
        assert config2.streaming_enabled is False
        
        os.environ["CHATBOT_STREAMING_ENABLED"] = "True"
        config3 = ChatbotConfig.from_env()
        assert config3.streaming_enabled is True
        
        os.environ["CHATBOT_STREAMING_ENABLED"] = "FALSE"
        config4 = ChatbotConfig.from_env()
        assert config4.streaming_enabled is False
    
    def test_from_env_float_parsing(self):
        """Test float parsing from environment strings."""
        os.environ["CHATBOT_TEMPERATURE"] = "1.5"
        config = ChatbotConfig.from_env()
        assert config.temperature == 1.5
        
        os.environ["CHATBOT_MIN_CITATION_SCORE"] = "0.7"
        config = ChatbotConfig.from_env()
        assert config.min_citation_score == 0.7
    
    def test_from_env_int_parsing(self):
        """Test integer parsing from environment strings."""
        os.environ["CHATBOT_MAX_TOKENS"] = "1500"
        config = ChatbotConfig.from_env()
        assert config.max_tokens == 1500
        
        os.environ["CHATBOT_MAX_CONTEXT_MESSAGES"] = "15"
        config = ChatbotConfig.from_env()
        assert config.max_context_messages == 15


class TestChatbotConfigValidation:
    """Test configuration validation."""
    
    def test_validation_passes_with_valid_config(self):
        """Test that validation passes with valid configuration."""
        config = ChatbotConfig(openai_api_key="test-key")
        config.validate()  # Should not raise
    
    def test_validation_fails_without_api_key(self):
        """Test that validation fails without API key."""
        config = ChatbotConfig(openai_api_key="")
        
        with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
            config.validate()
    
    def test_validation_temperature_range(self):
        """Test temperature range validation."""
        # Too low
        config = ChatbotConfig(openai_api_key="test", temperature=-0.1)
        with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
            config.validate()
        
        # Too high
        config = ChatbotConfig(openai_api_key="test", temperature=2.1)
        with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
            config.validate()
        
        # Valid values
        for temp in [0.0, 0.5, 1.0, 1.5, 2.0]:
            config = ChatbotConfig(openai_api_key="test", temperature=temp)
            config.validate()  # Should not raise
    
    def test_validation_positive_max_tokens(self):
        """Test that max_tokens must be positive."""
        config = ChatbotConfig(openai_api_key="test", max_tokens=0)
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            config.validate()
        
        config = ChatbotConfig(openai_api_key="test", max_tokens=-1)
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            config.validate()
    
    def test_validation_positive_max_context_messages(self):
        """Test that max_context_messages must be positive."""
        config = ChatbotConfig(openai_api_key="test", max_context_messages=0)
        with pytest.raises(ValueError, match="max_context_messages must be positive"):
            config.validate()
    
    def test_validation_citation_score_range(self):
        """Test citation score range validation."""
        # Too low
        config = ChatbotConfig(openai_api_key="test", min_citation_score=-0.1)
        with pytest.raises(ValueError, match="min_citation_score must be between 0.0 and 1.0"):
            config.validate()
        
        # Too high
        config = ChatbotConfig(openai_api_key="test", min_citation_score=1.1)
        with pytest.raises(ValueError, match="min_citation_score must be between 0.0 and 1.0"):
            config.validate()
        
        # Valid values
        for score in [0.0, 0.3, 0.5, 0.8, 1.0]:
            config = ChatbotConfig(openai_api_key="test", min_citation_score=score)
            config.validate()  # Should not raise
    
    def test_validation_positive_max_citations(self):
        """Test that max_citations_per_response must be positive."""
        config = ChatbotConfig(openai_api_key="test", max_citations_per_response=0)
        with pytest.raises(ValueError, match="max_citations_per_response must be positive"):
            config.validate()
    
    def test_validation_positive_max_query_length(self):
        """Test that max_query_length must be positive."""
        config = ChatbotConfig(openai_api_key="test", max_query_length=0)
        with pytest.raises(ValueError, match="max_query_length must be positive"):
            config.validate()
    
    def test_validation_valid_mode(self):
        """Test that default_mode must be a valid mode."""
        valid_modes = ["expert", "summary", "tutorial", "comparison"]
        
        # Test valid modes
        for mode in valid_modes:
            config = ChatbotConfig(openai_api_key="test", default_mode=mode)
            config.validate()  # Should not raise
        
        # Test invalid mode
        config = ChatbotConfig(openai_api_key="test", default_mode="invalid")
        with pytest.raises(ValueError, match="default_mode must be one of"):
            config.validate()


class TestChatbotConfigCustomization:
    """Test custom configuration scenarios."""
    
    def test_custom_model(self):
        """Test using different models."""
        models = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
        for model in models:
            config = ChatbotConfig(model=model, openai_api_key="test")
            assert config.model == model
            config.validate()  # Should work with any model name
    
    def test_tutorial_mode_config(self):
        """Test configuration optimized for tutorial mode."""
        config = ChatbotConfig(
            openai_api_key="test",
            default_mode="tutorial",
            temperature=0.8,  # Higher for more creative explanations
            max_tokens=1500,  # More tokens for detailed explanations
        )
        config.validate()
        
        assert config.default_mode == "tutorial"
        assert config.temperature == 0.8
        assert config.max_tokens == 1500
    
    def test_expert_mode_config(self):
        """Test configuration optimized for expert mode."""
        config = ChatbotConfig(
            openai_api_key="test",
            default_mode="expert",
            temperature=0.3,  # Lower for more focused responses
            max_citations_per_response=10,  # More citations for expert queries
        )
        config.validate()
        
        assert config.default_mode == "expert"
        assert config.temperature == 0.3
        assert config.max_citations_per_response == 10
    
    def test_production_config(self):
        """Test production-ready configuration."""
        config = ChatbotConfig(
            openai_api_key="test",
            model="gpt-4-turbo",
            temperature=0.7,
            max_tokens=1000,
            streaming_enabled=True,
            enable_citation=True,
            enable_query_validation=True,
            enable_response_validation=True,
        )
        config.validate()
        
        assert config.streaming_enabled
        assert config.enable_citation
        assert config.enable_query_validation
        assert config.enable_response_validation


class TestChatbotConfigIntegration:
    """Test integration with other configuration systems."""
    
    def test_config_with_rag_shared_key(self):
        """Test that chatbot config can share OpenAI key with RAG."""
        # Simulate shared environment
        os.environ["OPENAI_API_KEY"] = "shared-key-123"
        
        chatbot_config = ChatbotConfig.from_env()
        
        # Both should use the same key
        assert chatbot_config.openai_api_key == "shared-key-123"
        
        # Cleanup
        del os.environ["OPENAI_API_KEY"]
    
    def test_config_serialization(self):
        """Test that config can be represented as dict."""
        config = ChatbotConfig(
            openai_api_key="test",
            model="gpt-4",
            temperature=0.5
        )
        
        # Check key attributes exist
        assert hasattr(config, "model")
        assert hasattr(config, "temperature")
        assert hasattr(config, "openai_api_key")

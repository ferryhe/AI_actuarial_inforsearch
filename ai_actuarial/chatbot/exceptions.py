"""
Exception classes for the chatbot module.
"""


class ChatbotException(Exception):
    """Base exception for all chatbot-related errors."""
    pass


class RetrievalException(ChatbotException):
    """Exception raised when RAG retrieval fails."""
    pass


class LLMException(ChatbotException):
    """Exception raised when LLM API calls fail."""
    pass


class ConversationException(ChatbotException):
    """Exception raised for conversation management errors."""
    pass


class InvalidKBException(ChatbotException):
    """Exception raised when KB ID is invalid or not found."""
    pass


class InvalidModeException(ChatbotException):
    """Exception raised when chatbot mode is invalid."""
    pass


class NoResultsException(RetrievalException):
    """Exception raised when no retrieval results are found."""
    pass


class CitationValidationException(ChatbotException):
    """Exception raised when citation validation fails."""
    pass

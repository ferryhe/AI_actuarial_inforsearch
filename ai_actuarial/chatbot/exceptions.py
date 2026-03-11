"""
Exception classes for the chatbot module.
"""


class ChatbotException(Exception):
    """Base exception for all chatbot-related errors."""
    pass


class RetrievalException(ChatbotException):
    """Exception raised when RAG retrieval fails."""
    pass


class EmbeddingConfigurationMismatchException(RetrievalException):
    """Raised when KB index embeddings are incompatible with current query embeddings."""

    def __init__(
        self,
        message: str,
        *,
        kb_id: str,
        current_provider: str,
        current_model: str,
        current_dimension: int | None,
        index_provider: str | None,
        index_model: str | None,
        index_dimension: int | None,
        needs_reindex: bool = True,
    ) -> None:
        super().__init__(message)
        self.kb_id = kb_id
        self.current_provider = current_provider
        self.current_model = current_model
        self.current_dimension = current_dimension
        self.index_provider = index_provider
        self.index_model = index_model
        self.index_dimension = index_dimension
        self.needs_reindex = needs_reindex


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

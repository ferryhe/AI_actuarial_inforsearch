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

    code = "LLM_PROVIDER_UNAVAILABLE"
    classification = "provider_error"
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        classification: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if classification is not None:
            self.classification = classification
        if retryable is not None:
            self.retryable = retryable


class LLMProviderError(LLMException):
    """Safe provider failure suitable for API classification."""

    code = "LLM_PROVIDER_UNAVAILABLE"
    classification = "upstream"
    retryable = True
    safe_message = "The AI provider is temporarily unavailable."

    def __init__(self, _provider_detail: str | None = None):
        super().__init__(self.safe_message)


class LLMContextLengthError(LLMProviderError):
    code = "LLM_CONTEXT_LENGTH"
    classification = "context_length"
    safe_message = "The selected document is too large for the active AI model."


class LLMTimeoutError(LLMProviderError):
    code = "LLM_PROVIDER_TIMEOUT"
    classification = "timeout"
    safe_message = "AI provider timeout."


class LLMUpstreamError(LLMProviderError):
    pass


class LLMAuthenticationError(LLMProviderError):
    code = "CHAT_PROVIDER_AUTH"
    classification = "authentication"
    retryable = False
    safe_message = "Authentication failed for the AI provider."


class ConversationException(ChatbotException):
    """Exception raised for conversation management errors."""

    pass


class InvalidKBException(ChatbotException):
    """Exception raised when KB ID is invalid or not found."""

    pass


class NoResultsException(RetrievalException):
    """Exception raised when no retrieval results are found."""

    pass

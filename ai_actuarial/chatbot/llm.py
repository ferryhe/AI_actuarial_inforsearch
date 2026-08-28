"""
LLM integration for chatbot.

Provides OpenAI GPT integration with retry logic, rate limiting,
and error handling.
"""

import logging
import time
from typing import List, Dict, Any, Optional

import openai

from ai_actuarial.ai_runtime import is_chat_provider_supported
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import LLMException
from ai_actuarial.chatbot.prompts import build_full_prompt

logger = logging.getLogger(__name__)


_OPENAI_MAX_COMPLETION_TOKENS_PREFIXES = (
    "gpt-5",
    "o1",
    "o3",
    "o4",
)

_MISSING = object()


class _TransientEmptyResponse(Exception):
    """Internal signal for a retryable empty or malformed provider response."""

    def __init__(self, classification: str):
        super().__init__(classification)
        self.classification = classification


def _is_explicit_azure_gpt5_deployment(
    provider: str | None,
    model: str | None,
) -> bool:
    """Recognize only Azure deployment names that explicitly name GPT-5."""
    if str(provider or "").strip().lower() != "azure_openai":
        return False
    deployment = f"-{str(model or '').strip().lower().replace('_', '-')}-"
    return any(
        marker in deployment
        for marker in ("-gpt5-", "-gpt5.", "-gpt-5-", "-gpt-5.")
    )


def _uses_max_completion_tokens(provider: str | None, model: str | None) -> bool:
    """Return True for OpenAI chat models that reject deprecated max_tokens."""
    provider_norm = str(provider or "").strip().lower()
    if provider_norm not in {"openai", "azure_openai"}:
        return False
    model_norm = str(model or "").strip().lower().split("/")[-1]
    return model_norm.startswith(
        _OPENAI_MAX_COMPLETION_TOKENS_PREFIXES
    ) or _is_explicit_azure_gpt5_deployment(provider, model)


def _uses_default_temperature_only(provider: str | None, model: str | None) -> bool:
    """Return True for OpenAI GPT-5 models that reject custom temperature values."""
    provider_norm = str(provider or "").strip().lower()
    model_norm = str(model or "").strip().lower().split("/")[-1]
    return provider_norm in {"openai", "azure_openai"} and (
        model_norm.startswith("gpt-5")
        or _is_explicit_azure_gpt5_deployment(provider, model)
    )


def _supports_reasoning_effort(provider: str | None, model: str | None) -> bool:
    """Return True when recovery may safely send the reasoning_effort parameter."""
    return _uses_max_completion_tokens(provider, model)


def _matches_known_model(
    provider: str | None,
    model: str | None,
    direct_name: str,
    azure_markers: tuple[str, ...],
) -> bool:
    model_norm = str(model or "").strip().lower().split("/")[-1]
    if model_norm == direct_name or model_norm.startswith(f"{direct_name}-20"):
        return True
    if str(provider or "").strip().lower() != "azure_openai":
        return False
    deployment = f"-{model_norm.replace('_', '-')}-"
    return any(marker in deployment for marker in azure_markers)


def _compatible_reasoning_effort(
    provider: str | None,
    model: str | None,
    configured_effort: str | None,
) -> str | None:
    """Omit configured efforts known to be invalid for specific OpenAI models."""
    effort = str(configured_effort or "").strip().lower()
    if not effort or not _supports_reasoning_effort(provider, model):
        return None
    if _matches_known_model(
        provider,
        model,
        "gpt-5-pro",
        ("-gpt5-pro-", "-gpt-5-pro-"),
    ):
        return effort if effort == "high" else None
    if _matches_known_model(
        provider,
        model,
        "gpt-5.1",
        ("-gpt5.1-", "-gpt-5.1-"),
    ):
        return effort if effort in {"none", "low", "medium", "high"} else None
    return effort


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _safe_log_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


def _extract_text_content(content: Any) -> tuple[str | None, str]:
    if content is _MISSING:
        return None, "missing_content"
    if content is None:
        return None, "null_content"
    if isinstance(content, str):
        if not content:
            return None, "empty_content"
        if not content.strip():
            return None, "whitespace_content"
        return content, "text"
    if isinstance(content, (list, tuple)):
        text_parts: list[str] = []
        for part in content:
            part_type = str(_field(part, "type", "") or "").strip().lower()
            if part_type not in {"text", "output_text"}:
                continue
            part_text = _field(part, "text", None)
            if isinstance(part_text, str):
                text_parts.append(part_text)
        combined = "".join(text_parts)
        if not combined:
            return None, "empty_structured_content"
        if not combined.strip():
            return None, "whitespace_content"
        return combined, "structured_text"
    return None, "unsupported_content"


def _classify_response(response: Any) -> tuple[str | None, str, str | None]:
    choices = _field(response, "choices", None)
    if not isinstance(choices, (list, tuple)) or not choices:
        return None, "missing_choices", None
    choice = choices[0]
    finish_reason_value = _field(choice, "finish_reason", None)
    finish_reason = (
        finish_reason_value.strip().lower()
        if isinstance(finish_reason_value, str)
        else None
    )
    if finish_reason == "content_filter":
        return None, "content_filter", finish_reason
    message = _field(choice, "message", _MISSING)
    if message is _MISSING or message is None:
        return None, "missing_message", finish_reason
    refusal = _field(message, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        return None, "refusal", finish_reason
    content, classification = _extract_text_content(
        _field(message, "content", _MISSING)
    )
    return content, classification, finish_reason


class LLMClient:
    """
    LLM client with OpenAI integration.
    
    Features:
    - Support for GPT-4, GPT-4-turbo, GPT-3.5-turbo
    - Retry logic with exponential backoff
    - Rate limiting
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        config: Optional[ChatbotConfig] = None,
        *,
        storage=None,
    ):
        """
        Initialize LLM client.
        
        Args:
            config: Chatbot configuration
        
        Raises:
            LLMException: If API key is missing
        """
        self.config = config or ChatbotConfig.from_config(storage=storage)
        
        # Validate configuration
        try:
            self.config.validate()
        except ValueError as e:
            raise LLMException(f"Invalid configuration: {e}")
        
        # Initialize OpenAI-compatible client
        if not is_chat_provider_supported(self.config.llm_provider):
            raise LLMException(
                f"Unsupported LLM provider: {self.config.llm_provider}"
            )
        client_kwargs: dict[str, Any] = {
            "api_key": self.config.api_key,
            "timeout": 60.0,
        }
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url
        self.client = openai.OpenAI(**client_kwargs)
        
        # Rate limiting state
        self._last_request_time = 0.0
        self._min_request_interval = 60.0 / self.config.rate_limit_rpm
        
        logger.info(
            f"Initialized LLM client with provider={self.config.llm_provider}, "
            f"model={self.config.model}"
        )
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> str:
        """
        Generate response from LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use (default: config.model)
            temperature: Sampling temperature (default: config.temperature)
            max_tokens: Maximum tokens to generate (default: config.max_tokens)
            stream: Whether to stream response (not implemented in MVP)
        
        Returns:
            Generated text response
        
        Raises:
            LLMException: If generation fails
        """
        model = model or self.config.model
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens
        
        # Validate inputs
        if not messages:
            raise LLMException("Messages list cannot be empty")
        
        for msg in messages:
            if 'role' not in msg or 'content' not in msg:
                raise LLMException(
                    f"Invalid message format: {msg}. Must have 'role' and 'content'"
                )
        
        # Rate limiting
        self._apply_rate_limit()
        
        # Retry logic
        attempt = 0
        last_error = None
        recovery_used = False
        
        while attempt < self.config.max_retries:
            try:
                attempt += 1
                logger.info(
                    f"Generating response with model={model}, "
                    f"temperature={temperature}, max_tokens={max_tokens}, "
                    f"attempt={attempt}"
                )
                
                response = self.client.chat.completions.create(
                    **self._completion_request_kwargs(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=stream,
                    )
                )
                
                if stream:
                    raise LLMException("Streaming not yet supported")

                is_recovery = False
                while True:
                    content, classification, finish_reason = _classify_response(response)
                    self._log_response_metadata(
                        response,
                        model=model,
                        finish_reason=finish_reason,
                        classification=classification,
                        attempt=attempt,
                        recovery=is_recovery,
                        successful=content is not None,
                    )
                    if content is not None:
                        return content
                    if classification == "refusal":
                        raise LLMException("LLM response was refused")
                    if classification == "content_filter":
                        raise LLMException("LLM response was blocked by content filtering")
                    if (
                        finish_reason == "length"
                        and self.config.length_recovery_enabled
                        and not recovery_used
                        and attempt < self.config.max_retries
                    ):
                        recovery_used = True
                        is_recovery = True
                        attempt += 1
                        try:
                            response = self.client.chat.completions.create(
                                **self._completion_request_kwargs(
                                    messages=messages,
                                    model=model,
                                    temperature=temperature,
                                    max_tokens=self.config.length_recovery_max_tokens,
                                    stream=stream,
                                    reasoning_effort=self.config.length_recovery_reasoning_effort,
                                )
                            )
                        except openai.BadRequestError as exc:
                            raise LLMException(
                                "LLM length recovery request was rejected due to "
                                "incompatible parameters"
                            ) from exc
                        continue
                    if finish_reason == "length" and is_recovery:
                        raise LLMException(
                            "LLM response remained empty after bounded recovery"
                        )
                    if finish_reason == "length":
                        raise LLMException(
                            "LLM completion exhausted its output budget without visible content"
                        )
                    raise _TransientEmptyResponse(classification)

            except _TransientEmptyResponse as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "Retrying empty or malformed LLM response "
                        "classification=%s wait_seconds=%.1f attempt=%s/%s",
                        exc.classification,
                        wait_time,
                        attempt + 1,
                        self.config.max_retries,
                    )
                    time.sleep(wait_time)
                else:
                    raise LLMException(
                        "LLM response was empty or malformed after "
                        f"{self.config.max_retries} attempts"
                    )

            except LLMException:
                raise
                
            except openai.AuthenticationError as e:
                # Authentication errors are not retryable
                logger.error("Authentication error from LLM provider")
                raise LLMException(
                    "Authentication failed. Please check your API key."
                ) from e
            
            except openai.RateLimitError as e:
                # Rate limit - wait and retry
                last_error = e
                
                if attempt < self.config.max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Rate limit exceeded. Retrying in {wait_time:.1f}s "
                        f"(attempt {attempt+1}/{self.config.max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded for rate limit")
                    raise LLMException(
                        f"Rate limit exceeded after {self.config.max_retries} retries"
                    )
            
            except openai.APITimeoutError as e:
                # Timeout - retry with backoff
                last_error = e
                
                if attempt < self.config.max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        f"API timeout. Retrying in {wait_time:.1f}s "
                        f"(attempt {attempt+1}/{self.config.max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded for timeout")
                    raise LLMException(
                        f"API timeout after {self.config.max_retries} retries"
                    )
            
            except openai.APIError as e:
                # General API error - retry
                last_error = e
                
                if attempt < self.config.max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        f"API error. Retrying in {wait_time:.1f}s "
                        f"(attempt {attempt+1}/{self.config.max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded for API error")
                    raise LLMException(
                        f"API error after {self.config.max_retries} retries: {e}"
                    )
            
            except Exception as e:
                # Unexpected error - fail immediately
                logger.error(
                    "Unexpected error during LLM generation error_type=%s",
                    type(e).__name__,
                )
                raise LLMException("Unexpected LLM generation error") from e
        
        # Should not reach here, but just in case
        raise LLMException(
            f"Failed to generate response after {self.config.max_retries} retries: {last_error}"
        )

    def _completion_request_kwargs(
        self,
        *,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
        reasoning_effort: str | None = None,
    ) -> Dict[str, Any]:
        request_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if not _uses_default_temperature_only(self.config.llm_provider, model):
            request_kwargs["temperature"] = temperature
        if _uses_max_completion_tokens(self.config.llm_provider, model):
            request_kwargs["max_completion_tokens"] = max_tokens
        else:
            request_kwargs["max_tokens"] = max_tokens
        compatible_effort = _compatible_reasoning_effort(
            self.config.llm_provider,
            model,
            reasoning_effort,
        )
        if compatible_effort:
            request_kwargs["reasoning_effort"] = compatible_effort
        return request_kwargs

    def _log_response_metadata(
        self,
        response: Any,
        *,
        model: str,
        finish_reason: str | None,
        classification: str,
        attempt: int,
        recovery: bool,
        successful: bool,
    ) -> None:
        usage = _field(response, "usage", None)
        completion_details = _field(usage, "completion_tokens_details", None)
        response_id = _safe_log_value(_field(response, "id", None)) or _safe_log_value(
            _field(response, "_request_id", None)
        )
        log_method = logger.info if successful else logger.warning
        log_method(
            "LLM response metadata provider=%s model=%s finish_reason=%s "
            "classification=%s attempt=%s response_id=%s prompt_tokens=%s "
            "completion_tokens=%s total_tokens=%s reasoning_tokens=%s recovery=%s",
            self.config.llm_provider,
            model,
            finish_reason,
            classification,
            attempt,
            response_id,
            _safe_log_value(_field(usage, "prompt_tokens", None)),
            _safe_log_value(_field(usage, "completion_tokens", None)),
            _safe_log_value(_field(usage, "total_tokens", None)),
            _safe_log_value(_field(completion_details, "reasoning_tokens", None)),
            recovery,
        )

    def generate_response(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        mode: str = "expert",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        prompts_override: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Build a chat prompt from query+chunks and generate a response.

        This method is a compatibility wrapper used by chat routes.
        """
        messages = build_full_prompt(
            mode=mode,
            retrieved_chunks=chunks,
            query=query,
            conversation_history=conversation_history or [],
            prompts_override=prompts_override,
        )
        return self.generate(messages=messages)
    
    def _apply_rate_limit(self):
        """Apply rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self._min_request_interval:
            wait_time = self._min_request_interval - time_since_last
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            time.sleep(wait_time)
        
        self._last_request_time = time.time()
    
    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff delay for retry.
        
        Args:
            attempt: Retry attempt number (1-indexed)
        
        Returns:
            Delay in seconds
        """
        if self.config.exponential_backoff:
            # Exponential backoff: retry_delay * 2^(attempt-1)
            return self.config.retry_delay * (2 ** (attempt - 1))
        else:
            # Linear backoff
            return self.config.retry_delay * attempt
    
    def validate_response(
        self,
        response: str,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate LLM response quality and citations.
        
        Args:
            response: Generated response text
            retrieved_chunks: Retrieved chunks used for generation
        
        Returns:
            Validation result dict with:
            - valid: bool
            - issues: List[str]
            - citations_found: List[str]
            - citations_valid: bool
        """
        issues = []
        
        # Extract citations from response
        citations = self._extract_citations(response)
        
        # Get filenames from retrieved chunks
        retrieved_filenames = {
            chunk['metadata']['filename']
            for chunk in retrieved_chunks
        }
        
        # Validate citations
        invalid_citations = []
        for citation in citations:
            if citation not in retrieved_filenames:
                invalid_citations.append(citation)
        
        if invalid_citations:
            issues.append(
                f"Invalid citations (not in retrieved chunks): {invalid_citations}"
            )
        
        # Check for hallucination indicators
        if not citations and len(response) > 50:
            issues.append("Response lacks citations despite substantial length")
        
        # Check for "I don't know" phrases (good for uncertainty)
        uncertainty_phrases = [
            "i don't have",
            "i don't know",
            "not enough information",
            "based on the available",
            "according to the provided"
        ]
        
        has_uncertainty = any(
            phrase in response.lower()
            for phrase in uncertainty_phrases
        )
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'citations_found': list(citations),
            'citations_valid': len(invalid_citations) == 0,
            'has_uncertainty_language': has_uncertainty
        }
    
    def _extract_citations(self, text: str) -> List[str]:
        """
        Extract citations from response text.
        
        Looks for [Source: filename] patterns.
        
        Args:
            text: Response text
        
        Returns:
            List of cited filenames
        """
        import re
        
        # Pattern: [Source: filename.pdf] or [Source: file1.pdf, file2.pdf]
        pattern = r'\[Source:\s*([^\]]+)\]'
        matches = re.findall(pattern, text)
        
        citations = []
        for match in matches:
            # Split by comma in case of multiple citations
            filenames = [f.strip() for f in match.split(',')]
            citations.extend(filenames)
        
        return citations
    
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            model: Model to use for tokenization (default: config.model)
        
        Returns:
            Estimated token count
        """
        model = model or self.config.model
        
        try:
            import tiktoken
            
            # Get encoding for model
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                # Default to cl100k_base for GPT-4
                encoding = tiktoken.get_encoding("cl100k_base")
            
            return len(encoding.encode(text))
            
        except ImportError:
            # Fallback: approximate 4 chars per token
            logger.warning("tiktoken not available, using approximate token count")
            return len(text) // 4

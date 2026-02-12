"""
LLM integration for chatbot.

Provides OpenAI GPT integration with retry logic, rate limiting,
and error handling.
"""

import logging
import time
from typing import List, Dict, Any, Optional

from openai import OpenAI, APITimeoutError, RateLimitError, APIError, AuthenticationError

from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import LLMException

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM client with OpenAI integration.
    
    Features:
    - Support for GPT-4, GPT-4-turbo, GPT-3.5-turbo
    - Retry logic with exponential backoff
    - Rate limiting
    - Comprehensive error handling
    """
    
    def __init__(self, config: Optional[ChatbotConfig] = None):
        """
        Initialize LLM client.
        
        Args:
            config: Chatbot configuration
        
        Raises:
            LLMException: If API key is missing
        """
        self.config = config or ChatbotConfig()
        
        # Validate configuration
        try:
            self.config.validate()
        except ValueError as e:
            raise LLMException(f"Invalid configuration: {e}")
        
        # Initialize OpenAI client
        if self.config.llm_provider == "openai":
            self.client = OpenAI(
                api_key=self.config.api_key,
                timeout=60.0  # 60 second timeout
            )
        else:
            raise LLMException(
                f"Unsupported LLM provider: {self.config.llm_provider}"
            )
        
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
        
        while attempt < self.config.max_retries:
            try:
                logger.info(
                    f"Generating response with model={model}, "
                    f"temperature={temperature}, max_tokens={max_tokens}, "
                    f"attempt={attempt+1}"
                )
                
                # Call OpenAI API
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream
                )
                
                # Extract content
                if stream:
                    # Streaming not implemented in MVP
                    raise LLMException("Streaming not yet supported")
                else:
                    content = response.choices[0].message.content
                
                if not content:
                    raise LLMException("Empty response from LLM")
                
                logger.info(
                    f"Generated response successfully "
                    f"(length={len(content)} chars, "
                    f"tokens={response.usage.total_tokens if response.usage else 'unknown'})"
                )
                
                return content
                
            except AuthenticationError as e:
                # Authentication errors are not retryable
                logger.error(f"Authentication error: {e}")
                raise LLMException(
                    "Authentication failed. Please check your API key."
                )
            
            except RateLimitError as e:
                # Rate limit - wait and retry
                attempt += 1
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
            
            except APITimeoutError as e:
                # Timeout - retry with backoff
                attempt += 1
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
            
            except APIError as e:
                # General API error - retry
                attempt += 1
                last_error = e
                
                if attempt < self.config.max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        f"API error: {e}. Retrying in {wait_time:.1f}s "
                        f"(attempt {attempt+1}/{self.config.max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Max retries exceeded for API error: {e}")
                    raise LLMException(
                        f"API error after {self.config.max_retries} retries: {e}"
                    )
            
            except Exception as e:
                # Unexpected error - fail immediately
                logger.error(f"Unexpected error during LLM generation: {e}")
                raise LLMException(f"Unexpected error: {e}")
        
        # Should not reach here, but just in case
        raise LLMException(
            f"Failed to generate response after {self.config.max_retries} retries: {last_error}"
        )
    
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

"""
Embedding generation for RAG system.

Supports multiple embedding providers:
- OpenAI (text-embedding-3-large, text-embedding-3-small)
- Local models via sentence-transformers (fallback)

Features:
- Batch processing for efficiency
- Retry logic with exponential backoff
- Rate limiting
- Embedding caching
"""

import time
import hashlib
import json
from pathlib import Path
from typing import List, Optional

from openai import OpenAI, APITimeoutError, RateLimitError, APIError

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import EmbeddingException


class EmbeddingCache:
    """Simple file-based cache for embeddings."""
    
    def __init__(self, cache_dir: str):
        """
        Initialize embedding cache.
        
        Args:
            cache_dir: Directory to store cached embeddings
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, text: str, model: str) -> str:
        """Generate cache key for text and model."""
        content = f"{model}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, text: str, model: str) -> Optional[List[float]]:
        """Retrieve cached embedding."""
        cache_key = self._get_cache_key(text, model)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    return data['embedding']
            except (json.JSONDecodeError, KeyError, IOError):
                # Cache corrupted, ignore
                return None
        
        return None
    
    def set(self, text: str, model: str, embedding: List[float]) -> None:
        """Store embedding in cache."""
        cache_key = self._get_cache_key(text, model)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump({'embedding': embedding}, f)
        except IOError:
            # Failed to cache, not critical
            pass


class EmbeddingGenerator:
    """
    Generate embeddings for text chunks.
    
    Supports multiple providers with automatic fallback and caching.
    """
    
    def __init__(self, config: Optional[RAGConfig] = None):
        """
        Initialize embedding generator.
        
        Args:
            config: RAG configuration (defaults to env-based config)
        """
        self.config = config or RAGConfig.from_env()
        self.cache = EmbeddingCache(f"{self.config.data_dir}/embeddings_cache") if self.config.embedding_cache_enabled else None
        
        # Initialize OpenAI client if using OpenAI
        if self.config.embedding_provider == "openai":
            if not self.config.openai_api_key:
                raise EmbeddingException("OpenAI API key required but not provided")
            
            self.openai_client = OpenAI(
                api_key=self.config.openai_api_key,
                timeout=self.config.openai_timeout
            )
        else:
            self.openai_client = None
        
        # Lazy-load local model if needed
        self._local_model = None
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            EmbeddingException: If embedding generation fails
        """
        if not texts:
            return []
        
        # Check cache first
        if self.cache:
            cached_embeddings = []
            uncached_indices = []
            uncached_texts = []
            
            for i, text in enumerate(texts):
                cached = self.cache.get(text, self.config.embedding_model)
                if cached:
                    cached_embeddings.append((i, cached))
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
            
            # Generate embeddings for uncached texts
            if uncached_texts:
                if self.config.embedding_provider == "openai":
                    new_embeddings = self._generate_openai_embeddings(uncached_texts)
                else:
                    new_embeddings = self._generate_local_embeddings(uncached_texts)
                
                # Cache new embeddings
                for text, embedding in zip(uncached_texts, new_embeddings):
                    self.cache.set(text, self.config.embedding_model, embedding)
            else:
                new_embeddings = []
            
            # Combine cached and new embeddings in original order
            all_embeddings = [None] * len(texts)
            for i, emb in cached_embeddings:
                all_embeddings[i] = emb
            for i, emb in zip(uncached_indices, new_embeddings):
                all_embeddings[i] = emb
            
            return all_embeddings
        else:
            # No caching
            if self.config.embedding_provider == "openai":
                return self._generate_openai_embeddings(texts)
            else:
                return self._generate_local_embeddings(texts)
    
    def _generate_openai_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using OpenAI API with batching and retries.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        batch_size = self.config.embedding_batch_size
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self._generate_openai_batch_with_retry(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    def _generate_openai_batch_with_retry(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch with retry logic.
        
        Args:
            texts: Batch of texts to embed
            
        Returns:
            List of embedding vectors
        """
        max_retries = self.config.openai_max_retries
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                response = self.openai_client.embeddings.create(
                    model=self.config.embedding_model,
                    input=texts
                )
                
                # Extract embeddings in order
                embeddings = [item.embedding for item in response.data]
                return embeddings
                
            except RateLimitError as e:
                if attempt < max_retries - 1:
                    # Exponential backoff
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise EmbeddingException(f"Rate limit exceeded after {max_retries} retries: {e}")
            
            except APITimeoutError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise EmbeddingException(f"API timeout after {max_retries} retries: {e}")
            
            except APIError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise EmbeddingException(f"API error after {max_retries} retries: {e}")
            
            except Exception as e:
                raise EmbeddingException(f"Unexpected error generating embeddings: {e}")
        
        raise EmbeddingException("Failed to generate embeddings")
    
    def _generate_local_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using local sentence-transformers model.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                # Use a multilingual model for Chinese + English support
                model_name = "paraphrase-multilingual-mpnet-base-v2"
                self._local_model = SentenceTransformer(model_name)
            except ImportError:
                raise EmbeddingException(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
        
        try:
            embeddings = self._local_model.encode(texts, convert_to_numpy=True)
            # Convert numpy arrays to lists
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            raise EmbeddingException(f"Local embedding generation failed: {e}")
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings for the current model.
        
        Returns:
            Embedding dimension
        """
        if self.config.embedding_provider == "openai":
            # OpenAI embedding dimensions
            if "text-embedding-3-large" in self.config.embedding_model:
                return 3072
            elif "text-embedding-3-small" in self.config.embedding_model:
                return 1536
            elif "ada-002" in self.config.embedding_model:
                return 1536
            else:
                # Unknown model, generate test embedding to determine dimension
                test_emb = self.generate_embeddings(["test"])
                return len(test_emb[0]) if test_emb else 1536
        else:
            # Local model - generate test embedding
            test_emb = self.generate_embeddings(["test"])
            return len(test_emb[0]) if test_emb else 768  # Default for most local models


def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0
):
    """
    Decorator for retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (APITimeoutError, RateLimitError, APIError) as e:
                    if attempt < max_retries - 1:
                        delay = min(initial_delay * (2 ** attempt), max_delay)
                        time.sleep(delay)
                    else:
                        raise EmbeddingException(f"Failed after {max_retries} retries: {e}")
            return None
        return wrapper
    return decorator

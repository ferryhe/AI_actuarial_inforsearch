"""
Dynamic LLM model discovery and management.

This module provides functionality to discover available models from LLM providers
and cache them for efficient access. Similar to ragflow's implementation.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Default/fallback models if API discovery fails
DEFAULT_MODELS = {
    "openai": [
        {"name": "gpt-4-turbo", "display_name": "GPT-4 Turbo", "types": ["chatbot", "catalog"]},
        {"name": "gpt-4", "display_name": "GPT-4", "types": ["chatbot", "catalog"]},
        {"name": "gpt-4o", "display_name": "GPT-4o", "types": ["chatbot", "catalog"]},
        {"name": "gpt-4o-mini", "display_name": "GPT-4o Mini", "types": ["chatbot", "catalog"]},
        {"name": "gpt-3.5-turbo", "display_name": "GPT-3.5 Turbo", "types": ["chatbot", "catalog"]},
        {"name": "text-embedding-3-large", "display_name": "Text Embedding 3 Large", "types": ["embeddings"]},
        {"name": "text-embedding-3-small", "display_name": "Text Embedding 3 Small", "types": ["embeddings"]},
        {"name": "text-embedding-ada-002", "display_name": "Text Embedding Ada 002", "types": ["embeddings"]},
    ],
    "mistral": [
        {"name": "mistral-large-latest", "display_name": "Mistral Large", "types": ["chatbot", "catalog"]},
        {"name": "mistral-medium-latest", "display_name": "Mistral Medium", "types": ["chatbot", "catalog"]},
        {"name": "mistral-small-latest", "display_name": "Mistral Small", "types": ["chatbot", "catalog"]},
        {"name": "open-mistral-7b", "display_name": "Mistral 7B", "types": ["chatbot", "catalog"]},
        {"name": "pixtral-large-latest", "display_name": "Pixtral Large", "types": ["chatbot", "catalog", "ocr"]},
        {"name": "mistral-ocr-latest", "display_name": "Mistral OCR Latest", "types": ["ocr"]},
        {"name": "pixtral-12b-2409", "display_name": "Pixtral 12B", "types": ["ocr"]},
    ],
    "siliconflow": [
        {"name": "deepseek-ai/DeepSeek-V3", "display_name": "DeepSeek V3", "types": ["chatbot", "catalog"]},
        {"name": "deepseek-ai/DeepSeek-R1", "display_name": "DeepSeek R1", "types": ["chatbot", "catalog"]},
        {"name": "Qwen/Qwen2.5-72B-Instruct", "display_name": "Qwen 2.5 72B", "types": ["chatbot", "catalog"]},
        {"name": "deepseek-ai/DeepSeek-OCR", "display_name": "DeepSeek OCR", "types": ["ocr"]},
        {"name": "BAAI/bge-large-zh-v1.5", "display_name": "BGE Large ZH", "types": ["embeddings"]},
        {"name": "BAAI/bge-m3", "display_name": "BGE M3", "types": ["embeddings"]},
    ],
    "anthropic": [
        {"name": "claude-opus-4-5", "display_name": "Claude Opus 4.5", "types": ["chatbot", "catalog"]},
        {"name": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet", "types": ["chatbot", "catalog"]},
        {"name": "claude-3-5-haiku-20241022", "display_name": "Claude 3.5 Haiku", "types": ["chatbot", "catalog"]},
        {"name": "claude-3-opus-20240229", "display_name": "Claude 3 Opus", "types": ["chatbot", "catalog"]},
    ],
    "google": [
        {"name": "gemini-2.0-flash", "display_name": "Gemini 2.0 Flash", "types": ["chatbot", "catalog"]},
        {"name": "gemini-2.0-pro-exp", "display_name": "Gemini 2.0 Pro Exp", "types": ["chatbot", "catalog"]},
        {"name": "gemini-1.5-pro", "display_name": "Gemini 1.5 Pro", "types": ["chatbot", "catalog"]},
        {"name": "gemini-1.5-flash", "display_name": "Gemini 1.5 Flash", "types": ["chatbot", "catalog"]},
        {"name": "text-embedding-004", "display_name": "Text Embedding 004", "types": ["embeddings"]},
    ],
    "deepseek": [
        {"name": "deepseek-chat", "display_name": "DeepSeek Chat (V3)", "types": ["chatbot", "catalog"]},
        {"name": "deepseek-reasoner", "display_name": "DeepSeek Reasoner (R1)", "types": ["chatbot", "catalog"]},
    ],
    "zhipuai": [
        {"name": "glm-4-plus", "display_name": "GLM-4 Plus", "types": ["chatbot", "catalog"]},
        {"name": "glm-4-air", "display_name": "GLM-4 Air", "types": ["chatbot", "catalog"]},
        {"name": "glm-4v-plus", "display_name": "GLM-4V Plus", "types": ["chatbot", "catalog"]},
        {"name": "embedding-3", "display_name": "Embedding 3", "types": ["embeddings"]},
    ],
    "moonshot": [
        {"name": "moonshot-v1-128k", "display_name": "Moonshot v1 128K", "types": ["chatbot", "catalog"]},
        {"name": "moonshot-v1-32k", "display_name": "Moonshot v1 32K", "types": ["chatbot", "catalog"]},
        {"name": "moonshot-v1-8k", "display_name": "Moonshot v1 8K", "types": ["chatbot", "catalog"]},
    ],
    "kimi": [
        {"name": "kimi-latest", "display_name": "Kimi Latest", "types": ["chatbot", "catalog"]},
        {"name": "moonshot-v1-128k", "display_name": "Moonshot v1 128K", "types": ["chatbot", "catalog"]},
        {"name": "moonshot-v1-32k", "display_name": "Moonshot v1 32K", "types": ["chatbot", "catalog"]},
        {"name": "moonshot-v1-8k", "display_name": "Moonshot v1 8K", "types": ["chatbot", "catalog"]},
    ],
    "minimax": [
        {"name": "MiniMax-Text-01", "display_name": "MiniMax Text 01", "types": ["chatbot", "catalog"]},
        {"name": "abab6.5s-chat", "display_name": "ABAB 6.5s Chat", "types": ["chatbot", "catalog"]},
        {"name": "abab6.5-chat", "display_name": "ABAB 6.5 Chat", "types": ["chatbot", "catalog"]},
        {"name": "embo-01", "display_name": "Embo 01", "types": ["embeddings"]},
    ],
    "qwen": [
        {"name": "qwen-max", "display_name": "Qwen Max", "types": ["chatbot", "catalog"]},
        {"name": "qwen-plus", "display_name": "Qwen Plus", "types": ["chatbot", "catalog"]},
        {"name": "qwen-long", "display_name": "Qwen Long", "types": ["chatbot", "catalog"]},
        {"name": "text-embedding-v3", "display_name": "Qwen Text Embedding V3", "types": ["embeddings"]},
    ],
    "cohere": [
        {"name": "command-r-plus", "display_name": "Command R+", "types": ["chatbot", "catalog"]},
        {"name": "command-r", "display_name": "Command R", "types": ["chatbot", "catalog"]},
        {"name": "embed-multilingual-v3.0", "display_name": "Embed Multilingual v3", "types": ["embeddings"]},
    ],
    "mathpix": [
        {"name": "mathpix", "display_name": "Mathpix", "types": ["ocr"]},
    ],
    "local": [
        {"name": "sentence-transformers", "display_name": "Sentence Transformers", "types": ["embeddings"]},
        {"name": "opendataloader", "display_name": "OpenDataLoader", "types": ["ocr"]},
        {"name": "markitdown", "display_name": "MarkItDown", "types": ["ocr"]},
        {"name": "docling", "display_name": "Docling", "types": ["ocr"]},
        {"name": "marker", "display_name": "Marker", "types": ["ocr"]},
    ],
}


class ModelCache:
    """Thread-safe cache for discovered models."""
    
    def __init__(self, refresh_interval_hours: int = 24):
        """
        Initialize model cache.
        
        Args:
            refresh_interval_hours: How often to refresh models from APIs (default: 24 hours)
        """
        self._models: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()
        self._last_refresh: Optional[datetime] = None
        self._refresh_interval = timedelta(hours=refresh_interval_hours)
        self._initialized = False
    
    def get_models(self, provider: Optional[str] = None) -> Dict[str, List[Dict]]:
        """
        Get cached models, refresh if needed.
        
        Args:
            provider: Specific provider to get models for, or None for all
            
        Returns:
            Dictionary of models by provider (deep copy to prevent mutation)
        """
        # Check if refresh is needed (with lock)
        needs_refresh = False
        with self._lock:
            if not self._initialized:
                needs_refresh = True
            elif self._last_refresh and datetime.now() - self._last_refresh > self._refresh_interval:
                needs_refresh = True
        
        # Perform refresh outside lock to avoid blocking
        if needs_refresh:
            self._perform_refresh()
        
        # Return cached models (with lock for consistency)
        with self._lock:
            if provider:
                # Deep copy to prevent mutation
                provider_models = self._models.get(provider, DEFAULT_MODELS.get(provider, []))
                return {provider: [model.copy() for model in provider_models]}
            # Deep copy all models to prevent mutation
            return {
                prov: [model.copy() for model in models]
                for prov, models in self._models.items()
            }
    
    def force_refresh(self):
        """Force an immediate refresh of the model cache."""
        self._perform_refresh()
    
    def _perform_refresh(self):
        """Perform model refresh with minimal lock duration."""
        logger.info("Refreshing model cache from providers...")
        
        # Fetch from all providers (without holding lock)
        new_models = {}
        new_models["openai"] = self._fetch_openai_models()
        new_models["mistral"] = self._fetch_mistral_models()
        new_models["siliconflow"] = self._fetch_siliconflow_models()
        new_models["anthropic"] = DEFAULT_MODELS["anthropic"]  # Static known models
        new_models["local"] = DEFAULT_MODELS["local"]  # Local models are static
        new_models["mathpix"] = DEFAULT_MODELS["mathpix"]  # Mathpix has no model-list API in this app
        # Additional providers with static model lists (no live discovery API yet)
        for _provider in ("google", "deepseek", "zhipuai", "moonshot", "kimi", "minimax", "qwen", "cohere"):
            new_models[_provider] = DEFAULT_MODELS[_provider]
        
        # Atomically swap in the new cache (with lock)
        with self._lock:
            self._models = new_models
            self._last_refresh = datetime.now()
            self._initialized = True
        
        logger.info(f"Model cache refreshed at {self._last_refresh}")
    
    def _fetch_openai_models(self) -> List[Dict]:
        """
        Fetch available models from OpenAI API.
        
        Returns:
            List of model dictionaries
        """
        try:
            from openai import OpenAI
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, using default models")
                return DEFAULT_MODELS["openai"]
            
            client = OpenAI(api_key=api_key, timeout=10.0)
            
            # Fetch available models
            response = client.models.list()
            available_model_ids = {model.id for model in response.data}
            
            # Map known models to their capabilities
            # Only include models that are actually available
            known_models = {
                # Chat/completion models
                "gpt-4-turbo": {"display_name": "GPT-4 Turbo", "types": ["chatbot", "catalog"]},
                "gpt-4-turbo-preview": {"display_name": "GPT-4 Turbo Preview", "types": ["chatbot", "catalog"]},
                "gpt-4": {"display_name": "GPT-4", "types": ["chatbot", "catalog"]},
                "gpt-4o": {"display_name": "GPT-4o", "types": ["chatbot", "catalog"]},
                "gpt-4o-mini": {"display_name": "GPT-4o Mini", "types": ["chatbot", "catalog"]},
                "gpt-3.5-turbo": {"display_name": "GPT-3.5 Turbo", "types": ["chatbot", "catalog"]},
                "gpt-3.5-turbo-16k": {"display_name": "GPT-3.5 Turbo 16K", "types": ["chatbot", "catalog"]},
                # Embedding models
                "text-embedding-3-large": {"display_name": "Text Embedding 3 Large", "types": ["embeddings"]},
                "text-embedding-3-small": {"display_name": "Text Embedding 3 Small", "types": ["embeddings"]},
                "text-embedding-ada-002": {"display_name": "Text Embedding Ada 002", "types": ["embeddings"]},
            }
            
            models = []
            for model_id, info in known_models.items():
                # Check if the model or any of its dated variants are available
                # Use exact match or dated variant (e.g., gpt-4-0613) to avoid false positives
                if any(mid == model_id or mid.startswith(model_id + '-') for mid in available_model_ids):
                    models.append({
                        "name": model_id,
                        "display_name": info["display_name"],
                        "types": info["types"]
                    })
            
            if models:
                logger.info(f"Fetched {len(models)} OpenAI models from API")
                return models
            else:
                logger.warning("No known OpenAI models found in API response, using defaults")
                return DEFAULT_MODELS["openai"]
            
        except Exception as e:
            logger.warning(f"Failed to fetch OpenAI models: {e}, using defaults")
            return DEFAULT_MODELS["openai"]
    
    def _fetch_mistral_models(self) -> List[Dict]:
        """
        Fetch available models from Mistral API.
        
        Returns:
            List of model dictionaries
        """
        try:
            from mistralai import Mistral
            
            api_key = os.getenv("MISTRAL_API_KEY")
            if not api_key:
                logger.warning("MISTRAL_API_KEY not set, using default models")
                return DEFAULT_MODELS["mistral"]
            
            client = Mistral(api_key=api_key, timeout_ms=10000)
            
            # Fetch available models
            response = client.models.list()
            available_model_ids = {model.id for model in response.data}
            
            # Map known OCR models
            known_models = {
                "pixtral-12b-2409": {"display_name": "Pixtral 12B", "types": ["ocr"]},
                "mistral-ocr-latest": {"display_name": "Mistral OCR Latest", "types": ["ocr"]},
            }
            
            models = []
            for model_id, info in known_models.items():
                if model_id in available_model_ids:
                    models.append({
                        "name": model_id,
                        "display_name": info["display_name"],
                        "types": info["types"]
                    })
            
            if models:
                logger.info(f"Fetched {len(models)} Mistral models from API")
                return models
            else:
                logger.warning("No known Mistral models found in API response, using defaults")
                return DEFAULT_MODELS["mistral"]
            
        except Exception as e:
            logger.warning(f"Failed to fetch Mistral models: {e}, using defaults")
            return DEFAULT_MODELS["mistral"]
    
    def _fetch_siliconflow_models(self) -> List[Dict]:
        """
        Fetch available models from SiliconFlow API.
        
        Note: SiliconFlow uses OpenAI-compatible API
        
        Returns:
            List of model dictionaries
        """
        try:
            from openai import OpenAI
            
            api_key = os.getenv("SILICONFLOW_API_KEY")
            base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
            
            if not api_key:
                logger.warning("SILICONFLOW_API_KEY not set, using default models")
                return DEFAULT_MODELS["siliconflow"]
            
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=10.0
            )
            
            # Fetch available models
            response = client.models.list()
            available_model_ids = {model.id for model in response.data}
            
            # Map known OCR models
            known_models = {
                "deepseek-ai/DeepSeek-OCR": {"display_name": "DeepSeek OCR", "types": ["ocr"]},
            }
            
            models = []
            for model_id, info in known_models.items():
                if model_id in available_model_ids:
                    models.append({
                        "name": model_id,
                        "display_name": info["display_name"],
                        "types": info["types"]
                    })
            
            if models:
                logger.info(f"Fetched {len(models)} SiliconFlow models from API")
                return models
            else:
                logger.warning("No known SiliconFlow models found in API response, using defaults")
                return DEFAULT_MODELS["siliconflow"]
            
        except Exception as e:
            logger.warning(f"Failed to fetch SiliconFlow models: {e}, using defaults")
            return DEFAULT_MODELS["siliconflow"]


# Global model cache instance
_model_cache: Optional[ModelCache] = None
_cache_lock = threading.Lock()


def get_model_cache() -> ModelCache:
    """
    Get the global model cache instance.
    
    Returns:
        The global ModelCache instance
    """
    global _model_cache
    
    with _cache_lock:
        if _model_cache is None:
            _model_cache = ModelCache(refresh_interval_hours=24)
        return _model_cache


def get_available_models(provider: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Get available models from cache.
    
    This is the main public API for getting models.
    
    Args:
        provider: Specific provider to get models for, or None for all
        
    Returns:
        Dictionary of models by provider
    """
    cache = get_model_cache()
    return cache.get_models(provider)


def refresh_models():
    """Force refresh of the model cache."""
    cache = get_model_cache()
    cache.force_refresh()


def initialize_models():
    """
    Initialize model cache on application startup.
    
    This should be called during application initialization to populate
    the cache before the first request.
    """
    logger.info("Initializing model cache on startup...")
    cache = get_model_cache()
    # First access will trigger initialization
    cache.get_models()
    logger.info("Model cache initialization complete")

"""
Dynamic LLM model discovery and management.

This module provides functionality to discover available models from LLM providers
and cache them for efficient access. Similar to ragflow's implementation.
"""

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

logger = logging.getLogger(__name__)


def _model(name: str, display_name: str, *types: str) -> Dict[str, Any]:
    return {"name": name, "display_name": display_name, "types": list(types)}


# Default/fallback models if API discovery fails
DEFAULT_MODELS = {
    "openai": [
        _model("gpt-5.5", "GPT-5.5", "chatbot", "catalog"),
        _model("gpt-5.4", "GPT-5.4", "chatbot", "catalog"),
        _model("gpt-5.4-mini", "GPT-5.4 Mini", "chatbot", "catalog"),
        _model("gpt-5.4-nano", "GPT-5.4 Nano", "chatbot", "catalog"),
        _model("gpt-5.2", "GPT-5.2", "chatbot", "catalog"),
        _model("gpt-5.1", "GPT-5.1", "chatbot", "catalog"),
        _model("gpt-5", "GPT-5", "chatbot", "catalog"),
        _model("gpt-4.1", "GPT-4.1", "chatbot", "catalog"),
        _model("gpt-4.1-mini", "GPT-4.1 Mini", "chatbot", "catalog"),
        _model("gpt-4o", "GPT-4o", "chatbot", "catalog"),
        _model("gpt-4o-mini", "GPT-4o Mini", "chatbot", "catalog"),
        _model("o3", "o3", "chatbot", "catalog"),
        _model("o4-mini", "o4 Mini", "chatbot", "catalog"),
        _model("gpt-4-turbo", "GPT-4 Turbo", "chatbot", "catalog"),
        _model("text-embedding-3-large", "Text Embedding 3 Large", "embeddings"),
        _model("text-embedding-3-small", "Text Embedding 3 Small", "embeddings"),
        _model("text-embedding-ada-002", "Text Embedding Ada 002", "embeddings"),
    ],
    "mistral": [
        _model("mistral-medium-latest", "Mistral Medium Latest", "chatbot", "catalog"),
        _model("mistral-small-latest", "Mistral Small Latest", "chatbot", "catalog"),
        _model("mistral-large-latest", "Mistral Large Latest", "chatbot", "catalog"),
        _model("magistral-medium-latest", "Magistral Medium Latest", "chatbot", "catalog"),
        _model("magistral-small-latest", "Magistral Small Latest", "chatbot", "catalog"),
        _model("devstral-medium-latest", "Devstral Medium Latest", "chatbot", "catalog"),
        _model("devstral-small-latest", "Devstral Small Latest", "chatbot", "catalog"),
        _model("codestral-latest", "Codestral Latest", "chatbot", "catalog"),
        _model("ministral-8b-latest", "Ministral 8B Latest", "chatbot", "catalog"),
        _model("ministral-3b-latest", "Ministral 3B Latest", "chatbot", "catalog"),
        _model("pixtral-large-latest", "Pixtral Large Latest", "chatbot", "catalog"),
        _model("mistral-ocr-latest", "Mistral OCR Latest", "ocr"),
        _model("mistral-embed", "Mistral Embed", "embeddings"),
        _model("codestral-embed-latest", "Codestral Embed Latest", "embeddings"),
    ],
    "siliconflow": [
        _model("deepseek-ai/DeepSeek-V3.2", "DeepSeek V3.2", "chatbot", "catalog"),
        _model("deepseek-ai/DeepSeek-V3.1", "DeepSeek V3.1", "chatbot", "catalog"),
        _model("deepseek-ai/DeepSeek-V3", "DeepSeek V3", "chatbot", "catalog"),
        _model("deepseek-ai/DeepSeek-R1", "DeepSeek R1", "chatbot", "catalog"),
        _model("Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen3 235B A22B Instruct", "chatbot", "catalog"),
        _model("Qwen/Qwen3-30B-A3B", "Qwen3 30B A3B", "chatbot", "catalog"),
        _model("Qwen/Qwen2.5-72B-Instruct", "Qwen 2.5 72B Instruct", "chatbot", "catalog"),
        _model("THUDM/GLM-4.6", "GLM 4.6", "chatbot", "catalog"),
        _model("deepseek-ai/DeepSeek-OCR", "DeepSeek OCR", "ocr"),
        _model("Qwen/Qwen3-Embedding-8B", "Qwen3 Embedding 8B", "embeddings"),
        _model("Qwen/Qwen3-Embedding-4B", "Qwen3 Embedding 4B", "embeddings"),
        _model("Qwen/Qwen3-Embedding-0.6B", "Qwen3 Embedding 0.6B", "embeddings"),
        _model("BAAI/bge-m3", "BGE M3", "embeddings"),
        _model("BAAI/bge-large-zh-v1.5", "BGE Large ZH", "embeddings"),
        _model("BAAI/bge-large-en-v1.5", "BGE Large EN", "embeddings"),
    ],
    "anthropic": [
        _model("claude-opus-4-7", "Claude Opus 4.7", "chatbot", "catalog"),
        _model("claude-sonnet-4-6", "Claude Sonnet 4.6", "chatbot", "catalog"),
        _model("claude-haiku-4-5", "Claude Haiku 4.5", "chatbot", "catalog"),
        _model("claude-haiku-4-5-20251001", "Claude Haiku 4.5 20251001", "chatbot", "catalog"),
        _model("claude-opus-4-5", "Claude Opus 4.5", "chatbot", "catalog"),
        _model("claude-sonnet-4-5", "Claude Sonnet 4.5", "chatbot", "catalog"),
        _model("claude-opus-4-1-20250805", "Claude Opus 4.1", "chatbot", "catalog"),
        _model("claude-sonnet-4-20250514", "Claude Sonnet 4", "chatbot", "catalog"),
        _model("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet", "chatbot", "catalog"),
        _model("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet", "chatbot", "catalog"),
        _model("claude-3-5-haiku-20241022", "Claude 3.5 Haiku", "chatbot", "catalog"),
    ],
    "google": [
        _model("gemini-3-pro-preview", "Gemini 3 Pro Preview", "chatbot", "catalog"),
        _model("gemini-3-flash-preview", "Gemini 3 Flash Preview", "chatbot", "catalog"),
        _model("gemini-2.5-pro", "Gemini 2.5 Pro", "chatbot", "catalog"),
        _model("gemini-2.5-flash", "Gemini 2.5 Flash", "chatbot", "catalog"),
        _model("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "chatbot", "catalog"),
        _model("gemini-2.0-flash", "Gemini 2.0 Flash", "chatbot", "catalog"),
        _model("gemini-embedding-2", "Gemini Embedding 2", "embeddings"),
        _model("gemini-embedding-001", "Gemini Embedding 001", "embeddings"),
        _model("text-embedding-004", "Text Embedding 004", "embeddings"),
    ],
    "deepseek": [
        _model("deepseek-chat", "DeepSeek Chat", "chatbot", "catalog"),
        _model("deepseek-reasoner", "DeepSeek Reasoner", "chatbot", "catalog"),
    ],
    "zhipuai": [
        _model("glm-4.7", "GLM-4.7", "chatbot", "catalog"),
        _model("glm-4.6", "GLM-4.6", "chatbot", "catalog"),
        _model("glm-4.5", "GLM-4.5", "chatbot", "catalog"),
        _model("glm-4.5-air", "GLM-4.5 Air", "chatbot", "catalog"),
        _model("glm-4.5-flash", "GLM-4.5 Flash", "chatbot", "catalog"),
        _model("glm-z1-air", "GLM Z1 Air", "chatbot", "catalog"),
        _model("glm-4-plus", "GLM-4 Plus", "chatbot", "catalog"),
        _model("glm-4-air", "GLM-4 Air", "chatbot", "catalog"),
        _model("glm-4v-plus", "GLM-4V Plus", "chatbot", "catalog"),
        _model("embedding-3", "Embedding 3", "embeddings"),
    ],
    "moonshot": [
        _model("kimi-k2.5", "Kimi K2.5", "chatbot", "catalog"),
        _model("kimi-k2-thinking", "Kimi K2 Thinking", "chatbot", "catalog"),
        _model("kimi-k2-thinking-turbo", "Kimi K2 Thinking Turbo", "chatbot", "catalog"),
        _model("kimi-k2-0905-preview", "Kimi K2 0905 Preview", "chatbot", "catalog"),
        _model("kimi-k2-turbo-preview", "Kimi K2 Turbo Preview", "chatbot", "catalog"),
        _model("kimi-k2-0711-preview", "Kimi K2 0711 Preview", "chatbot", "catalog"),
        _model("moonshot-v1-128k", "Moonshot v1 128K", "chatbot", "catalog"),
        _model("moonshot-v1-32k", "Moonshot v1 32K", "chatbot", "catalog"),
        _model("moonshot-v1-8k", "Moonshot v1 8K", "chatbot", "catalog"),
    ],
    "kimi": [
        _model("kimi-k2.5", "Kimi K2.5", "chatbot", "catalog"),
        _model("kimi-k2-thinking", "Kimi K2 Thinking", "chatbot", "catalog"),
        _model("kimi-k2-thinking-turbo", "Kimi K2 Thinking Turbo", "chatbot", "catalog"),
        _model("kimi-k2-0905-preview", "Kimi K2 0905 Preview", "chatbot", "catalog"),
        _model("kimi-k2-turbo-preview", "Kimi K2 Turbo Preview", "chatbot", "catalog"),
        _model("kimi-k2-0711-preview", "Kimi K2 0711 Preview", "chatbot", "catalog"),
        _model("kimi-latest", "Kimi Latest", "chatbot", "catalog"),
        _model("moonshot-v1-128k", "Moonshot v1 128K", "chatbot", "catalog"),
        _model("moonshot-v1-32k", "Moonshot v1 32K", "chatbot", "catalog"),
        _model("moonshot-v1-8k", "Moonshot v1 8K", "chatbot", "catalog"),
    ],
    "minimax": [
        _model("MiniMax-M2.7", "MiniMax M2.7", "chatbot", "catalog"),
        _model("MiniMax-M2.7-highspeed", "MiniMax M2.7 Highspeed", "chatbot", "catalog"),
        _model("MiniMax-M2.5", "MiniMax M2.5", "chatbot", "catalog"),
        _model("MiniMax-M2.5-highspeed", "MiniMax M2.5 Highspeed", "chatbot", "catalog"),
        _model("MiniMax-M2.1", "MiniMax M2.1", "chatbot", "catalog"),
        _model("MiniMax-M2.1-highspeed", "MiniMax M2.1 Highspeed", "chatbot", "catalog"),
        _model("MiniMax-M2", "MiniMax M2", "chatbot", "catalog"),
        _model("MiniMax-Text-01", "MiniMax Text 01", "chatbot", "catalog"),
        _model("MiniMax-VL-01", "MiniMax VL 01", "chatbot", "catalog"),
        _model("embo-01", "Embo 01", "embeddings"),
    ],
    "qwen": [
        _model("qwen3-max", "Qwen3 Max", "chatbot", "catalog"),
        _model("qwen3-max-2026-01-23", "Qwen3 Max 2026-01-23", "chatbot", "catalog"),
        _model("qwen3-max-preview", "Qwen3 Max Preview", "chatbot", "catalog"),
        _model("qwen-max", "Qwen Max", "chatbot", "catalog"),
        _model("qwen-max-latest", "Qwen Max Latest", "chatbot", "catalog"),
        _model("qwen-plus", "Qwen Plus", "chatbot", "catalog"),
        _model("qwen-plus-latest", "Qwen Plus Latest", "chatbot", "catalog"),
        _model("qwen-flash", "Qwen Flash", "chatbot", "catalog"),
        _model("qwen-long", "Qwen Long", "chatbot", "catalog"),
        _model("qwen-long-latest", "Qwen Long Latest", "chatbot", "catalog"),
        _model("qwq-plus", "QwQ Plus", "chatbot", "catalog"),
        _model("deepseek-v3.2", "DeepSeek V3.2", "chatbot", "catalog"),
        _model("deepseek-r1", "DeepSeek R1", "chatbot", "catalog"),
        _model("text-embedding-v4", "Text Embedding V4", "embeddings"),
        _model("text-embedding-v3", "Text Embedding V3", "embeddings"),
        _model("qwen3-vl-embedding", "Qwen3 VL Embedding", "embeddings"),
    ],
    "cohere": [
        _model("command-a-03-2025", "Command A", "chatbot", "catalog"),
        _model("command-r-plus-08-2024", "Command R+ 08-2024", "chatbot", "catalog"),
        _model("command-r-08-2024", "Command R 08-2024", "chatbot", "catalog"),
        _model("command-r-plus", "Command R+", "chatbot", "catalog"),
        _model("command-r", "Command R", "chatbot", "catalog"),
        _model("embed-v4.0", "Embed v4.0", "embeddings"),
        _model("embed-english-v3.0", "Embed English v3", "embeddings"),
        _model("embed-multilingual-v3.0", "Embed Multilingual v3", "embeddings"),
    ],
    "openrouter": [
        _model("openai/gpt-5.5", "OpenAI GPT-5.5", "chatbot", "catalog"),
        _model("openai/gpt-5.4", "OpenAI GPT-5.4", "chatbot", "catalog"),
        _model("anthropic/claude-opus-4.7", "Claude Opus 4.7", "chatbot", "catalog"),
        _model("anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6", "chatbot", "catalog"),
        _model("google/gemini-3-pro-preview", "Gemini 3 Pro Preview", "chatbot", "catalog"),
        _model("google/gemini-3-flash-preview", "Gemini 3 Flash Preview", "chatbot", "catalog"),
        _model("deepseek/deepseek-chat", "DeepSeek Chat", "chatbot", "catalog"),
        _model("deepseek/deepseek-reasoner", "DeepSeek Reasoner", "chatbot", "catalog"),
        _model("qwen/qwen3-max", "Qwen3 Max", "chatbot", "catalog"),
        _model("minimax/minimax-m2.7", "MiniMax M2.7", "chatbot", "catalog"),
    ],
    "mathpix": [
        _model("mathpix", "Mathpix", "ocr"),
    ],
    "local": [
        _model("sentence-transformers", "Sentence Transformers", "embeddings"),
        _model("opendataloader", "OpenDataLoader", "ocr"),
        _model("markitdown", "MarkItDown", "ocr"),
        _model("docling", "Docling", "ocr"),
        _model("marker", "Marker", "ocr"),
    ],
}

OPENAI_COMPATIBLE_DISCOVERY = {
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1", True),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1", True),
    "zhipuai": ("ZHIPUAI_API_KEY", "ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4", True),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1", True),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL", "https://api.moonshot.cn/v1", True),
    "qwen": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1", True),
    "minimax": ("MINIMAX_API_KEY", "MINIMAX_BASE_URL", "https://api.minimax.chat/v1", True),
    "volcengine": ("VOLCENGINE_API_KEY", "VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3", True),
    "tencent_cloud": ("TENCENT_CLOUD_API_KEY", "TENCENT_CLOUD_BASE_URL", "https://api.hunyuan.cloud.tencent.com/v1", True),
    "baiduyiyan": ("BAIDUYIYAN_API_KEY", "BAIDUYIYAN_BASE_URL", "https://qianfan.baidubce.com/v2", True),
    "xunfei_spark": ("XUNFEI_SPARK_API_KEY", "XUNFEI_SPARK_BASE_URL", "https://spark-api-open.xf-yun.com/v1", True),
    "google_cloud": ("GOOGLE_CLOUD_API_KEY", "GOOGLE_CLOUD_BASE_URL", "https://aiplatform.googleapis.com/v1", True),
    # Local OpenAI-compatible servers are queried only when their base URL is explicitly configured.
    "vllm": ("VLLM_API_KEY", "VLLM_BASE_URL", "http://localhost:8001/v1", False),
    "localai": ("LOCALAI_API_KEY", "LOCALAI_BASE_URL", "http://localhost:8080/v1", False),
    "huggingface": ("HUGGINGFACE_API_KEY", "HUGGINGFACE_BASE_URL", "https://api-inference.huggingface.co/v1", True),
}

ProviderCredentialsMap = Mapping[str, Mapping[str, str | None]]

NON_TEXT_MODEL_PATTERNS = (
    "audio",
    "dall-e",
    "flux",
    "image",
    "imagen",
    "lyria",
    "moderation",
    "rerank",
    "realtime",
    "sora",
    "speech",
    "stable-diffusion",
    "sdxl",
    "transcribe",
    "translation",
    "tts",
    "veo",
    "video",
    "whisper",
)

EMBEDDING_MODEL_PATTERNS = (
    "bce-embedding",
    "bge",
    "e5",
    "embed",
    "embedding",
    "gte",
    "text-embedding",
)

OCR_MODEL_PATTERNS = (
    "deepseek-ocr",
    "docling",
    "markitdown",
    "marker",
    "mathpix",
    "ocr",
    "opendataloader",
    "paddleocr",
)


def _copy_models(models: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(model) for model in models]


def _credential_value(
    provider_credentials: ProviderCredentialsMap | None,
    provider: str,
    field: str,
) -> str | None:
    if not provider_credentials:
        return None
    value = provider_credentials.get(provider, {}).get(field)
    value = str(value or "").strip()
    return value or None


def _provider_api_key(
    provider: str,
    api_key_env: str,
    provider_credentials: ProviderCredentialsMap | None = None,
) -> str | None:
    return _credential_value(provider_credentials, provider, "api_key") or os.getenv(api_key_env) or None


def _provider_base_url(
    provider: str,
    base_url_env: str | None,
    default_base_url: str | None,
    provider_credentials: ProviderCredentialsMap | None = None,
) -> str | None:
    env_base_url = os.getenv(base_url_env) if base_url_env else None
    return _credential_value(provider_credentials, provider, "base_url") or env_base_url or default_base_url


def _model_id(raw_model: Any) -> str | None:
    model_id = getattr(raw_model, "id", None)
    if model_id is None and isinstance(raw_model, dict):
        model_id = raw_model.get("id")
    model_id = str(model_id or "").strip()
    return model_id or None


def _model_ids(raw_models: Iterable[Any]) -> Set[str]:
    return {model_id for model in raw_models if (model_id := _model_id(model))}


def _format_display_name(model_id: str) -> str:
    name = re.sub(r"[_-]+", " ", model_id.split("/")[-1]).strip()
    tokens = []
    for token in name.split():
        lower = token.lower()
        if lower in {"ai", "api", "gpt", "glm", "ocr", "vl", "vlm"}:
            tokens.append(lower.upper())
        elif re.fullmatch(r"[a-z]\d+(?:\.\d+)?", lower):
            tokens.append(lower)
        else:
            tokens.append(token[:1].upper() + token[1:])
    return " ".join(tokens) or model_id


def _contains_any(value: str, patterns: Iterable[str]) -> bool:
    return any(pattern in value for pattern in patterns)


def _is_non_text_model(model_id: str) -> bool:
    lower = model_id.lower()
    if _contains_any(lower, EMBEDDING_MODEL_PATTERNS) or _contains_any(lower, OCR_MODEL_PATTERNS):
        return False
    return _contains_any(lower, NON_TEXT_MODEL_PATTERNS)


def _infer_model_types(provider: str, model_id: str) -> List[str]:
    lower = model_id.lower()
    if _contains_any(lower, OCR_MODEL_PATTERNS):
        return ["ocr"]
    if _contains_any(lower, EMBEDDING_MODEL_PATTERNS):
        return ["embeddings"]
    if _is_non_text_model(model_id):
        return []
    if provider == "cohere" and lower.startswith("embed-"):
        return ["embeddings"]
    return ["chatbot", "catalog"]


def get_model_types(provider: str | None, model_id: str | None) -> List[str]:
    """Return known or inferred capability types for a provider model."""
    provider_norm = str(provider or "").strip().lower()
    model_norm = str(model_id or "").strip()
    if not model_norm:
        return []
    for model in DEFAULT_MODELS.get(provider_norm, []):
        if str(model.get("name") or "").strip() == model_norm:
            return list(model.get("types") or [])
    return _infer_model_types(provider_norm, model_norm)


def _dedupe_models(models: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for model in models:
        name = str(model.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(
            {
                "name": name,
                "display_name": str(model.get("display_name") or _format_display_name(name)),
                "types": list(model.get("types") or []),
            }
        )
    return deduped


def _has_exact_or_snapshot(model_id: str, available_model_ids: Set[str]) -> bool:
    return any(mid == model_id or mid.startswith(f"{model_id}-") for mid in available_model_ids)


def _build_models_from_ids(provider: str, available_model_ids: Set[str], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    models: List[Dict[str, Any]] = []
    for model in fallback:
        name = str(model.get("name") or "").strip()
        if name and _has_exact_or_snapshot(name, available_model_ids):
            models.append(dict(model))

    fallback_names = {str(model.get("name") or "") for model in fallback}
    for model_id in sorted(available_model_ids):
        if model_id in fallback_names:
            continue
        model_types = _infer_model_types(provider, model_id)
        if not model_types:
            continue
        models.append(_model(model_id, _format_display_name(model_id), *model_types))

    return _dedupe_models(models) or _copy_models(fallback)


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
    
    def get_models(
        self,
        provider: Optional[str] = None,
        *,
        provider_credentials: ProviderCredentialsMap | None = None,
    ) -> Dict[str, List[Dict]]:
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
            self._perform_refresh(provider_credentials=provider_credentials)
        
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
    
    def force_refresh(self, *, provider_credentials: ProviderCredentialsMap | None = None):
        """Force an immediate refresh of the model cache."""
        self._perform_refresh(provider_credentials=provider_credentials)
    
    def _perform_refresh(self, *, provider_credentials: ProviderCredentialsMap | None = None):
        """Perform model refresh with minimal lock duration."""
        logger.info("Refreshing model cache from providers...")
        
        # Fetch from all providers (without holding lock)
        new_models = {}
        new_models["openai"] = self._fetch_openai_models(provider_credentials=provider_credentials)
        new_models["mistral"] = self._fetch_mistral_models(provider_credentials=provider_credentials)
        new_models["siliconflow"] = self._fetch_siliconflow_models(provider_credentials=provider_credentials)
        for provider, discovery in OPENAI_COMPATIBLE_DISCOVERY.items():
            if provider in new_models:
                continue
            key_env, base_url_env, default_base_url, api_key_required = discovery
            new_models[provider] = self._fetch_openai_compatible_models(
                provider,
                api_key_env=key_env,
                base_url_env=base_url_env,
                default_base_url=default_base_url,
                api_key_required=api_key_required,
                provider_credentials=provider_credentials,
            )
        for provider, models in DEFAULT_MODELS.items():
            new_models.setdefault(provider, models)
        
        # Atomically swap in the new cache (with lock)
        with self._lock:
            self._models = new_models
            self._last_refresh = datetime.now()
            self._initialized = True
        
        logger.info(f"Model cache refreshed at {self._last_refresh}")
    
    def _fetch_openai_models(
        self,
        *,
        provider_credentials: ProviderCredentialsMap | None = None,
    ) -> List[Dict]:
        """
        Fetch available models from OpenAI API.
        
        Returns:
            List of model dictionaries
        """
        try:
            from openai import OpenAI
            
            api_key = _provider_api_key("openai", "OPENAI_API_KEY", provider_credentials)
            base_url = _provider_base_url("openai", "OPENAI_BASE_URL", None, provider_credentials)
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, using default models")
                return _copy_models(DEFAULT_MODELS["openai"])
            
            client_kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": 10.0}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
            
            response = client.models.list()
            available_model_ids = _model_ids(response.data)
            models = _build_models_from_ids("openai", available_model_ids, DEFAULT_MODELS["openai"])
            logger.info(f"Fetched {len(models)} OpenAI models from API")
            return models
            
        except Exception as e:
            logger.warning(f"Failed to fetch OpenAI models: {e}, using defaults")
            return _copy_models(DEFAULT_MODELS["openai"])
    
    def _fetch_mistral_models(
        self,
        *,
        provider_credentials: ProviderCredentialsMap | None = None,
    ) -> List[Dict]:
        """
        Fetch available models from Mistral API.
        
        Returns:
            List of model dictionaries
        """
        try:
            from mistralai import Mistral
            
            api_key = _provider_api_key("mistral", "MISTRAL_API_KEY", provider_credentials)
            if not api_key:
                logger.warning("MISTRAL_API_KEY not set, using default models")
                return _copy_models(DEFAULT_MODELS["mistral"])
            
            client = Mistral(api_key=api_key, timeout_ms=10000)
            
            response = client.models.list()
            available_model_ids = _model_ids(response.data)
            models = _build_models_from_ids("mistral", available_model_ids, DEFAULT_MODELS["mistral"])
            logger.info(f"Fetched {len(models)} Mistral models from API")
            return models
            
        except Exception as e:
            logger.warning(f"Failed to fetch Mistral models: {e}, using defaults")
            return _copy_models(DEFAULT_MODELS["mistral"])
    
    def _fetch_siliconflow_models(
        self,
        *,
        provider_credentials: ProviderCredentialsMap | None = None,
    ) -> List[Dict]:
        """
        Fetch available models from SiliconFlow API.
        
        Note: SiliconFlow uses OpenAI-compatible API
        
        Returns:
            List of model dictionaries
        """
        try:
            from openai import OpenAI
            
            api_key = _provider_api_key("siliconflow", "SILICONFLOW_API_KEY", provider_credentials)
            base_url = _provider_base_url(
                "siliconflow",
                "SILICONFLOW_BASE_URL",
                "https://api.siliconflow.cn/v1",
                provider_credentials,
            )
            
            if not api_key:
                logger.warning("SILICONFLOW_API_KEY not set, using default models")
                return _copy_models(DEFAULT_MODELS["siliconflow"])
            
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=10.0
            )
            
            response = client.models.list()
            available_model_ids = _model_ids(response.data)
            models = _build_models_from_ids("siliconflow", available_model_ids, DEFAULT_MODELS["siliconflow"])
            logger.info(f"Fetched {len(models)} SiliconFlow models from API")
            return models
            
        except Exception as e:
            logger.warning(f"Failed to fetch SiliconFlow models: {e}, using defaults")
            return _copy_models(DEFAULT_MODELS["siliconflow"])

    def _fetch_openai_compatible_models(
        self,
        provider: str,
        *,
        api_key_env: str,
        base_url_env: str,
        default_base_url: str,
        api_key_required: bool,
        provider_credentials: ProviderCredentialsMap | None = None,
    ) -> List[Dict]:
        """
        Fetch available models from an OpenAI-compatible provider.

        Providers without a model-list API, missing credentials, or local endpoints
        that were not explicitly configured fall back to the curated static list.
        """
        fallback = DEFAULT_MODELS.get(provider, [])
        try:
            from openai import OpenAI

            api_key = _provider_api_key(provider, api_key_env, provider_credentials)
            base_url = _provider_base_url(provider, base_url_env, default_base_url, provider_credentials)
            if api_key_required and not api_key:
                logger.debug("%s not set, using default %s models", api_key_env, provider)
                return _copy_models(fallback)
            if not api_key_required and not _provider_base_url(provider, base_url_env, None, provider_credentials):
                logger.debug("%s not set, skipping local model discovery for %s", base_url_env, provider)
                return _copy_models(fallback)

            client = OpenAI(api_key=api_key or "not-needed", base_url=base_url, timeout=10.0)
            response = client.models.list()
            models = _build_models_from_ids(provider, _model_ids(response.data), fallback)
            logger.info("Fetched %s %s models from OpenAI-compatible API", len(models), provider)
            return models
        except Exception as e:
            logger.warning(f"Failed to fetch {provider} models: {e}, using defaults")
            return _copy_models(fallback)


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


def get_available_models(
    provider: Optional[str] = None,
    *,
    provider_credentials: ProviderCredentialsMap | None = None,
) -> Dict[str, List[Dict]]:
    """
    Get available models from cache.
    
    This is the main public API for getting models.
    
    Args:
        provider: Specific provider to get models for, or None for all
        
    Returns:
        Dictionary of models by provider
    """
    cache = get_model_cache()
    return cache.get_models(provider, provider_credentials=provider_credentials)


def refresh_models(*, provider_credentials: ProviderCredentialsMap | None = None):
    """Force refresh of the model cache."""
    cache = get_model_cache()
    cache.force_refresh(provider_credentials=provider_credentials)


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

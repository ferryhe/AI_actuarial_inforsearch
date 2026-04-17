"""Unified AI runtime configuration and provider resolution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Mapping

import ai_actuarial.llm_models as llm_models
from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml

logger = logging.getLogger(__name__)

AI_SUPPORTED_PROVIDERS = {
    "openai",
    "azure_openai",
    "openrouter",
    "vllm",
    "localai",
    "huggingface",
    "mistral",
    "siliconflow",
    "anthropic",
    "google",
    "google_cloud",
    "deepseek",
    "zhipuai",
    "moonshot",
    "qwen",
    "cohere",
    "kimi",
    "minimax",
    "volcengine",
    "tencent_cloud",
    "baiduyiyan",
    "xunfei_spark",
    "bedrock",
    "fish_audio",
    "mineru",
    "paddleocr",
    "local",
}

KNOWN_LLM_PROVIDERS = {
    "openai": {
        "display_name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_hint": "sk-...",
    },
    "azure_openai": {
        "display_name": "Azure OpenAI",
        "default_base_url": "",
        "api_key_hint": "...",
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "api_key_hint": "sk-or-...",
    },
    "vllm": {
        "display_name": "vLLM",
        "default_base_url": "http://localhost:8001/v1",
        "api_key_hint": "optional",
    },
    "localai": {
        "display_name": "LocalAI",
        "default_base_url": "http://localhost:8080/v1",
        "api_key_hint": "optional",
    },
    "huggingface": {
        "display_name": "HuggingFace",
        "default_base_url": "https://api-inference.huggingface.co/v1",
        "api_key_hint": "hf_...",
    },
    "mistral": {
        "display_name": "Mistral AI",
        "default_base_url": "https://api.mistral.ai/v1",
        "api_key_hint": "...",
    },
    "anthropic": {
        "display_name": "Anthropic",
        "default_base_url": "https://api.anthropic.com",
        "api_key_hint": "sk-ant-...",
    },
    "google": {
        "display_name": "Google Gemini",
        "default_base_url": "https://generativelanguage.googleapis.com",
        "api_key_hint": "AIza...",
    },
    "google_cloud": {
        "display_name": "Google Cloud",
        "default_base_url": "https://aiplatform.googleapis.com/v1",
        "api_key_hint": "...",
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com/v1",
        "api_key_hint": "sk-...",
    },
    "zhipuai": {
        "display_name": "ZhipuAI",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_hint": "...",
    },
    "moonshot": {
        "display_name": "Moonshot (Kimi)",
        "default_base_url": "https://api.moonshot.cn/v1",
        "api_key_hint": "sk-...",
    },
    "qwen": {
        "display_name": "Qwen",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_hint": "sk-...",
    },
    "siliconflow": {
        "display_name": "SiliconFlow",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "api_key_hint": "sk-...",
    },
    "cohere": {
        "display_name": "Cohere",
        "default_base_url": "https://api.cohere.com/v1",
        "api_key_hint": "...",
    },
    "kimi": {
        "display_name": "Kimi (Moonshot v2)",
        "default_base_url": "https://api.moonshot.cn/v1",
        "api_key_hint": "sk-...",
    },
    "minimax": {
        "display_name": "MiniMax",
        "default_base_url": "https://api.minimax.chat/v1",
        "api_key_hint": "...",
    },
    "volcengine": {
        "display_name": "VolcEngine",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key_hint": "...",
    },
    "tencent_cloud": {
        "display_name": "Tencent Cloud",
        "default_base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "api_key_hint": "...",
    },
    "baiduyiyan": {
        "display_name": "BaiduYiyan",
        "default_base_url": "https://qianfan.baidubce.com/v2",
        "api_key_hint": "...",
    },
    "xunfei_spark": {
        "display_name": "XunFei Spark",
        "default_base_url": "https://spark-api-open.xf-yun.com/v1",
        "api_key_hint": "...",
    },
    "bedrock": {
        "display_name": "AWS Bedrock",
        "default_base_url": "",
        "api_key_hint": "AKIA...",
    },
    "fish_audio": {
        "display_name": "Fish Audio",
        "default_base_url": "https://api.fish.audio/v1",
        "api_key_hint": "...",
    },
    "mineru": {
        "display_name": "MinerU",
        "default_base_url": "",
        "api_key_hint": "optional",
    },
    "paddleocr": {
        "display_name": "PaddleOCR",
        "default_base_url": "",
        "api_key_hint": "optional",
    },
    "brave_search": {
        "display_name": "Brave Search",
        "default_base_url": "",
        "api_key_hint": "BSA...",
        "is_search_provider": True,
    },
    "serpapi": {
        "display_name": "Google (SerpAPI)",
        "default_base_url": "",
        "api_key_hint": "...",
        "is_search_provider": True,
    },
    "serper": {
        "display_name": "Google (Serper.dev)",
        "default_base_url": "",
        "api_key_hint": "...",
        "is_search_provider": True,
    },
    "tavily": {
        "display_name": "Tavily",
        "default_base_url": "",
        "api_key_hint": "tvly-...",
        "is_search_provider": True,
    },
}

PROVIDER_STARTUP_ENV_MAP = {
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
    "azure_openai": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_BASE_URL"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL"),
    "vllm": ("VLLM_API_KEY", "VLLM_BASE_URL"),
    "localai": ("LOCALAI_API_KEY", "LOCALAI_BASE_URL"),
    "huggingface": ("HUGGINGFACE_API_KEY", "HUGGINGFACE_BASE_URL"),
    "mistral": ("MISTRAL_API_KEY", "MISTRAL_BASE_URL"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"),
    "google": ("GOOGLE_API_KEY", "GOOGLE_BASE_URL"),
    "google_cloud": ("GOOGLE_CLOUD_API_KEY", "GOOGLE_CLOUD_BASE_URL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
    "zhipuai": ("ZHIPUAI_API_KEY", "ZHIPUAI_BASE_URL"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL"),
    "qwen": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "siliconflow": ("SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL"),
    "cohere": ("COHERE_API_KEY", "COHERE_BASE_URL"),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL"),
    "minimax": ("MINIMAX_API_KEY", "MINIMAX_BASE_URL"),
    "volcengine": ("VOLCENGINE_API_KEY", "VOLCENGINE_BASE_URL"),
    "tencent_cloud": ("TENCENT_CLOUD_API_KEY", "TENCENT_CLOUD_BASE_URL"),
    "baiduyiyan": ("BAIDUYIYAN_API_KEY", "BAIDUYIYAN_BASE_URL"),
    "xunfei_spark": ("XUNFEI_SPARK_API_KEY", "XUNFEI_SPARK_BASE_URL"),
    "bedrock": ("BEDROCK_API_KEY", "BEDROCK_BASE_URL"),
    "fish_audio": ("FISH_AUDIO_API_KEY", "FISH_AUDIO_BASE_URL"),
    "mineru": ("MINERU_API_KEY", "MINERU_BASE_URL"),
    "paddleocr": ("PADDLEOCR_API_KEY", "PADDLEOCR_BASE_URL"),
    "brave_search": ("BRAVE_API_KEY", None),
    "serpapi": ("SERPAPI_API_KEY", None),
    "serper": ("SERPER_API_KEY", None),
    "tavily": ("TAVILY_API_KEY", None),
}

PROVIDER_ENV_VARS = {
    provider: key_env
    for provider, (key_env, _) in PROVIDER_STARTUP_ENV_MAP.items()
}

PROVIDER_BASE_URL_ENV_VARS = {
    provider: base_url_env
    for provider, (_, base_url_env) in PROVIDER_STARTUP_ENV_MAP.items()
}

CHAT_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "azure_openai",
    "openrouter",
    "vllm",
    "localai",
    "huggingface",
    "mistral",
    "deepseek",
    "moonshot",
    "kimi",
    "qwen",
    "zhipuai",
    "siliconflow",
    "minimax",
    "volcengine",
    "tencent_cloud",
    "baiduyiyan",
    "xunfei_spark",
    "google_cloud",
    "bedrock",
}

EMBEDDING_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "azure_openai",
    "openrouter",
    "vllm",
    "localai",
    "huggingface",
    "siliconflow",
    "qwen",
    "zhipuai",
    "minimax",
    "volcengine",
    "tencent_cloud",
    "baiduyiyan",
    "xunfei_spark",
    "google_cloud",
    "bedrock",
}

DEFAULT_AI_FUNCTION_CONFIG = {
    "catalog": {"provider": "openai", "model": "gpt-4o-mini"},
    "embeddings": {"provider": "openai", "model": "text-embedding-3-large"},
    "chatbot": {"provider": "openai", "model": "gpt-4-turbo"},
    "ocr": {"provider": "local", "model": "docling"},
}

KNOWN_EMBEDDING_MODEL_DIMENSIONS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
    "text-embedding-v3": 1024,
    "text-embedding-004": 768,
    "embed-multilingual-v3.0": 1024,
    "all-MiniLM-L6-v2": 384,
    "BAAI/bge-m3": 1024,
    "BAAI/bge-large-zh-v1.5": 1024,
    "sentence-transformers": 768,
}

KNOWN_EMBEDDING_MODEL_PROVIDERS = {
    "text-embedding-3-large": "openai",
    "text-embedding-3-small": "openai",
    "text-embedding-ada-002": "openai",
    "text-embedding-v3": "qwen",
    "text-embedding-004": "google",
    "embedding-3": "minimax",
    "embo-01": "zhipuai",
    "embed-multilingual-v3.0": "cohere",
    "all-MiniLM-L6-v2": "local",
    "BAAI/bge-m3": "local",
    "BAAI/bge-large-zh-v1.5": "local",
    "sentence-transformers": "local",
}

OCR_ENGINE_PROVIDER_MAP = {
    "docling": "local",
    "marker": "local",
    "local": "local",
    "mistral": "mistral",
    "deepseekocr": "siliconflow",
}

OCR_PROVIDER_ENGINE_MAP = {
    "local": "docling",
    "mistral": "mistral",
    "siliconflow": "deepseekocr",
    "mineru": "mineru",
    "paddleocr": "paddleocr",
}

FUNCTION_BINDING_TO_SECTION = {
    "chat": "chatbot",
    "chatbot": "chatbot",
    "embeddings": "embeddings",
    "catalog": "catalog",
    "ocr": "ocr",
}

OPTIONAL_API_KEY_SENTINEL = "__HERMES_OPTIONAL_EMPTY_API_KEY__"

SECTION_TO_FUNCTION_BINDING = {
    "chatbot": "chat",
    "embeddings": "embeddings",
    "catalog": "catalog",
    "ocr": "ocr",
}


@dataclass(frozen=True)
class ProviderCredentials:
    provider: str
    api_key: str | None
    base_url: str | None
    source: str
    configured: bool


@dataclass(frozen=True)
class AIFunctionRuntime:
    function_name: str
    provider: str
    model: str
    raw_config: dict[str, Any]
    api_key: str | None = None
    base_url: str | None = None
    credential_source: str = "none"


@dataclass(frozen=True)
class OCRRuntime:
    engine: str
    provider: str
    model: str
    api_key: str | None
    base_url: str | None
    credential_source: str
    raw_config: dict[str, Any]


def list_provider_registry() -> dict[str, list[dict[str, Any]]]:
    providers: list[dict[str, Any]] = []
    for provider_id, info in sorted(KNOWN_LLM_PROVIDERS.items()):
        providers.append(
            {
                "provider_id": provider_id,
                "display_name": info.get("display_name", provider_id),
                "default_base_url": info.get("default_base_url") or None,
                "api_key_hint": info.get("api_key_hint") or "",
                "provider_type": _provider_type_labels(provider_id, info),
                "supports": {
                    "chat": is_chat_provider_supported(provider_id),
                    "embeddings": is_embedding_provider_supported(provider_id),
                    "catalog": is_catalog_provider_supported(provider_id),
                    "ocr": provider_id in OCR_PROVIDER_ENGINE_MAP or provider_id == "local",
                    "search": bool(info.get("is_search_provider")),
                },
                "status": "active",
            }
        )
    return {"providers": providers}


def list_provider_credentials(*, storage: Any | None = None) -> dict[str, list[dict[str, Any]]]:
    credentials: list[dict[str, Any]] = []
    seen: set[str] = set()

    if storage is not None:
        try:
            for category in ("llm", "search"):
                for entry in storage.list_llm_providers(category=category):
                    provider = str(entry.get("provider") or "").strip().lower()
                    entry_category = str(entry.get("category") or category).strip().lower() or category
                    decrypt_ok = True
                    try:
                        from ai_actuarial.services.token_encryption import TokenEncryption

                        TokenEncryption().decrypt(str(entry.get("api_key_encrypted") or ""))
                    except Exception:
                        decrypt_ok = False
                    credentials.append(
                        {
                            "credential_id": f"{provider}:{entry_category}:db:{entry.get('id')}",
                            "provider_id": provider,
                            "label": f"{provider} ({entry_category})",
                            "category": entry_category,
                            "source": "db",
                            "api_base_url": str(entry.get("api_base_url") or "").strip() or _get_effective_base_url(provider),
                            "status": str(entry.get("status") or "active").strip() or "active",
                            "decrypt_ok": decrypt_ok,
                            "is_default": True,
                            "created_at": entry.get("created_at"),
                            "updated_at": entry.get("updated_at"),
                            "last_error": None if decrypt_ok else "decrypt_failed",
                            "notes": entry.get("notes"),
                        }
                    )
                    seen.add(f"{provider}:{entry_category}")
        except Exception:
            logger.exception("Failed to list provider credentials from storage")

    for provider, (key_env, _base_env) in sorted(PROVIDER_STARTUP_ENV_MAP.items()):
        api_key = str(os.getenv(key_env) or "").strip()
        if not api_key:
            continue
        category = "search" if bool(KNOWN_LLM_PROVIDERS.get(provider, {}).get("is_search_provider")) else "llm"
        if f"{provider}:{category}" in seen:
            continue
        credentials.append(
            {
                "credential_id": f"{provider}:{category}:env",
                "provider_id": provider,
                "label": f"{provider} ({category})",
                "category": category,
                "source": "env",
                "api_base_url": _get_effective_base_url(provider),
                "status": "active",
                "decrypt_ok": True,
                "is_default": True,
                "created_at": None,
                "updated_at": None,
                "last_error": None,
                "notes": None,
            }
        )

    return {"credentials": credentials}


def get_model_catalog() -> dict[str, Any]:
    return {
        "available": llm_models.get_available_models(),
        "providers": list_provider_registry()["providers"],
    }


def get_ai_routing(*, storage: Any | None = None, yaml_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    for function_name in ["chat", "embeddings", "catalog", "ocr"]:
        section_name = FUNCTION_BINDING_TO_SECTION[function_name]
        runtime = resolve_ai_function_runtime(section_name, storage=storage, yaml_config=yaml_config)
        binding: dict[str, Any] = {
            "function_name": function_name,
            "config_section": section_name,
            "provider": runtime.provider,
            "model": runtime.model,
            "credential_source": runtime.credential_source,
            "binding_source": "sites.yaml:ai_config",
            "configured": bool(runtime.api_key) or runtime.provider == "local",
            "api_base_url": runtime.base_url,
            "raw_config": runtime.raw_config,
        }
        if function_name == "embeddings":
            binding["embedding_dimension"] = infer_embedding_dimension(runtime.model)
            binding["embedding_fingerprint"] = build_embedding_fingerprint(runtime.provider, runtime.model)
        bindings.append(binding)
    return {"bindings": bindings}


def get_provider_api_key_env_var(provider: str | None) -> str | None:
    """Return the env var that stores the provider API key."""
    return PROVIDER_ENV_VARS.get(_normalize_provider(provider))


def get_provider_base_url_env_var(provider: str | None) -> str | None:
    """Return the env var that stores the provider base URL."""
    return PROVIDER_BASE_URL_ENV_VARS.get(_normalize_provider(provider))


def get_provider_default_base_url(provider: str | None) -> str | None:
    """Return the default base URL for a provider if one is known."""
    info = KNOWN_LLM_PROVIDERS.get(_normalize_provider(provider), {})
    base_url = str(info.get("default_base_url") or "").strip()
    return base_url or None


def is_chat_provider_supported(provider: str | None) -> bool:
    """Return whether the provider is currently supported by the chat runtime."""
    return _normalize_provider(provider) in CHAT_OPENAI_COMPATIBLE_PROVIDERS


def is_catalog_provider_supported(provider: str | None) -> bool:
    """Return whether the provider is currently supported by the catalog runtime."""
    return _normalize_provider(provider) in CHAT_OPENAI_COMPATIBLE_PROVIDERS


def is_embedding_provider_supported(provider: str | None) -> bool:
    """Return whether the provider is currently supported by the embedding runtime."""
    normalized = _normalize_provider(provider)
    return normalized == "local" or normalized in EMBEDDING_OPENAI_COMPATIBLE_PROVIDERS


def get_ai_function_section(
    function_name: str,
    *,
    yaml_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the normalized ai_config section for a single AI function."""
    from config.yaml_config import load_ai_config

    if yaml_config is None:
        ai_config = load_ai_config()
    else:
        ai_config = dict(yaml_config.get("ai_config") or {})

    raw_section = ai_config.get(function_name) or {}
    if not isinstance(raw_section, Mapping):
        raw_section = {}

    normalized = dict(raw_section)
    defaults = DEFAULT_AI_FUNCTION_CONFIG.get(function_name, {})

    provider = normalized.get("provider")
    if function_name == "chatbot" and not provider:
        provider = normalized.get("llm_provider")
    normalized["provider"] = _normalize_provider(
        provider,
        default=str(defaults.get("provider") or "openai"),
    )

    model = str(normalized.get("model") or defaults.get("model") or "").strip()
    if model:
        normalized["model"] = model
    elif "model" in defaults:
        normalized["model"] = str(defaults["model"])

    return normalized


def resolve_ai_function_runtime(
    function_name: str,
    *,
    storage: Any | None = None,
    yaml_config: Mapping[str, Any] | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> AIFunctionRuntime:
    """Resolve effective runtime config for an AI function."""
    section = get_ai_function_section(function_name, yaml_config=yaml_config)
    if provider_override:
        section["provider"] = _normalize_provider(
            provider_override,
            default=str(section.get("provider") or "openai"),
        )
    if model_override:
        section["model"] = str(model_override).strip()
    provider = _normalize_provider(
        section.get("provider"),
        default=str(DEFAULT_AI_FUNCTION_CONFIG.get(function_name, {}).get("provider") or "openai"),
    )
    model = str(
        section.get("model")
        or DEFAULT_AI_FUNCTION_CONFIG.get(function_name, {}).get("model")
        or ""
    ).strip()

    if provider == "local":
        return AIFunctionRuntime(
            function_name=function_name,
            provider=provider,
            model=model,
            raw_config=section,
            api_key=None,
            base_url=None,
            credential_source="local",
        )

    credentials = resolve_provider_credentials(provider, storage=storage)
    return AIFunctionRuntime(
        function_name=function_name,
        provider=provider,
        model=model,
        raw_config=section,
        api_key=credentials.api_key,
        base_url=credentials.base_url,
        credential_source=credentials.source,
    )


def resolve_ocr_runtime(
    *,
    storage: Any | None = None,
    yaml_config: Mapping[str, Any] | None = None,
    engine_override: str | None = None,
    model_override: str | None = None,
) -> OCRRuntime:
    """Resolve OCR runtime including engine/provider/model mapping."""
    engine = str(engine_override or "").strip().lower()
    provider_override = OCR_ENGINE_PROVIDER_MAP.get(engine) if engine else None
    effective_model_override = model_override
    if effective_model_override is None and engine:
        if engine in {"docling", "marker"}:
            effective_model_override = engine
        elif engine in {"mistral", "deepseekocr"}:
            effective_model_override = ""

    runtime = resolve_ai_function_runtime(
        "ocr",
        storage=storage,
        yaml_config=yaml_config,
        provider_override=provider_override,
        model_override=effective_model_override,
    )

    resolved_engine = _resolve_ocr_engine(runtime.provider, runtime.model, engine_override=engine_override)
    resolved_model = _resolve_ocr_model(runtime.provider, runtime.model, resolved_engine)
    return OCRRuntime(
        engine=resolved_engine,
        provider=runtime.provider,
        model=resolved_model,
        api_key=runtime.api_key,
        base_url=runtime.base_url,
        credential_source=runtime.credential_source,
        raw_config=runtime.raw_config,
    )


def apply_runtime_environment(runtime: AIFunctionRuntime) -> None:
    """Project runtime config into process env for legacy settings-based consumers."""
    provider = runtime.provider
    if provider != "local":
        key_env = get_provider_api_key_env_var(provider)
        base_env = get_provider_base_url_env_var(provider)
        if key_env and runtime.api_key:
            os.environ[key_env] = runtime.api_key
        if base_env and runtime.base_url:
            os.environ[base_env] = runtime.base_url

    if runtime.function_name == "embeddings":
        os.environ["RAG_EMBEDDING_PROVIDER"] = provider
        os.environ["RAG_EMBEDDING_MODEL"] = runtime.model

    _reload_settings_if_available()


def apply_ocr_runtime_environment(runtime: OCRRuntime) -> None:
    """Project OCR runtime config into env/settings for doc_to_md engines."""
    if runtime.provider != "local":
        key_env = get_provider_api_key_env_var(runtime.provider)
        base_env = get_provider_base_url_env_var(runtime.provider)
        if key_env and runtime.api_key:
            os.environ[key_env] = runtime.api_key
        if base_env and runtime.base_url:
            os.environ[base_env] = runtime.base_url

    os.environ["DEFAULT_ENGINE"] = runtime.engine
    if runtime.provider == "mistral":
        os.environ["MISTRAL_DEFAULT_MODEL"] = runtime.model
    elif runtime.provider == "siliconflow":
        os.environ["SILICONFLOW_DEFAULT_MODEL"] = runtime.model

    _reload_settings_if_available()


def resolve_provider_credentials(
    provider: str | None,
    *,
    storage: Any | None = None,
    category: str = "llm",
) -> ProviderCredentials:
    """Resolve provider credentials from DB first, then environment fallback."""
    normalized_provider = _normalize_provider(provider)

    if storage is not None:
        db_credentials = _resolve_provider_credentials_from_storage(
            normalized_provider,
            storage=storage,
            category=category,
        )
        if db_credentials is not None:
            return db_credentials

    api_key_env = get_provider_api_key_env_var(normalized_provider)
    api_key = str(os.getenv(api_key_env) or "").strip() or None if api_key_env else None
    base_url = _get_effective_base_url(normalized_provider)
    if api_key:
        return ProviderCredentials(
            provider=normalized_provider,
            api_key=api_key,
            base_url=base_url,
            source="env",
            configured=True,
        )

    return ProviderCredentials(
        provider=normalized_provider,
        api_key=None,
        base_url=base_url,
        source="missing",
        configured=False,
    )


def _resolve_provider_credentials_from_storage(
    provider: str,
    *,
    storage: Any,
    category: str,
) -> ProviderCredentials | None:
    """Resolve provider credentials from the provider token store."""
    try:
        row = storage.get_llm_provider(provider, category=category)
    except Exception:
        logger.exception("Failed to load provider credentials from storage for %s", provider)
        return None

    if not row:
        return None

    encrypted_key = str(row.get("api_key_encrypted") or "").strip()
    if not encrypted_key:
        return None

    try:
        from ai_actuarial.services.token_encryption import TokenEncryption

        api_key = TokenEncryption().decrypt(encrypted_key)
        if api_key == OPTIONAL_API_KEY_SENTINEL:
            api_key = None
    except Exception:
        logger.warning(
            "Could not decrypt stored provider key for %s; falling back to environment",
            provider,
        )
        return None

    base_url = str(row.get("api_base_url") or "").strip() or _get_effective_base_url(provider)
    return ProviderCredentials(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        source="db",
        configured=True,
    )


def _get_effective_base_url(provider: str) -> str | None:
    base_url_env = get_provider_base_url_env_var(provider)
    env_base_url = str(os.getenv(base_url_env) or "").strip() if base_url_env else ""
    return env_base_url or get_provider_default_base_url(provider)


def _resolve_ocr_engine(provider: str, model: str, *, engine_override: str | None = None) -> str:
    if engine_override:
        normalized_override = str(engine_override).strip().lower()
        if normalized_override == "auto":
            return "docling"
        return normalized_override

    normalized_provider = _normalize_provider(provider, default="local")
    if normalized_provider == "local":
        normalized_model = str(model or "").strip().lower()
        if normalized_model in {"docling", "marker"}:
            return normalized_model
        return OCR_PROVIDER_ENGINE_MAP["local"]
    return OCR_PROVIDER_ENGINE_MAP.get(normalized_provider, OCR_PROVIDER_ENGINE_MAP["local"])


def _resolve_ocr_model(provider: str, model: str, engine: str) -> str:
    normalized_provider = _normalize_provider(provider, default="local")
    normalized_model = str(model or "").strip()
    if normalized_model:
        return normalized_model
    if normalized_provider == "mistral":
        return "mistral-ocr-latest"
    if normalized_provider == "siliconflow":
        return "deepseek-ai/DeepSeek-OCR"
    if engine in {"docling", "marker"}:
        return engine
    return DEFAULT_AI_FUNCTION_CONFIG["ocr"]["model"]


def _reload_settings_if_available() -> None:
    try:
        from config.settings import reload_settings

        reload_settings()
    except Exception:
        return


def _normalize_provider(provider: str | None, *, default: str = "openai") -> str:
    normalized = str(provider or "").strip().lower()
    return normalized or default


def _provider_type_labels(provider_id: str, info: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    if is_chat_provider_supported(provider_id):
        labels.append("chat")
    if is_embedding_provider_supported(provider_id):
        labels.append("embedding")
    if is_catalog_provider_supported(provider_id):
        labels.append("catalog")
    if provider_id in OCR_PROVIDER_ENGINE_MAP or provider_id == "local":
        labels.append("ocr")
    if bool(info.get("is_search_provider")):
        labels.append("search")
    return labels


def normalize_binding_function_name(function_name: str | None) -> str:
    normalized = str(function_name or "").strip().lower()
    if normalized not in FUNCTION_BINDING_TO_SECTION:
        raise ValueError(f"Unsupported function binding: {function_name}")
    return normalized


def binding_to_section_name(function_name: str | None) -> str:
    return FUNCTION_BINDING_TO_SECTION[normalize_binding_function_name(function_name)]


def infer_embedding_dimension(model: str | None) -> int | None:
    """Infer embedding dimension for a known model identifier."""
    normalized = str(model or "").strip()
    if not normalized:
        return None
    if normalized in KNOWN_EMBEDDING_MODEL_DIMENSIONS:
        return int(KNOWN_EMBEDDING_MODEL_DIMENSIONS[normalized])
    lowered = normalized.lower()
    if lowered.startswith("text-embedding-3-large"):
        return 3072
    if lowered.startswith("text-embedding-3-small") or "ada-002" in lowered:
        return 1536
    return None


def infer_embedding_provider(
    model: str | None,
    *,
    fallback: str | None = None,
) -> str | None:
    """Infer provider from an embedding model name when legacy rows lack it."""
    normalized = str(model or "").strip()
    if not normalized:
        normalized_fallback = str(fallback or "").strip().lower()
        return normalized_fallback or None
    if normalized in KNOWN_EMBEDDING_MODEL_PROVIDERS:
        return KNOWN_EMBEDDING_MODEL_PROVIDERS[normalized]
    lowered = normalized.lower()
    if lowered.startswith("text-embedding-3") or "ada-002" in lowered:
        return "openai"
    if normalized.startswith("BAAI/") or normalized == "sentence-transformers":
        return "local"
    normalized_fallback = str(fallback or "").strip().lower()
    return normalized_fallback or None


def build_embedding_fingerprint(provider: str | None, model: str | None, dimension: int | None = None) -> str:
    provider_norm = _normalize_provider(provider)
    model_norm = str(model or "").strip()
    effective_dimension = dimension if dimension is not None else infer_embedding_dimension(model_norm)
    return f"{provider_norm}:{model_norm}:{effective_dimension or 'unknown'}"

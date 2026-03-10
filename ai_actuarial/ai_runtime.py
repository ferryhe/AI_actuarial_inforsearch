"""Unified AI runtime configuration and provider resolution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger(__name__)

AI_SUPPORTED_PROVIDERS = {
    "openai",
    "mistral",
    "siliconflow",
    "anthropic",
    "google",
    "deepseek",
    "zhipuai",
    "moonshot",
    "qwen",
    "cohere",
    "kimi",
    "minimax",
    "local",
}

KNOWN_LLM_PROVIDERS = {
    "openai": {
        "display_name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_hint": "sk-...",
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
    "mistral": ("MISTRAL_API_KEY", "MISTRAL_BASE_URL"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"),
    "google": ("GOOGLE_API_KEY", "GOOGLE_BASE_URL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
    "zhipuai": ("ZHIPUAI_API_KEY", "ZHIPUAI_BASE_URL"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL"),
    "qwen": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "siliconflow": ("SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL"),
    "cohere": ("COHERE_API_KEY", "COHERE_BASE_URL"),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL"),
    "minimax": ("MINIMAX_API_KEY", "MINIMAX_BASE_URL"),
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
    "mistral",
    "deepseek",
    "moonshot",
    "kimi",
    "qwen",
    "zhipuai",
    "siliconflow",
    "minimax",
}

EMBEDDING_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "siliconflow",
    "qwen",
    "zhipuai",
    "minimax",
}

DEFAULT_AI_FUNCTION_CONFIG = {
    "catalog": {"provider": "openai", "model": "gpt-4o-mini"},
    "embeddings": {"provider": "openai", "model": "text-embedding-3-large"},
    "chatbot": {"provider": "openai", "model": "gpt-4-turbo"},
    "ocr": {"provider": "local", "model": "docling"},
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

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

DEFAULT_AI_FUNCTION_CONFIG = {
    "catalog": {"provider": "openai", "model": "gpt-4o-mini"},
    "embeddings": {"provider": "openai", "model": "text-embedding-3-large"},
    "chatbot": {"provider": "openai", "model": "gpt-4-turbo"},
    "ocr": {"provider": "local", "model": "docling"},
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
) -> AIFunctionRuntime:
    """Resolve effective runtime config for an AI function."""
    section = get_ai_function_section(function_name, yaml_config=yaml_config)
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
    api_key = str(os.getenv(api_key_env) or "").strip() or None
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


def _normalize_provider(provider: str | None, *, default: str = "openai") -> str:
    normalized = str(provider or "").strip().lower()
    return normalized or default

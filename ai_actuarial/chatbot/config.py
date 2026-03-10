"""Configuration for the AI chatbot module."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Mapping

from ai_actuarial.ai_runtime import (
    AI_SUPPORTED_PROVIDERS,
    get_ai_function_section,
    get_provider_api_key_env_var,
    get_provider_base_url_env_var,
    get_provider_default_base_url,
    is_chat_provider_supported,
    resolve_ai_function_runtime,
)


def _safe_int(value: Any, key: str, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid value for {key}: {value!r}. Expected integer.") from exc


def _safe_float(value: Any, key: str, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid value for {key}: {value!r}. Expected float.") from exc


@dataclass
class ChatbotConfig:
    """Configuration for the chatbot system."""

    # LLM Settings
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 1000
    api_key: str | None = None
    base_url: str | None = None
    _apply_env_defaults: bool = field(default=True, repr=False, compare=False)

    # Retrieval Settings
    top_k: int = 5
    similarity_threshold: float = 0.4
    min_results: int = 1

    # Conversation Settings
    max_messages: int = 20
    max_context_tokens: int = 8000
    summarization_threshold: int = 15

    # Mode Settings
    default_mode: str = "expert"
    available_modes: List[str] = field(default_factory=lambda: [
        "expert", "summary", "tutorial", "comparison"
    ])

    # Retry & Rate Limiting
    max_retries: int = 3
    retry_delay: float = 1.0
    exponential_backoff: bool = True
    rate_limit_rpm: int = 60

    # Quality & Validation
    require_citations: bool = True
    validate_citations: bool = True
    hallucination_check: bool = True

    # Multi-KB Query Settings
    multi_kb_enabled: bool = True
    min_results_per_kb: int = 2
    kb_diversity_weight: float = 0.3

    def __post_init__(self) -> None:
        """Apply lightweight environment defaults for direct instantiation."""
        if not self._apply_env_defaults:
            return

        provider_from_env = str(
            os.getenv("CHATBOT_LLM_PROVIDER")
            or os.getenv("CHATBOT_PROVIDER")
            or ""
        ).strip().lower()
        if provider_from_env:
            self.llm_provider = provider_from_env

        if not self.api_key:
            env_var = get_provider_api_key_env_var(self.llm_provider)
            self.api_key = (
                str(os.getenv(env_var) or "").strip() or None
                if env_var
                else None
            )

        if not self.base_url:
            base_url_env = get_provider_base_url_env_var(self.llm_provider)
            self.base_url = (
                str(os.getenv(base_url_env) or "").strip() or None
                if base_url_env
                else None
            )
            if not self.base_url:
                self.base_url = get_provider_default_base_url(self.llm_provider)

        self.model = os.getenv("CHATBOT_MODEL", self.model)
        self.temperature = float(os.getenv("CHATBOT_TEMPERATURE", str(self.temperature)))
        self.max_tokens = int(os.getenv("CHATBOT_MAX_TOKENS", str(self.max_tokens)))
        self.top_k = int(os.getenv("CHATBOT_TOP_K", str(self.top_k)))
        self.similarity_threshold = float(
            os.getenv("RAG_SIMILARITY_THRESHOLD", str(self.similarity_threshold))
        )

    @classmethod
    def from_env(cls) -> "ChatbotConfig":
        """Create configuration from environment variables."""
        provider = str(
            os.getenv("CHATBOT_LLM_PROVIDER")
            or os.getenv("CHATBOT_PROVIDER")
            or "openai"
        ).strip().lower()
        api_key_env = get_provider_api_key_env_var(provider)
        base_url_env = get_provider_base_url_env_var(provider)

        return cls(
            llm_provider=provider,
            model=os.getenv("CHATBOT_MODEL", "gpt-4"),
            temperature=_safe_float(os.getenv("CHATBOT_TEMPERATURE"), "CHATBOT_TEMPERATURE", 0.7),
            max_tokens=_safe_int(os.getenv("CHATBOT_MAX_TOKENS"), "CHATBOT_MAX_TOKENS", 1000),
            api_key=(
                str(os.getenv(api_key_env) or "").strip() or None
                if api_key_env
                else None
            ),
            base_url=(
                str(os.getenv(base_url_env) or "").strip() or None
                if base_url_env
                else None
            ) or get_provider_default_base_url(provider),
            _apply_env_defaults=False,
            top_k=_safe_int(os.getenv("CHATBOT_TOP_K"), "CHATBOT_TOP_K", 5),
            similarity_threshold=_safe_float(
                os.getenv("RAG_SIMILARITY_THRESHOLD"),
                "RAG_SIMILARITY_THRESHOLD",
                0.4,
            ),
            min_results=_safe_int(os.getenv("CHATBOT_MIN_RESULTS"), "CHATBOT_MIN_RESULTS", 1),
            max_messages=_safe_int(os.getenv("CHATBOT_MAX_MESSAGES"), "CHATBOT_MAX_MESSAGES", 20),
            max_context_tokens=_safe_int(
                os.getenv("CHATBOT_MAX_CONTEXT_TOKENS"),
                "CHATBOT_MAX_CONTEXT_TOKENS",
                8000,
            ),
            summarization_threshold=_safe_int(
                os.getenv("CHATBOT_SUMMARIZATION_THRESHOLD"),
                "CHATBOT_SUMMARIZATION_THRESHOLD",
                15,
            ),
            default_mode=os.getenv("CHATBOT_DEFAULT_MODE", "expert"),
            max_retries=_safe_int(os.getenv("CHATBOT_MAX_RETRIES"), "CHATBOT_MAX_RETRIES", 3),
            retry_delay=_safe_float(os.getenv("CHATBOT_RETRY_DELAY"), "CHATBOT_RETRY_DELAY", 1.0),
            exponential_backoff=os.getenv("CHATBOT_EXPONENTIAL_BACKOFF", "true").lower() == "true",
            rate_limit_rpm=_safe_int(os.getenv("CHATBOT_RATE_LIMIT_RPM"), "CHATBOT_RATE_LIMIT_RPM", 60),
            require_citations=os.getenv("CHATBOT_REQUIRE_CITATIONS", "true").lower() == "true",
            validate_citations=os.getenv("CHATBOT_VALIDATE_CITATIONS", "true").lower() == "true",
            hallucination_check=os.getenv("CHATBOT_HALLUCINATION_CHECK", "true").lower() == "true",
            multi_kb_enabled=os.getenv("CHATBOT_MULTI_KB_ENABLED", "true").lower() == "true",
            min_results_per_kb=_safe_int(
                os.getenv("CHATBOT_MIN_RESULTS_PER_KB"),
                "CHATBOT_MIN_RESULTS_PER_KB",
                2,
            ),
            kb_diversity_weight=_safe_float(
                os.getenv("CHATBOT_KB_DIVERSITY_WEIGHT"),
                "CHATBOT_KB_DIVERSITY_WEIGHT",
                0.3,
            ),
        )

    @classmethod
    def from_yaml(
        cls,
        yaml_config: Mapping[str, Any],
        *,
        storage: Any | None = None,
    ) -> "ChatbotConfig":
        """Create configuration from sites.yaml ai_config.chatbot."""
        section = get_ai_function_section("chatbot", yaml_config=yaml_config)
        runtime = resolve_ai_function_runtime("chatbot", storage=storage, yaml_config=yaml_config)

        try:
            return cls(
                llm_provider=runtime.provider,
                model=runtime.model or "gpt-4",
                temperature=_safe_float(section.get("temperature"), "chatbot.temperature", 0.7),
                max_tokens=_safe_int(section.get("max_tokens"), "chatbot.max_tokens", 1000),
                api_key=runtime.api_key,
                base_url=runtime.base_url,
                _apply_env_defaults=False,
                top_k=_safe_int(section.get("top_k"), "chatbot.top_k", 5),
                similarity_threshold=_safe_float(
                    section.get("similarity_threshold"),
                    "chatbot.similarity_threshold",
                    0.4,
                ),
                min_results=_safe_int(section.get("min_results"), "chatbot.min_results", 1),
                max_messages=_safe_int(section.get("max_messages"), "chatbot.max_messages", 20),
                max_context_tokens=_safe_int(
                    section.get("max_context_tokens"),
                    "chatbot.max_context_tokens",
                    8000,
                ),
                summarization_threshold=_safe_int(
                    section.get("summarization_threshold"),
                    "chatbot.summarization_threshold",
                    15,
                ),
                default_mode=str(section.get("default_mode") or "expert"),
                max_retries=_safe_int(section.get("max_retries"), "chatbot.max_retries", 3),
                retry_delay=_safe_float(section.get("retry_delay"), "chatbot.retry_delay", 1.0),
                exponential_backoff=bool(section.get("exponential_backoff", True)),
                rate_limit_rpm=_safe_int(section.get("rate_limit_rpm"), "chatbot.rate_limit_rpm", 60),
                require_citations=bool(section.get("require_citations", True)),
                validate_citations=bool(section.get("validate_citations", True)),
                hallucination_check=bool(section.get("hallucination_check", True)),
                multi_kb_enabled=bool(section.get("multi_kb_enabled", True)),
                min_results_per_kb=_safe_int(
                    section.get("min_results_per_kb"),
                    "chatbot.min_results_per_kb",
                    2,
                ),
                kb_diversity_weight=_safe_float(
                    section.get("kb_diversity_weight"),
                    "chatbot.kb_diversity_weight",
                    0.3,
                ),
            )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"Error loading chatbot configuration from sites.yaml: {exc}"
            ) from exc

    @classmethod
    def from_config(
        cls,
        *,
        storage: Any | None = None,
        default_mode: str | None = None,
    ) -> "ChatbotConfig":
        """Create configuration from sites.yaml with environment fallback."""
        try:
            from config.yaml_config import load_yaml_config
        except (ImportError, ModuleNotFoundError):
            config = cls.from_env()
        else:
            try:
                yaml_config = load_yaml_config()
            except (FileNotFoundError, OSError):
                config = cls.from_env()
            else:
                if "ai_config" in yaml_config and "chatbot" in yaml_config.get("ai_config", {}):
                    config = cls.from_yaml(yaml_config, storage=storage)
                else:
                    config = cls.from_env()

        if default_mode is not None:
            config.default_mode = default_mode
        return config

    def validate(self) -> bool:
        """Validate configuration parameters."""
        errors = []
        provider = str(self.llm_provider or "").strip().lower()

        if provider not in AI_SUPPORTED_PROVIDERS:
            errors.append(f"Unsupported LLM provider: {provider}")
        elif not is_chat_provider_supported(provider):
            errors.append(
                f"Provider '{provider}' is configured but chat runtime currently supports: "
                "openai, mistral, deepseek, moonshot, kimi, qwen, zhipuai, siliconflow, minimax"
            )

        if provider != "local" and not self.api_key:
            env_var = get_provider_api_key_env_var(provider) or "API_KEY"
            errors.append(
                f"API key is required for provider '{provider}' ({env_var} environment variable or provider store)"
            )

        if self.temperature < 0 or self.temperature > 2:
            errors.append(f"Temperature must be between 0 and 2, got {self.temperature}")

        if self.max_tokens < 1:
            errors.append(f"max_tokens must be positive, got {self.max_tokens}")

        if self.top_k < 1:
            errors.append(f"top_k must be positive, got {self.top_k}")

        if self.similarity_threshold < 0 or self.similarity_threshold > 1:
            errors.append(
                f"similarity_threshold must be between 0 and 1, got {self.similarity_threshold}"
            )

        if self.default_mode not in self.available_modes:
            errors.append(f"default_mode '{self.default_mode}' not in available_modes")

        if errors:
            raise ValueError(f"Invalid chatbot configuration: {'; '.join(errors)}")

        return True


default_config = ChatbotConfig()

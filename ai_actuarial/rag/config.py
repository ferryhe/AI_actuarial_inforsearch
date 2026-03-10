"""
Configuration for RAG module.

Provides centralized configuration management for RAG components with
environment variable support and sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from ai_actuarial.ai_runtime import (
    get_ai_function_section,
    get_provider_api_key_env_var,
    get_provider_base_url_env_var,
    get_provider_default_base_url,
    is_embedding_provider_supported,
    resolve_ai_function_runtime,
)


@dataclass
class RAGConfig:
    """Configuration for RAG system."""

    # Chunking configuration
    chunk_strategy: str = "semantic_structure"
    max_chunk_tokens: int = 800
    min_chunk_tokens: int = 100
    preserve_headers: bool = True
    preserve_citations: bool = True
    include_hierarchy: bool = True

    # Embedding configuration
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    embedding_batch_size: int = 64
    embedding_cache_enabled: bool = True

    # Vector store configuration
    similarity_threshold: float = 0.4
    index_type: str = "Flat"

    # API configuration
    api_key: str = ""
    api_base_url: str = ""
    openai_api_key: str = ""
    openai_max_retries: int = 3
    openai_timeout: int = 60

    # Storage paths
    data_dir: str = "data/rag"

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Create configuration from environment variables."""
        provider = str(os.getenv("RAG_EMBEDDING_PROVIDER", "openai")).strip().lower() or "openai"
        api_key_env = get_provider_api_key_env_var(provider)
        base_url_env = get_provider_base_url_env_var(provider)
        api_key = str(os.getenv(api_key_env) or "").strip() if api_key_env else ""
        api_base_url = str(os.getenv(base_url_env) or "").strip() if base_url_env else ""
        if not api_base_url:
            api_base_url = str(get_provider_default_base_url(provider) or "").strip()
        return cls(
            chunk_strategy=os.getenv("RAG_CHUNK_STRATEGY", "semantic_structure"),
            max_chunk_tokens=int(os.getenv("RAG_MAX_CHUNK_TOKENS", "800")),
            min_chunk_tokens=int(os.getenv("RAG_MIN_CHUNK_TOKENS", "100")),
            preserve_headers=os.getenv("RAG_PRESERVE_HEADERS", "true").lower() == "true",
            preserve_citations=os.getenv("RAG_PRESERVE_CITATIONS", "true").lower() == "true",
            include_hierarchy=os.getenv("RAG_INCLUDE_HIERARCHY", "true").lower() == "true",
            embedding_provider=provider,
            embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large"),
            embedding_batch_size=int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "64")),
            embedding_cache_enabled=os.getenv("RAG_EMBEDDING_CACHE_ENABLED", "true").lower() == "true",
            similarity_threshold=float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.4")),
            index_type=os.getenv("RAG_INDEX_TYPE", "Flat"),
            api_key=api_key,
            api_base_url=api_base_url,
            openai_api_key=api_key,
            openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
            openai_timeout=int(os.getenv("OPENAI_TIMEOUT", "60")),
            data_dir=os.getenv("RAG_DATA_DIR", "data/rag"),
        )

    @classmethod
    def from_yaml(
        cls,
        yaml_config: Mapping[str, Any],
        *,
        storage: Any | None = None,
    ) -> "RAGConfig":
        """Create configuration from sites.yaml rag_config and ai_config sections."""
        rag_cfg = yaml_config.get("rag_config", {})
        section = get_ai_function_section("embeddings", yaml_config=yaml_config)
        runtime = resolve_ai_function_runtime(
            "embeddings",
            storage=storage,
            yaml_config=yaml_config,
        )

        def safe_int(value: Any, key: str, default: int) -> int:
            if value is None:
                return default
            try:
                return int(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Invalid value for {key} in sites.yaml: {value!r}. Expected integer."
                ) from exc

        def safe_float(value: Any, key: str, default: float) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Invalid value for {key} in sites.yaml: {value!r}. Expected float."
                ) from exc

        def safe_bool(value: Any, key: str, default: bool) -> bool:
            if value is None:
                return default
            if isinstance(value, str):
                lowered = value.lower()
                if lowered in {"true", "1", "yes"}:
                    return True
                if lowered in {"false", "0", "no"}:
                    return False
                raise ValueError(
                    f"Invalid boolean value for {key} in sites.yaml: {value!r}. "
                    "Expected true/false, yes/no, 1/0, or boolean type."
                )
            return bool(value)

        try:
            api_key = str(runtime.api_key or "").strip()
            api_base_url = str(runtime.base_url or "").strip()
            return cls(
                chunk_strategy=str(rag_cfg.get("chunk_strategy", "semantic_structure")),
                max_chunk_tokens=safe_int(
                    rag_cfg.get("max_chunk_tokens"),
                    "rag_config.max_chunk_tokens",
                    800,
                ),
                min_chunk_tokens=safe_int(
                    rag_cfg.get("min_chunk_tokens"),
                    "rag_config.min_chunk_tokens",
                    100,
                ),
                preserve_headers=safe_bool(
                    rag_cfg.get("preserve_headers"),
                    "rag_config.preserve_headers",
                    True,
                ),
                preserve_citations=safe_bool(
                    rag_cfg.get("preserve_citations"),
                    "rag_config.preserve_citations",
                    True,
                ),
                include_hierarchy=safe_bool(
                    rag_cfg.get("include_hierarchy"),
                    "rag_config.include_hierarchy",
                    True,
                ),
                embedding_provider=runtime.provider,
                embedding_model=runtime.model or "text-embedding-3-large",
                embedding_batch_size=safe_int(
                    section.get("batch_size"),
                    "ai_config.embeddings.batch_size",
                    64,
                ),
                embedding_cache_enabled=safe_bool(
                    section.get("cache_enabled"),
                    "ai_config.embeddings.cache_enabled",
                    True,
                ),
                similarity_threshold=safe_float(
                    section.get("similarity_threshold"),
                    "ai_config.embeddings.similarity_threshold",
                    0.4,
                ),
                index_type=str(rag_cfg.get("index_type", "Flat")),
                api_key=api_key,
                api_base_url=api_base_url,
                openai_api_key=api_key,
                openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
                openai_timeout=int(os.getenv("OPENAI_TIMEOUT", "60")),
                data_dir=os.getenv("RAG_DATA_DIR", "data/rag"),
            )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Error loading RAG configuration from sites.yaml: {exc}") from exc

    @classmethod
    def from_config(
        cls,
        *,
        storage: Any | None = None,
    ) -> "RAGConfig":
        """
        Create configuration from sites.yaml with .env fallback.

        This is the recommended method for loading configuration. It will:
        1. Try to load from sites.yaml rag_config and ai_config sections
        2. Fall back to environment variables if not found

        Raises:
            ValueError: If configuration values are invalid in sites.yaml
        """
        try:
            from config.yaml_config import load_yaml_config
        except (ImportError, ModuleNotFoundError):
            return cls.from_env()

        try:
            yaml_config = load_yaml_config()
        except (FileNotFoundError, OSError):
            return cls.from_env()

        has_rag_config = "rag_config" in yaml_config
        has_ai_embeddings = "ai_config" in yaml_config and "embeddings" in yaml_config.get("ai_config", {})

        if has_rag_config or has_ai_embeddings:
            return cls.from_yaml(yaml_config, storage=storage)

        return cls.from_env()

    def validate(self) -> None:
        """Validate configuration."""
        provider = str(self.embedding_provider or "").strip().lower()
        if not is_embedding_provider_supported(provider):
            raise ValueError(
                "Embedding provider '%s' is not supported. Supported providers: local, "
                "openai, siliconflow, qwen, zhipuai, minimax" % provider
            )

        if provider != "local" and not self.api_key:
            env_var = get_provider_api_key_env_var(provider) or "API_KEY"
            raise ValueError(
                f"{env_var} is required when using {provider} embeddings"
            )

        if self.max_chunk_tokens <= self.min_chunk_tokens:
            raise ValueError("max_chunk_tokens must be greater than min_chunk_tokens")

        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")

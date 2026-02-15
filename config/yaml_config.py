"""
Configuration loader for YAML-based configuration with .env fallback.

This module provides centralized configuration loading from sites.yaml,
with backward compatibility for environment variables.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Configuration cache version for invalidation
_cache_version = 0


def _get_sites_config_path() -> Path:
    """Get the path to sites.yaml configuration file."""
    # Try multiple locations
    locations = [
        Path("config/sites.yaml"),  # Development
        Path("/app/config/sites.yaml"),  # Docker
        Path(__file__).parent / "sites.yaml",  # Relative to this file
    ]
    
    for path in locations:
        if path.exists():
            return path
    
    # Default to first location
    return locations[0]


@lru_cache(maxsize=1)
def _load_yaml_config_cached(cache_version: int) -> Dict[str, Any]:
    """
    Load sites.yaml configuration with caching.
    
    Args:
        cache_version: Version number for cache invalidation
        
    Returns:
        Dict containing the full configuration
    """
    config_path = _get_sites_config_path()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config or {}
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration: {e}")
        return {}


def load_yaml_config() -> Dict[str, Any]:
    """
    Load the full sites.yaml configuration.
    
    Returns:
        Dict containing the full configuration
    """
    global _cache_version
    return _load_yaml_config_cached(_cache_version)


def invalidate_config_cache():
    """Invalidate the configuration cache to force reload on next access."""
    global _cache_version
    _cache_version += 1
    _load_yaml_config_cached.cache_clear()
    logger.info("Configuration cache invalidated")


def load_ai_config() -> Dict[str, Any]:
    """
    Load AI configuration from sites.yaml with .env fallback.
    
    Returns:
        Dict containing ai_config section with catalog, embeddings, chatbot, ocr
    """
    yaml_config = load_yaml_config()
    
    if "ai_config" in yaml_config:
        logger.debug("Using ai_config from sites.yaml")
        return yaml_config["ai_config"]
    else:
        logger.warning(
            "ai_config not found in sites.yaml, falling back to environment variables. "
            "Consider running 'python scripts/migrate_env_to_yaml.py' to migrate configuration."
        )
        return _extract_ai_config_from_env()


def _extract_ai_config_from_env() -> Dict[str, Any]:
    """
    Extract AI configuration from environment variables (fallback).
    
    Returns:
        Dict in ai_config format extracted from environment
    """
    return {
        "catalog": {
            "provider": "openai",
            "model": os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini"),
            "temperature": float(os.getenv("CATALOG_TEMPERATURE", "0.7")),
            "timeout_seconds": int(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
        },
        "embeddings": {
            "provider": os.getenv("RAG_EMBEDDING_PROVIDER", "openai"),
            "model": os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large"),
            "batch_size": int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "64")),
            "similarity_threshold": float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.4")),
        },
        "chatbot": {
            "provider": "openai",
            "model": os.getenv("CHATBOT_MODEL", "gpt-4-turbo"),
            "temperature": float(os.getenv("CHATBOT_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("CHATBOT_MAX_TOKENS", "1000")),
            "streaming_enabled": os.getenv("CHATBOT_STREAMING_ENABLED", "true").lower() == "true",
            "max_context_messages": int(os.getenv("CHATBOT_MAX_CONTEXT_MESSAGES", "10")),
            "default_mode": os.getenv("CHATBOT_DEFAULT_MODE", "expert"),
            "enable_citation": os.getenv("CHATBOT_ENABLE_CITATION", "true").lower() == "true",
            "min_citation_score": float(os.getenv("CHATBOT_MIN_CITATION_SCORE", "0.4")),
            "max_citations_per_response": int(os.getenv("CHATBOT_MAX_CITATIONS_PER_RESPONSE", "5")),
            "enable_query_validation": os.getenv("CHATBOT_ENABLE_QUERY_VALIDATION", "true").lower() == "true",
            "enable_response_validation": os.getenv("CHATBOT_ENABLE_RESPONSE_VALIDATION", "true").lower() == "true",
            "max_query_length": int(os.getenv("CHATBOT_MAX_QUERY_LENGTH", "1000")),
        },
        "ocr": {
            "provider": os.getenv("DEFAULT_ENGINE", "local"),
            "model": "docling",  # Default for local provider
            "mistral": {
                "max_pdf_tokens": int(os.getenv("MISTRAL_MAX_PDF_TOKENS", "9000")),
                "max_pages_per_chunk": int(os.getenv("MISTRAL_MAX_PAGES_PER_CHUNK", "10")),
                "timeout_seconds": int(os.getenv("MISTRAL_TIMEOUT_SECONDS", "60")),
                "retry_attempts": int(os.getenv("MISTRAL_RETRY_ATTEMPTS", "3")),
                "extract_header": os.getenv("MISTRAL_EXTRACT_HEADER", "true").lower() == "true",
                "extract_footer": os.getenv("MISTRAL_EXTRACT_FOOTER", "true").lower() == "true",
            },
            "siliconflow": {
                "max_input_tokens": int(os.getenv("SILICONFLOW_MAX_INPUT_TOKENS", "3500")),
                "chunk_overlap_tokens": int(os.getenv("SILICONFLOW_CHUNK_OVERLAP_TOKENS", "200")),
                "timeout_seconds": int(os.getenv("SILICONFLOW_TIMEOUT_SECONDS", "60")),
                "retry_attempts": int(os.getenv("SILICONFLOW_RETRY_ATTEMPTS", "3")),
            },
        },
    }


def load_rag_config() -> Dict[str, Any]:
    """
    Load RAG configuration from sites.yaml with .env fallback.
    
    Returns:
        Dict containing rag_config section
    """
    yaml_config = load_yaml_config()
    
    if "rag_config" in yaml_config:
        logger.debug("Using rag_config from sites.yaml")
        return yaml_config["rag_config"]
    else:
        logger.warning(
            "rag_config not found in sites.yaml, falling back to environment variables. "
            "Consider running 'python scripts/migrate_env_to_yaml.py' to migrate configuration."
        )
        return _extract_rag_config_from_env()


def _extract_rag_config_from_env() -> Dict[str, Any]:
    """
    Extract RAG configuration from environment variables (fallback).
    
    Returns:
        Dict in rag_config format extracted from environment
    """
    return {
        "chunk_strategy": os.getenv("RAG_CHUNK_STRATEGY", "semantic_structure"),
        "max_chunk_tokens": int(os.getenv("RAG_MAX_CHUNK_TOKENS", "800")),
        "min_chunk_tokens": int(os.getenv("RAG_MIN_CHUNK_TOKENS", "100")),
        "preserve_headers": True,  # Not in .env, default
        "preserve_citations": True,  # Not in .env, default
        "include_hierarchy": True,  # Not in .env, default
        "index_type": os.getenv("RAG_INDEX_TYPE", "Flat"),
    }


def load_features() -> Dict[str, Any]:
    """
    Load feature flags from sites.yaml with .env fallback.
    
    Returns:
        Dict containing feature flags
    """
    yaml_config = load_yaml_config()
    
    if "features" in yaml_config:
        logger.debug("Using features from sites.yaml")
        return yaml_config["features"]
    else:
        logger.warning(
            "features not found in sites.yaml, falling back to environment variables. "
            "Consider running 'python scripts/migrate_env_to_yaml.py' to migrate configuration."
        )
        return _extract_features_from_env()


def _extract_features_from_env() -> Dict[str, Any]:
    """
    Extract feature flags from environment variables (fallback).
    
    Returns:
        Dict with feature flags extracted from environment
    """
    return {
        "enable_file_deletion": os.getenv("ENABLE_FILE_DELETION", "false").lower() == "true",
        "require_auth": os.getenv("REQUIRE_AUTH", "false").lower() == "true",
        "enable_csrf": os.getenv("ENABLE_CSRF", "false").lower() == "true",
        "enable_security_headers": os.getenv("ENABLE_SECURITY_HEADERS", "true").lower() == "true",
        "expose_error_details": os.getenv("EXPOSE_ERROR_DETAILS", "false").lower() == "true",
        "enable_global_logs_api": os.getenv("ENABLE_GLOBAL_LOGS_API", "false").lower() == "true",
        "enable_rate_limiting": os.getenv("ENABLE_RATE_LIMITING", "false").lower() == "true",
        "rate_limit_defaults": os.getenv("RATE_LIMIT_DEFAULTS", "200 per hour, 50 per minute"),
        "rate_limit_storage_uri": os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
        "content_security_policy": os.getenv("CONTENT_SECURITY_POLICY", ""),
    }


def load_server_config() -> Dict[str, Any]:
    """
    Load server configuration from sites.yaml with .env fallback.
    
    Returns:
        Dict containing server configuration
    """
    yaml_config = load_yaml_config()
    
    if "server" in yaml_config:
        logger.debug("Using server config from sites.yaml")
        return yaml_config["server"]
    else:
        logger.warning(
            "server config not found in sites.yaml, falling back to environment variables."
        )
        return _extract_server_config_from_env()


def _extract_server_config_from_env() -> Dict[str, Any]:
    """
    Extract server configuration from environment variables (fallback).
    
    Returns:
        Dict with server config extracted from environment
    """
    return {
        "host": os.getenv("FLASK_HOST", "0.0.0.0"),
        "port": int(os.getenv("FLASK_PORT", "5000")),
        "max_content_length": int(os.getenv("MAX_CONTENT_LENGTH", "52428800")),
        "flask_env": os.getenv("FLASK_ENV", "production"),
        "flask_debug": os.getenv("FLASK_DEBUG", "false").lower() == "true",
    }


def load_database_config() -> Dict[str, Any]:
    """
    Load database configuration from sites.yaml with .env fallback.
    
    Returns:
        Dict containing database configuration
    """
    yaml_config = load_yaml_config()
    
    if "database" in yaml_config:
        logger.debug("Using database config from sites.yaml")
        return yaml_config["database"]
    else:
        logger.warning(
            "database config not found in sites.yaml, falling back to environment variables."
        )
        return _extract_database_config_from_env()


def _extract_database_config_from_env() -> Dict[str, Any]:
    """
    Extract database configuration from environment variables (fallback).
    
    Returns:
        Dict with database config extracted from environment
    """
    db_type = os.getenv("DB_TYPE", "sqlite")
    
    config = {
        "type": db_type,
    }
    
    if db_type == "sqlite":
        config["path"] = os.getenv("DB_PATH", "data/index.db")
    elif db_type == "postgresql":
        config["host"] = os.getenv("DB_HOST", "localhost")
        config["port"] = int(os.getenv("DB_PORT", "5432"))
        config["database"] = os.getenv("DB_NAME", "ai_actuarial")
        config["username"] = os.getenv("DB_USER", "postgres")
        # Password should still come from .env
    
    return config

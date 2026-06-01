"""Shared defaults and provider limits for RAG configuration."""

from __future__ import annotations

DEFAULT_RAG_EMBEDDING_BATCH_SIZE = 64
DEFAULT_RAG_SIMILARITY_THRESHOLD = 0.4

# Runtime safety caps applied after user configuration is loaded.
# Keyed by supported provider ID and model so provider-wide throttling does not
# accidentally slow newer models with different API limits.
EMBEDDING_BATCH_SIZE_LIMITS: dict[tuple[str, str], int] = {
    ("qwen", "text-embedding-v3"): 10,
}

# Provider/model score scales are not identical across embedding APIs. Qwen's
# DashScope text-embedding-v3 returns much lower FAISS score values in this
# codebase's L2-derived scoring path, so the OpenAI-oriented 0.4 threshold can
# filter every otherwise-useful result.
SIMILARITY_THRESHOLD_LIMITS: dict[tuple[str, str], float] = {
    ("qwen", "text-embedding-v3"): 0.03,
}


def _normalize_provider_model(provider: str, model: str) -> tuple[str, str]:
    return str(provider or "").strip().lower(), str(model or "").strip()


def get_embedding_batch_size_limit(provider: str, model: str) -> int | None:
    """Return the max embedding batch size for a provider/model pair, if known."""
    return EMBEDDING_BATCH_SIZE_LIMITS.get(_normalize_provider_model(provider, model))


def get_similarity_threshold_limit(provider: str, model: str) -> float | None:
    """Return the max similarity threshold for a provider/model pair, if known."""
    return SIMILARITY_THRESHOLD_LIMITS.get(_normalize_provider_model(provider, model))

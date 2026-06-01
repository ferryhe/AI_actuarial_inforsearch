"""Shared defaults and provider limits for RAG configuration."""

from __future__ import annotations

DEFAULT_RAG_EMBEDDING_BATCH_SIZE = 64

# Runtime safety caps applied after user configuration is loaded.
# Keyed by supported provider ID and model so provider-wide throttling does not
# accidentally slow newer models with different API limits.
EMBEDDING_BATCH_SIZE_LIMITS: dict[tuple[str, str], int] = {
    ("qwen", "text-embedding-v3"): 10,
}


def get_embedding_batch_size_limit(provider: str, model: str) -> int | None:
    """Return the max embedding batch size for a provider/model pair, if known."""
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip()
    return EMBEDDING_BATCH_SIZE_LIMITS.get((normalized_provider, normalized_model))

"""Shared embedding-model defaults for RAG configuration."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RAG_EMBEDDING_BATCH_SIZE = 64
DEFAULT_RAG_SIMILARITY_THRESHOLD = 0.4


@dataclass(frozen=True)
class EmbeddingModelDefaults:
    """Operational defaults tied to an embedding provider/model pair."""

    batch_size: int = DEFAULT_RAG_EMBEDDING_BATCH_SIZE
    similarity_threshold: float = DEFAULT_RAG_SIMILARITY_THRESHOLD


# Embedding runtime knobs are model properties. Keep provider/model-specific
# values here so changing the embeddings binding updates both indexing and chat
# retrieval consistently. UI/config migration code can persist these defaults
# when an embedding model is selected; code remains the source of truth.
EMBEDDING_MODEL_DEFAULTS: dict[tuple[str, str], EmbeddingModelDefaults] = {
    ("qwen", "text-embedding-v3"): EmbeddingModelDefaults(
        batch_size=10,
        similarity_threshold=0.02,
    ),
}


def _normalize_provider_model(provider: str, model: str) -> tuple[str, str]:
    return str(provider or "").strip().lower(), str(model or "").strip()


def get_embedding_model_defaults(provider: str, model: str) -> EmbeddingModelDefaults:
    """Return model-aware embedding defaults for provider/model."""
    return EMBEDDING_MODEL_DEFAULTS.get(
        _normalize_provider_model(provider, model),
        EmbeddingModelDefaults(),
    )


def get_embedding_batch_size_default(provider: str, model: str) -> int:
    """Return the default embedding request batch size for provider/model."""
    return get_embedding_model_defaults(provider, model).batch_size


def get_similarity_threshold_default(provider: str, model: str) -> float:
    """Return the default similarity threshold for a provider/model pair."""
    return get_embedding_model_defaults(provider, model).similarity_threshold

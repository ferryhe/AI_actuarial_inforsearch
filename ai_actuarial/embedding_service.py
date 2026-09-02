from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit

from ai_actuarial.ai_runtime import infer_embedding_dimension
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.storage import Storage

CHUNK_REMOVED_OPTIONS = frozenset(
    {
        "kb_id",
        "knowledge_base_id",
        "bind_to_kb",
        "binding_mode",
        "full_reindex",
        "full_rebuild",
        "force_reindex",
    }
)
LEGACY_CHUNK_OPTIONS = CHUNK_REMOVED_OPTIONS.union({"overwrite_same_profile"})
_SENSITIVE_ENDPOINT_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "password",
        "secret",
        "sig",
        "signature",
        "token",
    }
)
EMBEDDING_FORBIDDEN_OPTIONS = frozenset(
    {
        "api_key",
        "openai_api_key",
        "credential",
        "credential_id",
        "endpoint",
        "api_base_url",
        "base_url",
        "text",
        "texts",
        "content",
        "provider",
        "model",
        "dimension",
        "config_fingerprint",
    }
)
OVERWRITE_DEPRECATION_WARNING = (
    "overwrite_same_profile is deprecated and ignored; ready chunk sets are immutable. "
    "Change Markdown or create a new profile/version to generate a new chunk set."
)
KB_BINDING_GUIDANCE = "Run KB Binding separately after Chunk & Embedding completes."


class UnsupportedOptionsError(ValueError):
    def __init__(self, options: Iterable[str], guidance: str) -> None:
        self.options = sorted({str(option) for option in options})
        self.guidance = guidance
        super().__init__(f"unsupported_option: {', '.join(self.options)}. {self.guidance}")


class EmbeddingSelectionError(ValueError):
    pass


def validate_chunk_generation_payload(payload: Mapping[str, Any]) -> list[str]:
    removed = CHUNK_REMOVED_OPTIONS.intersection(payload)
    if removed:
        raise UnsupportedOptionsError(removed, KB_BINDING_GUIDANCE)
    return [OVERWRITE_DEPRECATION_WARNING] if "overwrite_same_profile" in payload else []


def sanitize_legacy_chunk_generation_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value for key, value in payload.items() if str(key) not in LEGACY_CHUNK_OPTIONS
    }


def validate_embedding_generation_payload(payload: Mapping[str, Any]) -> None:
    forbidden = EMBEDDING_FORBIDDEN_OPTIONS.intersection(payload)
    if forbidden:
        raise UnsupportedOptionsError(
            forbidden,
            "Use the server-owned incremental backlog or select stable chunk sets.",
        )


def _canonical_endpoint_identity(config: RAGConfig) -> str:
    if str(config.embedding_provider or "").strip().lower() == "local":
        return "local"
    raw = str(config.api_base_url or "").strip()
    if not raw:
        return "default"
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        raise ValueError("configured embedding endpoint is invalid")
    default_port = (scheme == "https" and parsed.port == 443) or (
        scheme == "http" and parsed.port == 80
    )
    port = "" if parsed.port is None or default_port else f":{parsed.port}"
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    semantic_query = sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if str(key).strip().lower() not in _SENSITIVE_ENDPOINT_QUERY_KEYS
    )
    query = urlencode(semantic_query, doseq=True)
    endpoint = f"{scheme}://{host}{port}{path.rstrip('/')}"
    return f"{endpoint}?{query}" if query else endpoint


@dataclass(frozen=True)
class EmbeddingIdentity:
    embedding_identity_key: str
    provider: str
    model: str
    dimension: int
    config_fingerprint: str
    config: RAGConfig = field(repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "embedding_identity_key": self.embedding_identity_key,
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "config_fingerprint": self.config_fingerprint,
        }


def compute_embedding_identity(
    config: RAGConfig,
    *,
    dimension: int | None = None,
) -> EmbeddingIdentity:
    provider = str(config.embedding_provider or "").strip().lower()
    model = str(config.embedding_model or "").strip()
    resolved_dimension = int(
        dimension if dimension is not None else (infer_embedding_dimension(model) or 0)
    )
    if not provider or not model or resolved_dimension <= 0:
        raise ValueError("embedding provider, model, and dimension must be configured")
    endpoint_identity = _canonical_endpoint_identity(config)
    config_fingerprint = hashlib.sha256(endpoint_identity.encode("utf-8")).hexdigest()
    contract = json.dumps(
        {
            "provider": provider,
            "model": model,
            "dimension": resolved_dimension,
            "config_fingerprint": config_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    key = "emb_" + hashlib.sha256(contract.encode("utf-8")).hexdigest()
    return EmbeddingIdentity(
        embedding_identity_key=key,
        provider=provider,
        model=model,
        dimension=resolved_dimension,
        config_fingerprint=config_fingerprint,
        config=config,
    )


def resolve_server_embedding_identity(
    storage: Storage,
    requested_key: str | None = None,
) -> EmbeddingIdentity:
    identity = compute_embedding_identity(RAGConfig.from_config(storage=storage))
    requested = str(requested_key or "").strip()
    if requested and requested != identity.embedding_identity_key:
        raise EmbeddingSelectionError(
            "embedding_identity_key is not allowed by the current server configuration"
        )
    return identity


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def resolve_embedding_selection(
    storage: Storage,
    *,
    chunk_set_ids: Iterable[str] = (),
    file_urls: Iterable[str] = (),
    profile_id: str | None = None,
    incremental: bool = False,
    identity: EmbeddingIdentity | None = None,
) -> dict[str, Any]:
    requested_chunk_sets = _dedupe(chunk_set_ids)
    requested_files = _dedupe(file_urls)
    requested_profile = str(profile_id or "").strip()
    selector_count = int(bool(requested_chunk_sets)) + int(bool(requested_files))
    if selector_count > 1 or (selector_count == 0 and not incremental):
        raise EmbeddingSelectionError(
            "provide one selection mode: chunk_set_ids, file_urls, or incremental"
        )
    if selector_count and incremental:
        raise EmbeddingSelectionError(
            "provide one selection mode: chunk_set_ids, file_urls, or incremental"
        )
    if incremental and requested_profile:
        raise EmbeddingSelectionError(
            "profile_id cannot be combined with incremental embedding selection"
        )
    if incremental and identity is None:
        raise EmbeddingSelectionError("embedding identity is required for incremental selection")
    selected_rows: list[tuple[Any, ...]] = []
    if incremental:
        selected_rows = storage._conn.execute("""
            SELECT chunk_set_id, file_url, profile_id, markdown_hash,
                   profile_config_hash, chunk_count
            FROM file_chunk_sets
            WHERE status = 'ready'
            ORDER BY created_at, chunk_set_id
            """).fetchall()
    elif requested_chunk_sets:
        selected_rows = storage._conn.execute(
            f"""
            SELECT chunk_set_id, file_url, profile_id, markdown_hash,
                   profile_config_hash, chunk_count
            FROM file_chunk_sets
            WHERE status = 'ready'
              AND chunk_set_id IN ({','.join('?' for _ in requested_chunk_sets)})
            """,
            tuple(requested_chunk_sets),
        ).fetchall()
        by_id = {str(row[0]): row for row in selected_rows}
        if any(chunk_set_id not in by_id for chunk_set_id in requested_chunk_sets):
            raise EmbeddingSelectionError("one or more chunk_set_ids are not ready")
        selected_rows = [by_id[chunk_set_id] for chunk_set_id in requested_chunk_sets]
    else:
        if not requested_profile:
            raise EmbeddingSelectionError("profile_id is required with file_urls")
        for file_url in requested_files:
            rows = storage._conn.execute(
                """
                SELECT chunk_set_id, file_url, profile_id, markdown_hash,
                       profile_config_hash, chunk_count
                FROM file_chunk_sets
                WHERE file_url = ? AND profile_id = ? AND status = 'ready'
                ORDER BY created_at, chunk_set_id
                """,
                (file_url, requested_profile),
            ).fetchall()
            if not rows:
                raise EmbeddingSelectionError(f"no ready chunk set for file_url={file_url}")
            if len(rows) != 1:
                raise EmbeddingSelectionError(
                    f"ambiguous ready chunk sets for file_url={file_url}; use chunk_set_ids"
                )
            selected_rows.append(rows[0])

    resolved_ids = [str(row[0]) for row in selected_rows]
    chunks = storage.list_chunks_for_embedding(resolved_ids)
    actual_counts: dict[str, int] = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        content = chunk.get("content")
        if not chunk_id or not isinstance(content, str) or not content:
            raise EmbeddingSelectionError("selected chunk set contains an invalid chunk")
        chunk_set_id = str(chunk["chunk_set_id"])
        actual_counts[chunk_set_id] = actual_counts.get(chunk_set_id, 0) + 1
    for row in selected_rows:
        chunk_set_id = str(row[0])
        if int(row[5] or 0) <= 0 or actual_counts.get(chunk_set_id, 0) != int(row[5] or 0):
            raise EmbeddingSelectionError(f"chunk set is not stably ready: {chunk_set_id}")
    if incremental:
        coverage = storage.read_valid_chunk_embeddings(
            [str(chunk["chunk_id"]) for chunk in chunks],
            identity=identity.as_dict(),
        )
        pending_chunk_ids = set(coverage["missing_chunk_ids"]).union(coverage["invalid_chunk_ids"])
        eligible_ids = {
            str(chunk["chunk_set_id"])
            for chunk in chunks
            if str(chunk["chunk_id"]) in pending_chunk_ids
        }
        selected_rows = [row for row in selected_rows if str(row[0]) in eligible_ids]
        resolved_ids = [str(row[0]) for row in selected_rows]
        chunks = [chunk for chunk in chunks if str(chunk["chunk_set_id"]) in eligible_ids]
    return {
        "requested_file_urls": requested_files,
        "requested_chunk_set_ids": requested_chunk_sets,
        "profile_id": requested_profile or None,
        "chunk_sets": [
            {
                "chunk_set_id": str(row[0]),
                "file_url": str(row[1]),
                "profile_id": str(row[2]),
                "markdown_hash": str(row[3]),
                "profile_config_hash": str(row[4]),
                "chunk_count": int(row[5] or 0),
            }
            for row in selected_rows
        ],
        "chunk_set_ids": resolved_ids,
        "chunks": chunks,
    }


class EmbeddingGeneratorProtocol(Protocol):
    def generate_embeddings(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class EnsureEmbeddingsResult:
    identity: EmbeddingIdentity
    expected_count: int
    ready_count: int
    generated: int
    reused: int
    invalid_regenerated: int
    failed: int
    persisted_record_count: int
    errors: list[dict[str, Any]]
    started_at: str
    completed_at: str
    stopped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.identity.as_dict(),
            "expected_count": self.expected_count,
            "ready_count": self.ready_count,
            "generated": self.generated,
            "reused": self.reused,
            "invalid_regenerated": self.invalid_regenerated,
            "failed": self.failed,
            "persisted_record_count": self.persisted_record_count,
            "errors": list(self.errors),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stopped": self.stopped,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(chunk: Mapping[str, Any], identity: EmbeddingIdentity, code: str) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.get("chunk_id") or ""),
        "provider": identity.provider,
        "model": identity.model,
        "dimension": identity.dimension,
        "code": code,
    }


def _valid_provider_vector(vector: Any, dimension: int) -> bool:
    return bool(
        isinstance(vector, list)
        and vector
        and len(vector) == dimension
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in vector
        )
    )


def ensure_chunk_embeddings(
    *,
    storage: Storage,
    chunks: Iterable[Mapping[str, Any]],
    identity: EmbeddingIdentity,
    generator: EmbeddingGeneratorProtocol | None = None,
    batch_size: int | None = None,
    stop_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> EnsureEmbeddingsResult:
    started_at = _now()
    chunk_rows = list(chunks)
    chunk_ids = [str(chunk.get("chunk_id") or "") for chunk in chunk_rows]
    if len(chunk_ids) != len(set(chunk_ids)) or any(not chunk_id for chunk_id in chunk_ids):
        raise ValueError("chunks must have unique non-empty chunk_id values")
    existing = storage.read_valid_chunk_embeddings(
        chunk_ids,
        identity=identity.as_dict(),
    )
    invalid_ids = set(existing["invalid_chunk_ids"])
    pending_ids = invalid_ids.union(existing["missing_chunk_ids"])
    pending = [chunk for chunk in chunk_rows if str(chunk["chunk_id"]) in pending_ids]
    generated = 0
    invalid_regenerated = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    stopped = False

    def report_progress() -> None:
        if progress_callback is None:
            return
        processed = len(existing["valid"]) + generated + invalid_regenerated + failed
        progress_callback(
            processed,
            len(chunk_rows),
            (
                f"Embedding progress: {processed}/{len(chunk_rows)} processed "
                f"(generated={generated}, reused={len(existing['valid'])}, "
                f"invalid_regenerated={invalid_regenerated}, failed={failed})"
            ),
        )

    report_progress()
    effective_batch_size = max(
        1,
        int(batch_size or identity.config.embedding_batch_size or 1),
    )
    if pending and generator is None:
        from ai_actuarial.rag.embeddings import EmbeddingGenerator

        generator = EmbeddingGenerator(
            replace(identity.config, embedding_cache_enabled=False),
            storage=storage,
        )

    for offset in range(0, len(pending), effective_batch_size):
        if stop_check is not None and stop_check():
            stopped = True
            break
        batch = pending[offset : offset + effective_batch_size]
        texts = [str(chunk["content"]) for chunk in batch]
        try:
            vectors = generator.generate_embeddings(texts) if generator is not None else []
        except Exception:  # provider exceptions must never enter task history or logs verbatim
            failed += len(batch)
            errors.extend(_safe_error(chunk, identity, "provider_error") for chunk in batch)
        else:
            if not isinstance(vectors, list) or len(vectors) != len(batch):
                failed += len(batch)
                errors.extend(
                    _safe_error(chunk, identity, "provider_count_mismatch") for chunk in batch
                )
            else:
                valid_rows: list[dict[str, Any]] = []
                valid_chunks: list[Mapping[str, Any]] = []
                for chunk, vector in zip(batch, vectors):
                    if not _valid_provider_vector(vector, identity.dimension):
                        failed += 1
                        errors.append(_safe_error(chunk, identity, "invalid_embedding_vector"))
                        continue
                    valid_rows.append({"chunk_id": chunk["chunk_id"], "vector": vector})
                    valid_chunks.append(chunk)
                storage.batch_upsert_chunk_embeddings(
                    valid_rows,
                    identity=identity.as_dict(),
                )
                for chunk in valid_chunks:
                    if str(chunk["chunk_id"]) in invalid_ids:
                        invalid_regenerated += 1
                    else:
                        generated += 1
        report_progress()
        if stop_check is not None and stop_check():
            stopped = True
            break

    coverage = storage.read_valid_chunk_embeddings(
        chunk_ids,
        identity=identity.as_dict(),
    )
    return EnsureEmbeddingsResult(
        identity=identity,
        expected_count=len(chunk_rows),
        ready_count=len(coverage["valid"]),
        generated=generated,
        reused=len(existing["valid"]),
        invalid_regenerated=invalid_regenerated,
        failed=failed,
        persisted_record_count=len(coverage["valid"]),
        errors=errors,
        started_at=started_at,
        completed_at=_now(),
        stopped=stopped,
    )


def embedding_coverage_for_selection(
    *,
    storage: Storage,
    selection: Mapping[str, Any],
    identity: EmbeddingIdentity,
) -> dict[str, Any]:
    return {
        "contract_version": 1,
        **identity.as_dict(),
        "chunk_set_ids": list(selection.get("chunk_set_ids") or []),
        **storage.embedding_coverage(
            chunk_set_ids=selection.get("chunk_set_ids") or [],
            identity=identity.as_dict(),
        ),
    }

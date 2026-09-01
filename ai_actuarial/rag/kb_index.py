from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import numpy as np

from ai_actuarial.embedding_service import (
    EmbeddingIdentity,
    ensure_chunk_embeddings,
    resolve_server_embedding_identity,
)
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.vector_store import VectorStore
from ai_actuarial.storage import Storage

FAILURE_CATEGORIES = frozenset(
    {
        "invalid_selector",
        "missing_chunk",
        "missing_or_failed_embedding",
        "stale_snapshot",
        "build_failure",
        "publish_failure",
    }
)


class KBIndexContractError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        if code not in FAILURE_CATEGORIES:
            raise ValueError(f"unknown KB index failure category: {code}")
        self.code = code
        super().__init__(f"{code}: {message}")


class KBIndexStopped(KBIndexContractError):
    def __init__(self) -> None:
        super().__init__("build_failure", "index task was stopped")


def _dedupe(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _binding_snapshot(
    storage: Storage,
    kb_id: str,
    *,
    file_urls: Iterable[str] | None = None,
) -> dict[str, Any]:
    kid = str(kb_id or "").strip()
    if not kid:
        raise KBIndexContractError("invalid_selector", "kb_id is required")
    conn = storage._conn
    required_tables = {
        "rag_knowledge_bases",
        "rag_kb_files",
        "files",
        "kb_chunk_bindings",
        "file_chunk_sets",
        "global_chunks",
    }
    existing_tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()
    }
    if not required_tables <= existing_tables:
        raise KBIndexContractError(
            "invalid_selector", "knowledge-base composition tables are unavailable"
        )
    started_read = not conn.in_transaction
    if started_read:
        conn.execute("BEGIN")
    try:
        kb_row = conn.execute(
            """
            SELECT chunk_profile_id
            FROM rag_knowledge_bases
            WHERE kb_id = ?
            """,
            (kid,),
        ).fetchone()
        if not kb_row:
            raise KBIndexContractError("invalid_selector", f"knowledge base '{kid}' was not found")
        selected_profile_id = str(kb_row[0] or "").strip()
        member_rows = conn.execute(
            """
            SELECT kf.file_url
            FROM rag_kb_files kf
            LEFT JOIN files f ON f.url = kf.file_url
            WHERE kf.kb_id = ? AND f.url IS NOT NULL
            ORDER BY kf.file_url
            """,
            (kid,),
        ).fetchall()
        members = [str(row[0]) for row in member_rows]
        if not members:
            raise KBIndexContractError("invalid_selector", "knowledge base has no file membership")
        requested = sorted(_dedupe(file_urls or ()))
        if file_urls is not None and requested != members:
            raise KBIndexContractError(
                "invalid_selector",
                "file_urls must exactly match the complete knowledge-base membership",
            )

        binding_rows = conn.execute(
            """
            SELECT b.file_url, b.chunk_set_id, b.binding_mode,
                   fcs.file_url, fcs.profile_id, fcs.profile_config_hash,
                   fcs.status, fcs.chunk_count
            FROM kb_chunk_bindings b
            LEFT JOIN file_chunk_sets fcs ON fcs.chunk_set_id = b.chunk_set_id
            WHERE b.kb_id = ?
            ORDER BY b.file_url, b.chunk_set_id
            """,
            (kid,),
        ).fetchall()
        bindings_by_file: dict[str, list[Any]] = {}
        for row in binding_rows:
            bindings_by_file.setdefault(str(row[0] or ""), []).append(row)
        if set(bindings_by_file) - set(members):
            raise KBIndexContractError(
                "invalid_selector", "binding references a file outside KB membership"
            )

        files: list[dict[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        for file_url in members:
            rows = bindings_by_file.get(file_url) or []
            if len(rows) != 1:
                raise KBIndexContractError(
                    "invalid_selector",
                    f"file binding is missing or ambiguous: {file_url}",
                )
            row = rows[0]
            chunk_set_id = str(row[1] or "")
            bound_file_url = str(row[3] or "")
            profile_id = str(row[4] or "")
            profile_config_hash = str(row[5] or "")
            status = str(row[6] or "")
            declared_count = int(row[7] or 0)
            if not chunk_set_id or bound_file_url != file_url:
                raise KBIndexContractError(
                    "invalid_selector", f"cross-file or missing binding: {file_url}"
                )
            if selected_profile_id and profile_id != selected_profile_id:
                raise KBIndexContractError(
                    "invalid_selector", f"binding uses the wrong chunk profile: {file_url}"
                )
            if status != "ready" or declared_count <= 0:
                raise KBIndexContractError(
                    "missing_chunk", f"bound chunk set is not ready: {chunk_set_id}"
                )
            chunk_rows = conn.execute(
                """
                SELECT chunk_id, chunk_index, content, content_hash,
                       token_count, section_hierarchy
                FROM global_chunks
                WHERE chunk_set_id = ?
                ORDER BY chunk_index, chunk_id
                """,
                (chunk_set_id,),
            ).fetchall()
            if len(chunk_rows) != declared_count:
                raise KBIndexContractError(
                    "missing_chunk", f"chunk count mismatch for set: {chunk_set_id}"
                )
            file_chunk_ids: list[str] = []
            file_content_hashes: list[str] = []
            for chunk_row in chunk_rows:
                chunk_id = str(chunk_row[0] or "")
                content = chunk_row[2]
                if not chunk_id or not isinstance(content, str) or not content:
                    raise KBIndexContractError(
                        "missing_chunk",
                        f"bound chunk set contains an invalid chunk: {chunk_set_id}",
                    )
                if chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(chunk_id)
                content_hash = (
                    str(chunk_row[3] or "") or hashlib.sha256(content.encode("utf-8")).hexdigest()
                )
                file_chunk_ids.append(chunk_id)
                file_content_hashes.append(content_hash)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "chunk_set_id": chunk_set_id,
                        "chunk_index": int(chunk_row[1]),
                        "content": content,
                        "content_hash": content_hash,
                        "token_count": int(chunk_row[4] or 0),
                        "section_hierarchy": chunk_row[5] or "",
                        "file_url": file_url,
                        "profile_id": profile_id,
                        "profile_config_hash": profile_config_hash,
                    }
                )
            if len(file_chunk_ids) != declared_count:
                raise KBIndexContractError(
                    "missing_chunk", f"chunk IDs are not unique for set: {chunk_set_id}"
                )
            files.append(
                {
                    "file_url": file_url,
                    "chunk_set_id": chunk_set_id,
                    "profile_id": profile_id,
                    "profile_config_hash": profile_config_hash,
                    "chunk_ids": file_chunk_ids,
                    "content_hashes": file_content_hashes,
                }
            )
        fingerprint_payload = {
            "contract_version": 1,
            "kb_id": kid,
            "chunk_profile_id": selected_profile_id,
            "files": [
                [
                    item["file_url"],
                    item["chunk_set_id"],
                    item["profile_config_hash"],
                    list(zip(item["chunk_ids"], item["content_hashes"])),
                ]
                for item in files
            ],
        }
        fingerprint = (
            "bind_"
            + hashlib.sha256(
                json.dumps(
                    fingerprint_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        )
        return {
            "contract_version": 1,
            "kb_id": kid,
            "binding_snapshot_fingerprint": fingerprint,
            "bound_file_count": len(files),
            "bound_chunk_set_count": len(files),
            "bound_chunk_count": len(chunks),
            "files": files,
            "chunks": chunks,
        }
    finally:
        if started_read and conn.in_transaction:
            conn.rollback()


def resolve_kb_bound_chunks(
    storage: Storage,
    kb_id: str,
    *,
    file_urls: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Resolve a complete KB binding snapshot without writing or using Markdown."""
    return _binding_snapshot(storage, kb_id, file_urls=file_urls)


def binding_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: snapshot[key]
        for key in (
            "contract_version",
            "kb_id",
            "binding_snapshot_fingerprint",
            "bound_file_count",
            "bound_chunk_set_count",
            "bound_chunk_count",
        )
    }


def _artifact_digest(index_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (index_path, index_path.with_suffix(".meta.pkl")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _progress(
    callback: Callable[[str, int, int], None] | None,
    message: str,
    current: int,
    total: int,
) -> None:
    if callback is not None:
        callback(message, current, total)


def build_kb_index(
    *,
    storage: Storage,
    kb_id: str,
    expected_binding_snapshot_fingerprint: str,
    embedding_identity_key: str,
    force_rebuild: bool = False,
    identity: EmbeddingIdentity | None = None,
    generator: Any | None = None,
    config: RAGConfig | None = None,
    stop_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Build and atomically publish one complete immutable KB index version."""
    del force_rebuild  # every supported run rebuilds the complete candidate
    kid = str(kb_id or "").strip()
    expected = str(expected_binding_snapshot_fingerprint or "").strip()
    requested_identity_key = str(embedding_identity_key or "").strip()
    if not kid or not expected or not requested_identity_key:
        raise KBIndexContractError(
            "invalid_selector", "kb_id, snapshot fingerprint, and embedding identity are required"
        )
    kb_row = storage._conn.execute(
        """
        SELECT embedding_identity_key, embedding_provider, embedding_model,
               embedding_dimension, index_type
        FROM rag_knowledge_bases
        WHERE kb_id = ?
        """,
        (kid,),
    ).fetchone()
    if not kb_row:
        raise KBIndexContractError("invalid_selector", "knowledge base was not found")
    kb_identity_key = str(kb_row[0] or "").strip()
    if not kb_identity_key or kb_identity_key != requested_identity_key:
        raise KBIndexContractError(
            "invalid_selector", "embedding identity does not exactly match the knowledge base"
        )
    if identity is None:
        try:
            identity = resolve_server_embedding_identity(storage, requested_identity_key)
        except ValueError as exc:
            raise KBIndexContractError("invalid_selector", str(exc)) from exc
    if identity.embedding_identity_key != requested_identity_key:
        raise KBIndexContractError("invalid_selector", "embedding identity key mismatch")
    if (
        str(kb_row[1] or "").strip().lower() != identity.provider
        or str(kb_row[2] or "").strip() != identity.model
        or int(kb_row[3] or 0) != identity.dimension
    ):
        raise KBIndexContractError(
            "invalid_selector", "embedding identity metadata does not match the knowledge base"
        )

    _progress(progress_callback, "Resolve", 0, 4)
    snapshot = resolve_kb_bound_chunks(storage, kid)
    if snapshot["binding_snapshot_fingerprint"] != expected:
        raise KBIndexContractError("stale_snapshot", "binding snapshot changed before build")
    chunks = list(snapshot["chunks"])
    if stop_check is not None and stop_check():
        raise KBIndexStopped

    _progress(progress_callback, "Ensure missing embeddings", 1, 4)
    try:
        ensured = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=generator,
            batch_size=identity.config.embedding_batch_size,
            stop_check=stop_check,
        )
    except KBIndexStopped:
        raise
    except Exception as exc:
        raise KBIndexContractError(
            "missing_or_failed_embedding",
            "embedding initialization or generation failed",
        ) from exc
    if ensured.stopped:
        raise KBIndexStopped
    if ensured.failed or ensured.ready_count != len(chunks):
        raise KBIndexContractError(
            "missing_or_failed_embedding", "one or more bound chunks have no valid embedding"
        )
    embedding_rows = storage.read_valid_chunk_embeddings(
        [str(chunk["chunk_id"]) for chunk in chunks],
        identity=identity.as_dict(),
    )
    valid = embedding_rows["valid"]
    if len(valid) != len(chunks):
        raise KBIndexContractError(
            "missing_or_failed_embedding", "persisted embedding coverage is incomplete"
        )

    _progress(progress_callback, "Build/validate", 2, 4)
    index_version_id = f"idxv_{uuid.uuid4().hex}"
    effective_config = replace(
        config or identity.config,
        index_type=str(kb_row[4] or "Flat"),
    )
    index_path = (
        Path(effective_config.data_dir) / kid / "versions" / index_version_id / "index.faiss"
    )
    try:
        vectors = np.asarray([valid[str(chunk["chunk_id"])] for chunk in chunks], dtype="float32")
        if vectors.shape != (len(chunks), identity.dimension) or not np.isfinite(vectors).all():
            raise ValueError("candidate vector matrix is invalid")
        metadata = [
            {
                "vector_ordinal": ordinal,
                "chunk_id": str(chunk["chunk_id"]),
                "chunk_set_id": str(chunk["chunk_set_id"]),
                "kb_id": kid,
                "file_url": str(chunk["file_url"]),
                "chunk_index": int(chunk["chunk_index"]),
                "content": str(chunk["content"]),
                "token_count": int(chunk["token_count"]),
                "section_hierarchy": chunk["section_hierarchy"],
            }
            for ordinal, chunk in enumerate(chunks)
        ]
        vector_store = VectorStore(
            dimension=identity.dimension,
            config=effective_config,
            index_path=str(index_path),
        )
        vector_store.add_vectors(vectors, metadata)
        if int(vector_store.index.ntotal) != len(chunks) or len(vector_store.metadata) != len(
            chunks
        ):
            raise ValueError("candidate FAISS or metadata count mismatch")
        if [row["vector_ordinal"] for row in vector_store.metadata] != list(range(len(chunks))):
            raise ValueError("candidate vector ordinal mapping is invalid")
        vector_store.save_index()
        digest = _artifact_digest(index_path)
    except KBIndexContractError:
        raise
    except Exception as exc:
        raise KBIndexContractError("build_failure", "candidate index build failed") from exc

    if stop_check is not None and stop_check():
        raise KBIndexStopped
    _progress(progress_callback, "Commit", 3, 4)
    try:
        with storage.transaction(immediate=True):
            current_identity_row = storage._conn.execute(
                "SELECT embedding_identity_key FROM rag_knowledge_bases WHERE kb_id = ?",
                (kid,),
            ).fetchone()
            if (
                not current_identity_row
                or str(current_identity_row[0] or "") != requested_identity_key
            ):
                raise KBIndexContractError(
                    "stale_snapshot", "embedding identity changed before commit"
                )
            current_snapshot = resolve_kb_bound_chunks(storage, kid)
            if current_snapshot["binding_snapshot_fingerprint"] != expected:
                raise KBIndexContractError(
                    "stale_snapshot", "binding snapshot changed before commit"
                )
            now = storage._utcnow_iso()
            storage._conn.execute(
                """
                INSERT INTO kb_index_versions (
                    index_version_id, kb_id, embedding_provider, embedding_model,
                    embedding_dimension, embedding_identity_key,
                    binding_snapshot_fingerprint, index_type, status,
                    artifact_path, artifact_digest, chunk_count, built_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?, ?, ?)
                """,
                (
                    index_version_id,
                    kid,
                    identity.provider,
                    identity.model,
                    identity.dimension,
                    identity.embedding_identity_key,
                    expected,
                    effective_config.index_type,
                    str(index_path),
                    digest,
                    len(chunks),
                    now,
                    now,
                ),
            )
            storage._conn.executemany(
                """
                INSERT INTO kb_index_items (index_version_id, chunk_id, vector_ordinal)
                VALUES (?, ?, ?)
                """,
                [
                    (index_version_id, str(chunk["chunk_id"]), ordinal)
                    for ordinal, chunk in enumerate(chunks)
                ],
            )
            storage._conn.execute(
                """
                INSERT INTO kb_ready_index_state (
                    kb_id, index_version_id, embedding_provider, embedding_model,
                    embedding_dimension, embedding_identity_key,
                    binding_snapshot_fingerprint, artifact_path, artifact_digest,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kb_id) DO UPDATE SET
                    index_version_id = excluded.index_version_id,
                    embedding_provider = excluded.embedding_provider,
                    embedding_model = excluded.embedding_model,
                    embedding_dimension = excluded.embedding_dimension,
                    embedding_identity_key = excluded.embedding_identity_key,
                    binding_snapshot_fingerprint = excluded.binding_snapshot_fingerprint,
                    artifact_path = excluded.artifact_path,
                    artifact_digest = excluded.artifact_digest,
                    updated_at = excluded.updated_at
                """,
                (
                    kid,
                    index_version_id,
                    identity.provider,
                    identity.model,
                    identity.dimension,
                    identity.embedding_identity_key,
                    expected,
                    str(index_path),
                    digest,
                    now,
                ),
            )
            storage._conn.execute(
                """
                UPDATE rag_knowledge_bases
                SET embedding_provider = ?, embedding_model = ?,
                    embedding_dimension = ?, chunk_count = ?,
                    index_path = ?, metadata_path = ?, index_dirty_at = NULL,
                    updated_at = ?
                WHERE kb_id = ?
                """,
                (
                    identity.provider,
                    identity.model,
                    identity.dimension,
                    len(chunks),
                    str(index_path),
                    str(index_path.with_suffix(".meta.pkl")),
                    now,
                    kid,
                ),
            )
            storage._conn.execute(
                """
                UPDATE rag_kb_files
                SET indexed_at = ?, chunk_count = (
                    SELECT COUNT(*)
                    FROM kb_index_items items
                    JOIN global_chunks chunks ON chunks.chunk_id = items.chunk_id
                    JOIN file_chunk_sets sets ON sets.chunk_set_id = chunks.chunk_set_id
                    WHERE items.index_version_id = ?
                      AND sets.file_url = rag_kb_files.file_url
                )
                WHERE kb_id = ?
                """,
                (now, index_version_id, kid),
            )
            storage.mark_agentic_ready_source_event_for_kb(kb_id=kid, reason="index_committed")
    except KBIndexContractError:
        raise
    except Exception as exc:
        raise KBIndexContractError("build_failure", "index commit failed") from exc
    _progress(progress_callback, "Commit", 4, 4)
    return {
        "contract_version": 1,
        "index_version_id": index_version_id,
        "binding_snapshot_fingerprint": expected,
        "embedding_identity_key": identity.embedding_identity_key,
        "chunk_count": len(chunks),
        "vector_dimension": identity.dimension,
        "artifact_digest": digest,
    }

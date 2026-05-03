from __future__ import annotations

import os
from typing import Any, Mapping

from ai_actuarial.ai_runtime import build_embedding_fingerprint, infer_embedding_dimension, resolve_ai_function_runtime
from ai_actuarial.config import settings
from ai_actuarial.shared_runtime import parse_int_clamped
from ai_actuarial.storage import Storage


class RagAdminError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code



def _manager_and_storage(db_path: str):
    try:
        from ai_actuarial.rag.knowledge_base import KnowledgeBase, KnowledgeBaseManager
    except ImportError as exc:  # noqa: BLE001
        raise RagAdminError("RAG functionality not available", status_code=503) from exc

    storage = Storage(db_path)
    manager = KnowledgeBaseManager(storage)
    return KnowledgeBase, manager, storage



def _norm(value: Any) -> str:
    return str(value or "").strip()



def _list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RagAdminError(f"{field} must be a list")
    out: list[str] = []
    for item in value:
        normalized = _norm(item)
        if normalized and normalized not in out:
            out.append(normalized)
    return out



def _kb_id(value: Any) -> str:
    kb_id = _norm(value)
    if not kb_id:
        raise RagAdminError("kb_id is required")
    if not (2 <= len(kb_id) <= 64):
        raise RagAdminError("kb_id must be between 2 and 64 characters long")
    return kb_id



def _serialize_kb(kb: Any) -> dict[str, Any]:
    return {
        "kb_id": kb.kb_id,
        "name": kb.name,
        "description": kb.description,
        "kb_mode": kb.kb_mode,
        "embedding_provider": getattr(kb, "embedding_provider", "openai"),
        "embedding_model": kb.embedding_model,
        "embedding_dimension": getattr(kb, "embedding_dimension", None),
        "chunk_size": kb.chunk_size,
        "chunk_overlap": kb.chunk_overlap,
        "index_type": kb.index_type,
        "file_count": kb.file_count,
        "chunk_count": kb.chunk_count,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
    }



def _embedding_metadata_matches(current: Mapping[str, Any], *, provider: Any, model: Any, dimension: Any) -> bool:
    current_provider = str(current.get("provider") or "").strip().lower()
    current_model = str(current.get("model") or "").strip()
    current_dimension = current.get("dimension")

    index_provider = str(provider or "").strip().lower()
    index_model = str(model or "").strip()
    index_dimension = dimension

    if index_provider and current_provider and index_provider != current_provider:
        return False
    if index_model and current_model and index_model != current_model:
        return False
    if index_dimension not in (None, "") and current_dimension not in (None, ""):
        try:
            if int(index_dimension) != int(current_dimension):
                return False
        except (TypeError, ValueError):
            return False
    return True



def _current_embeddings_payload(*, storage: Storage) -> dict[str, Any]:
    runtime = resolve_ai_function_runtime("embeddings", storage=storage)
    return {
        "provider": runtime.provider,
        "model": runtime.model,
        "dimension": infer_embedding_dimension(runtime.model),
        "credential_source": runtime.credential_source,
        "credential_id": runtime.credential_id,
        "stable_credential_id": runtime.stable_credential_id,
        "credential_label": runtime.credential_label,
        "configured": runtime.configured,
        "credential_error": runtime.credential_error,
        "embedding_fingerprint": build_embedding_fingerprint(runtime.provider, runtime.model),
    }



def _build_kb_embedding_status(
    *,
    storage: Storage,
    kb_payload: dict[str, Any],
    current_embeddings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    kb_id = str(kb_payload.get("kb_id") or "").strip()
    effective_current_embeddings = dict(current_embeddings) if current_embeddings is not None else _current_embeddings_payload(storage=storage)
    composition = storage.get_kb_composition_status(kb_id) if kb_id else {}
    latest_index = composition.get("latest_index") or {}
    has_index = bool(composition.get("has_index"))
    kb_provider = kb_payload.get("embedding_provider") or "openai"
    kb_model = kb_payload.get("embedding_model")
    kb_dimension = kb_payload.get("embedding_dimension")
    effective_index_provider = latest_index.get("embedding_provider") or kb_provider
    effective_index_model = latest_index.get("embedding_model") or kb_model
    effective_index_dimension = latest_index.get("embedding_dimension")
    if effective_index_dimension in (None, ""):
        effective_index_dimension = kb_dimension
    embedding_compatible = _embedding_metadata_matches(
        effective_current_embeddings,
        provider=effective_index_provider,
        model=effective_index_model,
        dimension=effective_index_dimension,
    )
    needs_reindex = bool(composition.get("needs_reindex")) or (has_index and not embedding_compatible)
    index_status = str(latest_index.get("status") or "").strip().lower()
    if not has_index or index_status in {"pending", "queued", "running", "building", "indexing"}:
        availability = "building"
        usable = False
    elif needs_reindex:
        availability = "needs_reindex"
        usable = False
    else:
        availability = "ready"
        usable = True
    return {
        **kb_payload,
        "index_embedding_provider": effective_index_provider,
        "index_embedding_model": effective_index_model,
        "index_embedding_dimension": effective_index_dimension,
        "index_status": latest_index.get("status") or ("ready" if has_index and effective_index_model else None),
        "index_built_at": latest_index.get("built_at"),
        "needs_reindex": needs_reindex,
        "embedding_compatible": embedding_compatible,
        "availability": availability,
        "usable": usable,
        "current_embeddings": effective_current_embeddings,
    }



def _require_config_write_token(headers: Mapping[str, str]) -> None:
    expected_token = os.getenv("CONFIG_WRITE_AUTH_TOKEN") or settings.CONFIG_WRITE_AUTH_TOKEN
    if not expected_token:
        return
    provided_token = headers.get("X-Auth-Token") or headers.get("x-auth-token")
    if not provided_token or provided_token != expected_token:
        raise RagAdminError("Forbidden", status_code=403)



def list_chunk_profiles(*, db_path: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        return {"profiles": storage.list_chunk_profiles()}
    finally:
        storage.close()



def create_chunk_profile(*, db_path: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    name = _norm(payload.get("name"))
    if not name:
        raise RagAdminError("name is required")
    chunk_size = parse_int_clamped(payload.get("chunk_size"), default=800, min_value=1, max_value=10000)
    chunk_overlap = parse_int_clamped(payload.get("chunk_overlap"), default=100, min_value=0, max_value=10000)
    splitter = _norm(payload.get("splitter") or "semantic")
    tokenizer = _norm(payload.get("tokenizer") or "cl100k_base")
    version = _norm(payload.get("version") or "v1")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    storage = Storage(db_path)
    try:
        profile = storage.create_chunk_profile(
            name=name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            splitter=splitter,
            tokenizer=tokenizer,
            version=version,
            metadata=metadata,
            upsert=True,
        )
        return {"profile": profile}
    finally:
        storage.close()



def delete_chunk_profile(*, db_path: str, profile_id: str, headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    normalized_profile_id = _norm(profile_id)
    if not normalized_profile_id:
        raise RagAdminError("profile_id is required")
    storage = Storage(db_path)
    try:
        deleted = storage.delete_chunk_profile(normalized_profile_id)
        if not deleted:
            raise RagAdminError("chunk profile not found", status_code=404)
        return deleted
    finally:
        storage.close()


def update_chunk_profile(*, db_path: str, profile_id: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    normalized_profile_id = _norm(profile_id)
    if not normalized_profile_id:
        raise RagAdminError("profile_id is required")
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    storage = Storage(db_path)
    try:
        profile = storage.get_chunk_profile(normalized_profile_id)
        if not profile:
            raise RagAdminError("chunk profile not found", status_code=404)
        updates = []
        values = []
        if "name" in payload:
            updates.append("name = ?")
            values.append(_norm(payload["name"]))
        if "chunk_size" in payload:
            updates.append("chunk_size = ?")
            values.append(int(payload["chunk_size"]))
        if "chunk_overlap" in payload:
            updates.append("chunk_overlap = ?")
            values.append(int(payload["chunk_overlap"]))
        if updates:
            import time as time_module
            updates.append("updated_at = ?")
            values.append(time_module.time())
            values.append(normalized_profile_id)
            storage._conn.execute(
                f"UPDATE chunk_profiles SET {', '.join(updates)} WHERE profile_id = ?",
                values,
            )
            storage._conn.commit()
        updated = storage.get_chunk_profile(normalized_profile_id)
        return {"profile": updated}
    finally:
        storage.close()


def get_kb_bindings(*, db_path: str, kb_id: str) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    storage = Storage(db_path)
    try:
        bindings = storage.list_kb_chunk_bindings(kid)
        return {"kb_id": kid, "bindings": bindings, "count": len(bindings)}
    finally:
        storage.close()


def get_categories_mapping(*, db_path: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        cursor = storage._conn.execute(
            """
            SELECT DISTINCT category FROM source_metadata WHERE category IS NOT NULL AND category != ''
            """
        )
        mapped_categories = [row[0] for row in cursor.fetchall() if row[0]]
        return {"categories": mapped_categories, "count": len(mapped_categories)}
    finally:
        storage.close()


def list_knowledge_bases(*, db_path: str, query: Mapping[str, Any]) -> dict[str, Any]:
    KnowledgeBase, _manager, storage = _manager_and_storage(db_path)
    try:
        kb_mode = _norm(query.get("kb_mode"))
        search = _norm(query.get("search")).lower()
        cursor = storage._conn.execute(
            """
            SELECT kb_id, name, description, kb_mode, embedding_provider, embedding_model, embedding_dimension, chunk_size, chunk_overlap,
                   index_type, created_at, updated_at, file_count, chunk_count
            FROM rag_knowledge_bases
            ORDER BY created_at DESC
            """
        )
        current_embeddings = _current_embeddings_payload(storage=storage)
        kbs = []
        for row in cursor.fetchall():
            kb = KnowledgeBase(
                kb_id=row[0], name=row[1], description=row[2],
                kb_mode=row[3] or "category",
                embedding_provider=row[4] or "openai",
                embedding_model=row[5], embedding_dimension=row[6],
                chunk_size=row[7], chunk_overlap=row[8],
                index_type=row[9], created_at=row[10], updated_at=row[11],
                file_count=row[12], chunk_count=row[13],
            )
            if kb_mode and kb.kb_mode != kb_mode:
                continue
            if search and not (
                search in (kb.name or "").lower()
                or search in (kb.description or "").lower()
                or search in (kb.kb_id or "").lower()
            ):
                continue
            kbs.append(
                _build_kb_embedding_status(
                    storage=storage,
                    kb_payload=_serialize_kb(kb),
                    current_embeddings=current_embeddings,
                )
            )
        return {"knowledge_bases": kbs, "current_embeddings": current_embeddings}
    finally:
        storage.close()



def create_knowledge_base(*, db_path: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    kb_id = _kb_id(payload.get("kb_id"))
    name = _norm(payload.get("name"))
    if not name:
        raise RagAdminError("name is required")
    kb_mode = _norm(payload.get("kb_mode") or "manual").lower()
    if kb_mode not in {"manual", "category"}:
        raise RagAdminError("kb_mode must be 'category' or 'manual'")
    chunk_size = parse_int_clamped(payload.get("chunk_size"), default=800, min_value=1, max_value=10000)
    chunk_overlap = parse_int_clamped(payload.get("chunk_overlap"), default=100, min_value=0, max_value=10000)
    categories = _list(payload.get("categories"), "categories")
    file_urls = _list(payload.get("file_urls"), "file_urls")
    if kb_mode == "category" and not categories:
        raise RagAdminError("categories required for category mode")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if manager.get_kb(kb_id):
            raise RagAdminError(f"Knowledge base '{kb_id}' already exists", status_code=409)
        runtime_embedding = manager.get_current_embedding_metadata()
        manager.create_kb(
            kb_id=kb_id,
            name=name,
            description=_norm(payload.get("description")),
            kb_mode=kb_mode,
            embedding_model=runtime_embedding["model"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if kb_mode == "category":
            manager.link_kb_to_categories(kb_id, categories)
        elif file_urls:
            manager.add_files_to_kb(kb_id, file_urls)
        kb = manager.get_kb(kb_id)
        return {"knowledge_base": _serialize_kb(kb)}
    finally:
        storage.close()



def get_knowledge_base(*, db_path: str, kb_id: str) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        payload = _build_kb_embedding_status(storage=storage, kb_payload=_serialize_kb(kb))
        payload["stats"] = manager.get_kb_stats(kid)
        payload["categories"] = manager.get_kb_categories(kid)
        return {"knowledge_base": payload}
    finally:
        storage.close()



def update_knowledge_base(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    name = _norm(payload["name"]) if "name" in payload else None
    description = _norm(payload["description"]) if "description" in payload else None
    if name is None and description is None:
        raise RagAdminError("No valid update fields provided (name, description)")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        manager.update_kb(kid, name=name, description=description)
        return {"knowledge_base": _serialize_kb(manager.get_kb(kid))}
    finally:
        storage.close()



def delete_knowledge_base(*, db_path: str, kb_id: str, headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        manager.delete_kb(kid)
        return {"success": True, "message": f"Knowledge base '{kid}' deleted successfully"}
    finally:
        storage.close()



def get_knowledge_base_stats(*, db_path: str, kb_id: str) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        return manager.get_kb_stats(kid)
    finally:
        storage.close()



def list_knowledge_base_files(*, db_path: str, kb_id: str, query: Mapping[str, Any]) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    status_filter = _norm(query.get("status")).lower()
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        bindings = storage.list_kb_chunk_bindings(kid)
        latest_binding_by_file: dict[str, dict[str, Any]] = {}
        version_count_cache: dict[tuple[str, str], int] = {}
        profile_names: set[str] = set()
        for binding in bindings:
            file_url = str(binding.get("file_url") or "")
            if not file_url or file_url in latest_binding_by_file:
                continue
            latest_binding_by_file[file_url] = binding
            profile_name = str(binding.get("profile_name") or binding.get("profile_id") or "").strip()
            if profile_name:
                profile_names.add(profile_name)

        rows = []
        for item in manager.get_kb_files(kid):
            file_url = item.get("file_url")
            binding = latest_binding_by_file.get(str(file_url or ""), {})
            profile_id = str(binding.get("profile_id") or "").strip()
            cache_key = (str(file_url or ""), profile_id)
            if cache_key not in version_count_cache:
                if profile_id:
                    row = storage._conn.execute(
                        "SELECT COUNT(*) FROM file_chunk_sets WHERE file_url = ? AND profile_id = ?",
                        (cache_key[0], profile_id),
                    ).fetchone()
                else:
                    row = storage._conn.execute(
                        "SELECT COUNT(*) FROM file_chunk_sets WHERE file_url = ?",
                        (cache_key[0],),
                    ).fetchone()
                version_count_cache[cache_key] = int((row[0] if row else 0) or 0)
            indexed = item.get("indexed_at") is not None
            stale = bool(item.get("needs_reindex"))
            status = "indexed" if indexed and not stale else ("stale" if indexed else "pending")
            rows.append(
                {
                    "file_url": file_url,
                    "title": item.get("title") or "",
                    "category": item.get("category") or "",
                    "source_site": item.get("source_site") or "",
                    "added_at": item.get("added_at"),
                    "indexed_at": item.get("indexed_at"),
                    "markdown_updated_at": item.get("markdown_updated_at"),
                    "chunk_count": binding.get("chunk_count") or item.get("chunk_count") or 0,
                    "chunk_set_id": binding.get("chunk_set_id") or "",
                    "chunk_version_count": version_count_cache.get(cache_key, 0),
                    "chunk_set_updated_at": binding.get("chunk_set_updated_at") or binding.get("bound_at"),
                    "bound_at": binding.get("bound_at"),
                    "chunk_profile": binding.get("profile_name") or binding.get("profile_id") or "",
                    "indexed": indexed,
                    "needs_reindex": stale,
                    "status": status,
                }
            )
        if status_filter:
            rows = [row for row in rows if row.get("status") == status_filter]
        profile_summary = "-"
        if len(profile_names) == 1:
            profile_summary = next(iter(profile_names))
        elif len(profile_names) > 1:
            profile_summary = f"Mixed ({len(profile_names)})"
        return {
            "kb_id": kid,
            "total_files": len(rows),
            "files": rows,
            "profile_summary": profile_summary,
        }
    finally:
        storage.close()



def add_knowledge_base_files(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    file_urls = _list(payload.get("file_urls"), "file_urls")
    if not file_urls:
        raise RagAdminError("file_urls must be a non-empty list")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        result = manager.add_files_to_kb(kid, file_urls)
        return {
            "kb_id": kid,
            "added_count": int(result.get("added_count") or 0),
            "skipped_count": int(result.get("skipped_count") or 0),
            "total_files": int(result.get("total_files") or 0),
        }
    finally:
        storage.close()



def remove_knowledge_base_file(*, db_path: str, kb_id: str, file_url: str, headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    normalized_file_url = _norm(file_url)
    if not normalized_file_url:
        raise RagAdminError("file_url is required")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        removed = manager.remove_files_from_kb(kid, [normalized_file_url])
        if removed <= 0:
            raise RagAdminError("File not found in knowledge base", status_code=404)
        return {"kb_id": kid, "removed_count": int(removed), "file_url": normalized_file_url}
    finally:
        storage.close()



def get_unmapped_categories(*, db_path: str) -> dict[str, Any]:
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        rows = manager.get_unmapped_categories()
        return {
            "unmapped_categories": [
                {"name": row.get("category"), "file_count": row.get("file_count") or 0}
                for row in rows
            ],
            "total_count": len(rows),
        }
    finally:
        storage.close()



def list_selectable_files(*, db_path: str, query: Mapping[str, Any]) -> dict[str, Any]:
    q = _norm(query.get("query")).lower()
    category = _norm(query.get("category"))
    kb_id_raw = _norm(query.get("kb_id"))
    kb_id = _kb_id(kb_id_raw) if kb_id_raw else ""
    limit = parse_int_clamped(query.get("limit") or 100, default=100, min_value=1, max_value=500)
    offset = parse_int_clamped(query.get("offset") or 0, default=0, min_value=0, max_value=1_000_000)

    storage = Storage(db_path)
    try:
        conn = storage._conn
        where_parts = [
            "f.deleted_at IS NULL",
            "c.markdown_content IS NOT NULL",
            "c.markdown_content != ''",
        ]
        params: list[Any] = []
        if q:
            where_parts.append("(LOWER(f.title) LIKE ? OR LOWER(f.original_filename) LIKE ? OR LOWER(f.url) LIKE ?)")
            wildcard = f"%{q}%"
            params.extend([wildcard, wildcard, wildcard])
        if category:
            where_parts.append("(c.category = ? OR c.category LIKE ? OR c.category LIKE ? OR c.category LIKE ?)")
            params.extend([category, f"{category};%", f"%; {category}", f"%; {category};%"])
        if kb_id:
            row = conn.execute("SELECT 1 FROM rag_knowledge_bases WHERE kb_id = ?", [kb_id]).fetchone()
            if not row:
                raise RagAdminError(f"Knowledge base '{kb_id}' not found", status_code=404)
            where_parts.append("NOT EXISTS (SELECT 1 FROM rag_kb_files kf WHERE kf.kb_id = ? AND kf.file_url = f.url)")
            params.append(kb_id)
        where_sql = " AND ".join(where_parts)

        total = int(
            conn.execute(
                f"SELECT COUNT(*) FROM files f JOIN catalog_items c ON c.file_url = f.url WHERE {where_sql}",
                params,
            ).fetchone()[0]
            or 0
        )
        rows = conn.execute(
            f"""
            SELECT f.url, f.title, f.original_filename, f.source_site, f.bytes, f.last_seen, c.category, c.markdown_updated_at
            FROM files f
            JOIN catalog_items c ON c.file_url = f.url
            WHERE {where_sql}
            ORDER BY f.last_seen DESC, f.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        files = [
            {
                "url": row[0],
                "title": row[1] or "",
                "original_filename": row[2] or "",
                "source_site": row[3] or "",
                "bytes": row[4] or 0,
                "last_seen": row[5],
                "category": row[6] or "",
                "markdown_updated_at": row[7],
            }
            for row in rows
        ]
        return {"files": files, "total": total, "limit": limit, "offset": offset, "kb_id": kb_id or None}
    finally:
        storage.close()



def get_knowledge_base_categories(*, db_path: str, kb_id: str) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        categories = manager.get_kb_categories(kid)
        return {"kb_id": kid, "categories": categories, "count": len(categories)}
    finally:
        storage.close()



def set_knowledge_base_categories(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    categories = _list(payload.get("categories"), "categories")
    if not categories:
        raise RagAdminError("categories must be a non-empty list")
    action = _norm(payload.get("action") or "add").lower()
    if action not in {"add", "remove", "replace"}:
        raise RagAdminError("action must be one of: add, remove, replace")
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        before_n = int(manager.get_kb_stats(kid).get("total_files", 0))
        manager._ensure_category_mapping_table()
        conn = storage._conn
        timestamp = _KnowledgeBase._get_timestamp()

        if action == "add":
            manager.link_kb_to_categories(kid, categories)
            after_n = int(manager.get_kb_stats(kid).get("total_files", 0))
            return {"kb_id": kid, "action": action, "linked_count": len(categories), "files_added": max(0, after_n - before_n)}

        if action == "remove":
            placeholders = ",".join(["?" for _ in categories])
            deleted = conn.execute(
                f"DELETE FROM rag_kb_category_mappings WHERE kb_id = ? AND category IN ({placeholders})",
                [kid, *categories],
            ).rowcount
            conn.execute(
                "UPDATE rag_knowledge_bases SET updated_at = ? WHERE kb_id = ?",
                (timestamp, kid),
            )
            conn.commit()
            return {"kb_id": kid, "action": action, "removed_count": int(deleted), "categories": manager.get_kb_categories(kid)}

        conn.execute("DELETE FROM rag_kb_category_mappings WHERE kb_id = ?", (kid,))
        conn.commit()
        manager.link_kb_to_categories(kid, categories)
        after_n = int(manager.get_kb_stats(kid).get("total_files", 0))
        return {"kb_id": kid, "action": action, "linked_count": len(categories), "files_added": max(0, after_n - before_n), "categories": manager.get_kb_categories(kid)}
    finally:
        storage.close()



def get_pending_files(*, db_path: str, kb_id: str) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        pending = set(manager.get_files_needing_index(kid))
        rows = []
        for item in manager.get_kb_files(kid):
            if item.get("file_url") not in pending:
                continue
            rows.append(
                {
                    "file_url": item.get("file_url"),
                    "title": item.get("title") or "",
                    "category": item.get("category") or "",
                    "added_at": item.get("added_at"),
                    "indexed_at": item.get("indexed_at"),
                    "markdown_updated_at": item.get("markdown_updated_at"),
                }
            )
        return {"kb_id": kid, "pending_count": len(rows), "pending_files": rows}
    finally:
        storage.close()



def bind_chunk_sets(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    bound_by = _norm(payload.get("bound_by") or "api")
    default_binding_mode = _norm(payload.get("binding_mode") or "follow_latest").lower()
    if isinstance(payload.get("bindings"), list):
        items = payload.get("bindings") or []
    else:
        items = [{
            "file_url": payload.get("file_url"),
            "chunk_set_id": payload.get("chunk_set_id"),
            "binding_mode": payload.get("binding_mode") or "follow_latest",
        }]
    parsed: list[tuple[str, str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_url = _norm(item.get("file_url"))
        chunk_set_id = _norm(item.get("chunk_set_id"))
        binding_mode = _norm(item.get("binding_mode") or default_binding_mode or "pin").lower()
        if file_url and chunk_set_id and binding_mode:
            parsed.append((file_url, chunk_set_id, binding_mode))
    if not parsed:
        raise RagAdminError("bindings must include file_url and chunk_set_id")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        created_n = 0
        out: list[dict[str, Any]] = []
        for file_url, chunk_set_id, binding_mode in parsed:
            try:
                res = storage.bind_chunk_set_to_kb(
                    kb_id=kid,
                    file_url=file_url,
                    chunk_set_id=chunk_set_id,
                    bound_by=bound_by,
                    binding_mode=binding_mode,
                )
            except ValueError as exc:
                message = str(exc)
                status_code = 404 if "not found" in message.lower() else 400
                raise RagAdminError(message, status_code=status_code) from exc
            if res.get("created"):
                created_n += 1
            out.append(res)
        return {
            "kb_id": kid,
            "processed": len(out),
            "created": created_n,
            "existing": len(out) - created_n,
            "bindings": out,
        }
    finally:
        storage.close()



def create_index_task(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str], bridge_state: Any) -> tuple[dict[str, Any], int]:
    _require_config_write_token(headers)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    force_reindex = bool(payload.get("force_reindex", False) or payload.get("reindex_all", False))
    incremental = bool(payload.get("incremental", True))
    requested = _list(payload.get("file_urls"), "file_urls")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        user_requested = bool(requested)
        files_to_index = requested
        if not files_to_index:
            if force_reindex or not incremental:
                files_to_index = [row.get("file_url") for row in manager.get_kb_files(kid)]
                files_to_index = [url for url in files_to_index if url]
            else:
                files_to_index = manager.get_files_needing_index(kid)
        if not files_to_index:
            raise RagAdminError("No files to index")

        skipped_no_markdown = 0
        if not user_requested:
            markdown_urls = set()
            batch_size = 900
            for i in range(0, len(files_to_index), batch_size):
                batch = files_to_index[i:i + batch_size]
                placeholders = ",".join(["?" for _ in batch])
                rows = storage._conn.execute(
                    f"""
                    SELECT DISTINCT file_url FROM catalog_items
                    WHERE file_url IN ({placeholders})
                      AND markdown_content IS NOT NULL
                      AND markdown_content != ''
                    """,
                    batch,
                ).fetchall()
                markdown_urls.update(row[0] for row in rows if row and row[0])
            original_count = len(files_to_index)
            files_to_index = [url for url in files_to_index if url in markdown_urls]
            skipped_no_markdown = max(0, original_count - len(files_to_index))
            if not files_to_index:
                raise RagAdminError("No markdown files to index (all candidates missing markdown)")

        start_background_task = getattr(bridge_state, "start_background_task", None)
        if start_background_task is None:
            raise RagAdminError("Task bridge is unavailable", status_code=503)

        task_id = start_background_task(
            "rag_indexing",
            {
                "type": "rag_indexing",
                "kb_id": kid,
                "file_urls": files_to_index,
                "force_reindex": force_reindex,
                "incremental": incremental,
                "name": f"RAG Indexing: {kb.name}",
            },
            task_name=f"RAG Indexing: {kb.name}",
            extra_fields={"kb_id": kid, "kb_name": kb.name, "rag_file_count": len(files_to_index)},
        )

        return {
            "job_id": task_id,
            "kb_id": kid,
            "file_count": len(files_to_index),
            "skipped_no_markdown": skipped_no_markdown,
            "force_reindex": force_reindex,
            "incremental": incremental,
        }, 202
    finally:
        storage.close()



def cleanup_chunk_sets(*, db_path: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    _require_config_write_token(headers)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    older_than_days = parse_int_clamped(payload.get("older_than_days") or 30, default=30, min_value=1, max_value=3650)
    limit = parse_int_clamped(payload.get("limit") or 5000, default=5000, min_value=1, max_value=20000)
    dry_run = bool(payload.get("dry_run", False))

    storage = Storage(db_path)
    try:
        return storage.cleanup_orphan_chunk_sets(older_than_days=older_than_days, limit=limit, dry_run=dry_run)
    finally:
        storage.close()

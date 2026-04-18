from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

from ai_actuarial.config import settings
from ai_actuarial.rag.exceptions import ChunkingException
from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml, parse_int_clamped
from ai_actuarial.storage import Storage


class FileWriteError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code



def _config_data() -> dict[str, Any]:
    return load_yaml(get_sites_config_path(), default={})



def _download_dir() -> Path:
    config = _config_data()
    raw = str((config.get("paths") or {}).get("download_dir", "data/files"))
    path = Path(raw)
    return path.resolve() if path.is_absolute() else path.resolve()



def _resolve_local_path(local_path: str | None) -> Path | None:
    raw = str(local_path or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    base_dir = _download_dir()
    candidate = (base_dir.parent / p).resolve()
    if candidate.exists():
        return candidate
    fallback = (base_dir / p).resolve()
    return fallback



def _query_files_for_export(storage: Storage) -> list[dict[str, Any]]:
    rows, _total = storage.query_files_with_catalog(limit=100000, offset=0, include_deleted=True)
    return rows



def _is_file_deletion_enabled() -> bool:
    config = _config_data()
    system_cfg = config.get("system") or {}
    if "file_deletion_enabled" in system_cfg:
        return bool(system_cfg.get("file_deletion_enabled"))
    return settings.ENABLE_FILE_DELETION



def _check_file_deletion_token(headers: dict[str, str]) -> None:
    expected_token = settings.FILE_DELETION_AUTH_TOKEN
    if not expected_token:
        return
    provided = headers.get("x-auth-token") or headers.get("X-Auth-Token")
    if provided != expected_token:
        raise FileWriteError("Forbidden", status_code=403)



def update_file_record(*, db_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FileWriteError("Invalid or missing JSON body")
    url = payload.get("url")
    if not url:
        raise FileWriteError("No URL provided")

    title = payload.get("title")
    category = payload.get("category")
    summary = payload.get("summary")
    keywords = payload.get("keywords")

    if title is not None:
        title = str(title).strip() or None
    if isinstance(category, list):
        category = "; ".join([str(c).strip() for c in category if str(c).strip()])
    elif category is not None:
        category = str(category).strip()
    if keywords is not None and not isinstance(keywords, list):
        raise FileWriteError("Keywords must be a list")

    storage = Storage(db_path)
    try:
        if title is None and not any(v is not None for v in (category, summary, keywords)):
            raise FileWriteError("No updates provided")

        if title is not None:
            file_exists = storage._conn.execute("SELECT url FROM files WHERE url = ?", (url,)).fetchone()
            if not file_exists:
                raise FileWriteError("File not found", status_code=404)
            storage._conn.execute("UPDATE files SET title = ? WHERE url = ?", (title, url))
            storage._maybe_commit()

        if any(v is not None for v in (category, summary, keywords)):
            success, reason = storage.update_file_catalog(url=url, category=category, summary=summary, keywords=keywords)
            if not success and reason == "file_not_found":
                raise FileWriteError("File not found", status_code=404)
            if not success and reason != "no_updates":
                raise FileWriteError("Update failed", status_code=500)

        file_data = storage.get_file_with_catalog(url)
        return {"success": True, "file": file_data}
    finally:
        storage.close()



def update_file_markdown_content(*, db_path: str, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FileWriteError("Invalid or missing JSON body")
    markdown_content = payload.get("markdown_content")
    if markdown_content is None:
        raise FileWriteError("No markdown_content provided")
    markdown_source = str(payload.get("markdown_source") or "manual")

    storage = Storage(db_path)
    try:
        success, reason = storage.update_file_markdown(url=url, markdown_content=str(markdown_content), markdown_source=markdown_source)
        if not success and reason == "file_not_found":
            raise FileWriteError("File not found", status_code=404)
        if not success:
            raise FileWriteError("Update failed", status_code=500)
        markdown = storage.get_file_markdown(url)
        return {"success": True, "markdown": markdown}
    finally:
        storage.close()



def get_downloadable_file(*, db_path: str, url: str) -> tuple[Path, str]:
    if not url:
        raise FileWriteError("URL parameter required")
    storage = Storage(db_path)
    try:
        file_record = storage.get_file_by_url(url)
    finally:
        storage.close()
    if not file_record or not file_record.get("local_path"):
        raise FileWriteError("File not found", status_code=404)

    resolved = _resolve_local_path(file_record.get("local_path"))
    if resolved is None or not resolved.exists():
        raise FileWriteError("File not found on disk (path resolution failed)", status_code=404)

    data_root = _download_dir().parent.resolve()
    try:
        is_within = os.path.commonpath([str(data_root), str(resolved)]) == str(data_root)
    except ValueError:
        is_within = False
    if not is_within:
        raise FileWriteError("Forbidden", status_code=403)

    filename = str(file_record.get("original_filename") or resolved.name or "download.bin")
    return resolved, filename



def export_catalog(*, db_path: str, format_type: str) -> tuple[bytes, str, str]:
    storage = Storage(db_path)
    try:
        data = _query_files_for_export(storage)
    finally:
        storage.close()

    for row in data:
        keywords = row.get("keywords")
        row["keywords"] = ", ".join(keywords) if isinstance(keywords, list) else str(keywords or "")

    normalized = (format_type or "csv").strip().lower()
    if normalized == "json":
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json", "catalog_export.json"

    si = io.StringIO()
    fieldnames = list(data[0].keys()) if data else []
    writer = csv.DictWriter(si, fieldnames=fieldnames)
    if fieldnames:
        writer.writeheader()
        writer.writerows(data)
    return si.getvalue().encode("utf-8-sig"), "text/csv", "catalog_export.csv"



def delete_file_record(*, db_path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    if not _is_file_deletion_enabled():
        raise FileWriteError(
            "File deletion is disabled. Enable it via Settings > System or set ENABLE_FILE_DELETION=true in environment.",
            status_code=403,
        )
    _check_file_deletion_token(headers)
    if not isinstance(payload, dict):
        raise FileWriteError("Invalid or missing JSON body")

    url = payload.get("url")
    if not url:
        raise FileWriteError("No URL provided")
    if payload.get("confirm") != "DELETE":
        raise FileWriteError('Explicit confirmation required. Include {"confirm": "DELETE"} in the request body.')

    storage = Storage(db_path)
    details = {"url": url, "database_marked": False, "physical_file_deleted": False, "errors": []}
    try:
        deleted_time = __import__("datetime").datetime.now().isoformat()
        storage.mark_file_deleted(url, deleted_time)
        details["database_marked"] = True
        file_record = storage.get_file_by_url(url)
        if file_record and file_record.get("local_path"):
            candidate = _resolve_local_path(file_record.get("local_path"))
            if candidate is not None:
                base_dir = _download_dir().parent.resolve()
                try:
                    is_within = os.path.commonpath([str(base_dir), str(candidate)]) == str(base_dir)
                except ValueError:
                    is_within = False
                if not is_within:
                    details["errors"].append(f"Security: File outside allowed directory: {candidate}")
                elif candidate.exists():
                    os.remove(candidate)
                    details["physical_file_deleted"] = True
                    storage.clear_local_path(url)
                else:
                    details["errors"].append(f"Physical file not found (already deleted?): {candidate}")
                    storage.clear_local_path(url)
        else:
            details["errors"].append("No local_path found in database for this file")
        return {"success": True, "details": details}
    finally:
        storage.close()



def get_file_chunk_sets(*, db_path: str, file_url: str) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        file_info = storage.get_file_by_url(file_url)
        if not file_info:
            raise FileWriteError("File not found", status_code=404)
        rows = storage.list_file_chunk_sets(file_url)
        return {"file_url": file_url, "chunk_sets": rows, "count": len(rows)}
    finally:
        storage.close()



def generate_file_chunk_sets(*, db_path: str, file_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FileWriteError("Invalid JSON body")
    profile_id = str(payload.get("profile_id") or "").strip()
    overwrite_same_profile = bool(payload.get("overwrite_same_profile", False))
    chunk_size = parse_int_clamped(payload.get("chunk_size") or 800, default=800, min_value=1, max_value=10000)
    chunk_overlap = parse_int_clamped(payload.get("chunk_overlap") or 100, default=100, min_value=0, max_value=10000)
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size - 1)
    splitter = str(payload.get("splitter") or "semantic").strip()
    tokenizer = str(payload.get("tokenizer") or "cl100k_base").strip()
    version = str(payload.get("version") or "v1").strip()
    profile_name = str(payload.get("name") or f"default-{chunk_size}-{chunk_overlap}").strip()

    from ai_actuarial.rag.semantic_chunking import SemanticChunker

    storage = Storage(db_path)
    try:
        file_info = storage.get_file_by_url(file_url)
        if not file_info:
            raise FileWriteError("File not found", status_code=404)
        markdown_data = storage.get_file_markdown(file_url)
        markdown_content = (markdown_data or {}).get("markdown_content") or ""
        if not markdown_content.strip():
            raise FileWriteError("No markdown content available for this file")

        if profile_id:
            profile = storage.get_chunk_profile(profile_id)
            if not profile:
                raise FileWriteError("chunk profile not found", status_code=404)
        else:
            profile = storage.create_chunk_profile(
                name=profile_name,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                splitter=splitter,
                tokenizer=tokenizer,
                version=version,
                metadata={},
                upsert=True,
            )

        markdown_hash = hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=profile["profile_id"],
            markdown_hash=markdown_hash,
            status="ready",
        )
        if not chunk_set.get("created") and not overwrite_same_profile:
            return {
                "file_url": file_url,
                "chunk_set_id": chunk_set["chunk_set_id"],
                "profile": profile,
                "chunk_count": chunk_set.get("chunk_count", 0),
                "reused_existing": True,
                "overwrote_existing": False,
            }

        max_tokens = int(profile.get("chunk_size") or 800)
        min_tokens = max(20, min(100, max_tokens // 4))
        chunker = SemanticChunker(
            max_tokens=max_tokens,
            min_tokens=min_tokens,
            preserve_headers=True,
            preserve_citations=True,
            include_hierarchy=True,
            model="gpt-4",
        )
        chunks = chunker.chunk_document(markdown_content, metadata={"file_url": file_url})
        payload_chunks = [
            {
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "section_hierarchy": chunk.section_hierarchy,
            }
            for chunk in chunks
        ]
        write_res = storage.replace_global_chunks(chunk_set_id=chunk_set["chunk_set_id"], chunks=payload_chunks, overwrite=True)
        sync_res = storage.sync_follow_latest_bindings_for_chunk_set(
            file_url=file_url,
            profile_id=str(profile.get("profile_id") or ""),
            chunk_set_id=chunk_set["chunk_set_id"],
            bound_by="chunk_generation_auto_sync",
        )
        return {
            "file_url": file_url,
            "chunk_set_id": chunk_set["chunk_set_id"],
            "profile": profile,
            "chunk_count": write_res.get("chunk_count", 0),
            "reused_existing": not chunk_set.get("created", False),
            "overwrote_existing": write_res.get("replaced", False),
            "auto_synced_kb_bindings": sync_res.get("synced_bindings", 0),
            "auto_synced_kb_ids": sync_res.get("affected_kb_ids", []),
        }
    except ChunkingException as exc:
        raise FileWriteError(str(exc), status_code=400) from exc
    except ValueError as exc:
        raise FileWriteError(str(exc)) from exc
    finally:
        storage.close()



def get_rag_file_preview(*, db_path: str, file_url: str, chunk_set_id: str | None) -> dict[str, Any]:
    if not file_url:
        raise FileWriteError("file_url parameter is required")
    storage = Storage(db_path)
    try:
        file_info = storage.get_file_by_url(file_url)
        if not file_info:
            raise FileWriteError("File not found", status_code=404)
        markdown_data = storage.get_file_markdown(file_url) or {}
        chunk_sets = storage.list_file_chunk_sets(file_url)
        selected_chunk_set_id = ""
        if chunk_sets:
            available_ids = {str(item.get("chunk_set_id") or "") for item in chunk_sets}
            if chunk_set_id and chunk_set_id in available_ids:
                selected_chunk_set_id = chunk_set_id
            else:
                selected_chunk_set_id = str(chunk_sets[0].get("chunk_set_id") or "")

        chunks: list[dict[str, Any]] = []
        if selected_chunk_set_id:
            rows = storage._conn.execute(
                """
                SELECT chunk_id, chunk_index, content, token_count, section_hierarchy, created_at
                FROM global_chunks
                WHERE chunk_set_id = ?
                ORDER BY chunk_index
                """,
                (selected_chunk_set_id,),
            ).fetchall()
            for row in rows:
                chunks.append(
                    {
                        "chunk_id": row[0],
                        "chunk_index": row[1],
                        "content": row[2],
                        "token_count": row[3],
                        "section_hierarchy": row[4],
                        "created_at": row[5],
                        "chunk_set_id": selected_chunk_set_id,
                    }
                )

        return {
            "file_info": {
                "url": file_info["url"],
                "title": file_info["title"],
                "original_filename": file_info.get("original_filename", ""),
                "local_path": file_info.get("local_path", ""),
                "content_type": file_info.get("content_type", ""),
                "bytes": file_info.get("bytes", 0),
                "sha256": file_info.get("sha256", ""),
                "last_modified": file_info.get("last_modified", ""),
            },
            "markdown": {
                "content": markdown_data.get("markdown_content", ""),
                "source": markdown_data.get("markdown_source", ""),
                "updated_at": markdown_data.get("markdown_updated_at", ""),
            },
            "chunk_sets": chunk_sets,
            "active_chunk_set_id": selected_chunk_set_id,
            "chunks": chunks,
        }
    finally:
        storage.close()

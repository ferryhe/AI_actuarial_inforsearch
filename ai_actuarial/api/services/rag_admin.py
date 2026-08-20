from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from ai_actuarial.ai_runtime import build_embedding_fingerprint, infer_embedding_dimension, resolve_ai_function_runtime
from ai_actuarial.agentic_rag.manifest_profiles import PROFILES
from ai_actuarial.agentic_rag.staging_smoke import (
    STAGING_SMOKE_CONTRACT_VERSION,
    run_staging_smoke,
)
from ai_actuarial.config import settings
from ai_actuarial.shared_runtime import parse_int_clamped
from ai_actuarial.storage import Storage, _split_visible_categories


MAX_CATEGORY_STATS_CATEGORIES = 100
READY_DATA_GC_POLICY_VERSION = "ready-data-retention-gc.v1"
READY_DATA_GC_MINIMUM_AGE_DAYS = 14
READY_DATA_GC_KEEP_LATEST = 2
READY_DATA_GC_CLAIM_LEASE_SECONDS = 300


class RagAdminError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _staging_smoke_not_run(reason: str) -> dict[str, Any]:
    return {
        "contract_version": STAGING_SMOKE_CONTRACT_VERSION,
        "status": "not_run",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": 0,
        "query_source": "",
        "query": "",
        "query_sha256": hashlib.sha256(b"").hexdigest(),
        "matched_doc_id": "",
        "matched_file_url": "",
        "failure_reason": str(reason or "smoke_not_run")[:160],
        "catalog_doc_count": 0,
    }


def _staging_smoke_failed(reason: str) -> dict[str, Any]:
    result = _staging_smoke_not_run(reason)
    result["status"] = "failed"
    return result


def _staging_smoke_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return -1



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



def _visible_category_list(raw_categories: list[Any]) -> list[str]:
    categories: set[str] = set()
    for raw_category in raw_categories:
        for category in _split_visible_categories(_norm(raw_category)):
            categories.add(category)
    return sorted(categories, key=lambda item: item.lower())



def _category_filter(categories: list[str]) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    for category in categories:
        conditions.append("(ci.category = ? OR ci.category LIKE ? OR ci.category LIKE ? OR ci.category LIKE ?)")
        params.extend([category, f"{category};%", f"%; {category}", f"%; {category};%"])
    return " OR ".join(conditions), params



def _latest_ready_chunk_set(storage: Storage, *, file_url: str, profile_id: str) -> dict[str, Any] | None:
    row = storage._conn.execute(
        """
        SELECT s.chunk_set_id, s.file_url, s.profile_id, p.name, s.chunk_count, s.updated_at
        FROM file_chunk_sets s
        JOIN chunk_profiles p ON p.profile_id = s.profile_id
        WHERE s.file_url = ?
          AND s.profile_id = ?
          AND s.status = 'ready'
          AND COALESCE(s.chunk_count, 0) > 0
        ORDER BY s.updated_at DESC, s.created_at DESC
        LIMIT 1
        """,
        (file_url, profile_id),
    ).fetchone()
    if not row:
        return None
    return {
        "chunk_set_id": row[0],
        "file_url": row[1],
        "profile_id": row[2],
        "profile_name": row[3] or "",
        "chunk_count": row[4] or 0,
        "updated_at": row[5],
    }



def _unique_existing_chunk_file_urls(storage: Storage, *, file_urls: list[str], profile_id: str) -> list[str]:
    out: list[str] = []
    for file_url in file_urls:
        if file_url in out:
            continue
        if _latest_ready_chunk_set(storage, file_url=file_url, profile_id=profile_id):
            out.append(file_url)
    return out



def _category_file_urls_with_existing_chunks(storage: Storage, *, categories: list[str], profile_id: str) -> list[str]:
    where_sql, params = _category_filter(categories)
    if not where_sql:
        return []
    rows = storage._conn.execute(
        f"""
        SELECT DISTINCT ci.file_url
        FROM catalog_items ci
        JOIN file_chunk_sets s ON s.file_url = ci.file_url
        WHERE ({where_sql})
          AND ci.status = 'ok'
          AND ci.markdown_content IS NOT NULL
          AND ci.markdown_content != ''
          AND s.profile_id = ?
          AND s.status = 'ready'
          AND COALESCE(s.chunk_count, 0) > 0
        """,
        params + [profile_id],
    ).fetchall()
    return [row[0] for row in rows if row and row[0]]



def _bind_existing_chunk_sets(
    storage: Storage,
    *,
    kb_id: str,
    file_urls: list[str],
    profile_id: str,
    requested_count: int,
    bound_by: str = "kb_create",
) -> dict[str, Any]:
    bound = 0
    skipped_without_chunks: list[str] = []
    bindings: list[dict[str, Any]] = []
    for file_url in file_urls:
        chunk_set = _latest_ready_chunk_set(storage, file_url=file_url, profile_id=profile_id)
        if not chunk_set:
            skipped_without_chunks.append(file_url)
            continue
        binding = storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set["chunk_set_id"],
            bound_by=bound_by,
            binding_mode="follow_latest",
        )
        bound += 1
        bindings.append(binding)
    return {
        "profile_id": profile_id,
        "requested": requested_count,
        "bound": bound,
        "skipped_without_chunks": max(0, requested_count - bound),
        "skipped_file_urls": skipped_without_chunks,
        "bindings": bindings,
    }



def _add_and_bind_existing_profile_chunks(
    manager: Any,
    storage: Storage,
    *,
    kb_id: str,
    file_urls: list[str],
    profile_id: str,
    bound_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bindable_file_urls = _unique_existing_chunk_file_urls(
        storage,
        file_urls=file_urls,
        profile_id=profile_id,
    )
    add_result: dict[str, Any] = {"added_count": 0, "skipped_count": 0, "total_files": 0}
    if bindable_file_urls:
        add_result = manager.add_files_to_kb(kb_id, bindable_file_urls)
    binding_result = _bind_existing_chunk_sets(
        storage,
        kb_id=kb_id,
        file_urls=file_urls,
        profile_id=profile_id,
        requested_count=len(file_urls),
        bound_by=bound_by,
    )
    return add_result, binding_result


def _sync_category_kb_files(
    manager: Any,
    storage: Storage,
    *,
    kb_id: str,
    categories: list[str],
    profile_id: str,
    bound_by: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    sync_result = manager.sync_category_files(kb_id, categories)
    binding_result = None
    synced_file_urls = list(sync_result.get("file_urls") or [])
    if profile_id and synced_file_urls:
        binding_result = _bind_existing_chunk_sets(
            storage,
            kb_id=kb_id,
            file_urls=synced_file_urls,
            profile_id=profile_id,
            requested_count=len(synced_file_urls),
            bound_by=bound_by,
        )
    return sync_result, binding_result


def _sync_all_kb_files(
    manager: Any,
    storage: Storage,
    *,
    kb_id: str,
    profile_id: str,
    bound_by: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    sync_result = manager.sync_all_files(kb_id, profile_id=profile_id)
    binding_result = None
    synced_file_urls = list(sync_result.get("file_urls") or [])
    if profile_id and synced_file_urls:
        binding_result = _bind_existing_chunk_sets(
            storage,
            kb_id=kb_id,
            file_urls=synced_file_urls,
            profile_id=profile_id,
            requested_count=len(synced_file_urls),
            bound_by=bound_by,
        )
    return sync_result, binding_result



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
        "chunk_profile_id": getattr(kb, "chunk_profile_id", "") or "",
        "manifest_profile": getattr(kb, "manifest_profile", "general") or "general",
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



def _decorate_kb_chunk_profile(storage: Storage, payload: dict[str, Any]) -> dict[str, Any]:
    profile_id = _norm(payload.get("chunk_profile_id"))
    if not profile_id:
        bindings = storage.list_kb_chunk_bindings(_norm(payload.get("kb_id")))
        profile_ids = {
            _norm(binding.get("profile_id"))
            for binding in bindings
            if _norm(binding.get("profile_id"))
        }
        if len(profile_ids) == 1:
            profile_id = next(iter(profile_ids))
            payload["chunk_profile_id"] = profile_id
    if profile_id:
        profile = storage.get_chunk_profile(profile_id)
        if profile:
            payload["chunk_profile_name"] = profile.get("name") or profile_id
            payload["chunk_profile"] = {
                "profile_id": profile.get("profile_id") or profile_id,
                "name": profile.get("name") or profile_id,
                "chunk_size": profile.get("chunk_size"),
                "chunk_overlap": profile.get("chunk_overlap"),
                "splitter": profile.get("splitter"),
                "tokenizer": profile.get("tokenizer"),
                "version": profile.get("version"),
            }
    if "chunk_profile_name" not in payload:
        payload["chunk_profile_name"] = ""
    return payload



def _manifest_profile(value: Any) -> str:
    profile = _norm(value or "general").lower() or "general"
    if profile not in PROFILES:
        raise RagAdminError(f"manifest_profile must be one of: {', '.join(sorted(PROFILES))}")
    return profile


def _latest_iso(storage: Storage, *values: Any) -> str | None:
    best_raw = ""
    best_dt = None
    for value in values:
        raw = _norm(value)
        if not raw:
            continue
        dt = storage._parse_iso_to_utc(raw)
        if dt is None:
            if best_dt is None and raw > best_raw:
                best_raw = raw
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best_raw = raw
    return best_raw or None


def _iso_after(storage: Storage, left: Any, right: Any) -> bool:
    left_raw = _norm(left)
    right_raw = _norm(right)
    if not left_raw or not right_raw:
        return False
    left_dt = storage._parse_iso_to_utc(left_raw)
    right_dt = storage._parse_iso_to_utc(right_raw)
    if left_dt is not None and right_dt is not None:
        return left_dt > right_dt
    return left_raw > right_raw


def _resolve_agentic_output_dir(
    *,
    db_path: str,
    kb_id: str,
    profile: str,
    profile_version: str,
    requested_output_dir: Any,
) -> str:
    base_dir = (Path(db_path).resolve().parent / "agentic_ready_data").resolve()
    safe_kb_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in kb_id)
    requested = _norm(requested_output_dir)
    if requested:
        requested_path = Path(requested)
        if not requested_path.is_absolute():
            requested_path = base_dir / requested_path
        resolved = requested_path.resolve()
    else:
        resolved = (base_dir / "kbs" / safe_kb_id / profile / profile_version).resolve()
    try:
        resolved.relative_to(base_dir)
    except ValueError as exc:
        raise RagAdminError("output_dir must stay under the database agentic_ready_data directory", status_code=400) from exc
    return str(resolved)


def _is_link_or_reparse(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(file_attributes & reparse_flag)


def _recorded_ready_artifact_paths(
    output_path: Path,
    artifact_files: Any,
) -> list[tuple[str, Path]]:
    if not isinstance(artifact_files, (list, tuple)):
        raise ValueError("publication artifact list is invalid")
    resolved_output = output_path.resolve(strict=True)
    artifacts: dict[str, Path] = {}
    for raw_artifact in artifact_files:
        if not isinstance(raw_artifact, str):
            raise ValueError("publication artifact path is invalid")
        artifact = raw_artifact.strip()
        portable_parts = artifact.replace("\\", "/").split("/")
        windows_path = PureWindowsPath(artifact)
        if (
            not artifact
            or artifact != raw_artifact
            or Path(artifact).is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or any(part in {"", ".", ".."} for part in portable_parts)
        ):
            raise ValueError(f"invalid publication artifact path: {raw_artifact}")

        cursor = output_path
        for index, part in enumerate(portable_parts):
            cursor /= part
            if _is_link_or_reparse(cursor):
                raise ValueError(
                    f"ready_data artifact contains a link or reparse point: {artifact}"
                )
            entry_stat = cursor.lstat()
            if index < len(portable_parts) - 1:
                if not stat.S_ISDIR(entry_stat.st_mode):
                    raise ValueError(
                        f"ready_data artifact parent is not a directory: {artifact}"
                    )
            elif not stat.S_ISREG(entry_stat.st_mode):
                raise ValueError(
                    f"ready_data artifact is not a regular file: {artifact}"
                )
        resolved_artifact = cursor.resolve(strict=True)
        try:
            resolved_artifact.relative_to(resolved_output)
        except ValueError as exc:
            raise ValueError(
                f"artifact path escapes output_dir: {artifact}"
            ) from exc
        artifacts[artifact] = resolved_artifact
    return sorted(artifacts.items())


def _preflight_recorded_ready_publication(
    publication: Mapping[str, Any],
    *,
    allowed_output_root: str,
) -> tuple[Path, list[str]]:
    output_dir = str(publication.get("output_dir") or "")
    if not output_dir:
        raise ValueError("publication output_dir is empty")
    allowed_path = Path(os.path.abspath(allowed_output_root))
    if _is_link_or_reparse(allowed_path) or not allowed_path.is_dir():
        raise ValueError("allowed ready_data root is missing, linked, or a reparse point")
    allowed_root = allowed_path.resolve(strict=True)

    raw_output_path = Path(output_dir)
    if ".." in raw_output_path.parts:
        raise ValueError("publication output contains path traversal")
    output_path = Path(os.path.abspath(output_dir))
    try:
        relative_output = output_path.relative_to(allowed_path)
    except ValueError as exc:
        raise ValueError(
            "publication output escaped the allowed ready_data root"
        ) from exc
    current = allowed_path
    for part in relative_output.parts:
        current /= part
        if _is_link_or_reparse(current):
            raise ValueError("publication output contains a link or reparse point")
        if not current.is_dir():
            raise ValueError("publication output is not a directory")
    output_root = output_path.resolve(strict=True)
    try:
        output_root.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(
            "publication output escaped the allowed ready_data root"
        ) from exc

    artifact_files = publication.get("artifact_files")
    artifact_paths = _recorded_ready_artifact_paths(output_path, artifact_files)
    normalized_artifacts = [artifact for artifact, _path in artifact_paths]
    if "ready_data_manifest.json" not in normalized_artifacts:
        raise ValueError(
            "publication artifact list does not include ready_data_manifest.json"
        )
    return output_root, normalized_artifacts


def _agentic_staging_output_dir(base_output_dir: str, *, allowed_output_root: str) -> tuple[str, str]:
    allowed_root = Path(allowed_output_root).resolve()
    base = Path(base_output_dir).resolve()
    try:
        base.relative_to(allowed_root)
    except ValueError as exc:
        raise RagAdminError("ready_data output must stay under the allowed data root", status_code=400) from exc
    staging_path = base / "staging"
    if _is_link_or_reparse(staging_path):
        raise RagAdminError("ready_data staging root cannot be a link or reparse point", status_code=400)
    staging_path.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(staging_path):
        raise RagAdminError("ready_data staging root cannot be a link or reparse point", status_code=400)
    staging_root = staging_path.resolve(strict=True)
    try:
        staging_root.relative_to(allowed_root)
    except ValueError as exc:
        raise RagAdminError("ready_data staging root escaped the allowed data root", status_code=400) from exc
    candidate = staging_root / f"build-{uuid.uuid4().hex}"
    if candidate.parent != staging_root or _is_link_or_reparse(candidate):
        raise RagAdminError("invalid ready_data staging candidate", status_code=400)
    return str(candidate), str(staging_root)


def _ready_data_artifact_digest(output_dir: str, artifact_files: list[str]) -> str:
    """Hash ready-data content while excluding location/time-only manifest fields."""
    root_path = Path(os.path.abspath(output_dir))
    if _is_link_or_reparse(root_path):
        raise ValueError("ready_data output is a link or reparse point")
    root_path.resolve(strict=True)
    if not root_path.is_dir():
        raise ValueError("ready_data output is not a directory")
    artifact_paths = _recorded_ready_artifact_paths(root_path, artifact_files)
    digest = hashlib.sha256()
    for artifact, artifact_path in artifact_paths:
        content = artifact_path.read_bytes()
        if artifact_path.name == "ready_data_manifest.json":
            manifest = json.loads(content.decode("utf-8"))
            if isinstance(manifest, dict):
                manifest = dict(manifest)
                manifest.pop("built_at", None)
                manifest.pop("output_dir", None)
                manifest.pop("source_db", None)
                content = json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
        digest.update(artifact.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _same_ready_publication_identity(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> bool:
    return all(
        str(first.get(key) or "") == str(second.get(key) or "")
        for key in (
            "kb_id",
            "source_version_kind",
            "source_version_id",
            "profile",
            "artifact_digest",
        )
    )


def _validate_recorded_ready_publication(
    publication: Mapping[str, Any],
    *,
    validator,
    allowed_output_root: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        output_root, artifact_files = _preflight_recorded_ready_publication(
            publication,
            allowed_output_root=allowed_output_root,
        )
        actual_digest = _ready_data_artifact_digest(str(output_root), artifact_files)
        if actual_digest != str(publication.get("artifact_digest") or ""):
            raise ValueError("publication artifact digest does not match recorded digest")
        validation = validator(str(output_root))
        errors.extend(str(item) for item in validation.get("errors") or [])
        warnings.extend(str(item) for item in validation.get("warnings") or [])
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _verified_staging_candidate(
    *,
    output_dir: str,
    staging_root: str,
    allowed_output_root: str,
) -> tuple[Path, Path] | None:
    allowed_root = Path(allowed_output_root).resolve()
    root_path = Path(os.path.abspath(staging_root))
    if _is_link_or_reparse(root_path):
        raise ValueError("staging root is a link or reparse point")
    root = root_path.resolve(strict=True)
    try:
        root.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("staging root escaped the allowed output root") from exc

    candidate_path = Path(os.path.abspath(output_dir))
    if candidate_path.parent != root_path:
        raise ValueError("staging candidate is not a direct child of the verified staging root")
    if _is_link_or_reparse(candidate_path):
        raise ValueError("staging candidate is a link or reparse point")
    if not candidate_path.exists():
        return None
    candidate = candidate_path.resolve(strict=True)
    if candidate.parent != root:
        raise ValueError("staging candidate escaped the verified staging root")
    return candidate, root


def _require_generated_staging_candidate(
    *,
    returned_output_dir: str,
    expected_output_dir: str,
    staging_root: str,
    allowed_output_root: str,
) -> Path:
    returned_path = Path(os.path.abspath(returned_output_dir))
    expected_path = Path(os.path.abspath(expected_output_dir))
    if os.path.normcase(str(returned_path)) != os.path.normcase(str(expected_path)):
        raise ValueError("ready_data builder returned an unexpected staging output path")
    verified = _verified_staging_candidate(
        output_dir=str(returned_path),
        staging_root=staging_root,
        allowed_output_root=allowed_output_root,
    )
    if verified is None:
        raise ValueError("ready_data staging candidate does not exist")
    candidate, _root = verified
    if candidate != expected_path.resolve(strict=True):
        raise ValueError("ready_data staging candidate no longer matches the generated path")
    return candidate


def _staging_tree_digest(
    output_dir: str,
    *,
    staging_root: str,
    allowed_output_root: str,
) -> tuple[str, list[str]]:
    verified = _verified_staging_candidate(
        output_dir=output_dir,
        staging_root=staging_root,
        allowed_output_root=allowed_output_root,
    )
    artifact_files: list[str] = []
    digest = hashlib.sha256()
    if verified is None:
        return digest.hexdigest(), artifact_files
    root, _staging_root = verified
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if _is_link_or_reparse(path):
            raise ValueError(f"staging artifact is a link or reparse point: {path.name}")
        relative = path.relative_to(root).as_posix()
        artifact_files.append(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), artifact_files


def _remove_unreferenced_staging_dir(
    storage: Storage,
    *,
    output_dir: str,
    staging_root: str,
    allowed_output_root: str,
) -> bool:
    verified = _verified_staging_candidate(
        output_dir=output_dir,
        staging_root=staging_root,
        allowed_output_root=allowed_output_root,
    )
    if verified is None:
        return False
    candidate, root = verified
    if candidate == root or not candidate.is_dir():
        return False
    referenced_paths = {
        Path(str(row[0])).resolve()
        for row in storage._conn.execute(
            "SELECT output_dir FROM agentic_ready_publications WHERE output_dir <> ''"
        ).fetchall()
        if row[0]
    }
    referenced_paths.update(
        Path(str(row[0])).resolve()
        for row in storage._conn.execute(
            "SELECT output_dir FROM agentic_ready_manifests WHERE output_dir <> ''"
        ).fetchall()
        if row[0]
    )
    if candidate in referenced_paths:
        return False
    if _is_link_or_reparse(root) or _is_link_or_reparse(candidate):
        raise ValueError("staging path became a link or reparse point before cleanup")
    if candidate.parent != root:
        raise ValueError("staging candidate is no longer under the verified staging root")
    shutil.rmtree(candidate)
    return True


def _append_validation_warning(validation: dict[str, Any], warning: str) -> None:
    warnings = validation.setdefault("warnings", [])
    if warning not in warnings:
        warnings.append(warning)


def _best_effort_staging_cleanup(
    storage: Storage,
    *,
    output_dir: str,
    staging_root: str,
    allowed_output_root: str,
) -> str | None:
    try:
        _remove_unreferenced_staging_dir(
            storage,
            output_dir=output_dir,
            staging_root=staging_root,
            allowed_output_root=allowed_output_root,
        )
    except Exception as exc:  # noqa: BLE001
        return f"staging cleanup failed: {exc}"
    return None


def _bootstrap_legacy_ready_publication(
    storage: Storage,
    *,
    kb_id: str,
    profile: str,
    validator,
) -> None:
    state = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile=profile)
    if state["active_publication_id"]:
        return
    legacy = storage.get_agentic_ready_manifest(kb_id=kb_id, profile=profile)
    if not legacy or legacy.get("status") != "ready" or legacy.get("publication_id"):
        return
    output_dir = str(legacy.get("output_dir") or "")
    validation = validator(output_dir)
    if not validation.get("valid"):
        error_message = "; ".join(str(item) for item in validation.get("errors") or [])
        raise ValueError(f"legacy ready_data validation failed: {error_message or 'unknown error'}")
    artifact_files = list(legacy.get("artifact_files") or [])
    artifact_digest = _ready_data_artifact_digest(output_dir, artifact_files)
    publication = storage.record_agentic_ready_publication(
        kb_id=kb_id,
        index_version_id=None,
        source_version_kind="legacy_ready_data",
        source_version_id=f"artifact:{artifact_digest}",
        profile=profile,
        profile_version=str(legacy.get("profile_version") or "1"),
        status="validated",
        output_dir=output_dir,
        artifact_files=artifact_files,
        doc_count=int(legacy.get("doc_count") or 0),
        section_count=int(legacy.get("section_count") or 0),
        built_at=legacy.get("built_at"),
        artifact_digest=artifact_digest,
        source_db=str(legacy.get("source_db") or storage.db_path),
        schema_versions=dict(legacy.get("schema_versions") or {}),
    )
    storage.publish_agentic_ready_publication(
        str(publication["publication_id"]),
        expected_active_publication_id=None,
    )


def _rollback_agentic_ready_publication(
    storage: Storage,
    *,
    kb_id: str,
    profile: str,
    validator,
    allowed_output_root: str,
) -> dict[str, Any]:
    """Validate the previous artifact immediately before the guarded slot swap."""
    state = storage.get_agentic_ready_publication_state(
        kb_id=kb_id,
        profile=profile,
    )
    active_id = state["active_publication_id"]
    previous_id = state["previous_publication_id"]
    previous = state.get("previous_publication")
    if not active_id or not previous_id or not previous:
        raise ValueError("no previous validated ready-data publication is available")
    def validate_previous(candidate: dict[str, Any]) -> bool:
        validation = _validate_recorded_ready_publication(
            candidate,
            validator=validator,
            allowed_output_root=allowed_output_root,
        )
        if validation["valid"]:
            return True
        error_message = "; ".join(validation["errors"])
        raise ValueError(
            f"previous ready_data validation failed: {error_message or 'unknown error'}"
        )

    return storage.rollback_agentic_ready_publication(
        kb_id=kb_id,
        profile=profile,
        expected_active_publication_id=str(active_id),
        expected_previous_publication_id=str(previous_id),
        validated_previous_publication_id=str(previous_id),
        validate_previous_publication=validate_previous,
    )


def _kb_agentic_source_status(storage: Storage, *, kb_id: str) -> dict[str, Any]:
    row = storage._conn.execute(
        """
        SELECT updated_at
        FROM rag_knowledge_bases
        WHERE kb_id = ?
        """,
        (kb_id,),
    ).fetchone()
    kb_updated_at = row[0] if row else None
    doc_count = int(
        storage._conn.execute(
            """
            SELECT COUNT(DISTINCT c.file_url)
            FROM catalog_items c
            JOIN rag_kb_files kf ON kf.file_url = c.file_url
            WHERE kf.kb_id = ?
              AND c.status = 'ok'
            """,
            (kb_id,),
        ).fetchone()[0]
        or 0
    )
    has_chunk_bindings = bool(
        storage._conn.execute(
            """
            SELECT 1
            FROM kb_chunk_bindings b
            JOIN rag_kb_files kf
              ON kf.kb_id = b.kb_id
             AND kf.file_url = b.file_url
            JOIN catalog_items c
              ON c.file_url = b.file_url
             AND c.status = 'ok'
            JOIN file_chunk_sets s
              ON s.chunk_set_id = b.chunk_set_id
             AND s.file_url = b.file_url
            WHERE b.kb_id = ?
            LIMIT 1
            """,
            (kb_id,),
        ).fetchone()
    )
    if has_chunk_bindings:
        latest_chunk_at = storage._conn.execute(
            """
            SELECT MAX(s.updated_at)
            FROM kb_chunk_bindings b
            JOIN rag_kb_files kf
              ON kf.kb_id = b.kb_id
             AND kf.file_url = b.file_url
            JOIN catalog_items c
              ON c.file_url = b.file_url
             AND c.status = 'ok'
            JOIN file_chunk_sets s
              ON s.chunk_set_id = b.chunk_set_id
             AND s.file_url = b.file_url
            WHERE b.kb_id = ?
            """,
            (kb_id,),
        ).fetchone()[0]
    else:
        latest_chunk_at = storage._conn.execute(
            """
            SELECT MAX(s.updated_at)
            FROM rag_kb_files kf
            JOIN catalog_items c
              ON c.file_url = kf.file_url
             AND c.status = 'ok'
            LEFT JOIN file_chunk_sets s ON s.file_url = kf.file_url
            WHERE kf.kb_id = ?
            """,
            (kb_id,),
        ).fetchone()[0]
    latest_added_at = storage._conn.execute(
        """
        SELECT MAX(added_at)
        FROM rag_kb_files
        WHERE kb_id = ?
        """,
        (kb_id,),
    ).fetchone()[0]
    metadata_row = storage._conn.execute(
        """
        SELECT MAX(c.updated_at), MAX(c.markdown_updated_at), MAX(f.last_seen), MAX(f.crawl_time)
        FROM rag_kb_files kf
        JOIN catalog_items c ON c.file_url = kf.file_url
        LEFT JOIN files f ON f.url = kf.file_url
        WHERE kf.kb_id = ?
        """,
        (kb_id,),
    ).fetchone()
    latest_source_at = _latest_iso(
        storage,
        kb_updated_at,
        latest_added_at,
        latest_chunk_at,
        *(metadata_row or ()),
    )
    return {
        "current_doc_count": doc_count,
        "latest_source_at": latest_source_at,
    }


def _build_agentic_manifest_status(
    *,
    storage: Storage,
    kb_id: str,
    profile: str,
) -> dict[str, Any]:
    normalized_profile = _manifest_profile(profile)
    profile_def = PROFILES[normalized_profile]
    source_status = _kb_agentic_source_status(storage, kb_id=kb_id)
    source_state = storage.get_agentic_ready_source_state(
        kb_id=kb_id,
        profile=normalized_profile,
    )
    automation = storage.get_agentic_ready_automation_state(
        kb_id=kb_id,
        profile=normalized_profile,
    )
    publication_state = storage.get_agentic_ready_publication_state(
        kb_id=kb_id,
        profile=normalized_profile,
    )
    manifest = storage.get_agentic_ready_manifest(kb_id=kb_id, profile=normalized_profile)
    if not manifest:
        return {
            "kb_id": kb_id,
            "profile": normalized_profile,
            "profile_version": profile_def.version,
            "status": "missing",
            "usable": False,
            "fallback_mode": "standard",
            "current_doc_count": source_status["current_doc_count"],
            "stale_reason": "ready_data manifest has not been built",
            "source_state": source_state,
            "serving_stale": bool(source_state["serving_stale"]),
            "stale_confirmed": bool(source_state["stale_confirmed"]),
            "stale_severity": source_state["stale_severity"],
            "event_generation": source_state["event_generation"],
            "pending_evaluation_generation": source_state[
                "pending_evaluation_generation"
            ],
            "evaluated_generation": source_state["evaluated_generation"],
            "authoritative_source_version_kind": source_state[
                "evaluated_source_version_kind"
            ],
            "authoritative_source_version_id": source_state[
                "evaluated_source_version_id"
            ],
            "automatic_build_enabled": source_state["automatic_build_enabled"],
            "automatic_publish_enabled": source_state["automatic_publish_enabled"],
            "automation": automation,
            "automation_state": automation["automation_state"],
            "publication_revision": int(
                publication_state.get("publication_revision") or 0
            ),
        }

    payload = dict(manifest)
    status = _norm(payload.get("status")).lower() or "missing"
    stale_reason = ""
    authoritative_state_available = bool(
        source_state["has_source_state"]
        and not source_state["legacy_heuristic_required"]
    )
    if status == "ready" and authoritative_state_available:
        if source_state["serving_stale"]:
            status = "stale"
            stale_reason = "; ".join(source_state["stale_reasons"])
            if not stale_reason:
                stale_reason = "ready_data source evaluation is pending"
    elif status == "ready":
        built_at = _norm(payload.get("built_at"))
        latest_source_at = _norm(source_status.get("latest_source_at"))
        if _iso_after(storage, latest_source_at, built_at):
            status = "stale"
            stale_reason = "KB source files changed after the ready_data manifest was built"
        elif int(payload.get("doc_count") or 0) != int(source_status["current_doc_count"]):
            status = "stale"
            stale_reason = "KB document count differs from the ready_data manifest"
    if status == "ready" and not source_state["serving_allowed"]:
        status = "stale"
        stale_reason = "; ".join(source_state["stale_reasons"])
        if not stale_reason:
            stale_reason = "ready_data is blocked by a hard source-state gate"
    artifact_usable = _norm(payload.get("status")).lower() == "ready"
    usable = artifact_usable and bool(source_state["serving_allowed"])
    if not authoritative_state_available:
        usable = status == "ready" and bool(source_state["serving_allowed"])
    payload.update(
        {
            "status": status,
            "usable": usable,
            "fallback_mode": "agentic" if usable else "standard",
            "current_doc_count": source_status["current_doc_count"],
            "latest_source_at": source_status["latest_source_at"],
            "source_state": source_state,
            "serving_stale": bool(source_state["serving_stale"]),
            "stale_confirmed": bool(source_state["stale_confirmed"]),
            "stale_severity": source_state["stale_severity"],
            "event_generation": source_state["event_generation"],
            "pending_evaluation_generation": source_state[
                "pending_evaluation_generation"
            ],
            "evaluated_generation": source_state["evaluated_generation"],
            "authoritative_source_version_kind": source_state[
                "evaluated_source_version_kind"
            ],
            "authoritative_source_version_id": source_state[
                "evaluated_source_version_id"
            ],
            "automatic_build_enabled": source_state["automatic_build_enabled"],
            "automatic_publish_enabled": source_state[
                "automatic_publish_enabled"
            ],
            "automation": automation,
            "automation_state": automation["automation_state"],
            "publication_revision": int(
                publication_state.get("publication_revision") or 0
            ),
        }
    )
    if stale_reason:
        payload["stale_reason"] = stale_reason
    elif status in {"missing", "failed", "stale"} and "stale_reason" not in payload:
        payload["stale_reason"] = payload.get("error_message") or "ready_data is unavailable"
    return payload


def _decorate_kb_agentic_manifest(storage: Storage, payload: dict[str, Any]) -> dict[str, Any]:
    kb_id = _norm(payload.get("kb_id"))
    profile = _manifest_profile(payload.get("manifest_profile") or "general")
    payload["manifest_profile"] = profile
    payload["agentic_ready_manifest"] = _build_agentic_manifest_status(
        storage=storage,
        kb_id=kb_id,
        profile=profile,
    )
    payload["agentic_ready_available"] = bool(payload["agentic_ready_manifest"].get("usable"))
    payload["agentic_fallback_mode"] = payload["agentic_ready_manifest"].get("fallback_mode") or "standard"
    return payload


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



def _request_already_authorized(auth: Any | None) -> bool:
    if auth is None or not getattr(auth, "token", None):
        return False
    permissions = getattr(auth, "permissions", frozenset())
    return bool({"catalog.write", "config.write", "tasks.run"} & set(permissions))


def _require_config_write_token(headers: Mapping[str, str], auth: Any | None = None) -> None:
    if _request_already_authorized(auth):
        return
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



def create_chunk_profile(*, db_path: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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



def delete_chunk_profile(*, db_path: str, profile_id: str, headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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


def update_chunk_profile(*, db_path: str, profile_id: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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
        table_names = {
            row[0]
            for row in storage._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if row and row[0]
        }
        raw_categories: list[Any] = []
        if "source_metadata" in table_names:
            cursor = storage._conn.execute(
                """
                SELECT DISTINCT category FROM source_metadata
                WHERE category IS NOT NULL AND category != ''
                """
            )
            raw_categories.extend(row[0] for row in cursor.fetchall() if row[0])
        cursor = storage._conn.execute(
            """
            SELECT DISTINCT category FROM catalog_items
            WHERE category IS NOT NULL AND category != ''
            """
        )
        raw_categories.extend(row[0] for row in cursor.fetchall() if row[0])
        mapped_categories = _visible_category_list(raw_categories)
        return {"categories": mapped_categories, "count": len(mapped_categories)}
    finally:
        storage.close()


def get_category_stats(*, db_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    categories = _list(payload.get("categories"), "categories")
    if len(categories) > MAX_CATEGORY_STATS_CATEGORIES:
        raise RagAdminError(f"categories can include at most {MAX_CATEGORY_STATS_CATEGORIES} items")
    profile_id = _norm(payload.get("profile_id") or payload.get("chunk_profile_id"))
    kb_id = _norm(payload.get("kb_id"))

    _KnowledgeBase, _manager, storage = _manager_and_storage(db_path)
    try:
        if profile_id and not storage.get_chunk_profile(profile_id):
            raise RagAdminError("chunk profile not found", status_code=404)
        if kb_id:
            row = storage._conn.execute("SELECT 1 FROM rag_knowledge_bases WHERE kb_id = ?", (kb_id,)).fetchone()
            if not row:
                raise RagAdminError(f"Knowledge base '{kb_id}' not found", status_code=404)

        rows: list[dict[str, Any]] = []
        totals = {
            "total_files": 0,
            "markdown_files": 0,
            "ready_chunk_files": 0,
            "in_kb_files": 0,
        }
        chunk_profile_clause = "AND s.profile_id = ?" if profile_id else ""
        for category in categories:
            where_sql, params = _category_filter([category])
            if not where_sql:
                continue
            sql_params: list[Any] = []
            if profile_id:
                sql_params.append(profile_id)
            sql_params.append(kb_id)
            sql_params.append(kb_id)
            sql_params.extend(params)
            row = storage._conn.execute(
                f"""
                SELECT
                    COUNT(DISTINCT ci.file_url) AS total_files,
                    COUNT(DISTINCT CASE
                        WHEN ci.markdown_content IS NOT NULL AND ci.markdown_content != '' THEN ci.file_url
                    END) AS markdown_files,
                    COUNT(DISTINCT CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM file_chunk_sets s
                            WHERE s.file_url = ci.file_url
                              {chunk_profile_clause}
                              AND s.status = 'ready'
                              AND COALESCE(s.chunk_count, 0) > 0
                        ) THEN ci.file_url
                    END) AS ready_chunk_files,
                    COUNT(DISTINCT CASE
                        WHEN ? != '' AND EXISTS (
                            SELECT 1
                            FROM rag_kb_files kf
                            WHERE kf.kb_id = ? AND kf.file_url = ci.file_url
                        ) THEN ci.file_url
                    END) AS in_kb_files
                FROM catalog_items ci
                WHERE ({where_sql})
                  AND ci.status = 'ok'
                """,
                sql_params,
            ).fetchone()
            item = {
                "name": category,
                "total_files": int((row[0] if row else 0) or 0),
                "markdown_files": int((row[1] if row else 0) or 0),
                "ready_chunk_files": int((row[2] if row else 0) or 0),
                "in_kb_files": int((row[3] if row else 0) or 0),
            }
            for key in totals:
                totals[key] += int(item[key])
            rows.append(item)
        return {
            "categories": rows,
            "totals": totals,
            "profile_id": profile_id or None,
            "kb_id": kb_id or None,
        }
    finally:
        storage.close()


_KB_LIST_COLUMN_DEFINITIONS = {
    "kb_id": "TEXT",
    "name": "TEXT DEFAULT ''",
    "description": "TEXT DEFAULT ''",
    "kb_mode": "TEXT DEFAULT 'category'",
    "chunk_profile_id": "TEXT",
    "manifest_profile": "TEXT DEFAULT 'general'",
    "embedding_provider": "TEXT NOT NULL DEFAULT 'openai'",
    "embedding_model": "TEXT NOT NULL DEFAULT 'text-embedding-3-large'",
    "embedding_dimension": "INTEGER",
    "chunk_size": "INTEGER NOT NULL DEFAULT 800",
    "chunk_overlap": "INTEGER NOT NULL DEFAULT 100",
    "index_type": "TEXT NOT NULL DEFAULT 'Flat'",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    "file_count": "INTEGER DEFAULT 0",
    "chunk_count": "INTEGER DEFAULT 0",
    "index_dirty_at": "TEXT",
}
_KB_LIST_FILE_COLUMN_DEFINITIONS = {
    "kb_id": "TEXT",
    "file_url": "TEXT",
    "added_at": "TEXT",
    "chunk_count": "INTEGER DEFAULT 0",
    "indexed_at": "TEXT",
}
_KB_LIST_CONNECTION_LOCAL_PATHS = frozenset({"", ":memory:"})


def _kb_list_schema_ready(conn: Any) -> bool:
    kb_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(rag_knowledge_bases)")
    }
    if not _KB_LIST_COLUMN_DEFINITIONS.keys() <= kb_columns:
        return False
    file_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(rag_kb_files)")
    }
    return _KB_LIST_FILE_COLUMN_DEFINITIONS.keys() <= file_columns


def _ensure_kb_list_schema_on_connection(conn: Any) -> None:
    try:
        if _kb_list_schema_ready(conn):
            return
        conn.execute("BEGIN IMMEDIATE")
        if _kb_list_schema_ready(conn):
            conn.commit()
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            )
            """
        )
        existing_kb_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(rag_knowledge_bases)")
        }
        for name, definition in _KB_LIST_COLUMN_DEFINITIONS.items():
            if name not in existing_kb_columns:
                conn.execute(f"ALTER TABLE rag_knowledge_bases ADD COLUMN {name} {definition}")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
            )
            """
        )
        existing_file_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(rag_kb_files)")
        }
        for name, definition in _KB_LIST_FILE_COLUMN_DEFINITIONS.items():
            if name not in existing_file_columns:
                conn.execute(f"ALTER TABLE rag_kb_files ADD COLUMN {name} {definition}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _ensure_kb_list_schema(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _ensure_kb_list_schema_on_connection(conn)
    finally:
        conn.close()


def _kb_list_row_payload(row: Any) -> dict[str, Any]:
    return {
        "kb_id": row[0],
        "name": row[1],
        "description": row[2],
        "kb_mode": row[3] or "category",
        "chunk_profile_id": row[4] or "",
        "manifest_profile": str(row[5] or "general").strip().lower() or "general",
        "embedding_provider": str(row[6] or "openai").strip().lower() or "openai",
        "embedding_model": row[7],
        "embedding_dimension": int(row[8]) if row[8] not in (None, "") else None,
        "chunk_size": row[9],
        "chunk_overlap": row[10],
        "index_type": row[11],
        "created_at": row[12] or datetime.now(timezone.utc).isoformat(),
        "updated_at": row[13] or datetime.now(timezone.utc).isoformat(),
        "file_count": row[14],
        "chunk_count": row[15],
    }


def list_knowledge_bases(*, db_path: str, query: Mapping[str, Any]) -> dict[str, Any]:
    connection_local = db_path in _KB_LIST_CONNECTION_LOCAL_PATHS
    if not connection_local:
        _ensure_kb_list_schema(db_path)
    storage = Storage(db_path)
    try:
        if connection_local:
            _ensure_kb_list_schema_on_connection(storage._conn)
        kb_mode = _norm(query.get("kb_mode"))
        search = _norm(query.get("search")).lower()
        rows = storage._conn.execute(
            """
            SELECT kb_id, name, description, kb_mode, chunk_profile_id, manifest_profile, embedding_provider, embedding_model, embedding_dimension, chunk_size, chunk_overlap,
                   index_type, created_at, updated_at, file_count, chunk_count
            FROM rag_knowledge_bases
            ORDER BY created_at DESC
            """
        ).fetchall()
        current_embeddings = _current_embeddings_payload(storage=storage)
        kbs = []
        for row in rows:
            kb_payload = _kb_list_row_payload(row)
            if kb_mode and kb_payload["kb_mode"] != kb_mode:
                continue
            if search and not (
                search in (kb_payload["name"] or "").lower()
                or search in (kb_payload["description"] or "").lower()
                or search in (kb_payload["kb_id"] or "").lower()
            ):
                continue
            payload = _build_kb_embedding_status(
                storage=storage,
                kb_payload=_decorate_kb_chunk_profile(storage, kb_payload),
                current_embeddings=current_embeddings,
            )
            kbs.append(_decorate_kb_agentic_manifest(storage, payload))
        return {"knowledge_bases": kbs, "current_embeddings": current_embeddings}
    finally:
        storage.close()



def create_knowledge_base(*, db_path: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    kb_id = _kb_id(payload.get("kb_id"))
    name = _norm(payload.get("name"))
    if not name:
        raise RagAdminError("name is required")
    kb_mode = _norm(payload.get("kb_mode") or "manual").lower()
    if kb_mode not in {"manual", "category", "all"}:
        raise RagAdminError("kb_mode must be one of: 'all', 'category', or 'manual'")
    manifest_profile = _manifest_profile(payload.get("manifest_profile") or "general")
    categories = _list(payload.get("categories"), "categories")
    file_urls = _list(payload.get("file_urls"), "file_urls")
    if kb_mode == "category" and not categories:
        raise RagAdminError("categories required for category mode")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if manager.get_kb(kb_id):
            raise RagAdminError(f"Knowledge base '{kb_id}' already exists", status_code=409)
        chunk_profile_id = _norm(payload.get("chunk_profile_id") or payload.get("profile_id"))
        chunk_profile: dict[str, Any] | None = None
        if chunk_profile_id:
            chunk_profile = storage.get_chunk_profile(chunk_profile_id)
            if not chunk_profile:
                raise RagAdminError("chunk profile not found", status_code=404)
            chunk_size = int(chunk_profile.get("chunk_size") or manager.config.max_chunk_tokens)
            chunk_overlap = int(chunk_profile.get("chunk_overlap") or 0)
        else:
            chunk_size = parse_int_clamped(payload.get("chunk_size"), default=800, min_value=1, max_value=10000)
            chunk_overlap = parse_int_clamped(payload.get("chunk_overlap"), default=100, min_value=0, max_value=10000)
        runtime_embedding = manager.get_current_embedding_metadata()
        manager.create_kb(
            kb_id=kb_id,
            name=name,
            description=_norm(payload.get("description")),
            kb_mode=kb_mode,
            chunk_profile_id=chunk_profile_id,
            manifest_profile=manifest_profile,
            embedding_model=runtime_embedding["model"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunk_binding_result: dict[str, Any] | None = None
        category_sync_result: dict[str, Any] | None = None
        all_sync_result: dict[str, Any] | None = None
        if kb_mode == "category":
            if chunk_profile_id:
                manager.link_kb_to_categories(kb_id, categories, auto_sync=False)
                category_sync_result, chunk_binding_result = _sync_category_kb_files(
                    manager,
                    storage,
                    kb_id=kb_id,
                    categories=categories,
                    profile_id=chunk_profile_id,
                    bound_by="kb_create_category_sync",
                )
            else:
                manager.link_kb_to_categories(kb_id, categories)
        elif kb_mode == "all":
            all_sync_result, chunk_binding_result = _sync_all_kb_files(
                manager,
                storage,
                kb_id=kb_id,
                profile_id=chunk_profile_id,
                bound_by="kb_create_all_sync",
            )
        elif file_urls:
            if chunk_profile_id:
                bindable_file_urls = _unique_existing_chunk_file_urls(
                    storage,
                    file_urls=file_urls,
                    profile_id=chunk_profile_id,
                )
                if bindable_file_urls:
                    manager.add_files_to_kb(kb_id, bindable_file_urls)
                chunk_binding_result = _bind_existing_chunk_sets(
                    storage,
                    kb_id=kb_id,
                    file_urls=file_urls,
                    profile_id=chunk_profile_id,
                    requested_count=len(file_urls),
                )
            else:
                manager.add_files_to_kb(kb_id, file_urls)
        kb = manager.get_kb(kb_id)
        response_payload = _decorate_kb_agentic_manifest(
            storage,
            _decorate_kb_chunk_profile(storage, _serialize_kb(kb)),
        )
        response: dict[str, Any] = {"knowledge_base": response_payload}
        if chunk_profile:
            response["chunk_profile"] = chunk_profile
        if category_sync_result is not None:
            response["category_sync"] = category_sync_result
        if all_sync_result is not None:
            response["all_sync"] = all_sync_result
        if chunk_binding_result is not None:
            response["chunk_bindings"] = chunk_binding_result
        return response
    finally:
        storage.close()



def get_knowledge_base(*, db_path: str, kb_id: str) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        payload = _build_kb_embedding_status(storage=storage, kb_payload=_decorate_kb_chunk_profile(storage, _serialize_kb(kb)))
        payload = _decorate_kb_agentic_manifest(storage, payload)
        payload["stats"] = manager.get_kb_stats(kid)
        payload["categories"] = manager.get_kb_categories(kid)
        return {"knowledge_base": payload}
    finally:
        storage.close()


def get_agentic_ready_manifest(*, db_path: str, kb_id: str, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        profile = _manifest_profile((query or {}).get("profile") or getattr(kb, "manifest_profile", "general"))
        from .ready_data_publication import read_public_ready_data_snapshot

        return read_public_ready_data_snapshot(
            storage,
            kb_id=kid,
            profile=profile,
        )
    finally:
        storage.close()


def build_agentic_ready_manifest(
    *,
    db_path: str,
    kb_id: str,
    payload: dict[str, Any],
    headers: Mapping[str, str],
    auth: Any | None = None,
) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
    return _build_agentic_ready_manifest_core(
        db_path=db_path,
        kb_id=kb_id,
        payload=payload,
        publish=True,
    )


def _build_agentic_ready_manifest_core(
    *,
    db_path: str,
    kb_id: str,
    payload: dict[str, Any],
    publish: bool,
) -> dict[str, Any]:
    """Build and validate one staging attempt without applying HTTP authorization."""
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        profile = _manifest_profile(
            payload.get("profile")
            or payload.get("manifest_profile")
            or getattr(kb, "manifest_profile", "general")
        )
        profile_def = PROFILES[profile]

        from ai_actuarial.agentic_rag import ready_data_builder

        output_dir = _resolve_agentic_output_dir(
            db_path=db_path,
            kb_id=kid,
            profile=profile,
            profile_version=profile_def.version,
            requested_output_dir=payload.get("output_dir"),
        )
        allowed_output_root = str((Path(db_path).resolve().parent / "agentic_ready_data").resolve())
        staging_output_dir, staging_root = _agentic_staging_output_dir(
            output_dir,
            allowed_output_root=allowed_output_root,
        )
        builder_manifest: dict[str, Any] = {}
        candidate_output_dir = staging_output_dir
        artifact_files: list[str] = []
        artifact_digest = ""
        observed_index_version_id: str | None = None
        source_version_kind = "failed_build_attempt"
        source_version_id = f"attempt:{Path(staging_output_dir).name}"
        candidate_publication: dict[str, Any] = {}
        publication_state: dict[str, Any] = {}
        validated_attempt_recorded = False
        smoke_result = _staging_smoke_not_run("build_not_completed")
        initial_source_state = storage.get_agentic_ready_source_state(
            kb_id=kid,
            profile=profile,
        )
        captured_evaluation_generation = (
            initial_source_state["pending_evaluation_generation"]
            if initial_source_state["pending_evaluation"]
            else None
        )
        try:
            builder_manifest = ready_data_builder.build_l0(
                db_path=db_path,
                output_dir=staging_output_dir,
                profile=profile,
                kb_id=kid,
            )
            returned_output_dir = str(builder_manifest.get("output_dir") or staging_output_dir)
            _require_generated_staging_candidate(
                returned_output_dir=returned_output_dir,
                expected_output_dir=staging_output_dir,
                staging_root=staging_root,
                allowed_output_root=allowed_output_root,
            )
            candidate_output_dir = returned_output_dir
            source_version_kind = str(builder_manifest.get("source_version_kind") or "")
            source_version_id = str(builder_manifest.get("source_version_id") or "")
            observed_index_version_id = (
                str(builder_manifest.get("index_version_id") or "").strip() or None
            )
            if not source_version_kind or not source_version_id:
                raise ValueError("ready_data builder did not report its source snapshot version")
            validation = ready_data_builder.validate(candidate_output_dir)
            artifact_files = list(builder_manifest.get("artifact_files") or [])
            artifact_digest = _ready_data_artifact_digest(candidate_output_dir, artifact_files)
            if validation.get("valid"):
                try:
                    smoke_result = run_staging_smoke(
                        output_dir=candidate_output_dir,
                        profile=profile,
                        kb_id=kid,
                        timeout_seconds=float(
                            Storage.AGENTIC_READY_FUTURE_EXECUTION_POLICY[
                                "staging_smoke_timeout_seconds"
                            ]
                        ),
                    )
                except Exception:  # noqa: BLE001
                    smoke_result = _staging_smoke_failed("smoke_execution_failed")
                smoke_status = str(smoke_result.get("status") or "")
                smoke_contract = str(
                    smoke_result.get("contract_version") or ""
                )
                smoke_catalog_doc_count = _staging_smoke_count(
                    smoke_result.get("catalog_doc_count")
                )
                smoke_has_catalog_reference = bool(
                    str(smoke_result.get("matched_doc_id") or "").strip()
                    or str(smoke_result.get("matched_file_url") or "").strip()
                )
                smoke_contract_valid = (
                    smoke_contract == STAGING_SMOKE_CONTRACT_VERSION
                )
                smoke_passed = (
                    smoke_contract_valid
                    and smoke_status == "passed"
                    and smoke_catalog_doc_count > 0
                    and smoke_has_catalog_reference
                )
                empty_smoke_confirmed = (
                    smoke_contract_valid
                    and smoke_status == "skipped_empty"
                    and smoke_catalog_doc_count == 0
                )
                if not smoke_passed and not empty_smoke_confirmed:
                    if not smoke_contract_valid:
                        failure_reason = "invalid_smoke_contract"
                    elif smoke_status == "passed" and not smoke_has_catalog_reference:
                        failure_reason = "catalog_reference_missing"
                    elif smoke_status == "failed":
                        failure_reason = str(
                            smoke_result.get("failure_reason") or "smoke_failed"
                        )[:160]
                    else:
                        failure_reason = "invalid_smoke_status"
                    if not failure_reason:
                        failure_reason = "smoke_failed"
                    smoke_result = {
                        **smoke_result,
                        "contract_version": STAGING_SMOKE_CONTRACT_VERSION,
                        "status": "failed",
                        "catalog_doc_count": max(0, smoke_catalog_doc_count),
                        "failure_reason": failure_reason,
                    }
                    validation["valid"] = False
                    validation.setdefault("errors", []).append(
                        f"ready_data staging smoke failed: {failure_reason}"
                    )
            else:
                smoke_result = _staging_smoke_not_run(
                    "structural_validation_failed"
                )
            if not validation.get("valid"):
                error_message = "; ".join(str(item) for item in validation.get("errors") or [])
                candidate_publication = storage.record_agentic_ready_publication(
                    kb_id=kid,
                    index_version_id=observed_index_version_id,
                    source_version_kind=source_version_kind,
                    source_version_id=source_version_id,
                    profile=profile,
                    profile_version=str(builder_manifest.get("profile_version") or profile_def.version),
                    status="failed",
                    output_dir="",
                    artifact_files=artifact_files,
                    doc_count=int(builder_manifest.get("doc_count") or 0),
                    section_count=int(builder_manifest.get("section_count") or 0),
                    built_at=builder_manifest.get("built_at"),
                    artifact_digest=artifact_digest,
                    source_db=str(builder_manifest.get("source_db") or db_path),
                    schema_versions=dict(builder_manifest.get("schema_versions") or {}),
                    smoke_result=smoke_result,
                    error_message=error_message or "ready_data validation failed",
                )
                cleanup_warning = _best_effort_staging_cleanup(
                    storage,
                    output_dir=candidate_output_dir,
                    staging_root=staging_root,
                    allowed_output_root=allowed_output_root,
                )
                if cleanup_warning:
                    _append_validation_warning(validation, cleanup_warning)
            else:
                if publish:
                    _bootstrap_legacy_ready_publication(
                        storage,
                        kb_id=kid,
                        profile=profile,
                        validator=ready_data_builder.validate,
                    )
                _require_generated_staging_candidate(
                    returned_output_dir=candidate_output_dir,
                    expected_output_dir=staging_output_dir,
                    staging_root=staging_root,
                    allowed_output_root=allowed_output_root,
                )
                candidate_publication = storage.record_agentic_ready_publication(
                    kb_id=kid,
                    index_version_id=observed_index_version_id,
                    source_version_kind=source_version_kind,
                    source_version_id=source_version_id,
                    profile=profile,
                    profile_version=str(builder_manifest.get("profile_version") or profile_def.version),
                    status="validated",
                    output_dir=candidate_output_dir,
                    artifact_files=artifact_files,
                    doc_count=int(builder_manifest.get("doc_count") or 0),
                    section_count=int(builder_manifest.get("section_count") or 0),
                    built_at=builder_manifest.get("built_at"),
                    artifact_digest=artifact_digest,
                    source_db=str(builder_manifest.get("source_db") or db_path),
                    schema_versions=dict(builder_manifest.get("schema_versions") or {}),
                    smoke_result=smoke_result,
                    error_message="",
                )
                validated_attempt_recorded = True
                recorded_publication_id = str(candidate_publication["publication_id"])
                if not publish:
                    publication_state = storage.get_agentic_ready_publication_state(
                        kb_id=kid,
                        profile=profile,
                    )
                    return {
                        "kb_id": kid,
                        "manifest": _build_agentic_manifest_status(
                            storage=storage,
                            kb_id=kid,
                            profile=profile,
                        ),
                        "candidate_publication": candidate_publication,
                        "publication_state": publication_state,
                        "validation": validation,
                    }
                current_publication_state = storage.get_agentic_ready_publication_state(
                    kb_id=kid,
                    profile=profile,
                )
                _require_generated_staging_candidate(
                    returned_output_dir=str(candidate_publication["output_dir"]),
                    expected_output_dir=staging_output_dir,
                    staging_root=staging_root,
                    allowed_output_root=allowed_output_root,
                )
                active_publication = current_publication_state.get("active_publication")
                if active_publication:
                    active_validation = _validate_recorded_ready_publication(
                        active_publication,
                        validator=ready_data_builder.validate,
                        allowed_output_root=allowed_output_root,
                    )
                else:
                    active_validation = None

                if active_publication and active_validation and active_validation["valid"]:
                    expected_active_id = str(active_publication["publication_id"])
                    guarded_state = storage.get_agentic_ready_publication_state(
                        kb_id=kid,
                        profile=profile,
                    )
                    guarded_active = guarded_state.get("active_publication")
                    if (
                        guarded_state["active_publication_id"] == expected_active_id
                        and guarded_active
                    ):
                        guarded_validation = _validate_recorded_ready_publication(
                            guarded_active,
                            validator=ready_data_builder.validate,
                            allowed_output_root=allowed_output_root,
                        )
                        confirmed_state = storage.get_agentic_ready_publication_state(
                            kb_id=kid,
                            profile=profile,
                        )
                        if confirmed_state["active_publication_id"] == expected_active_id:
                            current_publication_state = confirmed_state
                            active_publication = guarded_active
                            active_validation = guarded_validation
                        else:
                            publication_state = confirmed_state
                    else:
                        publication_state = guarded_state

                    if publication_state and not publication_state.get("idempotent"):
                        publication_state["idempotent"] = False
                        publication_state["cas_won"] = False
                        publication_state["cas_lost"] = True

                if not publication_state:
                    same_active_identity = bool(
                        active_publication
                        and _same_ready_publication_identity(
                            active_publication,
                            candidate_publication,
                        )
                    )
                    if (
                        same_active_identity
                        and active_validation
                        and active_validation["valid"]
                    ):
                        duplicate_gc_marked = (
                            storage.mark_agentic_ready_publication_redundant_duplicate(
                                recorded_publication_id,
                                expected_active_publication_id=str(
                                    active_publication["publication_id"]
                                ),
                            )
                        )
                        publication_state = current_publication_state
                        publication_state["idempotent"] = True
                        publication_state["cas_won"] = True
                        publication_state["duplicate_retained"] = True
                        publication_state["duplicate_gc_deferred"] = True
                        publication_state["duplicate_gc_marked"] = duplicate_gc_marked
                        publication_state["duplicate_retained_reason"] = (
                            "governed garbage collection is deferred before automatic publication"
                            if duplicate_gc_marked
                            else "slot state changed before the duplicate could be classified; "
                            "candidate remains retryable"
                        )
                        # Automatic deletion cannot be made atomic with filesystem
                        # validation. Keep the candidate until a future governed GC pass.
                        _append_validation_warning(
                            validation,
                            "validated duplicate retained; governed garbage collection is deferred "
                            "before automatic publication"
                            if duplicate_gc_marked
                            else "validated duplicate retained as retryable because its garbage-collection "
                            "classification lost the slot guard",
                        )

                if not publication_state:
                    corrupt_active = bool(active_validation and not active_validation["valid"])
                    corrupt_error = ""
                    if corrupt_active:
                        corrupt_error = "; ".join(active_validation["errors"])
                    publication_state = storage.publish_agentic_ready_publication(
                        recorded_publication_id,
                        expected_active_publication_id=current_publication_state[
                            "active_publication_id"
                        ],
                        preserve_expected_active_as_previous=not corrupt_active,
                        invalidated_expected_active_error=corrupt_error,
                    )
                    if corrupt_active:
                        if publication_state["cas_won"]:
                            _append_validation_warning(
                                validation,
                                f"replaced invalid active ready_data: {corrupt_error}",
                            )
                        else:
                            publication_state["cas_lost"] = True
                            _append_validation_warning(
                                validation,
                                "detected invalid active ready_data but replacement "
                                f"lost publication CAS: {corrupt_error}",
                            )
                    candidate_publication = (
                        storage.get_agentic_ready_publication(recorded_publication_id)
                        or candidate_publication
                    )
        except Exception as exc:  # noqa: BLE001
            validation = {"valid": False, "errors": [str(exc)], "warnings": []}
            if validated_attempt_recorded:
                candidate_publication = (
                    storage.get_agentic_ready_publication(
                        str(candidate_publication["publication_id"])
                    )
                    or candidate_publication
                )
            else:
                if not artifact_digest:
                    try:
                        artifact_digest, artifact_files = _staging_tree_digest(
                            candidate_output_dir,
                            staging_root=staging_root,
                            allowed_output_root=allowed_output_root,
                        )
                    except Exception as digest_exc:  # noqa: BLE001
                        artifact_digest = hashlib.sha256(b"").hexdigest()
                        artifact_files = []
                        _append_validation_warning(validation, f"staging digest failed: {digest_exc}")
                candidate_publication = storage.record_agentic_ready_publication(
                    kb_id=kid,
                    index_version_id=observed_index_version_id,
                    source_version_kind=source_version_kind,
                    source_version_id=source_version_id,
                    profile=profile,
                    profile_version=profile_def.version,
                    status="failed",
                    output_dir="",
                    artifact_files=artifact_files,
                    doc_count=int(builder_manifest.get("doc_count") or 0),
                    section_count=int(builder_manifest.get("section_count") or 0),
                    built_at=builder_manifest.get("built_at"),
                    artifact_digest=artifact_digest,
                    source_db=str(builder_manifest.get("source_db") or db_path),
                    schema_versions=dict(builder_manifest.get("schema_versions") or {}),
                    smoke_result=smoke_result,
                    error_message=str(exc),
                )
                cleanup_warning = _best_effort_staging_cleanup(
                    storage,
                    output_dir=candidate_output_dir,
                    staging_root=staging_root,
                    allowed_output_root=allowed_output_root,
                )
                if cleanup_warning:
                    _append_validation_warning(validation, cleanup_warning)
        if not publication_state:
            publication_state = storage.get_agentic_ready_publication_state(
                kb_id=kid,
                profile=profile,
            )
        active_publication = publication_state.get("active_publication")
        active_matches_builder = bool(
            active_publication
            and validation.get("valid")
            and str(active_publication.get("source_version_kind") or "")
            == source_version_kind
            and str(active_publication.get("source_version_id") or "")
            == source_version_id
        )
        if captured_evaluation_generation is not None and active_matches_builder:
            try:
                storage.record_agentic_ready_source_evaluation(
                    kb_id=kid,
                    profile=profile,
                    evaluated_generation=int(captured_evaluation_generation),
                    source_version_kind=source_version_kind,
                    source_version_id=source_version_id,
                )
            except ValueError as exc:
                if str(exc) != "evaluation must target the latest event generation":
                    raise
        from .ready_data_publication import read_public_ready_data_snapshot

        ready_data_snapshot = read_public_ready_data_snapshot(
            storage,
            kb_id=kid,
            profile=profile,
            include_legacy_output_dir=False,
        )
        return {
            "kb_id": kid,
            "manifest": _build_agentic_manifest_status(storage=storage, kb_id=kid, profile=profile),
            "candidate_publication": candidate_publication,
            "publication_state": publication_state,
            "ready_data_snapshot": ready_data_snapshot,
            "validation": validation,
        }
    finally:
        storage.close()


def _parse_ready_data_gc_cutoff(value: str | None) -> tuple[datetime, str]:
    raw = str(value or "").strip()
    if not raw:
        cutoff = datetime.now(timezone.utc)
    else:
        try:
            cutoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("ready-data GC cutoff must be an ISO-8601 timestamp") from exc
        if cutoff.tzinfo is None:
            raise ValueError("ready-data GC cutoff must include a timezone")
        cutoff = cutoff.astimezone(timezone.utc)
    return cutoff, cutoff.isoformat()


def _ready_data_gc_tree_is_safe(path: Path) -> None:
    if _is_link_or_reparse(path):
        raise ValueError("ready_data GC path is a link or reparse point")
    if not path.is_dir():
        raise ValueError("ready_data GC path is not a directory")
    def raise_walk_error(error: OSError) -> None:
        raise error

    for directory, dirnames, filenames in os.walk(
        path,
        topdown=True,
        onerror=raise_walk_error,
        followlinks=False,
    ):
        directory_path = Path(directory)
        if _is_link_or_reparse(directory_path):
            raise ValueError("ready_data GC tree contains a link or reparse point")
        for name in [*dirnames, *filenames]:
            entry = directory_path / name
            if _is_link_or_reparse(entry):
                raise ValueError("ready_data GC tree contains a link or reparse point")


def _ready_data_gc_paths(
    *,
    publication_id: str,
    output_dir: str,
    recorded_quarantine_dir: str,
    allowed_output_root: str,
) -> tuple[Path, Path]:
    allowed_root = Path(os.path.abspath(allowed_output_root))
    if _is_link_or_reparse(allowed_root) or not allowed_root.is_dir():
        raise ValueError("allowed ready_data root is missing, linked, or a reparse point")
    output_path = Path(os.path.abspath(output_dir))
    try:
        relative_output = output_path.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("ready_data GC output escaped the allowed root") from exc
    if output_path.name.startswith("build-") is False or output_path.parent.name != "staging":
        raise ValueError("ready_data GC only accepts staging build attempts")
    if _is_link_or_reparse(output_path):
        raise ValueError("ready_data GC attempt is a link or reparse point")

    cursor = allowed_root
    for part in relative_output.parts[:-1]:
        cursor /= part
        if _is_link_or_reparse(cursor):
            raise ValueError("ready_data GC ancestor is a link or reparse point")
        if not cursor.is_dir():
            raise ValueError("ready_data GC staging ancestor is missing")
    resolved_root = allowed_root.resolve(strict=True)
    resolved_parent = output_path.parent.resolve(strict=True)
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("ready_data GC staging root escaped the allowed root") from exc

    quarantine_name = f".gc-quarantine-{publication_id}"
    quarantine_path = output_path.parent / quarantine_name
    if quarantine_path.parent != output_path.parent or quarantine_path.name != quarantine_name:
        raise ValueError("ready_data GC publication ID produced an unsafe quarantine path")
    if _is_link_or_reparse(quarantine_path):
        raise ValueError("ready_data GC quarantine is a link or reparse point")
    if recorded_quarantine_dir:
        recorded_path = Path(os.path.abspath(recorded_quarantine_dir))
        if os.path.normcase(str(recorded_path)) != os.path.normcase(str(quarantine_path)):
            raise ValueError("recorded ready_data GC quarantine path does not match policy")
    if output_path.exists() and quarantine_path.exists():
        raise ValueError("both ready_data attempt and quarantine paths exist")
    if output_path.exists():
        _ready_data_gc_tree_is_safe(output_path)
        if output_path.resolve(strict=True).parent != resolved_parent:
            raise ValueError("ready_data GC attempt escaped its staging root")
    if quarantine_path.exists():
        _ready_data_gc_tree_is_safe(quarantine_path)
        if quarantine_path.resolve(strict=True).parent != resolved_parent:
            raise ValueError("ready_data GC quarantine escaped its staging root")
    return output_path, quarantine_path


def _ready_data_gc_item(publication: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "publication_id": str(publication["publication_id"]),
        "kb_id": str(publication["kb_id"]),
        "profile": str(publication["profile"]),
        "status": str(publication["status"]),
        "attempt_disposition": str(publication.get("attempt_disposition") or ""),
        "retention_class": str(publication.get("retention_class") or ""),
        "gc_state": str(publication.get("gc_state") or ""),
        "marked_at": publication.get("gc_marked_at"),
        "output_dir": str(publication.get("output_dir") or ""),
        "quarantine_dir": str(publication.get("gc_quarantine_dir") or ""),
        "claim_token": str(publication.get("gc_claim_token") or ""),
        "lease_expires_at": publication.get("gc_lease_expires_at"),
        "reason": reason,
    }


def _ready_data_gc_fingerprint_payload(
    *,
    publications: list[dict[str, Any]],
    slots: list[dict[str, Any]],
    retained: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    cutoff_at: str,
    policy_version: str,
) -> dict[str, Any]:
    return {
        "policy": {
            "version": policy_version,
            "minimum_age_days": READY_DATA_GC_MINIMUM_AGE_DAYS,
            "keep_latest": READY_DATA_GC_KEEP_LATEST,
            "claim_lease_seconds": READY_DATA_GC_CLAIM_LEASE_SECONDS,
        },
        "cutoff_at": cutoff_at,
        "publications": [
            {
                "publication_id": item["publication_id"],
                "kb_id": item["kb_id"],
                "profile": item["profile"],
                "status": item["status"],
                "attempt_disposition": item["attempt_disposition"],
                "source_version_kind": item["source_version_kind"],
                "output_dir": item["output_dir"],
                "retention_class": item["retention_class"],
                "gc_state": item["gc_state"],
                "gc_marked_at": item["gc_marked_at"],
                "gc_quarantine_dir": item["gc_quarantine_dir"],
                "gc_claim_token": item["gc_claim_token"],
                "gc_lease_expires_at": item["gc_lease_expires_at"],
                "gc_updated_at": item["gc_updated_at"],
            }
            for item in publications
        ],
        "slots": slots,
        "plan_membership": {
            "retained": retained,
            "candidates": candidates,
            "skipped": skipped,
        },
    }


def _build_ready_data_publication_gc_plan(
    storage: Storage,
    *,
    cutoff_at: str | None,
    policy_version: str,
) -> dict[str, Any]:
    cutoff, canonical_cutoff = _parse_ready_data_gc_cutoff(cutoff_at)
    minimum_marked_at = cutoff - timedelta(days=READY_DATA_GC_MINIMUM_AGE_DAYS)
    publications = storage.list_agentic_ready_publications_for_gc()
    slots = storage.list_agentic_ready_slots_for_gc()
    active_ids = {str(item["active_publication_id"]) for item in slots if item["active_publication_id"]}
    previous_ids = {
        str(item["previous_publication_id"]) for item in slots if item["previous_publication_id"]
    }
    serving_path_keys: set[str] = set()
    for publication in publications:
        if str(publication["publication_id"]) in active_ids | previous_ids:
            serving_path_keys.update(
                Storage._agentic_ready_path_keys(str(publication["output_dir"]))
            )
    for row in storage._conn.execute(
        "SELECT output_dir FROM agentic_ready_manifests WHERE output_dir <> ''"
    ).fetchall():
        serving_path_keys.update(Storage._agentic_ready_path_keys(str(row[0])))

    marked_times: dict[str, datetime] = {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for publication in publications:
        if (
            publication["attempt_disposition"]
            or publication["retention_class"] != "redundant_duplicate"
            or publication["gc_state"] not in {"eligible", "claimed", "delete_failed"}
        ):
            continue
        parsed = Storage._parse_iso_to_utc(publication["gc_marked_at"])
        if parsed is None:
            continue
        publication_id = str(publication["publication_id"])
        marked_times[publication_id] = parsed
        grouped.setdefault(
            (str(publication["kb_id"]), str(publication["profile"])), []
        ).append(publication)
    newest_ids: set[str] = set()
    for attempts in grouped.values():
        attempts.sort(
            key=lambda item: (
                marked_times[str(item["publication_id"])],
                str(item["publication_id"]),
            ),
            reverse=True,
        )
        newest_ids.update(
            str(item["publication_id"]) for item in attempts[:READY_DATA_GC_KEEP_LATEST]
        )

    retained: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for publication in publications:
        publication_id = str(publication["publication_id"])
        if publication_id in active_ids:
            retained.append(_ready_data_gc_item(publication, reason="active_slot"))
            continue
        if publication_id in previous_ids:
            retained.append(_ready_data_gc_item(publication, reason="previous_slot"))
            continue
        if str(publication["source_version_kind"]).startswith("legacy"):
            retained.append(_ready_data_gc_item(publication, reason="legacy_publication"))
            continue
        if publication["attempt_disposition"]:
            retained.append(
                _ready_data_gc_item(
                    publication,
                    reason=f"attempt_disposition_{publication['attempt_disposition']}",
                )
            )
            continue
        if not publication["retention_class"]:
            reason = (
                "retryable_validated_candidate"
                if publication["status"] == "validated"
                else "unknown_historical_attempt"
            )
            retained.append(_ready_data_gc_item(publication, reason=reason))
            continue
        if publication["retention_class"] != "redundant_duplicate":
            retained.append(_ready_data_gc_item(publication, reason="unknown_retention_class"))
            continue
        if publication["gc_state"] == "deleted":
            retained.append(_ready_data_gc_item(publication, reason="gc_tombstone"))
            continue
        if publication["status"] != "validated" or publication["gc_state"] not in {
            "eligible",
            "claimed",
            "delete_failed",
        }:
            skipped.append(_ready_data_gc_item(publication, reason="invalid_gc_state"))
            continue
        publication_path_keys = Storage._agentic_ready_path_keys(
            str(publication["output_dir"])
        )
        if Storage._agentic_ready_path_key_sets_overlap(
            serving_path_keys,
            publication_path_keys,
        ):
            retained.append(_ready_data_gc_item(publication, reason="serving_output_path"))
            continue
        if storage._agentic_ready_paths_conflict(
            publication_id,
            str(publication["output_dir"]),
        ):
            retained.append(_ready_data_gc_item(publication, reason="reserved_output_path"))
            continue
        marked_at = marked_times.get(publication_id)
        if marked_at is None:
            skipped.append(_ready_data_gc_item(publication, reason="invalid_marked_at"))
            continue
        recovering = publication["gc_state"] in {"claimed", "delete_failed"}
        if publication["gc_state"] == "claimed":
            lease_expires_at = Storage._parse_iso_to_utc(
                publication["gc_lease_expires_at"]
            )
            if lease_expires_at is None:
                skipped.append(_ready_data_gc_item(publication, reason="invalid_claim_lease"))
                continue
            if lease_expires_at > cutoff:
                skipped.append(_ready_data_gc_item(publication, reason="claim_in_progress"))
                continue
        if not recovering and publication_id in newest_ids:
            retained.append(_ready_data_gc_item(publication, reason="newest_two"))
            continue
        if not recovering and marked_at > minimum_marked_at:
            retained.append(_ready_data_gc_item(publication, reason="minimum_age_not_met"))
            continue
        try:
            output_path, quarantine_path = _ready_data_gc_paths(
                publication_id=publication_id,
                output_dir=str(publication["output_dir"]),
                recorded_quarantine_dir=str(publication["gc_quarantine_dir"]),
                allowed_output_root=str(
                    Path(storage.db_path).resolve().parent / "agentic_ready_data"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            item = _ready_data_gc_item(publication, reason="unsafe_path")
            item["detail"] = str(exc)
            skipped.append(item)
            continue
        if storage._agentic_ready_paths_conflict(
            publication_id,
            str(output_path),
            str(quarantine_path),
        ):
            retained.append(_ready_data_gc_item(publication, reason="reserved_output_path"))
            continue
        item = _ready_data_gc_item(publication, reason="retention_boundary_exceeded")
        item["output_dir"] = str(output_path)
        item["quarantine_dir"] = str(quarantine_path)
        candidates.append(item)

    for bucket in (retained, candidates, skipped):
        bucket.sort(key=lambda item: (item["kb_id"], item["profile"], item["publication_id"]))
    fingerprint_payload = _ready_data_gc_fingerprint_payload(
        publications=publications,
        slots=slots,
        retained=retained,
        candidates=candidates,
        skipped=skipped,
        cutoff_at=canonical_cutoff,
        policy_version=policy_version,
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "mode": "dry_run",
        "policy": fingerprint_payload["policy"],
        "cutoff_at": canonical_cutoff,
        "plan_fingerprint": fingerprint,
        "retained": retained,
        "candidates": candidates,
        "deleted": [],
        "skipped": skipped,
        "failures": [],
    }


def plan_ready_data_publication_gc(
    *,
    db_path: str,
    cutoff_at: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic, zero-mutation ready-data retention plan."""
    storage = Storage.open_read_only(db_path)
    try:
        plan = _build_ready_data_publication_gc_plan(
            storage,
            cutoff_at=cutoff_at,
            policy_version=READY_DATA_GC_POLICY_VERSION,
        )
        storage.assert_read_only_snapshot_unchanged()
        return plan
    finally:
        storage.close()


def execute_ready_data_publication_gc(
    *,
    db_path: str,
    cutoff_at: str,
    plan_fingerprint: str,
    policy_version: str = READY_DATA_GC_POLICY_VERSION,
) -> dict[str, Any]:
    """Explicitly execute one exact dry-run plan with per-attempt CAS claims."""
    if policy_version != READY_DATA_GC_POLICY_VERSION:
        raise ValueError("ready-data GC policy version does not match the running code")
    if not str(plan_fingerprint or "").strip():
        raise ValueError("ready-data GC plan fingerprint is required")
    storage = Storage(db_path)
    try:
        with storage.transaction(immediate=True):
            current_plan = _build_ready_data_publication_gc_plan(
                storage,
                cutoff_at=cutoff_at,
                policy_version=policy_version,
            )
            if current_plan["plan_fingerprint"] != plan_fingerprint:
                raise ValueError("ready-data GC plan fingerprint no longer matches current state")
            result = {
                **current_plan,
                "mode": "execute",
                "deleted": [],
                "skipped": list(current_plan["skipped"]),
                "failures": [],
            }
            for candidate in current_plan["candidates"]:
                publication_id = str(candidate["publication_id"])
                claim = storage.claim_agentic_ready_publication_gc(
                    publication_id,
                    expected_gc_state=str(candidate["gc_state"]),
                    expected_marked_at=str(candidate["marked_at"]),
                    quarantine_dir=str(candidate["quarantine_dir"]),
                    cutoff_at=str(current_plan["cutoff_at"]),
                    minimum_age_days=READY_DATA_GC_MINIMUM_AGE_DAYS,
                    keep_latest=READY_DATA_GC_KEEP_LATEST,
                    claim_lease_seconds=READY_DATA_GC_CLAIM_LEASE_SECONDS,
                    expected_claim_token=str(candidate["claim_token"]),
                )
                if claim is None:
                    item = dict(candidate)
                    item["reason"] = "claim_lost"
                    result["skipped"].append(item)
                    continue
                claim_token = str(claim["gc_claim_token"])
                try:
                    output_path, quarantine_path = _ready_data_gc_paths(
                        publication_id=publication_id,
                        output_dir=str(claim["output_dir"]),
                        recorded_quarantine_dir=str(claim["gc_quarantine_dir"]),
                        allowed_output_root=str(
                            Path(db_path).resolve().parent / "agentic_ready_data"
                        ),
                    )
                    if output_path.exists():
                        _ready_data_gc_tree_is_safe(output_path)
                        os.replace(output_path, quarantine_path)
                    if quarantine_path.exists():
                        _ready_data_gc_tree_is_safe(quarantine_path)
                        shutil.rmtree(quarantine_path)
                    finalized = storage.finish_agentic_ready_publication_gc(
                        publication_id,
                        claim_token=claim_token,
                        deleted=True,
                    )
                    if not finalized or finalized["gc_state"] != "deleted":
                        raise RuntimeError("ready-data GC tombstone finalization lost its claim")
                    item = dict(candidate)
                    item["reason"] = "deleted"
                    result["deleted"].append(item)
                except Exception as exc:  # noqa: BLE001
                    storage.finish_agentic_ready_publication_gc(
                        publication_id,
                        claim_token=claim_token,
                        deleted=False,
                        error_message=str(exc),
                    )
                    item = dict(candidate)
                    item["reason"] = "delete_failed"
                    item["detail"] = str(exc)
                    result["failures"].append(item)
            for bucket_name in ("deleted", "skipped", "failures"):
                result[bucket_name].sort(
                    key=lambda item: (item["kb_id"], item["profile"], item["publication_id"])
                )
            return result
    finally:
        storage.close()


def update_knowledge_base(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    name = _norm(payload["name"]) if "name" in payload else None
    description = _norm(payload["description"]) if "description" in payload else None
    manifest_profile = _manifest_profile(payload["manifest_profile"]) if "manifest_profile" in payload else None
    if name is None and description is None and manifest_profile is None:
        raise RagAdminError("No valid update fields provided (name, description, manifest_profile)")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        manager.update_kb(kid, name=name, description=description, manifest_profile=manifest_profile)
        updated_payload = _decorate_kb_agentic_manifest(
            storage,
            _decorate_kb_chunk_profile(storage, _serialize_kb(manager.get_kb(kid))),
        )
        return {"knowledge_base": updated_payload}
    finally:
        storage.close()



def delete_knowledge_base(*, db_path: str, kb_id: str, headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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



def add_knowledge_base_files(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    file_urls = _list(payload.get("file_urls"), "file_urls")
    if not file_urls:
        raise RagAdminError("file_urls must be a non-empty list")

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        chunk_profile_id = _norm(payload.get("chunk_profile_id") or payload.get("profile_id") or getattr(kb, "chunk_profile_id", ""))
        if chunk_profile_id:
            if not storage.get_chunk_profile(chunk_profile_id):
                raise RagAdminError("chunk profile not found", status_code=404)
            result, binding_result = _add_and_bind_existing_profile_chunks(
                manager,
                storage,
                kb_id=kid,
                file_urls=file_urls,
                profile_id=chunk_profile_id,
                bound_by="kb_add_files",
            )
            return {
                "kb_id": kid,
                "added_count": int(result.get("added_count") or 0),
                "skipped_count": int(result.get("skipped_count") or 0) + int(binding_result.get("skipped_without_chunks") or 0),
                "total_files": int(result.get("total_files") or manager.get_kb_stats(kid).get("total_files") or 0),
                "chunk_bindings": binding_result,
            }
        result = manager.add_files_to_kb(kid, file_urls)
        return {
            "kb_id": kid,
            "added_count": int(result.get("added_count") or 0),
            "skipped_count": int(result.get("skipped_count") or 0),
            "total_files": int(result.get("total_files") or 0),
        }
    finally:
        storage.close()



def remove_knowledge_base_file(*, db_path: str, kb_id: str, file_url: str, headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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
    profile_id = _norm(query.get("profile_id") or query.get("chunk_profile_id"))
    kb_id_raw = _norm(query.get("kb_id"))
    kb_id = _kb_id(kb_id_raw) if kb_id_raw else ""
    limit = parse_int_clamped(query.get("limit") or 100, default=100, min_value=1, max_value=500)
    offset = parse_int_clamped(query.get("offset") or 0, default=0, min_value=0, max_value=1_000_000)

    storage = Storage(db_path)
    try:
        if profile_id and not storage.get_chunk_profile(profile_id):
            raise RagAdminError("chunk profile not found", status_code=404)
        conn = storage._conn
        chunk_join_sql = ""
        chunk_join_params: list[Any] = []
        chunk_columns = """
            NULL AS chunk_set_id,
            NULL AS chunk_profile_id,
            NULL AS chunk_profile_name,
            NULL AS chunk_count
        """
        if profile_id:
            chunk_join_sql = """
            JOIN (
                SELECT chunk_set_id, file_url, profile_id, profile_name, chunk_count
                FROM (
                    SELECT
                        s.chunk_set_id,
                        s.file_url,
                        s.profile_id,
                        p.name AS profile_name,
                        s.chunk_count,
                        ROW_NUMBER() OVER (
                            PARTITION BY s.file_url, s.profile_id
                            ORDER BY s.updated_at DESC, s.created_at DESC, s.chunk_set_id DESC
                        ) AS rn
                    FROM file_chunk_sets s
                    JOIN chunk_profiles p ON p.profile_id = s.profile_id
                    WHERE s.profile_id = ?
                      AND s.status = 'ready'
                      AND COALESCE(s.chunk_count, 0) > 0
                )
                WHERE rn = 1
            ) latest_chunk ON latest_chunk.file_url = f.url
            """
            chunk_join_params.append(profile_id)
            chunk_columns = """
                latest_chunk.chunk_set_id,
                latest_chunk.profile_id AS chunk_profile_id,
                latest_chunk.profile_name AS chunk_profile_name,
                latest_chunk.chunk_count
            """

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
                f"""
                SELECT COUNT(*)
                FROM files f
                JOIN catalog_items c ON c.file_url = f.url
                {chunk_join_sql}
                WHERE {where_sql}
                """,
                chunk_join_params + params,
            ).fetchone()[0]
            or 0
        )
        rows = conn.execute(
            f"""
            SELECT
                f.url,
                f.title,
                f.original_filename,
                f.source_site,
                f.bytes,
                f.last_seen,
                c.category,
                c.markdown_updated_at,
                {chunk_columns}
            FROM files f
            JOIN catalog_items c ON c.file_url = f.url
            {chunk_join_sql}
            WHERE {where_sql}
            ORDER BY f.last_seen DESC, f.id DESC
            LIMIT ? OFFSET ?
            """,
            chunk_join_params + params + [limit, offset],
        ).fetchall()
        files = []
        for row in rows:
            item = {
                "url": row[0],
                "title": row[1] or "",
                "original_filename": row[2] or "",
                "source_site": row[3] or "",
                "bytes": row[4] or 0,
                "last_seen": row[5],
                "category": row[6] or "",
                "markdown_updated_at": row[7],
            }
            if row[8]:
                item.update(
                    {
                        "chunk_set_id": row[8],
                        "chunk_profile_id": row[9],
                        "chunk_profile_name": row[10] or "",
                        "chunk_count": row[11] or 0,
                    }
                )
            files.append(item)
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



def set_knowledge_base_categories(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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
        kb = manager.get_kb(kid)
        if not kb:
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        before_n = int(manager.get_kb_stats(kid).get("total_files", 0))
        manager._ensure_category_mapping_table()
        conn = storage._conn
        timestamp = _KnowledgeBase._get_timestamp()
        chunk_profile_id = _norm(payload.get("chunk_profile_id") or payload.get("profile_id") or getattr(kb, "chunk_profile_id", ""))

        if action == "add":
            manager.link_kb_to_categories(kid, categories, auto_sync=not bool(chunk_profile_id))
            binding_result = None
            sync_result = None
            if chunk_profile_id:
                if not storage.get_chunk_profile(chunk_profile_id):
                    raise RagAdminError("chunk profile not found", status_code=404)
                sync_result, binding_result = _sync_category_kb_files(
                    manager,
                    storage,
                    kb_id=kid,
                    categories=categories,
                    profile_id=chunk_profile_id,
                    bound_by="kb_category_add",
                )
            after_n = int(manager.get_kb_stats(kid).get("total_files", 0))
            response = {"kb_id": kid, "action": action, "linked_count": len(categories), "files_added": max(0, after_n - before_n)}
            if sync_result is not None:
                response["category_sync"] = sync_result
            if binding_result is not None:
                response["chunk_bindings"] = binding_result
            return response

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
        manager.link_kb_to_categories(kid, categories, auto_sync=not bool(chunk_profile_id))
        binding_result = None
        sync_result = None
        if chunk_profile_id:
            if not storage.get_chunk_profile(chunk_profile_id):
                raise RagAdminError("chunk profile not found", status_code=404)
            sync_result, binding_result = _sync_category_kb_files(
                manager,
                storage,
                kb_id=kid,
                categories=categories,
                profile_id=chunk_profile_id,
                bound_by="kb_category_replace",
            )
        after_n = int(manager.get_kb_stats(kid).get("total_files", 0))
        response = {"kb_id": kid, "action": action, "linked_count": len(categories), "files_added": max(0, after_n - before_n), "categories": manager.get_kb_categories(kid)}
        if sync_result is not None:
            response["category_sync"] = sync_result
        if binding_result is not None:
            response["chunk_bindings"] = binding_result
        return response
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



def bind_chunk_sets(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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
        unique_file_urls = []
        for file_url, _chunk_set_id, _binding_mode in parsed:
            if file_url not in unique_file_urls:
                unique_file_urls.append(file_url)
        if unique_file_urls:
            manager.add_files_to_kb(kid, unique_file_urls)
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



def create_index_task(*, db_path: str, kb_id: str, payload: dict[str, Any], headers: Mapping[str, str], bridge_state: Any, auth: Any | None = None) -> tuple[dict[str, Any], int]:
    _require_config_write_token(headers, auth)
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
        category_sync_result = None
        all_sync_result = None
        chunk_binding_result = None
        kb_mode = getattr(kb, "kb_mode", "")
        if kb_mode == "category":
            categories = manager.get_kb_categories(kid)
            profile_id = _norm(getattr(kb, "chunk_profile_id", ""))
            if categories:
                category_sync_result, chunk_binding_result = _sync_category_kb_files(
                    manager,
                    storage,
                    kb_id=kid,
                    categories=categories,
                    profile_id=profile_id,
                    bound_by="kb_index_category_sync",
                )
        elif kb_mode == "all":
            profile_id = _norm(getattr(kb, "chunk_profile_id", ""))
            all_sync_result, chunk_binding_result = _sync_all_kb_files(
                manager,
                storage,
                kb_id=kid,
                profile_id=profile_id,
                bound_by="kb_index_all_sync",
            )
        if not force_reindex:
            embedding_status = _build_kb_embedding_status(
                storage=storage,
                kb_payload=_decorate_kb_chunk_profile(storage, _serialize_kb(kb)),
            )
            if embedding_status.get("index_status") and not embedding_status.get("embedding_compatible"):
                raise RagAdminError(
                    "Embedding configuration changed; full re-embed is required before incremental indexing",
                    status_code=409,
                )
        user_requested = bool(requested)
        files_to_index = requested
        if not files_to_index:
            if force_reindex or not incremental:
                files_to_index = [row.get("file_url") for row in manager.get_kb_files(kid)]
                files_to_index = [url for url in files_to_index if url]
            else:
                files_to_index = manager.get_files_needing_index(kid)
        if not files_to_index and not force_reindex:
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

        response = {
            "job_id": task_id,
            "kb_id": kid,
            "file_count": len(files_to_index),
            "skipped_no_markdown": skipped_no_markdown,
            "force_reindex": force_reindex,
            "incremental": incremental,
        }
        if category_sync_result is not None:
            response["category_sync"] = category_sync_result
        if all_sync_result is not None:
            response["all_sync"] = all_sync_result
        if chunk_binding_result is not None:
            response["chunk_bindings"] = chunk_binding_result
        return response, 202
    finally:
        storage.close()



def cleanup_chunk_sets(*, db_path: str, payload: dict[str, Any], headers: Mapping[str, str], auth: Any | None = None) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
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

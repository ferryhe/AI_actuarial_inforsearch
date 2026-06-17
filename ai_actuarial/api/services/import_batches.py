from __future__ import annotations

import hashlib
import json
import os
import posixpath
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import UploadFile

ALLOWED_EXTENSIONS = {
    "csv",
    "doc",
    "docx",
    "epub",
    "html",
    "htm",
    "md",
    "pdf",
    "ppt",
    "pptx",
    "rtf",
    "txt",
    "xls",
    "xlsx",
}
MAX_FILES_PER_BATCH = 100
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BATCH_BYTES = 250 * 1024 * 1024
MAX_RELATIVE_PATH_LENGTH = 240
MAX_RELATIVE_PATH_DEPTH = 12


class ImportBatchError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _load_config_paths() -> dict[str, Any]:
    config_path = os.getenv("CONFIG_PATH") or "config/sites.yaml"
    try:
        data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        data = {}
    return dict(data.get("paths") or {})


def import_batch_root() -> Path:
    env_root = os.getenv("IMPORT_BATCH_ROOT", "").strip()
    if env_root:
        root = Path(env_root)
    else:
        paths = _load_config_paths()
        download_dir = Path(str(paths.get("download_dir") or "data/files"))
        base_dir = download_dir.parent if download_dir.name else download_dir
        root = base_dir / "import_batches"
    return root.expanduser().resolve()


def _safe_relative_path(raw_path: str, fallback_name: str) -> str:
    raw = (raw_path or fallback_name or "uploaded-file").replace("\\", "/").strip()
    if raw in {"", "."} or raw.startswith("/") or raw.startswith("../") or raw == ".." or "/../" in raw:
        raise ImportBatchError("Invalid relative path")
    raw = posixpath.normpath(raw)
    if raw in {"", "."} or raw.startswith("/") or raw.startswith("../") or raw == ".." or "/../" in raw:
        raise ImportBatchError("Invalid relative path")
    parts = [part for part in raw.split("/") if part]
    if not parts or len(parts) > MAX_RELATIVE_PATH_DEPTH:
        raise ImportBatchError("Invalid relative path")
    for part in parts:
        if part in {".", ".."} or "\x00" in part:
            raise ImportBatchError("Invalid relative path")
    normalized = "/".join(parts)
    if len(normalized) > MAX_RELATIVE_PATH_LENGTH:
        raise ImportBatchError("Relative path is too long")
    suffix = Path(parts[-1]).suffix.lower().lstrip(".")
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise ImportBatchError("Unsupported file type")
    return normalized


def _auth_subject(auth_token: dict[str, Any] | None) -> str:
    if not auth_token:
        return "anonymous"
    user_id = auth_token.get("_email_user_id")
    if user_id is not None:
        return f"user:{user_id}"
    token_id = auth_token.get("id")
    if token_id is not None:
        return f"token:{token_id}"
    return str(auth_token.get("subject") or "unknown")


def _manifest_path(batch_id: str) -> Path:
    return import_batch_root() / batch_id / "manifest.json"


def _write_manifest(batch_dir: Path, manifest: dict[str, Any]) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _response_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    public_files = []
    for item in manifest.get("files") or []:
        public_files.append(
            {
                "original_name": item.get("original_name"),
                "relative_path": item.get("relative_path"),
                "size": item.get("size"),
                "content_type": item.get("content_type"),
                "sha256": item.get("sha256"),
            }
        )
    return {
        "success": True,
        "upload_batch_id": manifest.get("upload_batch_id"),
        "status": manifest.get("status"),
        "created_at": manifest.get("created_at"),
        "file_count": manifest.get("file_count"),
        "total_bytes": manifest.get("total_bytes"),
        "files": public_files,
    }


async def create_import_batch(*, files: list[UploadFile], relative_paths: list[str], auth_token: dict[str, Any] | None) -> dict[str, Any]:
    if not files:
        raise ImportBatchError("No files uploaded")
    if len(files) > MAX_FILES_PER_BATCH:
        raise ImportBatchError("Too many files in one batch")

    root = import_batch_root()
    root.mkdir(parents=True, exist_ok=True)
    batch_id = uuid.uuid4().hex
    batch_dir = (root / batch_id).resolve()
    if not str(batch_dir).startswith(str(root) + os.sep):
        raise ImportBatchError("Invalid upload batch path")
    files_dir = batch_dir / "files"
    manifest_files: list[dict[str, Any]] = []
    seen_relative_paths: set[str] = set()
    total_bytes = 0

    try:
        files_dir.mkdir(parents=True, exist_ok=True)
        for index, upload in enumerate(files):
            raw_relative_path = relative_paths[index] if index < len(relative_paths) else ""
            relative_path = _safe_relative_path(raw_relative_path, upload.filename or f"file-{index}")
            if relative_path in seen_relative_paths:
                raise ImportBatchError("Duplicate relative path")
            seen_relative_paths.add(relative_path)

            stored_path = (files_dir / relative_path).resolve()
            if not str(stored_path).startswith(str(files_dir.resolve()) + os.sep):
                raise ImportBatchError("Invalid stored path")
            stored_path.parent.mkdir(parents=True, exist_ok=True)

            sha256 = hashlib.sha256()
            file_size = 0
            with stored_path.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    total_bytes += len(chunk)
                    if file_size > MAX_SINGLE_FILE_BYTES:
                        raise ImportBatchError("Uploaded file is too large")
                    if total_bytes > MAX_TOTAL_BATCH_BYTES:
                        raise ImportBatchError("Upload batch is too large")
                    sha256.update(chunk)
                    out.write(chunk)

            manifest_files.append(
                {
                    "stored_path": str(stored_path),
                    "original_name": upload.filename or Path(relative_path).name,
                    "relative_path": relative_path,
                    "size": file_size,
                    "content_type": upload.content_type or "application/octet-stream",
                    "sha256": sha256.hexdigest(),
                }
            )

        now = datetime.now(timezone.utc).isoformat()
        manifest = {
            "upload_batch_id": batch_id,
            "status": "ready",
            "uploaded_by": _auth_subject(auth_token),
            "created_at": now,
            "file_count": len(manifest_files),
            "total_bytes": total_bytes,
            "files": manifest_files,
        }
        _write_manifest(batch_dir, manifest)
        return _response_manifest(manifest)
    except Exception:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise


def load_import_batch(batch_id: str, *, auth_token: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_id = str(batch_id or "").strip()
    if not clean_id or any(ch not in "0123456789abcdef" for ch in clean_id.lower()) or len(clean_id) != 32:
        raise ImportBatchError("Invalid upload batch")
    path = _manifest_path(clean_id)
    if not path.exists():
        raise ImportBatchError("Upload batch not found", status_code=404)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "ready":
        raise ImportBatchError("Upload batch is not ready")
    if auth_token is not None and str(auth_token.get("group_name") or "").lower() != "admin":
        expected_owner = _auth_subject(auth_token)
        if manifest.get("uploaded_by") != expected_owner:
            raise ImportBatchError("Upload batch is not available to this user", status_code=403)
    root = import_batch_root()
    for item in manifest.get("files") or []:
        stored = Path(str(item.get("stored_path") or "")).resolve()
        if not str(stored).startswith(str(root) + os.sep) or not stored.is_file():
            raise ImportBatchError("Upload batch contains invalid files")
    return manifest


def file_paths_for_batch(batch_id: str) -> list[str]:
    manifest = load_import_batch(batch_id)
    return [str(item["stored_path"]) for item in manifest.get("files") or []]

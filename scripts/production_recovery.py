#!/usr/bin/env python3
"""Production backup, verification, restore-smoke, and release metadata helpers.

The tool deliberately operates on an explicit data directory. In production that
directory is the mountpoint returned by ``docker volume inspect`` for the Compose
``ai-data`` named volume; it is not the repository's ignored ``data/`` directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BACKUP_FORMAT_VERSION = 1
# ``files`` holds re-crawlable source documents (PDF/PPTX/DOCX); it is excluded
# from full snapshots. Its metadata lives in the ``files`` table and is still
# captured by the online database backup, so a restore reports missing file
# paths as an expected, re-crawlable omission rather than snapshot loss.
SNAPSHOT_DIRECTORIES = ("agentic_ready_data", "rag")
# Format-v1 snapshots included ``files``; keep those manifests verifiable so a
# still-retained recovery point can be restored after the exclusion.
VERIFIABLE_SNAPSHOT_DIRECTORIES = SNAPSHOT_DIRECTORIES + ("files",)
RESTORE_COUNT_TABLES = ("agentic_ready_manifests", "files", "rag_knowledge_bases")
OCI_LABELS = (
    "org.opencontainers.image.revision",
    "org.opencontainers.image.created",
    "org.opencontainers.image.source",
    "com.aiinforsearch.git-dirty",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def _require_directory(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_manifest_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not _is_within(candidate, root.resolve()):
        raise ValueError(f"Backup manifest path escapes snapshot: {relative!r}")
    return candidate


def _directory_stats(path: Path) -> dict[str, Any]:
    files = 0
    total_bytes = 0
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise ValueError(f"Snapshot directories must not contain symlinks: {candidate}")
        if candidate.is_file():
            files += 1
            size = candidate.stat().st_size
            total_bytes += size
            relative = candidate.relative_to(path).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(size).encode("ascii"))
            digest.update(b"\0")
            digest.update(_sha256(candidate).encode("ascii"))
            digest.update(b"\n")
    return {"files": files, "bytes": total_bytes, "sha256": digest.hexdigest()}


def _restored_file_path(data_root: Path, raw_path: Any) -> Path:
    candidate = Path(str(raw_path))
    if candidate.is_absolute():
        parts = candidate.parts
        if len(parts) >= 3 and tuple(part.lower() for part in parts[:3]) == ("/", "app", "data"):
            return data_root.joinpath(*parts[3:])
        return candidate
    parts = candidate.parts
    if parts and parts[0].lower() == "data":
        parts = parts[1:]
    return data_root.joinpath(*parts)


def _database_report(db_path: Path, *, include_counts: bool = False) -> dict[str, Any]:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        quick_rows = [str(row[0]) for row in conn.execute("PRAGMA quick_check")]
        quick_check = "ok" if quick_rows == ["ok"] else "; ".join(quick_rows)
        schema_user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        report: dict[str, Any] = {
            "quick_check": quick_check,
            "schema_user_version": schema_user_version,
        }
        if include_counts:
            existing = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            missing_tables = sorted(set(RESTORE_COUNT_TABLES) - existing)
            report["counts"] = {
                table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in RESTORE_COUNT_TABLES
                if table in existing
            }
            report["missing_tables"] = missing_tables
            missing_paths = 0
            if "files" in existing:
                rows = conn.execute(
                    "SELECT local_path FROM files WHERE local_path IS NOT NULL AND local_path != ''"
                )
                data_root = db_path.parent
                for (raw_path,) in rows:
                    candidate = _restored_file_path(data_root, raw_path)
                    if not candidate.exists():
                        missing_paths += 1
            report["missing_file_paths"] = missing_paths
        return report


def _online_sqlite_backup(source_path: Path, destination_path: Path) -> dict[str, int]:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path)) as source:
        checkpoint = source.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        with closing(sqlite3.connect(destination_path)) as destination:
            source.backup(destination)
    values = tuple(int(value) for value in (checkpoint or (0, 0, 0)))
    return {
        "busy": values[0],
        "wal_frames": values[1],
        "checkpointed_frames": values[2],
    }


def _next_backup_path(backup_root: Path, timestamp: str) -> Path:
    base = backup_root / f"backup-{timestamp}"
    candidate = base
    suffix = 1
    while candidate.exists() or candidate.with_name(f".{candidate.name}.tmp").exists():
        candidate = backup_root / f"{base.name}-{suffix}"
        suffix += 1
    return candidate


def create_backup(
    *,
    data_dir: Path,
    config_path: Path,
    backup_root: Path,
    include_data: bool = False,
    quiesced: bool = False,
    now: Callable[[], datetime] = _utc_now,
) -> Path:
    """Create an online DB backup or a quiesced DB+file snapshot.

    ``include_data`` requires an explicit acknowledgement that all application
    writers have been stopped. The function cannot infer that safely by looking
    at the filesystem alone.
    """

    started = now()
    timestamp = started.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = backup_root.expanduser().resolve()
    backup_root_existed = backup_root.exists()
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not backup_root_existed:
        backup_root.chmod(0o700)
    published = _next_backup_path(backup_root, timestamp)
    staging = published.with_name(f".{published.name}.tmp")
    event_path = backup_root / "backup-events.jsonl"
    event_base = {
        "backup_id": published.name,
        "started_at": _iso_utc(started),
        "scope": "database-and-data" if include_data else "database",
    }

    try:
        data_dir = _require_directory(data_dir, "data directory")
        if _is_within(backup_root, data_dir):
            raise ValueError("Backup root must be outside the application data directory")
        if include_data and not quiesced:
            raise ValueError("Full data snapshots require quiesced=True after stopping application writers")
        config_path = _require_file(config_path, "configuration file")
        db_path = _require_file(data_dir / "index.db", "SQLite database index.db")

        included_directories: list[str] = []
        source_stats: dict[str, dict[str, Any]] = {}
        if include_data:
            for name in SNAPSHOT_DIRECTORIES:
                source = _require_directory(data_dir / name, f"snapshot directory {name}")
                source_stats[name] = _directory_stats(source)

        staging.mkdir(mode=0o700)
        backup_db = staging / "database" / "index.db"
        checkpoint = _online_sqlite_backup(db_path, backup_db)
        database = _database_report(backup_db)
        if database["quick_check"] != "ok":
            raise RuntimeError(f"Backup database quick_check failed: {database['quick_check']}")
        database.update(
            {
                "path": "database/index.db",
                "bytes": backup_db.stat().st_size,
                "sha256": _sha256(backup_db),
                "wal_checkpoint": checkpoint,
            }
        )

        backup_config = staging / "config" / "sites.yaml"
        backup_config.parent.mkdir(parents=True, exist_ok=True)
        config_sha256_before = _sha256(config_path)
        shutil.copy2(config_path, backup_config)
        if _sha256(config_path) != config_sha256_before:
            raise RuntimeError("Configuration changed while the backup was being created")

        directory_stats: dict[str, dict[str, Any]] = {}
        if include_data:
            for name in SNAPSHOT_DIRECTORIES:
                destination = staging / "data" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(data_dir / name, destination)
                copied_stats = _directory_stats(destination)
                if copied_stats != source_stats[name]:
                    raise RuntimeError(f"Snapshot size changed while copying {name}")
                included_directories.append(name)
                directory_stats[name] = copied_stats

        finished = now()
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "backup_id": published.name,
            "status": "success",
            "scope": event_base["scope"],
            "started_at": event_base["started_at"],
            "finished_at": _iso_utc(finished),
            "database": database,
            "configuration": {
                "path": "config/sites.yaml",
                "bytes": backup_config.stat().st_size,
                "sha256": _sha256(backup_config),
            },
            "included_data_directories": sorted(included_directories),
            "data_directories": directory_stats,
        }
        _write_json(staging / "manifest.json", manifest)
        staging.replace(published)
        _append_event(
            event_path,
            {
                **event_base,
                "finished_at": manifest["finished_at"],
                "status": "success",
                "path": str(published),
            },
        )
        return published
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging)
        _append_event(
            event_path,
            {
                **event_base,
                "finished_at": _iso_utc(now()),
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise


def prune_old_backups(
    backup_root: Path,
    retention_days: int,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> list[str]:
    """Delete published backups older than ``retention_days``, keyed by name timestamp."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")
    backup_root = backup_root.expanduser().resolve()
    if not backup_root.is_dir():
        return []
    cutoff = now() - timedelta(days=retention_days)
    removed: list[str] = []
    for entry in sorted(backup_root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or not entry.name.startswith("backup-"):
            continue
        match = re.fullmatch(r"backup-(\d{8}T\d{6}Z)(?:-\d+)?", entry.name)
        if not match:
            continue
        try:
            created = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            # A directory with a malformed calendar date (e.g. backup-20260229T000000Z)
            # is skipped so it cannot abort pruning and retention cleanup.
            continue
        if created < cutoff:
            shutil.rmtree(entry)
            removed.append(entry.name)
    return removed


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    backup_dir = _require_directory(backup_dir, "backup directory")
    manifest_path = _require_file(backup_dir / "manifest.json", "backup manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise ValueError(f"Unsupported backup format: {manifest.get('format_version')!r}")
    if manifest.get("status") != "success":
        raise ValueError("Only successful backup manifests can be verified")

    database_spec = manifest["database"]
    db_path = _require_file(
        _safe_manifest_path(backup_dir, str(database_spec["path"])),
        "backup database",
    )
    if _sha256(db_path) != database_spec["sha256"]:
        raise ValueError("Backup database checksum does not match manifest")
    database = _database_report(db_path)
    if database["quick_check"] != "ok":
        raise RuntimeError(f"Backup database quick_check failed: {database['quick_check']}")

    config_spec = manifest["configuration"]
    config_path = _require_file(
        _safe_manifest_path(backup_dir, str(config_spec["path"])),
        "backup configuration",
    )
    if _sha256(config_path) != config_spec["sha256"]:
        raise ValueError("Backup configuration checksum does not match manifest")

    included = sorted(str(value) for value in manifest.get("included_data_directories", []))
    for name in included:
        if name not in VERIFIABLE_SNAPSHOT_DIRECTORIES:
            raise ValueError(f"Unexpected data directory in manifest: {name!r}")
        directory = _require_directory(backup_dir / "data" / name, f"backup data directory {name}")
        if _directory_stats(directory) != manifest["data_directories"][name]:
            raise ValueError(f"Backup data directory stats do not match manifest: {name}")

    return {
        "status": "ok",
        "backup_id": manifest["backup_id"],
        "scope": manifest["scope"],
        "database": database,
        "included_data_directories": included,
    }


def restore_to_isolated_directory(backup_dir: Path, restore_dir: Path) -> dict[str, Any]:
    """Restore a verified snapshot without replacing any live production path."""

    verification = verify_backup(backup_dir)
    backup_dir = backup_dir.expanduser().resolve()
    restore_dir = restore_dir.expanduser().resolve()
    if _is_within(restore_dir, backup_dir):
        raise ValueError("Restore directory must be outside the source backup directory")
    if restore_dir.exists() and any(restore_dir.iterdir()):
        raise FileExistsError(f"Restore directory must be absent or empty: {restore_dir}")
    restore_dir.mkdir(parents=True, exist_ok=True)

    restored_data = restore_dir / "data"
    restored_data.mkdir()
    shutil.copy2(backup_dir / "database" / "index.db", restored_data / "index.db")
    for name in verification["included_data_directories"]:
        shutil.copytree(backup_dir / "data" / name, restored_data / name)
    restored_config = restore_dir / "config"
    restored_config.mkdir()
    shutil.copy2(backup_dir / "config" / "sites.yaml", restored_config / "sites.yaml")

    database = _database_report(restored_data / "index.db", include_counts=True)
    if database["quick_check"] != "ok":
        raise RuntimeError(f"Restored database quick_check failed: {database['quick_check']}")
    if database["missing_tables"]:
        raise RuntimeError(
            "Restored database is missing required smoke tables: "
            + ", ".join(database["missing_tables"])
        )
    report = {
        "status": "ok",
        "backup_id": verification["backup_id"],
        "restore_dir": str(restore_dir),
        "database": database,
        "included_data_directories": verification["included_data_directories"],
    }
    _write_json(restore_dir / "restore-smoke.json", report)
    return report


def capacity_status(
    path: Path,
    *,
    threshold_percent: float = 80.0,
    disk_usage: Sequence[int] | None = None,
) -> dict[str, Any]:
    if not 0 < threshold_percent <= 100:
        raise ValueError("threshold_percent must be greater than 0 and at most 100")
    target = path.expanduser().resolve()
    usage = tuple(disk_usage) if disk_usage is not None else tuple(shutil.disk_usage(target))
    total, used, free = (int(value) for value in usage)
    if total <= 0:
        raise ValueError("disk usage total must be positive")
    used_percent = round((used / total) * 100, 2)
    return {
        "path": str(target),
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_percent": used_percent,
        "threshold_percent": float(threshold_percent),
        "blocked": used_percent >= threshold_percent,
    }


def inspect_docker_image(image: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError(f"Unexpected docker image inspect output for {image!r}")
    return payload[0]


def create_release_record(
    *,
    image: str,
    config_path: Path,
    db_path: Path,
    output_path: Path,
    inspect_image: Callable[[str], dict[str, Any]] = inspect_docker_image,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, Any]:
    config_path = _require_file(config_path, "configuration file")
    db_path = _require_file(db_path, "SQLite database")
    image_data = inspect_image(image)
    labels = dict(((image_data.get("Config") or {}).get("Labels") or {}))
    selected_labels = {name: str(labels.get(name) or "unknown") for name in OCI_LABELS}
    digests = list(image_data.get("RepoDigests") or [])
    image_digest = str(digests[0] if digests else image_data.get("Id") or "unknown")
    missing = [name for name, value in selected_labels.items() if value == "unknown"]
    if missing:
        raise ValueError(f"Image is missing required traceability labels: {', '.join(missing)}")
    if image_digest == "unknown":
        raise ValueError("Docker image inspect did not return an image ID or repository digest")
    database = _database_report(db_path)
    dirty_label = selected_labels["com.aiinforsearch.git-dirty"].lower()
    record = {
        "recorded_at": _iso_utc(now()),
        "image": image,
        "image_digest": image_digest,
        "git_sha": selected_labels["org.opencontainers.image.revision"],
        "git_dirty": True if dirty_label == "true" else False if dirty_label == "false" else None,
        "build_utc": selected_labels["org.opencontainers.image.created"],
        "source_url": selected_labels["org.opencontainers.image.source"],
        "config_sha256": _sha256(config_path),
        "schema_user_version": database["schema_user_version"],
    }
    _write_json(output_path.expanduser().resolve(), record)
    return record


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create an online DB backup or quiesced full snapshot")
    backup.add_argument("--data-dir", type=Path, required=True)
    backup.add_argument("--config", type=Path, required=True)
    backup.add_argument("--backup-root", type=Path, required=True)
    backup.add_argument("--include-data", action="store_true")
    backup.add_argument("--quiesced", action="store_true")
    backup.add_argument("--retention-days", type=_non_negative_int, default=None, help="Delete backups older than this many days after a successful backup")
    backup.add_argument("--json", action="store_true", help="Emit the machine-readable JSON result")

    verify = subparsers.add_parser("verify", help="Verify a published backup manifest and artifacts")
    verify.add_argument("backup_dir", type=Path)
    verify.add_argument("--json", action="store_true", help="Emit the machine-readable JSON result")

    restore = subparsers.add_parser("restore-smoke", help="Restore into an isolated directory and validate it")
    restore.add_argument("backup_dir", type=Path)
    restore.add_argument("--restore-dir", type=Path, required=True)
    restore.add_argument("--json", action="store_true", help="Emit the machine-readable JSON result")

    capacity = subparsers.add_parser("capacity-check", help="Block when disk use reaches the threshold")
    capacity.add_argument("--path", type=Path, default=Path("/"))
    capacity.add_argument("--threshold", type=float, default=80.0)
    capacity.add_argument("--json", action="store_true", help="Emit the machine-readable JSON result")

    release = subparsers.add_parser("release-record", help="Record image, config, and schema versions")
    release.add_argument("--image", required=True)
    release.add_argument("--config", type=Path, required=True)
    release.add_argument("--db", type=Path, required=True)
    release.add_argument("--output", type=Path, required=True)
    release.add_argument("--json", action="store_true", help="Emit the machine-readable JSON result")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "backup":
        path = create_backup(
            data_dir=args.data_dir,
            config_path=args.config,
            backup_root=args.backup_root,
            include_data=args.include_data,
            quiesced=args.quiesced,
        )
        payload: dict[str, Any] = {"status": "success", "backup_dir": str(path)}
        if args.retention_days is not None:
            payload["pruned"] = prune_old_backups(args.backup_root, args.retention_days)
    elif args.command == "verify":
        payload = verify_backup(args.backup_dir)
    elif args.command == "restore-smoke":
        payload = restore_to_isolated_directory(args.backup_dir, args.restore_dir)
    elif args.command == "capacity-check":
        payload = capacity_status(args.path, threshold_percent=args.threshold)
    elif args.command == "release-record":
        payload = create_release_record(
            image=args.image,
            config_path=args.config,
            db_path=args.db,
            output_path=args.output,
        )
    else:  # pragma: no cover - argparse enforces a valid subcommand
        raise AssertionError(args.command)

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if args.command == "capacity-check" and payload["blocked"]:
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc

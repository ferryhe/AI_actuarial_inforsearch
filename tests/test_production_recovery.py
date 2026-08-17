from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import production_recovery


ROOT = Path(__file__).resolve().parents[1]


def _seed_data_dir(root: Path) -> tuple[Path, Path]:
    data_dir = root / "data"
    data_dir.mkdir()
    db_path = data_dir / "index.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA user_version=7")
        conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, local_path TEXT)")
        conn.execute("CREATE TABLE rag_knowledge_bases (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE agentic_ready_manifests (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO files (local_path) VALUES ('files/example.pdf')")
        conn.execute("INSERT INTO rag_knowledge_bases (id) VALUES ('kb-1')")
        conn.execute("INSERT INTO agentic_ready_manifests (id) VALUES ('ready-1')")

    for relative, content in (
        ("files/example.pdf", b"pdf"),
        ("rag/kb-1/index.faiss", b"index"),
        ("agentic_ready_data/kb-1/manifest.json", b"{}"),
    ):
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    config_path = root / "sites.yaml"
    config_path.write_text("paths:\n  db: data/index.db\n", encoding="utf-8")
    return data_dir, config_path


def test_online_database_backup_is_repeatable_and_records_success(tmp_path: Path) -> None:
    data_dir, config_path = _seed_data_dir(tmp_path)
    backup_root = tmp_path / "backups"
    clock = iter(
        (
            datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 16, 12, 0, 10, tzinfo=timezone.utc),
            datetime(2026, 8, 16, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 16, 12, 1, 10, tzinfo=timezone.utc),
        )
    )

    first = production_recovery.create_backup(
        data_dir=data_dir,
        config_path=config_path,
        backup_root=backup_root,
        now=lambda: next(clock),
    )
    second = production_recovery.create_backup(
        data_dir=data_dir,
        config_path=config_path,
        backup_root=backup_root,
        now=lambda: next(clock),
    )

    assert first != second
    assert production_recovery.verify_backup(first)["status"] == "ok"
    assert production_recovery.verify_backup(second)["status"] == "ok"
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert manifest["finished_at"] == "2026-08-16T12:00:10Z"
    assert manifest["database"]["quick_check"] == "ok"
    assert manifest["database"]["schema_user_version"] == 7
    assert manifest["included_data_directories"] == []

    events = [json.loads(line) for line in (backup_root / "backup-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["status"] for event in events] == ["success", "success"]


def test_full_snapshot_requires_quiesced_acknowledgement(tmp_path: Path) -> None:
    data_dir, config_path = _seed_data_dir(tmp_path)

    with pytest.raises(ValueError, match="quiesced"):
        production_recovery.create_backup(
            data_dir=data_dir,
            config_path=config_path,
            backup_root=tmp_path / "backups",
            include_data=True,
        )


def test_full_snapshot_verifies_and_restores_to_isolated_directory(tmp_path: Path) -> None:
    data_dir, config_path = _seed_data_dir(tmp_path)
    backup = production_recovery.create_backup(
        data_dir=data_dir,
        config_path=config_path,
        backup_root=tmp_path / "backups",
        include_data=True,
        quiesced=True,
        now=lambda: datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
    )

    report = production_recovery.verify_backup(backup)
    assert report["status"] == "ok"
    assert report["included_data_directories"] == ["agentic_ready_data", "files", "rag"]

    restored = production_recovery.restore_to_isolated_directory(backup, tmp_path / "restore")
    assert restored["status"] == "ok"
    assert restored["database"]["quick_check"] == "ok"
    assert restored["database"]["counts"] == {
        "agentic_ready_manifests": 1,
        "files": 1,
        "rag_knowledge_bases": 1,
    }
    assert (tmp_path / "restore/data/files/example.pdf").read_bytes() == b"pdf"
    assert (tmp_path / "restore/data/rag/kb-1/index.faiss").read_bytes() == b"index"
    assert (tmp_path / "restore/data/agentic_ready_data/kb-1/manifest.json").is_file()


def test_failed_backup_writes_failure_event_without_publishing_snapshot(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_path = tmp_path / "sites.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    backup_root = tmp_path / "backups"

    with pytest.raises(FileNotFoundError, match="index.db"):
        production_recovery.create_backup(
            data_dir=data_dir,
            config_path=config_path,
            backup_root=backup_root,
            now=lambda: datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        )

    events = [json.loads(line) for line in (backup_root / "backup-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1]["status"] == "failed"
    assert not list(backup_root.glob("*.tmp"))
    assert not list(backup_root.glob("backup-*/manifest.json"))


def test_capacity_gate_blocks_at_configured_threshold(tmp_path: Path) -> None:
    below = production_recovery.capacity_status(
        tmp_path,
        threshold_percent=80,
        disk_usage=(100, 79, 21),
    )
    blocked = production_recovery.capacity_status(
        tmp_path,
        threshold_percent=80,
        disk_usage=(100, 80, 20),
    )

    assert below["blocked"] is False
    assert blocked["blocked"] is True
    assert blocked["used_percent"] == 80.0


def test_release_record_captures_image_config_and_schema_versions(tmp_path: Path) -> None:
    data_dir, config_path = _seed_data_dir(tmp_path)
    output = tmp_path / "release.json"
    inspect_payload = {
        "Id": "sha256:image-id",
        "RepoDigests": ["example/api@sha256:digest"],
        "Config": {
            "Labels": {
                "org.opencontainers.image.revision": "abc123",
                "org.opencontainers.image.created": "2026-08-16T12:00:00Z",
                "org.opencontainers.image.source": "https://github.com/ferryhe/AI_actuarial_inforsearch",
                "com.aiinforsearch.git-dirty": "false",
            }
        },
    }

    record = production_recovery.create_release_record(
        image="example/api:latest",
        config_path=config_path,
        db_path=data_dir / "index.db",
        output_path=output,
        inspect_image=lambda _image: inspect_payload,
        now=lambda: datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert record["image_digest"] == "example/api@sha256:digest"
    assert record["git_sha"] == "abc123"
    assert record["git_dirty"] is False
    assert record["schema_user_version"] == 7
    assert record["config_sha256"]
    assert json.loads(output.read_text(encoding="utf-8")) == record


def test_docker_build_and_runbook_expose_recovery_contract() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "deployment-runbook.md").read_text(encoding="utf-8")

    for label in (
        "org.opencontainers.image.revision",
        "org.opencontainers.image.created",
        "org.opencontainers.image.source",
        "com.aiinforsearch.git-dirty",
    ):
        assert label in dockerfile
    for build_arg in ("BUILD_GIT_SHA", "BUILD_GIT_DIRTY", "BUILD_UTC", "BUILD_SOURCE_URL"):
        assert build_arg in compose

    assert "ai_actuarial_inforsearch_ai-data" in runbook
    assert "docker volume inspect" in runbook
    assert "production_recovery.py" in runbook
    assert "cp data/index.db" not in runbook


def test_scheduled_backup_and_deploy_gate_use_named_volume_recovery_tool() -> None:
    backup_wrapper = (ROOT / "scripts" / "production_backup.sh").read_text(encoding="utf-8")
    service = (ROOT / "ops" / "systemd" / "aiinforsearch-backup.service").read_text(encoding="utf-8")
    timer = (ROOT / "ops" / "systemd" / "aiinforsearch-backup.timer").read_text(encoding="utf-8")
    deploy_path = ROOT / "scripts" / "deploy_update.sh"
    deploy = deploy_path.read_text(encoding="utf-8")

    assert "docker volume inspect" in backup_wrapper
    assert "production_recovery.py" in backup_wrapper
    assert "--include-data" not in backup_wrapper
    assert 'BACKUP_ROOT="${BACKUP_ROOT:?' in backup_wrapper
    assert "/var/backups/aiinforsearch" not in backup_wrapper
    assert 'stat -c %d "$DATA_DIR"' in backup_wrapper
    assert 'stat -c %d "$BACKUP_ROOT"' in backup_wrapper
    assert 'flock -n 9' in backup_wrapper
    assert "ExecStart=/usr/bin/bash /opt/ai_actuarial_inforsearch/scripts/production_backup.sh" in service
    assert "EnvironmentFile=/etc/aiinforsearch/backup.conf" in service
    assert "EnvironmentFile=-" not in service
    assert "OnCalendar=" in timer
    assert "Persistent=true" in timer

    assert deploy_path.read_bytes().startswith(b"#!/usr/bin/env bash")
    assert "git status --porcelain" in deploy
    assert "capacity-check" in deploy
    assert 'BACKUP_ROOT="${BACKUP_ROOT:?' in deploy
    assert "/var/backups/aiinforsearch" not in deploy
    assert 'stat -c %d "$DATA_DIR"' in deploy
    assert 'stat -c %d "$BACKUP_ROOT"' in deploy
    assert 'flock -n 9' in deploy
    assert "--include-data" in deploy
    assert "--quiesced" in deploy
    assert "BUILD_GIT_SHA" in deploy
    assert "release-record" in deploy

    runbook = (ROOT / "docs" / "deployment-runbook.md").read_text(encoding="utf-8")
    assert "base64.urlsafe_b64encode(secrets.token_bytes(32))" in runbook
    assert "from cryptography.fernet import Fernet" not in runbook


def test_production_recovery_cli_help_and_json_output(tmp_path: Path) -> None:
    help_result = subprocess.run(
        [sys.executable, "scripts/production_recovery.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "capacity-check" in help_result.stdout

    json_result = subprocess.run(
        [
            sys.executable,
            "scripts/production_recovery.py",
            "capacity-check",
            "--path",
            str(tmp_path),
            "--threshold",
            "100",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert json_result.returncode == 0
    assert json.loads(json_result.stdout)["blocked"] is False

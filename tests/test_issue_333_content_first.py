from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.api.services.weekly_updates import generate_weekly_update_summary
from ai_actuarial.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"
PERIOD_START = "2026-09-01T00:00:00+00:00"
PERIOD_END = "2026-09-08T00:00:00+00:00"


def _build_weekly_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path, str, str]:
    db_path = tmp_path / "index.db"
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "db": str(db_path),
                    "download_dir": str(tmp_path / "files"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "defaults": {"file_exts": [".pdf"]},
                "sites": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    urls = (
        "https://example.test/metadata.pdf",
        "https://example.test/missing-catalog.pdf",
        "https://example.test/malformed-keywords.pdf",
    )
    storage = Storage(str(db_path))
    try:
        for index, url in enumerate(urls):
            storage.insert_file(
                url=url,
                sha256=f"hash-{index}",
                title=f"Issue 333 file {index}",
                source_site="example.test",
                source_page_url="https://example.test",
                original_filename=f"issue-333-{index}.pdf",
                local_path=str(tmp_path / f"issue-333-{index}.pdf"),
                bytes=1024 + index,
                content_type="application/pdf",
            )
            storage._conn.execute(
                "UPDATE files SET first_seen = ?, last_seen = ? WHERE url = ?",
                (f"2026-09-0{index + 2}T12:00:00+00:00", "2099-01-01T00:00:00+00:00", url),
            )
            storage._conn.commit()

        storage.upsert_catalog_item(
            item={
                "url": urls[0],
                "sha256": "hash-0",
                "category": " ; Risk & Capital ; AI ",
                "keywords": ["capital", "scenario"],
                "summary": "Public summary",
            },
            pipeline_version="issue-333",
        )
        storage.upsert_catalog_item(
            item={
                "url": urls[2],
                "sha256": "hash-2",
                "category": "",
                "keywords": [],
                "summary": "",
            },
            pipeline_version="issue-333",
        )
        storage._conn.execute(
            "UPDATE catalog_items SET keywords = ? WHERE file_url = ?",
            (json.dumps({"unexpected": True}), urls[2]),
        )
        reader_token = "issue-333-reader"
        storage.upsert_auth_token_by_hash(
            subject="issue-333-reader",
            group_name="reader",
            token_hash=hashlib.sha256(reader_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        storage._conn.commit()
    finally:
        storage.close()

    snapshot = generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    return TestClient(create_app()), db_path, str(snapshot["id"]), reader_token


def test_issue_333_executable_react_behavior() -> None:
    result = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", "client/src/lib/issue333-content-first.test.tsx"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Issue #333 content-first executable assertions passed" in result.stdout


def test_weekly_public_projection_joins_catalog_without_sensitive_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_path, snapshot_id, _reader_token = _build_weekly_client(tmp_path, monkeypatch)

    statements: list[str] = []
    storage = Storage(str(db_path))
    storage._conn.set_trace_callback(statements.append)
    try:
        rows, total = storage.list_weekly_snapshot_files(
            snapshot_id=snapshot_id,
            limit=2,
            offset=0,
        )
    finally:
        storage.close()

    assert total == 3
    assert len(rows) == 2
    member_query = next(
        statement for statement in statements if "FROM weekly_snapshot_members" in statement
    )
    assert "LEFT JOIN catalog_items" in member_query
    for sensitive in ("markdown_content", "local_path", "sha256", "bytes", "deleted_at"):
        assert sensitive not in member_query

    first_page = client.get(f"/api/weekly-updates/{snapshot_id}/files?limit=1&offset=0")
    full_page = client.get(f"/api/weekly-updates/{snapshot_id}/files?limit=3&offset=0")
    assert first_page.status_code == full_page.status_code == 200

    first_body = first_page.json()
    assert first_body["total"] == 3
    assert first_body["included_count"] == 1
    assert first_body["truncated"] is True
    returned_files = full_page.json()["files"]
    first = next(item for item in returned_files if item["url"].endswith("metadata.pdf"))
    assert first["category"] == " ; Risk & Capital ; AI "
    assert first["keywords"] == ["capital", "scenario"]
    assert first["summary"] == "Public summary"
    assert set(first) == {
        "url",
        "title",
        "original_filename",
        "first_seen",
        "category",
        "keywords",
        "summary",
    }
    assert not set(first).intersection(
        {"markdown_content", "markdown_source", "local_path", "sha256", "bytes", "deleted_at"}
    )

    missing = next(item for item in returned_files if item["url"].endswith("missing-catalog.pdf"))
    assert missing["category"] is None
    assert missing["keywords"] == []
    assert missing["summary"] is None
    malformed = next(
        item for item in returned_files if item["url"].endswith("malformed-keywords.pdf")
    )
    assert malformed["keywords"] == []


def test_weekly_and_database_reads_preserve_guest_and_reader_permissions_and_malformed_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _db_path, snapshot_id, reader_token = _build_weekly_client(tmp_path, monkeypatch)
    weekly_url = f"/api/weekly-updates/{snapshot_id}/files?limit=3&offset=0"

    guest_weekly = client.get(weekly_url)
    reader_weekly = client.get(
        weekly_url,
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    guest_database = client.get("/api/files?limit=10&order_by=first_seen&order_dir=asc")

    assert guest_weekly.status_code == reader_weekly.status_code == 200
    assert guest_weekly.json() == reader_weekly.json()
    assert guest_database.status_code == 200
    malformed = next(
        item
        for item in guest_database.json()["files"]
        if item["url"].endswith("malformed-keywords.pdf")
    )
    assert malformed["keywords"] == []

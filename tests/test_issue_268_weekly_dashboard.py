from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.api.services.weekly_updates import generate_weekly_update_summary
from ai_actuarial.storage import Storage

PERIOD_START = "2026-03-09T00:00:00+00:00"
PERIOD_END = "2026-03-16T00:00:00+00:00"


def _build_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path, str]:
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

    rows = [
        ("lower.pdf", "Weekly lower", "alpha.example", PERIOD_START, "Risk", False),
        (
            "middle.pdf",
            "Weekly middle",
            "alpha.example",
            "2026-03-12T12:00:00+00:00",
            "Risk",
            False,
        ),
        ("upper.pdf", "Weekly upper", "alpha.example", PERIOD_END, "Risk", False),
        ("prior.pdf", "Weekly prior", "alpha.example", "2026-03-08T23:59:59+00:00", "Risk", False),
        (
            "other.pdf",
            "Weekly other",
            "other.example",
            "2026-03-11T00:00:00+00:00",
            "Pricing",
            False,
        ),
        (
            "deleted.pdf",
            "Weekly deleted",
            "alpha.example",
            "2026-03-13T00:00:00+00:00",
            "Risk",
            True,
        ),
    ]
    storage = Storage(str(db_path))
    try:
        for filename, title, source, first_seen, category, deleted in rows:
            url = f"https://{source}/{filename}"
            storage.insert_file(
                url=url,
                sha256=f"hash-{filename}",
                title=title,
                source_site=source,
                source_page_url=f"https://{source}",
                original_filename=filename,
                local_path=str(tmp_path / filename),
                bytes=1024,
                content_type="application/pdf",
            )
            storage.upsert_catalog_item(
                item={
                    "url": url,
                    "sha256": f"hash-{filename}",
                    "keywords": ["weekly"],
                    "summary": f"Summary for {title}",
                    "category": category,
                },
                pipeline_version="issue-268",
                status="ok",
            )
            storage._conn.execute(
                "UPDATE files SET first_seen = ?, last_seen = ? WHERE url = ?",
                (first_seen, first_seen, url),
            )
            storage._conn.commit()
            if deleted:
                storage.mark_file_deleted(url, "2026-03-14T00:00:00+00:00")
                storage.clear_local_path(url)
            storage._conn.commit()

        operator_token = "issue-268-operator"
        storage.upsert_auth_token_by_hash(
            subject="issue-268-operator",
            group_name="operator",
            token_hash=hashlib.sha256(operator_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        storage._conn.commit()
    finally:
        storage.close()

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    return TestClient(create_app()), db_path, operator_token


def test_files_api_period_is_half_open_sorted_paginated_and_composes_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _db_path, operator_token = _build_client(tmp_path, monkeypatch)
    base = (
        "/api/files?first_seen_from=2026-03-09T00%3A00%3A00%2B00%3A00"
        "&first_seen_before=2026-03-16T00%3A00%3A00%2B00%3A00"
        "&query=weekly&source=alpha&category=Risk"
        "&order_by=first_seen&order_dir=desc&limit=1"
    )

    first_page = client.get(f"{base}&offset=0")
    second_page = client.get(f"{base}&offset=1")

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == second_page.json()["total"] == 2
    assert [item["title"] for item in first_page.json()["files"]] == ["Weekly middle"]
    assert [item["title"] for item in second_page.json()["files"]] == ["Weekly lower"]
    assert first_page.json()["files"][0]["first_seen"] == "2026-03-12T12:00:00+00:00"

    without_permission = client.get(f"{base}&include_deleted=true")
    assert without_permission.status_code == 401

    with_deleted = client.get(
        f"{base}&include_deleted=true&limit=20",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert with_deleted.status_code == 200
    assert with_deleted.json()["total"] == 3
    assert [item["title"] for item in with_deleted.json()["files"]] == [
        "Weekly deleted",
        "Weekly middle",
        "Weekly lower",
    ]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("order_by=not-a-field", "Invalid order_by"),
        ("order_by=", "Invalid order_by"),
        ("order_dir=sideways", "Invalid order_dir"),
        ("order_dir=", "Invalid order_dir"),
        (
            "first_seen_from=2026-03-09T00:00:00",
            "first_seen_from must be a timezone-aware RFC3339 timestamp",
        ),
        (
            "first_seen_before=not-a-date",
            "first_seen_before must be a timezone-aware RFC3339 timestamp",
        ),
        (
            "first_seen_from=2026-03-09T00:00:00Z",
            "first_seen_from and first_seen_before must be provided together",
        ),
        (
            "first_seen_before=2026-03-16T00:00:00Z",
            "first_seen_from and first_seen_before must be provided together",
        ),
        (
            "first_seen_from=&first_seen_before=",
            "first_seen_from and first_seen_before must be provided together",
        ),
        (
            "first_seen_from=2026-03-16T00:00:00Z&first_seen_before=2026-03-09T00:00:00Z",
            "first_seen_from must be before first_seen_before",
        ),
    ],
)
def test_files_api_rejects_invalid_sort_and_period_contracts_with_stable_400(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    message: str,
) -> None:
    client, _db_path, _operator_token = _build_client(tmp_path, monkeypatch)

    response = client.get(f"/api/files?{query}")

    assert response.status_code == 400
    assert response.json() == {"error": message}


def test_weekly_files_api_projects_a_title_edit_without_rebuilding_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_path, _operator_token = _build_client(tmp_path, monkeypatch)
    snapshot = generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    target_url = "https://alpha.example/lower.pdf"
    first = client.get(f"/api/weekly-updates/{snapshot['id']}/files?limit=8")
    assert first.status_code == 200
    assert (
        next(item for item in first.json()["files"] if item["url"] == target_url)["title"]
        == "Weekly lower"
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE files SET title = ? WHERE url = ?", ("Edited live title", target_url))

    reloaded = client.get(f"/api/weekly-updates/{snapshot['id']}/files?limit=8")
    assert reloaded.status_code == 200
    assert (
        next(item for item in reloaded.json()["files"] if item["url"] == target_url)["title"]
        == "Edited live title"
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE files SET title = NULL, original_filename = NULL WHERE url = ?",
            (target_url,),
        )
        conn.execute(
            "UPDATE weekly_snapshot_members SET original_filename = NULL WHERE snapshot_id = ? AND file_url = ?",
            (snapshot["id"], target_url),
        )

    url_fallback = client.get(f"/api/weekly-updates/{snapshot['id']}/files?limit=8")
    assert url_fallback.status_code == 200
    assert (
        next(item for item in url_fallback.json()["files"] if item["url"] == target_url)["title"]
        == ""
    )

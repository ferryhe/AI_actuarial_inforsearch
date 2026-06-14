from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _write_config_files(base_dir: Path) -> Path:
    db_path = base_dir / "index.db"
    config_path = base_dir / "sites.yaml"
    categories_path = base_dir / "categories.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "db": str(db_path),
                    "download_dir": str(base_dir / "files"),
                    "updates_dir": str(base_dir / "updates"),
                    "last_run_new": str(base_dir / "last_run_new.json"),
                },
                "defaults": {"user_agent": "test-agent/1.0", "max_pages": 10, "max_depth": 1},
                "sites": [],
                "scheduled_tasks": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    categories_path.write_text(yaml.safe_dump({"categories": {}}, sort_keys=False), encoding="utf-8")
    return db_path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_ready_data(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        output_dir / "doc_catalog.jsonl",
        [
            {
                "doc_id": "doc-a",
                "file_url": "https://example.test/a.pdf",
                "title": "Capital Adequacy Guideline",
                "category": "regulation",
                "summary": "Capital adequacy overview.",
                "headings": ["Capital"],
            },
            {
                "doc_id": "doc-b",
                "file_url": "https://example.test/b.pdf",
                "title": "Reserve Method Note",
                "category": "method",
                "summary": "Reserve method overview.",
                "headings": ["Reserve"],
            },
        ],
    )
    _write_jsonl(
        output_dir / "doc_summaries.jsonl",
        [
            {
                "doc_id": "doc-a",
                "file_url": "https://example.test/a.pdf",
                "title": "Capital Adequacy Guideline",
                "category": "regulation",
                "summary": "Required capital and solvency ratio summary.",
            },
            {
                "doc_id": "doc-b",
                "file_url": "https://example.test/b.pdf",
                "title": "Reserve Method Note",
                "category": "method",
                "summary": "Reserve assumptions summary.",
            },
        ],
    )
    _write_jsonl(
        output_dir / "sections.jsonl",
        [
            {
                "section_id": "doc-a#1",
                "doc_id": "doc-a",
                "heading_path": ["Capital"],
                "text": "Required capital appears in the solvency section.",
                "token_count": 8,
            }
        ],
    )
    (output_dir / "ready_data_manifest.json").write_text(
        json.dumps(
            {
                "profile": "general",
                "profile_version": "1",
                "artifact_files": ["doc_catalog.jsonl", "doc_summaries.jsonl", "sections.jsonl"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _build_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    db_path = _write_config_files(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "sites.yaml"))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(tmp_path / "categories.yaml"))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "agentic-rag-test-secret")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    return TestClient(app), db_path


def test_fastapi_agentic_rag_summary_search_uses_explicit_output_dir(tmp_path: Path, monkeypatch) -> None:
    client, _db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "agentic_ready_data" / "explicit"
    _write_ready_data(ready_dir)

    response = client.post(
        "/api/agentic-rag/search/summaries",
        json={"query": "required capital solvency", "limit": 1, "output_dir": str(ready_dir)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "required capital solvency"
    assert body["limit"] == 1
    assert body["count"] == 1
    assert body["results"][0]["file_url"] == "https://example.test/a.pdf"
    assert body["results"][0]["source"] == "doc_summaries"


def test_fastapi_agentic_rag_title_search_resolves_registry_ready_manifest(tmp_path: Path, monkeypatch) -> None:
    client, db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "agentic_ready_data" / "kbs" / "kb-a" / "general" / "1"
    _write_ready_data(ready_dir)
    storage = Storage(str(db_path))
    try:
        manager = KnowledgeBaseManager(storage)
        manager.create_kb(kb_id="kb-a", name="KB A", kb_mode="manual", manifest_profile="general")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-a",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(ready_dir),
            artifact_files=["doc_catalog.jsonl", "doc_summaries.jsonl", "sections.jsonl"],
            doc_count=2,
            section_count=1,
            built_at="2026-06-14T00:00:00+00:00",
            source_db=str(db_path),
        )
    finally:
        storage.close()

    response = client.post(
        "/api/agentic-rag/search/titles",
        json={"query": "reserve method", "limit": 3, "kb_id": "kb-a", "profile": "general"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kb_id"] == "kb-a"
    assert body["profile"] == "general"
    assert body["output_dir"] == str(ready_dir)
    assert body["results"][0]["title"] == "Reserve Method Note"


def test_fastapi_agentic_rag_search_returns_empty_results_for_no_match(tmp_path: Path, monkeypatch) -> None:
    client, _db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "agentic_ready_data" / "explicit"
    _write_ready_data(ready_dir)

    response = client.post(
        "/api/agentic-rag/search/summaries",
        json={"query": "nonexistent phrase", "output_dir": str(ready_dir)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"] == []
    assert response.json()["count"] == 0


def test_fastapi_agentic_rag_search_rejects_missing_output_dir(tmp_path: Path, monkeypatch) -> None:
    client, _db_path = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agentic-rag/search/summaries",
        json={"query": "capital", "output_dir": str(tmp_path / "missing-ready")},
    )

    assert response.status_code == 400
    assert "output_dir" in response.json()["error"]


def test_fastapi_agentic_rag_search_rejects_explicit_output_dir_outside_ready_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "outside-ready"
    _write_ready_data(ready_dir)

    response = client.post(
        "/api/agentic-rag/search/summaries",
        json={"query": "capital", "output_dir": str(ready_dir)},
    )

    assert response.status_code == 400
    assert "agentic_ready_data" in response.json()["error"]


def test_fastapi_agentic_rag_search_rejects_output_dir_mixed_with_kb_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "agentic_ready_data" / "explicit"
    _write_ready_data(ready_dir)

    response = client.post(
        "/api/agentic-rag/search/titles",
        json={"query": "capital", "output_dir": str(ready_dir), "kb_id": "kb-a", "profile": "general"},
    )

    assert response.status_code == 400
    assert "cannot be combined" in response.json()["error"]


def test_fastapi_agentic_rag_search_rejects_missing_ready_data_registry(tmp_path: Path, monkeypatch) -> None:
    client, _db_path = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agentic-rag/search/titles",
        json={"query": "capital", "kb_id": "kb-missing", "profile": "general"},
    )

    assert response.status_code == 404
    assert "ready_data" in response.json()["error"]


def test_fastapi_agentic_rag_search_rejects_not_ready_registry_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "agentic_ready_data" / "kbs" / "kb-building" / "general" / "1"
    _write_ready_data(ready_dir)
    storage = Storage(str(db_path))
    try:
        manager = KnowledgeBaseManager(storage)
        manager.create_kb(kb_id="kb-building", name="Building KB", kb_mode="manual", manifest_profile="general")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-building",
            profile="general",
            profile_version="1",
            status="building",
            output_dir=str(ready_dir),
        )
    finally:
        storage.close()

    response = client.post(
        "/api/agentic-rag/search/titles",
        json={"query": "capital", "kb_id": "kb-building", "manifest_profile": "general"},
    )

    assert response.status_code == 409
    assert "not ready" in response.json()["error"]


def test_fastapi_agentic_rag_search_rejects_registry_output_dir_outside_ready_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, db_path = _build_client(tmp_path, monkeypatch)
    ready_dir = tmp_path / "outside-ready"
    _write_ready_data(ready_dir)
    storage = Storage(str(db_path))
    try:
        manager = KnowledgeBaseManager(storage)
        manager.create_kb(kb_id="kb-outside", name="Outside KB", kb_mode="manual", manifest_profile="general")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-outside",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(ready_dir),
        )
    finally:
        storage.close()

    response = client.post(
        "/api/agentic-rag/search/titles",
        json={"query": "capital", "kb_id": "kb-outside", "profile": "general"},
    )

    assert response.status_code == 400
    assert "agentic_ready_data" in response.json()["error"]

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_fastapi_rag_admin_endpoints import (
    _build_test_client,
    _make_session_cookie,
)

CUSTOMER_FORBIDDEN = (
    "kb_mode",
    "chunk_profile_id",
    "manifest_profile",
    "embedding_provider",
    "embedding_model",
    "embedding_dimension",
    "embedding_identity_key",
    "chunk_size",
    "chunk_overlap",
    "index_type",
    "chunk_count",
    "created_at",
    "updated_at",
    "current_embeddings",
    "index_coverage",
    "agentic_ready_manifest",
    "agentic_ready_available",
    "agentic_fallback_mode",
)


def _customer_clients(app, seed):
    anon = TestClient(app)
    registered = TestClient(app)
    registered.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["registered_user_id"]}),
    )
    return anon, registered


def _operator_client(app, seed):
    op = TestClient(app)
    op.headers.update({"X-Auth-Token": seed["operator_token"]})
    return op


def test_kb_rbac_list_projects_diagnostics_for_customers(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-rbac-list",
            "name": "RBAC List KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    anon, registered = _customer_clients(app, seed)
    for customer in (anon, registered):
        resp = customer.get("/api/rag/knowledge-bases")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "current_embeddings" not in body
        kb = next(k for k in body["knowledge_bases"] if k["kb_id"] == "kb-rbac-list")
        assert kb["name"] == "RBAC List KB"
        assert "file_count" in kb
        for field in CUSTOMER_FORBIDDEN:
            assert field not in kb

    op = _operator_client(app, seed)
    op_body = op.get("/api/rag/knowledge-bases").json()
    op_kb = next(k for k in op_body["knowledge_bases"] if k["kb_id"] == "kb-rbac-list")
    assert op_kb["kb_mode"] == "manual"
    assert "embedding_provider" in op_kb
    assert "agentic_ready_manifest" in op_kb
    assert "current_embeddings" in op_body


def test_kb_rbac_detail_and_files_project_for_customers(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-rbac-detail",
            "name": "RBAC Detail KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    anon, registered = _customer_clients(app, seed)
    for customer in (anon, registered):
        detail = customer.get("/api/rag/knowledge-bases/kb-rbac-detail").json()
        kb = detail["knowledge_base"]
        assert kb["name"] == "RBAC Detail KB"
        assert "file_count" in kb
        for field in CUSTOMER_FORBIDDEN:
            assert field not in kb
        # stats: only file_count
        stats = customer.get("/api/rag/knowledge-bases/kb-rbac-detail/stats").json()
        assert set(stats.keys()) == {"file_count"}
        # files: only customer-safe columns
        files = customer.get("/api/rag/knowledge-bases/kb-rbac-detail/files").json()
        assert files["total_files"] >= 1
        row = files["files"][0]
        assert set(row.keys()) == {"file_url", "title", "category", "source_site"}

    op = _operator_client(app, seed)
    op_detail = op.get("/api/rag/knowledge-bases/kb-rbac-detail").json()["knowledge_base"]
    assert "agentic_ready_manifest" in op_detail
    assert "index_coverage" in op_detail


def test_kb_rbac_manifest_requires_tasks_run(tmp_path: Path, monkeypatch) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-rbac-manifest",
            "name": "RBAC Manifest KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    anon, registered = _customer_clients(app, seed)
    assert anon.get(
        "/api/rag/knowledge-bases/kb-rbac-manifest/agentic-ready-manifest"
    ).status_code == 401
    assert registered.get(
        "/api/rag/knowledge-bases/kb-rbac-manifest/agentic-ready-manifest"
    ).status_code == 403

    op = _operator_client(app, seed)
    assert op.get(
        "/api/rag/knowledge-bases/kb-rbac-manifest/agentic-ready-manifest"
    ).status_code == 200


def test_chat_knowledge_bases_projects_diagnostics_for_customers(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-rbac-chat",
            "name": "RBAC Chat KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    anon, registered = _customer_clients(app, seed)
    for customer in (anon, registered):
        resp = customer.get("/api/chat/knowledge-bases")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "current_embeddings" not in data
        kb = next(k for k in data["knowledge_bases"] if k["kb_id"] == "kb-rbac-chat")
        assert kb["name"] == "RBAC Chat KB"
        assert "file_count" in kb
        for field in CUSTOMER_FORBIDDEN:
            assert field not in kb

    op = _operator_client(app, seed)
    op_data = op.get("/api/chat/knowledge-bases").json()["data"]
    op_kb = next(k for k in op_data["knowledge_bases"] if k["kb_id"] == "kb-rbac-chat")
    assert "agentic_ready_manifest" in op_kb
    assert "current_embeddings" in op_data

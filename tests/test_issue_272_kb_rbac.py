from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_actuarial import shared_auth
from ai_actuarial.api.routers import rag_admin as rag_admin_router
from ai_actuarial.api.routers import ready_data_automation as ready_data_automation_router
from ai_actuarial.api.routers import ready_data_publication as ready_data_publication_router
from ai_actuarial.api.services.rag_admin import (
    RagAdminError,
    _request_already_authorized,
    _require_tasks_run,
)
from ai_actuarial.storage import Storage
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


def _catalog_only_client(app, monkeypatch) -> TestClient:
    token = "catalog-only-token"
    monkeypatch.setitem(
        shared_auth.GROUP_PERMISSIONS,
        "catalog_only",
        frozenset({"catalog.read", "catalog.write"}),
    )
    storage = Storage(app.state.db_path)
    try:
        storage.upsert_auth_token_by_hash(
            subject="catalog-only-token",
            group_name="catalog_only",
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
    finally:
        storage.close()
    client = TestClient(app)
    client.headers.update({"X-Auth-Token": token})
    return client


def test_kb_rbac_service_authorizes_each_mutation_capability() -> None:
    class Auth:
        token = {"id": "test"}

        def __init__(self, *permissions: str) -> None:
            self.permissions = frozenset(permissions)

    assert _request_already_authorized(Auth("catalog.write"), "catalog.write")
    assert not _request_already_authorized(Auth("catalog.write"), "tasks.run")
    assert not _request_already_authorized(Auth("catalog.write"), "config.write")
    assert _request_already_authorized(Auth("tasks.run"), "tasks.run")
    assert _request_already_authorized(Auth("config.write"), "config.write")
    with pytest.raises(RagAdminError, match="Forbidden"):
        _require_tasks_run({}, Auth("catalog.write"))


def test_kb_rbac_mutation_role_matrix(tmp_path: Path, monkeypatch) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    anonymous, registered = _customer_clients(app, seed)
    operator = _operator_client(app, seed)
    admin = TestClient(app)
    admin.headers.update({"X-Auth-Token": seed["admin_token"]})

    for customer in (anonymous, registered):
        assert customer.post(
            "/api/rag/knowledge-bases", json={"kb_id": "kb-denied", "name": "Denied"}
        ).status_code in {401, 403}
        assert customer.post("/api/rag/knowledge-bases/kb-denied/index", json={}).status_code in {
            401,
            403,
        }
        assert customer.post(
            "/api/chunk/profiles", json={"name": "Denied", "chunk_size": 10}
        ).status_code in {401, 403}

    assert (
        operator.post(
            "/api/rag/knowledge-bases", json={"kb_id": "kb-operator", "name": "Operator"}
        ).status_code
        == 201
    )
    assert (
        operator.put(
            "/api/rag/knowledge-bases/kb-operator/agentic-ready-automation",
            json={
                "profile": "general",
                "automatic_build_enabled": True,
                "automatic_publish_enabled": False,
            },
        ).status_code
        == 200
    )
    assert (
        operator.post(
            "/api/chunk/profiles", json={"name": "Operator denied", "chunk_size": 10}
        ).status_code
        == 403
    )
    assert (
        admin.post(
            "/api/chunk/profiles", json={"name": "Admin profile", "chunk_size": 10}
        ).status_code
        == 201
    )


def test_kb_mutating_endpoint_role_matrix_uses_real_fastapi_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    anonymous, registered = _customer_clients(app, seed)
    operator = _operator_client(app, seed)
    admin = TestClient(app)
    admin.headers.update({"X-Auth-Token": seed["admin_token"]})

    def result(*_args, **_kwargs):
        return {"ok": True}

    for name in (
        "create_knowledge_base",
        "update_knowledge_base",
        "delete_knowledge_base",
        "add_knowledge_base_files",
        "remove_knowledge_base_file",
        "set_knowledge_base_categories",
        "bind_chunk_sets",
        "create_chunk_profile",
        "update_chunk_profile",
        "delete_chunk_profile",
        "cleanup_chunk_sets",
        "get_agentic_ready_manifest",
        "get_unmapped_categories",
        "get_categories_mapping",
        "get_category_stats",
        "list_selectable_files",
        "get_pending_files",
        "get_kb_bindings",
        "list_knowledge_bases",
        "get_knowledge_base",
        "get_knowledge_base_stats",
        "list_knowledge_base_files",
        "get_knowledge_base_categories",
    ):
        monkeypatch.setattr(rag_admin_router, name, result)
    monkeypatch.setattr(
        rag_admin_router, "create_index_task", lambda *_args, **_kwargs: (result(), 200)
    )
    monkeypatch.setattr(
        rag_admin_router, "build_agentic_ready_manifest", lambda *_args, **_kwargs: (result(), 200)
    )
    monkeypatch.setattr(ready_data_automation_router, "set_ready_data_automation", result)
    monkeypatch.setattr(ready_data_publication_router, "publish_ready_data_publication", result)
    monkeypatch.setattr(ready_data_publication_router, "rollback_ready_data_publication", result)

    endpoint_matrix = (
        ("profile_read", "get", "/api/chunk/profiles", None),
        ("read", "get", "/api/rag/knowledge-bases", None),
        ("read", "get", "/api/rag/knowledge-bases/matrix", None),
        ("read", "get", "/api/rag/knowledge-bases/matrix/stats", None),
        ("read", "get", "/api/rag/knowledge-bases/matrix/files", None),
        ("read", "get", "/api/rag/knowledge-bases/matrix/categories", None),
        ("tasks", "get", "/api/rag/knowledge-bases/matrix/agentic-ready-manifest", None),
        ("tasks", "get", "/api/rag/knowledge-bases/matrix/files/pending", None),
        ("catalog", "get", "/api/rag/categories/unmapped", None),
        ("catalog", "get", "/api/rag/categories/mapping", None),
        ("catalog", "post", "/api/rag/categories/stats", {"categories": []}),
        ("catalog", "get", "/api/rag/files/selectable", None),
        ("catalog", "get", "/api/rag/knowledge-bases/matrix/bindings", None),
        ("catalog", "post", "/api/rag/knowledge-bases", {"kb_id": "matrix", "name": "Matrix"}),
        ("catalog", "put", "/api/rag/knowledge-bases/matrix", {"name": "Matrix"}),
        ("catalog", "delete", "/api/rag/knowledge-bases/matrix", None),
        (
            "catalog",
            "post",
            "/api/rag/knowledge-bases/matrix/files",
            {"file_urls": ["matrix-file"]},
        ),
        ("catalog", "delete", "/api/rag/knowledge-bases/matrix/files/matrix-file", None),
        (
            "catalog",
            "post",
            "/api/rag/knowledge-bases/matrix/categories",
            {"categories": ["matrix"]},
        ),
        ("catalog", "post", "/api/rag/knowledge-bases/matrix/bindings", {"bindings": []}),
        ("tasks", "post", "/api/rag/knowledge-bases/matrix/index", {}),
        ("tasks", "post", "/api/rag/knowledge-bases/matrix/agentic-ready-manifest/build", {}),
        ("tasks", "put", "/api/rag/knowledge-bases/matrix/agentic-ready-automation", {}),
        ("tasks", "post", "/api/rag/knowledge-bases/matrix/agentic-ready-manifest/publish", {}),
        ("tasks", "post", "/api/rag/knowledge-bases/matrix/agentic-ready-manifest/rollback", {}),
        ("config", "post", "/api/chunk/profiles", {"name": "Matrix", "chunk_size": 10}),
        ("config", "put", "/api/chunk/profiles/matrix", {"name": "Matrix", "chunk_size": 10}),
        ("config", "delete", "/api/chunk/profiles/matrix", None),
        ("config", "post", "/api/chunk-sets/cleanup", {"older_than_days": 30}),
    )
    role_matrix = (
        ("guest", anonymous, {"read"}),
        ("registered", registered, {"read"}),
        ("operator", operator, {"catalog", "tasks", "profile_read", "read"}),
        ("admin", admin, {"catalog", "tasks", "config", "profile_read", "read"}),
    )

    for role, role_client, allowed_kinds in role_matrix:
        for kind, method, path, payload in endpoint_matrix:
            response = role_client.request(method.upper(), path, json=payload)
            if kind in allowed_kinds:
                assert response.status_code < 300, (role, kind, method, path, response.text)
            else:
                assert response.status_code in {401, 403}, (role, kind, method, path, response.text)


def test_kb_rbac_list_projects_diagnostics_for_customers(tmp_path: Path, monkeypatch) -> None:
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


def test_kb_rbac_detail_and_files_project_for_customers(tmp_path: Path, monkeypatch) -> None:
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


def test_catalog_only_can_update_detail_and_bind_without_task_diagnostics(
    tmp_path: Path, monkeypatch
) -> None:
    _admin, app, seed = _build_test_client(tmp_path, monkeypatch)
    catalog_only = _catalog_only_client(app, monkeypatch)
    profile_id = str(seed["default_chunk_profile_id"])
    created = catalog_only.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-catalog-only",
            "name": "Catalog only KB",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    assert catalog_only.get("/api/chunk/profiles").status_code == 200
    detail = catalog_only.get("/api/rag/knowledge-bases/kb-catalog-only")
    assert detail.status_code == 200, detail.text
    kb = detail.json()["knowledge_base"]
    assert kb["chunk_profile_id"] == profile_id
    assert kb["kb_mode"] == "manual"
    assert "current_embeddings" not in kb
    assert "index_coverage" not in kb

    updated = catalog_only.put(
        "/api/rag/knowledge-bases/kb-catalog-only",
        json={"name": "Renamed catalog KB", "description": ""},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["knowledge_base"]["name"] == "Renamed catalog KB"

    storage = Storage(app.state.db_path)
    try:
        chunk_set = storage._conn.execute(
            "SELECT chunk_set_id FROM file_chunk_sets WHERE file_url = ? AND profile_id = ?",
            (seed["beta_url"], profile_id),
        ).fetchone()
    finally:
        storage.close()
    assert chunk_set
    bound = catalog_only.post(
        "/api/rag/knowledge-bases/kb-catalog-only/bindings",
        json={
            "bindings": [
                {
                    "file_url": seed["beta_url"],
                    "chunk_set_id": chunk_set[0],
                    "binding_mode": "follow_latest",
                }
            ]
        },
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["processed"] == 1


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
    assert (
        anon.get("/api/rag/knowledge-bases/kb-rbac-manifest/agentic-ready-manifest").status_code
        == 401
    )
    assert (
        registered.get(
            "/api/rag/knowledge-bases/kb-rbac-manifest/agentic-ready-manifest"
        ).status_code
        == 403
    )

    op = _operator_client(app, seed)
    assert (
        op.get("/api/rag/knowledge-bases/kb-rbac-manifest/agentic-ready-manifest").status_code
        == 200
    )


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

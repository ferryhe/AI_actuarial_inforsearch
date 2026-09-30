from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from ai_actuarial.api.app import create_app
from ai_actuarial.embedding_service import resolve_server_embedding_identity
from ai_actuarial.rag.kb_index import build_kb_index, resolve_kb_bound_chunks
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _write_config_files(base_dir: Path) -> tuple[Path, Path, Path, Path]:
    files_dir = base_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / "index.db"
    config_path = base_dir / "sites.yaml"
    categories_path = base_dir / "categories.yaml"
    export_dir = base_dir / "updates"
    export_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "paths": {
            "db": str(db_path),
            "download_dir": str(files_dir),
            "updates_dir": str(export_dir),
            "last_run_new": str(base_dir / "last_run_new.json"),
        },
        "defaults": {
            "user_agent": "test-agent/1.0",
            "max_pages": 10,
            "max_depth": 1,
            "file_exts": [".pdf", ".docx"],
        },
        "system": {
            "file_deletion_enabled": True,
        },
        "sites": [],
        "scheduled_tasks": [],
    }
    categories = {"categories": {"AI": ["artificial intelligence"]}}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path, files_dir


def _seed_storage(db_path: Path, files_dir: Path) -> dict[str, object]:
    alpha_path = files_dir / "alpha.pdf"
    alpha_path.write_bytes(PDF_BYTES)
    beta_path = files_dir / "beta.docx"
    beta_path.write_text("beta docx content", encoding="utf-8")

    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url="https://alpha.example/doc-a.pdf",
            sha256=hashlib.sha256(PDF_BYTES).hexdigest(),
            title="Alpha Document",
            source_site="alpha.example",
            source_page_url="https://alpha.example",
            original_filename="doc-a.pdf",
            local_path=str(alpha_path),
            bytes=len(PDF_BYTES),
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://alpha.example/doc-a.pdf",
                "sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
                "keywords": ["ai"],
                "summary": "Alpha summary",
                "category": "AI",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(
            "https://alpha.example/doc-a.pdf",
            "# Alpha\n\nOriginal markdown.",
            "manual",
        )

        storage.insert_file(
            url="https://beta.example/doc-b.docx",
            sha256=hashlib.sha256(beta_path.read_bytes()).hexdigest(),
            title="Beta Document",
            source_site="beta.example",
            source_page_url="https://beta.example",
            original_filename="doc-b.docx",
            local_path=str(beta_path),
            bytes=beta_path.stat().st_size,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://beta.example/doc-b.docx",
                "sha256": hashlib.sha256(beta_path.read_bytes()).hexdigest(),
                "keywords": ["pricing"],
                "summary": "Beta summary",
                "category": "Pricing",
            },
            pipeline_version="v1",
            status="ok",
        )
        operator_token = "operator-token"
        storage.upsert_auth_token_by_hash(
            subject="operator-token",
            group_name="operator",
            token_hash=hashlib.sha256(operator_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        reader_token = "reader-token"
        storage.upsert_auth_token_by_hash(
            subject="reader-token",
            group_name="reader",
            token_hash=hashlib.sha256(reader_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        operator_user_id = storage.create_user(
            "operator@example.com",
            "operator-password-hash",
            role="operator",
            display_name="Operator",
        )
    finally:
        storage.close()

    return {
        "alpha_url": "https://alpha.example/doc-a.pdf",
        "beta_url": "https://beta.example/doc-b.docx",
        "alpha_path": str(alpha_path),
        "operator_token": operator_token,
        "reader_token": reader_token,
        "operator_user_id": operator_user_id,
    }


def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, object]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "fastapi-file-mutations-test-secret")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    return client, app, seed


def _make_session_cookie(app, payload: dict[str, object]) -> str:
    serializer = URLSafeSerializer(app.state.fastapi_session_secret, salt="fastapi-session")
    return serializer.dumps(payload)


def test_fastapi_file_mutation_routes_are_listed_in_native_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/files/update" in body["native_paths"]
    assert "/api/files/delete" in body["native_paths"]
    assert "/api/files/{file_url:path}/markdown" in body["native_paths"]
    assert "/api/download" in body["native_paths"]
    assert "/api/export" in body["native_paths"]


def test_fastapi_file_mutations_download_and_export_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    update_response = client.post(
        "/api/files/update",
        json={
            "url": seed["alpha_url"],
            "title": "Alpha Document Updated",
            "category": "AI; Preview",
            "summary": "Updated summary",
            "keywords": ["ai", "preview"],
        },
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["file"]["title"] == "Alpha Document Updated"

    markdown_response = client.post(
        f"/api/files/{seed['alpha_url']}/markdown",
        json={"markdown_content": "# Updated\n\nFastAPI markdown.", "markdown_source": "manual"},
        headers=headers,
    )
    assert markdown_response.status_code == 200, markdown_response.text
    assert markdown_response.json()["markdown"]["markdown_content"].startswith("# Updated")

    download_response = client.get(
        "/api/download", params={"url": seed["alpha_url"]}, headers=headers
    )
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == PDF_BYTES

    export_response = client.get("/api/export", params={"format": "csv"}, headers=headers)
    assert export_response.status_code == 200, export_response.text
    assert "attachment; filename=catalog_export.csv" in export_response.headers.get(
        "content-disposition", ""
    )
    assert "Alpha Document Updated" in export_response.content.decode("utf-8-sig")

    delete_response = client.post(
        "/api/files/delete", json={"url": seed["beta_url"], "confirm": "DELETE"}, headers=headers
    )
    assert delete_response.status_code == 200, delete_response.text

    files_after_delete = client.get("/api/files?include_deleted=true", headers=headers)
    deleted = next(
        item for item in files_after_delete.json()["files"] if item["url"] == seed["beta_url"]
    )
    assert deleted["deleted_at"]


def test_filtered_export_matches_database_filters_and_uses_safe_fields(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    response = client.get(
        "/api/export",
        params={"format": "csv", "query": "Alpha", "order_by": "title", "order_dir": "asc"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["x-export-record-count"] == "1"
    csv_text = response.content.decode("utf-8-sig")
    assert "Alpha Document" in csv_text
    assert "Beta Document" not in csv_text
    assert "local_path" not in csv_text
    assert "sha256" not in csv_text
    assert "etag" not in csv_text


def test_full_export_requires_capability_and_snapshot_membership_is_shared(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    operator_headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    admin_token = "admin-export-token"
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage.upsert_auth_token_by_hash(
            subject="admin-export-token",
            group_name="admin",
            token_hash=hashlib.sha256(admin_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        storage.mark_file_deleted(str(seed["alpha_url"]), "2026-03-11T00:00:00+00:00")
        storage.clear_local_path(str(seed["alpha_url"]))
        storage.publish_weekly_snapshot(
            {
                "id": "snapshot-export-test",
                "period_start": "2026-03-01T00:00:00+00:00",
                "period_end": "2026-03-15T00:00:00+00:00",
                "file_count": 1,
            },
            members=[
                {
                    "url": str(seed["beta_url"]),
                    "first_seen": "2026-03-10T10:00:00+00:00",
                    "original_filename": "doc-b.docx",
                }
            ],
        )
    finally:
        storage.close()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    listed = client.get("/api/files?snapshot_id=snapshot-export-test", headers=operator_headers)
    exported = client.get("/api/export?snapshot_id=snapshot-export-test", headers=operator_headers)
    assert listed.json()["total"] == 1
    assert exported.headers["x-export-record-count"] == "1"
    assert "Beta Document" in exported.content.decode("utf-8-sig")
    assert "Alpha Document" not in exported.content.decode("utf-8-sig")

    assert (
        client.get("/api/export?include_deleted=true", headers=operator_headers).status_code == 400
    )
    assert (
        client.get("/api/export/full?include_deleted=true", headers=operator_headers).status_code
        == 403
    )

    full_without_deleted = client.get("/api/export/full", headers=admin_headers)
    assert "Alpha Document" not in full_without_deleted.content.decode("utf-8-sig")
    full = client.get(
        "/api/export/full?include_deleted=true&include_internal=true", headers=admin_headers
    )
    full_csv = full.content.decode("utf-8-sig")
    assert full.headers["x-export-record-count"] == "2"
    assert "Alpha Document" in full_csv
    assert "local_path" in full_csv and "sha256" in full_csv and "etag" in full_csv

    storage = Storage(str(tmp_path / "index.db"))
    try:
        audit_detail = storage._conn.execute(
            "SELECT detail FROM audit_events WHERE event_type = 'catalog_export' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        storage.close()
    assert audit_detail == "records=2; full=true"


def test_snapshot_export_keeps_frozen_member_filename_and_first_seen(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage.publish_weekly_snapshot(
            {
                "id": "snapshot-frozen-member-test",
                "period_start": "2024-01-01T00:00:00+00:00",
                "period_end": "2024-01-08T00:00:00+00:00",
                "file_count": 1,
            },
            members=[
                {
                    "url": str(seed["beta_url"]),
                    "first_seen": "2024-01-03T12:00:00+00:00",
                    "original_filename": "frozen-beta.docx",
                }
            ],
        )
        storage.upsert_file(
            str(seed["beta_url"]),
            "new-beta-hash",
            "Beta Document",
            "beta.example",
            "https://beta.example",
            "current-beta.docx",
            str(tmp_path / "files" / "beta.docx"),
            2048,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            None,
            None,
            None,
        )
        storage._conn.execute(
            "UPDATE files SET first_seen = ? WHERE url = ?",
            ("2030-01-03T12:00:00+00:00", seed["beta_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    params = {
        "snapshot_id": "snapshot-frozen-member-test",
        "query": "frozen-beta.docx",
        "first_seen_from": "2024-01-03T00:00:00+00:00",
        "first_seen_before": "2024-01-04T00:00:00+00:00",
        "order_by": "first_seen",
        "order_dir": "asc",
    }
    listed = client.get("/api/files", params=params, headers=headers)
    exported = client.get("/api/export", params=params, headers=headers)

    assert listed.json()["total"] == 1
    assert listed.json()["files"][0]["original_filename"] == "frozen-beta.docx"
    assert listed.json()["files"][0]["first_seen"] == "2024-01-03T12:00:00+00:00"
    assert exported.headers["x-export-record-count"] == "1"
    assert "frozen-beta.docx" in exported.content.decode("utf-8-sig")

    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage._conn.execute("DELETE FROM files WHERE url = ?", (seed["beta_url"],))
        storage._conn.commit()
    finally:
        storage.close()

    missing_current = client.get(
        "/api/files?snapshot_id=snapshot-frozen-member-test", headers=headers
    )
    missing_current_export = client.get(
        "/api/export?snapshot_id=snapshot-frozen-member-test", headers=headers
    )
    assert missing_current.json()["total"] == 1
    assert missing_current.json()["files"][0]["original_filename"] == "frozen-beta.docx"
    assert missing_current_export.headers["x-export-record-count"] == "1"


def test_global_file_delete_reconciles_kbs_and_reindexes_only_complete_nonempty_kb(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        identity = resolve_server_embedding_identity(storage)
        profile = storage.create_chunk_profile(
            name="delete-reconcile-profile",
            chunk_size=256,
            chunk_overlap=32,
        )
        profile_id = str(profile["profile_id"])
        manager = KnowledgeBaseManager(storage)
        for kb_id, urls in (
            ("kb-delete-two", [seed["alpha_url"], seed["beta_url"]]),
            ("kb-delete-empty", [seed["beta_url"]]),
        ):
            manager.create_kb(
                kb_id=kb_id,
                name=kb_id,
                kb_mode="manual",
                chunk_profile_id=profile_id,
                embedding_provider=identity.provider,
                embedding_model=identity.model,
                embedding_dimension=identity.dimension,
                embedding_identity_key=identity.embedding_identity_key,
            )
            manager.add_files_to_kb(kb_id, list(urls))

        storage.update_file_markdown(
            str(seed["beta_url"]), "# Beta\n\nDelete reconciliation.", "manual"
        )
        chunk_ids: dict[str, str] = {}
        for index, file_url in enumerate((str(seed["alpha_url"]), str(seed["beta_url"]))):
            chunk_set = storage.get_or_create_file_chunk_set(
                file_url=file_url,
                profile_id=profile_id,
                markdown_hash=f"delete-{index}",
                status="building",
            )
            storage.replace_global_chunks(
                chunk_set_id=str(chunk_set["chunk_set_id"]),
                chunks=[
                    {
                        "chunk_index": 0,
                        "content": f"Delete reconciliation chunk {index}",
                        "token_count": 4,
                        "section_hierarchy": "Root",
                    }
                ],
            )
            chunk_id = str(
                storage._conn.execute(
                    "SELECT chunk_id FROM global_chunks WHERE chunk_set_id = ?",
                    (chunk_set["chunk_set_id"],),
                ).fetchone()[0]
            )
            chunk_ids[file_url] = chunk_id
            for kb_id in (
                ["kb-delete-two", "kb-delete-empty"]
                if file_url == seed["beta_url"]
                else ["kb-delete-two"]
            ):
                storage.bind_chunk_set_to_kb(
                    kb_id=kb_id,
                    file_url=file_url,
                    chunk_set_id=str(chunk_set["chunk_set_id"]),
                    bound_by="delete-test",
                    binding_mode="pin",
                )
        storage.batch_upsert_chunk_embeddings(
            [
                {
                    "chunk_id": chunk_id,
                    "vector": [float(index + 1)] * identity.dimension,
                }
                for index, chunk_id in enumerate(chunk_ids.values())
            ],
            identity=identity.as_dict(),
        )
        old_versions: dict[str, str] = {}
        for kb_id in ("kb-delete-two", "kb-delete-empty"):
            snapshot = resolve_kb_bound_chunks(storage, kb_id)
            built = build_kb_index(
                storage=storage,
                kb_id=kb_id,
                expected_binding_snapshot_fingerprint=str(snapshot["binding_snapshot_fingerprint"]),
                embedding_identity_key=identity.embedding_identity_key,
                config=manager.config,
            )
            old_versions[kb_id] = str(built["index_version_id"])
    finally:
        storage.close()

    launched: list[tuple[str, dict[str, object]]] = []

    def start_task(task_type: str, payload: dict[str, object], **_kwargs: object) -> str:
        launched.append((task_type, dict(payload)))
        return f"job-delete-{len(launched)}"

    app.state.start_background_task = start_task
    response = client.post(
        "/api/files/delete",
        json={"url": seed["beta_url"], "confirm": "DELETE"},
        headers={"Authorization": f"Bearer {seed['operator_token']}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["details"]["affected_kb_count"] == 2
    assert response.json()["details"]["reindex_jobs"] == [
        {"kb_id": "kb-delete-two", "job_id": "job-delete-1"}
    ]
    assert launched[0][0] == "rag_indexing"
    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM rag_kb_files WHERE file_url = ?",
                (seed["beta_url"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE file_url = ?",
                (seed["beta_url"],),
            ).fetchone()[0]
            == 0
        )
        assert storage._conn.execute(
            "SELECT index_dirty_at FROM rag_knowledge_bases WHERE kb_id = ?",
            ("kb-delete-two",),
        ).fetchone()[0]
        assert (
            storage.get_agentic_ready_source_state(kb_id="kb-delete-two", profile="general")[
                "pending_evaluation_generation"
            ]
            is not None
        )
        assert (
            storage._conn.execute(
                "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
                ("kb-delete-empty",),
            ).fetchone()[0]
            == old_versions["kb-delete-empty"]
        )

        remaining = resolve_kb_bound_chunks(storage, "kb-delete-two")
        assert [row["chunk_id"] for row in remaining["chunks"]] == [
            chunk_ids[str(seed["alpha_url"])]
        ]
        rebuilt = build_kb_index(
            storage=storage,
            kb_id="kb-delete-two",
            expected_binding_snapshot_fingerprint=str(remaining["binding_snapshot_fingerprint"]),
            embedding_identity_key=str(launched[0][1]["embedding_identity_key"]),
            config=KnowledgeBaseManager(storage).config,
        )
        assert rebuilt["chunk_count"] == 1
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_index_items WHERE index_version_id = ?",
                (old_versions["kb-delete-two"],),
            ).fetchone()[0]
            == 2
        )
        with pytest.raises(Exception, match="invalid_selector"):
            resolve_kb_bound_chunks(storage, "kb-delete-empty")
    finally:
        storage.close()


@pytest.mark.parametrize("auth_mode", ["bearer", "x-api-token", "session"])
def test_fastapi_file_delete_ignores_legacy_service_token(
    tmp_path: Path,
    monkeypatch,
    auth_mode: str,
) -> None:
    monkeypatch.setenv("FILE_DELETION_AUTH_TOKEN", "legacy-delete-token")
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    headers: dict[str, str] = {}
    if auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {seed['operator_token']}"
    elif auth_mode == "x-api-token":
        headers["X-API-Token"] = str(seed["operator_token"])
    else:
        session_cookie = _make_session_cookie(app, {"email_user_id": seed["operator_user_id"]})
        client.cookies.set(app.state.fastapi_session_cookie_name, session_cookie)

    response = client.post(
        "/api/files/delete",
        json={"url": seed["beta_url"], "confirm": "DELETE"},
        headers=headers,
    )

    assert response.status_code == 200, response.text


def test_fastapi_file_delete_keeps_permission_feature_and_confirmation_checks(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    payload = {"url": seed["beta_url"], "confirm": "DELETE"}

    unauthorized = client.post("/api/files/delete", json=payload)
    forbidden = client.post(
        "/api/files/delete",
        json=payload,
        headers={"Authorization": f"Bearer {seed['reader_token']}"},
    )

    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    monkeypatch.setenv("ENABLE_FILE_DELETION", "false")
    disabled = client.post("/api/files/delete", json=payload, headers=headers)
    monkeypatch.setenv("ENABLE_FILE_DELETION", "true")
    missing_confirmation = client.post(
        "/api/files/delete",
        json={"url": seed["beta_url"]},
        headers=headers,
    )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403
    assert disabled.status_code == 403
    assert missing_confirmation.status_code == 400

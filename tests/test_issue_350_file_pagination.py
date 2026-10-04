from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_actuarial.api.services import rag_admin
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage
from tests.test_fastapi_rag_admin_endpoints import _build_test_client


@pytest.fixture
def paged_client(tmp_path, monkeypatch):
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-350",
            "name": "Large fixture",
            "kb_mode": "manual",
        },
    )
    assert created.status_code == 201, created.text
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        urls = [f"https://fixture.test/{i:04d}.pdf" for i in range(1101)]
        storage._conn.executemany(
            "INSERT INTO files(url,title,original_filename,source_site) VALUES(?,?,?,?)",
            [
                (
                    url,
                    f"  REPORT {i // 2:04d}  " if i % 2 else f"Report {i // 2:04d}",
                    f"{i:04d}.pdf",
                    "fixture",
                )
                for i, url in enumerate(urls)
            ],
        )
        storage._conn.executemany(
            "INSERT INTO catalog_items(file_url,sha256,pipeline_version,category,markdown_content,markdown_updated_at) VALUES(?,?,?,?,?,?)",
            [
                (url, str(i), "fixture", "A; B" if i % 2 else "A", "# Report", "2026-01-01")
                for i, url in enumerate(urls)
            ],
        )
        storage._conn.executemany(
            "INSERT INTO rag_kb_files(kb_id,file_url,added_at,indexed_at,chunk_count) VALUES(?,?,?,?,?)",
            [
                ("kb-350", url, "2026-01-01", None if i % 3 else "2025-12-31", 0)
                for i, url in enumerate(urls)
            ],
        )
        # Two versions of the selected profile plus one other-profile version.
        profile = storage.get_chunk_profile(seed["default_chunk_profile_id"])
        other = storage.create_chunk_profile(name="Other", chunk_size=200, chunk_overlap=20)
        for i, url in enumerate(urls[:50]):
            versions = []
            for suffix, selected in (("one", profile), ("two", profile), ("other", other)):
                chunk_set = storage.get_or_create_file_chunk_set(
                    file_url=url,
                    profile_id=selected["profile_id"],
                    markdown_hash=f"{i}-{suffix}",
                    profile_config_hash=selected["config_hash"],
                    status="ready",
                )
                versions.append(chunk_set["chunk_set_id"])
            storage.bind_chunk_set_to_kb(
                kb_id="kb-350", file_url=url, chunk_set_id=versions[1], binding_mode="pin"
            )
        storage._conn.commit()
    finally:
        storage.close()
    return client, db_path, urls


def test_kb_pages_are_stable_bounded_filtered_and_lightweight(paged_client, monkeypatch):
    client, _db_path, urls = paged_client

    def fail(*args, **kwargs):
        raise AssertionError("Full file/binding materialization is forbidden")

    monkeypatch.setattr(KnowledgeBaseManager, "get_kb_files", fail)
    monkeypatch.setattr(Storage, "list_kb_chunk_bindings", fail)
    first = client.get("/api/rag/knowledge-bases/kb-350/files").json()
    assert (first["total"], first["limit"], first["offset"]) == (1101, 50, 0)
    assert [row["file_url"] for row in first["items"]] == urls[:50]
    assert first["files"] == first["items"]  # bounded compatibility alias
    second = client.get("/api/rag/knowledge-bases/kb-350/files?offset=50").json()
    assert [row["file_url"] for row in second["items"]] == urls[50:100]
    assert client.get("/api/rag/knowledge-bases/kb-350/files?offset=50").json() == second
    tail = client.get("/api/rag/knowledge-bases/kb-350/files?offset=1100").json()
    assert [row["file_url"] for row in tail["items"]] == urls[1100:]
    assert client.get("/api/rag/knowledge-bases/kb-350/files?offset=1200").json()["items"] == []
    filtered = client.get(
        "/api/rag/knowledge-bases/kb-350/files?query=report%200500&category=B"
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["file_url"] == urls[1001]
    assert client.get("/api/rag/knowledge-bases/kb-350/files?limit=10000").json()["limit"] == 100
    assert client.get("/api/rag/knowledge-bases/kb-350/files?limit=bad").status_code == 400
    stale = client.get("/api/rag/knowledge-bases/kb-350/files?status=stale").json()
    assert stale["total"] == 367
    assert all(row["status"] == "stale" for row in stale["items"])


def test_operator_chunk_versions_use_one_grouped_count_query(paged_client, monkeypatch):
    client, _db_path, _urls = paged_client
    statements = []
    original = rag_admin.Storage

    def traced_storage(db_path):
        storage = original(db_path)
        storage._conn.set_trace_callback(statements.append)
        return storage

    monkeypatch.setattr(rag_admin, "Storage", traced_storage)
    first = client.get("/api/rag/knowledge-bases/kb-350/files").json()
    assert all(row["chunk_version_count"] == 2 for row in first["items"])
    counts = [
        sql for sql in statements if "COUNT(*)" in sql.upper() and "FILE_CHUNK_SETS" in sql.upper()
    ]
    assert len(counts) == 1
    assert "GROUP BY file_url, profile_id" in counts[0]


def test_chat_documents_expose_total_and_reach_beyond_1000(paged_client):
    client, _db_path, urls = paged_client
    first = client.get("/api/chat/available-documents?query=report").json()["data"]
    assert (first["total"], first["limit"], first["offset"]) == (1101, 50, 0)
    assert [row["file_url"] for row in first["items"]] == urls[:50]
    assert first["documents"] == first["items"]
    tail = client.get("/api/chat/available-documents?query=report&offset=1100").json()["data"]
    assert [row["file_url"] for row in tail["items"]] == urls[1100:]
    filtered = client.get("/api/chat/available-documents?query=report%200500&category=B").json()[
        "data"
    ]
    assert filtered["total"] == 1
    assert filtered["items"][0]["file_url"] == urls[1001]
    assert client.get("/api/chat/available-documents?offset=no").status_code == 400


def test_customer_page_preserves_safe_projection_without_chunk_diagnostics(paged_client):
    _client, db_path, urls = paged_client
    page = rag_admin.list_knowledge_base_files(
        db_path=str(db_path),
        kb_id="kb-350",
        query={"offset": "50"},
        auth=SimpleNamespace(permissions=frozenset({"catalog.read"})),
    )
    assert page["total"] == 1101
    assert [row["file_url"] for row in page["items"]] == urls[50:100]
    assert all(
        set(row) == {"file_url", "title", "category", "source_site"} for row in page["items"]
    )
    assert "profile_summary" not in page


@pytest.mark.parametrize("term", ["%", "_", "!"])
def test_chat_query_matches_literal_metadata_characters(paged_client, term):
    client, db_path, urls = paged_client
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("UPDATE files SET title = ? WHERE url = ?", ("Rate 100%", urls[0]))
        storage._conn.execute(
            "UPDATE files SET original_filename = ? WHERE url = ?", ("reserve_!.pdf", urls[1])
        )
        storage._conn.execute(
            "UPDATE catalog_items SET keywords = ? WHERE file_url = ?",
            ("discount%rate,under_score,bang!flag", urls[2]),
        )
        storage._conn.commit()
    finally:
        storage.close()
    result = client.get("/api/chat/available-documents", params={"query": term}).json()["data"]
    expected = [urls[0], urls[2]] if term == "%" else [urls[1], urls[2]]
    assert result["total"] == len(expected)
    assert {row["file_url"] for row in result["items"]} == set(expected)


@pytest.mark.parametrize("term", ["%", "_", "!"])
def test_kb_query_matches_literal_title_category_and_url(paged_client, term):
    client, db_path, urls = paged_client
    literal_url = "https://fixture.test/literal%_!.pdf"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("UPDATE files SET title = ? WHERE url = ?", ("Rate 100%!", urls[0]))
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?", ("under_score", urls[1])
        )
        storage._conn.execute(
            "INSERT INTO files(url,title) VALUES(?,?)", (literal_url, "Literal URL")
        )
        storage._conn.execute(
            "INSERT INTO rag_kb_files(kb_id,file_url,added_at) VALUES(?,?,?)",
            ("kb-350", literal_url, "2026-01-01"),
        )
        storage._conn.commit()
    finally:
        storage.close()
    result = client.get("/api/rag/knowledge-bases/kb-350/files", params={"query": term}).json()
    expected = [literal_url, urls[1] if term == "_" else urls[0]]
    assert result["total"] == len(expected)
    assert {row["file_url"] for row in result["items"]} == set(expected)


def test_chat_legacy_keywords_keep_wildcard_and_comma_semantics(paged_client):
    client, _db_path, urls = paged_client
    endpoint = "/api/chat/available-documents"
    total = client.get(endpoint).json()["data"]["total"]
    assert client.get(endpoint, params={"keywords": "%"}).json()["data"]["total"] == total
    result = client.get(endpoint, params={"keywords": "report%0500,report_0540"}).json()["data"]
    assert result["total"] == 4
    assert {row["file_url"] for row in result["items"]} == {
        urls[1000],
        urls[1001],
        urls[1080],
        urls[1081],
    }
    assert client.get(endpoint, params={"query": "report_0500"}).json()["data"]["total"] == 0

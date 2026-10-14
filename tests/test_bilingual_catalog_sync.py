from __future__ import annotations

import hashlib
import json

import pytest

import ai_actuarial.content_hub as content_hub
import ai_actuarial.postgres as postgres
import ai_actuarial.storage as storage_module
from ai_actuarial.content_hub import ContentHubError, sync_content_hub_catalog_metadata
from ai_actuarial.storage import Storage


def _metadata_rows(url: str, raw_sha: str) -> list[tuple]:
    rows = []
    for language in ("zh", "en"):
        rows.append(
            (
                17,
                json.dumps(url),
                hashlib.sha256(url.encode("utf-8")).hexdigest(),
                raw_sha,
                language,
                31,
                hashlib.sha256(json.dumps("source markdown").encode("utf-8")).hexdigest(),
                f"title {language}",
                f"summary {language}",
                "Other",
                [f"keyword {language}"],
                17,
                "markdown_content",
                json.dumps("source markdown"),
                False,
                hashlib.sha256(json.dumps("source markdown").encode("utf-8")).hexdigest(),
            )
        )
    return rows


class _FakeCursor:
    def __init__(self, rows: list[tuple], identity: tuple):
        self.rows = rows
        self.identity = identity

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query: str):
        return None

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.identity


class _FakeHubConnection:
    def __init__(self, rows: list[tuple], identity: tuple):
        self.rows = rows
        self.identity = identity
        self.session_options = None
        self.closed = False

    def set_session(self, **kwargs):
        self.session_options = kwargs

    def cursor(self):
        return _FakeCursor(self.rows, self.identity)

    def close(self):
        self.closed = True


def _install_fake_databases(monkeypatch, *, same_database: bool = False):
    monkeypatch.setenv("CONTENT_HUB_DATABASE_URL", "postgresql://hub.invalid/hub")
    target_identity = (
        "shared" if same_database else "application",
        "127.0.0.1",
        5432,
        "public",
    )
    hub_identity = (
        "shared" if same_database else "hub",
        "127.0.0.1",
        5432,
        "content_hub",
    )

    class FakeTargetConnection:
        def __init__(self, _database, *, read_only=False):
            assert read_only
            self.closed = False

        def execute(self, query, _parameters=None):
            if "current_database()" in query:
                return type("Result", (), {"fetchone": lambda _self: target_identity})()
            return type("Result", (), {"fetchone": lambda _self: (3,)})()

        def table_exists(self, _table):
            return True

        def table_columns(self, _table):
            return {"file_url", "sha256", "category"}

        def close(self):
            self.closed = True

    hub = _FakeHubConnection(
        _metadata_rows(
            "https://example.test/report.pdf",
            "a" * 64,
        ),
        hub_identity,
    )
    monkeypatch.setattr(postgres, "PostgresConnection", FakeTargetConnection)
    monkeypatch.setattr(content_hub, "_connect", lambda _url: hub)
    monkeypatch.setattr(content_hub, "_require_current_schema", lambda _cursor, _schema: None)
    return target_identity, hub


def test_hub_sync_reads_only_and_uses_original_file_hash_and_variant_binding(monkeypatch):
    target_identity, hub = _install_fake_databases(monkeypatch)
    outcomes = iter([("updated", 8), ("unchanged", 0)])
    merges = []

    class FakeStorage:
        def __init__(self, _database, *, data_root):
            assert data_root

        def merge_hub_bilingual_metadata(self, **kwargs):
            merges.append(kwargs)
            return next(outcomes)

        def close(self):
            pass

    monkeypatch.setattr(storage_module, "Storage", FakeStorage)
    first = sync_content_hub_catalog_metadata("postgresql://target.invalid/app")
    second = sync_content_hub_catalog_metadata("postgresql://target.invalid/app")

    assert hub.session_options == {"readonly": True, "autocommit": False}
    assert hub.closed
    assert merges[0]["url"] == "https://example.test/report.pdf"
    assert merges[0]["file_sha256"] == "a" * 64
    markdown_sha = hashlib.sha256(json.dumps("source markdown").encode("utf-8")).hexdigest()
    assert merges[0]["metadata_by_language"]["zh"]["hub_binding"] == {
        "content_version_id": 17,
        "markdown_text_variant_id": 31,
        "markdown_sha256": markdown_sha,
    }
    assert first["updated_count"] == 1
    assert first["field_fill_count"] == 8
    assert second["unchanged_count"] == 1


def test_hub_sync_rejects_same_database_before_storage_initialization(monkeypatch):
    _install_fake_databases(monkeypatch, same_database=True)

    class UnexpectedStorage:
        def __init__(self, *_args, **_kwargs):
            pytest.fail("must not initialize or write the content-hub database")

    monkeypatch.setattr(storage_module, "Storage", UnexpectedStorage)
    with pytest.raises(ContentHubError, match="separate PostgreSQL databases"):
        sync_content_hub_catalog_metadata("postgresql://target.invalid/app")


def test_legacy_sqlite_catalog_schema_searches_bilingual_values():
    storage = Storage._legacy_sqlite_schema_for_validation(":memory:")
    try:
        url = "https://example.test/search.pdf"
        storage.insert_file(
            url,
            "a" * 64,
            "Legacy",
            "test",
            None,
            "search.pdf",
            "/tmp/search.pdf",
            1,
            "application/pdf",
        )
        metadata = {
            "zh": {
                "title": "中文标题",
                "summary": "中文摘要",
                "category": "Other",
                "keywords": ["中文词"],
            },
            "en": {
                "title": "English title",
                "summary": "English summary",
                "category": "Other",
                "keywords": ["englishword"],
            },
        }
        storage.upsert_catalog_item(
            {
                "url": url,
                "sha256": "a" * 64,
                "title": "Legacy",
                "summary": "legacy",
                "category": "Other",
                "keywords": ["legacy"],
                "bilingual_metadata": metadata,
            },
            pipeline_version="v1",
        )
        for term in (
            "中文标题",
            "中文摘要",
            "中文词",
            "English title",
            "English summary",
            "englishword",
        ):
            files, total = storage.query_files_with_catalog(query=term)
            assert total == 1, term
            assert files[0]["bilingual_metadata"] == metadata
    finally:
        storage.close()


def test_sync_catalog_cli_emits_json_receipt(monkeypatch, capsys):
    from argparse import Namespace

    from ai_actuarial.cli import cmd_content_hub

    receipt = {
        "success": True,
        "source_version_count": 1,
        "metadata_record_count": 2,
        "updated_count": 1,
        "unchanged_count": 0,
        "unmatched_count": 0,
        "version_changed_count": 0,
        "conflict_count": 0,
        "field_fill_count": 8,
    }
    monkeypatch.setattr(
        content_hub,
        "sync_content_hub_catalog_metadata",
        lambda target, *, schema: receipt,
    )
    args = Namespace(
        hub_cmd="metadata",
        metadata_cmd="sync-catalog",
        target_database_url="postgresql://target.invalid/app",
        schema="content_hub",
        json=True,
    )
    assert cmd_content_hub(args) == 0
    assert json.loads(capsys.readouterr().out) == receipt

"""Publisher identity regressions against owned PostgreSQL 16 schemas."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import psycopg2
import pytest

from ai_actuarial import content_hub
from ai_actuarial import local_collection_target_worker as target_worker
from ai_actuarial.api.services import read
from ai_actuarial.collectors.base import CollectionConfig
from ai_actuarial.collectors.file import FileCollector
from ai_actuarial.manifest_ingest import ingest_manifest
from ai_actuarial.source_registry import (
    correct_sources,
    export_registry,
    install_registry,
    registry_deployed_targets,
    registry_identity,
    resolve_bookmark,
    resolve_source,
    validate_registry,
)
from ai_actuarial.source_registry_cli import inventory, main, plan_corrections, sync_targets
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path, uninitialized_postgres_url_for_path
from tests.test_local_collection_target_worker import _item
from tests.test_manifest_ingest import _sample_manifest


def _seed() -> dict:
    return json.loads(
        (Path(__file__).parents[1] / "config/source_registry_seed.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def storage(tmp_path):
    store = Storage(postgres_url_for_path(tmp_path / "app.db"))
    with store.transaction():
        install_registry(store._conn, _seed(), target="test", apply=True)
    yield store
    store.close()


def _upsert(storage, url, raw="local_docling", digest="a" * 64):
    storage.upsert_file(
        url,
        digest,
        "AI paper",
        raw,
        "https://www.casact.org/discovery",
        "paper.pdf",
        "paper.pdf",
        4,
        "application/pdf",
        None,
        None,
        "2025-03",
    )


def _record(url, *, old=None, new="cas", raw="local_docling"):
    return {
        "url": url,
        "raw_sha256": "a" * 64,
        "raw_source_site": raw,
        "old_source_key": old,
        "new_source_key": new,
        "reason": "verified exact article",
        "evidence": ["https://www.casact.org/about"],
    }


def _apply_reviewed(connection, records, *, hub, apply=True, request_id=None):
    """Exercise the actual dry-run/apply contract for fixture corrections."""
    assert apply is True
    preview = correct_sources(connection, records, hub=hub, apply=False, request_id=request_id)
    return correct_sources(
        connection,
        preview["request_body"]["records"],
        hub=hub,
        apply=True,
        request_id=preview["request_id"],
        reconfirm_same_key=preview["request_body"]["reconfirm_same_key"],
    )


def test_pending_filter_matches_visible_source_count_before_registry_bootstrap(tmp_path):
    store = Storage(postgres_url_for_path(tmp_path / "empty-registry.db"))
    try:
        _upsert(store, "https://unverified.example/unseeded.pdf", "Quick Check")
        assert store._conn.execute("SELECT COUNT(*) FROM canonical_sources").fetchone()[0] == 0
        assert resolve_bookmark(store._conn, " Pending ") == ("pending", "exact_key")
        options = read.list_sources(db_path=store.database)
        assert options["sources"] == ["pending"]
        assert options["source_options"][0]["count"] == 1
        files, count = store.query_files_with_catalog(source="pending")
        assert count == len(files) == options["source_options"][0]["count"] == 1
        assert files[0]["source_key"] == "pending"
    finally:
        store.close()


def test_app_correction_serializes_with_import_after_old_source_key_read(storage, monkeypatch):
    url = "https://cdn.example/concurrent-source-correction.pdf"
    _upsert(storage, url)
    importer = Storage(storage.database)
    old_key_read = threading.Event()
    resume_import = threading.Event()
    correction_file_lock_attempted = threading.Event()
    correction_done = threading.Event()
    outcomes = {}
    original_execute = importer._conn.execute

    def paused_import_execute(statement, parameters=None):
        cursor = original_execute(statement, parameters)
        if statement == "SELECT sha256, source_key FROM files WHERE url = ?":
            row = cursor.fetchone()
            outcomes["import_old_key"] = row[1]
            old_key_read.set()
            if not resume_import.wait(10):
                raise TimeoutError("import was not resumed")
            return SimpleNamespace(fetchone=lambda: row)
        return cursor

    monkeypatch.setattr(importer._conn, "execute", paused_import_execute)

    class CorrectionCursor(psycopg2.extensions.cursor):
        def execute(self, query, variables=None):
            if query == "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))" and variables == (
                f"file:{url}",
            ):
                correction_file_lock_attempted.set()
            return super().execute(query, variables)

    correction_connection = psycopg2.connect(storage.database._url, cursor_factory=CorrectionCursor)

    def run_import():
        try:
            _upsert(importer, url)
        except Exception as exc:
            outcomes["import_error"] = repr(exc)

    def run_correction():
        try:
            with correction_connection:
                outcomes["correction"] = _apply_reviewed(
                    correction_connection, [_record(url, old="pending")], hub=False, apply=True
                )
        except Exception as exc:
            outcomes["correction_error"] = repr(exc)
        finally:
            correction_done.set()

    import_thread = threading.Thread(target=run_import)
    correction_thread = threading.Thread(target=run_correction)
    correction_started = False
    import_thread.start()
    try:
        assert old_key_read.wait(10), "import did not reach its old-key snapshot"
        assert outcomes["import_old_key"] == "pending"
        correction_thread.start()
        correction_started = True
        assert correction_file_lock_attempted.wait(
            10
        ), "correction did not attempt Storage's native per-URL lock"
        assert not correction_done.wait(0.25), "correction passed the paused import's file lock"
    finally:
        resume_import.set()
        import_thread.join(15)
        if correction_started:
            correction_thread.join(15)
        importer.close()
        correction_connection.close()

    assert not import_thread.is_alive()
    assert not correction_thread.is_alive()
    assert "import_error" not in outcomes, outcomes.get("import_error")
    assert "correction_error" not in outcomes, outcomes.get("correction_error")
    assert outcomes["correction"]["records"][0]["status"] == "applied"
    final = storage.get_file_with_catalog(url)
    assert final["source_key"] == "cas"
    assert final["source_site"] == "local_docling"
    assert final["sha256"] == "a" * 64


def test_seed_roundtrip_versions_hash_and_replica_replay(storage):
    exported = export_registry(storage._conn)
    assert exported == validate_registry(_seed())
    with storage.transaction():
        repeated = install_registry(storage._conn, exported, target="test", apply=True)
    assert repeated["status"] == "unchanged"
    with pytest.raises(ValueError, match="hash mismatch"):
        install_registry(
            storage._conn, {**exported, "registry_sha256": "0" * 64}, target="test", apply=True
        )
    changed = copy.deepcopy(_seed())
    changed["registry_version"] = 2
    changed["sources"][1]["name_en"] += " updated"
    with storage.transaction():
        install_registry(storage._conn, changed, target="test", apply=True)
    with pytest.raises(ValueError, match="stale"):
        install_registry(storage._conn, exported, target="test", apply=True)
    assert export_registry(storage._conn)["registry_version"] == 2


@pytest.mark.parametrize("override", ["cas", "pending"])
def test_exact_override_survives_alias_changes_and_rollback_releases_to_current_alias(
    storage, override
):
    url = "https://www.casact.org/exact-identity.pdf"
    _upsert(storage, url)
    record = _record(url, old="cas", new=override)
    with storage.transaction():
        applied = _apply_reviewed(storage._conn, [record], hub=False, apply=True)
    row = applied["records"][0]
    assert row["status"] == "applied"
    assert row["old_override"] == {
        "exists": False,
        "source_key": None,
        "correction_receipt_id": None,
    }
    assert row["new_override"] == {
        "exists": True,
        "source_key": override,
        "correction_receipt_id": applied["receipt_id"],
    }
    with storage.transaction():
        assert (
            _apply_reviewed(storage._conn, [record], hub=False, apply=True)["records"][0]["status"]
            == "unchanged"
        )
    revision = export_registry(storage._conn)
    revision.pop("registry_sha256")
    revision["registry_version"] = 2
    for alias in revision["aliases"]:
        if alias["alias_kind"] == "hostname" and alias["alias_norm"] == "www.casact.org":
            alias["source_key"] = "soa"
    with storage.transaction():
        install_registry(storage._conn, revision, target="test", apply=True)
    assert storage.get_file_with_catalog(url)["source_key"] == override
    assert storage._project_source({"url": url})["source_key"] == override
    assert storage.query_files_with_catalog(source=override)[1] == 1
    with storage.transaction():
        released = correct_sources(
            storage._conn, [], hub=False, apply=True, rollback=applied["receipt_id"]
        )
    assert released["records"][0]["status"] == "applied"
    assert storage.get_file_with_catalog(url)["source_key"] == "soa"
    assert storage.get_file_with_catalog(url)["source_override_key"] is None
    assert storage.query_files_with_catalog(source="soa")[1] == 1
    # A second exact operation restores the previous explicit state, not its old alias cache.
    with storage.transaction():
        first = _apply_reviewed(
            storage._conn, [_record(url, old="soa", new="pending")], hub=False, apply=True
        )
        second = _apply_reviewed(
            storage._conn, [_record(url, old="pending", new="cas")], hub=False, apply=True
        )
        correct_sources(storage._conn, [], hub=False, apply=True, rollback=second["receipt_id"])
    assert storage.get_file_with_catalog(url)["source_override_key"] == "pending"
    with storage.transaction():
        correct_sources(storage._conn, [], hub=False, apply=True, rollback=first["receipt_id"])
    assert storage.get_file_with_catalog(url)["source_key"] == "soa"


def test_non_web_name_alias_updates_existing_article_without_replay(storage):
    url = "file:///existing-authority.pdf"
    _upsert(storage, url, "Synthetic publisher name")
    assert storage.get_file_with_catalog(url)["source_key"] == "pending"
    for version, key in ((2, "cas"), (3, None)):
        revision = export_registry(storage._conn)
        revision.pop("registry_sha256")
        revision["registry_version"] = version
        alias = next(
            (row for row in revision["aliases"] if row["alias_norm"] == "synthetic publisher name"),
            None,
        )
        if alias is None:
            alias = {
                "alias_norm": "synthetic publisher name",
                "alias_kind": "name",
                "evidence": ["synthetic verified original"],
            }
            revision["aliases"].append(alias)
        alias.update(source_key=key, resolution_status="verified" if key else "ambiguous")
        with storage.transaction():
            install_registry(storage._conn, revision, target="test", apply=True)
        assert storage.get_file_with_catalog(url)["source_key"] == (key or "pending")
        assert storage.query_files_with_catalog(source=key or "pending")[1] == 1
    assert storage._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0


def test_inflight_auto_cache_write_cannot_hide_committed_alias_revision(storage, monkeypatch):
    url = "https://inflight-publisher.example/article.pdf"
    _upsert(storage, url)
    importer = Storage(storage.database)
    observed = threading.Event()
    release = threading.Event()
    errors = []
    original = importer._conn.execute

    def pause(statement, parameters=None):
        cursor = original(statement, parameters)
        if statement == "SELECT sha256, source_key FROM files WHERE url = ?":
            row = cursor.fetchone()
            assert row[1] == "pending"
            observed.set()
            if not release.wait(10):
                raise TimeoutError("inflight importer was not released")
            return SimpleNamespace(fetchone=lambda: row)
        return cursor

    monkeypatch.setattr(importer._conn, "execute", pause)

    def import_article():
        try:
            _upsert(importer, url)
        except Exception as exc:
            errors.append(repr(exc))

    thread = threading.Thread(target=import_article)
    thread.start()
    try:
        assert observed.wait(10)
        revision = export_registry(storage._conn)
        revision.pop("registry_sha256")
        revision["registry_version"] = 2
        revision["aliases"].append(
            {
                "alias_norm": "inflight-publisher.example",
                "alias_kind": "hostname",
                "source_key": "cas",
                "resolution_status": "verified",
                "evidence": ["synthetic original publisher"],
            }
        )
        with storage.transaction():
            install_registry(storage._conn, revision, target="test", apply=True)
        assert storage.get_file_with_catalog(url)["source_key"] == "cas"
    finally:
        release.set()
        thread.join(15)
        importer.close()
    assert not thread.is_alive()
    assert not errors
    assert (
        storage._conn.execute("SELECT source_key FROM files WHERE url=?", (url,)).fetchone()[0]
        == "pending"
    )
    assert storage.get_file_with_catalog(url)["source_key"] == "cas"
    assert storage.query_files_with_catalog(source="cas")[1] == 1
    assert read.list_sources(db_path=storage.database)["sources"] == ["cas"]
    assert storage._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0


@pytest.mark.parametrize("format_version", [None, 99])
def test_unknown_receipt_format_cannot_guess_or_remove_overlay(storage, format_version):
    url = "https://cdn.example/unknown-receipt.pdf"
    _upsert(storage, url)
    with storage.transaction():
        receipt = _apply_reviewed(
            storage._conn, [_record(url, old="pending")], hub=False, apply=True
        )
    unknown = {**receipt, "receipt_id": "unknown-format", "overlay_state_version": format_version}
    storage._conn.execute(
        "INSERT INTO source_correction_receipts(receipt_id,receipt_json) VALUES(?,?::jsonb)",
        (unknown["receipt_id"], json.dumps(unknown)),
    )
    with pytest.raises(ValueError, match="overlay state; rerun reviewed dry-run"):
        with storage.transaction():
            correct_sources(
                storage._conn, [], hub=False, apply=True, rollback=unknown["receipt_id"]
            )
    assert storage.get_file_with_catalog(url)["source_override_key"] == "cas"


@pytest.mark.parametrize(
    ("url", "raw", "key"),
    [
        ("https://www.casact.org/paper.pdf", "Quick Check", "cas"),
        ("https://www.casact.org/paper.pdf", "CASA", "cas"),
        ("https://casa.example/paper.pdf", "CAS", "pending"),
        ("https://cdn.example/paper.pdf", "task", "pending"),
        ("https://www.actuarieskenya.or.ke/paper.pdf", "task", "actuarial_society_kenya"),
        ("file:///paper.pdf", "task", "pending"),
        ("https://www.soa.org/research/ai.pdf", "soa-research", "soa"),
        ("https://actuaries.org.hk/paper.pdf", "iaa", "ashk"),
        ("https://actuaries.org/paper.pdf", "ashk", "iaa"),
    ],
)
def test_exact_publisher_resolution(storage, url, raw, key):
    _upsert(storage, url, raw)
    result = storage.get_file_with_catalog(url)
    assert result["source_key"] == key
    assert result["source_site"] == raw
    assert resolve_source(storage._conn, url=url, raw_source=raw) == key


def test_visible_counts_exact_filter_pending_and_legacy_bookmarks(storage):
    _upsert(storage, "https://www.casact.org/visible.pdf", "CAS")
    _upsert(storage, "https://casa.example/visible.pdf", "CASA")
    _upsert(storage, "https://www.soa.org/hidden.pdf", "SOA")
    _upsert(storage, "https://www.actuarieskenya.or.ke/deleted.pdf", "task")
    storage._conn.execute("UPDATE files SET local_path='' WHERE source_site='SOA'")
    storage._conn.execute("UPDATE files SET deleted_at='2026-01-01' WHERE source_site='task'")
    storage._conn.commit()
    options = storage.get_source_options()
    assert {row["source_key"]: row["count"] for row in options} == {"cas": 1, "pending": 1}
    for option in options:
        files, total = storage.query_files_with_catalog(source=option["source_key"])
        assert total == option["count"] == len(files)
    assert storage.query_files_with_catalog(source="Casualty Actuarial Society")[1] == 1
    assert storage.query_files_with_catalog(source="CAS")[1] == 1
    assert storage.query_files_with_catalog(source="casa")[1] == 0
    assert storage.query_files_with_catalog(source="task")[1] == 0
    assert resolve_bookmark(storage._conn, "task") == (None, "ambiguous")
    payload = read.list_sources(db_path=storage.database)
    assert payload["sources"] == ["cas", "pending"]
    assert payload["source_options"] == options
    summary = inventory(storage._conn, hub=False)
    assert sum(row["visible_articles"] for row in summary["raw_sources"]) == 2
    assert sum(row["hidden_or_deleted_articles"] for row in summary["raw_sources"]) == 2


def test_correction_apply_rerun_rollback_conflict_and_content_unchanged(storage):
    url = "https://cdn.example/article.pdf"
    _upsert(storage, url)
    storage.update_file_markdown(url, "# Exact immutable Markdown", "fixture")
    storage._conn.execute(
        "INSERT INTO weekly_snapshots(id,period_start,period_end,generated_at,file_count) VALUES('weekly','2026-01-01','2026-01-08','2026-01-08',1)"
    )
    storage._conn.execute(
        "INSERT INTO weekly_snapshot_members VALUES('weekly',?,'2026-01-02','paper.pdf',0)", (url,)
    )
    storage._conn.execute(
        "INSERT INTO rag_knowledge_bases(kb_id,name,embedding_model,chunk_size,chunk_overlap,index_type,created_at,updated_at) VALUES('ai','AI','fixture',512,50,'flat','2026-01-01','2026-01-01')"
    )
    storage._conn.execute(
        "INSERT INTO rag_kb_files(kb_id,file_url,added_at,chunk_count,indexed_at) VALUES('ai',?,'2026-01-01',1,'2026-01-01')",
        (url,),
    )
    storage._conn.execute(
        "INSERT INTO chunk_profiles VALUES('p','fixture','profilehash','{}',512,50,'fixture','fixture','1','2026-01-01','2026-01-01')"
    )
    storage._conn.execute(
        "INSERT INTO file_chunk_sets(chunk_set_id,file_url,profile_id,markdown_hash,created_at,updated_at) VALUES('set',?,'p','mdhash','2026-01-01','2026-01-01')",
        (url,),
    )
    storage._conn.execute(
        "INSERT INTO global_chunks(chunk_id,chunk_set_id,chunk_index,content,created_at) VALUES('chunk','set',0,'exact content','2026-01-01')"
    )
    storage._conn.execute(
        "INSERT INTO kb_index_versions(index_version_id,kb_id,embedding_model,index_type,status,created_at) VALUES('index','ai','fixture','flat','ready','2026-01-01')"
    )
    storage._conn.execute("INSERT INTO kb_index_items VALUES('index','chunk',0)")
    immutable_tables = (
        "weekly_snapshots",
        "weekly_snapshot_members",
        "rag_kb_files",
        "global_chunks",
        "kb_index_items",
        "kb_index_versions",
    )

    def memberships():
        return {
            table: [
                tuple(row) for row in storage._conn.execute(f"SELECT * FROM {table}").fetchall()
            ]
            for table in immutable_tables
        }

    original_memberships = memberships()
    before = dict(storage._conn.execute("SELECT * FROM files WHERE url=?", (url,)).fetchone())
    before_catalog = dict(
        storage._conn.execute("SELECT * FROM catalog_items WHERE file_url=?", (url,)).fetchone()
    )
    record = _record(url, old="pending")
    with storage.transaction():
        dry = correct_sources(storage._conn, [record], hub=False, apply=False)
    assert dry["records"][0]["status"] == "would_apply"
    assert storage.get_file_with_catalog(url)["source_key"] == "pending"
    assert memberships() == original_memberships
    with storage.transaction():
        applied = _apply_reviewed(storage._conn, [record], hub=False, apply=True)
    assert applied["records"][0]["status"] == "applied"
    assert dict(storage._conn.execute("SELECT * FROM files WHERE url=?", (url,)).fetchone()) == {
        **before,
        "source_key": "cas",
    }
    with storage.transaction():
        assert (
            _apply_reviewed(storage._conn, [record], hub=False, apply=True)["records"][0]["status"]
            == "unchanged"
        )
    # A historical import replay must retain the exact corrected key.
    _upsert(storage, url)
    assert storage.get_file_with_catalog(url)["source_key"] == "cas"
    after = dict(storage._conn.execute("SELECT * FROM files WHERE url=?", (url,)).fetchone())
    # Import replay has the existing last_seen/crawl_time contract, unrelated to correction.
    for field in ("source_key", "last_seen", "crawl_time"):
        before.pop(field)
        after.pop(field)
    assert before == after
    assert before_catalog == dict(
        storage._conn.execute("SELECT * FROM catalog_items WHERE file_url=?", (url,)).fetchone()
    )
    with storage.transaction():
        rolled = correct_sources(
            storage._conn, [], hub=False, apply=True, rollback=applied["receipt_id"]
        )
    assert rolled["records"][0]["status"] == "applied"
    assert storage.get_file_with_catalog(url)["source_key"] == "pending"
    storage._conn.execute(
        "INSERT INTO source_projection(url,raw_sha256,source_key) VALUES (?,?,'soa') ON CONFLICT(url,raw_sha256) DO UPDATE SET source_key='soa'",
        (url, "a" * 64),
    )
    with storage.transaction():
        conflict = _apply_reviewed(storage._conn, [record], hub=False, apply=True)
    assert conflict["records"][0]["status"] == "conflict"
    assert storage.get_file_with_catalog(url)["source_key"] == "soa"
    assert memberships() == original_memberships


@pytest.mark.parametrize("shape", ["scheduled", "quick_check", "url", "search"])
def test_real_crawler_import_shapes_use_publisher_not_task(storage, tmp_path, monkeypatch, shape):
    from ai_actuarial.collectors.scheduled import ScheduledCollector
    from ai_actuarial.collectors.url import URLCollector
    from ai_actuarial.crawler import Crawler, SiteConfig
    from ai_actuarial.task_runtime import NativeTaskRuntime

    crawler = Crawler(storage, str(tmp_path / "downloads"), "fixture")
    url = f"https://www.casact.org/{shape}.pdf"
    config = SiteConfig(name="Scheduled collection", url=url)
    if shape == "quick_check":
        config = NativeTaskRuntime.__new__(NativeTaskRuntime)._quick_check_site_config(
            {}, {"url": url}
        )
    raw_label = {
        "scheduled": "Scheduled collection",
        "quick_check": "Quick Check",
        "url": "URL Collection",
        "search": "Web Search (Brave)",
    }[shape]

    def save(site_config, *args, **kwargs):
        staged = tmp_path / (shape + ".part")
        raw = ("PDF fixture " + shape).encode()
        staged.write_bytes(raw)
        result = crawler._handle_file(
            url,
            staged,
            {"content-type": "application/pdf"},
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            site_config,
            "https://www.casact.org/discovery",
            source_site_override=raw_label,
        )
        return [result] if result else []

    if shape in {"scheduled", "quick_check"}:
        monkeypatch.setattr(crawler, "crawl_site", save)
        result = ScheduledCollector(storage, crawler).collect(
            CollectionConfig(name=raw_label, source_type=shape, metadata={"site_configs": [config]})
        )
        assert result.items_downloaded == 1
    elif shape == "url":
        monkeypatch.setattr(
            crawler,
            "scan_page_for_files",
            lambda page_url, site_config, **kwargs: save(site_config),
        )
        result = URLCollector(storage, crawler).collect(
            CollectionConfig(name=raw_label, source_type="url", metadata={"urls": [url]})
        )
        assert result.items_downloaded == 1
    else:
        # Search runtime supplies result.source as the crawler override.
        save(config)
    saved = storage.get_file_with_catalog(url)
    assert saved["source_key"] == "cas"
    assert saved["source_site"] == raw_label


def test_crawler_page_content_direct_insert_and_target_payload(storage, tmp_path, monkeypatch):
    from ai_actuarial.crawler import Crawler, SiteConfig

    crawler = Crawler(storage, str(tmp_path / "downloads"), "fixture")
    monkeypatch.setattr(
        crawler, "_extract_text_from_html", lambda *_args: "Publisher article " * 40
    )
    url = "https://www.soa.org/page"
    saved = crawler._handle_page_content(
        url, "<html>fixture</html>", "AI article", None, SiteConfig(name="Quick Check", url=url)
    )
    assert saved
    assert storage.get_file_with_catalog(url)["source_key"] == "soa"

    monkeypatch.setattr("ai_actuarial.capacity.ensure_capacity", lambda **kwargs: None)
    item = _item("https://www.casact.org/target.pdf", b"target PDF bytes", "# Original Markdown")
    item.update(registry_identity(storage._conn), source_key="cas", source_override_key=None)
    normalized = target_worker._normalize_item(item, "china", ["AI", "Pricing", "Other"])

    class Manager:
        def add_files_to_kb(self, kb_id, urls):
            return {"added_count": 0, "skipped_count": 0}

    ack, _needs_chunks = target_worker._write_item(
        storage, Manager(), normalized, tmp_path / "target", []
    )
    assert ack["source_key"] == "cas"
    assert ack["registry_sha256"] == item["registry_sha256"]
    assert storage.get_file_with_catalog(item["url"])["source_site"] == "cas"
    assert (
        target_worker._write_item(storage, Manager(), normalized, tmp_path / "target", [])[0][
            "status"
        ]
        == "already_current"
    )


def test_manifest_and_file_real_import_shapes_preserve_provenance(storage, tmp_path):
    manifest = _sample_manifest()
    manifest["source"]["site_name"] = "URL Collection"
    ingest_manifest(storage, manifest)
    for asset in manifest["downloaded_assets"]:
        result = storage.get_file_with_catalog(asset["url"])
        assert result["source_key"] == "soa"
        assert result["source_site"] == "URL Collection"
    file = tmp_path / "local.pdf"
    file.write_bytes(b"a unique local file")
    collector = FileCollector(storage, str(tmp_path / "downloads"))
    result = collector.collect(
        CollectionConfig(
            name="File Import", source_type="file", metadata={"file_paths": [str(file)]}
        )
    )
    assert result.items_downloaded == 1
    saved = storage.get_file_with_catalog(f"file://{file}")
    assert saved["source_key"] == "pending"
    assert saved["source_site"] == "Local Import"


def test_target_registry_receiver_and_article_revision_validation(storage):
    reply = target_worker.apply_source_registry(
        {"target": "china", "registry": export_registry(storage._conn), "apply": True},
        storage_factory=lambda: Storage(storage.database),
    )
    assert reply["target"] == "china"
    assert reply["status"] == "unchanged"
    item = _item("https://www.casact.org/paper.pdf", b"original bytes", "# original Markdown")
    item.update(registry_identity(storage._conn), source_key="cas", source_override_key=None)
    normalized = target_worker._normalize_item(item, "china", ["AI", "Pricing", "Other"])
    target_worker._check_source_identity(storage, normalized)
    stale = {**normalized, "registry_version": 0}
    with pytest.raises(ValueError, match="revision/hash"):
        target_worker._check_source_identity(storage, stale)
    from ai_actuarial.local_collection_runtime import _target_metadata_fingerprint

    assert normalized["metadata_fingerprint"] == _target_metadata_fingerprint(item)


def test_published_target_batch_preserves_native_memberships_and_source_ack(
    storage, tmp_path, monkeypatch
):
    monkeypatch.setattr("ai_actuarial.capacity.ensure_capacity", lambda **kwargs: None)
    monkeypatch.setattr("ai_actuarial.capacity.capacity_status", lambda **kwargs: {"status": "ok"})
    for kb_id in ("ai", "all"):
        storage._conn.execute(
            "INSERT INTO rag_knowledge_bases(kb_id,name,embedding_model,chunk_size,chunk_overlap,index_type,created_at,updated_at) VALUES(?,?,'fixture',512,50,'flat','2026-01-01','2026-01-01')",
            (kb_id, kb_id),
        )

    class Manager:
        def __init__(self, store):
            self.store = store

        def get_kb(self, kb_id):
            return SimpleNamespace(
                kb_id=kb_id,
                embedding_provider="fixture",
                embedding_model="fixture",
                embedding_dimension=1024,
                embedding_identity_key="fixture",
            )

        def add_files_to_kb(self, kb_id, urls):
            for url in urls:
                self.store._conn.execute(
                    "INSERT INTO rag_kb_files(kb_id,file_url,added_at) VALUES(?,?,'2026-01-01')",
                    (kb_id, url),
                )
            return {"added_count": len(urls), "skipped_count": 0}

    runtime = SimpleNamespace(
        data_root=tmp_path,
        _load_site_config=lambda: {},
        _resolve_db_path=lambda config: storage.database,
    )
    item = _item(
        "https://www.casact.org/published-batch.pdf", b"batch original bytes", "# original content"
    )
    item.update(registry_identity(storage._conn), source_key="cas", source_override_key=None)
    result = target_worker.apply_batch(
        {"target": "china", "items": [item], "approved_categories": ["AI", "Pricing", "Other"]},
        runtime_factory=lambda: runtime,
        storage_factory=lambda *args, **kwargs: Storage(storage.database),
        manager_factory=Manager,
        ready_builder=lambda *args: {"test_only_ready_stub": True},
    )
    assert result["failures"] == []
    ack = result["acknowledgements"][0]
    assert ack["source_key"] == "cas"
    assert ack["registry_sha256"] == item["registry_sha256"]
    assert {
        row[0]
        for row in storage._conn.execute(
            "SELECT kb_id FROM rag_kb_files WHERE file_url=?", (item["url"],)
        ).fetchall()
    } == {"ai", "all"}


def test_sync_requires_exact_target_version_hash_receipts(storage, monkeypatch):
    from ai_actuarial import local_collection_runtime as runtime

    registry = export_registry(storage._conn)
    monkeypatch.setattr(
        runtime,
        "_invoke_target_worker",
        lambda config, target, payload: {
            "target": target,
            "receipt_id": target,
            "registry_version": registry["registry_version"],
            "registry_sha256": registry["registry_sha256"],
            "status": "applied",
        },
    )
    assert len(sync_targets(storage._conn, {}, apply=True)["targets"]) == 2
    monkeypatch.setattr(
        runtime,
        "_invoke_target_worker",
        lambda config, target, payload: {
            "target": target,
            "registry_version": 99,
            "registry_sha256": registry["registry_sha256"],
            "status": "applied",
        },
    )
    rejected = sync_targets(storage._conn, {}, apply=True)
    assert rejected["status"] == "failed"
    assert len(rejected["failures"]) == 2
    assert all("acknowledge" in row["error"] for row in rejected["failures"])


def test_sync_reports_requested_and_current_revision_when_hub_advances(storage, monkeypatch):
    from ai_actuarial import local_collection_runtime as runtime

    original = export_registry(storage._conn)

    def receive(config, target, payload):
        if target == "china":
            next_revision = copy.deepcopy(_seed())
            next_revision["registry_version"] = 2
            next_revision["sources"][1]["name_en"] = "New PG display name during sync"
            with storage.transaction():
                install_registry(storage._conn, next_revision, target="hub", apply=True)
        return {
            "target": target,
            "receipt_id": target + "-old",
            "registry_version": original["registry_version"],
            "registry_sha256": original["registry_sha256"],
            "status": "applied",
        }

    monkeypatch.setattr(runtime, "_invoke_target_worker", receive)
    result = sync_targets(storage._conn, {}, apply=True)
    assert result["status"] == "hub_advanced"
    assert result["requested_registry"]["registry_version"] == 1
    assert result["current_hub_registry"]["registry_version"] == 2
    assert registry_deployed_targets(storage._conn) == []


@pytest.mark.parametrize("failed_target", ["china", "overseas"])
def test_partial_replica_receipts_allow_only_that_target_to_dispatch(
    storage, tmp_path, monkeypatch, failed_target
):
    from ai_actuarial import local_collection_runtime as runtime

    registry = export_registry(storage._conn)
    good_target = "overseas" if failed_target == "china" else "china"

    def receive(config, target, payload):
        if target == failed_target:
            raise RuntimeError(f"{target} temporarily unavailable")
        return {
            "target": target,
            "receipt_id": target + "-current",
            "registry_version": registry["registry_version"],
            "registry_sha256": registry["registry_sha256"],
            "status": "applied",
        }

    monkeypatch.setattr(runtime, "_invoke_target_worker", receive)
    result = sync_targets(storage._conn, {}, apply=True)
    assert result["status"] == "partial"
    assert result["failures"][0]["target"] == failed_target
    assert registry_deployed_targets(storage._conn) == [good_target]
    raw = b"exact dispatch bytes"
    artifact = tmp_path / "dispatch.pdf"
    artifact.write_bytes(raw)
    item = _item("https://www.casact.org/dispatch.pdf", raw, "# original")
    item.update(
        registry_identity(storage._conn),
        source_key="cas",
        source_override_key=None,
        source_registry_targets=registry_deployed_targets(storage._conn),
        artifact_path=str(artifact),
    )
    calls = []
    monkeypatch.setattr(
        runtime,
        "_invoke_target_worker",
        lambda config, target, payload: calls.append(target) or {"target": target},
    )
    assert runtime._stream_target({}, good_target, [item], False)["target"] == good_target
    with pytest.raises(runtime.RuntimeErrorSafe, match=f"{failed_target} has not acknowledged"):
        runtime._stream_target({}, failed_target, [item], False)
    assert calls == [good_target]

    # Follow the same normal dispatch loop after the aggregate partial sync result.
    calls.clear()
    item["ai_candidate"] = True
    article_key = runtime._file_key(item["url"], item["raw_sha256"])
    state = {
        "articles": {
            article_key: {
                **item,
                "site_id": "cas",
                "stage": "downloaded",
                "discovery_sites": ["fixture"],
            }
        },
        "target_acks": {},
    }
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(runtime, "content_hub_read_version", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "_prepare_hub_article", lambda *args, **kwargs: (item, True, True))

    def article_worker(config, target, payload):
        calls.append(target)
        return {
            "target": target,
            "capacity": {"status": "ok"},
            "failures": [],
            "ready_status": "succeeded",
            "acknowledgements": [
                {
                    "content_version_id": item["content_version_id"],
                    "raw_sha256": item["raw_sha256"],
                    "metadata_fingerprint": runtime._target_metadata_fingerprint(item),
                    "status": "written",
                    **{
                        field: item[field]
                        for field in (
                            "source_key",
                            "source_override_key",
                            "registry_version",
                            "registry_sha256",
                        )
                    },
                }
            ],
        }

    monkeypatch.setattr(runtime, "_invoke_target_worker", article_worker)
    summary = runtime._process_articles(
        "fixture",
        state,
        {"state_root": str(tmp_path), "data_root": str(tmp_path)},
        "unused-hub",
        preview=False,
        article_limit=1,
    )
    assert calls == [good_target]
    assert summary["target"][good_target]["acknowledged"] == 1
    assert summary["target"][good_target]["ready_status"] == "succeeded"
    assert (
        state["target_acks"][runtime._target_ack_key(good_target, item)]["status"] == "acknowledged"
    )
    assert summary["target"][failed_target]["pending"] == 1
    assert state["target_acks"][runtime._target_ack_key(failed_target, item)]["status"] == "pending"


def test_hub_overlay_preserves_every_immutable_table_and_rollback(tmp_path):
    url = uninitialized_postgres_url_for_path(tmp_path / "hub.db")
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = cursor.fetchone()[0]
    content_hub.apply_content_hub_schema(url, schema=schema)
    article_url = "https://cdn.example/kenya.pdf"
    raw = b"Kenya original PDF bytes"
    digest = hashlib.sha256(raw).hexdigest()
    ingested = content_hub.ingest_live_article(
        canonical_url=article_url,
        title="Kenya original",
        raw_bytes=raw,
        markdown="# Kenya AI article",
        source_site="task",
        source_page_url="https://www.actuarieskenya.or.ke/",
        content_type="application/pdf",
        data_root=tmp_path / "data",
        database_url=url,
        schema=schema,
    )
    package = {
        "title": "Kenya AI article",
        "summary": "Kenya AI article",
        "category": "AI",
        "keywords": ["AI"],
    }
    content_hub.save_live_enrichment(
        content_version_id=ingested["content_version_id"],
        markdown_text_variant_id=ingested["markdown_text_variant_id"],
        markdown_sha256=ingested["markdown_sha256"],
        primary_category="AI",
        bilingual_metadata={"zh": package, "en": package},
        categories=[{"key": "AI", "evidence": ["Kenya AI article"]}],
        date_facts={"publication_date": None, "revision_date": None, "document_version_date": None},
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="source-fixture",
        run_id="source-fixture",
        database_url=url,
        schema=schema,
    )
    with psycopg2.connect(url) as connection:
        install_registry(connection, _seed(), target="hub", apply=True)
        with connection.cursor() as cursor:
            immutable = (
                "source_snapshots",
                "source_record_map",
                "source_file_observations",
                "text_variants",
                "content_versions",
                "content_blobs",
                "bilingual_metadata",
                "article_enrichment_annotations",
            )

            def snapshot():
                result = {}
                for table in immutable:
                    cursor.execute(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY 1")
                    result[table] = cursor.fetchall()
                return result

            before = snapshot()
            record = {
                **_record(article_url, new="actuarial_society_kenya", raw="task"),
                "raw_sha256": digest,
                "evidence": ["Exact Kenya original cover and official discovery page"],
            }
            applied = _apply_reviewed(connection, [record], hub=True, apply=True)
            assert applied["records"][0]["status"] == "applied"
            assert (
                resolve_source(connection, url=article_url, raw_source="task", raw_sha256=digest)
                == "actuarial_society_kenya"
            )
            assert snapshot() == before
            planned = plan_corrections(connection, hub=True)
            assert not any(row["url"] == article_url for row in planned["records"])
            assert (
                _apply_reviewed(connection, [record], hub=True, apply=True)["records"][0]["status"]
                == "unchanged"
            )
            assert (
                correct_sources(
                    connection, [], hub=True, apply=True, rollback=applied["receipt_id"]
                )["records"][0]["status"]
                == "applied"
            )
            assert snapshot() == before


def test_cli_readonly_dry_run_json_and_apply_receipts(storage, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CONTENT_HUB_DATABASE_URL", storage.database._url)
    manifest = tmp_path / "registry.json"
    manifest.write_text(json.dumps(_seed()), encoding="utf-8")
    with storage._conn.cursor() as cursor:
        cursor.execute("SELECT current_schema()")
        schema = cursor.fetchone()[0]
    assert (
        main(["publish", "--hub", "--schema", schema, "--manifest", str(manifest), "--json"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "unchanged"
    monkeypatch.setenv("DATABASE_URL", storage.database._url)
    _upsert(storage, "https://cdn.example/cli.pdf")
    planned = plan_corrections(storage._conn, hub=False)
    assert planned["unresolved"][0]["url"] == "https://cdn.example/cli.pdf"
    manifest.write_text(
        json.dumps({"records": [_record("https://cdn.example/cli.pdf", old="pending")]}),
        encoding="utf-8",
    )
    assert main(["correct", "--manifest", str(manifest), "--json"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["records"][0]["status"] == "would_apply"
    assert dry["request_id"]
    assert dry["request_body"]["records"][0]["old_override"]["exists"] is False
    manifest.write_text(json.dumps(dry), encoding="utf-8")
    assert main(["correct", "--manifest", str(manifest), "--json"]) == 0
    preview_again = json.loads(capsys.readouterr().out)
    assert preview_again["request_body"]["reconfirm_same_key"] is False
    assert preview_again["request_id"] != dry["request_id"]
    assert main(["correct", "--manifest", str(manifest), "--apply", "--json"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["receipt_id"] == dry["request_id"]
    assert receipt["records"][0]["status"] == "applied"
    assert main(["correct", "--manifest", str(manifest), "--apply", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["records"][0]["status"] == "unchanged"
    manifest.write_text(
        json.dumps({"records": [_record("https://cdn.example/cli.pdf", old="cas")]}),
        encoding="utf-8",
    )
    assert (
        main(
            ["correct", "--manifest", str(manifest), "--request-id", "cli-reconfirmation", "--json"]
        )
        == 0
    )
    reconfirm_preview = json.loads(capsys.readouterr().out)
    assert reconfirm_preview["request_body"]["reconfirm_same_key"] is True
    assert reconfirm_preview["records"][0]["status"] == "would_apply"
    manifest.write_text(json.dumps(reconfirm_preview), encoding="utf-8")
    assert (
        main(
            [
                "correct",
                "--manifest",
                str(manifest),
                "--request-id",
                "changed-after-review",
                "--apply",
            ]
        )
        == 2
    )
    assert "cannot change" in json.loads(capsys.readouterr().out)["error"]
    assert main(["correct", "--manifest", str(manifest), "--apply"]) == 0
    reconfirmed = json.loads(capsys.readouterr().out)
    assert reconfirmed["receipt_id"] == "cli-reconfirmation"
    assert reconfirmed["records"][0]["status"] == "applied"
    assert main(["rollback", "--receipt", reconfirmed["receipt_id"], "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["records"][0]["status"] == "applied"
    rollback_args = [
        "rollback",
        "--receipt",
        receipt["receipt_id"],
        "--request-id",
        "cli-rollback-request",
        "--apply",
    ]
    assert main(rollback_args) == 0
    assert json.loads(capsys.readouterr().out)["records"][0]["status"] == "applied"
    assert main(rollback_args) == 0
    assert json.loads(capsys.readouterr().out)["records"][0]["status"] == "unchanged"


def test_hub_database_authority_rename_sync_and_stale_bootstrap(tmp_path, monkeypatch, capsys):
    from ai_actuarial import local_collection_runtime as runtime

    hub_url = uninitialized_postgres_url_for_path(tmp_path / "authority.db")
    with psycopg2.connect(hub_url) as hub:
        with hub.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = cursor.fetchone()[0]
    content_hub.apply_content_hub_schema(hub_url, schema=schema)
    seed_path = tmp_path / "bootstrap.json"
    seed_path.write_text(json.dumps(_seed()), encoding="utf-8")
    monkeypatch.setenv("CONTENT_HUB_DATABASE_URL", hub_url)
    common = ["publish", "--hub", "--schema", schema, "--apply", "--manifest"]
    assert main([*common, str(seed_path)]) == 0
    initial = json.loads(capsys.readouterr().out)
    replicas = {
        target: Storage(postgres_url_for_path(tmp_path / f"{target}.db"))
        for target in ("china", "overseas")
    }
    try:

        def receive(config, target, payload):
            return target_worker.apply_source_registry(
                payload, storage_factory=lambda: Storage(replicas[target].database)
            )

        monkeypatch.setattr(runtime, "_invoke_target_worker", receive)
        with psycopg2.connect(hub_url) as hub:
            assert len(sync_targets(hub, {}, apply=True)["targets"]) == 2
            revised = export_registry(hub)
        article_url = "https://publisher-authority.example/authority.pdf"
        originals = {}
        raw = b"authority source bytes"
        digest = hashlib.sha256(raw).hexdigest()
        for target, replica in replicas.items():
            _upsert(replica, article_url, "Quick Check", digest=digest)
            assert replica.get_file_with_catalog(article_url)["source_key"] == "pending"
            originals[target] = dict(
                replica._conn.execute("SELECT * FROM files WHERE url=?", (article_url,)).fetchone()
            )
        content_hub.ingest_live_article(
            canonical_url=article_url,
            source_site="cas",
            source_page_url="https://www.casact.org/discovery",
            title="AI authority",
            raw_bytes=raw,
            markdown="# AI authority",
            content_type="application/pdf",
            data_root=tmp_path / "hubdata",
            database_url=hub_url,
            schema=schema,
        )
        assert (
            content_hub.content_hub_read_version(article_url, digest, hub_url, schema=schema)[
                "source_key"
            ]
            == "pending"
        )
        revised["aliases"].append(
            {
                "alias_norm": "publisher-authority.example",
                "alias_kind": "hostname",
                "source_key": "cas",
                "resolution_status": "verified",
                "evidence": ["synthetic reviewed publisher"],
            }
        )
        revised.pop("registry_sha256")
        revised["registry_version"] = 2
        cas = next(row for row in revised["sources"] if row["source_key"] == "cas")
        cas.update(name_en="CAS maintained in PostgreSQL", name_zh="PostgreSQL维护的CAS")
        revision_path = tmp_path / "reviewed-revision.json"
        revision_path.write_text(json.dumps(revised), encoding="utf-8")
        assert main([*common, str(revision_path)]) == 0
        updated = json.loads(capsys.readouterr().out)
        assert updated["registry_sha256"] != initial["registry_sha256"]
        with psycopg2.connect(hub_url) as hub:
            receipts = sync_targets(hub, {}, apply=True)["targets"]
        assert all(
            row["registry_version"] == 2 and row["registry_sha256"] == updated["registry_sha256"]
            for row in receipts
        )
        for target, replica in replicas.items():
            file = read.get_file_detail(db_path=replica.database, url=article_url)
            assert (
                dict(
                    replica._conn.execute(
                        "SELECT * FROM files WHERE url=?", (article_url,)
                    ).fetchone()
                )
                == originals[target]
            )
            assert inventory(replica._conn, hub=False)["raw_sources"][0]["canonical_keys"] == {
                "cas": 1
            }
            planned = plan_corrections(replica._conn, hub=False)
            assert planned["records"] == []
            assert planned["cache_differences"][0]["cached_source_key"] == "pending"
            assert planned["cache_differences"][0]["source_key"] == "cas"
            assert (
                replica._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0
            )
            assert file["source_name_en"] == "CAS maintained in PostgreSQL"
            assert file["source_name_zh"] == "PostgreSQL维护的CAS"
            assert replica.query_files_with_catalog(source="CAS maintained in PostgreSQL")[1] == 1
            assert (
                read.list_sources(db_path=replica.database)["source_options"][0]["source_name_en"]
                == "CAS maintained in PostgreSQL"
            )
            with pytest.raises(ValueError, match="stale"):
                target_worker.apply_source_registry(
                    {"target": "china", "registry": _seed(), "apply": True},
                    storage_factory=lambda: Storage(replica.database),
                )
        for version, key in ((3, "soa"), (4, None)):
            with psycopg2.connect(hub_url) as hub:
                revision = export_registry(hub)
            revision.pop("registry_sha256")
            revision["registry_version"] = version
            alias = next(
                row
                for row in revision["aliases"]
                if row["alias_norm"] == "publisher-authority.example"
            )
            alias.update(source_key=key, resolution_status="verified" if key else "ambiguous")
            revision_path.write_text(json.dumps(revision), encoding="utf-8")
            assert main([*common, str(revision_path)]) == 0
            capsys.readouterr()
            with psycopg2.connect(hub_url) as hub:
                assert sync_targets(hub, {}, apply=True)["status"] == "synchronized"
            expected = key or "pending"
            assert (
                content_hub.content_hub_read_version(article_url, digest, hub_url, schema=schema)[
                    "source_key"
                ]
                == expected
            )
            for target, replica in replicas.items():
                assert (
                    read.get_file_detail(db_path=replica.database, url=article_url)["source_key"]
                    == expected
                )
                assert replica.query_files_with_catalog(source=expected)[1] == 1
                assert read.list_sources(db_path=replica.database)["sources"] == [expected]
                assert (
                    dict(
                        replica._conn.execute(
                            "SELECT * FROM files WHERE url=?", (article_url,)
                        ).fetchone()
                    )
                    == originals[target]
                )
                with pytest.raises(ValueError, match="stale"):
                    target_worker.apply_source_registry(
                        {"target": target, "registry": revised, "apply": True},
                        storage_factory=lambda: Storage(replica.database),
                    )
        assert main([*common, str(seed_path)]) == 2
        assert "stale" in json.loads(capsys.readouterr().out)["error"]
        with psycopg2.connect(hub_url) as hub:
            assert export_registry(hub)["registry_version"] == 4
    finally:
        for replica in replicas.values():
            replica.close()


def test_reviewed_request_id_replay_reconfirmation_and_pointer_safe_rollback(storage):
    url = "https://www.casact.org/manual-confirmation.pdf"
    _upsert(storage, url)
    record = _record(url, old="cas")
    with storage.transaction():
        dry = correct_sources(storage._conn, [record], hub=False, apply=False)
    assert dry["records"][0]["status"] == "would_apply"
    reviewed = dry["request_body"]["records"]
    with storage.transaction():
        applied = correct_sources(
            storage._conn,
            reviewed,
            hub=False,
            apply=True,
            request_id=dry["request_id"],
            reconfirm_same_key=False,
        )
    assert applied["records"][0]["status"] == "applied"
    with storage.transaction():
        replay = correct_sources(
            storage._conn,
            reviewed,
            hub=False,
            apply=True,
            request_id=dry["request_id"],
            reconfirm_same_key=False,
        )
    assert replay["records"][0]["status"] == "unchanged"
    with pytest.raises(ValueError, match="request_id conflict"), storage.transaction():
        correct_sources(
            storage._conn,
            [{**reviewed[0], "reason": "different reviewed request"}],
            hub=False,
            apply=True,
            request_id=dry["request_id"],
            reconfirm_same_key=False,
        )
    with storage.transaction():
        reconfirmed = _apply_reviewed(
            storage._conn, [record], hub=False, apply=True, request_id="new-manual-confirmation"
        )
    assert reconfirmed["records"][0]["status"] == "applied"
    assert reconfirmed["records"][0]["old_override"] == applied["records"][0]["new_override"]
    with storage.transaction():
        old_rollback = correct_sources(
            storage._conn, [], hub=False, apply=True, rollback=applied["receipt_id"]
        )
        stale_replay = correct_sources(
            storage._conn,
            reviewed,
            hub=False,
            apply=True,
            request_id=dry["request_id"],
            reconfirm_same_key=False,
        )
    assert old_rollback["records"][0]["status"] == "conflict"
    assert stale_replay["records"][0]["status"] == "conflict"
    with storage.transaction():
        restored = correct_sources(
            storage._conn,
            [],
            hub=False,
            apply=True,
            rollback=reconfirmed["receipt_id"],
            request_id="rollback-reconfirmation",
        )
        repeated = correct_sources(
            storage._conn,
            [],
            hub=False,
            apply=True,
            rollback=reconfirmed["receipt_id"],
            request_id="rollback-reconfirmation",
        )
    assert restored["records"][0]["new_override"] == applied["records"][0]["new_override"]
    assert repeated["records"][0]["status"] == "unchanged"
    with storage.transaction():
        final = correct_sources(
            storage._conn,
            [],
            hub=False,
            apply=True,
            rollback=applied["receipt_id"],
            request_id="rollback-original",
        )
        rerun = correct_sources(
            storage._conn,
            [],
            hub=False,
            apply=True,
            rollback=applied["receipt_id"],
            request_id="rollback-original",
        )
    assert final["records"][0]["status"] == "applied"
    assert rerun["records"][0]["status"] == "unchanged"
    with storage.transaction():
        repeated_without_request_id = correct_sources(
            storage._conn, [], hub=False, apply=True, rollback=applied["receipt_id"]
        )
    assert repeated_without_request_id["records"][0]["status"] == "unchanged"
    assert storage.get_file_with_catalog(url)["source_override_key"] is None


@pytest.mark.parametrize("override", ["cas", "pending"])
def test_target_marker_checks_receipted_state_without_ever_mutating_overlay(
    storage, tmp_path, monkeypatch, override
):
    monkeypatch.setattr("ai_actuarial.capacity.ensure_capacity", lambda **kwargs: None)
    item = _item("https://www.casact.org/three-state.pdf", b"marker bytes", "# AI marker")
    item.update(registry_identity(storage._conn), source_key="cas", source_override_key=None)
    manager = SimpleNamespace(add_files_to_kb=lambda *args: {"added_count": 0, "skipped_count": 0})

    def write(payload):
        normalized = target_worker._normalize_item(payload, "china", ["AI", "Pricing", "Other"])
        return target_worker._write_item(storage, manager, normalized, tmp_path / "target", [])[0]

    legacy = {
        key: value
        for key, value in item.items()
        if key not in {"registry_version", "registry_sha256", "source_key", "source_override_key"}
    }
    write(legacy)
    ack = write(item)
    assert ack["source_override_key"] is None
    assert ack["source_correction_receipt_id"] is None
    assert storage._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0
    missing = {key: value for key, value in item.items() if key != "source_override_key"}
    with pytest.raises(ValueError, match="override state is required"):
        write(missing)
    exact = {**item, "source_key": override, "source_override_key": override}
    with pytest.raises(ValueError, match="projection conflict"):
        write(exact)
    assert storage._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0
    record = {
        **_record(item["url"], old="cas", new=override, raw="cas"),
        "raw_sha256": item["raw_sha256"],
    }
    with storage.transaction():
        receipt = _apply_reviewed(storage._conn, [record], hub=False, apply=True)
    before = tuple(storage._conn.execute("SELECT * FROM source_projection").fetchone())
    ack = write(exact)
    assert ack["source_correction_receipt_id"] == receipt["receipt_id"]
    assert ack["source_override_key"] == override
    with pytest.raises(ValueError, match="projection conflict"):
        write(item)  # Explicit null states Hub intent; it cannot delete a local exact overlay.
    write(legacy)  # Missing legacy fields have no authority over the local overlay.
    assert tuple(storage._conn.execute("SELECT * FROM source_projection").fetchone()) == before
    with storage.transaction():
        rolled = correct_sources(
            storage._conn, [], hub=False, apply=True, rollback=receipt["receipt_id"]
        )
    assert rolled["records"][0]["status"] == "applied"
    with pytest.raises(ValueError, match="projection conflict"):
        write(exact)  # Old exact replay cannot resurrect a revoked override, at the same revision.
    assert storage._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0
    assert write(item)["source_override_key"] is None


def test_target_exact_marker_requires_receipt_not_an_unowned_projection(storage, tmp_path):
    url = "https://www.casact.org/unowned.pdf"
    _upsert(storage, url)
    storage._conn.execute(
        "INSERT INTO source_projection(url,raw_sha256,source_key) VALUES(?,?,'cas')",
        (url, "a" * 64),
    )
    item = _item(url, b"unused", "# marker")
    item.update(
        registry_identity(storage._conn),
        raw_sha256="a" * 64,
        source_key="cas",
        source_override_key="cas",
    )
    with pytest.raises(ValueError, match="confirmed correction receipt"):
        target_worker._write_item(storage, None, item, tmp_path, [])


@pytest.mark.parametrize("blocked_target", ["china", "overseas"])
@pytest.mark.parametrize("override", ["cas", "pending"])
def test_hub_exact_intent_and_independent_target_receipts_require_explicit_rollback(
    tmp_path, monkeypatch, blocked_target, override
):
    import ai_actuarial.local_collection_runtime as runtime

    monkeypatch.setattr("ai_actuarial.capacity.ensure_capacity", lambda **kwargs: None)
    hub_url = uninitialized_postgres_url_for_path(tmp_path / "hub-marker.db")
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = cursor.fetchone()[0]
    content_hub.apply_content_hub_schema(hub_url, schema=schema)
    with psycopg2.connect(hub_url) as connection:
        install_registry(connection, _seed(), target="hub", apply=True)
    url = "https://www.casact.org/hub-marker.pdf"
    raw, markdown = (
        b"Hub exact marker fixture",
        "# AI marker fixture\nAI methods and Pricing models",
    )
    base = _item(url, raw, markdown)
    ingested = content_hub.ingest_live_article(
        canonical_url=url,
        title=base["title"],
        raw_bytes=raw,
        markdown=markdown,
        source_site="cas",
        source_page_url="https://www.casact.org/",
        content_type="application/pdf",
        data_root=tmp_path / "hub-data",
        database_url=hub_url,
        schema=schema,
    )
    content_hub.save_live_enrichment(
        content_version_id=ingested["content_version_id"],
        markdown_text_variant_id=ingested["markdown_text_variant_id"],
        markdown_sha256=ingested["markdown_sha256"],
        primary_category="AI",
        bilingual_metadata=base["bilingual_metadata"],
        categories=base["categories"],
        date_facts=base["date_facts"],
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="marker-fixture",
        run_id="marker-fixture",
        database_url=hub_url,
        schema=schema,
    )
    monkeypatch.setattr(
        runtime,
        "content_hub_read_version",
        lambda source_url, source_sha, database: content_hub.content_hub_read_version(
            source_url, source_sha, database, schema=schema
        ),
    )
    base["content_version_id"] = ingested["content_version_id"]

    def current_item():
        refreshed, error = runtime._refresh_pending_target_item(base, hub_url)
        assert error is None
        exact = content_hub.content_hub_read_version(
            url, base["raw_sha256"], hub_url, schema=schema
        )
        listed = content_hub.content_hub_list_ai_versions(database_url=hub_url, schema=schema)[
            "versions"
        ][0]
        for field in ("source_key", "source_override_key", "registry_version", "registry_sha256"):
            assert refreshed[field] == exact[field] == listed[field]
        return refreshed

    automatic = current_item()
    assert automatic["source_override_key"] is None
    signature = automatic["source_signature"]
    annotation_digest = automatic["result_sha256"]
    replicas = {
        target: Storage(postgres_url_for_path(tmp_path / (target + ".db")))
        for target in ("china", "overseas")
    }
    manager = SimpleNamespace(add_files_to_kb=lambda *args: {"added_count": 0, "skipped_count": 0})

    def deliver(target, item):
        normalized = target_worker._normalize_item(item, target, ["AI", "Pricing", "Other"])
        return target_worker._write_item(
            replicas[target], manager, normalized, tmp_path / target, []
        )[0]

    receipts, rollbacks = {}, {}
    try:
        for target, replica in replicas.items():
            with replica.transaction():
                install_registry(replica._conn, _seed(), target=target, apply=True)
            assert deliver(target, automatic)["source_override_key"] is None
            assert (
                replica._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0
            )
        hub_record = {**_record(url, new=override, raw="cas"), "raw_sha256": base["raw_sha256"]}
        with psycopg2.connect(hub_url) as connection:
            hub_receipt = _apply_reviewed(connection, [hub_record], hub=True, apply=True)
        exact = current_item()
        assert exact["source_override_key"] == exact["source_key"] == override
        assert exact["source_signature"] == signature
        assert exact["result_sha256"] == annotation_digest
        assert exact["registry_sha256"] == automatic["registry_sha256"]
        assert runtime._target_metadata_fingerprint(exact) != runtime._target_metadata_fingerprint(
            automatic
        )
        for target, replica in replicas.items():
            with pytest.raises(ValueError, match="projection conflict"):
                deliver(target, exact)
            target_record = {
                **hub_record,
                "old_source_key": "cas",
                "upstream_receipt_id": hub_receipt["receipt_id"],
            }
            with replica.transaction():
                receipts[target] = _apply_reviewed(
                    replica._conn, [target_record], hub=False, apply=True
                )
            ack = deliver(target, exact)
            assert ack["source_correction_receipt_id"] == receipts[target]["receipt_id"]
        with psycopg2.connect(hub_url) as connection:
            hub_rollback = correct_sources(
                connection, [], hub=True, apply=True, rollback=hub_receipt["receipt_id"]
            )
        revoked = current_item()
        assert revoked["source_override_key"] is None
        for target, replica in replicas.items():
            assert replica.get_file_with_catalog(url)["source_override_key"] == override
            with pytest.raises(ValueError, match="projection conflict"):
                deliver(target, revoked)  # Hub rollback never cascades through article messages.
        # A later same-key local confirmation owns the blocked endpoint's overlay.
        blocked = replicas[blocked_target]
        with blocked.transaction():
            newer = _apply_reviewed(
                blocked._conn,
                [{**hub_record, "old_source_key": override}],
                hub=False,
                apply=True,
                request_id="later-target-local-confirmation",
            )
        for target, replica in replicas.items():
            with replica.transaction():
                rollbacks[target] = correct_sources(
                    replica._conn,
                    [],
                    hub=False,
                    apply=True,
                    rollback=receipts[target]["receipt_id"],
                )
            expected = "conflict" if target == blocked_target else "applied"
            assert rollbacks[target]["records"][0]["status"] == expected
            if target != blocked_target:
                assert deliver(target, revoked)["source_override_key"] is None
                with pytest.raises(ValueError, match="projection conflict"):
                    deliver(target, exact)
                assert replica.get_file_with_catalog(url)["source_override_key"] is None
        with blocked.transaction():
            correct_sources(blocked._conn, [], hub=False, apply=True, rollback=newer["receipt_id"])
            completed = correct_sources(
                blocked._conn,
                [],
                hub=False,
                apply=True,
                rollback=receipts[blocked_target]["receipt_id"],
            )
        assert completed["records"][0]["status"] == "applied"
        assert deliver(blocked_target, revoked)["source_override_key"] is None
        with pytest.raises(ValueError, match="projection conflict"):
            deliver(blocked_target, exact)
        print(
            json.dumps(
                {
                    "synthetic_receipt_evidence": {
                        "override": override,
                        "independent_pending_target": blocked_target,
                        "hub_apply": hub_receipt["receipt_id"],
                        "hub_rollback": hub_rollback["receipt_id"],
                        "targets": {
                            target: {
                                "apply": receipts[target]["receipt_id"],
                                "rollback": rollbacks[target]["receipt_id"],
                                "first_rollback_status": rollbacks[target]["records"][0]["status"],
                                "upstream_receipt_id": receipts[target]["records"][0][
                                    "upstream_receipt_id"
                                ],
                            }
                            for target in replicas
                        },
                        "compensating_rollback": completed["receipt_id"],
                    }
                },
                sort_keys=True,
            )
        )
    finally:
        for replica in replicas.values():
            replica.close()


@pytest.mark.parametrize("failed_target", ["china", "overseas"])
def test_partial_alias_revision_reaches_real_other_target_article_worker(
    storage, tmp_path, monkeypatch, failed_target
):
    import ai_actuarial.local_collection_runtime as runtime

    monkeypatch.setattr("ai_actuarial.capacity.ensure_capacity", lambda **kwargs: None)
    monkeypatch.setattr("ai_actuarial.capacity.capacity_status", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(runtime, "_load_category_keys", lambda: ["AI", "Pricing", "Other"])
    url, raw = "https://new-verified-publisher.example/partial.pdf", b"partial alias fixture"
    item = _item(url, raw, "# AI methods Pricing models")
    replicas = {
        target: Storage(postgres_url_for_path(tmp_path / (target + ".db")))
        for target in ("china", "overseas")
    }
    calls = []

    class Manager:
        def __init__(self, store, target):
            self.store = store
            self.dimension = 1024 if target == "china" else 3072

        def get_kb(self, kb_id):
            return SimpleNamespace(
                kb_id=kb_id,
                embedding_provider="fixture",
                embedding_model="fixture",
                embedding_dimension=self.dimension,
                embedding_identity_key="fixture",
            )

        def add_files_to_kb(self, kb_id, urls):
            for article_url in urls:
                self.store._conn.execute(
                    "INSERT INTO rag_kb_files(kb_id,file_url,added_at) VALUES(?,?,'2026-01-01') ON CONFLICT DO NOTHING",
                    (kb_id, article_url),
                )
            return {"added_count": len(urls), "skipped_count": 0}

    def receive(config, target, payload):
        calls.append((target, payload.get("operation", "articles")))
        if payload.get("operation") == "sync_source_registry":
            if target == failed_target:
                raise RuntimeError("synthetic alias revision connection failure")
            return target_worker.apply_source_registry(
                payload, storage_factory=lambda: Storage(replicas[target].database)
            )
        target_runtime = SimpleNamespace(
            data_root=tmp_path / target,
            _load_site_config=lambda: {},
            _resolve_db_path=lambda config: replicas[target].database,
        )
        return target_worker.apply_batch(
            payload,
            runtime_factory=lambda: target_runtime,
            storage_factory=lambda *args, **kwargs: Storage(replicas[target].database),
            manager_factory=lambda store: Manager(store, target),
            ready_builder=lambda *args: {"test_only_ready_stub": True},
        )

    try:
        for target, replica in replicas.items():
            with replica.transaction():
                install_registry(replica._conn, _seed(), target=target, apply=True)
            _upsert(replica, url, raw="cas", digest=item["raw_sha256"])
            assert replica.get_file_with_catalog(url)["source_key"] == "pending"
            for kb_id in ("ai", "all"):
                replica._conn.execute(
                    "INSERT INTO rag_knowledge_bases(kb_id,name,embedding_model,chunk_size,chunk_overlap,index_type,created_at,updated_at) VALUES(?,?,'fixture',512,50,'flat','2026-01-01','2026-01-01')",
                    (kb_id, kb_id),
                )
        revision = export_registry(storage._conn)
        revision.pop("registry_sha256")
        revision["registry_version"] = 2
        revision["aliases"].append(
            {
                "alias_kind": "hostname",
                "alias_norm": "new-verified-publisher.example",
                "source_key": "cas",
                "resolution_status": "verified",
                "evidence": ["synthetic exact host evidence"],
            }
        )
        with storage.transaction():
            install_registry(storage._conn, revision, target="hub", apply=True)
        monkeypatch.setattr(runtime, "_invoke_target_worker", receive)
        synced = sync_targets(storage._conn, {}, apply=True)
        healthy = "overseas" if failed_target == "china" else "china"
        assert synced["status"] == "partial"
        assert calls == [("china", "sync_source_registry"), ("overseas", "sync_source_registry")]
        assert registry_deployed_targets(storage._conn) == [healthy]
        assert replicas[healthy].get_file_with_catalog(url)["source_key"] == "cas"
        assert replicas[failed_target].get_file_with_catalog(url)["source_key"] == "pending"
        artifact = tmp_path / "original.pdf"
        artifact.write_bytes(raw)
        item.update(
            registry_identity(storage._conn),
            source_key="cas",
            source_override_key=None,
            source_registry_targets=[healthy],
            artifact_path=str(artifact),
            ai_candidate=True,
        )
        state = {
            "articles": {
                runtime._file_key(url, item["raw_sha256"]): {
                    **item,
                    "site_id": "cas",
                    "stage": "downloaded",
                    "discovery_sites": ["fixture"],
                }
            },
            "target_acks": {},
        }
        monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "dispatch-state.json")
        monkeypatch.setattr(runtime, "content_hub_read_version", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            runtime, "_prepare_hub_article", lambda *args, **kwargs: (item, True, True)
        )
        summary = runtime._process_articles(
            "fixture",
            state,
            {"state_root": str(tmp_path), "data_root": str(tmp_path)},
            "unused-hub",
            preview=False,
            article_limit=1,
        )
        assert calls[-1] == (healthy, "articles")
        assert calls.count((failed_target, "articles")) == 0
        assert summary["target"][healthy]["acknowledged"] == 1
        assert summary["target"][healthy]["ready_status"] == "succeeded"
        assert summary["target"][failed_target]["pending"] == 1
        ack = state["target_acks"][runtime._target_ack_key(healthy, item)]["ack"]
        assert ack["registry_version"] == 2
        assert ack["source_key"] == "cas" and ack["source_override_key"] is None
        assert ack["source_correction_receipt_id"] is None
        assert (
            replicas[healthy]._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0]
            == 0
        )
        assert replicas[healthy].get_file_with_catalog(url)["sha256"] == item["raw_sha256"]
        print(
            json.dumps(
                {
                    "synthetic_partial_alias_evidence": {
                        "failed_target": failed_target,
                        "article_worker_acknowledged": healthy,
                        "registry_receipt": synced["targets"][0],
                        "article_ack": ack,
                        "ready_status": summary["target"][healthy]["ready_status"],
                    }
                },
                sort_keys=True,
            )
        )
    finally:
        for replica in replicas.values():
            replica.close()


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_id",
        "missing_snapshot",
        "missing_exists",
        "missing_source_key",
        "missing_pointer",
        "malformed_exists",
        "malformed_absent_key",
        "malformed_pointer",
        "missing_intent",
        "second_missing_pointer",
    ],
)
def test_nonrollback_apply_rejects_incomplete_review_without_any_write(storage, invalid):
    url = "https://cdn.example/incomplete-review.pdf"
    _upsert(storage, url)
    with storage.transaction():
        dry = correct_sources(storage._conn, [_record(url, old="pending")], hub=False, apply=False)
    records = copy.deepcopy(dry["request_body"]["records"])
    request_id = dry["request_id"]
    intent = dry["request_body"]["reconfirm_same_key"]
    if invalid == "second_missing_pointer":
        records.append(copy.deepcopy(records[0]))
        records[1]["old_override"].pop("correction_receipt_id")
    elif invalid == "missing_id":
        request_id = None
    elif invalid == "missing_snapshot":
        records[0].pop("old_override")
    elif invalid.startswith("missing_") and invalid != "missing_intent":
        records[0]["old_override"].pop(
            {
                "missing_exists": "exists",
                "missing_source_key": "source_key",
                "missing_pointer": "correction_receipt_id",
            }[invalid]
        )
    elif invalid == "malformed_exists":
        records[0]["old_override"]["exists"] = "false"
    elif invalid == "malformed_absent_key":
        records[0]["old_override"]["source_key"] = "pending"
    elif invalid == "malformed_pointer":
        records[0]["old_override"].update(
            exists=True, source_key="pending", correction_receipt_id=123
        )
    elif invalid == "missing_intent":
        intent = None
    before = tuple(storage._conn.execute("SELECT * FROM files WHERE url=?", (url,)).fetchone())
    with pytest.raises(ValueError, match="saved dry-run"), storage.transaction():
        correct_sources(
            storage._conn,
            records,
            hub=False,
            apply=True,
            request_id=request_id,
            reconfirm_same_key=intent,
        )
    assert (
        tuple(storage._conn.execute("SELECT * FROM files WHERE url=?", (url,)).fetchone()) == before
    )
    assert storage._conn.execute("SELECT COUNT(*) FROM source_projection").fetchone()[0] == 0
    assert (
        storage._conn.execute("SELECT COUNT(*) FROM source_correction_receipts").fetchone()[0] == 0
    )


@pytest.mark.parametrize("prior_overlay", [False, True])
def test_saved_preview_rejects_same_effective_pending_concurrent_pointer_change(
    storage, tmp_path, monkeypatch, capsys, prior_overlay
):
    url = "https://cdn.example/concurrent-reviewed.pdf"
    _upsert(storage, url)
    if prior_overlay:
        with storage.transaction():
            _apply_reviewed(storage._conn, [_record(url, old="pending", new="pending")], hub=False)
    with storage.transaction():
        preview = correct_sources(
            storage._conn, [_record(url, old="pending")], hub=False, apply=False
        )
    assert preview["request_body"]["records"][0]["old_override"]["exists"] is prior_overlay
    with storage.transaction():
        cli_preview = correct_sources(
            storage._conn, [_record(url, old="pending")], hub=False, apply=False
        )
    with psycopg2.connect(storage.database._url) as concurrent:
        changed = _apply_reviewed(
            concurrent,
            [_record(url, old="pending", new="pending")],
            hub=False,
            request_id="concurrent-pending-confirmation",
        )
    assert changed["records"][0]["status"] == "applied"
    expected = tuple(storage._conn.execute("SELECT * FROM source_projection").fetchone())
    assert expected[2:] == ("pending", "concurrent-pending-confirmation")
    assert storage.get_file_with_catalog(url)["source_key"] == "pending"
    with storage.transaction():
        stale = correct_sources(
            storage._conn,
            preview["request_body"]["records"],
            hub=False,
            apply=True,
            request_id=preview["request_id"],
            reconfirm_same_key=preview["request_body"]["reconfirm_same_key"],
        )
    assert stale["records"][0]["status"] == "conflict"
    with storage.transaction():
        replay = correct_sources(
            storage._conn,
            preview["request_body"]["records"],
            hub=False,
            apply=True,
            request_id=preview["request_id"],
            reconfirm_same_key=preview["request_body"]["reconfirm_same_key"],
        )
    assert replay["records"][0]["status"] == "conflict"
    assert tuple(storage._conn.execute("SELECT * FROM source_projection").fetchone()) == expected
    monkeypatch.setenv("DATABASE_URL", storage.database._url)
    original = tmp_path / "raw-records.json"
    original.write_text(json.dumps({"records": [_record(url, old="pending")]}), encoding="utf-8")
    assert main(["correct", "--manifest", str(original), "--apply"]) == 2
    assert "saved dry-run JSON" in json.loads(capsys.readouterr().out)["error"]
    assert main(["correct", "--manifest", str(original), "--request-id", "bypass", "--apply"]) == 2
    assert "saved dry-run JSON" in json.loads(capsys.readouterr().out)["error"]
    saved = tmp_path / "reviewed-preview.json"
    saved.write_text(json.dumps(cli_preview), encoding="utf-8")
    cli_first_exit = main(["correct", "--manifest", str(saved), "--apply"])
    assert cli_first_exit == 2
    cli_first_status = json.loads(capsys.readouterr().out)["records"][0]["status"]
    assert cli_first_status == "conflict"
    cli_replay_exit = main(["correct", "--manifest", str(saved), "--apply"])
    assert cli_replay_exit == 2
    cli_replay_status = json.loads(capsys.readouterr().out)["records"][0]["status"]
    assert cli_replay_status == "conflict"
    assert tuple(storage._conn.execute("SELECT * FROM source_projection").fetchone()) == expected
    # A fresh reviewed explicit same-key confirmation changes ownership; plain preview does not.
    with storage.transaction():
        noop = _apply_reviewed(
            storage._conn, [_record(url, old="pending", new="pending")], hub=False
        )
    assert noop["records"][0]["status"] == "unchanged"
    assert tuple(storage._conn.execute("SELECT * FROM source_projection").fetchone()) == expected
    print(
        json.dumps(
            {
                "reviewed_snapshot_conflict": {
                    "prior_overlay": prior_overlay,
                    "preview_request_id": preview["request_id"],
                    "reviewed_before": preview["request_body"]["records"][0]["old_override"],
                    "concurrent_after": changed["records"][0]["new_override"],
                    "stale_status": stale["records"][0]["status"],
                    "same_id_replay_status": replay["records"][0]["status"],
                    "cli_first_exit": cli_first_exit,
                    "cli_first_status": cli_first_status,
                    "cli_replay_exit": cli_replay_exit,
                    "cli_replay_status": cli_replay_status,
                    "pointer_preserved": tuple(
                        storage._conn.execute("SELECT * FROM source_projection").fetchone()
                    )
                    == expected,
                    "owned_schema": storage._conn.execute("SELECT current_schema()").fetchone()[0],
                    "effective_source": storage.get_file_with_catalog(url)["source_key"],
                }
            }
        )
    )

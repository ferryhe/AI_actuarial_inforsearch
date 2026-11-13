"""Synthetic, isolated first-observation daily projection regressions."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from functools import partial
from pathlib import Path

import psycopg2
import pytest

from ai_actuarial import content_hub as hub
from ai_actuarial import local_collection_runtime as runtime
from ai_actuarial.api.services.read import list_source_portals
from ai_actuarial.local_collection_target_worker import apply_source_portals
from ai_actuarial.source_portals import SOURCE_PORTALS_BY_KEY
from ai_actuarial.storage import Storage
from tests.postgres_helpers import uninitialized_postgres_url_for_path


def _hub(tmp_path: Path) -> tuple[str, str]:
    url = uninitialized_postgres_url_for_path(tmp_path / "hub")
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = cursor.fetchone()[0]
    hub.apply_content_hub_schema(url, schema=schema)
    return url, schema


def _capture(
    *,
    day: str = "2026-11-06",
    hour: int = 6,
    site: str = "cia-ica",
    url: str = "https://www.cia-ica.ca/publications/synthetic-study",
    raw_sha: str,
    title: str = "Synthetic AI study",
) -> dict:
    portal = "cia-publications"
    captured_at = f"{day}T{hour:02}:00:00-05:00"
    return {
        "schema_version": 1,
        "portal_key": portal,
        "site_id": site,
        "run_id": hashlib.sha256(f"{site}|{captured_at}|{url}|{raw_sha}".encode()).hexdigest(),
        "captured_at": captured_at,
        "acquired_on": day,
        "observations": [
            {
                "url": url,
                "raw_sha256": raw_sha,
                "source_page_url": SOURCE_PORTALS_BY_KEY[portal].url,
                "title": title,
                "kind": "page",
                "is_article": True,
            }
        ],
        "hub_results": [],
        "limits": {
            "request_count": 1,
            "request_limit": 30,
            "budget_exhausted": False,
            "frontier_remaining": 2,
            "source_error_count": 1,
            "finished": False,
        },
    }


def _version(url: str, schema: str, database_url: str, root: Path, body: bytes) -> dict:
    return hub.ingest_live_article(
        canonical_url=url,
        source_site="cia-ica",
        source_page_url=SOURCE_PORTALS_BY_KEY["cia-publications"].url,
        title="Synthetic AI study",
        raw_bytes=body,
        markdown="Synthetic content",
        content_type="text/html",
        data_root=root,
        database_url=database_url,
        schema=schema,
    )


def _annotate(database_url: str, schema: str, version_id: int, category: str) -> None:
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "INSERT INTO article_enrichment_annotations "
                "(content_version_id, source_text_variant_id, source_markdown_sha256, "
                "source_primary_category, source_signature, categories_json, date_facts_json, "
                "date_review_status, date_review_unresolved_json, result_sha256, recipe, run_id) "
                "VALUES (%s, 1, %s, %s, %s, %s::jsonb, '{}'::jsonb, 'complete', "
                "'[]'::jsonb, %s, 'synthetic', 'synthetic') "
                "ON CONFLICT (content_version_id) DO UPDATE SET "
                "source_primary_category = excluded.source_primary_category, "
                "categories_json = excluded.categories_json, result_sha256 = excluded.result_sha256, "
                "annotated_at = clock_timestamp()",
                (
                    version_id,
                    "a" * 64,
                    category,
                    "b" * 64,
                    json.dumps([{"key": category, "evidence": ["synthetic"]}]),
                    hashlib.sha256(category.encode()).hexdigest(),
                ),
            )


def test_delayed_first_category_revises_original_day_and_two_targets(tmp_path: Path, monkeypatch):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    body = b"synthetic original for delayed classification"
    sha = hashlib.sha256(body).hexdigest()
    first_evidence = _capture(raw_sha=sha)
    first = hub.content_hub_record_source_portal_daily(
        first_evidence, database_url=url, schema=schema
    )
    assert first["description_en"].startswith("No new AI materials were found.")
    version = _version(article_url, schema, url, root, body)
    _annotate(url, schema, version["content_version_id"], "AI")
    assert hub.content_hub_source_portal_dates_for_versions(
        [version["content_version_id"]], database_url=url, schema=schema
    ) == [("cia-publications", "2026-11-06")]

    def project():
        return hub.content_hub_project_source_portal_daily(
            portal_key="cia-publications",
            acquired_on="2026-11-06",
            data_root=root,
            database_url=url,
            schema=schema,
        )

    revision = project()
    assert revision["capture_kind"] == "daily_projection"
    assert revision["acquired_on"] == "2026-11-06"
    assert "Synthetic AI study" in revision["description_en"]
    assert "successful reads" in revision["description_en"]
    assert revision["captured_at"] == first["captured_at"]
    assert project()["capture_id"] == revision["capture_id"]
    old = hub.content_hub_read_source_portal_capture(
        portal_key="cia-publications",
        capture_id=first["capture_id"],
        database_url=url,
        schema=schema,
    )
    assert old["description_en"] == first["description_en"]
    assert old["evidence_sha256"] == hub.validate_daily_evidence(first_evidence)[2]
    saved_revision = hub.content_hub_read_source_portal_capture(
        portal_key="cia-publications",
        capture_id=revision["capture_id"],
        database_url=url,
        schema=schema,
    )
    assert saved_revision["capture_kind"] == "daily_projection"
    assert saved_revision["generated_at"] > saved_revision["captured_at"]
    assert old["generated_at"] is None

    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target, target_url in targets.items():
        storage = Storage(target_url)
        storage.close()
        apply_source_portals(
            {
                "target": target,
                "cards": runtime.source_portal_cards(),
                "updates": [
                    {
                        "portal_key": "cia-publications",
                        **{
                            field: first[field]
                            for field in (
                                "capture_id",
                                "captured_at",
                                "acquired_on",
                                "description_zh",
                                "description_en",
                            )
                        },
                    }
                ],
            },
            storage_factory=lambda target_url=target_url: Storage(target_url),
        )

    def stream(_config, target, updates):
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        )

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    monkeypatch.setattr(
        runtime,
        "content_hub_latest_source_portal_update",
        partial(hub.content_hub_latest_source_portal_update, schema=schema),
    )
    monkeypatch.setattr(
        runtime,
        "content_hub_read_source_portal_capture",
        partial(hub.content_hub_read_source_portal_capture, schema=schema),
    )
    monkeypatch.setattr(
        runtime,
        "content_hub_source_portal_dates_for_versions",
        partial(hub.content_hub_source_portal_dates_for_versions, schema=schema),
    )
    monkeypatch.setattr(
        runtime,
        "content_hub_project_source_portal_daily",
        partial(hub.content_hub_project_source_portal_daily, schema=schema),
    )
    state = {"pending_source_portal_publications": {}}
    config = {
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    sync = runtime._sync_source_portals(
        state, config, url, projection_versions=[version["content_version_id"]]
    )
    assert sync["status"] == "succeeded", sync
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            row = storage._conn.execute(
                "SELECT capture_id FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                ("cia-publications", "2026-11-06"),
            ).fetchone()
            assert int(row[0]) == revision["capture_id"]
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == "cia-publications"
        )
        assert len(card["updates"]) == 1
        assert "Synthetic AI study" in card["updates"][0]["description_en"]

    _annotate(url, schema, version["content_version_id"], "Other")
    removed = project()
    assert removed["capture_id"] > revision["capture_id"]
    assert removed["description_en"].startswith("No new AI materials")
    assert project()["capture_id"] == removed["capture_id"]
    key = "cia-publications|2026-11-06"
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], "cia-publications", revision, hub=url
    )
    assert runtime._sync_source_portals(state, config, url, only_key=key)["status"] == "succeeded"
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            row = storage._conn.execute(
                "SELECT capture_id FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                ("cia-publications", "2026-11-06"),
            ).fetchone()
            assert int(row[0]) == removed["capture_id"]
        finally:
            storage.close()

    _annotate(url, schema, version["content_version_id"], "AI")
    restored = project()
    assert restored["capture_id"] > removed["capture_id"]
    overseas = Storage(targets["overseas"])
    try:
        with overseas.transaction(immediate=True):
            overseas._conn.execute(
                "UPDATE source_portal_updates SET capture_id = ?, captured_at = ?, "
                "description_zh = ?, description_en = ? "
                "WHERE portal_key = ? AND acquired_on = ?",
                (
                    999999,
                    "2026-11-06T20:00:00+00:00",
                    "未知外部更新",
                    "Unknown external update",
                    "cia-publications",
                    "2026-11-06",
                ),
            )
    finally:
        overseas.close()
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], "cia-publications", restored, hub=url
    )
    partial_sync = runtime._sync_source_portals(state, config, url, only_key=key)
    assert partial_sync["status"] == "partial"
    assert "without comparable Hub evidence" in partial_sync["targets"]["overseas"]["error"]
    assert key in state["pending_source_portal_publications"]
    overseas = Storage(targets["overseas"])
    try:
        with overseas.transaction(immediate=True):
            overseas._conn.execute(
                "UPDATE source_portal_updates SET capture_id = ?, captured_at = ?, "
                "description_zh = ?, description_en = ? "
                "WHERE portal_key = ? AND acquired_on = ?",
                (
                    removed["capture_id"],
                    removed["captured_at"],
                    removed["description_zh"],
                    removed["description_en"],
                    "cia-publications",
                    "2026-11-06",
                ),
            )
    finally:
        overseas.close()
    assert runtime._sync_source_portals(state, config, url, only_key=key)["status"] == "succeeded"
    for target_url in targets.values():
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == "cia-publications"
        )
        assert "Synthetic AI study" in card["updates"][0]["description_en"]


def test_same_day_other_then_ai_version_is_first_ai_discovery(tmp_path: Path):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    first_body, later_body = b"same-day Other", b"same-day AI"
    first_sha = hashlib.sha256(first_body).hexdigest()
    later_sha = hashlib.sha256(later_body).hexdigest()
    first = _capture(raw_sha=first_sha, title="Other title")
    later = _capture(hour=7, raw_sha=later_sha, title="First AI title")
    for evidence, body, category in (
        (first, first_body, "Other"),
        (later, later_body, "AI"),
    ):
        hub.content_hub_record_source_portal_daily(evidence, database_url=hub_url, schema=schema)
        version = _version(article_url, schema, hub_url, root, body)
        _annotate(hub_url, schema, version["content_version_id"], category)
    revision = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=hub_url,
        schema=schema,
    )
    assert revision["description_en"].count("First AI title") == 1
    assert "Other title" not in revision["description_en"]


def test_later_collection_cannot_hide_changed_public_projection(tmp_path: Path):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    body = b"reclassified after first projection"
    sha = hashlib.sha256(body).hexdigest()
    evidence = _capture(raw_sha=sha)
    hub.content_hub_record_source_portal_daily(evidence, database_url=hub_url, schema=schema)
    version = _version(evidence["observations"][0]["url"], schema, hub_url, root, body)
    _annotate(hub_url, schema, version["content_version_id"], "AI")

    def project():
        return hub.content_hub_project_source_portal_daily(
            portal_key="cia-publications",
            acquired_on="2026-11-06",
            data_root=root,
            database_url=hub_url,
            schema=schema,
        )

    first = project()
    assert "Synthetic AI study" in first["description_en"]
    _annotate(hub_url, schema, version["content_version_id"], "Other")
    later_evidence = _capture(hour=7, raw_sha=sha)
    later_collection = hub.content_hub_record_source_portal_daily(
        later_evidence, database_url=hub_url, schema=schema
    )
    assert later_collection["description_en"].startswith("No new AI materials")
    revised = project()
    assert revised["capture_kind"] == "daily_projection"
    assert revised["capture_id"] > later_collection["capture_id"]
    assert revised["description_en"].startswith("No new AI materials")
    public = hub.content_hub_latest_source_portal_update(
        portal_key="cia-publications", acquired_on="2026-11-06", database_url=hub_url, schema=schema
    )
    assert "Synthetic AI study" not in public["description_en"]
    assert project()["capture_id"] == revised["capture_id"]
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT count(*) FROM source_portal_captures "
                "WHERE portal_key = %s AND capture_kind = 'daily_projection'",
                ("cia-publications",),
            )
            assert cursor.fetchone()[0] == 2


def test_ordinary_pending_retry_refreshes_hub_and_waits_for_both_target_readbacks(
    tmp_path: Path, monkeypatch
):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    body = b"committed projection before local pending checkpoint"
    sha = hashlib.sha256(body).hexdigest()
    evidence = _capture(raw_sha=sha)
    old = hub.content_hub_record_source_portal_daily(evidence, database_url=hub_url, schema=schema)
    version = _version(evidence["observations"][0]["url"], schema, hub_url, root, body)
    _annotate(hub_url, schema, version["content_version_id"], "AI")
    latest = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=hub_url,
        schema=schema,
    )
    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target_url in targets.values():
        storage = Storage(target_url)
        storage.close()
    state_path = tmp_path / "runtime-state.json"
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", state_path)
    key = "cia-publications|2026-11-06"
    state = {"pending_source_portal_publications": {}}
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], "cia-publications", old
    )
    runtime._atomic_json(state_path, state)
    config = {
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    real_latest = partial(hub.content_hub_latest_source_portal_update, schema=schema)
    monkeypatch.setattr(
        runtime,
        "content_hub_read_source_portal_capture",
        partial(hub.content_hub_read_source_portal_capture, schema=schema),
    )
    monkeypatch.setattr(runtime, "content_hub_latest_source_portal_update", lambda **_kwargs: None)
    missing = runtime._sync_source_portals(state, config, hub_url)
    assert missing["status"] == "partial"
    assert key in state["pending_source_portal_publications"]
    assert state["pending_source_portal_publications"][key]["capture_id"] == old["capture_id"]
    monkeypatch.setattr(runtime, "content_hub_latest_source_portal_update", real_latest)

    crashed = False

    def stream(_config, target, updates):
        nonlocal crashed
        reply = apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        )
        if target == "overseas" and not crashed:
            crashed = True
            raise RuntimeError("synthetic crash after target commit")
        return reply

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    interrupted = runtime._sync_source_portals(state, config, hub_url)
    assert interrupted["status"] == "partial"
    assert key in state["pending_source_portal_publications"]
    checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
    assert (
        checkpoint["pending_source_portal_publications"][key]["capture_id"] == latest["capture_id"]
    )
    retry = runtime._sync_source_portals(checkpoint, config, hub_url)
    assert retry["status"] == "succeeded", retry
    assert key not in checkpoint["pending_source_portal_publications"]
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            row = storage._conn.execute(
                "SELECT capture_id, description_en FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                ("cia-publications", "2026-11-06"),
            ).fetchone()
            assert int(row[0]) == latest["capture_id"]
            assert "Synthetic AI study" in row[1]
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == "cia-publications"
        )
        assert len(card["updates"]) == 1
        assert "Synthetic AI study" in card["updates"][0]["description_en"]


def test_normal_run_reprojects_hub_only_annotation_change_without_new_bytes(
    tmp_path: Path, monkeypatch
):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    first_url = "https://www.cia-ica.ca/publications/synthetic-study"
    other_url = "https://www.cia-ica.ca/publications/other-synthetic-study"
    first_body, other_body = b"reclassified Hub-only", b"unrelated AI"
    evidence = _capture(raw_sha=hashlib.sha256(first_body).hexdigest(), title="Removed AI")
    evidence["observations"].append(
        {
            **evidence["observations"][0],
            "url": other_url,
            "raw_sha256": hashlib.sha256(other_body).hexdigest(),
            "title": "Retained AI",
        }
    )
    hub.content_hub_record_source_portal_daily(evidence, database_url=hub_url, schema=schema)
    first = _version(first_url, schema, hub_url, root, first_body)
    other = _version(other_url, schema, hub_url, root, other_body)
    _annotate(hub_url, schema, first["content_version_id"], "AI")
    _annotate(hub_url, schema, other["content_version_id"], "AI")
    initial = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=hub_url,
        schema=schema,
    )
    assert "Removed AI" in initial["description_en"]
    _annotate(hub_url, schema, first["content_version_id"], "Other")

    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target_url in targets.values():
        storage = Storage(target_url)
        storage.close()
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    for name in (
        "content_hub_source_portal_annotation_watermark",
        "content_hub_source_portal_annotation_versions",
        "content_hub_source_portal_dates_for_versions",
        "content_hub_project_source_portal_daily",
        "content_hub_project_source_portal_update",
        "content_hub_latest_source_portal_update",
        "content_hub_read_source_portal_capture",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    monkeypatch.setattr(runtime, "_new_crawler", lambda *_args: object())
    monkeypatch.setattr(
        runtime,
        "_capture",
        lambda *_args, **_kwargs: {
            "downloads": [],
            "portal_captures": [],
            "errors": [],
            "request_count": 0,
            "request_limit": 1,
            "budget_exhausted": False,
            "frontier_remaining": 0,
        },
    )
    monkeypatch.setattr(
        runtime,
        "_process_articles",
        lambda *_args, **_kwargs: {
            "candidate_count": 0,
            "new_versions": 0,
            "duplicates": 0,
            "enriched": 0,
            "ai_candidates": 0,
            "article_errors": [],
            "database": {"new_version_ids": [], "duplicate_version_ids": []},
            "target": {
                target: {"acknowledged": 0, "pending": 0, "failed": 0} for target in targets
            },
        },
    )
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, target, updates: apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_write_receipt",
        lambda _root, _day, _site, stages, evidence, _reason, _telemetry: {
            "stages": stages,
            "evidence": evidence,
        },
    )
    state = {
        "sites": {},
        "articles": {
            "obsolete-local-row": {
                "url": "https://www.cia-ica.ca/publications/no-hub-version",
                "raw_sha256": "f" * 64,
                "stage": "complete",
                "discovery_sites": ["cia-ica"],
            }
        },
        "target_acks": {},
    }
    config = {
        "state_root": str(tmp_path),
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    result = runtime._run_site("cia-ica", "2026-11-13", config, state, hub_url)
    assert not any("annotation scan" in item for item in result["evidence"])
    assert state["pending_source_portal_projection_versions"] == []
    revised = hub.content_hub_latest_source_portal_update(
        portal_key="cia-publications", acquired_on="2026-11-06", database_url=hub_url, schema=schema
    )
    assert "Removed AI" not in revised["description_en"]
    assert "Retained AI" in revised["description_en"]
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            row = storage._conn.execute(
                "SELECT capture_id, description_en FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                ("cia-publications", "2026-11-06"),
            ).fetchone()
            assert int(row[0]) == revised["capture_id"]
            assert "Removed AI" not in row[1]
            assert "Retained AI" in row[1]
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == "cia-publications"
        )
        assert "Removed AI" not in card["updates"][0]["description_en"]
        assert "Retained AI" in card["updates"][0]["description_en"]


def test_annotation_cursor_persists_queue_before_advancing_and_retries_after_crash(
    tmp_path: Path, monkeypatch
):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    first_url = "https://www.cia-ica.ca/publications/synthetic-study"
    other_url = "https://www.cia-ica.ca/publications/other-synthetic-study"
    bodies = (b"first originally Other", b"second originally Other")
    evidence = _capture(raw_sha=hashlib.sha256(bodies[0]).hexdigest())
    evidence["observations"].append(
        {
            **evidence["observations"][0],
            "url": other_url,
            "raw_sha256": hashlib.sha256(bodies[1]).hexdigest(),
            "title": "Second AI title",
        }
    )
    hub.content_hub_record_source_portal_daily(evidence, database_url=hub_url, schema=schema)
    first = _version(first_url, schema, hub_url, root, bodies[0])
    other = _version(other_url, schema, hub_url, root, bodies[1])
    for version in (first, other):
        _annotate(hub_url, schema, version["content_version_id"], "Other")
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "UPDATE article_enrichment_annotations SET annotated_at = "
                "(SELECT applied_at FROM schema_migrations WHERE version = 7) - interval '1 day' "
                "WHERE content_version_id = ANY(%s)",
                ([first["content_version_id"], other["content_version_id"]],),
            )
    for name in (
        "content_hub_source_portal_annotation_watermark",
        "content_hub_source_portal_annotation_versions",
        "content_hub_source_portal_dates_for_versions",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    state_path = tmp_path / "runtime-state.json"
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", state_path)
    state = {"articles": {}}
    runtime._queue_source_portal_annotation_changes("cia-ica", state, hub_url)
    assert state["pending_source_portal_projection_versions"] == []
    baseline_cursor = state["source_portal_annotation_scan"]["cursor"]

    real_atomic = runtime._atomic_json
    _annotate(hub_url, schema, first["content_version_id"], "AI")

    def fail_before_queue(_path, _value):
        raise RuntimeError("synthetic crash before queue checkpoint")

    monkeypatch.setattr(runtime, "_atomic_json", fail_before_queue)
    with pytest.raises(RuntimeError, match="before queue checkpoint"):
        runtime._queue_source_portal_annotation_changes("cia-ica", state, hub_url)
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["pending_source_portal_projection_versions"] == []
    assert saved["source_portal_annotation_scan"]["cursor"] == baseline_cursor
    monkeypatch.setattr(runtime, "_atomic_json", real_atomic)
    runtime._queue_source_portal_annotation_changes("cia-ica", saved, hub_url)
    assert saved["pending_source_portal_projection_versions"] == [first["content_version_id"]]

    saved["pending_source_portal_projection_versions"] = []
    real_atomic(state_path, saved)
    cursor_before_second = saved["source_portal_annotation_scan"]["cursor"]
    _annotate(hub_url, schema, other["content_version_id"], "AI")
    writes = 0

    def fail_after_queue(path, value):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise RuntimeError("synthetic crash before cursor checkpoint")
        real_atomic(path, value)

    monkeypatch.setattr(runtime, "_atomic_json", fail_after_queue)
    with pytest.raises(RuntimeError, match="before cursor checkpoint"):
        runtime._queue_source_portal_annotation_changes("cia-ica", saved, hub_url)
    checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
    assert checkpoint["pending_source_portal_projection_versions"] == [other["content_version_id"]]
    assert checkpoint["source_portal_annotation_scan"]["cursor"] == cursor_before_second
    monkeypatch.setattr(runtime, "_atomic_json", real_atomic)
    runtime._queue_source_portal_annotation_changes("cia-ica", checkpoint, hub_url)
    assert checkpoint["pending_source_portal_projection_versions"] == [other["content_version_id"]]
    assert checkpoint["source_portal_annotation_scan"]["cursor"] != cursor_before_second
    assert hub.content_hub_source_portal_dates_for_versions(
        [other["content_version_id"]], database_url=hub_url, schema=schema
    ) == [("cia-publications", "2026-11-06")]


def test_more_than_32_saved_dates_page_and_resume_after_target_failure(tmp_path: Path, monkeypatch):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    body = b"one exact original observed on thirty-five days"
    sha = hashlib.sha256(body).hexdigest()
    first_day = dt.date(2026, 11, 1)
    days = [(first_day + dt.timedelta(days=index)).isoformat() for index in range(35)]
    for day in days:
        hub.content_hub_record_source_portal_daily(
            _capture(day=day, raw_sha=sha), database_url=hub_url, schema=schema
        )
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    version = _version(article_url, schema, hub_url, root, body)
    _annotate(hub_url, schema, version["content_version_id"], "AI")
    assert (
        len(
            hub.content_hub_source_portal_dates_for_versions(
                [version["content_version_id"]], database_url=hub_url, schema=schema
            )
        )
        == 32
    )
    assert hub.content_hub_source_portal_dates_for_versions(
        [version["content_version_id"]],
        after=("cia-publications", days[31]),
        database_url=hub_url,
        schema=schema,
    ) == [("cia-publications", day) for day in days[32:]]

    for name in (
        "content_hub_source_portal_annotation_watermark",
        "content_hub_source_portal_annotation_versions",
        "content_hub_source_portal_dates_for_versions",
        "content_hub_project_source_portal_daily",
        "content_hub_latest_source_portal_update",
        "content_hub_read_source_portal_capture",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    state = {"articles": {}}
    runtime._queue_source_portal_annotation_changes("cia-ica", state, hub_url)
    assert state["pending_source_portal_projection_versions"] == [version["content_version_id"]]
    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target_url in targets.values():
        storage = Storage(target_url)
        storage.close()
    fail_second_page = True

    def stream(_config, target, updates):
        nonlocal fail_second_page
        if (
            target == "overseas"
            and fail_second_page
            and any(update["acquired_on"] == days[32] for update in updates)
        ):
            fail_second_page = False
            raise RuntimeError("synthetic second-page target failure")
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        )

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    config = {
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    first = runtime._sync_source_portals(state, config, hub_url)
    assert first["status"] == "partial", first
    assert first["projection_versions_pending"] == 1
    assert state["source_portal_projection_date_cursors"][str(version["content_version_id"])] == [
        "cia-publications",
        days[31],
    ]
    assert state["pending_source_portal_projection_versions"] == [version["content_version_id"]]
    second = runtime._sync_source_portals(state, config, hub_url)
    assert second["status"] == "partial", second
    assert state["source_portal_projection_date_cursors"][str(version["content_version_id"])] == [
        "cia-publications",
        days[31],
    ]
    assert all(
        f"cia-publications|{day}" in state["pending_source_portal_publications"]
        for day in days[32:]
    )
    checkpoint = json.loads((tmp_path / "runtime-state.json").read_text(encoding="utf-8"))
    assert runtime._sync_source_portals(checkpoint, config, hub_url)["status"] == "succeeded"
    assert checkpoint["pending_source_portal_projection_versions"] == []
    assert checkpoint["pending_source_portal_publications"] == {}
    assert checkpoint["source_portal_projection_date_cursors"] == {}
    assert runtime._sync_source_portals(checkpoint, config, hub_url)["status"] == "succeeded"
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            rows = storage._conn.execute(
                "SELECT acquired_on, description_en FROM source_portal_updates "
                "WHERE portal_key = ? ORDER BY acquired_on",
                ("cia-publications",),
            ).fetchall()
            assert len(rows) == 35
            assert str(rows[0][0]) == days[0]
            assert "Synthetic AI study" in rows[0][1]
            assert str(rows[-1][0]) == days[-1]
            assert rows[-1][1].startswith("No new AI materials")
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == "cia-publications"
        )
        assert card["updates"][0]["acquired_on"] == days[-1]


@pytest.mark.parametrize("fail_first", [False, True])
def test_two_changed_versions_on_different_cards_share_one_date_budget(
    tmp_path: Path, monkeypatch, fail_first: bool
):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    cases = [
        (
            "cia-publications",
            "cia-ica",
            "https://www.cia-ica.ca/publications/synthetic-study",
            "2026-11-06",
            b"first card original",
            "First card AI",
        ),
        (
            "soa-research-topics",
            "soa",
            "https://www.soa.org/research/synthetic-study",
            "2026-11-07",
            b"second card original",
            "Second card AI",
        ),
    ]
    versions = []
    for portal_key, site_id, article_url, day, body, title in cases:
        evidence = _capture(
            site=site_id,
            url=article_url,
            day=day,
            raw_sha=hashlib.sha256(body).hexdigest(),
            title=title,
        )
        evidence["portal_key"] = portal_key
        evidence["observations"][0]["source_page_url"] = SOURCE_PORTALS_BY_KEY[portal_key].url
        hub.content_hub_record_source_portal_daily(evidence, database_url=hub_url, schema=schema)
        version = hub.ingest_live_article(
            canonical_url=article_url,
            source_site=site_id,
            source_page_url=SOURCE_PORTALS_BY_KEY[portal_key].url,
            title=title,
            raw_bytes=body,
            markdown="Synthetic content",
            content_type="text/html",
            data_root=root,
            database_url=hub_url,
            schema=schema,
        )
        _annotate(hub_url, schema, version["content_version_id"], "AI")
        versions.append(version["content_version_id"])
    for name in (
        "content_hub_source_portal_annotation_watermark",
        "content_hub_source_portal_annotation_versions",
        "content_hub_source_portal_dates_for_versions",
        "content_hub_project_source_portal_daily",
        "content_hub_latest_source_portal_update",
        "content_hub_read_source_portal_capture",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    state = {"articles": {}}
    runtime._queue_source_portal_annotation_changes("cia-ica", state, hub_url)
    assert state["pending_source_portal_projection_versions"] == versions
    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target_url in targets.values():
        storage = Storage(target_url)
        storage.close()
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, target, updates: apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        ),
    )
    config = {
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    real_project = runtime.content_hub_project_source_portal_daily
    if fail_first:
        first_failure = True

        def project_with_first_failure(**kwargs):
            nonlocal first_failure
            if first_failure and kwargs["portal_key"] == "cia-publications":
                first_failure = False
                raise RuntimeError("synthetic first-card projection failure")
            return real_project(**kwargs)

        monkeypatch.setattr(
            runtime, "content_hub_project_source_portal_daily", project_with_first_failure
        )
    sync = runtime._sync_source_portals(state, config, hub_url)
    if fail_first:
        assert sync["status"] == "partial", sync
        assert state["pending_source_portal_projection_versions"] == [versions[0]]
        for target_url in targets.values():
            storage = Storage(target_url)
            try:
                row = storage._conn.execute(
                    "SELECT description_en FROM source_portal_updates "
                    "WHERE portal_key = ? AND acquired_on = ?",
                    ("soa-research-topics", "2026-11-07"),
                ).fetchone()
                assert "Second card AI" in row[0]
            finally:
                storage.close()
        monkeypatch.setattr(runtime, "content_hub_project_source_portal_daily", real_project)
        sync = runtime._sync_source_portals(state, config, hub_url)
    assert sync["status"] == "succeeded", sync
    assert sync["projection_versions_pending"] == 0
    assert state["pending_source_portal_publications"] == {}
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            for portal_key, _site_id, _article_url, day, _body, title in cases:
                row = storage._conn.execute(
                    "SELECT description_en FROM source_portal_updates "
                    "WHERE portal_key = ? AND acquired_on = ?",
                    (portal_key, day),
                ).fetchone()
                assert title in row[0]
        finally:
            storage.close()
        cards = {
            card["portal_key"]: card for card in list_source_portals(db_path=target_url)["portals"]
        }
        assert "First card AI" in cards["cia-publications"]["updates"][0]["description_en"]
        assert "Second card AI" in cards["soa-research-topics"]["updates"][0]["description_en"]


def test_same_day_collection_recomposes_existing_soa_projection_and_retries(
    tmp_path: Path, monkeypatch
):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    first_url = "https://www.soa.org/research/synthetic-first-ai.pdf"
    second_url = "https://www.soa.org/research/synthetic-second-ai.pdf"
    first_body, second_body = b"first SOA AI original", b"second SOA AI original"

    def evidence(article_url: str, body: bytes, hour: int, title: str):
        run = _capture(
            site="soa-ai-bulletin-focused",
            url=article_url,
            raw_sha=hashlib.sha256(body).hexdigest(),
            hour=hour,
            title=title,
        )
        run["portal_key"] = portal.portal_key
        run["observations"][0].update(kind="file", source_page_url=portal.url)
        run["observations"][0].pop("is_article")
        return run

    def ingest(article_url: str, body: bytes):
        version = hub.ingest_live_article(
            canonical_url=article_url,
            source_site="soa-ai-bulletin-focused",
            source_page_url=portal.url,
            title="Synthetic SOA AI",
            raw_bytes=body,
            markdown="Synthetic content",
            content_type="application/pdf",
            data_root=root,
            database_url=hub_url,
            schema=schema,
        )
        _annotate(hub_url, schema, version["content_version_id"], "AI")
        return version

    first_evidence = evidence(first_url, first_body, 6, "First AI")
    first_capture = hub.content_hub_record_source_portal_daily(
        first_evidence, database_url=hub_url, schema=schema
    )
    ingest(first_url, first_body)
    first_projection = hub.content_hub_project_source_portal_daily(
        portal_key=portal.portal_key,
        acquired_on="2026-11-06",
        data_root=root,
        database_url=hub_url,
        schema=schema,
    )
    assert "First AI" in first_projection["description_en"]
    ingest(second_url, second_body)
    second_evidence = evidence(second_url, second_body, 9, "Second AI")
    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target, target_url in targets.items():
        storage = Storage(target_url)
        storage.close()
        apply_source_portals(
            {
                "target": target,
                "cards": runtime.source_portal_cards(),
                "updates": [
                    {
                        "portal_key": portal.portal_key,
                        **{
                            field: first_projection[field]
                            for field in (
                                "capture_id",
                                "captured_at",
                                "acquired_on",
                                "description_zh",
                                "description_en",
                            )
                        },
                    }
                ],
            },
            storage_factory=lambda target_url=target_url: Storage(target_url),
        )
    for name in (
        "content_hub_record_source_portal_daily",
        "content_hub_project_source_portal_daily",
        "content_hub_project_source_portal_update",
        "content_hub_latest_source_portal_update",
        "content_hub_read_source_portal_capture",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, target, updates: apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        ),
    )
    state = {
        "source_portal_daily_runs": {second_evidence["run_id"]: {"evidence": [second_evidence]}}
    }
    config = {
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    real_project = runtime.content_hub_project_source_portal_daily
    fail_once = True

    def interrupted_project(**kwargs):
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise RuntimeError("synthetic crash after immutable collection")
        return real_project(**kwargs)

    monkeypatch.setattr(runtime, "content_hub_project_source_portal_daily", interrupted_project)
    interrupted = runtime._sync_source_portals(state, config, hub_url)
    assert interrupted["status"] == "partial", interrupted
    assert second_evidence["run_id"] in state["source_portal_daily_runs"]
    active_before_retry = hub.content_hub_latest_source_portal_update(
        portal_key=portal.portal_key, acquired_on="2026-11-06", database_url=hub_url, schema=schema
    )
    assert "First AI" in active_before_retry["description_en"]
    assert "Second AI" not in active_before_retry["description_en"]
    monkeypatch.setattr(runtime, "content_hub_project_source_portal_daily", real_project)
    checkpoint = json.loads((tmp_path / "runtime-state.json").read_text(encoding="utf-8"))
    retry = runtime._sync_source_portals(checkpoint, config, hub_url)
    assert retry["errors"] == [], retry["errors"]
    assert retry["status"] == "succeeded", retry
    assert checkpoint["source_portal_daily_runs"] == {}
    active = hub.content_hub_latest_source_portal_update(
        portal_key=portal.portal_key, acquired_on="2026-11-06", database_url=hub_url, schema=schema
    )
    assert active["description_en"].count("First AI") == 1
    assert active["description_en"].count("Second AI") == 1
    saved_first = hub.content_hub_read_source_portal_capture(
        portal_key=portal.portal_key,
        capture_id=first_capture["capture_id"],
        database_url=hub_url,
        schema=schema,
    )
    assert saved_first["evidence_sha256"] == hub.validate_daily_evidence(first_evidence)[2]
    assert saved_first["description_en"] == first_capture["description_en"]
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT count(*) FROM source_portal_captures "
                "WHERE portal_key = %s AND capture_kind = 'daily_projection'",
                (portal.portal_key,),
            )
            assert cursor.fetchone()[0] == 2
    assert runtime._sync_source_portals(checkpoint, config, hub_url)["status"] == "succeeded"
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            row = storage._conn.execute(
                "SELECT capture_id, description_en FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                (portal.portal_key, "2026-11-06"),
            ).fetchone()
            assert int(row[0]) == active["capture_id"]
            assert "First AI" in row[1] and "Second AI" in row[1]
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == portal.portal_key
        )
        assert "First AI" in card["updates"][0]["description_en"]
        assert "Second AI" in card["updates"][0]["description_en"]


def test_reclassification_keeps_other_title_and_later_ai_version_reaches_two_targets(
    tmp_path: Path, monkeypatch
):
    hub_url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    first_url = "https://www.cia-ica.ca/publications/synthetic-study"
    other_url = "https://www.cia-ica.ca/publications/other-synthetic-study"
    first_body, other_body, later_body = b"first AI", b"independent AI", b"later AI"
    first_sha = hashlib.sha256(first_body).hexdigest()
    other_sha = hashlib.sha256(other_body).hexdigest()
    later_sha = hashlib.sha256(later_body).hexdigest()
    evidence = _capture(raw_sha=first_sha, title="First AI title")
    evidence["observations"].append(
        {
            **evidence["observations"][0],
            "url": other_url,
            "raw_sha256": other_sha,
            "title": "Other AI title",
        }
    )
    original = hub.content_hub_record_source_portal_daily(
        evidence, database_url=hub_url, schema=schema
    )
    first = _version(first_url, schema, hub_url, root, first_body)
    other = _version(other_url, schema, hub_url, root, other_body)
    _annotate(hub_url, schema, first["content_version_id"], "AI")
    _annotate(hub_url, schema, other["content_version_id"], "AI")

    def project(day: str):
        return hub.content_hub_project_source_portal_daily(
            portal_key="cia-publications",
            acquired_on=day,
            data_root=root,
            database_url=hub_url,
            schema=schema,
        )

    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }

    def publish(update):
        for target, target_url in targets.items():
            storage = Storage(target_url)
            storage.close()
            result = apply_source_portals(
                {
                    "target": target,
                    "cards": runtime.source_portal_cards(),
                    "updates": [
                        {
                            "portal_key": "cia-publications",
                            **{
                                field: update[field]
                                for field in (
                                    "capture_id",
                                    "captured_at",
                                    "acquired_on",
                                    "description_zh",
                                    "description_en",
                                )
                            },
                        }
                    ],
                },
                storage_factory=lambda target_url=target_url: Storage(target_url),
            )
            assert result["failures"] == [], result
            assert result["updates_skipped"] == [], result

    initial = project("2026-11-06")
    assert "First AI title" in initial["description_en"]
    assert "Other AI title" in initial["description_en"]
    publish(initial)

    later = _version(first_url, schema, hub_url, root, later_body)
    _annotate(hub_url, schema, later["content_version_id"], "AI")
    later_evidence = _capture(day="2026-11-11", raw_sha=later_sha, title="New AI version")
    hub.content_hub_record_source_portal_daily(later_evidence, database_url=hub_url, schema=schema)
    before_change = project("2026-11-11")
    assert "New AI version" not in before_change["description_en"]
    publish(before_change)

    _annotate(hub_url, schema, first["content_version_id"], "Other")
    assert hub.content_hub_source_portal_dates_for_versions(
        [first["content_version_id"]], database_url=hub_url, schema=schema
    ) == [
        ("cia-publications", "2026-11-06"),
        ("cia-publications", "2026-11-11"),
    ]

    def stream(_config, target, updates):
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        )

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    for name in (
        "content_hub_latest_source_portal_update",
        "content_hub_read_source_portal_capture",
        "content_hub_source_portal_dates_for_versions",
        "content_hub_project_source_portal_daily",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    state = {"pending_source_portal_publications": {}}
    config = {
        "data_root": str(root),
        "targets": {"china": {"host": "synthetic"}, "overseas": {"host": "synthetic"}},
    }
    sync = runtime._sync_source_portals(
        state, config, hub_url, projection_versions=[first["content_version_id"]]
    )
    assert sync["status"] == "succeeded", sync
    revised = project("2026-11-06")
    discovered = project("2026-11-11")
    assert revised["capture_id"] > initial["capture_id"]
    assert "First AI title" not in revised["description_en"]
    assert "Other AI title" in revised["description_en"]
    assert discovered["capture_id"] > before_change["capture_id"]
    assert discovered["description_en"].count("New AI version") == 1
    assert "First AI title" not in discovered["description_en"]
    assert project("2026-11-06")["capture_id"] == revised["capture_id"]
    assert project("2026-11-11")["capture_id"] == discovered["capture_id"]

    saved_original = hub.content_hub_read_source_portal_capture(
        portal_key="cia-publications",
        capture_id=original["capture_id"],
        database_url=hub_url,
        schema=schema,
    )
    assert saved_original["evidence_sha256"] == hub.validate_daily_evidence(evidence)[2]
    assert saved_original["description_en"] == original["description_en"]
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            rows = storage._conn.execute(
                "SELECT acquired_on, capture_id, description_en FROM source_portal_updates "
                "WHERE portal_key = ? ORDER BY acquired_on",
                ("cia-publications",),
            ).fetchall()
            assert [(str(row[0]), int(row[1])) for row in rows] == [
                ("2026-11-06", revised["capture_id"]),
                ("2026-11-11", discovered["capture_id"]),
            ]
            assert "First AI title" not in rows[0][2]
            assert "Other AI title" in rows[0][2]
            assert rows[1][2].count("New AI version") == 1
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == "cia-publications"
        )
        assert len(card["updates"]) == 2
        assert "Other AI title" in card["updates"][1]["description_en"]
        assert "First AI title" not in card["updates"][1]["description_en"]
        assert card["updates"][0]["description_en"].count("New AI version") == 1


def test_projection_uses_latest_actual_daily_time_and_rejects_corrupt_evidence(tmp_path: Path):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    body = b"synthetic original with later same-day collection"
    sha = hashlib.sha256(body).hexdigest()
    first = _capture(raw_sha=sha)
    original = hub.content_hub_record_source_portal_daily(first, database_url=url, schema=schema)
    later = _capture(raw_sha=sha, hour=9, site="cia-research-publications")
    later["observations"][0]["title"] = "Synthetic AI study"
    hub.content_hub_record_source_portal_daily(later, database_url=url, schema=schema)
    directory = hub.content_hub_record_source_portal_capture(
        portal_key="cia-publications",
        page_url=SOURCE_PORTALS_BY_KEY["cia-publications"].url,
        scope_key="synthetic-directory",
        captured_at="2026-11-06T10:00:00-05:00",
        acquired_on="2026-11-06",
        page_sha256="c" * 64,
        entries=[{"url": article_url, "title": "Synthetic AI study"}],
        complete=True,
        intro_zh="合成入口",
        intro_en="Synthetic directory",
        database_url=url,
        schema=schema,
    )
    version = _version(article_url, schema, url, root, body)
    _annotate(url, schema, version["content_version_id"], "AI")
    revision = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    assert revision["captured_at"] == "2026-11-06T15:00:00+00:00"
    assert revision["capture_id"] > original["capture_id"]
    assert revision["description_en"].startswith("Found 1 new AI material")
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT evidence_json FROM source_portal_captures WHERE capture_id = %s",
                (revision["capture_id"],),
            )
            trace = cursor.fetchone()[0]
            assert len(trace["source_captures"]) == 2
            assert trace["directory_captures"][0]["capture_id"] == directory["capture_id"]
            assert (
                trace["content_sha256"]
                == hashlib.sha256(
                    (revision["description_zh"] + "\0" + revision["description_en"]).encode()
                ).hexdigest()
            )
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "UPDATE source_portal_captures SET evidence_sha256 = %s WHERE capture_id = %s",
                ("f" * 64, original["capture_id"]),
            )
    with pytest.raises(hub.ContentHubError, match="conflicts with its identity"):
        hub.content_hub_project_source_portal_daily(
            portal_key="cia-publications",
            acquired_on="2026-11-06",
            data_root=root,
            database_url=url,
            schema=schema,
        )


def test_first_observation_after_hub_import_and_later_sha_are_one_discovery(tmp_path: Path):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    first_body, later_body = b"first synthetic original", b"later synthetic revision"
    first_sha = hashlib.sha256(first_body).hexdigest()
    later_sha = hashlib.sha256(later_body).hexdigest()
    first_version = _version(article_url, schema, url, root, first_body)
    _annotate(url, schema, first_version["content_version_id"], "AI")
    first = _capture(raw_sha=first_sha)
    first["hub_results"] = [
        {
            "url": article_url,
            "raw_sha256": first_sha,
            "source_page_url": SOURCE_PORTALS_BY_KEY["cia-publications"].url,
            "content_version_id": str(first_version["content_version_id"]),
            "status": "existing",
        }
    ]
    hub.content_hub_record_source_portal_daily(first, database_url=url, schema=schema)
    discovered = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    assert "Synthetic AI study" in discovered["description_en"]
    later_version = _version(article_url, schema, url, root, later_body)
    _annotate(url, schema, later_version["content_version_id"], "AI")
    later = _capture(day="2026-11-11", raw_sha=later_sha)
    hub.content_hub_record_source_portal_daily(later, database_url=url, schema=schema)
    unchanged = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-11",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    assert unchanged["description_en"].startswith("No new AI materials")
    assert "Synthetic AI study" not in unchanged["description_en"]


def test_missing_cas_and_conflicting_category_stop_revision(tmp_path: Path):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    body = b"synthetic original for evidence checks"
    sha = hashlib.sha256(body).hexdigest()
    evidence = _capture(raw_sha=sha)
    hub.content_hub_record_source_portal_daily(evidence, database_url=url, schema=schema)
    version = _version(article_url, schema, url, root, body)
    _annotate(url, schema, version["content_version_id"], "AI")
    project = partial(
        hub.content_hub_project_source_portal_daily,
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    cas = root / "cas" / "sha256" / sha[:2] / sha
    cas.unlink()
    with pytest.raises(hub.ContentHubError, match="verified live original"):
        project()
    cas.write_bytes(body)
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "UPDATE article_enrichment_annotations SET source_primary_category = 'Other' "
                "WHERE content_version_id = %s",
                (version["content_version_id"],),
            )
    with pytest.raises(hub.ContentHubError, match="conflicts with primary"):
        project()
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "UPDATE article_enrichment_annotations SET source_primary_category = 'AI' "
                "WHERE content_version_id = %s",
                (version["content_version_id"],),
            )
    assert "Synthetic AI study" in project()["description_en"]


def test_bounded_resume_json_uses_saved_hub_only_and_repeats_cleanly(
    tmp_path: Path, monkeypatch, capsys
):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    old_body = b"synthetic original classified Other"
    old_sha = hashlib.sha256(old_body).hexdigest()
    old_evidence = _capture(day="2026-11-05", raw_sha=old_sha, title="Older Other version")
    prior = hub.content_hub_record_source_portal_daily(
        old_evidence, database_url=url, schema=schema
    )
    old_version = _version(old_evidence["observations"][0]["url"], schema, url, root, old_body)
    _annotate(url, schema, old_version["content_version_id"], "Other")
    body = b"synthetic saved original for bounded replay"
    sha = hashlib.sha256(body).hexdigest()
    evidence = _capture(raw_sha=sha)
    first = hub.content_hub_record_source_portal_daily(evidence, database_url=url, schema=schema)
    version = _version(evidence["observations"][0]["url"], schema, url, root, body)
    _annotate(url, schema, version["content_version_id"], "AI")
    connection_file = tmp_path / "synthetic-hub-url.json"
    connection_file.write_text(json.dumps({"database_url": url}), encoding="utf-8")
    config_file = tmp_path / "synthetic-config.json"
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "data_root": str(root),
                "state_root": str(tmp_path / "state"),
                "hub_connection_file": str(connection_file),
                "targets": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime,
        "content_hub_project_source_portal_daily",
        partial(hub.content_hub_project_source_portal_daily, schema=schema),
    )
    monkeypatch.setattr(
        runtime,
        "content_hub_latest_source_portal_update",
        partial(hub.content_hub_latest_source_portal_update, schema=schema),
    )
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    args = [
        "resume-daily-projection",
        "--portal",
        "cia-publications",
        "--date",
        "2026-11-06",
        "--config",
        str(config_file),
        "--json",
    ]
    assert runtime.main(args) == 2  # No serving targets are configured in this synthetic test.
    first_output = json.loads(capsys.readouterr().out)
    assert first_output["sync"]["status"] == "deferred"
    assert first_output["projection"]["capture_kind"] == "daily_projection"
    assert first_output["projection"]["capture_id"] > first["capture_id"]
    assert "Synthetic AI study" in first_output["projection"]["description_en"]
    assert runtime.main(args) == 2
    repeat = json.loads(capsys.readouterr().out)
    assert repeat["projection"]["duplicate"] is True
    assert repeat["projection"]["capture_id"] == first_output["projection"]["capture_id"]
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT count(*) FROM source_portal_captures "
                "WHERE capture_kind = 'daily_projection'"
            )
            assert cursor.fetchone()[0] == 1
    saved_prior = hub.content_hub_read_source_portal_capture(
        portal_key="cia-publications",
        capture_id=prior["capture_id"],
        database_url=url,
        schema=schema,
    )
    assert saved_prior["evidence_sha256"] == hub.validate_daily_evidence(old_evidence)[2]
    assert saved_prior["description_en"] == prior["description_en"]


def test_soa_revision_preserves_article_and_structure_text(tmp_path: Path):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    article_url = "https://www.soa.org/research/synthetic-ai-study.pdf"
    body = b"synthetic SOA article original"
    sha = hashlib.sha256(body).hexdigest()
    first = _capture(raw_sha=sha, url=article_url, site="soa-ai-bulletin-focused")
    first["portal_key"] = portal.portal_key
    first["observations"][0]["source_page_url"] = portal.url
    first["run_id"] = hashlib.sha256(b"synthetic-soa-run").hexdigest()
    hub.content_hub_record_source_portal_daily(first, database_url=url, schema=schema)
    base_entries = [{"url": "https://www.soa.org/research/ai-base", "title": "Base resource"}]
    directory_args = {
        "portal_key": portal.portal_key,
        "page_url": portal.url,
        "scope_key": "ai-resources-v1",
        "acquired_on": "2026-11-05",
        "captured_at": "2026-11-05T08:00:00-05:00",
        "page_sha256": "b" * 64,
        "entries": base_entries,
        "complete": True,
        "intro_zh": portal.overview_zh,
        "intro_en": portal.overview_en,
        "database_url": url,
        "schema": schema,
    }
    hub.content_hub_record_source_portal_capture(**directory_args)
    changed = hub.content_hub_record_source_portal_capture(
        **{
            **directory_args,
            "acquired_on": "2026-11-06",
            "captured_at": "2026-11-06T09:00:00-05:00",
            "page_sha256": "c" * 64,
            "entries": [
                *base_entries,
                {"url": "https://www.soa.org/research/ai-new", "title": "New structure resource"},
            ],
        }
    )
    assert "New structure resource" in changed["description_en"]
    version = hub.ingest_live_article(
        canonical_url=article_url,
        source_site="soa-ai-bulletin-focused",
        source_page_url=portal.url,
        title="Synthetic AI study",
        raw_bytes=body,
        markdown="Synthetic AI study",
        content_type="application/pdf",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    _annotate(url, schema, version["content_version_id"], "AI")
    revision = hub.content_hub_project_source_portal_daily(
        portal_key=portal.portal_key,
        acquired_on="2026-11-06",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    assert revision["captured_at"] == changed["captured_at"]
    combined = hub.content_hub_project_source_portal_update(
        portal_key=portal.portal_key,
        acquired_on="2026-11-06",
        database_url=url,
        schema=schema,
    )
    assert "Synthetic AI study" in combined["description_en"]
    assert "New structure resource" in combined["description_en"]
    assert combined["description_en"].index("Synthetic AI study") < combined[
        "description_en"
    ].index("New structure resource")


@pytest.mark.parametrize(
    ("earlier_day", "earlier_kind"),
    [
        ("2026-11-06", "unverified_sha"),
        ("2026-11-05", "unverified_sha"),
        ("2026-11-05", "navigation"),
        ("2026-11-06", "hub_only"),
    ],
)
def test_first_verified_observation_ignores_ineligible_url_history(
    tmp_path: Path, earlier_day: str, earlier_kind: str
):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    body = b"first verified synthetic original"
    sha = hashlib.sha256(body).hexdigest()
    earlier = _capture(day=earlier_day, hour=6, raw_sha="b" * 64)
    if earlier_kind == "navigation":
        earlier["observations"][0].update(kind="page", is_article=False)
    elif earlier_kind == "hub_only":
        earlier["observations"][0].update(
            url="https://www.cia-ica.ca/publications/navigation", is_article=False
        )
        earlier["hub_results"] = [
            {
                "url": article_url,
                "raw_sha256": sha,
                "source_page_url": SOURCE_PORTALS_BY_KEY["cia-publications"].url,
                "content_version_id": "1",
                "status": "existing",
            }
        ]
    hub.content_hub_record_source_portal_daily(earlier, database_url=url, schema=schema)
    later = _capture(day="2026-11-06", hour=7, raw_sha=sha)
    later["run_id"] = hashlib.sha256(f"later|{earlier_kind}".encode()).hexdigest()
    hub.content_hub_record_source_portal_daily(later, database_url=url, schema=schema)
    version = _version(article_url, schema, url, root, body)
    _annotate(url, schema, version["content_version_id"], "AI")
    revised = hub.content_hub_project_source_portal_daily(
        portal_key="cia-publications",
        acquired_on="2026-11-06",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    assert revised["acquired_on"] == "2026-11-06"
    assert revised["description_en"].startswith("Found 1 new AI material")
    assert "Synthetic AI study" in revised["description_en"]
    expected_dates = [("cia-publications", "2026-11-06")]
    if earlier_day == "2026-11-05" and earlier_kind == "unverified_sha":
        expected_dates.insert(0, ("cia-publications", "2026-11-05"))
    assert (
        hub.content_hub_source_portal_dates_for_versions(
            [version["content_version_id"]], database_url=url, schema=schema
        )
        == expected_dates
    )


def test_later_directory_reuses_unchanged_revision_and_changed_prose_advances_at_same_time(
    tmp_path: Path, monkeypatch
):
    url, schema = _hub(tmp_path)
    root = tmp_path / "originals"
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    article_url = "https://www.cia-ica.ca/publications/synthetic-study"
    body = b"first synthetic source"
    sha = hashlib.sha256(body).hexdigest()
    first = _capture(raw_sha=sha)
    hub.content_hub_record_source_portal_daily(first, database_url=url, schema=schema)
    version = _version(article_url, schema, url, root, body)
    _annotate(url, schema, version["content_version_id"], "AI")
    project = partial(
        hub.content_hub_project_source_portal_daily,
        portal_key=portal.portal_key,
        acquired_on="2026-11-06",
        data_root=root,
        database_url=url,
        schema=schema,
    )
    initial = project()
    targets = {
        target: uninitialized_postgres_url_for_path(tmp_path / target)
        for target in ("china", "overseas")
    }
    for target_url in targets.values():
        Storage(target_url).close()

    def stream(_config, target, updates):
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        )

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    monkeypatch.setattr(
        runtime,
        "content_hub_latest_source_portal_update",
        partial(hub.content_hub_latest_source_portal_update, schema=schema),
    )
    state = {"pending_source_portal_publications": {}}
    config = {"targets": {target: {"host": "synthetic"} for target in targets}}
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], portal.portal_key, initial, hub=url
    )
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    directory = hub.content_hub_record_source_portal_capture(
        portal_key=portal.portal_key,
        page_url=portal.url,
        scope_key="synthetic-structure",
        captured_at="2026-11-06T10:00:00-05:00",
        acquired_on="2026-11-06",
        page_sha256="c" * 64,
        complete=True,
        entries=[
            {
                "url": "https://www.cia-ica.ca/publications/new-structure",
                "title": "New structure resource",
            }
        ],
        intro_zh="合成入口",
        intro_en="Synthetic directory",
        database_url=url,
        schema=schema,
    )
    assert directory["projection_present"] is True
    assert project()["capture_id"] == initial["capture_id"]
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT count(*) FROM source_portal_captures "
                "WHERE portal_key = %s AND acquired_on = %s AND capture_kind = 'daily_projection'",
                (portal.portal_key, "2026-11-06"),
            )
            assert cursor.fetchone()[0] == 1
    combined = hub.content_hub_latest_source_portal_update(
        portal_key=portal.portal_key,
        acquired_on="2026-11-06",
        database_url=url,
        schema=schema,
    )
    assert combined["captured_at"] == directory["captured_at"]
    assert combined["capture_id"] == directory["capture_id"]
    assert "Synthetic AI study" in combined["description_en"]
    assert "New structure resource" in combined["description_en"]
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], portal.portal_key, directory, hub=url
    )
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            actual = storage._conn.execute(
                "SELECT capture_id, captured_at FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                (portal.portal_key, "2026-11-06"),
            ).fetchone()
            assert int(actual[0]) == directory["capture_id"]
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == portal.portal_key
        )
        assert "Synthetic AI study" in card["updates"][0]["description_en"]
        assert "New structure resource" in card["updates"][0]["description_en"]

    second_url = "https://www.cia-ica.ca/publications/second-synthetic-study"
    second_body = b"second synthetic source"
    second_sha = hashlib.sha256(second_body).hexdigest()
    second = _capture(hour=9, url=second_url, raw_sha=second_sha, title="Second AI study")
    hub.content_hub_record_source_portal_daily(second, database_url=url, schema=schema)
    second_version = _version(second_url, schema, url, root, second_body)
    _annotate(url, schema, second_version["content_version_id"], "AI")
    changed = project()
    assert changed["capture_kind"] == "daily_projection"
    assert changed["capture_id"] > directory["capture_id"]
    assert changed["captured_at"] == directory["captured_at"]
    assert project()["capture_id"] == changed["capture_id"]
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], portal.portal_key, changed, hub=url
    )
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    for target_url in targets.values():
        storage = Storage(target_url)
        try:
            actual = storage._conn.execute(
                "SELECT capture_id FROM source_portal_updates "
                "WHERE portal_key = ? AND acquired_on = ?",
                (portal.portal_key, "2026-11-06"),
            ).fetchone()
            assert int(actual[0]) == changed["capture_id"]
        finally:
            storage.close()
        card = next(
            card
            for card in list_source_portals(db_path=target_url)["portals"]
            if card["portal_key"] == portal.portal_key
        )
        assert "Second AI study" in card["updates"][0]["description_en"]
        assert "New structure resource" in card["updates"][0]["description_en"]

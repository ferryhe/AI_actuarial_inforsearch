from __future__ import annotations

import json
import sqlite3

import pytest

from ai_actuarial.manifest_ingest import ManifestIngestError, content_kind_for, ingest_manifest
from ai_actuarial.storage import Storage


def _sample_manifest() -> dict:
    return {
        "schema_version": "web-listening-manifest.v1",
        "manifest_id": "manifest-test-001",
        "generated_at": "2026-04-07T15:30:00Z",
        "source": {
            "source_id": "soa",
            "site_url": "https://www.soa.org/",
            "site_name": "Society of Actuaries",
        },
        "run": {"run_id": "run-soa-001"},
        "downloaded_assets": [
            {
                "asset_id": "asset-pdf-001",
                "url": "https://www.soa.org/sample-report.pdf",
                "local_path": "data/downloads/_tracked/soa/sample-report.pdf",
                "canonical_blob_path": "data/downloads/_blobs/01/23/sample.pdf",
                "filename": "sample-report.pdf",
                "media_type": "application/pdf",
                "bytes": 123456,
                "checksum": {"algorithm": "sha256", "value": "a" * 64},
            },
            {
                "asset_id": "asset-html-001",
                "url": "https://www.soa.org/research/",
                "local_path": "data/downloads/_tracked/soa/research.html",
                "filename": "research.html",
                "media_type": "text/html",
                "bytes": 5000,
                "checksum": {"algorithm": "sha256", "value": "b" * 64},
            },
        ],
    }


def test_content_kind_for() -> None:
    assert content_kind_for("text/html") == "web_page"
    assert content_kind_for("text/html; charset=utf-8") == "web_page"
    assert content_kind_for("application/pdf") == "file"
    assert content_kind_for(None) == "file"


def test_upsert_file_default_content_kind() -> None:
    storage = Storage(":memory:")
    try:
        storage.upsert_file(
            url="https://example.com/a.pdf",
            sha256="c" * 64,
            title="a.pdf",
            source_site="site",
            source_page_url=None,
            original_filename="a.pdf",
            local_path="a.pdf",
            bytes_size=100,
            content_type="application/pdf",
            last_modified=None,
            etag=None,
            published_time=None,
        )
        row = storage._conn.execute(
            "SELECT content_kind FROM files WHERE url = ?", ("https://example.com/a.pdf",)
        ).fetchone()
        assert row[0] == "file"
    finally:
        storage.close()


def test_upsert_file_explicit_web_page_kind() -> None:
    storage = Storage(":memory:")
    try:
        storage.upsert_file(
            url="https://example.com/page",
            sha256="d" * 64,
            title="page",
            source_site="site",
            source_page_url=None,
            original_filename="page.md",
            local_path="page.md",
            bytes_size=100,
            content_type="text/markdown",
            last_modified=None,
            etag=None,
            published_time=None,
            content_kind="web_page",
        )
        row = storage._conn.execute(
            "SELECT content_kind FROM files WHERE url = ?", ("https://example.com/page",)
        ).fetchone()
        assert row[0] == "web_page"
    finally:
        storage.close()


def test_v4_migration_adds_content_kind_and_manifest_raw(tmp_path) -> None:
    from ai_actuarial.sqlite_schema import apply_schema

    db_path = str(tmp_path / "v3.db")
    storage = Storage(db_path)
    try:
        # Downgrade a fresh v4 database back to v3 shape: drop content_kind and
        # manifest_raw, then rewind the user_version so apply_schema migrates it.
        storage._conn.execute("ALTER TABLE files DROP COLUMN content_kind")
        storage._conn.execute("DROP TABLE manifest_raw")
        storage._conn.execute("PRAGMA user_version=3")
        storage._conn.commit()
    finally:
        storage.close()

    result = apply_schema(db_path)
    assert result["state"] == "current"

    conn = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(files)")}
        assert "content_kind" in cols
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "manifest_raw" in tables
    finally:
        conn.close()


def test_v4_migration_backfills_html_rows_as_web_page(tmp_path) -> None:
    from ai_actuarial.sqlite_schema import apply_schema

    db_path = str(tmp_path / "backfill.db")
    storage = Storage(db_path)
    try:
        storage._conn.execute(
            "INSERT INTO files (url, sha256, title, content_type, first_seen, last_seen) "
            "VALUES ('https://example.com/page.html', 'a1', 'Page', 'text/html', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        storage._conn.execute(
            "INSERT INTO files (url, sha256, title, content_type, first_seen, last_seen) "
            "VALUES ('https://example.com/doc.pdf', 'b2', 'Doc', 'application/pdf', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        storage._conn.commit()
        # Downgrade to v3 (drop content_kind + manifest_raw, rewind version),
        # then let apply_schema re-run the v4 migration with its backfill.
        storage._conn.execute("ALTER TABLE files DROP COLUMN content_kind")
        storage._conn.execute("DROP TABLE manifest_raw")
        storage._conn.execute("PRAGMA user_version=3")
        storage._conn.commit()
    finally:
        storage.close()

    result = apply_schema(db_path)
    assert result["state"] == "current"

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT content_type, content_kind FROM files ORDER BY content_type"
        ).fetchall()
        assert rows == [
            ("application/pdf", "file"),
            ("text/html", "web_page"),
        ]
    finally:
        conn.close()


def test_ingest_manifest_stores_raw() -> None:
    storage = Storage(":memory:")
    try:
        ingest_manifest(storage, _sample_manifest())
        row = storage._conn.execute(
            "SELECT manifest_id, schema_version, manifest_json FROM manifest_raw"
        ).fetchone()
        assert row[0] == "manifest-test-001"
        assert row[1] == "web-listening-manifest.v1"
        assert "sample-report.pdf" in row[2]
    finally:
        storage.close()


def test_ingest_manifest_maps_assets_to_files() -> None:
    storage = Storage(":memory:")
    try:
        ingest_manifest(storage, _sample_manifest())
        rows = storage._conn.execute(
            "SELECT url, content_kind, sha256 FROM files ORDER BY url"
        ).fetchall()
        assert len(rows) == 2
        pdf = next(r for r in rows if r[0].endswith(".pdf"))
        html = next(r for r in rows if r[0].endswith("/research/"))
        assert pdf[1] == "file"
        assert html[1] == "web_page"
        assert len(pdf[2]) == 64
    finally:
        storage.close()


def test_ingest_manifest_is_idempotent() -> None:
    storage = Storage(":memory:")
    try:
        first = ingest_manifest(storage, _sample_manifest())
        second = ingest_manifest(storage, _sample_manifest())
        assert first["imported"] == 2
        assert second["imported"] == 2
        count = storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 2  # no duplicates after replay
    finally:
        storage.close()


def test_ingest_manifest_rejects_non_sha256_checksum() -> None:
    manifest = _sample_manifest()
    manifest["downloaded_assets"][0]["checksum"] = {"algorithm": "md5", "value": "e" * 32}
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.code == "invalid_manifest_contract"
        assert exc_info.value.field == "downloaded_assets[0].checksum.algorithm"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_rejects_non_dict_checksum() -> None:
    manifest = _sample_manifest()
    manifest["downloaded_assets"][0]["checksum"] = "not-a-dict"
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.field == "downloaded_assets[0].checksum"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_rejects_missing_manifest_id() -> None:
    manifest = _sample_manifest()
    del manifest["manifest_id"]
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.field == "manifest_id"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_empty_assets_still_archives_raw() -> None:
    manifest = _sample_manifest()
    manifest["downloaded_assets"] = []
    storage = Storage(":memory:")
    try:
        result = ingest_manifest(storage, manifest)
        assert result["imported"] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 1
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_rejects_asset_without_url() -> None:
    manifest = _sample_manifest()
    del manifest["downloaded_assets"][0]["url"]
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.field == "downloaded_assets[0].url"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_stores_raw_text_byte_for_byte() -> None:
    raw = (
        '{"schema_version":"web-listening-manifest.v1","manifest_id":"m-raw",\n'
        '  "run":{"run_id":"run-raw"},'
        '"source":{"source_id":"source-raw","site_name":"Raw",'
        '"site_url":"https://example.com/"},"downloaded_assets": []}'
    )
    manifest = json.loads(raw)
    storage = Storage(":memory:")
    try:
        ingest_manifest(storage, manifest, raw_text=raw)
        row = storage._conn.execute(
            "SELECT manifest_json FROM manifest_raw WHERE manifest_id = ?", ("m-raw",)
        ).fetchone()
        assert row[0] == raw  # byte-for-byte provenance
    finally:
        storage.close()


def test_ingest_manifest_rejects_non_dict_assets() -> None:
    manifest = _sample_manifest()
    manifest["downloaded_assets"] = [
        "not-a-dict",
        None,
        {
            "url": "https://example.com/valid",
            "checksum": {"algorithm": "sha256", "value": "a" * 64},
        },
    ]
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.field == "downloaded_assets[0]"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_rejects_non_list_assets() -> None:
    manifest = _sample_manifest()
    manifest["downloaded_assets"] = "not-a-list"
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.field == "downloaded_assets"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_ingest_manifest_rejects_non_string_media_type() -> None:
    manifest = _sample_manifest()
    manifest["downloaded_assets"][0]["media_type"] = 12345  # non-string
    storage = Storage(":memory:")
    try:
        with pytest.raises(ManifestIngestError) as exc_info:
            ingest_manifest(storage, manifest)
        assert exc_info.value.field == "downloaded_assets[0].media_type"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()

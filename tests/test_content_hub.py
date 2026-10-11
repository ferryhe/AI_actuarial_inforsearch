from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest

import ai_actuarial.source_stage as source_stage
from ai_actuarial.content_hub import (
    ContentHubError,
    apply_content_hub_schema,
    content_hub_schema_plan,
    content_hub_show_url,
    content_hub_status,
    import_content_snapshot,
)
from ai_actuarial.postgres_import import _source_snapshot
from ai_actuarial.source_stage import (
    SOURCE_STAGE_FORMAT,
    SourceStageError,
    encode_source_row,
    source_stage_schema_plan,
    stage_sqlite_v16,
)
from ai_actuarial.storage import Storage
from tests.postgres_helpers import uninitialized_postgres_url_for_path


def _isolated_database_schema(tmp_path: Path, name: str) -> tuple[str, str]:
    url = uninitialized_postgres_url_for_path(tmp_path / f"{name}.db")
    connection = psycopg2.connect(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = str(cursor.fetchone()[0])
    finally:
        connection.close()
    return url, schema


def _other_database_name(url: str, database: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))


@pytest.mark.parametrize(
    ("stage_url", "hub_url"),
    [
        (
            "postgresql://review@localhost:55434/content_hub",
            "postgresql://review@127.0.0.1:55434/content_hub",
        ),
        (
            "postgresql://review@localhost:55434/content_hub",
            "postgresql://review@[::1]:55434/content_hub",
        ),
        (
            "postgresql://review@[::1]:55434/content_hub",
            "postgresql://review@127.0.0.1:55434/content_hub",
        ),
        (
            "postgresql://review@pg.local:55434/content_hub?hostaddr=127.0.0.1",
            "postgresql://review@localhost:55434/content_hub",
        ),
    ],
)
def test_loopback_aliases_cannot_bypass_database_separation(
    tmp_path: Path, monkeypatch, stage_url: str, hub_url: str
) -> None:
    connection_attempts = []

    def record_connection(_database_url):
        connection_attempts.append(True)
        pytest.fail("Database separation must be checked before connecting or writing a schema")

    monkeypatch.setattr(source_stage, "_connect", record_connection)
    source_path = tmp_path / "source-must-not-be-opened.db"
    with pytest.raises(SourceStageError, match="separate PostgreSQL databases"):
        stage_sqlite_v16(source_path, "same-db", stage_url, hub_database_url=hub_url)
    assert not connection_attempts
    assert not source_path.exists()


def _add_column_if_missing(
    connection: sqlite3.Connection, table: str, column: str, declaration: str = "TEXT"
) -> None:
    existing = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
    if column not in existing:
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}')


def _create_v16_source(
    path: Path, payload: bytes, *, source_label: str
) -> tuple[str, dict[str, int]]:
    storage = Storage._legacy_sqlite_schema_for_validation(path)
    try:
        connection = storage._conn
        for name in (
            "title",
            "source_site",
            "original_filename",
            "local_path",
            "keywords_json",
            "markdown_source",
            "rag_indexed_at",
        ):
            _add_column_if_missing(connection, "catalog_items", name)
        for name in ("rag_chunk_count", "rag_indexed"):
            _add_column_if_missing(connection, "catalog_items", name, "INTEGER")
        digest = hashlib.sha256(payload).hexdigest()
        urls = (
            "https://content.example.test/primary?version=1",
            "https://content.example.test/alias?version=1",
        )
        for file_id, url in enumerate(urls, 101):
            connection.execute(
                "INSERT INTO files (id, url, sha256, title, bytes, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    url,
                    digest,
                    f"{source_label} title {file_id}",
                    len(payload),
                    "2026-10-01" if file_id == 101 else None,
                ),
            )
            connection.execute(
                "INSERT INTO catalog_items "
                "(rowid, file_url, sha256, pipeline_version, status, keywords, keywords_json, "
                "summary, category, markdown_content, title, source_site, original_filename, local_path, "
                "markdown_source, rag_chunk_count, rag_indexed_at, rag_indexed) "
                "VALUES (?, ?, ?, ?, 'ok', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id + 200,
                    url,
                    digest,
                    "recipe-v16",
                    "life; health",
                    '["life", "health"]',
                    (f"{source_label} actuarial summary " * 20),
                    "Insurance",
                    f"{source_label} markdown\x00preserved",
                    f"{source_label} catalog title {file_id}",
                    "legacy-site",
                    "source.pdf",
                    f"legacy/{source_label}/{file_id}.pdf",
                    "catalog-import\x00provenance",
                    7,
                    "2026-10-03T08:00:00Z",
                    1,
                ),
            )
        connection.execute(
            "INSERT INTO auth_tokens (id, subject, group_name, token_hash, is_active, token_type) "
            "VALUES (?, ?, ?, ?, 1, 'standard')",
            (900, "staging-only-user", "admin", sqlite3.Binary(b"\x00\xffprivate-test")),
        )
        connection.commit()
    finally:
        storage.close()

    source, metadata, counts, source_sha = _source_snapshot(path)
    source.rollback()
    source.close()
    assert "files" in metadata and "catalog_items" in metadata
    return source_sha, counts


def _write_manifest(
    source_path: Path,
    source_name: str,
    artifact_root: Path,
    payload: bytes,
    table_counts: dict[str, int],
) -> tuple[Path, str]:
    digest = hashlib.sha256(payload).hexdigest()
    cas_relpath = f"cas/sha256/{digest[:2]}/{digest}"
    artifact_path = artifact_root / Path(*cas_relpath.split("/"))
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(payload)
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest = {
        "format": "ai_actuarial.content_hub.artifact_manifest",
        "version": 1,
        "source_name": source_name,
        "snapshot": {
            "sha256": source_sha,
            "bytes": source_path.stat().st_size,
            "sqlite_user_version": 16,
            "wal_checkpointed": True,
            "table_counts": table_counts,
        },
        "files": [
            {
                "legacy_id": file_id,
                "url": url,
                "raw_sha256": digest,
                "bytes": len(payload),
                "state": "present",
                "deleted_at": "2026-10-01" if file_id == 101 else None,
                "cas_relpath": cas_relpath,
                "verified_sha256": digest,
            }
            for file_id, url in (
                (101, "https://content.example.test/primary?version=1"),
                (102, "https://content.example.test/alias?version=1"),
            )
        ],
        "indexes": [
            {
                "legacy_kb_id": "legacy-kb-100",
                "artifact_kind": "faiss_index",
                "source_path": f"D:/legacy/{source_name}/index.faiss",
                "artifact_relpath": None,
                "sha256": None,
                "bytes": None,
                "state": "missing",
                "embedding_identity": {
                    "provider": "unknown",
                    "model": "unknown",
                    "dimension": 1024 if source_name == "overseas" else 3072,
                    "profile_id": "unknown",
                },
                "source_metadata": {"identity": "source-specific"},
            }
        ],
        "source_staging": {
            "database_name": f"legacy_{source_name}_20261011_raw",
            "snapshot_sha256": source_sha,
        },
    }
    manifest_path = artifact_root / "manifests" / source_name / f"{source_sha}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return manifest_path, source_sha


def test_source_stage_preserves_nul_blob_rowid_and_rejects_conflicts(
    tmp_path: Path, monkeypatch
) -> None:
    postgres_url, schema = _isolated_database_schema(tmp_path, "stage")
    source_path = tmp_path / "source-v16.db"
    source_sha, expected_counts = _create_v16_source(
        source_path, b"source bytes\x00", source_label="stage"
    )
    other_database_url = _other_database_name(postgres_url, "unconnected_content_hub_test")

    with pytest.raises(SourceStageError, match="separate PostgreSQL databases"):
        stage_sqlite_v16(
            source_path, "stage-source", postgres_url, hub_database_url=postgres_url, schema=schema
        )

    plan = source_stage_schema_plan(postgres_url, schema=schema)
    assert plan["current_version"] == 0
    assert plan["pending"] == [{"version": 1, "file": "0001_lossless_source_stage.sql"}]
    result = stage_sqlite_v16(
        source_path,
        "stage-source",
        postgres_url,
        hub_database_url=other_database_url,
        schema=schema,
    )
    assert result["state"] == "verified"
    assert result["table_counts"] == expected_counts
    assert result["row_format"] == SOURCE_STAGE_FORMAT
    assert result["snapshot_sha256"] == source_sha

    connection = psycopg2.connect(postgres_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_json, table_counts_json, table_digests_json FROM snapshot"
            )
            schema_json, counts_json, digests_json = cursor.fetchone()
            assert json.loads(counts_json) == expected_counts
            assert set(json.loads(digests_json)) == set(expected_counts)
            metadata = json.loads(schema_json)
            catalog_columns = metadata["columns"]["catalog_items"]
            catalog_fields = catalog_columns
            markdown_index = catalog_fields.index("markdown_content")
            cursor.execute(
                "SELECT row_json FROM table_rows WHERE table_name = 'catalog_items' ORDER BY row_number"
            )
            catalog_rows = [json.loads(row[0]) for row in cursor.fetchall()]
            assert {row["rowid"] for row in catalog_rows} == {301, 302}
            assert {row["values"][markdown_index] for row in catalog_rows} == {
                "stage markdown\x00preserved"
            }
            token_columns = metadata["columns"]["auth_tokens"]
            token_hash_index = token_columns.index("token_hash")
            cursor.execute("SELECT row_json FROM table_rows WHERE table_name = 'auth_tokens'")
            token_row = json.loads(cursor.fetchone()[0])
            assert token_row["values"][token_hash_index] == {
                "sqlite_blob_hex": b"\x00\xffprivate-test".hex()
            }
    finally:
        connection.close()

    assert (
        stage_sqlite_v16(
            source_path,
            "stage-source",
            postgres_url,
            hub_database_url=other_database_url,
            schema=schema,
        )["state"]
        == "unchanged"
    )

    changed_source = tmp_path / "changed-source-v16.db"
    changed_source.write_bytes(source_path.read_bytes())
    connection = sqlite3.connect(changed_source)
    try:
        connection.execute("UPDATE files SET title = 'different source snapshot' WHERE id = 101")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(SourceStageError, match="different source snapshot"):
        stage_sqlite_v16(
            changed_source,
            "stage-source",
            postgres_url,
            hub_database_url=other_database_url,
            schema=schema,
        )

    copied_source = tmp_path / "copied-source-v16.db"
    copied_source.write_bytes(source_path.read_bytes())
    with pytest.raises(SourceStageError, match="different source snapshot"):
        stage_sqlite_v16(
            copied_source,
            "another-source",
            postgres_url,
            hub_database_url=other_database_url,
            schema=schema,
        )

    connection = psycopg2.connect(postgres_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT source_name, source_sha256 FROM snapshot")
            assert cursor.fetchone() == ("stage-source", source_sha)
            cursor.execute("SELECT COUNT(*) FROM table_rows")
            assert int(cursor.fetchone()[0]) == sum(expected_counts.values())
    finally:
        connection.close()


def test_content_hub_import_keeps_alias_versions_text_and_source_namespaces(tmp_path: Path) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "hub")
    assert content_hub_schema_plan(hub_url, schema=schema)["current_version"] == 0
    assert apply_content_hub_schema(hub_url, schema=schema)["version"] == 1
    artifact_root = tmp_path / "shared-hub-root"
    first_path = tmp_path / "overseas-v16.db"
    second_path = tmp_path / "china-v16.db"
    first_payload = b"overseas pdf bytes\x00"
    second_payload = b"china pdf bytes\x00"
    _, first_counts = _create_v16_source(first_path, first_payload, source_label="overseas")
    _, second_counts = _create_v16_source(second_path, second_payload, source_label="china")
    first_manifest, first_sha = _write_manifest(
        first_path, "overseas", artifact_root, first_payload, first_counts
    )
    second_manifest, second_sha = _write_manifest(
        second_path, "china", artifact_root, second_payload, second_counts
    )

    first = import_content_snapshot(
        first_path,
        first_manifest,
        artifact_root,
        tmp_path / "data",
        hub_url,
        schema=schema,
        expected_source_name="overseas",
    )
    assert first["already_imported"] is False
    assert first["table_count"] == len(first_counts)
    assert first["file_observation_count"] == 2
    repeated = import_content_snapshot(
        first_path,
        first_manifest,
        artifact_root,
        tmp_path / "data",
        hub_url,
        schema=schema,
        expected_source_name="overseas",
    )
    assert repeated["already_imported"] is True

    second = import_content_snapshot(
        second_path,
        second_manifest,
        artifact_root,
        tmp_path / "data",
        hub_url,
        schema=schema,
        expected_source_name="china",
    )
    assert second["already_imported"] is False
    assert first_sha != second_sha

    url = "https://content.example.test/primary?version=1"
    shown = content_hub_show_url(url, hub_url, schema=schema)
    assert len(shown["versions"]) == 2
    assert {variant["source_name"] for variant in shown["text_variants"]} == {"overseas", "china"}
    catalog_records = [
        record for record in shown["source_records"] if record["source_table"] == "catalog_items"
    ]
    assert {record["source_name"] for record in catalog_records} == {"overseas", "china"}
    assert all(
        record["source_metadata"]["pipeline_version"] == "recipe-v16" for record in catalog_records
    )
    assert all(
        record["source_metadata"]["source_site"] == "legacy-site" for record in catalog_records
    )
    assert all(
        record["source_metadata"]["markdown_source"] == "catalog-import\x00provenance"
        for record in catalog_records
    )
    assert all(record["source_metadata"]["rag_chunk_count"] == 7 for record in catalog_records)
    assert all(record["source_metadata"]["rag_indexed"] == 1 for record in catalog_records)
    markdown = [
        variant for variant in shown["text_variants"] if variant["field_name"] == "markdown_content"
    ]
    assert {variant["value"] for variant in markdown} == {
        "overseas markdown\x00preserved",
        "china markdown\x00preserved",
    }
    assert all(variant["model_identity"] == "unknown" for variant in markdown)
    assert all(variant["recipe_identity"] == "recipe-v16" for variant in markdown)
    assert len(shown["source_file_observations"]) == 2
    assert any(
        observation["deleted_at"] == "2026-10-01"
        for observation in shown["source_file_observations"]
    )

    status = content_hub_status(hub_url, schema=schema)
    assert status["source_count"] == 2
    assert status["content_version_count"] == 4
    assert status["content_blob_counts"] == {"present": 2, "missing": 0}
    assert status["source_file_observation_count"] == 4
    assert status["legacy_index_artifact_counts"] == {"present": 0, "missing": 2}

    original_manifest = first_manifest.read_text(encoding="utf-8")
    manifest_doc = json.loads(original_manifest)
    manifest_doc["indexes"].append(
        {
            "legacy_kb_id": "late-index-metadata",
            "artifact_kind": "embedding_profile",
            "source_path": None,
            "artifact_relpath": None,
            "sha256": None,
            "bytes": None,
            "state": "missing",
            "embedding_identity": {
                "provider": "unknown",
                "model": "unknown",
                "dimension": 999,
                "profile_id": "unknown",
            },
            "source_metadata": {},
        }
    )
    first_manifest.write_text(
        json.dumps(manifest_doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    with pytest.raises(ContentHubError, match="conflicts with this manifest"):
        import_content_snapshot(
            first_path,
            first_manifest,
            artifact_root,
            tmp_path / "data",
            hub_url,
            schema=schema,
            expected_source_name="overseas",
        )

    first_manifest.write_text(original_manifest, encoding="utf-8")
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_snapshot_id FROM source_snapshots WHERE source_name = %s",
                ("overseas",),
            )
            first_snapshot_id = int(cursor.fetchone()[0])
            cursor.execute(
                "DELETE FROM source_record_map WHERE source_snapshot_id = %s AND source_table = 'files' "
                "AND legacy_pk_json::json->>'pk' = '101'",
                (first_snapshot_id,),
            )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ContentHubError, match="crosswalk count"):
        import_content_snapshot(
            first_path,
            first_manifest,
            artifact_root,
            tmp_path / "data",
            hub_url,
            schema=schema,
            expected_source_name="overseas",
        )

    assert hashlib.sha256(first_path.read_bytes()).hexdigest() == first_sha


def test_content_import_retry_recovers_receipt_without_changing_imported_rows(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "receipt-recovery")
    apply_content_hub_schema(hub_url, schema=schema)
    source_path = tmp_path / "receipt-recovery-v16.db"
    payload = b"receipt recovery source bytes"
    _, table_counts = _create_v16_source(source_path, payload, source_label="receipt_recovery")
    artifact_root = tmp_path / "shared-hub-root"
    manifest_path, source_sha = _write_manifest(
        source_path, "receipt_recovery", artifact_root, payload, table_counts
    )
    blocked_data_root = tmp_path / "data-root-is-a-file"
    blocked_data_root.write_text("not a directory", encoding="utf-8")

    import_args = (
        source_path,
        manifest_path,
        artifact_root,
    )

    def database_state() -> tuple[list[tuple], list[tuple], list[tuple]]:
        connection = psycopg2.connect(hub_url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT source_name, snapshot_sha256 FROM source_snapshots ORDER BY source_name"
                )
                sources = cursor.fetchall()
                cursor.execute(
                    "SELECT source_table, legacy_pk_json, content_version_id, source_metadata_json "
                    "FROM source_record_map ORDER BY source_table, legacy_pk_json"
                )
                records = cursor.fetchall()
                cursor.execute(
                    "SELECT source_table, source_pk_json, field_name, payload_sha256, payload_value_json "
                    "FROM text_variants ORDER BY source_table, source_pk_json, field_name, payload_sha256"
                )
                variants = cursor.fetchall()
            return sources, records, variants
        finally:
            connection.close()

    from ai_actuarial.cli import main

    monkeypatch.setenv("CONTENT_HUB_DATABASE_URL", hub_url)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ai-actuarial",
            "content-hub",
            "import",
            "--source-name",
            "receipt_recovery",
            "--source",
            str(source_path),
            "--manifest",
            str(manifest_path),
            "--artifact-root",
            str(artifact_root),
            "--data-root",
            str(blocked_data_root),
            "--schema",
            schema,
            "--json",
        ],
    )
    assert main() == 2
    error_output = capsys.readouterr().out
    error_response = json.loads(error_output)
    assert error_response == {
        "success": False,
        "error": "Could not write the sanitized content hub import receipt",
    }
    assert str(blocked_data_root) not in error_output
    assert str(source_path) not in error_output
    assert hub_url not in error_output

    committed_state = database_state()
    assert committed_state[0] == [("receipt_recovery", source_sha)]
    assert len(committed_state[1]) == 4
    assert committed_state[2]

    data_root = tmp_path / "valid-data-root"
    retried = import_content_snapshot(
        *import_args,
        data_root,
        hub_url,
        schema=schema,
        expected_source_name="receipt_recovery",
    )
    assert retried["already_imported"] is True
    receipt_path = (
        data_root / "content-hub" / "import-receipts" / "receipt_recovery" / f"{source_sha}.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["already_imported"] is False
    assert receipt["source_name"] == "receipt_recovery"
    receipt_payload = receipt_path.read_bytes()
    assert database_state() == committed_state

    original_write_text = Path.write_text

    def forbid_receipt_rewrite(path, *args, **kwargs):
        if path == receipt_path:
            raise AssertionError("An exact rerun should leave an existing receipt untouched")
        return original_write_text(path, *args, **kwargs)

    with monkeypatch.context() as receipt_guard:
        receipt_guard.setattr(Path, "write_text", forbid_receipt_rewrite)
        repeated = import_content_snapshot(
            *import_args,
            data_root,
            hub_url,
            schema=schema,
            expected_source_name="receipt_recovery",
        )
    assert repeated["already_imported"] is True
    assert database_state() == committed_state
    assert receipt_path.read_bytes() == receipt_payload

    receipt_path.write_text('{"success":false}\n', encoding="utf-8")
    with pytest.raises(
        ContentHubError, match="Existing import receipt conflicts with the source snapshot"
    ):
        import_content_snapshot(
            *import_args,
            data_root,
            hub_url,
            schema=schema,
            expected_source_name="receipt_recovery",
        )
    assert database_state() == committed_state


def test_content_hub_cli_help_json_errors_and_stage_output(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from ai_actuarial.cli import main

    postgres_url, schema = _isolated_database_schema(tmp_path, "cli-stage")
    source_path = tmp_path / "cli-v16.db"
    source_sha, _ = _create_v16_source(source_path, b"cli source", source_label="cli")
    hub_url = _other_database_name(postgres_url, "content_hub_cli_unconnected")
    monkeypatch.setenv("CONTENT_HUB_STAGE_DATABASE_URL", postgres_url)
    monkeypatch.setenv("CONTENT_HUB_DATABASE_URL", hub_url)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ai-actuarial",
            "content-hub",
            "stage",
            "--source-name",
            "cli-source",
            "--source",
            str(source_path),
            "--schema",
            schema,
            "--json",
        ],
    )
    assert main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["success"] is True
    assert response["source_name"] == "cli-source"
    assert response["snapshot_sha256"] == source_sha
    assert postgres_url not in json.dumps(response)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ai-actuarial",
            "content-hub",
            "import",
            "--source-name",
            "cli-source",
            "--source",
            str(source_path),
            "--manifest",
            str(tmp_path / "README.md"),
            "--artifact-root",
            str(tmp_path),
            "--data-root",
            str(tmp_path / "data"),
            "--schema",
            schema,
            "--json",
        ],
    )
    assert main() == 2
    error = json.loads(capsys.readouterr().out)
    assert error["success"] is False
    assert "traceback" not in json.dumps(error).lower()


def test_encode_source_row_keeps_nul_out_of_postgresql_text() -> None:
    row = encode_source_row(40, ("text\x00tail", b"\x00\xff", 3_000_000_000))
    assert "\x00" not in row
    assert json.loads(row) == {
        "rowid": 40,
        "values": ["text\x00tail", {"sqlite_blob_hex": "00ff"}, 3_000_000_000],
    }

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest
from psycopg2 import sql

import ai_actuarial.content_hub as content_hub
import ai_actuarial.postgres as postgres
import ai_actuarial.source_stage as source_stage
from ai_actuarial.content_hub import (
    ContentHubError,
    apply_content_hub_schema,
    content_hub_ai_url_versions,
    content_hub_list_ai_versions,
    content_hub_read_version,
    content_hub_schema_plan,
    content_hub_show_url,
    content_hub_status,
    import_bilingual_metadata,
    import_content_snapshot,
    ingest_live_article,
    save_live_enrichment,
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


def test_git_checkout_keeps_migration_sql_lf_with_autocrlf_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    source_root = Path(__file__).resolve().parents[1]
    repository = tmp_path / "migration-eol-repo"
    repository.mkdir()

    def run_git(*args: str, cwd: Path = repository) -> bytes:
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True).stdout

    migration_paths = [
        "ai_actuarial/content_hub_migrations/0001_content_hub.sql",
        "ai_actuarial/content_hub_migrations/0002_bilingual_metadata.sql",
        "ai_actuarial/content_hub_migrations/0003_live_capture.sql",
        "ai_actuarial/source_stage_migrations/0001_lossless_source_stage.sql",
    ]
    source_blobs = {
        relative_path: (
            (source_root / relative_path).read_bytes()
            if relative_path.endswith(("0002_bilingual_metadata.sql", "0003_live_capture.sql"))
            else run_git("show", f"HEAD:{relative_path}", cwd=source_root)
        )
        for relative_path in migration_paths
    }
    assert all(b"\r\n" not in payload for payload in source_blobs.values())

    attributes = source_root / ".gitattributes"
    (repository / ".gitattributes").write_bytes(attributes.read_bytes())
    for relative_path, payload in source_blobs.items():
        destination = repository / Path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    run_git("init", "--quiet")
    run_git("config", "core.autocrlf", "true")
    run_git("config", "user.name", "Migration EOL regression")
    run_git("config", "user.email", "migration-eol@example.invalid")
    run_git("config", "commit.gpgsign", "false")
    run_git("add", "--", ".gitattributes", *migration_paths)
    run_git("commit", "--quiet", "-m", "fixture migration files")

    materialized = tmp_path / "migration-eol-checkout"
    materialized.mkdir()
    run_git(
        "checkout-index",
        "--force",
        f"--prefix={materialized.as_posix()}/",
        "--",
        *migration_paths,
    )
    for relative_path, source_payload in source_blobs.items():
        committed_payload = run_git("show", f"HEAD:{relative_path}")
        checked_out_payload = (materialized / Path(relative_path)).read_bytes()
        assert committed_payload == source_payload
        assert checked_out_payload == source_payload
        assert b"\r\n" not in checked_out_payload

    database_url, schema = _isolated_database_schema(tmp_path, "migration-eol-plan")
    monkeypatch.setattr(
        content_hub, "_MIGRATION_DIR", materialized / "ai_actuarial/content_hub_migrations"
    )
    monkeypatch.setattr(
        source_stage,
        "_MIGRATION_DIR",
        materialized / "ai_actuarial/source_stage_migrations",
    )
    content_plan = content_hub.content_hub_schema_plan(database_url, schema=schema)
    stage_plan = source_stage.source_stage_schema_plan(database_url, schema=schema)
    assert content_plan["pending"] == [
        {"version": 1, "file": migration_paths[0].split("/")[-1]},
        {"version": 2, "file": migration_paths[1].split("/")[-1]},
        {"version": 3, "file": migration_paths[2].split("/")[-1]},
    ]
    assert stage_plan["pending"] == [{"version": 1, "file": migration_paths[3].split("/")[-1]}]


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


def _digest_test_rows(rows: list[tuple]) -> str:
    serialized = sorted(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) for row in rows
    )
    return hashlib.sha256("\n".join(serialized).encode("utf-8")).hexdigest()


def _content_hub_state(database_url: str, schema: str) -> dict[str, dict[str, int | str]]:
    tables = (
        "schema_migrations",
        "source_snapshots",
        "source_table_counts",
        "content_blobs",
        "content_versions",
        "source_file_observations",
        "source_record_map",
        "text_variants",
        "legacy_index_artifacts",
        "bilingual_metadata",
        "article_enrichment_annotations",
        "excluded_urls",
    )
    connection = psycopg2.connect(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            state = {}
            for table in tables:
                cursor.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))
                rows = cursor.fetchall()
                state[table] = {"count": len(rows), "digest": _digest_test_rows(rows)}
            return state
    finally:
        connection.close()


def _source_stage_state(database_url: str, schema: str) -> dict:
    connection = psycopg2.connect(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute(
                "SELECT version, filename, checksum FROM schema_migrations ORDER BY version"
            )
            migrations = cursor.fetchall()
            cursor.execute(
                "SELECT source_name, source_sha256, schema_json, table_counts_json, "
                "table_digests_json, format_version FROM snapshot ORDER BY source_name"
            )
            snapshots = cursor.fetchall()
            cursor.execute(
                "SELECT table_name, row_number, row_json FROM table_rows "
                "ORDER BY table_name, row_number"
            )
            rows = cursor.fetchall()
        if len(snapshots) == 1:
            stored_counts = json.loads(snapshots[0][3])
            stored_digests = json.loads(snapshots[0][4])
        else:
            stored_counts = {}
            stored_digests = {}
        row_payloads: dict[str, list[bytes]] = {table: [] for table in stored_counts}
        for table, _row_number, payload in rows:
            row_payloads[str(table)].append(str(payload).encode("utf-8") + b"\n")
        actual_counts = {table: len(payloads) for table, payloads in row_payloads.items()}
        actual_digests = {
            table: hashlib.sha256(b"".join(payloads)).hexdigest()
            for table, payloads in row_payloads.items()
        }
        return {
            "migration_rows": migrations,
            "snapshots": snapshots,
            "row_count": len(rows),
            "rows_digest": _digest_test_rows(rows),
            "stored_counts": stored_counts,
            "stored_digests": stored_digests,
            "actual_counts": actual_counts,
            "actual_digests": actual_digests,
        }
    finally:
        connection.close()


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
    assert apply_content_hub_schema(hub_url, schema=schema)["version"] == 3
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
    assert status["bilingual_metadata_count"] == 0
    assert status["bilingual_metadata_by_language"] == {"zh": 0, "en": 0}

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


def test_live_capture_migration_preserves_immutable_v16_and_existing_operational_rows(
    tmp_path: Path, monkeypatch
) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "live-migration")
    repository_migrations = Path(content_hub.__file__).with_name("content_hub_migrations")
    legacy_migrations = tmp_path / "legacy-migrations"
    legacy_migrations.mkdir()
    for name in ("0001_content_hub.sql", "0002_bilingual_metadata.sql"):
        shutil.copy2(repository_migrations / name, legacy_migrations / name)
    monkeypatch.setattr(content_hub, "_MIGRATION_DIR", legacy_migrations)
    assert apply_content_hub_schema(hub_url, schema=schema)["version"] == 2

    url = "https://example.test/old-excluded-tender"
    digest = hashlib.sha256(url.encode()).hexdigest()
    migration = (repository_migrations / "0003_live_capture.sql").read_text(encoding="utf-8")
    annotation_ddl = re.search(
        r"CREATE TABLE IF NOT EXISTS article_enrichment_annotations\s*\(.*?\);",
        migration,
        flags=re.DOTALL,
    )
    exclusion_ddl = re.search(
        r"CREATE TABLE IF NOT EXISTS excluded_urls\s*\(.*?\);",
        migration,
        flags=re.DOTALL,
    )
    assert annotation_ddl and exclusion_ddl
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(annotation_ddl.group(0))
            cursor.execute(exclusion_ddl.group(0))
            cursor.execute(
                "INSERT INTO source_snapshots (source_name, snapshot_sha256, snapshot_bytes, "
                "sqlite_user_version, manifest_sha256) VALUES (%s, %s, 1, 16, %s) RETURNING source_snapshot_id",
                ("old-v16-source", "a" * 64, "b" * 64),
            )
            snapshot_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO source_table_counts (source_snapshot_id, table_name, row_count) "
                "VALUES (%s, 'files', 1)",
                (snapshot_id,),
            )
            cursor.execute(
                "INSERT INTO content_versions (url_value_json, url_identity_sha256, raw_sha256, "
                "identity_key, blob_sha256) VALUES (%s, %s, NULL, %s, NULL) RETURNING content_version_id",
                (json.dumps("https://example.test/annotated-legacy"), digest, "c" * 64),
            )
            old_version_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO article_enrichment_annotations (content_version_id, source_text_variant_id, "
                "source_markdown_sha256, source_primary_category, source_signature, categories_json, "
                "date_facts_json, date_review_status, date_review_unresolved_json, result_sha256, recipe, run_id) "
                "VALUES (%s, 77, %s, 'AI', %s, %s::jsonb, '{}'::jsonb, 'complete', '[]'::jsonb, %s, 'legacy', 'legacy-run')",
                (
                    old_version_id,
                    "d" * 64,
                    "e" * 64,
                    json.dumps([{"key": "AI", "evidence": ["old evidence"]}]),
                    "f" * 64,
                ),
            )
            cursor.execute(
                "INSERT INTO excluded_urls (url_identity_sha256, url_value_json, reason) "
                "VALUES (%s, %s, 'tender')",
                (digest, json.dumps(url)),
            )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(content_hub, "_MIGRATION_DIR", repository_migrations)
    assert apply_content_hub_schema(hub_url, schema=schema)["version"] == 3
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_name, sqlite_user_version, source_kind FROM source_snapshots"
            )
            assert cursor.fetchall() == [("old-v16-source", 16, "sqlite_v16")]
            cursor.execute("SELECT COUNT(*) FROM source_table_counts")
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT content_version_id, categories_json, recipe, run_id "
                "FROM article_enrichment_annotations"
            )
            assert cursor.fetchall() == [
                (
                    old_version_id,
                    [{"key": "AI", "evidence": ["old evidence"]}],
                    "legacy",
                    "legacy-run",
                )
            ]
            cursor.execute("SELECT url_identity_sha256, reason FROM excluded_urls")
            assert cursor.fetchall() == [(digest, "tender")]
            with pytest.raises(psycopg2.Error, match="content hub source snapshots are immutable"):
                cursor.execute("UPDATE source_snapshots SET source_kind = 'live_capture'")
            connection.rollback()
    finally:
        connection.close()


def test_live_capture_lists_only_ai_primary_and_preserves_secondary_categories(
    tmp_path: Path,
) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "live-capture")
    apply_content_hub_schema(hub_url, schema=schema)
    url = "https://research.example.test/ai-pricing.pdf"
    raw = b"original PDF bytes"
    markdown = "Pricing markets apply AI analysis. Published September 2026."
    args = {
        "canonical_url": url,
        "source_site": "iaa",
        "source_page_url": "https://research.example.test/research",
        "title": "Pricing and AI",
        "raw_bytes": raw,
        "markdown": markdown,
        "content_type": "application/pdf",
        "data_root": tmp_path / "live-data",
        "database_url": hub_url,
        "schema": schema,
        "metadata": {"observed_at": "2026-10-25T12:00:00.123456+00:00"},
    }
    first = ingest_live_article(**args)
    repeated = ingest_live_article(**args)
    assert first["already_imported"] is False
    assert repeated["already_imported"] is True
    assert repeated["content_version_id"] == first["content_version_id"]
    assert repeated["markdown_text_variant_id"] == first["markdown_text_variant_id"]

    categories = [
        {"key": "AI", "evidence": ["AI analysis"]},
        {"key": "Pricing", "evidence": ["Pricing markets"]},
        {"key": "Product Development & Profitability", "evidence": ["Pricing markets"]},
        {"key": "Other", "evidence": ["AI analysis"]},
    ]
    package = {
        "title": "Pricing and AI",
        "summary": "Pricing markets and AI analysis.",
        "category": "AI",
        "keywords": ["pricing", "AI"],
    }
    date_facts = {
        "publication_date": {
            "value": "2026-09",
            "precision": "month",
            "semantic": "publication",
            "evidence": "September 2026",
            "location": "cover",
        },
        "revision_date": None,
        "document_version_date": None,
    }
    with pytest.raises(ContentHubError, match="one to three exact quotes"):
        save_live_enrichment(
            content_version_id=first["content_version_id"],
            markdown_text_variant_id=first["markdown_text_variant_id"],
            markdown_sha256=first["markdown_sha256"],
            primary_category="Pricing",
            bilingual_metadata={"zh": package, "en": package},
            categories=[categories[0], {"key": "Pricing", "evidence": []}],
            date_facts=date_facts,
            date_review_status="complete",
            date_review_reason=None,
            date_review_unresolved=[],
            recipe="test-fixture",
            run_id="test-empty-category-evidence",
            database_url=hub_url,
            schema=schema,
        )
    with pytest.raises(ContentHubError, match="one to three exact quotes"):
        save_live_enrichment(
            content_version_id=first["content_version_id"],
            markdown_text_variant_id=first["markdown_text_variant_id"],
            markdown_sha256=first["markdown_sha256"],
            primary_category="AI",
            bilingual_metadata={"zh": package, "en": package},
            categories=[{"key": "AI", "evidence": []}, *categories[1:]],
            date_facts=date_facts,
            date_review_status="complete",
            date_review_reason=None,
            date_review_unresolved=[],
            recipe="test-fixture",
            run_id="test-empty-primary-evidence",
            database_url=hub_url,
            schema=schema,
        )
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM article_enrichment_annotations "
                "WHERE content_version_id = %s",
                (first["content_version_id"],),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        connection.close()

    saved = save_live_enrichment(
        content_version_id=first["content_version_id"],
        markdown_text_variant_id=first["markdown_text_variant_id"],
        markdown_sha256=first["markdown_sha256"],
        primary_category="AI",
        bilingual_metadata={"zh": package, "en": package},
        categories=categories,
        date_facts=date_facts,
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="test-fixture",
        run_id="test-live-capture",
        database_url=hub_url,
        schema=schema,
    )
    assert saved["success"] is True
    legacy_categories = [{**categories[0], "evidence": []}, *categories[1:]]
    legacy_annotation = {
        "categories": legacy_categories,
        "date_facts": date_facts,
        "date_review_status": "complete",
        "date_review_reason": None,
        "date_review_unresolved": [],
    }
    legacy_result_sha = hashlib.sha256(
        content_hub._canonical_json(legacy_annotation).encode("utf-8")
    ).hexdigest()
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE article_enrichment_annotations "
                "SET categories_json = %s::jsonb, result_sha256 = %s "
                "WHERE content_version_id = %s",
                (json.dumps(legacy_categories), legacy_result_sha, first["content_version_id"]),
            )
        connection.commit()
    finally:
        connection.close()
    categories = legacy_categories
    shown = content_hub_read_version(url, first["raw_sha256"], hub_url, schema=schema)
    assert shown and shown["annotation"]["categories"] == categories
    assert shown["annotation"]["date_facts"]["publication_date"]["precision"] == "month"
    assert shown["markdown_sha256"] == first["markdown_sha256"]
    assert shown["hub_markdown_sha256"] == first["markdown_sha256"]
    assert shown["hub_markdown_sha256_kind"] == "raw_utf8"
    assert content_hub_ai_url_versions([url], database_url=hub_url, schema=schema) == {
        url: [first["content_version_id"]]
    }
    ai_page = content_hub_list_ai_versions(
        after_version_id=0, limit=10, database_url=hub_url, schema=schema
    )
    assert ai_page["eligible_ai_count"] == 1
    assert ai_page["versions"][0]["content_version_id"] == first["content_version_id"]
    assert ai_page["versions"][0]["source_site"] == "iaa"
    assert ai_page["versions"][0]["hub_markdown_sha256_kind"] == "raw_utf8"
    assert ai_page["versions"][0]["categories"] == categories
    assert saved["is_ai_candidate"] is True

    secondary_url = "https://research.example.test/pricing-secondary-ai.pdf"
    secondary_markdown = "Pricing markets use AI analysis. Published September 2026."
    secondary_args = {
        **args,
        "canonical_url": secondary_url,
        "raw_bytes": b"secondary AI PDF bytes",
        "markdown": secondary_markdown,
    }
    secondary = ingest_live_article(**secondary_args)
    secondary_categories = [
        {"key": "Pricing", "evidence": ["Pricing markets"]},
        {"key": "AI", "evidence": ["AI analysis"]},
    ]
    secondary_package = {**package, "category": "Pricing"}
    secondary_saved = save_live_enrichment(
        content_version_id=secondary["content_version_id"],
        markdown_text_variant_id=secondary["markdown_text_variant_id"],
        markdown_sha256=secondary["markdown_sha256"],
        primary_category="Pricing",
        bilingual_metadata={"zh": secondary_package, "en": secondary_package},
        categories=secondary_categories,
        date_facts={
            "publication_date": None,
            "revision_date": None,
            "document_version_date": None,
        },
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="test-fixture",
        run_id="test-secondary-ai",
        database_url=hub_url,
        schema=schema,
    )
    assert secondary_saved["is_ai_candidate"] is False
    assert content_hub_ai_url_versions([secondary_url], database_url=hub_url, schema=schema) == {
        secondary_url: []
    }
    primary_page = content_hub_list_ai_versions(
        after_version_id=0, limit=10, database_url=hub_url, schema=schema
    )
    assert primary_page["eligible_ai_count"] == 1
    assert [row["content_version_id"] for row in primary_page["versions"]] == [
        first["content_version_id"]
    ]

    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE source_record_map SET source_metadata_json = '{}' "
                "WHERE content_version_id = %s",
                (first["content_version_id"],),
            )
        connection.commit()
    finally:
        connection.close()
    unknown_source_page = content_hub_list_ai_versions(
        after_version_id=0, limit=10, database_url=hub_url, schema=schema
    )
    assert unknown_source_page["versions"][0]["source_site"] is None

    changed = ingest_live_article(
        **{**args, "raw_bytes": b"changed PDF bytes", "markdown": markdown + " Revised."}
    )
    assert changed["content_version_id"] != first["content_version_id"]
    status = content_hub_status(hub_url, schema=schema)
    assert status["source_kind_counts"] == {"sqlite_v16": 0, "live_capture": 3}
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT sqlite_user_version, source_kind FROM source_snapshots ORDER BY source_snapshot_id"
            )
            assert cursor.fetchall() == [
                (None, "live_capture"),
                (None, "live_capture"),
                (None, "live_capture"),
            ]
    finally:
        connection.close()


def test_legacy_json_payload_binding_reads_and_lists_with_raw_digest(tmp_path: Path) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "legacy-markdown-binding")
    apply_content_hub_schema(hub_url, schema=schema)
    artifact_root = tmp_path / "legacy-artifacts"
    source_path = tmp_path / "legacy-binding-v16.db"
    source_payload = b"legacy original PDF bytes"
    _, counts = _create_v16_source(source_path, source_payload, source_label="binding")
    manifest_path, _ = _write_manifest(
        source_path, "binding", artifact_root, source_payload, counts
    )
    import_content_snapshot(
        source_path,
        manifest_path,
        artifact_root,
        tmp_path / "legacy-data",
        hub_url,
        schema=schema,
        expected_source_name="binding",
    )
    url = "https://content.example.test/primary?version=1"
    shown = content_hub_show_url(url, hub_url, schema=schema)
    version_id = shown["versions"][0]["content_version_id"]
    raw_sha = shown["versions"][0]["raw_sha256"]
    markdown_variant = next(
        item for item in shown["text_variants"] if item["field_name"] == "markdown_content"
    )
    markdown = markdown_variant["value"]
    assert isinstance(markdown, str)
    raw_markdown_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    legacy_binding_sha = hashlib.sha256(
        content_hub._json_text(markdown).encode("utf-8")
    ).hexdigest()
    assert legacy_binding_sha == markdown_variant["payload_sha256"]
    assert raw_markdown_sha != legacy_binding_sha

    metadata_path = tmp_path / "legacy-binding-metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "format": "ai_actuarial.content_hub.generated_metadata",
                "version": 1,
                "items": [
                    {
                        "content_version_id": version_id,
                        "language_code": language,
                        "markdown_text_variant_id": markdown_variant["text_variant_id"],
                        "markdown_sha256": legacy_binding_sha,
                        "title": f"AI research {language}",
                        "summary": f"AI actuarial research {language} summary",
                        "category": "Pricing",
                        "keywords": ["actuarial", "AI"],
                        "recipe": "legacy-metadata-fixture",
                        "author": "test",
                    }
                    for language in ("zh", "en")
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    import_bilingual_metadata(metadata_path, hub_url, schema=schema)

    signature = "a" * 64
    result_sha = "b" * 64
    categories = [
        {"key": "Pricing", "evidence": ["Pricing"]},
        {"key": "AI", "evidence": ["AI research"]},
    ]
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute(
                "INSERT INTO article_enrichment_annotations "
                "(content_version_id, source_text_variant_id, source_markdown_sha256, "
                "source_primary_category, source_signature, categories_json, date_facts_json, "
                "date_review_status, date_review_unresolved_json, result_sha256, recipe, run_id) "
                "VALUES (%s, %s, %s, 'Pricing', %s, %s::jsonb, '{}'::jsonb, 'complete', "
                "'[]'::jsonb, %s, 'legacy-fixture', 'legacy-binding-run')",
                (
                    version_id,
                    markdown_variant["text_variant_id"],
                    legacy_binding_sha,
                    signature,
                    json.dumps(categories),
                    result_sha,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    direct = content_hub_read_version(url, raw_sha, hub_url, schema=schema)
    assert direct["markdown_sha256"] == raw_markdown_sha
    assert direct["hub_markdown_sha256"] == legacy_binding_sha
    assert direct["hub_markdown_sha256_kind"] == "json_payload_utf8"
    assert set(direct["bilingual_metadata"]) == {"zh", "en"}
    assert direct["annotation"]["source_primary_category"] == "Pricing"
    page = content_hub_list_ai_versions(
        after_version_id=0, limit=10, database_url=hub_url, schema=schema
    )
    assert page["versions"] == []
    assert page["eligible_ai_count"] == 0
    assert content_hub_ai_url_versions([url], database_url=hub_url, schema=schema) == {url: []}

    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute(
                "UPDATE article_enrichment_annotations SET source_markdown_sha256 = %s "
                "WHERE content_version_id = %s",
                ("0" * 64, version_id),
            )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ContentHubError, match="binding is invalid"):
        content_hub_read_version(url, raw_sha, hub_url, schema=schema)
    malformed_page = content_hub_list_ai_versions(
        after_version_id=0, limit=10, database_url=hub_url, schema=schema
    )
    assert malformed_page["versions"] == []


@pytest.mark.parametrize(
    "binding_kind",
    [
        "json_payload_utf8",
        "raw_utf8",
        "mismatch",
        "different_bilingual_variant",
        "different_language_binding",
    ],
)
def test_catalog_projection_keeps_legacy_or_live_binding_exact(
    monkeypatch, binding_kind: str
) -> None:
    url = "https://projection.example.test/article.pdf"
    markdown = "Source Markdown for projection."
    payload_json = content_hub._json_text(markdown)
    payload_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    raw_markdown_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    binding_sha = {
        "json_payload_utf8": payload_sha,
        "raw_utf8": raw_markdown_sha,
        "mismatch": "0" * 64,
        "different_bilingual_variant": payload_sha,
        "different_language_binding": payload_sha,
    }[binding_kind]
    rows = [
        (
            71,
            json.dumps(url),
            hashlib.sha256(url.encode("utf-8")).hexdigest(),
            "a" * 64,
            language,
            82 if binding_kind == "different_bilingual_variant" and language == "en" else 81,
            (
                raw_markdown_sha
                if binding_kind == "different_language_binding" and language == "en"
                else binding_sha
            ),
            f"title {language}",
            f"summary {language}",
            "Other",
            [f"keyword {language}"],
            71,
            "markdown_content",
            payload_json,
            False,
            payload_sha,
        )
        for language in ("zh", "en")
    ]
    target_identity = ("target", "127.0.0.1", 5432, "public")
    hub_identity = ("hub", "127.0.0.1", 5432, "content_hub")

    class FakeTargetConnection:
        def __init__(self, _database, *, read_only=False):
            assert read_only

        def execute(self, query, _parameters=None):
            if "current_database()" in query:
                value = target_identity
            else:
                value = (3,)
            return type("Result", (), {"fetchone": lambda _self: value})()

        def table_exists(self, _table):
            return True

        def table_columns(self, _table):
            return {"file_url", "sha256", "category"}

        def close(self):
            pass

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query):
            self.query = query

        def fetchone(self):
            return hub_identity

        def fetchall(self):
            return rows

    class FakeHubConnection:
        def set_session(self, **_kwargs):
            pass

        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    merged = []

    class FakeStorage:
        def __init__(self, _database, *, data_root):
            assert data_root

        def merge_hub_bilingual_metadata(self, **kwargs):
            merged.append(kwargs)
            return ("updated", 1)

        def close(self):
            pass

    monkeypatch.setattr(postgres, "PostgresConnection", FakeTargetConnection)
    monkeypatch.setattr(content_hub, "_connect", lambda _url: FakeHubConnection())
    monkeypatch.setattr(content_hub, "_require_current_schema", lambda *_args: None)
    monkeypatch.setattr("ai_actuarial.storage.Storage", FakeStorage)

    result = content_hub.sync_content_hub_catalog_metadata(
        "postgresql://target.invalid/app", "postgresql://hub.invalid/content_hub"
    )
    if binding_kind not in {"json_payload_utf8", "raw_utf8"}:
        assert result["conflict_count"] == 1
        assert merged == []
        return
    assert result["updated_count"] == 1
    assert merged[0]["metadata_by_language"]["zh"]["hub_binding"] == {
        "content_version_id": 71,
        "markdown_text_variant_id": 81,
        "markdown_sha256": binding_sha,
    }


def test_raw_only_live_capture_can_be_completed_on_same_content_version(tmp_path: Path) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "live-raw-only")
    apply_content_hub_schema(hub_url, schema=schema)
    url = "https://research.example.test/legacy-office.doc"
    raw = bytes.fromhex("d0cf11e0a1b11ae1") + b"legacy office bytes"
    args = {
        "canonical_url": url,
        "source_site": "iaa",
        "source_page_url": "https://research.example.test/papers",
        "title": "Legacy source document",
        "raw_bytes": raw,
        "content_type": "application/msword",
        "data_root": tmp_path / "live-data",
        "database_url": hub_url,
        "schema": schema,
    }
    pending = ingest_live_article(**args, markdown=None)
    repeated_pending = ingest_live_article(**args, markdown=None)
    assert pending["already_versioned"] is False
    assert pending["markdown_text_variant_id"] is None
    assert repeated_pending["already_imported"] is True
    assert repeated_pending["content_version_id"] == pending["content_version_id"]
    assert repeated_pending["markdown_text_variant_id"] is None
    raw_readback = content_hub_read_version(url, pending["raw_sha256"], hub_url, schema=schema)
    assert raw_readback["content_version_id"] == pending["content_version_id"]
    assert raw_readback["blob_available"] is True
    assert raw_readback["markdown"] is None
    assert raw_readback["markdown_text_variant_id"] is None
    assert raw_readback["markdown_extraction_status"] == "extraction_gap"
    assert raw_readback["annotation"] is None

    markdown = "The same original source is now parseable with a supported converter."
    completed = ingest_live_article(**args, markdown=markdown)
    assert completed["already_versioned"] is True
    assert completed["content_version_id"] == pending["content_version_id"]
    assert completed["markdown_text_variant_id"] is not None
    completed_again = ingest_live_article(**args, markdown=markdown)
    assert completed_again["already_imported"] is True
    assert completed_again["content_version_id"] == pending["content_version_id"]
    readback = content_hub_read_version(url, pending["raw_sha256"], hub_url, schema=schema)
    assert readback["content_version_id"] == pending["content_version_id"]
    assert readback["markdown"] == markdown
    assert readback["markdown_extraction_status"] == "available"
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.content_versions").format(sql.Identifier(schema))
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.source_snapshots").format(sql.Identifier(schema))
            )
            assert cursor.fetchone()[0] == 2
    finally:
        connection.close()


def test_live_capture_refuses_existing_recruitment_or_tender_exclusion(tmp_path: Path) -> None:
    hub_url, schema = _isolated_database_schema(tmp_path, "live-exclusion")
    apply_content_hub_schema(hub_url, schema=schema)
    url = "https://research.example.test/known-tender.pdf"
    identity = hashlib.sha256(url.encode("utf-8")).hexdigest()
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {}.excluded_urls (url_identity_sha256, url_value_json, reason) "
                    "VALUES (%s, %s, 'tender')"
                ).format(sql.Identifier(schema)),
                (identity, json.dumps(url)),
            )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ContentHubError, match="Hub excludes this URL as tender"):
        ingest_live_article(
            canonical_url=url,
            source_site="cas",
            source_page_url="https://research.example.test/",
            title="Tender",
            raw_bytes=b"unwanted source",
            markdown="Tender notice.",
            content_type="application/pdf",
            data_root=tmp_path / "live-data",
            database_url=hub_url,
            schema=schema,
        )
    assert content_hub.content_hub_url_exclusion(url, hub_url, schema=schema) == {
        "url": url,
        "reason": "tender",
    }


def test_bilingual_metadata_validator_requires_one_category_per_content_version(
    tmp_path: Path,
) -> None:
    item = {
        "content_version_id": 1,
        "markdown_text_variant_id": 2,
        "markdown_sha256": "a" * 64,
        "title": "Title",
        "summary": "Summary",
        "category": "AI",
        "keywords": ["keyword"],
        "recipe": "fixture",
        "author": "fixture",
    }
    metadata_path = tmp_path / "split-category.json"
    metadata_path.write_text(
        json.dumps(
            {
                "format": "ai_actuarial.content_hub.generated_metadata",
                "version": 1,
                "items": [
                    {**item, "language_code": "zh"},
                    {**item, "language_code": "en", "category": "Data & Analytics"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContentHubError, match="share a canonical category"):
        content_hub._validate_bilingual_metadata_input(metadata_path)


def test_bilingual_metadata_import_is_version_bound_fill_only_and_idempotent(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from ai_actuarial.cli import main

    hub_url, schema = _isolated_database_schema(tmp_path, "bilingual-metadata")
    apply_content_hub_schema(hub_url, schema=schema)
    artifact_root = tmp_path / "artifacts"
    source_path = tmp_path / "source-v16.db"
    payload = b"source markdown backing bytes"
    _, counts = _create_v16_source(source_path, payload, source_label="bilingual")
    manifest_path, _ = _write_manifest(source_path, "bilingual", artifact_root, payload, counts)
    import_content_snapshot(
        source_path,
        manifest_path,
        artifact_root,
        tmp_path / "data",
        hub_url,
        schema=schema,
        expected_source_name="bilingual",
    )
    shown = content_hub_show_url(
        "https://content.example.test/primary?version=1", hub_url, schema=schema
    )
    assert len(shown["versions"]) == 1
    version_id = shown["versions"][0]["content_version_id"]
    markdown = next(
        variant for variant in shown["text_variants"] if variant["field_name"] == "markdown_content"
    )
    raw_before = _content_hub_state(hub_url, schema)
    source_table_names = set(raw_before) - {"bilingual_metadata"}

    def metadata_item(language: str) -> dict:
        return {
            "content_version_id": version_id,
            "language_code": language,
            "markdown_text_variant_id": markdown["text_variant_id"],
            "markdown_sha256": markdown["payload_sha256"],
            "title": "中英标题" if language == "zh" else "English title",
            "summary": "中文摘要" if language == "zh" else "English summary",
            "category": "Life",
            "keywords": ["寿险", "精算"] if language == "zh" else ["life", "actuarial"],
            "recipe": "offline-summary-v1",
            "author": "controller",
        }

    metadata_path = tmp_path / "generated-metadata.json"

    def write_metadata(items: list[dict]) -> None:
        metadata_path.write_text(
            json.dumps(
                {
                    "format": "ai_actuarial.content_hub.generated_metadata",
                    "version": 1,
                    "items": items,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    write_metadata([metadata_item("zh"), metadata_item("en")])
    monkeypatch.setenv("CONFIG_PATH", os.environ.get("CONFIG_PATH", ""))
    monkeypatch.setenv("CONTENT_HUB_DATABASE_URL", hub_url)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ai-actuarial",
            "content-hub",
            "metadata",
            "import",
            "--input",
            str(metadata_path),
            "--schema",
            schema,
            "--json",
        ],
    )
    assert main() == 0
    first = json.loads(capsys.readouterr().out)
    assert first == {
        "success": True,
        "schema": schema,
        "item_count": 2,
        "inserted_count": 2,
        "filled_count": 0,
        "unchanged_count": 0,
    }
    assert main() == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["inserted_count"] == 0
    assert repeated["unchanged_count"] == 2

    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE bilingual_metadata SET summary = NULL, keywords_json = NULL "
                "WHERE content_version_id = %s",
                (version_id,),
            )
        connection.commit()
    finally:
        connection.close()

    partial_items = []
    for language in ("zh", "en"):
        item = metadata_item(language)
        item.update(
            {
                "title": "replacement title",
                "summary": f"filled {language} summary",
                "category": "Life",
                "keywords": [f"filled-{language}"],
                "recipe": "offline-summary-v2",
                "author": "second-controller",
            }
        )
        partial_items.append(item)
    write_metadata(partial_items)
    filled = import_bilingual_metadata(metadata_path, hub_url, schema=schema)
    assert filled["filled_count"] == 2

    after_show = content_hub_show_url(
        "https://content.example.test/primary?version=1", hub_url, schema=schema
    )
    by_language = after_show["versions"][0]["bilingual_metadata"]
    assert set(by_language) == {"zh", "en"}
    for language in ("zh", "en"):
        metadata = by_language[language]
        original = metadata_item(language)
        assert metadata["title"] == original["title"]
        assert metadata["category"] == "Life"
        assert metadata["summary"] == f"filled {language} summary"
        assert metadata["keywords"] == [f"filled-{language}"]
        assert metadata["provenance"][-1] == {
            "recipe": "offline-summary-v2",
            "author": "second-controller",
            "fields": ["summary", "keywords"],
        }

    write_metadata([metadata_item("zh"), metadata_item("en")])
    preserved = import_bilingual_metadata(metadata_path, hub_url, schema=schema)
    assert preserved["unchanged_count"] == 2
    after_state = _content_hub_state(hub_url, schema)
    assert {name: after_state[name] for name in source_table_names} == {
        name: raw_before[name] for name in source_table_names
    }
    status = content_hub_status(hub_url, schema=schema)
    assert status["bilingual_metadata_by_language"] == {"zh": 1, "en": 1}

    invalid_cases = []
    wrong_version = metadata_item("zh")
    wrong_version["content_version_id"] += 10000
    invalid_cases.append([wrong_version])
    mismatched_version = metadata_item("zh")
    alias = content_hub_show_url(
        "https://content.example.test/alias?version=1", hub_url, schema=schema
    )
    mismatched_version["content_version_id"] = alias["versions"][0]["content_version_id"]
    invalid_cases.append([mismatched_version])
    wrong_variant = metadata_item("zh")
    wrong_variant["markdown_text_variant_id"] += 1
    invalid_cases.append([wrong_variant])
    wrong_digest = metadata_item("zh")
    wrong_digest["markdown_sha256"] = "0" * 64
    invalid_cases.append([wrong_digest])
    alias_markdown = next(
        variant for variant in alias["text_variants"] if variant["field_name"] == "markdown_content"
    )
    valid_alias_record = metadata_item("en")
    valid_alias_record.update(
        {
            "content_version_id": alias["versions"][0]["content_version_id"],
            "markdown_text_variant_id": alias_markdown["text_variant_id"],
            "markdown_sha256": alias_markdown["payload_sha256"],
        }
    )
    invalid_cases.append([valid_alias_record, wrong_digest])
    wrong_language = metadata_item("zh")
    wrong_language["language_code"] = "fr"
    invalid_cases.append([wrong_language])
    empty_title = metadata_item("zh")
    empty_title["title"] = "  "
    invalid_cases.append([empty_title])
    empty_keywords = metadata_item("zh")
    empty_keywords["keywords"] = []
    invalid_cases.append([empty_keywords])
    unknown_category = metadata_item("zh")
    unknown_category["category"] = "Unknown category"
    invalid_cases.append([unknown_category])
    split_categories = [metadata_item("zh"), metadata_item("en")]
    split_categories[0]["category"] = "AI"
    split_categories[1]["category"] = "Data & Analytics"
    invalid_cases.append(split_categories)
    conflicting_duplicate = metadata_item("zh")
    invalid_cases.append([metadata_item("zh"), {**conflicting_duplicate, "title": "conflict"}])
    for invalid in invalid_cases:
        write_metadata(invalid)
        before = _content_hub_state(hub_url, schema)
        with pytest.raises(ContentHubError):
            import_bilingual_metadata(metadata_path, hub_url, schema=schema)
        assert _content_hub_state(hub_url, schema) == before

    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM bilingual_metadata WHERE content_version_id = %s "
                "AND language_code = 'en'",
                (version_id,),
            )
        connection.commit()
    finally:
        connection.close()

    before_sibling_conflict = _content_hub_state(hub_url, schema)
    mismatched_sibling = metadata_item("en")
    mismatched_sibling["category"] = "AI"
    write_metadata([mismatched_sibling])
    with pytest.raises(ContentHubError, match="conflicts with an existing language package"):
        import_bilingual_metadata(metadata_path, hub_url, schema=schema)
    assert _content_hub_state(hub_url, schema) == before_sibling_conflict

    matching_sibling = metadata_item("en")
    write_metadata([matching_sibling])
    imported_sibling = import_bilingual_metadata(metadata_path, hub_url, schema=schema)
    assert imported_sibling["inserted_count"] == 1
    assert imported_sibling["unchanged_count"] == 0
    repeated_sibling = import_bilingual_metadata(metadata_path, hub_url, schema=schema)
    assert repeated_sibling["inserted_count"] == 0
    assert repeated_sibling["unchanged_count"] == 1

    first_language_only = metadata_item("zh")
    first_language_only.update(
        {
            "content_version_id": alias["versions"][0]["content_version_id"],
            "markdown_text_variant_id": alias_markdown["text_variant_id"],
            "markdown_sha256": alias_markdown["payload_sha256"],
        }
    )
    write_metadata([first_language_only])
    first_language_result = import_bilingual_metadata(metadata_path, hub_url, schema=schema)
    assert first_language_result["inserted_count"] == 1
    assert first_language_result["unchanged_count"] == 0

    monkeypatch.setattr(
        sys, "argv", ["ai-actuarial", "content-hub", "metadata", "import", "--help"]
    )
    with pytest.raises(SystemExit) as help_exit:
        main()
    assert help_exit.value.code == 0
    assert "--input" in capsys.readouterr().out


def test_import_rejects_corrupt_present_cas_without_mutating_hub_or_source_stage(
    tmp_path: Path,
) -> None:
    hub_url, hub_schema = _isolated_database_schema(tmp_path, "cas-hub")
    stage_url, stage_schema = _isolated_database_schema(tmp_path, "cas-stage")
    apply_content_hub_schema(hub_url, schema=hub_schema)

    source_path = tmp_path / "cas-hash-mismatch-v16.db"
    payload = b"verified CAS payload"
    _, table_counts = _create_v16_source(source_path, payload, source_label="cas_hash_mismatch")
    artifact_root = tmp_path / "shared-cas-root"
    manifest_path, source_sha = _write_manifest(
        source_path, "cas_hash_mismatch", artifact_root, payload, table_counts
    )
    stage_result = stage_sqlite_v16(
        source_path,
        "cas_hash_mismatch",
        stage_url,
        hub_database_url=_other_database_name(stage_url, "cas_hash_hub_guard"),
        schema=stage_schema,
    )
    assert stage_result["state"] == "verified"

    hub_before = _content_hub_state(hub_url, hub_schema)
    stage_before = _source_stage_state(stage_url, stage_schema)
    assert all(
        state["count"] == (3 if table == "schema_migrations" else 0)
        for table, state in hub_before.items()
    )
    assert stage_before["actual_counts"] == stage_before["stored_counts"]
    assert stage_before["actual_digests"] == stage_before["stored_digests"]
    assert stage_before["snapshots"][0][1] == source_sha

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cas_path = artifact_root / Path(*manifest["files"][0]["cas_relpath"].split("/"))
    corrupt_payload = b"X" * len(payload)
    assert hashlib.sha256(corrupt_payload).hexdigest() != hashlib.sha256(payload).hexdigest()
    cas_path.write_bytes(corrupt_payload)

    with pytest.raises(
        ContentHubError, match="CAS artifact hash or size does not match its manifest"
    ):
        import_content_snapshot(
            source_path,
            manifest_path,
            artifact_root,
            tmp_path / "hub-data",
            hub_url,
            schema=hub_schema,
            expected_source_name="cas_hash_mismatch",
        )

    assert _content_hub_state(hub_url, hub_schema) == hub_before
    assert _source_stage_state(stage_url, stage_schema) == stage_before


def test_import_rolls_back_when_sqlite_source_changes_after_canonical_rows_are_written(
    tmp_path: Path, monkeypatch
) -> None:
    hub_url, hub_schema = _isolated_database_schema(tmp_path, "mutation-hub")
    stage_url, stage_schema = _isolated_database_schema(tmp_path, "mutation-stage")
    apply_content_hub_schema(hub_url, schema=hub_schema)

    source_path = tmp_path / "late-mutation-v16.db"
    payload = b"source bytes verified before mutation"
    _, table_counts = _create_v16_source(source_path, payload, source_label="late_mutation")
    artifact_root = tmp_path / "shared-mutation-root"
    manifest_path, source_sha = _write_manifest(
        source_path, "late_mutation", artifact_root, payload, table_counts
    )
    stage_result = stage_sqlite_v16(
        source_path,
        "late_mutation",
        stage_url,
        hub_database_url=_other_database_name(stage_url, "late_mutation_hub_guard"),
        schema=stage_schema,
    )
    assert stage_result["state"] == "verified"

    hub_before = _content_hub_state(hub_url, hub_schema)
    stage_before = _source_stage_state(stage_url, stage_schema)
    assert all(
        state["count"] == (3 if table == "schema_migrations" else 0)
        for table, state in hub_before.items()
    )
    assert stage_before["actual_counts"] == stage_before["stored_counts"]
    assert stage_before["actual_digests"] == stage_before["stored_digests"]
    assert stage_before["snapshots"][0][1] == source_sha

    source_hash_checks = 0
    canonical_rows_verified = False
    original_source_sha256 = content_hub._source_sha256
    original_verify_import_counts = content_hub._verify_import_counts

    def mark_canonical_rows_verified(*args, **kwargs):
        nonlocal canonical_rows_verified
        original_verify_import_counts(*args, **kwargs)
        canonical_rows_verified = True

    def mutate_source_before_final_hash(path: Path):
        nonlocal source_hash_checks
        source_hash_checks += 1
        if source_hash_checks == 2:
            assert canonical_rows_verified
            with sqlite3.connect(path) as mutator:
                mutator.execute(
                    "UPDATE files SET title = ? WHERE id = ?", ("late source mutation", 101)
                )
        return original_source_sha256(path)

    monkeypatch.setattr(content_hub, "_verify_import_counts", mark_canonical_rows_verified)
    monkeypatch.setattr(content_hub, "_source_sha256", mutate_source_before_final_hash)
    with pytest.raises(
        ContentHubError, match="SQLite source changed while the content hub import was running"
    ):
        import_content_snapshot(
            source_path,
            manifest_path,
            artifact_root,
            tmp_path / "hub-data",
            hub_url,
            schema=hub_schema,
            expected_source_name="late_mutation",
        )

    assert source_hash_checks == 2
    assert canonical_rows_verified
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() != source_sha
    assert _content_hub_state(hub_url, hub_schema) == hub_before
    assert _source_stage_state(stage_url, stage_schema) == stage_before


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

    # Track cli.main()'s direct CONFIG_PATH assignment for teardown.
    monkeypatch.setenv("CONFIG_PATH", os.environ.get("CONFIG_PATH", ""))
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
    # Track cli.main()'s direct CONFIG_PATH assignment for teardown.
    monkeypatch.setenv("CONFIG_PATH", os.environ.get("CONFIG_PATH", ""))
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

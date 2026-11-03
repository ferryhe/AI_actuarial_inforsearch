"""Plan or apply deterministic AICT name corrections to selected Content Hub text."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg2

from ai_actuarial import content_hub
from ai_actuarial.source_registry import normalize_aict_institution_text
from ai_actuarial.storage import Storage

_TEXT_FIELDS = ("title", "keywords", "keywords_json", "category", "summary", "markdown_content")
_CORRECTION_RECIPE = "aict-name-correction-v1"
_FIXED_TIMESTAMP = "2026-11-03T00:00:00+00:00"


def normalize_article_text(value: str) -> str:
    """Replace known former names in prose while preserving every URL token."""
    return normalize_aict_institution_text(value)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_article_text(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _connect_read_only(database_url: str, schema: str):
    schema = content_hub._validate_schema(schema)
    connection = psycopg2.connect(
        content_hub._database_url(database_url),
        options=f"-c search_path={schema},pg_catalog",
        connect_timeout=15,
    )
    connection.set_session(readonly=True)
    return connection


def _scan_historical_variants(connection: Any) -> tuple[Counter[str], set[int]]:
    """Use the same text normalizer for the full historical variant inventory."""
    counts: Counter[str] = Counter()
    version_ids: set[int] = set()
    with connection.cursor(name="aict_name_variant_scan") as cursor:
        cursor.execute(
            "SELECT content_version_id, field_name, payload_value_json "
            "FROM text_variants WHERE NOT payload_is_null ORDER BY text_variant_id"
        )
        while rows := cursor.fetchmany(500):
            for version_id, field_name, payload in rows:
                value = _json_value(payload)
                if _normalize_value(value) != value:
                    counts[str(field_name)] += 1
                    version_ids.add(int(version_id))
    return counts, version_ids


def _scan_historical_bilingual(connection: Any) -> tuple[Counter[str], set[int]]:
    """Find old names in bilingual rows bound to the current annotation Markdown."""
    counts: Counter[str] = Counter()
    version_ids: set[int] = set()
    with connection.cursor(name="aict_name_bilingual_scan") as cursor:
        cursor.execute(
            "SELECT b.content_version_id, b.language_code, b.title, b.summary, b.keywords_json "
            "FROM bilingual_metadata b JOIN article_enrichment_annotations a "
            "USING (content_version_id) "
            "WHERE b.markdown_text_variant_id=a.source_text_variant_id "
            "AND b.markdown_sha256=a.source_markdown_sha256 "
            "ORDER BY b.content_version_id, b.language_code"
        )
        while rows := cursor.fetchmany(500):
            for version_id, language, title, summary, keywords in rows:
                for field, raw_value in (
                    ("title", title),
                    ("summary", summary),
                    ("keywords", keywords),
                ):
                    value = _json_value(raw_value)
                    if _normalize_value(value) != value:
                        counts[f"{language}.{field}"] += 1
                        version_ids.add(int(version_id))
    return counts, version_ids


def _scan_current_source_sites(connection: Any) -> tuple[Counter[str], set[int]]:
    counts: Counter[str] = Counter()
    version_ids: set[int] = set()
    with connection.cursor(name="aict_name_source_site_scan") as cursor:
        cursor.execute(
            "SELECT DISTINCT ON (r.content_version_id, r.source_table) "
            "r.content_version_id, r.source_table, r.source_metadata_json "
            "FROM source_record_map r JOIN source_snapshots s USING (source_snapshot_id) "
            "WHERE r.source_table IN ('files', 'catalog_items') "
            "ORDER BY r.content_version_id, r.source_table, s.imported_at DESC, "
            "s.source_snapshot_id DESC, r.legacy_pk_json"
        )
        while rows := cursor.fetchmany(500):
            for version_id, source_table, metadata_json in rows:
                metadata = _json_value(metadata_json)
                source_site = metadata.get("source_site") if isinstance(metadata, dict) else None
                if isinstance(source_site, str) and _normalize_value(source_site) != source_site:
                    counts[str(source_table)] += 1
                    version_ids.add(int(version_id))
    return counts, version_ids


def _latest_source_metadata(
    cursor: Any, version_id: int, table: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    cursor.execute(
        "SELECT r.source_metadata_json, o.deleted_at_json, o.source_byte_size, "
        "o.availability, o.cas_relpath, o.verified_sha256 "
        "FROM source_record_map r JOIN source_snapshots s USING (source_snapshot_id) "
        "LEFT JOIN source_file_observations o ON o.source_snapshot_id=r.source_snapshot_id "
        "AND o.content_version_id=r.content_version_id "
        "WHERE r.content_version_id=%s AND r.source_table=%s "
        "ORDER BY s.imported_at DESC, s.source_snapshot_id DESC, r.legacy_pk_json LIMIT 1",
        (version_id, table),
    )
    row = cursor.fetchone()
    if row is None:
        return {}, {}
    return (
        _json_value(row[0]) or {},
        {
            "deleted_at": _json_value(row[1]),
            "source_byte_size": row[2],
            "availability": row[3],
            "cas_relpath": row[4],
            "verified_sha256": str(row[5]).strip() if row[5] else None,
        },
    )


def _read_current_source_metadata(
    database_url: str, schema: str, version_id: int, table: str
) -> dict[str, Any]:
    connection = _connect_read_only(database_url, schema)
    try:
        with connection.cursor() as cursor:
            metadata, _observation = _latest_source_metadata(cursor, version_id, table)
            return metadata
    finally:
        connection.close()


def _latest_text_fields(cursor: Any, version_id: int) -> dict[str, Any]:
    cursor.execute(
        "SELECT field_name, payload_value_json, payload_is_null FROM text_variants "
        "WHERE content_version_id=%s ORDER BY text_variant_id DESC",
        (version_id,),
    )
    values: dict[str, Any] = {}
    for field_name, payload, payload_is_null in cursor.fetchall():
        if field_name in _TEXT_FIELDS and field_name not in values:
            values[field_name] = None if payload_is_null else _json_value(payload)
    return values


def _selected_correction_plan(
    connection: Any, database_url: str, schema: str
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[dict[str, Any]]]:
    variant_counts, version_ids = _scan_historical_variants(connection)
    bilingual_counts, bilingual_version_ids = _scan_historical_bilingual(connection)
    version_ids.update(bilingual_version_ids)
    source_site_counts, source_site_version_ids = _scan_current_source_sites(connection)
    version_ids.update(source_site_version_ids)
    if not version_ids:
        return (
            dict(sorted(variant_counts.items())),
            dict(sorted(bilingual_counts.items())),
            dict(sorted(source_site_counts.items())),
            [],
        )
    planned = []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT content_version_id, url_value_json, raw_sha256 FROM content_versions "
            "WHERE content_version_id = ANY(%s) AND raw_sha256 IS NOT NULL "
            "ORDER BY content_version_id",
            (sorted(version_ids),),
        )
        identities = cursor.fetchall()
        for version_id, url_value, raw_sha256 in identities:
            url = _json_value(url_value)
            digest = str(raw_sha256).strip().lower()
            version = content_hub.content_hub_read_version(url, digest, database_url, schema=schema)
            if version is None:
                raise content_hub.ContentHubError("Matched Hub URL/raw-SHA version disappeared")
            fields = _latest_text_fields(cursor, int(version_id))
            selected_markdown = version.get("markdown")
            if selected_markdown is not None:
                fields["markdown_content"] = selected_markdown
            original_fields = dict(fields)
            corrected_fields = _normalize_value(fields)
            bilingual = version.get("bilingual_metadata") or {}
            corrected_bilingual = _normalize_value(bilingual)
            annotation = _normalize_value(version.get("annotation"))
            file_metadata, file_observation = _latest_source_metadata(
                cursor, int(version_id), "files"
            )
            catalog_metadata, _ = _latest_source_metadata(cursor, int(version_id), "catalog_items")
            source_site = file_metadata.get("source_site")
            corrected_source_site = _normalize_value(source_site)
            catalog_source_site = catalog_metadata.get("source_site")
            corrected_catalog_source_site = _normalize_value(catalog_source_site)
            if corrected_catalog_source_site != catalog_source_site:
                catalog_metadata = {
                    **catalog_metadata,
                    "source_site": corrected_catalog_source_site,
                }
            if (
                corrected_fields == fields
                and corrected_bilingual == bilingual
                and annotation == version.get("annotation")
                and corrected_source_site == source_site
                and corrected_catalog_source_site == catalog_source_site
            ):
                continue
            if annotation and set(corrected_bilingual) != {"zh", "en"}:
                raise content_hub.ContentHubError("Selected annotation lacks exact zh/en metadata")
            planned.append(
                {
                    "content_version_id": int(version_id),
                    "url": url,
                    "raw_sha256": digest,
                    "version": version,
                    "source_metadata": file_metadata,
                    "source_observation": file_observation,
                    "catalog_metadata": catalog_metadata,
                    "original_fields": original_fields,
                    "fields": corrected_fields,
                    "bilingual_metadata": corrected_bilingual,
                    "annotation": annotation,
                    "source_site_before": source_site,
                    "source_site_after": corrected_source_site,
                    "catalog_source_site_before": catalog_source_site,
                    "catalog_source_site_after": corrected_catalog_source_site,
                    "fields_changed": sorted(
                        field
                        for field in set(original_fields) | set(corrected_fields)
                        if original_fields.get(field) != corrected_fields.get(field)
                    ),
                }
            )
    return (
        dict(sorted(variant_counts.items())),
        dict(sorted(bilingual_counts.items())),
        dict(sorted(source_site_counts.items())),
        planned,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _snapshot_source_name(item: dict[str, Any]) -> str:
    correction = {
        "url": item["url"],
        "raw_sha256": item["raw_sha256"],
        "fields": item["fields"],
        "bilingual_metadata": item["bilingual_metadata"],
        "annotation": item["annotation"],
        "source_site": _normalize_value(item["source_metadata"].get("source_site")),
        "catalog_source_site": item["catalog_metadata"].get("source_site"),
    }
    digest = hashlib.sha256(_canonical_json(correction).encode("utf-8")).hexdigest()[:12]
    return f"aict_name_correction_v1_{item['content_version_id']}_{digest}"


def _write_correction_snapshot(
    item: dict[str, Any], *, artifact_root: Path, temporary_root: Path
) -> tuple[Path, Path, str]:
    source_name = _snapshot_source_name(item)
    source_path = temporary_root / f"{source_name}.sqlite"
    storage = Storage._legacy_sqlite_schema_for_validation(source_path)
    file_metadata = item["source_metadata"]
    observation = item["source_observation"]
    catalog_metadata = item["catalog_metadata"]
    raw_sha = item["raw_sha256"]
    artifact_relpath = f"cas/sha256/{raw_sha[:2]}/{raw_sha}"
    artifact_path = artifact_root / artifact_relpath
    state = "missing"
    artifact_size = observation.get("source_byte_size") or item["version"].get("byte_size")
    verified_sha = None
    if artifact_path.is_file():
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        actual_size = artifact_path.stat().st_size
        if artifact_hash != raw_sha:
            raise content_hub.ContentHubError(
                "Original CAS artifact conflicts with its raw SHA-256"
            )
        if artifact_size is not None and int(artifact_size) != actual_size:
            raise content_hub.ContentHubError(
                "Original CAS artifact size conflicts with Hub metadata"
            )
        state, artifact_size, verified_sha = "present", actual_size, raw_sha
    elif bool(item["version"].get("blob_available")):
        raise content_hub.ContentHubError(
            "Hub marks the original CAS object present but it is unavailable"
        )
    try:
        database = storage._conn
        database.execute(
            "INSERT INTO files (id,url,sha256,title,source_site,source_page_url,original_filename,local_path,"
            "bytes,content_type,last_modified,etag,published_time,first_seen,last_seen,crawl_time,content_kind,"
            "deleted_at) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item["url"],
                raw_sha,
                item["fields"].get("title"),
                _normalize_value(file_metadata.get("source_site")),
                file_metadata.get("source_page_url"),
                file_metadata.get("original_filename"),
                file_metadata.get("local_path"),
                file_metadata.get("bytes"),
                file_metadata.get("content_type"),
                file_metadata.get("last_modified"),
                file_metadata.get("etag"),
                file_metadata.get("published_time"),
                file_metadata.get("first_seen"),
                file_metadata.get("last_seen"),
                file_metadata.get("crawl_time"),
                file_metadata.get("content_kind"),
                observation.get("deleted_at"),
            ),
        )
        keywords = item["fields"].get("keywords")
        if isinstance(keywords, (list, dict)):
            keywords = _canonical_json(keywords)
        bilingual_snapshot = _json_value(catalog_metadata.get("bilingual_metadata_json"))
        if bilingual_snapshot is not None:
            bilingual_snapshot = _canonical_json(_normalize_value(bilingual_snapshot))
        catalog_columns = [
            "file_url",
            "sha256",
            "pipeline_version",
            "processed_at",
            "status",
            "error",
            "keywords",
            "summary",
            "category",
            "bilingual_metadata_json",
            "updated_at",
            "file_sha256",
            "catalog_version",
            "markdown_content",
            "markdown_updated_at",
            "markdown_source",
            "rag_chunk_count",
            "rag_indexed",
            "rag_indexed_at",
        ]
        catalog_values = [
            item["url"],
            raw_sha,
            _CORRECTION_RECIPE,
            catalog_metadata.get("processed_at"),
            catalog_metadata.get("status") or "ok",
            catalog_metadata.get("error"),
            keywords,
            item["fields"].get("summary"),
            item["fields"].get("category"),
            bilingual_snapshot,
            _FIXED_TIMESTAMP,
            raw_sha,
            _CORRECTION_RECIPE,
            item["fields"].get("markdown_content"),
            _FIXED_TIMESTAMP,
            _CORRECTION_RECIPE,
            catalog_metadata.get("rag_chunk_count") or 0,
            catalog_metadata.get("rag_indexed") or 0,
            catalog_metadata.get("rag_indexed_at"),
        ]
        if "keywords_json" in item["fields"]:
            columns = {
                str(row[1])
                for row in database.execute("PRAGMA table_info(catalog_items)").fetchall()
            }
            if "keywords_json" not in columns:
                database.execute("ALTER TABLE catalog_items ADD COLUMN keywords_json TEXT")
            keywords_json = item["fields"]["keywords_json"]
            if isinstance(keywords_json, (list, dict)):
                keywords_json = _canonical_json(keywords_json)
            catalog_columns.append("keywords_json")
            catalog_values.append(keywords_json)
        if "source_site" in catalog_metadata:
            columns = {
                str(row[1])
                for row in database.execute("PRAGMA table_info(catalog_items)").fetchall()
            }
            if "source_site" not in columns:
                database.execute("ALTER TABLE catalog_items ADD COLUMN source_site TEXT")
            catalog_columns.append("source_site")
            catalog_values.append(catalog_metadata["source_site"])
        insert = (
            f"INSERT INTO catalog_items ({','.join(catalog_columns)}) "
            f"VALUES ({','.join('?' for _ in catalog_values)})"
        )
        database.execute(insert, tuple(catalog_values))
        database.commit()
        database.execute("VACUUM")
        database.commit()
        table_names = [
            str(row[0])
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        table_counts = {
            name: int(database.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
            for name in table_names
        }
    except sqlite3.Error as exc:
        raise content_hub.ContentHubError(
            "Could not build a deterministic AICT correction snapshot"
        ) from exc
    finally:
        storage._conn.close()

    snapshot_bytes = source_path.read_bytes()
    snapshot_sha = hashlib.sha256(snapshot_bytes).hexdigest()
    manifest = {
        "format": content_hub.MANIFEST_FORMAT,
        "version": 1,
        "source_name": source_name,
        "snapshot": {
            "sha256": snapshot_sha,
            "bytes": len(snapshot_bytes),
            "sqlite_user_version": content_hub.CURRENT_SQLITE_SCHEMA_VERSION,
            "wal_checkpointed": True,
            "table_counts": table_counts,
        },
        "files": [
            {
                "legacy_id": 1,
                "url": item["url"],
                "raw_sha256": raw_sha,
                "bytes": artifact_size,
                "state": state,
                "deleted_at": observation.get("deleted_at"),
                "cas_relpath": artifact_relpath if state == "present" else None,
                "verified_sha256": verified_sha,
            }
        ],
        "indexes": [],
    }
    manifest_path = artifact_root / "manifests" / source_name / f"{snapshot_sha}.json"
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
        raise content_hub.ContentHubError(
            "Existing correction manifest conflicts with its snapshot"
        )
    if not manifest_path.exists():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
    return source_path, manifest_path, source_name


def _new_markdown_variant_id(
    database_url: str, schema: str, source_name: str, version_id: int
) -> int:
    connection = psycopg2.connect(
        content_hub._database_url(database_url),
        options=f"-c search_path={schema},pg_catalog",
        connect_timeout=15,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tv.text_variant_id FROM text_variants tv "
                "JOIN source_snapshots s USING (source_snapshot_id) "
                "WHERE s.source_name=%s AND tv.content_version_id=%s "
                "AND tv.field_name='markdown_content' ORDER BY tv.text_variant_id DESC LIMIT 1",
                (source_name, version_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise content_hub.ContentHubError(
                    "Correction snapshot did not create a Markdown variant"
                )
            return int(row[0])
    finally:
        connection.close()


def run_correction(
    database_url: str,
    data_root: str | Path,
    *,
    apply: bool = False,
    schema: str = content_hub.HUB_SCHEMA,
) -> dict[str, Any]:
    """Read a selected-field plan; optionally append and bind deterministic corrections."""
    schema = content_hub._validate_schema(schema)
    root = Path(data_root).expanduser().resolve()
    connection = _connect_read_only(database_url, schema)
    try:
        variant_counts, bilingual_counts, source_site_counts, plan = _selected_correction_plan(
            connection, database_url, schema
        )
    finally:
        connection.close()
    report: dict[str, Any] = {
        "apply": bool(apply),
        "schema": schema,
        "historical_variant_hits": variant_counts,
        "historical_bilingual_hits": bilingual_counts,
        "current_source_site_hits": source_site_counts,
        "selected_versions_to_correct": len(plan),
        "records": [],
    }
    if not apply:
        report["records"] = [
            {
                "content_version_id": item["content_version_id"],
                "url": item["url"],
                "raw_sha256": item["raw_sha256"],
                "annotation_bound": item["annotation"] is not None,
                "source_site_before": item["source_site_before"],
                "source_site_after": item["source_site_after"],
                "catalog_source_site_before": item["catalog_source_site_before"],
                "catalog_source_site_after": item["catalog_source_site_after"],
                "old_markdown_text_variant_id": item["version"].get("markdown_text_variant_id"),
                "planned_markdown_sha256": (
                    hashlib.sha256(
                        str(item["fields"].get("markdown_content") or "").encode("utf-8")
                    ).hexdigest()
                    if item["fields"].get("markdown_content") is not None
                    else None
                ),
                "fields_changed": item["fields_changed"],
                "bilingual_fields_changed": sorted(
                    f"{language}.{field}"
                    for language in ("zh", "en")
                    for field in ("title", "summary", "keywords")
                    if item["bilingual_metadata"].get(language, {}).get(field)
                    != item["version"].get("bilingual_metadata", {}).get(language, {}).get(field)
                ),
                "annotation_evidence_changed": bool(
                    item["annotation"] and item["annotation"] != item["version"].get("annotation")
                ),
            }
            for item in plan
        ]
        return report

    if not plan:
        return report
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aict-name-correction-") as temporary_name:
        temporary_root = Path(temporary_name)
        for item in plan:
            source_path, manifest_path, source_name = _write_correction_snapshot(
                item, artifact_root=root, temporary_root=temporary_root
            )
            imported = content_hub.import_content_snapshot(
                source_path,
                manifest_path,
                root,
                root,
                database_url,
                schema=schema,
                expected_source_name=source_name,
            )
            if item["annotation"] is not None:
                markdown = item["fields"].get("markdown_content")
                if not isinstance(markdown, str) or not markdown.strip():
                    raise content_hub.ContentHubError(
                        "Annotated correction has no selected Markdown"
                    )
                variant_id = _new_markdown_variant_id(
                    database_url, schema, source_name, item["content_version_id"]
                )
                saved = content_hub.save_live_enrichment(
                    content_version_id=item["content_version_id"],
                    markdown_text_variant_id=variant_id,
                    markdown_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    primary_category=item["annotation"]["source_primary_category"],
                    bilingual_metadata=item["bilingual_metadata"],
                    categories=item["annotation"]["categories"],
                    date_facts=item["annotation"]["date_facts"],
                    date_review_status=item["annotation"]["date_review_status"],
                    date_review_reason=item["annotation"].get("date_review_reason"),
                    date_review_unresolved=item["annotation"].get("date_review_unresolved") or [],
                    recipe=_CORRECTION_RECIPE,
                    run_id=f"aict-name-correction-{item['content_version_id']}-{source_name.rsplit('_', 1)[-1]}",
                    database_url=database_url,
                    schema=schema,
                )
            else:
                variant_id = None
                saved = None
            current = content_hub.content_hub_read_version(
                item["url"], item["raw_sha256"], database_url, schema=schema
            )
            if (
                current is None
                or current["url"] != item["url"]
                or current["raw_sha256"] != item["raw_sha256"]
            ):
                raise content_hub.ContentHubError("Corrected Hub URL/raw-SHA identity changed")
            if current.get("source_key") != item["version"].get("source_key"):
                raise content_hub.ContentHubError("Correction changed the effective publisher key")
            current_file_metadata = _read_current_source_metadata(
                database_url, schema, item["content_version_id"], "files"
            )
            current_catalog_metadata = _read_current_source_metadata(
                database_url, schema, item["content_version_id"], "catalog_items"
            )
            if current_file_metadata.get("source_site") != item["source_site_after"]:
                raise content_hub.ContentHubError(
                    "Corrected file source-site metadata did not bind"
                )
            if current_catalog_metadata.get("source_site") != item["catalog_source_site_after"]:
                raise content_hub.ContentHubError(
                    "Corrected catalog source-site metadata did not bind"
                )
            if current.get("markdown") != item["fields"].get("markdown_content"):
                raise content_hub.ContentHubError("Corrected selected Markdown did not bind")
            if current.get("bilingual_metadata") != item["bilingual_metadata"]:
                raise content_hub.ContentHubError("Corrected bilingual metadata did not bind")
            if current.get("annotation") is not None:
                if current.get("markdown_text_variant_id") != variant_id:
                    raise content_hub.ContentHubError("Corrected annotation variant binding failed")
                if _normalize_value(current["annotation"]) != current["annotation"]:
                    raise content_hub.ContentHubError(
                        "Selected annotation still contains an old name"
                    )
            if _normalize_value(current.get("markdown")) != current.get("markdown"):
                raise content_hub.ContentHubError("Selected Markdown still contains an old name")
            if _normalize_value(current.get("bilingual_metadata")) != current.get(
                "bilingual_metadata"
            ):
                raise content_hub.ContentHubError(
                    "Selected bilingual metadata still contains an old name"
                )
            report["records"].append(
                {
                    "content_version_id": item["content_version_id"],
                    "url": item["url"],
                    "raw_sha256": item["raw_sha256"],
                    "source_site_before": item["source_site_before"],
                    "source_site_after": item["source_site_after"],
                    "catalog_source_site_before": item["catalog_source_site_before"],
                    "catalog_source_site_after": item["catalog_source_site_after"],
                    "correction_source": source_name,
                    "snapshot_already_imported": imported["already_imported"],
                    "markdown_text_variant_id": variant_id,
                    "markdown_sha256": current.get("markdown_sha256"),
                    "hub_binding_sha256": current.get("hub_markdown_sha256"),
                    "source_signature": (
                        current.get("annotation", {}).get("source_signature")
                        if current.get("annotation")
                        else None
                    ),
                    "result_sha256": (
                        current.get("annotation", {}).get("result_sha256")
                        if current.get("annotation")
                        else None
                    ),
                    "enrichment_saved": bool(saved),
                }
            )
    report["applied_count"] = len(report["records"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument(
        "--apply", action="store_true", help="write correction snapshots and rebind selections"
    )
    parser.add_argument("--schema", default=content_hub.HUB_SCHEMA)
    args = parser.parse_args()
    result = run_correction(args.database_url, args.data_root, apply=args.apply, schema=args.schema)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

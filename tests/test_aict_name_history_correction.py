from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote

import psycopg2
import pytest

from ai_actuarial import content_hub
from ai_actuarial import local_collection_target_worker as target_worker
from ai_actuarial.source_registry import install_registry, resolve_source
from scripts.aict_name_history_correction import (
    _legacy_copy_proof,
    _normalize_value,
    normalize_article_text,
    run_correction,
)
from tests.postgres_helpers import uninitialized_postgres_url_for_path


def _hub_database(tmp_path: Path) -> tuple[str, str]:
    database_url = uninitialized_postgres_url_for_path(tmp_path / "aict-hub.db")
    connection = psycopg2.connect(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = str(cursor.fetchone()[0])
    finally:
        connection.close()
    content_hub.apply_content_hub_schema(database_url, schema=schema)
    seed = json.loads(
        (Path(__file__).parents[1] / "config/source_registry_seed.json").read_text(encoding="utf-8")
    )
    with psycopg2.connect(database_url) as connection:
        install_registry(connection, seed, target="hub", apply=True)
    return database_url, schema


def _legacy_copy_preflight_fixture(
    tmp_path: Path, monkeypatch, binding_kind: str = "raw_utf8"
) -> dict:
    database_url, schema = _hub_database(tmp_path)
    data_root = tmp_path / "legacy-preflight-data"
    url = "https://en.airc.org.tw/re/files/legacy-preflight.pdf"
    raw = b"%PDF-1.7\nLegacy proof fixture source bytes"
    raw_sha = hashlib.sha256(raw).hexdigest()
    old_quote = "Actuarial Institute of Chinese Taipei (AICT)"
    old_secondary = "中華民國精算學會发布公告。"
    markdown = f"{old_quote}\n{old_secondary}\nPublished in 2024."
    with monkeypatch.context() as old_intake:
        old_intake.setattr(content_hub, "normalize_aict_institution_text", lambda value: value)
        imported = content_hub.ingest_live_article(
            canonical_url=url,
            source_site="aict",
            source_page_url="https://en.airc.org.tw/re/",
            title=old_quote,
            raw_bytes=raw,
            markdown=markdown,
            content_type="application/pdf",
            data_root=data_root,
            database_url=database_url,
            schema=schema,
        )
    bilingual = {
        "zh": {
            "title": "中华民国精算学会 2024 公告",
            "summary": "中华民国精算学会发布公告。",
            "category": "AI",
            "keywords": ["精算", "AI"],
        },
        "en": {
            "title": "Actuarial Institute of Chinese Taipei (AICT) 2024 Update",
            "summary": "Actuarial Institute of Chinese Taipei announced this update.",
            "category": "AI",
            "keywords": ["actuarial", "AI"],
        },
    }
    dates = {
        "publication_date": {
            "value": "2024",
            "precision": "year",
            "semantic": "publication",
            "evidence": "Published in 2024.",
            "location": "Article opening",
        },
        "revision_date": None,
        "document_version_date": None,
    }
    content_hub.save_live_enrichment(
        content_version_id=imported["content_version_id"],
        markdown_text_variant_id=imported["markdown_text_variant_id"],
        markdown_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        primary_category="AI",
        bilingual_metadata=bilingual,
        categories=[
            {"key": "AI", "evidence": [old_quote]},
            {"key": "Pricing", "evidence": [old_secondary]},
        ],
        date_facts=dates,
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="legacy-preflight-seed-v1",
        run_id="legacy-preflight-seed",
        database_url=database_url,
        schema=schema,
    )
    legacy_categories = [
        {"key": "AI", "evidence": []},
        {"key": "Pricing", "evidence": [old_secondary]},
    ]
    legacy_annotation = {
        "categories": legacy_categories,
        "date_facts": dates,
        "date_review_status": "complete",
        "date_review_reason": None,
        "date_review_unresolved": [],
    }
    result_sha = hashlib.sha256(
        content_hub._canonical_json(legacy_annotation).encode("utf-8")
    ).hexdigest()
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_sha256 FROM text_variants WHERE text_variant_id=%s",
                (imported["markdown_text_variant_id"],),
            )
            json_binding = cursor.fetchone()[0]
            binding_sha = (
                json_binding
                if binding_kind == "json_payload_utf8"
                else hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            )
            cursor.execute(
                "UPDATE article_enrichment_annotations SET source_markdown_sha256=%s, "
                "source_signature=%s, categories_json=%s, result_sha256=%s "
                "WHERE content_version_id=%s",
                (
                    binding_sha,
                    "a" * 64,
                    json.dumps(legacy_categories, ensure_ascii=False),
                    result_sha,
                    imported["content_version_id"],
                ),
            )
            cursor.execute(
                "UPDATE bilingual_metadata SET markdown_sha256=%s WHERE content_version_id=%s",
                (binding_sha, imported["content_version_id"]),
            )
        connection.commit()
    finally:
        connection.close()
    version = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert version is not None
    old_annotation = version["annotation"]
    corrected_annotation = _normalize_value(old_annotation)
    corrected = {
        "content_version_id": version["content_version_id"],
        "markdown": normalize_article_text(version["markdown"]),
        "primary_category": old_annotation["source_primary_category"],
        "bilingual_metadata": _normalize_value(version["bilingual_metadata"]),
        "categories": corrected_annotation["categories"],
        "date_facts": corrected_annotation["date_facts"],
        "date_review_status": corrected_annotation["date_review_status"],
        "date_review_reason": corrected_annotation["date_review_reason"],
        "date_review_unresolved": corrected_annotation["date_review_unresolved"],
        "recipe": "aict-name-correction-v1",
        "run_id": "legacy-preflight-correction",
        "database_url": database_url,
        "schema": schema,
        "legacy_copy_proof": _legacy_copy_proof(version),
    }
    return {"common": corrected, "version": version, "schema": schema}


def test_name_normalizer_handles_wrapped_whitespace_and_preserves_url_destinations() -> None:
    source = (
        "Actuarial\nInstitute of Chinese\u00a0Taipei (AICT) and "
        "Actuarial Institute of the Republic of China (AIRC); "
        "中華民國精算學會 (AICT); "
        "[原档](https://example.test/Actuarial%20Institute%20of%20Chinese%20Taipei.pdf)"
    )
    corrected = normalize_article_text(source)
    assert corrected == (
        "Actuarial Institute Of Chinese Taibei (AICT) and "
        "Actuarial Institute Of Chinese Taibei (AICT); "
        "中华台北精算师协会; "
        "[原档](https://example.test/Actuarial%20Institute%20of%20Chinese%20Taipei.pdf)"
    )
    assert normalize_article_text(corrected) == corrected
    assert unquote(corrected.split("](", 1)[1][:-1]) == unquote(source.split("](", 1)[1][:-1])


def test_name_normalizer_preserves_markdown_destinations_and_reference_ids() -> None:
    source = (
        "中华民国精算学会 and surrounding 中華民國精算學會. "
        '[中華民國精算學會](../docs/中華民國精算學會.pdf "Actuarial Institute of the Republic of China (AIRC)")\n'
        "![中华民国精算学会](../images/中华民国精算学会.png '中华民国精算学会 (AICT)')\n"
        "[中文参考标签][old-reference]\n"
        '[old-reference]: <../reference/中华民国精算学会.pdf> "中華民國精算學會（AIRC）"\n'
        "[中华民国精算学会][]\n"
        '[中华民国精算学会]: ../collapsed/中华民国精算学会.pdf "中华民国精算学会"\n'
        "[中華民國精算學會 (AIRC)]\n"
        '[中華民國精算學會 (AIRC)]: ../shortcut/中华民国精算学会.pdf "中华民国精算学会"\n'
        '<a href="../html/中华民国精算学会.html" title="中华民国精算学会">中华民国精算学会</a> '
        "after 中華民國精算學會"
    )
    corrected = normalize_article_text(source)
    assert corrected == (
        "中华台北精算师协会 and surrounding 中华台北精算师协会. "
        '[中华台北精算师协会](../docs/中華民國精算學會.pdf "Actuarial Institute Of Chinese Taibei (AICT)")\n'
        "![中华台北精算师协会](../images/中华民国精算学会.png '中华台北精算师协会')\n"
        "[中文参考标签][old-reference]\n"
        '[old-reference]: <../reference/中华民国精算学会.pdf> "中华台北精算师协会"\n'
        "[中华台北精算师协会][中华民国精算学会]\n"
        '[中华民国精算学会]: ../collapsed/中华民国精算学会.pdf "中华台北精算师协会"\n'
        "[中华台北精算师协会][中華民國精算學會 (AIRC)]\n"
        '[中華民國精算學會 (AIRC)]: ../shortcut/中华民国精算学会.pdf "中华台北精算师协会"\n'
        '<a href="../html/中华民国精算学会.html" title="中华台北精算师协会">中华台北精算师协会</a> '
        "after 中华台北精算师协会"
    )
    assert normalize_article_text(corrected) == corrected


@pytest.mark.parametrize(
    "former_name",
    [
        "中華民國精算學會（AIRC）",
        "中华台北精算学会 (AICT)",
        "台灣精算師協會（AIRC）",
    ],
)
def test_name_normalizer_consumes_acronym_suffixes_for_chinese_names(former_name: str) -> None:
    assert normalize_article_text(former_name) == "中华台北精算师协会"
    assert normalize_article_text(f"{former_name}，{former_name}") == (
        "中华台北精算师协会，中华台北精算师协会"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("中华民国精算学会发布公告", "中华台北精算师协会发布公告"),
        ("中华民国精算学会（AIRC）发布公告", "中华台北精算师协会发布公告"),
        ("中華民國精算學會（AICT）发布公告", "中华台北精算师协会发布公告"),
        ("中华台北精算学会表示", "中华台北精算师协会表示"),
        (
            "资料由Actuarial Institute of Chinese Taipei发布",
            "资料由Actuarial Institute Of Chinese Taibei (AICT)发布",
        ),
        (
            "资料由Actuarial Institute of the Republic of China (AIRC)发布",
            "资料由Actuarial Institute Of Chinese Taibei (AICT)发布",
        ),
    ],
)
def test_name_normalizer_replaces_chinese_names_before_adjacent_prose(
    source: str, expected: str
) -> None:
    corrected = normalize_article_text(source)
    assert corrected == expected
    assert normalize_article_text(corrected) == corrected


def test_live_ingest_normalizes_derived_text_without_changing_raw_identity(tmp_path: Path) -> None:
    database_url, schema = _hub_database(tmp_path)
    data_root = tmp_path / "future-hub-data"
    url = "https://en.airc.org.tw/re/files/future-name.pdf?download=1"
    raw = b"%PDF-1.7\nThe unchanged downloaded source bytes"
    raw_sha = hashlib.sha256(raw).hexdigest()
    old_title = (
        "Actuarial\nInstitute of Chinese\u00a0Taipei (AICT) update；"
        "中華民國精算學會发布公告；"
        "资料由Actuarial Institute of Chinese Taipei发布"
    )
    old_markdown = (
        "# 中華台北精算學會\n\n"
        "Actuarial Institute of the Republic of China published an update.\n"
        "中华民国精算学会（AIRC）发布公告。\n"
        "资料由Actuarial Institute of the Republic of China (AIRC)发布公告。\n"
        "[Original](https://example.test/Actuarial%20Institute%20of%20Chinese%20Taipei.pdf)"
    )
    args = {
        "canonical_url": url,
        "source_site": "aict",
        "source_page_url": "https://en.airc.org.tw/re/",
        "title": old_title,
        "raw_bytes": raw,
        "markdown": old_markdown,
        "content_type": "application/pdf",
        "data_root": data_root,
        "database_url": database_url,
        "schema": schema,
        "metadata": {"observed_at": "2026-11-03T12:00:00+00:00", "title": old_title},
    }
    imported = content_hub.ingest_live_article(**args)
    repeated = content_hub.ingest_live_article(**args)
    selected = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert selected is not None
    assert imported["raw_sha256"] == repeated["raw_sha256"] == raw_sha
    assert imported["source_name"] == repeated["source_name"]
    assert repeated["already_imported"] is True
    assert selected["url"] == url
    assert selected["raw_sha256"] == raw_sha
    assert selected["markdown"] == normalize_article_text(old_markdown)
    assert (
        selected["markdown_sha256"]
        == hashlib.sha256(selected["markdown"].encode("utf-8")).hexdigest()
    )
    cas_path = data_root / selected["cas_relpath"]
    assert cas_path.read_bytes() == raw
    assert hashlib.sha256(cas_path.read_bytes()).hexdigest() == raw_sha

    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_value_json FROM text_variants "
                "WHERE content_version_id=%s AND field_name='title' ORDER BY text_variant_id DESC LIMIT 1",
                (imported["content_version_id"],),
            )
            assert content_hub._load_json(cursor.fetchone()[0]) == normalize_article_text(old_title)
    finally:
        connection.close()


@pytest.mark.parametrize("old_binding_kind", ["raw_utf8", "json_payload_utf8"])
def test_historical_selected_correction_rebinds_hashes_and_is_idempotent(
    tmp_path: Path, monkeypatch, old_binding_kind: str
) -> None:
    # Model a live capture created before the centrally enforced naming rule.
    database_url, schema = _hub_database(tmp_path)
    data_root = tmp_path / "hub-data"
    url = "https://en.airc.org.tw/re/files/name-correction.pdf"
    raw = b"%PDF-1.7\nOriginal CAS bytes remain unchanged"
    old_quote = "Actuarial\nInstitute of Chinese\u00a0Taipei (AICT)"
    markdown = (
        f"# {old_quote}\n\n{old_quote} published in 2024. "
        "中華民國精算學會（AIRC）发布公告。 "
        "资料由Actuarial Institute of Chinese Taipei发布。 "
        "[Source](https://example.test/Actuarial%20Institute%20of%20Chinese%20Taipei.pdf)\n"
        "Published in 2024."
    )
    raw_sha = hashlib.sha256(raw).hexdigest()
    with monkeypatch.context() as old_intake:
        old_intake.setattr(content_hub, "normalize_aict_institution_text", lambda value: value)
        imported = content_hub.ingest_live_article(
            canonical_url=url,
            source_site="aict",
            source_page_url="https://en.airc.org.tw/re/",
            title=old_quote,
            raw_bytes=raw,
            markdown=markdown,
            content_type="application/pdf",
            data_root=data_root,
            database_url=database_url,
            schema=schema,
        )
    historical_source_site = "Actuarial Institute of Chinese Taipei (AICT)"
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_metadata_json FROM source_record_map "
                "WHERE source_snapshot_id=%s AND source_table='files'",
                (imported["source_snapshot_id"],),
            )
            source_metadata = content_hub._load_json(cursor.fetchone()[0])
            source_metadata.update(
                {
                    "source_site": historical_source_site,
                    "source_page_url": "https://en.airc.org.tw/re/files/",
                    "original_filename": "name-correction.pdf",
                    "local_path": None,
                    "bytes": len(raw),
                    "content_type": None,
                    "last_modified": None,
                    "etag": 'W/"original-etag"',
                    "published_time": None,
                    "first_seen": "2024-01-02T03:04:05+00:00",
                    "last_seen": None,
                    "crawl_time": "2024-02-03T04:05:06+00:00",
                    "content_kind": "web_page",
                }
            )
            original_file_metadata = dict(source_metadata)
            cursor.execute(
                "UPDATE source_record_map SET source_metadata_json=%s "
                "WHERE source_snapshot_id=%s AND source_table='files'",
                (json.dumps(source_metadata, ensure_ascii=False), imported["source_snapshot_id"]),
            )
            cursor.execute(
                "SELECT legacy_metadata_json FROM source_file_observations WHERE source_snapshot_id=%s",
                (imported["source_snapshot_id"],),
            )
            observation_metadata = content_hub._load_json(cursor.fetchone()[0])
            observation_metadata["source_site"] = historical_source_site
            cursor.execute(
                "UPDATE source_file_observations SET legacy_metadata_json=%s "
                "WHERE source_snapshot_id=%s",
                (
                    json.dumps(observation_metadata, ensure_ascii=False),
                    imported["source_snapshot_id"],
                ),
            )
            catalog_metadata = {
                "file_url": url,
                "source_site": historical_source_site,
            }
            cursor.execute(
                "INSERT INTO source_record_map "
                "(source_snapshot_id,source_table,legacy_pk_json,content_version_id,source_metadata_json) "
                "VALUES (%s,'catalog_items',%s,%s,%s)",
                (
                    imported["source_snapshot_id"],
                    json.dumps({"file_url": url}, ensure_ascii=False, sort_keys=True),
                    imported["content_version_id"],
                    json.dumps(catalog_metadata, ensure_ascii=False),
                ),
            )
        connection.commit()
    finally:
        connection.close()
    seed_categories = [
        {"key": "AI", "evidence": [old_quote]},
        {"key": "Pricing", "evidence": ["中華民國精算學會（AIRC）发布公告。"]},
    ]
    old_dates = {
        "publication_date": {
            "value": "2024",
            "precision": "year",
            "semantic": "publication",
            "evidence": "Published in 2024.",
            "location": "Article opening",
        },
        "revision_date": None,
        "document_version_date": None,
    }
    old_bilingual = {
        "zh": {
            "title": "中华民国精算学会 2024 公告",
            "summary": "中华民国精算学会发布该公告。",
            "category": "AI",
            "keywords": ["精算", "AI"],
        },
        "en": {
            "title": "Actuarial Institute of Chinese Taipei (AICT) 2024 Update",
            "summary": "Actuarial Institute of Chinese Taipei announced this update.",
            "category": "AI",
            "keywords": ["actuarial", "AI"],
        },
    }
    original_enrichment = content_hub.save_live_enrichment(
        content_version_id=imported["content_version_id"],
        markdown_text_variant_id=imported["markdown_text_variant_id"],
        markdown_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        primary_category="AI",
        bilingual_metadata=old_bilingual,
        categories=seed_categories,
        date_facts=old_dates,
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="fixture-enrichment-v1",
        run_id="fixture-old-name",
        database_url=database_url,
        schema=schema,
    )
    assert original_enrichment["success"] is True
    legacy_categories = [
        {"key": "AI", "evidence": []},
        {"key": "Pricing", "evidence": ["中華民國精算學會（AIRC）发布公告。"]},
    ]
    legacy_annotation = {
        "categories": legacy_categories,
        "date_facts": old_dates,
        "date_review_status": "complete",
        "date_review_reason": None,
        "date_review_unresolved": [],
    }
    legacy_result_sha = hashlib.sha256(
        content_hub._canonical_json(legacy_annotation).encode("utf-8")
    ).hexdigest()
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT language_code, provenance_json FROM bilingual_metadata "
                "WHERE content_version_id=%s ORDER BY language_code",
                (imported["content_version_id"],),
            )
            old_provenance = {language: provenance for language, provenance in cursor.fetchall()}
            cursor.execute(
                "SELECT payload_value_json, payload_sha256 FROM text_variants "
                "WHERE text_variant_id=%s AND field_name='markdown_content'",
                (imported["markdown_text_variant_id"],),
            )
            _old_payload, old_payload_sha = cursor.fetchone()
            old_markdown_binding = (
                old_payload_sha
                if old_binding_kind == "json_payload_utf8"
                else hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            )
            cursor.execute(
                "UPDATE article_enrichment_annotations SET source_markdown_sha256=%s, "
                "source_signature=%s, categories_json=%s, result_sha256=%s "
                "WHERE content_version_id=%s",
                (
                    old_markdown_binding,
                    "a" * 64,
                    json.dumps(legacy_categories, ensure_ascii=False),
                    legacy_result_sha,
                    imported["content_version_id"],
                ),
            )
            cursor.execute(
                "UPDATE bilingual_metadata SET markdown_sha256=%s WHERE content_version_id=%s",
                (old_markdown_binding, imported["content_version_id"]),
            )
        connection.commit()
    finally:
        connection.close()
    original = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert original is not None
    assert original["source_key"] == "aict"
    assert original["source_name_zh"] == "中华台北精算师协会"
    assert original["source_name_en"] == "Actuarial Institute Of Chinese Taibei"
    assert original["hub_markdown_sha256_kind"] == old_binding_kind
    assert original["annotation"]["source_signature"] == "a" * 64
    assert original["annotation"]["categories"] == legacy_categories
    assert original["annotation"]["result_sha256"] == legacy_result_sha
    cas_path = data_root / original["cas_relpath"]
    assert cas_path.read_bytes() == raw
    raw_sha_before = original["raw_sha256"]

    plan = run_correction(database_url, data_root, schema=schema)
    assert plan["selected_versions_to_correct"] == 1
    assert plan["annotation_preflight"]["annotation_bound_versions"] == 1
    assert plan["annotation_preflight"]["legacy_empty_primary_versions"] == 1
    assert plan["annotation_preflight"]["binding_kind_counts"][old_binding_kind] == 1
    assert plan["records"][0]["annotation_bound"] is True
    assert plan["records"][0]["source_site_before"] == historical_source_site
    assert plan["records"][0]["source_site_after"] == "Actuarial Institute Of Chinese Taibei (AICT)"
    assert plan["records"][0]["catalog_source_site_before"] == historical_source_site
    assert plan["records"][0]["catalog_source_site_after"] == (
        "Actuarial Institute Of Chinese Taibei (AICT)"
    )
    assert plan["records"][0]["fields_changed"] == ["markdown_content", "title"]
    before_status = content_hub.content_hub_status(database_url, schema=schema)

    applied = run_correction(database_url, data_root, apply=True, schema=schema)
    assert applied["applied_count"] == 1
    corrected = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert corrected is not None
    assert corrected["url"] == original["url"] == url
    assert corrected["raw_sha256"] == raw_sha_before == raw_sha
    assert corrected["source_key"] == original["source_key"] == "aict"
    assert corrected["source_name_zh"] == original["source_name_zh"] == "中华台北精算师协会"
    assert (
        corrected["source_name_en"]
        == original["source_name_en"]
        == "Actuarial Institute Of Chinese Taibei"
    )
    assert corrected["markdown"] == normalize_article_text(markdown)
    assert corrected["markdown_text_variant_id"] != original["markdown_text_variant_id"]
    assert (
        corrected["markdown_sha256"]
        == hashlib.sha256(corrected["markdown"].encode("utf-8")).hexdigest()
    )
    assert corrected["hub_markdown_sha256"] == corrected["markdown_sha256"]
    assert corrected["annotation"] is not None
    assert corrected["annotation"]["source_signature"] != original["annotation"]["source_signature"]
    assert corrected["annotation"]["result_sha256"] != original["annotation"]["result_sha256"]
    assert corrected["annotation"]["source_primary_category"] == "AI"
    assert [item["key"] for item in corrected["annotation"]["categories"]] == [
        "AI",
        "Pricing",
    ]
    assert corrected["annotation"]["date_facts"]["publication_date"]["value"] == "2024"
    assert corrected["annotation"]["date_facts"]["publication_date"]["semantic"] == "publication"
    assert corrected["annotation"]["categories"][0]["evidence"] == []
    assert corrected["annotation"]["categories"][1]["evidence"] == ["中华台北精算师协会发布公告。"]
    assert corrected["bilingual_metadata"]["zh"]["title"] == "中华台北精算师协会 2024 公告"
    assert corrected["bilingual_metadata"]["en"]["summary"] == (
        "Actuarial Institute Of Chinese Taibei (AICT) announced this update."
    )
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT language_code, provenance_json FROM bilingual_metadata "
                "WHERE content_version_id=%s ORDER BY language_code",
                (original["content_version_id"],),
            )
            current_provenance = {
                language: provenance for language, provenance in cursor.fetchall()
            }
        copied_provenance = {
            "recipe": "aict-name-correction-v1",
            "author": "Deterministic AICT name-only correction copy",
            "fields": ["title", "summary", "category", "keywords"],
        }
        assert current_provenance == {
            language: [*prior, copied_provenance] for language, prior in old_provenance.items()
        }
    finally:
        connection.close()
    assert (
        "https://example.test/Actuarial%20Institute%20of%20Chinese%20Taipei.pdf"
        in corrected["markdown"]
    )
    assert cas_path.read_bytes() == raw
    assert hashlib.sha256(cas_path.read_bytes()).hexdigest() == raw_sha

    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_metadata_json FROM source_record_map "
                "WHERE content_version_id=%s AND source_table='files' "
                "ORDER BY source_snapshot_id DESC",
                (original["content_version_id"],),
            )
            current_metadata_json = cursor.fetchone()[0]
            current_metadata = content_hub._load_json(current_metadata_json)
            assert current_metadata["source_site"] == "Actuarial Institute Of Chinese Taibei (AICT)"
            expected_current_file_metadata = {
                "sha256": raw_sha,
                "deleted_at": None,
                **{
                    field: original_file_metadata[field]
                    for field in (
                        "source_page_url",
                        "original_filename",
                        "local_path",
                        "bytes",
                        "content_type",
                        "last_modified",
                        "etag",
                        "published_time",
                        "first_seen",
                        "last_seen",
                        "crawl_time",
                        "content_kind",
                    )
                },
                "source_site": "Actuarial Institute Of Chinese Taibei (AICT)",
            }
            assert current_metadata == expected_current_file_metadata
            cursor.execute(
                "SELECT source_metadata_json FROM source_record_map "
                "WHERE content_version_id=%s AND source_table='catalog_items' "
                "ORDER BY source_snapshot_id DESC",
                (original["content_version_id"],),
            )
            current_catalog_json = cursor.fetchone()[0]
            current_catalog_metadata = content_hub._load_json(current_catalog_json)
            assert current_catalog_metadata["source_site"] == (
                "Actuarial Institute Of Chinese Taibei (AICT)"
            )
            cursor.execute(
                "SELECT source_metadata_json FROM source_record_map "
                "WHERE source_snapshot_id=%s AND source_table='files'",
                (imported["source_snapshot_id"],),
            )
            archived_metadata = content_hub._load_json(cursor.fetchone()[0])
            assert archived_metadata == original_file_metadata
            cursor.execute(
                "SELECT source_metadata_json FROM source_record_map "
                "WHERE source_snapshot_id=%s AND source_table='catalog_items'",
                (imported["source_snapshot_id"],),
            )
            archived_catalog_metadata = content_hub._load_json(cursor.fetchone()[0])
            assert archived_catalog_metadata["source_site"] == historical_source_site
            cursor.execute(
                "SELECT payload_value_json FROM text_variants WHERE text_variant_id=%s",
                (original["markdown_text_variant_id"],),
            )
            historical_payload = content_hub._load_json(cursor.fetchone()[0])
        assert historical_payload == markdown
        assert (
            resolve_source(
                connection,
                url=url,
                raw_source=historical_source_site,
                raw_sha256=raw_sha,
            )
            == corrected["source_key"]
        )
        assert (
            resolve_source(
                connection,
                url=url,
                raw_source=current_metadata["source_site"],
                raw_sha256=raw_sha,
            )
            == corrected["source_key"]
        )
    finally:
        connection.close()

    repeat = run_correction(database_url, data_root, apply=True, schema=schema)
    assert repeat["selected_versions_to_correct"] == 0
    after_status = content_hub.content_hub_status(database_url, schema=schema)
    assert after_status["content_version_count"] == before_status["content_version_count"]
    assert after_status["text_variant_count"] == before_status["text_variant_count"] + 5


def _run_legacy_copy_preflight(case: dict, **overrides):
    payload = copy.deepcopy(case["common"])
    payload.update(overrides)
    return content_hub._preflight_legacy_name_correction_copy(**payload)


@pytest.mark.parametrize(
    "proof_field",
    [
        "source_text_variant_id",
        "markdown_sha256",
        "hub_markdown_sha256",
        "hub_markdown_sha256_kind",
        "source_signature",
        "result_sha256",
        "bilingual_payload_sha256",
        "bilingual_metadata",
    ],
)
def test_legacy_name_copy_preflight_rejects_stale_binding_proof(
    tmp_path: Path, monkeypatch, proof_field: str
) -> None:
    case = _legacy_copy_preflight_fixture(tmp_path, monkeypatch)
    proof = copy.deepcopy(case["common"]["legacy_copy_proof"])
    if proof_field == "source_text_variant_id":
        proof[proof_field] += 1
    elif proof_field == "hub_markdown_sha256_kind":
        proof[proof_field] = "json_payload_utf8"
    elif proof_field == "bilingual_metadata":
        proof[proof_field]["en"]["title"] += " changed"
    else:
        proof[proof_field] = "b" * 64
    with pytest.raises(content_hub.ContentHubError):
        _run_legacy_copy_preflight(case, legacy_copy_proof=proof)


@pytest.mark.parametrize("mutation", ["markdown", "bilingual", "category", "date"])
def test_legacy_name_copy_preflight_rejects_non_name_only_changes(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    case = _legacy_copy_preflight_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(case["common"])
    if mutation == "markdown":
        payload["markdown"] += "\nUnrelated added text."
    elif mutation == "bilingual":
        payload["bilingual_metadata"]["en"]["title"] += " changed"
    elif mutation == "category":
        payload["categories"][1]["key"] = "Other"
    else:
        payload["date_facts"]["publication_date"]["value"] = "2025"
    with pytest.raises(
        content_hub.ContentHubError,
        match="non-name changes|changes beyond institution names",
    ):
        content_hub._preflight_legacy_name_correction_copy(**payload)


@pytest.mark.parametrize("mutation", ["bilingual_value", "bilingual_binding"])
def test_legacy_name_copy_preflight_rejects_changed_locked_bilingual_rows(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    case = _legacy_copy_preflight_fixture(tmp_path, monkeypatch)
    common = case["common"]
    connection = psycopg2.connect(
        common["database_url"], options=f"-c search_path={common['schema']},pg_catalog"
    )
    try:
        with connection.cursor() as cursor:
            if mutation == "bilingual_value":
                cursor.execute(
                    "UPDATE bilingual_metadata SET title=title || ' changed' "
                    "WHERE content_version_id=%s AND language_code='en'",
                    (common["content_version_id"],),
                )
            else:
                cursor.execute(
                    "UPDATE bilingual_metadata SET markdown_sha256=%s "
                    "WHERE content_version_id=%s AND language_code='en'",
                    ("b" * 64, common["content_version_id"]),
                )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(content_hub.ContentHubError):
        _run_legacy_copy_preflight(case)


def test_unannotated_correction_preserves_keywords_and_keywords_json_variants(
    tmp_path: Path, monkeypatch
) -> None:
    # Model a pre-normalizer, unannotated Hub version whose two keyword fields
    # independently contain the old institution name.
    monkeypatch.setattr(content_hub, "normalize_aict_institution_text", lambda value: value)
    database_url, schema = _hub_database(tmp_path)
    data_root = tmp_path / "unannotated-hub-data"
    url = "https://en.airc.org.tw/re/files/unannotated-keywords.pdf"
    raw = b"%PDF-1.7\nUnannotated source bytes remain unchanged"
    raw_sha = hashlib.sha256(raw).hexdigest()
    old_name = "Actuarial Institute of Chinese Taipei"
    imported = content_hub.ingest_live_article(
        canonical_url=url,
        source_site="aict",
        source_page_url="https://en.airc.org.tw/re/",
        title=old_name,
        raw_bytes=raw,
        markdown=f"# {old_name}\n\nHistorical article.",
        content_type="application/pdf",
        data_root=data_root,
        database_url=database_url,
        schema=schema,
    )
    keywords_json = json.dumps([old_name, "risk management"], ensure_ascii=False)
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            for field_name, payload in (
                ("keywords", old_name),
                ("keywords_json", keywords_json),
            ):
                content_hub._insert_variant(
                    cursor,
                    snapshot_id=imported["source_snapshot_id"],
                    version_id=imported["content_version_id"],
                    source_table="catalog_items",
                    source_pk_json=content_hub._json_text({"pk": url, "rowid": None}),
                    field_name=field_name,
                    payload=payload,
                    recipe_identity="fixture-pre-normalizer-v1",
                    provenance={"source": "focused regression fixture"},
                )
        connection.commit()
    finally:
        connection.close()

    plan = run_correction(database_url, data_root, schema=schema)
    assert plan["selected_versions_to_correct"] == 1
    assert plan["records"][0]["annotation_bound"] is False
    assert "keywords" in plan["records"][0]["fields_changed"]
    assert "keywords_json" in plan["records"][0]["fields_changed"]

    applied = run_correction(database_url, data_root, apply=True, schema=schema)
    assert applied["applied_count"] == 1
    corrected = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert corrected is not None
    assert corrected["raw_sha256"] == raw_sha
    assert (data_root / corrected["cas_relpath"]).read_bytes() == raw

    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT field_name, payload_value_json FROM text_variants "
                "WHERE content_version_id=%s AND field_name IN ('keywords','keywords_json') "
                "ORDER BY text_variant_id DESC",
                (imported["content_version_id"],),
            )
            selected: dict[str, object] = {}
            for field_name, payload in cursor.fetchall():
                if field_name not in selected:
                    selected[str(field_name)] = content_hub._load_json(payload)
        assert selected["keywords"] == normalize_article_text(old_name)
        assert selected["keywords_json"] == json.dumps(
            [normalize_article_text(old_name), "risk management"], ensure_ascii=False
        )
    finally:
        connection.close()

    repeated = run_correction(database_url, data_root, apply=True, schema=schema)
    assert repeated["selected_versions_to_correct"] == 0
    assert repeated.get("applied_count", 0) == 0


def test_unannotated_correction_preserves_latest_explicit_null_field(
    tmp_path: Path, monkeypatch
) -> None:
    # A newer explicit-null title must win over the older title when Markdown
    # independently causes a selected correction.
    monkeypatch.setattr(content_hub, "normalize_aict_institution_text", lambda value: value)
    database_url, schema = _hub_database(tmp_path)
    data_root = tmp_path / "explicit-null-hub-data"
    url = "https://en.airc.org.tw/re/files/explicit-null-title.pdf"
    raw = b"%PDF-1.7\nUnannotated explicit-null source bytes"
    raw_sha = hashlib.sha256(raw).hexdigest()
    old_name = "Actuarial Institute of Chinese Taipei"
    markdown = f"# {old_name}\n\nHistorical article body."
    imported = content_hub.ingest_live_article(
        canonical_url=url,
        source_site="aict",
        source_page_url="https://en.airc.org.tw/re/",
        title=old_name,
        raw_bytes=raw,
        markdown=markdown,
        content_type="application/pdf",
        data_root=data_root,
        database_url=database_url,
        schema=schema,
    )
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            content_hub._insert_variant(
                cursor,
                snapshot_id=imported["source_snapshot_id"],
                version_id=imported["content_version_id"],
                source_table="files",
                source_pk_json=content_hub._json_text({"pk": 999, "rowid": None}),
                field_name="title",
                payload=None,
                recipe_identity="fixture-explicit-null-v1",
                provenance={"source": "focused regression fixture"},
            )
        connection.commit()
    finally:
        connection.close()

    plan = run_correction(database_url, data_root, schema=schema)
    assert plan["selected_versions_to_correct"] == 1
    assert plan["records"][0]["fields_changed"] == ["markdown_content"]
    applied = run_correction(database_url, data_root, apply=True, schema=schema)
    assert applied["applied_count"] == 1

    corrected = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert corrected is not None
    assert corrected["markdown"] == normalize_article_text(markdown)
    assert corrected["raw_sha256"] == raw_sha
    assert (data_root / corrected["cas_relpath"]).read_bytes() == raw
    repeated = run_correction(database_url, data_root, apply=True, schema=schema)
    assert repeated["selected_versions_to_correct"] == 0
    assert repeated.get("applied_count", 0) == 0
    connection = psycopg2.connect(database_url, options=f"-c search_path={schema},pg_catalog")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_value_json, payload_is_null FROM text_variants "
                "WHERE content_version_id=%s AND field_name='title' "
                "ORDER BY text_variant_id DESC LIMIT 1",
                (imported["content_version_id"],),
            )
            title_payload, title_is_null = cursor.fetchone()
            assert title_is_null is True
            assert content_hub._load_json(title_payload) is None
    finally:
        connection.close()


def test_bilingual_only_old_names_are_selected_corrected_and_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(content_hub, "normalize_aict_institution_text", lambda value: value)
    database_url, schema = _hub_database(tmp_path)
    data_root = tmp_path / "bilingual-only-hub-data"
    url = "https://en.airc.org.tw/re/files/bilingual-only.pdf"
    raw = b"%PDF-1.7\nBilingual-only source bytes remain unchanged"
    raw_sha = hashlib.sha256(raw).hexdigest()
    markdown = "# Current article\n\nPublished in 2024."
    imported = content_hub.ingest_live_article(
        canonical_url=url,
        source_site="aict",
        source_page_url="https://en.airc.org.tw/re/",
        title="Current article",
        raw_bytes=raw,
        markdown=markdown,
        content_type="application/pdf",
        data_root=data_root,
        database_url=database_url,
        schema=schema,
    )
    date_facts = {
        "publication_date": {
            "value": "2024",
            "precision": "year",
            "semantic": "publication",
            "evidence": "Published in 2024.",
            "location": "Article opening",
        },
        "revision_date": None,
        "document_version_date": None,
    }
    bilingual = {
        "zh": {
            "title": "中华民国精算学会公告",
            "summary": "中华民国精算学会发布公告。",
            "category": "AI",
            "keywords": ["中华民国精算学会"],
        },
        "en": {
            "title": "Actuarial Institute of Chinese Taipei (AICT)",
            "summary": "The Actuarial Institute of Chinese Taipei issued this notice.",
            "category": "AI",
            "keywords": ["Actuarial Institute of Chinese Taipei"],
        },
    }
    content_hub.save_live_enrichment(
        content_version_id=imported["content_version_id"],
        markdown_text_variant_id=imported["markdown_text_variant_id"],
        markdown_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        primary_category="AI",
        bilingual_metadata=bilingual,
        categories=[{"key": "AI", "evidence": ["Current article"]}],
        date_facts=date_facts,
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="fixture-bilingual-only-v1",
        run_id="fixture-bilingual-only-old-name",
        database_url=database_url,
        schema=schema,
    )

    original = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert original is not None
    assert original["markdown"] == markdown
    assert original["bilingual_metadata"] == bilingual
    plan = run_correction(database_url, data_root, schema=schema)
    assert plan["selected_versions_to_correct"] == 1
    assert plan["historical_bilingual_hits"] == {
        "en.keywords": 1,
        "en.summary": 1,
        "en.title": 1,
        "zh.keywords": 1,
        "zh.summary": 1,
        "zh.title": 1,
    }
    assert plan["records"][0]["fields_changed"] == []
    assert plan["records"][0]["bilingual_fields_changed"] == [
        "en.keywords",
        "en.summary",
        "en.title",
        "zh.keywords",
        "zh.summary",
        "zh.title",
    ]

    applied = run_correction(database_url, data_root, apply=True, schema=schema)
    assert applied["applied_count"] == 1
    corrected = content_hub.content_hub_read_version(url, raw_sha, database_url, schema=schema)
    assert corrected is not None
    assert corrected["url"] == url
    assert corrected["raw_sha256"] == raw_sha
    assert corrected["markdown"] == markdown
    assert corrected["bilingual_metadata"] == {
        "zh": {
            "title": "中华台北精算师协会公告",
            "summary": "中华台北精算师协会发布公告。",
            "category": "AI",
            "keywords": ["中华台北精算师协会"],
        },
        "en": {
            "title": "Actuarial Institute Of Chinese Taibei (AICT)",
            "summary": ("The Actuarial Institute Of Chinese Taibei (AICT) issued this notice."),
            "category": "AI",
            "keywords": ["Actuarial Institute Of Chinese Taibei (AICT)"],
        },
    }
    assert (data_root / corrected["cas_relpath"]).read_bytes() == raw

    repeated = run_correction(database_url, data_root, apply=True, schema=schema)
    assert repeated["selected_versions_to_correct"] == 0
    assert repeated.get("applied_count", 0) == 0


class _LabelCursor:
    def __init__(self, columns: list[str], row: tuple | None) -> None:
        self.description = [(column,) for column in columns]
        self._row = row

    def fetchone(self):
        return self._row


class _RegistryCursor:
    def __init__(self) -> None:
        self._row = None

    def execute(self, statement: str, parameters: tuple) -> None:
        if "FROM source_projection" in statement:
            self._row = None
        elif "FROM source_aliases" in statement:
            self._row = ("iaa",) if parameters[1] == "actuaries.org" else None
        else:
            raise AssertionError(f"unexpected resolver query: {statement}")

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _LabelConnection:
    def __init__(self, file_row: dict, catalog_row: dict) -> None:
        self.file_row = file_row
        self.catalog_row = catalog_row

    def table_exists(self, table: str) -> bool:
        return table == "catalog_items"

    def cursor(self):
        return _RegistryCursor()

    def execute(self, statement: str, parameters: tuple):
        if statement.startswith("SELECT * FROM files"):
            row = self.file_row.copy()
            return _LabelCursor(list(row), tuple(row.values()))
        if statement.startswith("SELECT * FROM catalog_items"):
            row = self.catalog_row.copy()
            return _LabelCursor(list(row), tuple(row.values()))
        if statement.startswith("UPDATE files SET source_site"):
            self.file_row["source_site"] = parameters[0]
            return None
        if statement.startswith("UPDATE catalog_items SET source_site"):
            self.catalog_row["source_site"] = parameters[0]
            return None
        raise AssertionError(f"unexpected label-normalization SQL: {statement}")


class _LabelStorage:
    def __init__(self, file_row: dict, catalog_row: dict) -> None:
        self._conn = _LabelConnection(file_row, catalog_row)

    @contextmanager
    def transaction(self, **_kwargs):
        yield

    def _ready_data_builder_metadata_snapshot(self, _url: str):
        return ("inactive",)

    def _mark_ready_data_builder_metadata_change(self, **_kwargs):
        return ()

    def close(self):
        return None


def test_target_label_migration_preserves_iaa_publisher_and_active_file_identity() -> None:
    url = "https://actuaries.org/app/uploads/2025/07/AI_Draft.pdf"
    digest = "a" * 64
    old_site = "Actuarial Institute of the Republic of China (AIRC)"
    file_row = {
        "id": 17,
        "url": url,
        "sha256": digest,
        "source_site": old_site,
        "source_key": None,
        "deleted_at": None,
        "title": "Unchanged title",
    }
    catalog_row = {
        "file_url": url,
        "sha256": digest,
        "file_sha256": digest,
        "source_site": old_site,
        "status": "ok",
        "markdown_content": "No old name in active content",
    }
    storage = _LabelStorage(file_row, catalog_row)
    record = {"url": url, "raw_sha256": digest, "expected_source_site": old_site}
    before = resolve_source(storage._conn, url=url, raw_source=old_site, raw_sha256=digest)
    assert before == "iaa"

    dry_run = target_worker.apply_aict_source_label_normalization(
        {"target": "overseas", "records": [record]}, storage_factory=lambda: storage
    )
    assert dry_run["records"][0]["status"] == "would_update"
    assert storage._conn.file_row["source_site"] == old_site

    applied = target_worker.apply_aict_source_label_normalization(
        {"target": "overseas", "records": [record], "apply": True},
        storage_factory=lambda: storage,
    )
    row = applied["records"][0]
    assert row["status"] == "updated"
    assert row["backup"]["file_id"] == 17
    assert row["backup"]["file_source_site"] == old_site
    assert row["source_site_after"] == "Actuarial Institute Of Chinese Taibei (AICT)"
    assert row["effective_publisher_key"] == "iaa"
    assert row["source_key_before"] == row["source_key_after"] is None
    assert row["file_row_unchanged_except_source_site"] is True
    assert row["catalog_row_unchanged_except_source_site"] is True
    assert row["ready_affected_kbs"] == []
    assert storage._conn.file_row["deleted_at"] is None
    assert storage._conn.catalog_row["markdown_content"] == "No old name in active content"
    assert (
        resolve_source(
            storage._conn,
            url=url,
            raw_source=storage._conn.file_row["source_site"],
            raw_sha256=digest,
        )
        == before
    )

    repeated = target_worker.apply_aict_source_label_normalization(
        {"target": "overseas", "records": [record]}, storage_factory=lambda: storage
    )
    assert repeated["records"][0]["status"] == "unchanged"


@pytest.mark.parametrize(
    "former_name",
    [
        "中華民國精算學會（AIRC）",
        "中 华 民 国 精 算 学 会 (AICT)",
        "中华台北精算学会 (AIRC)",
        "中华台北精算师协会（AICT）",
    ],
)
def test_target_label_aliases_accept_chinese_full_names_with_known_acronyms(
    former_name: str,
) -> None:
    assert target_worker._normalize_aict_display_name(former_name) == "中华台北精算师协会"


def test_target_label_migration_refuses_deleted_files() -> None:
    url = "https://actuaries.org/app/uploads/2025/07/deleted.pdf"
    digest = "b" * 64
    old_site = "Actuarial Institute of Chinese Taipei (AICT)"
    storage = _LabelStorage(
        {
            "id": 18,
            "url": url,
            "sha256": digest,
            "source_site": old_site,
            "source_key": None,
            "deleted_at": "2026-10-16",
        },
        {"file_url": url, "sha256": digest, "file_sha256": digest, "source_site": old_site},
    )
    with pytest.raises(ValueError, match="file is deleted"):
        target_worker.apply_aict_source_label_normalization(
            {
                "target": "overseas",
                "apply": True,
                "records": [{"url": url, "raw_sha256": digest, "expected_source_site": old_site}],
            },
            storage_factory=lambda: storage,
        )

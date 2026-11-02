from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

import ai_actuarial.capacity as capacity
import ai_actuarial.embedding_service as embedding_service
import ai_actuarial.local_collection_runtime as runtime
import ai_actuarial.local_collection_target_worker as worker


def _bind_item_enrichment(item: dict) -> dict:
    annotation = {
        key: item.get(key)
        for key in (
            "categories",
            "date_facts",
            "date_review_status",
            "date_review_reason",
            "date_review_unresolved",
        )
    }
    item["result_sha256"] = worker._hash(worker._canonical_json(annotation).encode("utf-8"))
    item["source_signature"] = worker._hash(
        worker._canonical_json(
            {
                "content_version_id": item["content_version_id"],
                "source_text_variant_id": item["markdown_text_variant_id"],
                "source_markdown_sha256": item["markdown_sha256"],
                "source_primary_category": item["source_primary_category"],
            }
        ).encode("utf-8")
    )
    return item


def _item(url: str, raw: bytes, markdown: str, *, version: int = 17) -> dict:
    md_sha = hashlib.sha256(markdown.encode()).hexdigest()
    raw_sha = hashlib.sha256(raw).hexdigest()
    return _bind_item_enrichment(
        {
            "url": url,
            "raw_sha256": raw_sha,
            "raw_bytes_b64": __import__("base64").b64encode(raw).decode(),
            "markdown": markdown,
            "markdown_sha256": md_sha,
            "hub_markdown_sha256": md_sha,
            "hub_markdown_sha256_kind": "raw_utf8",
            "content_version_id": version,
            "markdown_text_variant_id": version + 100,
            "title": "Pricing AI paper",
            "source_site": "cas",
            "source_page_url": "https://example.test/research",
            "content_type": "application/pdf",
            "source_primary_category": "AI",
            "categories": [
                {"key": "AI", "evidence": ["AI methods"]},
                {"key": "Pricing", "evidence": ["Pricing models"]},
                {"key": "Other", "evidence": ["AI methods"]},
            ],
            "date_facts": {
                "publication_date": None,
                "revision_date": None,
                "document_version_date": None,
            },
            "date_review_status": "complete",
            "date_review_reason": None,
            "date_review_unresolved": [],
            "bilingual_metadata": {
                language: {
                    "title": "Pricing AI paper",
                    "summary": "Pricing models use AI methods.",
                    "category": "AI",
                    "keywords": ["pricing", "AI"],
                }
                for language in ("zh", "en")
            },
        }
    )


class _ChunkSetCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows


class _ChunkSetConnection:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def execute(self, statement: str, params: tuple):
        if "chunk_set_id IN" in statement:
            return _ChunkSetCursor([row for row in self.rows if row[0] in params])
        if "file_url = ?" in statement and "profile_id = ?" in statement:
            url, profile_id = params
            return _ChunkSetCursor(
                [row for row in self.rows if row[1] == url and row[2] == profile_id]
            )
        raise AssertionError(f"unexpected chunk selection SQL: {statement}")


class _ChunkSetStorage:
    def __init__(self, rows: list[tuple]) -> None:
        self._conn = _ChunkSetConnection(rows)
        self.rows = rows

    def list_chunks_for_embedding(self, chunk_set_ids: list[str]) -> list[dict]:
        selected = [row for row in self.rows if row[0] in chunk_set_ids]
        return [
            {
                "chunk_id": f"{chunk_set_id}-{index}",
                "chunk_set_id": chunk_set_id,
                "content": "valid native chunk",
            }
            for row in selected
            for chunk_set_id in [row[0]]
            for index in range(row[5])
        ]


def test_native_embedding_selector_uses_exact_chunk_set_id_when_url_is_ambiguous() -> None:
    url = "https://example.test/article.pdf"
    profile_id = "profile-ai"
    rows = [
        ("set-older", url, profile_id, "a" * 64, "profile-hash", 2),
        ("set-current", url, profile_id, "b" * 64, "profile-hash", 3),
    ]
    storage = _ChunkSetStorage(rows)

    with pytest.raises(
        embedding_service.EmbeddingSelectionError, match="ambiguous ready chunk sets"
    ):
        embedding_service.resolve_embedding_selection(
            storage, file_urls=[url], profile_id=profile_id
        )

    selected = embedding_service.resolve_embedding_selection(storage, chunk_set_ids=["set-current"])
    assert selected["chunk_set_ids"] == ["set-current"]
    assert selected["chunk_sets"] == [
        {
            "chunk_set_id": "set-current",
            "file_url": url,
            "profile_id": profile_id,
            "markdown_hash": "b" * 64,
            "profile_config_hash": "profile-hash",
            "chunk_count": 3,
        }
    ]
    assert {row["chunk_set_id"] for row in selected["chunks"]} == {"set-current"}


def test_target_item_preserves_ai_primary_and_three_secondary_categories() -> None:
    raw = b"%PDF-1.7\nsource bytes"
    markdown = "Pricing models use AI methods."
    original = _item("https://example.test/pricing.pdf", raw, markdown)
    original["categories"] = [
        {"key": "AI", "evidence": ["AI methods"]},
        {"key": "Pricing", "evidence": ["Pricing models"]},
        {"key": "Research", "evidence": ["Pricing models use AI methods"]},
        {"key": "Other", "evidence": ["AI methods"]},
    ]
    _bind_item_enrichment(original)
    item = worker._normalize_item(original, "china", ["AI", "Pricing", "Research", "Other"])
    assert item["target_category"] == "AI"
    assert item["serving_metadata"]["hub_enrichment"]["source_primary_category"] == "AI"
    assert (
        item["serving_metadata"]["hub_enrichment"]["ordered_categories"] == original["categories"]
    )
    assert item["serving_metadata"]["zh"]["category"] == "AI"
    assert item["serving_metadata"]["hub_enrichment"]["source_primary_category"] == "AI"
    assert item["metadata_fingerprint"] == runtime._target_metadata_fingerprint(original)
    assert item["source_site"] == "cas"
    non_ai_first = _bind_item_enrichment(
        {**original, "categories": [{"key": "Pricing", "evidence": ["Pricing models"]}]}
    )
    with pytest.raises(ValueError, match="primary category must be AI"):
        worker._normalize_item(
            non_ai_first,
            "china",
            ["AI", "Pricing"],
        )
    wrong_source_primary = _bind_item_enrichment({**original, "source_primary_category": "Pricing"})
    with pytest.raises(ValueError, match="primary category must be AI"):
        worker._normalize_item(
            wrong_source_primary,
            "china",
            ["AI", "Pricing", "Research", "Other"],
        )


@pytest.mark.parametrize("field", ["source_signature", "result_sha256"])
def test_target_rejects_forged_current_hub_signature_or_result_digest(field: str) -> None:
    item = _item(
        "https://example.test/forged-hub-binding.pdf",
        b"forged binding bytes",
        "Pricing models use AI methods.",
    )
    item[field] = "0" * 64
    message = (
        "source signature mismatch" if field == "source_signature" else "result digest mismatch"
    )
    with pytest.raises(ValueError, match=message):
        worker._normalize_item(item, "china", ["AI", "Pricing", "Other"])


def test_target_accepts_only_result_bound_legacy_empty_ai_primary_evidence() -> None:
    item = _item(
        "https://example.test/legacy-empty-primary-evidence.pdf",
        b"legacy annotation bytes",
        "Pricing research uses AI methods. Published 2024-12.",
    )
    item["categories"] = [
        {"key": "AI", "evidence": []},
        {"key": "Pricing", "evidence": ["Pricing research"]},
        {"key": "Research", "evidence": ["AI methods"]},
        {"key": "Other", "evidence": ["Pricing research uses AI methods."]},
    ]
    item["legacy_hub_annotation"] = True
    item["date_facts"]["publication_date"] = {
        "semantic": "publication",
        "value": "2024-12",
        "precision": "month",
        "evidence": "Published 2024-12",
        "location": "page 1",
    }
    item["result_sha256"] = worker._hash(
        worker._canonical_json(
            {
                key: item.get(key)
                for key in (
                    "categories",
                    "date_facts",
                    "date_review_status",
                    "date_review_reason",
                    "date_review_unresolved",
                )
            }
        ).encode("utf-8")
    )
    normalized = worker._normalize_item(item, "china", ["AI", "Pricing", "Research", "Other"])
    assert normalized["published_time"] == "2024-12"
    assert (
        normalized["serving_metadata"]["hub_enrichment"]["ordered_categories"] == item["categories"]
    )

    unmarked = {**item, "legacy_hub_annotation": False}
    with pytest.raises(ValueError, match="primary category must be AI"):
        worker._normalize_item(unmarked, "china", ["AI", "Pricing", "Research", "Other"])

    tampered = {**item, "categories": [*item["categories"]]}
    tampered["categories"][0] = {"key": "AI", "evidence": ["invented quote"]}
    with pytest.raises(ValueError, match="result digest mismatch"):
        worker._normalize_item(tampered, "china", ["AI", "Pricing", "Research", "Other"])


def test_target_rejects_ai_only_as_a_secondary_category() -> None:
    item = _item(
        "https://example.test/secondary-ai.pdf",
        b"%PDF secondary AI",
        "Pricing models use AI methods.",
    )
    item["source_primary_category"] = "Pricing"
    item["categories"] = [
        {"key": "Pricing", "evidence": ["Pricing models"]},
        {"key": "AI", "evidence": ["AI methods"]},
    ]
    for language in ("zh", "en"):
        item["bilingual_metadata"][language]["category"] = "Pricing"
    _bind_item_enrichment(item)
    with pytest.raises(ValueError, match="primary category must be AI"):
        worker._normalize_item(item, "china", ["AI", "Pricing", "Other"])


@pytest.mark.parametrize(
    ("value", "precision", "evidence"),
    [
        ("2024", "year", "Published 2024"),
        ("2024-12", "month", "Published 2024-12"),
        ("2024-12-31", "day", "Published 2024-12-31"),
    ],
)
def test_target_projects_verified_publication_date_without_losing_precision(
    value: str, precision: str, evidence: str
) -> None:
    markdown = "Pricing models use AI methods. Published 2024-12-31."
    item = _item("https://example.test/publication-date.pdf", b"%PDF date", markdown)
    fact = {
        "semantic": "publication",
        "value": value,
        "precision": precision,
        "evidence": evidence,
        "location": "page 1",
    }
    item["date_facts"]["publication_date"] = fact
    _bind_item_enrichment(item)
    normalized = worker._normalize_item(item, "overseas", ["AI", "Pricing", "Other"])
    assert normalized["published_time"] == value
    assert (
        normalized["serving_metadata"]["hub_enrichment"]["date_facts"]["publication_date"] == fact
    )
    assert normalized["metadata_fingerprint"] == runtime._target_metadata_fingerprint(item)


def test_unknown_publication_date_projects_to_null() -> None:
    item = _item("https://example.test/unknown-date.pdf", b"%PDF no date", "No date found.")
    normalized = worker._normalize_item(item, "overseas", ["AI", "Pricing", "Other"])
    assert normalized["published_time"] is None
    assert normalized["serving_metadata"]["hub_enrichment"]["date_facts"] == item["date_facts"]
    assert normalized["metadata_fingerprint"] == runtime._target_metadata_fingerprint(item)


def test_metadata_only_date_backfill_preserves_legacy_fields_and_skips_chunking(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/legacy-date-backfill.pdf"
    markdown = "Pricing models use AI methods. Published 2024-12."
    item = _item(url, b"%PDF legacy date record", markdown)
    item["date_facts"]["publication_date"] = {
        "semantic": "publication",
        "value": "2024-12",
        "precision": "month",
        "evidence": "Published 2024-12",
        "location": "page 1",
    }
    _bind_item_enrichment(item)
    storage = _FakeStorage(tmp_path)
    legacy_package = {
        **item["bilingual_metadata"]["en"],
        "hub_binding": {"content_version_id": item["content_version_id"], "sha256": "c" * 64},
        "legacy_note": "keep this",
    }
    zh_package = {**legacy_package, "title": "中文标题"}
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "source_site": "cas",
        "markdown_content": markdown,
        "published_time": None,
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "summary": "Legacy top-level summary",
        "keywords": ["legacy"],
        "first_seen": "2025-01-01T00:00:00+00:00",
        "last_seen": "2025-02-01T00:00:00+00:00",
        "bilingual_metadata": {
            "zh": zh_package,
            "en": legacy_package,
            "hub_binding": {"version_id": item["content_version_id"]},
        },
    }
    storage.memberships.add(("ai", url))
    before_first_seen = storage.rows[url]["first_seen"]
    before_last_seen = storage.rows[url]["last_seen"]
    ready: list = []

    result = _apply_payload(tmp_path, storage, "overseas", [item], ready)

    assert result["failures"] == []
    assert result["acknowledgements"][0]["metadata_only"] is True
    assert storage.rows[url]["published_time"] == "2024-12"
    assert storage.rows[url]["summary"] == "Legacy top-level summary"
    assert storage.rows[url]["keywords"] == ["legacy"]
    assert storage.rows[url]["first_seen"] == before_first_seen
    assert storage.rows[url]["last_seen"] == before_last_seen
    saved = storage.rows[url]["bilingual_metadata"]
    assert saved["en"]["hub_binding"] == legacy_package["hub_binding"]
    assert saved["en"]["legacy_note"] == "keep this"
    assert saved["zh"]["hub_binding"] == legacy_package["hub_binding"]
    assert saved["zh"]["title"] == "中文标题"
    assert saved["hub_binding"] == {"version_id": item["content_version_id"]}
    assert (
        saved["hub_enrichment"]["date_facts"]["publication_date"]
        == item["date_facts"]["publication_date"]
    )
    assert ready == [("ai", [])]
    assert storage.blobs == {}


def test_unknown_hub_date_preserves_legacy_target_date_and_updates_categories(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/legacy-unknown-date.pdf"
    markdown = "Pricing models use AI methods."
    item = _item(url, b"%PDF legacy unknown date", markdown)
    storage = _FakeStorage(tmp_path)
    legacy_package = {
        **item["bilingual_metadata"]["en"],
        "hub_binding": {"content_version_id": item["content_version_id"]},
        "legacy_note": "preserve me",
    }
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "source_site": "cas",
        "markdown_content": markdown,
        "published_time": "2024-12",
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "summary": "Keep old summary",
        "keywords": ["legacy"],
        "bilingual_metadata": {"en": legacy_package, "zh": dict(legacy_package)},
    }
    storage.memberships.add(("ai", url))

    result = _apply_payload(tmp_path, storage, "overseas", [item], [])

    assert result["failures"] == []
    assert result["acknowledgements"][0]["metadata_only"] is True
    assert result["acknowledgements"][0]["published_time_status"] == "legacy_preserved_unverified"
    assert storage.rows[url]["published_time"] == "2024-12"
    assert storage.rows[url]["summary"] == "Keep old summary"
    saved = storage.rows[url]["bilingual_metadata"]
    assert saved["en"]["hub_binding"] == legacy_package["hub_binding"]
    assert saved["en"]["legacy_note"] == "preserve me"
    assert saved["hub_enrichment"]["ordered_categories"] == item["categories"]


@pytest.mark.parametrize(
    "source_site",
    [
        "Conference of Consulting Actuaries (CCA)",
        "Actuarial Association of Europe (AAE)",
        "iaa",
    ],
)
@pytest.mark.parametrize("target", ["china", "overseas"])
def test_target_preserves_legacy_and_registry_source_site_values(
    source_site: str, target: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"status": "ok", "percent_used": 70}
    )
    storage = _FakeStorage(tmp_path)
    item = _item(
        f"https://example.test/{target}-{source_site[:3]}.pdf",
        b"%PDF legacy source-site provenance",
        "Pricing models use AI methods.",
    )
    item["source_site"] = source_site
    ready: list = []

    normalized = worker._normalize_item(item, target, ["AI", "Pricing", "Other"])
    assert normalized["source_site"] == source_site
    result = _apply_payload(tmp_path, storage, target, [item], ready)

    assert result["failures"] == []
    assert result["acknowledgements"][0]["source_site"] == source_site
    assert storage.rows[item["url"]]["source_site"] == source_site
    kb_ids = ["ai", "all"] if target == "china" else ["ai"]
    assert worker._existing_is_current(storage, normalized, kb_ids)

    ready.clear()
    repeated = _apply_payload(tmp_path, storage, target, [item], ready)
    assert repeated["failures"] == []
    assert repeated["acknowledgements"][0]["status"] == "already_current"
    assert repeated["acknowledgements"][0]["source_site"] == source_site
    assert ready == []


@pytest.mark.parametrize("source_site", ["", " \t ", 123, ["cas"]])
def test_target_rejects_blank_or_non_string_source_site(source_site) -> None:
    item = _item(
        "https://example.test/invalid-source-site.pdf",
        b"%PDF invalid source-site provenance",
        "Pricing models use AI methods.",
    )
    item["source_site"] = source_site

    with pytest.raises(ValueError, match="source-site provenance is malformed"):
        worker._normalize_item(item, "china", ["AI", "Pricing", "Other"])


def test_target_preserves_legacy_hub_binding_and_rejects_mismatch(tmp_path: Path) -> None:
    raw = b"%PDF-1.7\nlegacy payload binding"
    markdown = "Pricing models use AI methods."
    item = _item("https://example.test/legacy-binding.pdf", raw, markdown)
    item["hub_markdown_sha256"] = hashlib.sha256(
        json.dumps(markdown, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    item["hub_markdown_sha256_kind"] = "json_payload_utf8"

    normalized = worker._normalize_item(item, "china", ["AI", "Pricing", "Other"])
    enrichment = normalized["serving_metadata"]["hub_enrichment"]
    assert normalized["markdown_sha256"] == hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    assert enrichment["hub_markdown_sha256"] == item["hub_markdown_sha256"]
    assert enrichment["hub_markdown_sha256_kind"] == "json_payload_utf8"
    assert normalized["metadata_fingerprint"] == runtime._target_metadata_fingerprint(item)

    storage = _FakeStorage(tmp_path)
    ready: list = []
    saved = _apply_payload(tmp_path, storage, "china", [item], ready)
    assert saved["failures"] == []
    assert saved["acknowledgements"][0]["hub_markdown_sha256_kind"] == "json_payload_utf8"
    assert worker._existing_is_current(storage, normalized, ["ai", "all"])

    tampered = copy.deepcopy(item)
    tampered["hub_markdown_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Hub Markdown binding digest mismatch"):
        worker._normalize_item(tampered, "china", ["AI", "Pricing", "Other"])

    changed_binding = copy.deepcopy(normalized)
    changed_binding["hub_markdown_sha256"] = "f" * 64
    assert not worker._existing_is_current(storage, changed_binding, ["ai", "all"])


class _FakeConnection:
    def __init__(self, storage: "_FakeStorage") -> None:
        self.storage = storage

    def execute(self, statement: str, params: tuple):
        if "SELECT kb_id FROM rag_kb_files" in statement:
            url = params[0]
            return _ChunkSetCursor(
                [(kb_id,) for kb_id, file_url in self.storage.memberships if file_url == url]
            )
        if "SELECT 1 FROM rag_kb_files" in statement:
            return _FakeCursor((params[0], params[1]) in self.storage.memberships)
        if "UPDATE files SET deleted_at = NULL" in statement:
            row = self.storage.rows.get(params[0])
            if row:
                row["deleted_at"] = None
            return None
        if "UPDATE files SET published_time = ? WHERE url = ? AND sha256 = ?" in statement:
            published_time, url, raw_sha = params
            row = self.storage.rows.get(url)
            if row and row.get("sha256") == raw_sha:
                row["published_time"] = published_time
            return None
        if (
            "UPDATE files SET published_time = COALESCE(?, published_time), source_site = ?"
            in statement
        ):
            published_time, source_site, url, raw_sha = params
            row = self.storage.rows.get(url)
            if row and row.get("sha256") == raw_sha:
                if published_time is not None:
                    row["published_time"] = published_time
                row["source_site"] = source_site
            return None
        raise AssertionError(f"unexpected target SQL: {statement}")


class _FakeCursor:
    def __init__(self, exists: bool) -> None:
        self.exists = exists

    def fetchone(self):
        return (1,) if self.exists else None


class _FakeStorage:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.rows: dict[str, dict] = {}
        self.blobs: dict[str, dict] = {}
        self.memberships: set[tuple[str, str]] = set()
        self.fail_markdown_urls: set[str] = set()
        self._conn = _FakeConnection(self)

    @contextmanager
    def transaction(self, **_kwargs):
        snapshot = copy.deepcopy((self.rows, self.blobs, self.memberships))
        try:
            yield
        except Exception:
            self.rows, self.blobs, self.memberships = snapshot
            raise

    def _ready_data_builder_metadata_snapshot(self, _url: str):
        return {}

    def _lock_postgres_key(self, *_args):
        return None

    def _mark_ready_data_builder_metadata_change(self, **_kwargs):
        return None

    def get_blob(self, digest: str):
        return self.blobs.get(digest)

    def upsert_blob(self, digest: str, path: str, size: int, content_type: str):
        self.blobs[digest] = {"canonical_path": path, "bytes": size, "content_type": content_type}

    def upsert_file(
        self,
        url: str,
        digest: str,
        title: str,
        source_site: str,
        source_page_url: str,
        original_filename: str,
        local_path: str,
        size: int,
        content_type: str,
        last_modified: str,
        etag: str,
        published_time: str,
        content_kind: str = "file",
    ):
        prior = self.rows.get(url)
        first_seen = prior.get("first_seen") if prior else "2026-10-25T12:00:00.000001+00:00"
        self.rows[url] = {
            **(prior or {}),
            "url": url,
            "sha256": digest,
            "title": title,
            "source_site": source_site,
            "source_page_url": source_page_url,
            "original_filename": original_filename,
            "local_path": local_path,
            "bytes": size,
            "content_type": content_type,
            "last_modified": last_modified,
            "etag": etag,
            "published_time": published_time,
            "first_seen": first_seen,
            "last_seen": "2026-10-25T12:00:01.000001+00:00",
            "crawl_time": "2026-10-25T12:00:01.000001+00:00",
            "deleted_at": prior.get("deleted_at") if prior else None,
            "content_kind": content_kind,
        }

    def update_file_markdown(self, url: str, markdown: str, _pipeline: str):
        if url in self.fail_markdown_urls:
            self.fail_markdown_urls.remove(url)
            return False, "temporary markdown write failure"
        self.rows[url]["markdown_content"] = markdown
        return True, None

    def upsert_catalog_item(self, item: dict, **_kwargs):
        self.rows[item["url"]].update(
            {
                "category": item["category"],
                "summary": item["summary"],
                "keywords": item["keywords"],
                "bilingual_metadata": item["bilingual_metadata"],
                "catalog_status": "ok",
            }
        )

    def get_file_with_catalog(self, url: str):
        return self.rows.get(url)

    def mark_file_deleted(self, url: str, deleted_time: str):
        row = self.rows.get(url)
        if row:
            row["deleted_at"] = deleted_time
            row["catalog_status"] = "deleted"

    def bind_chunk_set_to_kb(self, *, kb_id: str, file_url: str, chunk_set_id: str, **_kwargs):
        self.memberships.add((kb_id, file_url))
        return {
            "kb_id": kb_id,
            "file_url": file_url,
            "chunk_set_id": chunk_set_id,
            "binding_mode": "follow_latest",
        }

    def close(self):
        return None


class _FakeKB:
    def __init__(self, kb_id: str, dimension: int) -> None:
        self.kb_id = kb_id
        self.embedding_dimension = dimension
        self.embedding_identity_key = f"server:{kb_id}:{dimension}"
        self.embedding_provider = "qwen" if dimension == 1024 else "openai"
        self.embedding_model = "qwen-embedding" if dimension == 1024 else "text-embedding-3-large"
        self.chunk_profile_id = f"profile:{kb_id}"


class _FakeManager:
    def __init__(self, storage: _FakeStorage, target: str) -> None:
        self.storage = storage
        dimension = 1024 if target == "china" else 3072
        ids = ("ai", "all") if target == "china" else ("ai",)
        self.kbs = {kb_id: _FakeKB(kb_id, dimension) for kb_id in ids}
        self.remove_calls: list[tuple[str, str]] = []

    def get_kb(self, kb_id: str):
        return self.kbs.get(kb_id)

    def add_files_to_kb(self, kb_id: str, files: list[str]):
        added = 0
        for url in files:
            key = (kb_id, url)
            if key not in self.storage.memberships:
                self.storage.memberships.add(key)
                added += 1
        return {"added_count": added, "skipped_count": len(files) - added}

    def remove_files_from_kb(self, kb_id: str, files: list[str]):
        removed = 0
        for url in files:
            self.remove_calls.append((kb_id, url))
            if (kb_id, url) in self.storage.memberships:
                self.storage.memberships.remove((kb_id, url))
                removed += 1
        return removed


class _FakeRuntime:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    def _load_site_config(self):
        return {}

    def _resolve_db_path(self, _config):
        return "read-only-profile-test"


def _apply_payload(
    tmp_path: Path,
    storage: _FakeStorage,
    target: str,
    items: list[dict],
    ready_rows: list,
    *,
    ready_pending: bool = False,
    ready_builder=None,
) -> dict:
    def successful_ready_builder(runtime_instance, _storage, kb, urls):
        ready_rows.append((kb.kb_id, list(urls)))
        worker._clear_pending_ready_for_kb(Path(runtime_instance.data_root), kb.kb_id, urls)
        return {"kb_id": kb.kb_id}

    return worker.apply_batch(
        {
            "schema_version": 1,
            "target": target,
            "items": items,
            "ready_pending": ready_pending,
            "approved_categories": ["AI", "Pricing", "Other"],
        },
        runtime_factory=lambda: _FakeRuntime(tmp_path),
        storage_factory=lambda *_args, **_kwargs: storage,
        manager_factory=lambda _storage: _FakeManager(storage, target),
        ready_builder=ready_builder or successful_ready_builder,
    )


def test_worker_startup_exception_json_retains_payload_target(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(worker.sys, "stdin", StringIO('{"target":"china"}'))
    monkeypatch.setattr(worker.sys, "stdout", output)
    monkeypatch.setattr(
        worker,
        "apply_batch",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    assert worker.main() == 2
    reply = json.loads(output.getvalue())
    assert reply["target"] == "china"
    assert reply["error"] == "database unavailable"


def test_worker_main_accepts_valid_source_batch_above_interpretation_stream_cap(
    monkeypatch,
):
    item = _item(
        "https://example.test/large-source.pdf",
        b"x" * 409_609,
        "Pricing models use AI methods.",
    )
    payload = {
        "schema_version": 1,
        "target": "china",
        "items": [item],
        "approved_categories": ["AI", "Pricing", "Other"],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert len(item["raw_bytes_b64"]) > worker.MAX_INTERPRETATION_EVENT_BYTES
    assert len(encoded.encode("utf-8")) > worker.MAX_INTERPRETATION_EVENT_BYTES
    assert worker.MAX_ARTICLE_BYTES >= 409_609
    worker._normalize_item(item, "china", payload["approved_categories"])

    received = []
    monkeypatch.setattr(worker.sys, "stdin", StringIO(encoded + "\n"))
    monkeypatch.setattr(worker.sys, "stdout", StringIO())
    monkeypatch.setattr(
        worker,
        "apply_batch",
        lambda value: received.append(value)
        or {"target": "china", "failures": [], "ready_status": "succeeded"},
    )

    assert worker.main() == 0
    assert received == [payload]


def test_worker_main_keeps_interpretation_stream_request_cap(monkeypatch):
    payload = {
        "schema_version": 1,
        "operation": "run_article_interpretation_stream",
        "target": "china",
        "padding": "x" * worker.MAX_INTERPRETATION_EVENT_BYTES,
    }
    encoded = json.dumps(payload, separators=(",", ":"))
    output = StringIO()
    monkeypatch.setattr(worker.sys, "stdin", StringIO(encoded + "\n"))
    monkeypatch.setattr(worker.sys, "stdout", output)
    monkeypatch.setattr(
        worker,
        "_run_article_interpretation_stream_operation",
        lambda _payload: pytest.fail("oversized stream request must be rejected first"),
    )

    assert worker.main() == 2
    assert json.loads(output.getvalue()) == {
        "schema_version": 1,
        "event": "failure",
        "code": "stream_request_too_large",
    }


@pytest.mark.parametrize(
    ("task_id", "status", "error", "log_file"),
    [
        ("rag-20261026-001", "error", "chunk manifest unavailable", "/logs/001.log"),
        ("rag-20261026-002", "stopped", "embedding worker stopped", "/logs/002.log"),
    ],
)
def test_failed_native_task_diagnostic_survives_same_kb_ready_retries(
    task_id: str, status: str, error: str, log_file: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"status": "ok", "percent_used": 70}
    )
    storage = _FakeStorage(tmp_path)
    item = _item(
        "https://example.test/native-task-diagnostic.pdf",
        b"%PDF native task diagnostic",
        "Pricing models use AI methods.",
    )
    ready_rows: list = []
    task_record = {
        "id": task_id,
        "type": "chunk_generation" if status == "error" else "rag_indexing",
        "status": status,
        "errors": [error],
        "error_details": {"kb_id": "ai", "error_code": f"{task_id}-code"},
        "log_file": log_file,
    }

    def fail_with_native_task_record(runtime_instance, _storage, _kb, _urls):
        runtime_instance._pipeline_task_status = lambda requested_id: (
            status if requested_id == task_id else None
        )
        runtime_instance._pipeline_task_result = lambda requested_id: (
            dict(task_record) if requested_id == task_id else None
        )
        worker._wait_task(runtime_instance, task_id)

    reply = _apply_payload(
        tmp_path,
        storage,
        "overseas",
        [item],
        ready_rows,
        ready_builder=fail_with_native_task_record,
    )
    assert reply["ready_status"] == "failed"
    assert reply["ready_error"] == {"ai": worker._NativeTaskFailure(task_record).__str__()}
    assert len(reply["ready_evidence"]["ai"]) == 1
    saved_task = json.loads(reply["ready_evidence"]["ai"][0])
    assert saved_task == task_record

    # A second task on the same KB must report its own native ID and log path.
    second_record = {
        **task_record,
        "id": f"{task_id}-retry",
        "errors": [f"different {error}"],
        "log_file": f"{log_file}.retry",
    }

    def fail_with_second_native_task(runtime_instance, _storage, _kb, _urls):
        runtime_instance._pipeline_task_status = lambda requested_id: (
            second_record["status"] if requested_id == second_record["id"] else None
        )
        runtime_instance._pipeline_task_result = lambda requested_id: (
            dict(second_record) if requested_id == second_record["id"] else None
        )
        worker._wait_task(runtime_instance, second_record["id"])

    retry = _apply_payload(
        tmp_path,
        storage,
        "overseas",
        [],
        ready_rows,
        ready_pending=True,
        ready_builder=fail_with_second_native_task,
    )
    first_ready_error = reply["ready_error"]
    retry_ready_error = retry["ready_error"]
    assert isinstance(first_ready_error, dict)
    assert isinstance(retry_ready_error, dict)
    retry_task = json.loads(retry["ready_evidence"]["ai"][0])
    assert retry_task == second_record
    assert retry_ready_error.get("ai") != first_ready_error.get("ai")


def test_additive_reactivation_preserves_retired_history_and_unrelated_rows(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"status": "ok", "percent_used": 70}
    )
    storage = _FakeStorage(tmp_path)
    url = "https://example.test/retired-ai-url.pdf"
    storage.rows[url] = {
        "url": url,
        "sha256": "c" * 64,
        "first_seen": "2025-02-01T00:00:00+00:00",
        "crawl_time": "2025-03-01T00:00:00+00:00",
        "last_seen": "2025-03-01T00:00:00+00:00",
        "deleted_at": "2026-01-01T00:00:00+00:00",
        "category": "Other",
        "catalog_status": "ok",
    }
    unrelated = "https://example.test/unrelated-retired.pdf"
    storage.rows[unrelated] = {
        "url": unrelated,
        "sha256": "d" * 64,
        "deleted_at": "2025-01-01T00:00:00+00:00",
        "first_seen": "2024-01-01T00:00:00+00:00",
    }
    before_unrelated = copy.deepcopy(storage.rows[unrelated])
    item = _item(url, b"%PDF-1.7\nselected URL bytes", "Pricing models use AI methods.")
    ready: list = []

    result = _apply_payload(tmp_path, storage, "china", [item], ready)
    assert result["failures"] == []
    assert result["acknowledgements"][0]["status"] == "written"
    assert result["acknowledgements"][0]["source_site"] == "cas"
    assert set(kb for kb, _ in ready) == {"ai", "all"}
    restored = storage.rows[url]
    assert restored["deleted_at"] is None
    assert restored["first_seen"] == "2025-02-01T00:00:00+00:00"
    assert storage.rows[unrelated] == before_unrelated
    assert worker._existing_is_current(
        storage, worker._normalize_item(item, "china", ["AI", "Pricing", "Other"]), ["ai", "all"]
    )

    ready.clear()
    repeated = _apply_payload(tmp_path, storage, "china", [item], ready)
    assert repeated["acknowledgements"][0]["status"] == "already_current"
    assert repeated["acknowledgements"][0]["source_site"] == "cas"
    assert ready == []


@pytest.mark.parametrize(
    ("field", "updated_value"),
    [
        ("date_review_status", "candidate_limit_gap"),
        ("date_review_reason", "date evidence requires review"),
        (
            "date_review_unresolved",
            [{"field": "revision_date", "evidence": "revision pending"}],
        ),
    ],
)
def test_target_updates_when_any_projected_enrichment_field_changes(
    field: str, updated_value, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"status": "ok", "percent_used": 70}
    )
    storage = _FakeStorage(tmp_path)
    item = _item(
        "https://example.test/date-review.pdf",
        b"%PDF date review metadata",
        "Pricing models use AI methods.",
    )
    ready: list = []
    inserted = _apply_payload(tmp_path, storage, "overseas", [item], ready)
    assert inserted["acknowledgements"][0]["status"] == "written"

    revised = copy.deepcopy(item)
    revised[field] = updated_value
    _bind_item_enrichment(revised)
    current_item = worker._normalize_item(item, "overseas", ["AI", "Pricing", "Other"])
    revised_item = worker._normalize_item(revised, "overseas", ["AI", "Pricing", "Other"])
    assert revised_item["metadata_fingerprint"] != current_item["metadata_fingerprint"]
    assert runtime._target_metadata_fingerprint(revised) == revised_item["metadata_fingerprint"]
    assert not worker._existing_is_current(storage, revised_item, ["ai"])

    updated = _apply_payload(tmp_path, storage, "overseas", [revised], ready)
    assert updated["failures"] == []
    assert updated["acknowledgements"][0]["status"] == "written"
    saved_enrichment = storage.rows[item["url"]]["bilingual_metadata"]["hub_enrichment"]
    assert saved_enrichment[field] == updated_value
    assert worker._existing_is_current(storage, revised_item, ["ai"])


def test_unknown_historical_source_is_not_fabricated_or_overwritten(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"status": "ok", "percent_used": 70}
    )
    storage = _FakeStorage(tmp_path)
    url = "https://example.test/unknown-source.pdf"
    item = _item(url, b"%PDF unknown source", "Pricing models use AI methods.")
    item["source_site"] = None
    normalized = worker._normalize_item(item, "overseas", ["AI", "Pricing", "Other"])
    assert normalized["source_site"] is None

    ready: list = []
    result = _apply_payload(tmp_path, storage, "overseas", [item], ready)
    assert result["failures"] == []
    assert result["acknowledgements"][0]["source_site"] is None
    assert storage.rows[url]["source_site"] is None
    ready.clear()
    repeated = _apply_payload(tmp_path, storage, "overseas", [item], ready)
    assert repeated["acknowledgements"][0]["status"] == "already_current"
    assert repeated["acknowledgements"][0]["source_site"] is None
    assert ready == []

    retained_url = "https://example.test/retained-source.pdf"
    retained = _item(
        retained_url, b"%PDF retained source", "Pricing models use AI methods.", version=18
    )
    retained["source_site"] = None
    storage.rows[retained_url] = {
        "url": retained_url,
        "sha256": "c" * 64,
        "source_site": "cas",
        "deleted_at": "2026-01-01T00:00:00+00:00",
    }
    result = _apply_payload(tmp_path, storage, "overseas", [retained], ready)
    assert result["failures"] == []
    assert result["acknowledgements"][0]["source_site"] == "cas"
    assert storage.rows[retained_url]["source_site"] == "cas"


def test_target_item_failure_isolated_and_retry_keeps_successful_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"status": "ok", "percent_used": 70}
    )
    storage = _FakeStorage(tmp_path)
    first = _item(
        "https://example.test/first.pdf",
        b"%PDF first",
        "Pricing models and AI methods.",
        version=17,
    )
    second = _item(
        "https://example.test/second.pdf",
        b"%PDF second",
        "Pricing models and AI methods.",
        version=18,
    )
    storage.fail_markdown_urls.add(second["url"])
    ready: list = []

    partial = _apply_payload(tmp_path, storage, "overseas", [first, second], ready)
    assert [item["url"] for item in partial["acknowledgements"]] == [first["url"]]
    assert [item["url"] for item in partial["failures"]] == [second["url"]]
    assert storage.rows[first["url"]]["markdown_content"] == first["markdown"]
    assert second["url"] not in storage.rows
    assert [kb for kb, _ in ready] == ["ai"]

    ready.clear()
    retried = _apply_payload(tmp_path, storage, "overseas", [second], ready)
    assert retried["failures"] == []
    assert retried["acknowledgements"][0]["status"] == "written"
    assert storage.rows[first["url"]]["markdown_content"] == first["markdown"]
    assert storage.rows[second["url"]]["markdown_content"] == second["markdown"]


class _TaskRuntime:
    def __init__(
        self,
        data_root: Path,
        *,
        fail_chunk: bool = False,
        fail_embedding: bool = False,
        fail_ready: bool = False,
        chunk_sets: list[dict] | None = None,
    ) -> None:
        self.data_root = data_root
        self.fail_chunk = fail_chunk
        self.fail_embedding = fail_embedding
        self.fail_ready = fail_ready
        self.task_types: list[str] = []
        self.embedding_payloads: list[dict] = []
        self.chunk_sets = chunk_sets

    def start_background_task(self, task_type: str, payload: dict, **_kwargs):
        self.task_types.append(task_type)
        if task_type == "chunk_generation":
            if self.chunk_sets is None:
                self.chunk_sets = [
                    {
                        "file_url": file["file_url"],
                        "markdown_hash": file["markdown_hash"],
                        "profile_id": payload["profile_id"],
                        "profile_config_hash": "profile-config",
                        "chunk_set_id": f"set-{index}",
                        "chunk_count": 1,
                        "reused_existing": False,
                    }
                    for index, file in enumerate(payload["files"], start=1)
                ]
            return "chunk"
        if task_type == "embedding_generation":
            self.embedding_payloads.append(payload)
            return "embedding"
        if task_type == "rag_indexing":
            return "index"
        raise AssertionError(task_type)

    def _pipeline_task_status(self, task_id: str):
        return (
            "error"
            if (task_id == "chunk" and self.fail_chunk)
            or (task_id == "embedding" and self.fail_embedding)
            else "completed"
        )

    def _pipeline_task_result(self, task_id: str):
        if task_id == "chunk":
            return {
                "id": task_id,
                "type": "chunk_generation",
                "status": "error" if self.fail_chunk else "completed",
                "errors": ["chunk generation failed"] if self.fail_chunk else [],
                "result": {"contract_version": 1, "chunk_sets": self.chunk_sets},
            }
        if task_id == "embedding":
            return {
                "id": task_id,
                "type": "embedding_generation",
                "status": "error" if self.fail_embedding else "completed",
                "errors": ["Embedding generation failed."] if self.fail_embedding else [],
                "log_file": "/logs/embedding.log",
                "result": {},
            }
        if task_id == "index":
            return {"result": {"index_version_id": "index-1"}, "ready_data_task_id": "ready"}
        if task_id == "ready":
            publish_status = "failed" if self.fail_ready else "published"
            return {"result": {"publish_status": publish_status}}
        return {"result": {}}


def test_chunk_stage_failure_resumes_but_ready_only_failure_skips_chunks(
    tmp_path: Path, monkeypatch
) -> None:
    from ai_actuarial.rag import kb_index

    monkeypatch.setattr(
        kb_index,
        "resolve_kb_bound_chunks",
        lambda *_args, **_kwargs: {"binding_snapshot_fingerprint": "bindings"},
    )
    url = "https://example.test/recovery.pdf"
    markdown = "Pricing models use AI methods."
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {"url": url, "markdown_content": markdown}
    kb = _FakeKB("ai", 3072)
    worker._add_pending_ready(tmp_path, "overseas", ["ai"], [url])

    first = _TaskRuntime(tmp_path, fail_chunk=True)
    with pytest.raises(RuntimeError, match="native chunk_generation task ended with error"):
        worker._refresh_ready(first, storage, kb, [url])
    assert worker._read_pending_ready(tmp_path, "overseas") == {"ai": [url]}

    second = _TaskRuntime(tmp_path, fail_ready=True)
    with pytest.raises(RuntimeError, match="Ready Data build did not publish"):
        worker._refresh_ready(second, storage, kb, [url])
    assert second.task_types == ["chunk_generation", "embedding_generation", "rag_indexing"]
    assert second.embedding_payloads == [
        {
            "chunk_set_ids": ["set-1"],
            "embedding_identity_key": kb.embedding_identity_key,
        }
    ]
    assert worker._read_pending_ready(tmp_path, "overseas") == {}

    ready_only = _TaskRuntime(tmp_path)
    result = worker._refresh_ready(ready_only, storage, kb, [])
    assert ready_only.task_types == ["rag_indexing"]
    assert result["index_version_id"] == "index-1"


@pytest.mark.parametrize(
    ("defect", "expected_error"),
    [
        ("missing", "exactly one current chunk set"),
        ("wrong_url", "exactly one current chunk set"),
        ("duplicate_url", "exactly one current chunk set"),
        ("wrong_profile", "different KB profile"),
        ("blank_id", "distinct nonblank chunk-set IDs"),
    ],
)
def test_refresh_ready_rejects_invalid_current_chunk_task_results(
    defect: str, expected_error: str, tmp_path: Path, monkeypatch
) -> None:
    from ai_actuarial.rag import kb_index

    monkeypatch.setattr(
        kb_index,
        "resolve_kb_bound_chunks",
        lambda *_args, **_kwargs: {"binding_snapshot_fingerprint": "bindings"},
    )
    url = "https://example.test/chunk-result-contract.pdf"
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {"url": url, "markdown_content": "Pricing models use AI methods."}
    valid = {
        "file_url": url,
        "markdown_hash": hashlib.sha256(
            storage.rows[url]["markdown_content"].encode("utf-8")
        ).hexdigest(),
        "profile_id": "profile:ai",
        "profile_config_hash": "profile-config",
        "chunk_set_id": "set-1",
        "chunk_count": 1,
        "reused_existing": False,
    }
    rows = {
        "missing": [],
        "wrong_url": [{**valid, "file_url": "https://example.test/other.pdf"}],
        "duplicate_url": [valid, {**valid, "chunk_set_id": "set-2"}],
        "wrong_profile": [{**valid, "profile_id": "profile:other"}],
        "blank_id": [{**valid, "chunk_set_id": "  "}],
    }[defect]
    task_runtime = _TaskRuntime(tmp_path, chunk_sets=rows)

    with pytest.raises(RuntimeError, match=expected_error):
        worker._refresh_ready(task_runtime, storage, _FakeKB("ai", 1024), [url])

    assert task_runtime.task_types == ["chunk_generation"]
    assert task_runtime.embedding_payloads == []


def test_embedding_failure_keeps_pending_urls_for_exact_id_restart_retry(
    tmp_path: Path, monkeypatch
) -> None:
    from ai_actuarial.rag import kb_index

    monkeypatch.setattr(
        kb_index,
        "resolve_kb_bound_chunks",
        lambda *_args, **_kwargs: {"binding_snapshot_fingerprint": "bindings"},
    )
    url = "https://example.test/embedding-restart.pdf"
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {"url": url, "markdown_content": "Pricing models use AI methods."}
    kb = _FakeKB("ai", 3072)
    worker._add_pending_ready(tmp_path, "overseas", ["ai"], [url])

    first = _TaskRuntime(tmp_path, fail_embedding=True)
    with pytest.raises(RuntimeError, match="native embedding_generation task ended with error"):
        worker._refresh_ready(first, storage, kb, [url])
    assert first.embedding_payloads == [
        {"chunk_set_ids": ["set-1"], "embedding_identity_key": kb.embedding_identity_key}
    ]
    assert worker._read_pending_ready(tmp_path, "overseas") == {"ai": [url]}

    retry = _TaskRuntime(tmp_path)
    result = worker._refresh_ready(retry, storage, kb, [url])
    assert retry.task_types == ["chunk_generation", "embedding_generation", "rag_indexing"]
    assert retry.embedding_payloads == first.embedding_payloads
    assert result["index_version_id"] == "index-1"
    assert worker._read_pending_ready(tmp_path, "overseas") == {}


def _cleanup_record(url: str, raw: bytes, *, version_id: int | None = 17) -> dict:
    raw_sha = hashlib.sha256(raw).hexdigest()
    evidence = {
        "url": url,
        "raw_sha256": raw_sha,
        "primary_category": "Pricing",
        "categories": [
            {"key": "Pricing", "evidence": ["Pricing models"]},
            {"key": "AI", "evidence": ["AI methods"]},
        ],
    }
    if version_id is not None:
        evidence["content_version_id"] = version_id
    return {"url": url, "raw_sha256": raw_sha, "hub_evidence": evidence}


def test_cleanup_accepts_only_empty_legacy_non_ai_primary_evidence() -> None:
    record = _cleanup_record("https://example.test/legacy-cleanup.pdf", b"cleanup source")
    record["hub_evidence"]["primary_category"] = "Other"
    record["hub_evidence"]["categories"] = [
        {"key": "Other", "evidence": []},
        {"key": "Pricing", "evidence": ["Pricing models"]},
        {"key": "Research", "evidence": ["AI methods"]},
        {"key": "AI", "evidence": ["AI methods"]},
    ]
    normalized = worker._normalize_cleanup_records([record], ["AI", "Pricing", "Research", "Other"])
    assert normalized[0]["categories"] == record["hub_evidence"]["categories"]

    secondary_empty = copy.deepcopy(record)
    secondary_empty["hub_evidence"]["categories"][1]["evidence"] = []
    with pytest.raises(ValueError, match="only legacy primary evidence may be empty"):
        worker._normalize_cleanup_records([secondary_empty], ["AI", "Pricing", "Research", "Other"])

    missing_version = copy.deepcopy(record)
    del missing_version["hub_evidence"]["content_version_id"]
    with pytest.raises(ValueError, match="content_version_id"):
        worker._normalize_cleanup_records([missing_version], ["AI", "Pricing", "Research", "Other"])


def test_cleanup_dry_run_uses_readonly_profile_reader_without_manager(
    tmp_path: Path, monkeypatch
) -> None:
    url = "https://example.test/readonly-cleanup-dryrun.pdf"
    record = _cleanup_record(url, b"readonly cleanup source")
    record["hub_evidence"]["categories"][0]["evidence"] = []
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
        "category": "AI",
    }
    storage.memberships.add(("ai", url))
    monkeypatch.setattr(worker, "_read_target_profiles", lambda *_args: {"ai": {}})

    result = worker.apply_cleanup(
        {
            "schema_version": 1,
            "target": "overseas",
            "dry_run": True,
            "records": [record],
            "approved_categories": ["AI", "Pricing", "Other"],
        },
        runtime_factory=lambda: _FakeRuntime(tmp_path),
        storage_factory=lambda *_args, **_kwargs: storage,
    )

    assert result["records"][0]["target_status"] == "present"
    assert result["records"][0]["knowledge_base_memberships"] == ["ai"]
    assert storage.rows[url]["deleted_at"] is None
    assert storage.memberships == {("ai", url)}


def _run_cleanup(
    tmp_path: Path,
    storage: _FakeStorage,
    target: str,
    records: list[dict],
    *,
    dry_run: bool,
    ready_builder=None,
):
    managers = []

    def manager_factory(value):
        manager = _FakeManager(value, target)
        managers.append(manager)
        return manager

    result = worker.apply_cleanup(
        {
            "schema_version": 1,
            "target": target,
            "dry_run": dry_run,
            "records": records,
            "approved_categories": ["AI", "Pricing", "Other"],
        },
        runtime_factory=lambda: _FakeRuntime(tmp_path),
        storage_factory=lambda *_args, **_kwargs: storage,
        manager_factory=manager_factory,
        ready_builder=ready_builder,
    )
    return result, managers


def _metadata_backfill_record(item: dict, expected_published_time: str | None) -> dict:
    record = {
        key: item.get(key)
        for key in (
            "url",
            "raw_sha256",
            "content_version_id",
            "markdown_text_variant_id",
            "markdown_sha256",
            "hub_markdown_sha256",
            "hub_markdown_sha256_kind",
            "source_primary_category",
            "categories",
            "date_facts",
            "date_review_status",
            "date_review_reason",
            "date_review_unresolved",
            "source_signature",
            "result_sha256",
        )
    } | {"expected_published_time": expected_published_time}
    record["result_sha256"] = worker._hash(
        worker._canonical_json(
            {
                key: record.get(key)
                for key in (
                    "categories",
                    "date_facts",
                    "date_review_status",
                    "date_review_reason",
                    "date_review_unresolved",
                )
            }
        ).encode("utf-8")
    )
    return record


def test_metadata_backfill_preserves_four_ordered_categories_with_empty_legacy_primary() -> None:
    item = _item(
        "https://example.test/legacy-metadata.pdf",
        b"legacy metadata bytes",
        "Pricing research uses AI methods.",
    )
    item["categories"] = [
        {"key": "AI", "evidence": []},
        {"key": "Pricing", "evidence": ["Pricing research"]},
        {"key": "Research", "evidence": ["AI methods"]},
        {"key": "Other", "evidence": ["Pricing research uses AI methods."]},
    ]
    item["date_facts"]["publication_date"] = {
        "semantic": "publication",
        "value": "2024-12",
        "precision": "month",
        "evidence": "Published 2024-12",
        "location": "page 2",
    }
    record = _metadata_backfill_record(item, None)
    normalized = worker._normalize_metadata_records(
        [record], ["AI", "Pricing", "Research", "Other"]
    )
    assert normalized[0]["categories"] == item["categories"]
    assert normalized[0]["date_facts"]["publication_date"]["semantic"] == "publication"
    assert worker._publication_date_value(normalized[0]["date_facts"]) == "2024-12"

    secondary_empty = copy.deepcopy(record)
    secondary_empty["categories"][1]["evidence"] = []
    with pytest.raises(ValueError, match="only legacy primary evidence may be empty"):
        worker._normalize_metadata_records(
            [secondary_empty], ["AI", "Pricing", "Research", "Other"]
        )

    changed_annotation = copy.deepcopy(record)
    changed_annotation["categories"][1]["evidence"] = ["different quote"]
    with pytest.raises(ValueError, match="Hub result digest"):
        worker._normalize_metadata_records(
            [changed_annotation], ["AI", "Pricing", "Research", "Other"]
        )


def test_metadata_dry_run_uses_readonly_profile_reader_without_manager(
    tmp_path: Path, monkeypatch
) -> None:
    url = "https://example.test/readonly-metadata-dryrun.pdf"
    markdown = "Pricing models use AI methods."
    item = _item(url, b"readonly metadata source", markdown)
    item["categories"][0]["evidence"] = []
    record = _metadata_backfill_record(item, None)
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "local_path": "cas/existing",
        "markdown_content": markdown,
        "published_time": None,
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "bilingual_metadata": item["bilingual_metadata"],
    }
    storage.memberships.add(("ai", url))
    monkeypatch.setattr(worker, "_read_target_profiles", lambda *_args: {"ai": {}})

    result = worker.apply_metadata_backfill(
        {
            "schema_version": 1,
            "target": "overseas",
            "dry_run": True,
            "records": [record],
            "approved_categories": ["AI", "Pricing", "Other"],
        },
        runtime_factory=lambda: _FakeRuntime(tmp_path),
        storage_factory=lambda *_args, **_kwargs: storage,
    )

    assert result["records"][0]["target_status"] == "would_update"
    assert result["records"][0]["url"] == url
    assert storage.rows[url]["bilingual_metadata"] == item["bilingual_metadata"]


def _run_metadata_backfill(
    tmp_path: Path,
    storage: _FakeStorage,
    target: str,
    records: list[dict],
    *,
    dry_run: bool,
):
    managers = []

    def manager_factory(value):
        manager = _FakeManager(value, target)
        managers.append(manager)
        return manager

    result = worker.apply_metadata_backfill(
        {
            "schema_version": 1,
            "target": target,
            "dry_run": dry_run,
            "records": records,
            "approved_categories": ["AI", "Pricing", "Other"],
        },
        runtime_factory=lambda: _FakeRuntime(tmp_path),
        storage_factory=lambda *_args, **_kwargs: storage,
        manager_factory=manager_factory,
    )
    return result, managers


def test_metadata_backfill_is_exact_metadata_only_and_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/existing-metadata-backfill.pdf"
    markdown = "Pricing models use AI methods. Published 2024-12."
    item = _item(url, b"source bytes stay on target", markdown)
    item["categories"][0]["evidence"] = []
    item["date_facts"]["publication_date"] = {
        "semantic": "publication",
        "value": "2024-12",
        "precision": "month",
        "evidence": "Published 2024-12",
        "location": "page 1",
    }
    record = _metadata_backfill_record(item, "2023-01")
    storage = _FakeStorage(tmp_path)
    language_package = {
        **item["bilingual_metadata"]["en"],
        "hub_binding": {"version_id": item["content_version_id"], "sha256": "c" * 64},
        "legacy_note": "preserve all language fields",
    }
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "local_path": "cas/sha256/existing",
        "markdown_content": markdown,
        "published_time": "2023-01",
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "summary": "Keep old summary",
        "keywords": ["legacy"],
        "last_seen": "2026-10-01T00:00:00+00:00",
        "bilingual_metadata": {
            "en": language_package,
            "zh": {**language_package, "title": "旧标题"},
            "hub_binding": {"version_id": item["content_version_id"]},
        },
    }
    storage.memberships.update({("ai", url)})
    before_metadata = copy.deepcopy(storage.rows[url]["bilingual_metadata"])
    before_local_path = storage.rows[url]["local_path"]
    before_last_seen = storage.rows[url]["last_seen"]

    preview, _ = _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=True)
    assert preview["records"][0]["target_status"] == "would_update"
    assert preview["records"][0]["published_time_status"] == "verified_source_date"
    assert storage.rows[url]["bilingual_metadata"] == before_metadata
    assert worker._read_pending_index_refresh(tmp_path, "overseas") == []

    result, _ = _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=False)
    assert result["failures"] == []
    assert result["ready_status"] == "deferred"
    assert result["records"][0]["target_status"] == "updated"
    assert result["records"][0]["published_time_status"] == "verified_source_date"
    assert result["pending_index_refresh"] == ["ai"]
    assert storage.rows[url]["published_time"] == "2024-12"
    assert storage.rows[url]["local_path"] == before_local_path
    assert storage.rows[url]["last_seen"] == before_last_seen
    assert storage.blobs == {}
    saved = storage.rows[url]["bilingual_metadata"]
    assert saved["en"] == before_metadata["en"]
    assert saved["zh"] == before_metadata["zh"]
    assert saved["hub_binding"] == before_metadata["hub_binding"]
    assert saved["hub_enrichment"]["ordered_categories"] == item["categories"]
    assert saved["hub_enrichment"]["date_facts"] == item["date_facts"]

    replay, _ = _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=False)
    assert replay["failures"] == []
    assert replay["records"][0]["target_status"] == "already_current"
    assert replay["pending_index_refresh"] == ["ai"]
    assert storage.rows[url]["published_time"] == "2024-12"

    cleanup_url = "https://example.test/non-ai-first-cleanup-after-backfill.pdf"
    cleanup_raw = b"unrelated exact removal bytes"
    cleanup_record = _cleanup_record(cleanup_url, cleanup_raw)
    storage.rows[cleanup_url] = {
        "url": cleanup_url,
        "sha256": cleanup_record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
        "category": "AI",
    }
    storage.memberships.add(("ai", cleanup_url))
    ready_calls = []
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    cleanup_result, _ = _run_cleanup(
        tmp_path,
        storage,
        "overseas",
        [cleanup_record],
        dry_run=False,
        ready_builder=lambda _runtime, _storage, kb, urls: ready_calls.append(
            (kb.kb_id, list(urls))
        )
        or {"index_version_id": "index-after-backfill"},
    )
    assert cleanup_result["failures"] == [], cleanup_result["failures"]
    assert cleanup_result["cleanup_status"] == "succeeded", cleanup_result
    assert cleanup_result["ready_status"] == "succeeded"
    assert ready_calls == [("ai", [])]
    assert worker._read_pending_index_refresh(tmp_path, "overseas") == []


def test_unknown_metadata_backfill_preserves_unverified_target_date(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/unknown-date-backfill.pdf"
    markdown = "Pricing models use AI methods."
    item = _item(url, b"target-only bytes", markdown)
    record = _metadata_backfill_record(item, "2024-12")
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "markdown_content": markdown,
        "published_time": "2024-12",
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "summary": "Keep summary",
        "keywords": ["legacy"],
        "bilingual_metadata": {"en": {"legacy_note": "keep"}, "zh": {"legacy_note": "保留"}},
    }
    storage.memberships.add(("ai", url))

    result, _ = _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=False)

    assert result["failures"] == []
    assert result["records"][0]["published_time_status"] == "legacy_preserved_unverified"
    assert storage.rows[url]["published_time"] == "2024-12"
    assert storage.rows[url]["bilingual_metadata"]["en"] == {"legacy_note": "keep"}
    assert storage.rows[url]["bilingual_metadata"]["zh"] == {"legacy_note": "保留"}


def test_metadata_backfill_rejects_unbound_markdown_before_any_write(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/metadata-mismatch.pdf"
    markdown = "Pricing models use AI methods."
    item = _item(url, b"existing bytes", markdown)
    record = _metadata_backfill_record(item, None)
    record["markdown_sha256"] = "f" * 64
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "markdown_content": markdown,
        "published_time": None,
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "bilingual_metadata": {"en": {"legacy": True}, "zh": {"legacy": True}},
    }
    storage.memberships.add(("ai", url))
    before = copy.deepcopy(storage.rows[url])

    with pytest.raises(ValueError, match="target Markdown binding mismatch"):
        _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=False)
    assert storage.rows[url] == before
    assert worker._read_pending_index_refresh(tmp_path, "overseas") == []


def test_metadata_backfill_capacity_gate_leaves_exact_target_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity,
        "capacity_status",
        lambda **_kwargs: {"blocked": True, "used_percent": 80.1},
    )
    url = "https://example.test/metadata-capacity-blocked.pdf"
    markdown = "Pricing models use AI methods."
    item = _item(url, b"existing bytes", markdown)
    record = _metadata_backfill_record(item, "2023-01")
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "markdown_content": markdown,
        "published_time": "2023-01",
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "summary": "Keep summary",
        "keywords": ["legacy"],
        "bilingual_metadata": {"en": {"legacy": True}, "zh": {"legacy": True}},
    }
    storage.memberships.add(("ai", url))
    before = copy.deepcopy(storage.rows[url])

    result, _ = _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=False)

    assert result["backfill_status"] == "not_started_capacity_blocked"
    assert result["failures"]
    assert storage.rows[url] == before
    assert worker._read_pending_index_refresh(tmp_path, "overseas") == []


def test_cleanup_dry_run_is_exact_read_only_and_reports_pending_memberships(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/non-ai-primary.pdf"
    raw = b"verified bytes for cleanup"
    record = _cleanup_record(url, raw)
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
        "category": "AI",
    }
    storage.memberships.update({("ai", url), ("all", url)})
    worker._add_pending_ready(tmp_path, "china", ["ai", "all"], [url])
    ready: list = []

    result, managers = _run_cleanup(
        tmp_path,
        storage,
        "china",
        [record],
        dry_run=True,
        ready_builder=lambda *_args: ready.append("unexpected"),
    )

    assert result["dry_run"] is True
    assert result["records"][0]["target_status"] == "present"
    assert set(result["records"][0]["knowledge_base_memberships"]) == {"ai", "all"}
    assert storage.rows[url]["deleted_at"] is None
    assert storage.memberships == {("ai", url), ("all", url)}
    assert worker._read_pending_ready(tmp_path, "china") == {"ai": [url], "all": [url]}
    assert managers[0].remove_calls == []
    assert ready == []


def test_cleanup_retires_exact_record_rebuilds_ready_and_replays_idempotently(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/retire-exact.pdf"
    raw = b"original retained CAS bytes"
    record = _cleanup_record(url, raw)
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
        "local_path": "cas/sha256/original",
    }
    storage.blobs[record["raw_sha256"]] = {"canonical_path": "cas/sha256/original"}
    storage.memberships.update({("ai", url), ("all", url)})
    worker._add_pending_ready(tmp_path, "china", ["ai", "all"], [url])
    ready_calls: list[tuple[str, list[str]]] = []

    def successful_ready(_runtime, _storage, kb, urls):
        ready_calls.append((kb.kb_id, list(urls)))
        return {"index_version_id": f"index-{kb.kb_id}"}

    first, managers = _run_cleanup(
        tmp_path,
        storage,
        "china",
        [record],
        dry_run=False,
        ready_builder=successful_ready,
    )
    assert first["cleanup_status"] == "succeeded"
    assert first["ready_status"] == "succeeded"
    assert storage.rows[url]["deleted_at"]
    assert storage.rows[url]["catalog_status"] == "deleted"
    assert storage.rows[url]["local_path"] == "cas/sha256/original"
    assert storage.blobs[record["raw_sha256"]]["canonical_path"] == "cas/sha256/original"
    assert storage.memberships == set()
    assert set(managers[0].remove_calls) == {("ai", url), ("all", url)}
    assert sorted((kb, tuple(urls)) for kb, urls in ready_calls) == [
        ("ai", ()),
        ("all", ()),
    ]
    assert worker._read_pending_ready(tmp_path, "china") == {}
    assert worker._read_pending_cleanup(tmp_path, "china") == []

    ready_calls.clear()
    repeated, _ = _run_cleanup(
        tmp_path,
        storage,
        "china",
        [record],
        dry_run=False,
        ready_builder=successful_ready,
    )
    assert repeated["records"][0]["target_status"] == "already_retired"
    assert repeated["ready_status"] == "not_required"
    assert ready_calls == []


def test_cleanup_ready_failure_keeps_index_only_retry_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    monkeypatch.setattr(
        capacity, "capacity_status", lambda **_kwargs: {"blocked": False, "used_percent": 70}
    )
    url = "https://example.test/cleanup-ready-retry.pdf"
    raw = b"cleanup ready retry bytes"
    record = _cleanup_record(url, raw)
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
    }
    storage.memberships.add(("ai", url))
    worker._add_pending_ready(tmp_path, "overseas", ["ai"], [url])

    failed, _ = _run_cleanup(
        tmp_path,
        storage,
        "overseas",
        [record],
        dry_run=False,
        ready_builder=lambda *_args: (_ for _ in ()).throw(RuntimeError("index capacity blocked")),
    )
    assert failed["cleanup_status"] == "partial"
    assert failed["ready_status"] == "failed"
    assert failed["resume_with_same_manifest"] is True
    assert failed["pending_cleanup_ready"] == ["ai"]
    assert storage.rows[url]["deleted_at"]
    assert storage.memberships == set()
    assert worker._read_pending_ready(tmp_path, "overseas") == {}

    ready_calls: list[tuple[str, list[str]]] = []
    retried, _ = _run_cleanup(
        tmp_path,
        storage,
        "overseas",
        [record],
        dry_run=False,
        ready_builder=lambda _runtime, _storage, kb, urls: ready_calls.append(
            (kb.kb_id, list(urls))
        )
        or {"index_version_id": "index-retry"},
    )
    assert retried["cleanup_status"] == "succeeded"
    assert retried["ready_status"] == "succeeded"
    assert ready_calls == [("ai", [])]
    assert worker._read_pending_cleanup(tmp_path, "overseas") == []


def test_cleanup_capacity_block_does_not_hide_document_before_index_refresh(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity,
        "capacity_status",
        lambda **_kwargs: {"blocked": True, "used_percent": 80.15},
    )
    monkeypatch.setattr(
        capacity,
        "ensure_capacity",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("capacity gate was bypassed")),
    )
    url = "https://example.test/blocked-cleanup.pdf"
    raw = b"blocked cleanup bytes"
    record = _cleanup_record(url, raw)
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
    }
    storage.memberships.add(("ai", url))

    result, managers = _run_cleanup(tmp_path, storage, "overseas", [record], dry_run=False)

    assert result["cleanup_status"] == "not_started_capacity_blocked"
    assert result["ready_status"] == "failed"
    assert "no file or membership changes" in result["ready_error"]
    assert storage.rows[url]["deleted_at"] is None
    assert storage.memberships == {("ai", url)}
    assert managers[0].remove_calls == []


def test_cleanup_rejects_raw_sha_mismatch_before_any_target_write(tmp_path: Path) -> None:
    url = "https://example.test/ambiguous-cleanup.pdf"
    record = _cleanup_record(url, b"manifest source bytes")
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": hashlib.sha256(b"different target bytes").hexdigest(),
        "deleted_at": None,
        "catalog_status": "ok",
    }
    storage.memberships.add(("ai", url))

    with pytest.raises(ValueError, match="different raw SHA-256"):
        _run_cleanup(tmp_path, storage, "overseas", [record], dry_run=False)

    assert storage.rows[url]["deleted_at"] is None
    assert storage.memberships == {("ai", url)}


def test_cleanup_rechecks_exact_identity_after_initial_audit(tmp_path: Path, monkeypatch) -> None:
    url = "https://example.test/cleanup-replaced-between-audit.pdf"
    original = b"approved cleanup bytes"
    replacement = b"concurrent replacement bytes"
    record = _cleanup_record(url, original)
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
    }
    storage.memberships.add(("ai", url))

    def replace_after_audit(**_kwargs):
        storage.rows[url]["sha256"] = hashlib.sha256(replacement).hexdigest()
        return {"blocked": False, "used_percent": 70}

    monkeypatch.setattr(capacity, "capacity_status", replace_after_audit)
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)

    result, managers = _run_cleanup(tmp_path, storage, "overseas", [record], dry_run=False)

    assert result["cleanup_status"] == "partial"
    assert "raw SHA-256 changed after cleanup audit" in result["failures"][0]["error"]
    assert storage.rows[url]["sha256"] == hashlib.sha256(replacement).hexdigest()
    assert storage.rows[url]["deleted_at"] is None
    assert storage.memberships == {("ai", url)}
    assert managers[0].remove_calls == []
    assert worker._read_pending_cleanup(tmp_path, "overseas") == ["ai"]


def test_cleanup_rolls_back_membership_removal_when_retirement_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "capacity_status", lambda **_kwargs: {"blocked": False})
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    url = "https://example.test/cleanup-retirement-rollback.pdf"
    record = _cleanup_record(url, b"rollback cleanup bytes")
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": record["raw_sha256"],
        "deleted_at": None,
        "catalog_status": "ok",
    }
    storage.memberships.update({("ai", url), ("all", url)})
    worker._add_pending_ready(tmp_path, "china", ["ai", "all"], [url])
    original_mark_deleted = storage.mark_file_deleted

    def fail_retirement(*_args, **_kwargs):
        raise RuntimeError("injected retirement failure")

    storage.mark_file_deleted = fail_retirement
    managers = []

    def manager_factory(value):
        manager = _FakeManager(value, "china")
        managers.append(manager)
        return manager

    result = worker.apply_cleanup(
        {
            "schema_version": 1,
            "target": "china",
            "dry_run": False,
            "records": [record],
            "approved_categories": ["AI", "Pricing", "Other"],
        },
        runtime_factory=lambda: _FakeRuntime(tmp_path),
        storage_factory=lambda *_args, **_kwargs: storage,
        manager_factory=manager_factory,
        ready_builder=lambda *_args: pytest.fail("Ready must wait for the rolled back cleanup"),
    )
    storage.mark_file_deleted = original_mark_deleted

    assert result["cleanup_status"] == "partial"
    assert "injected retirement failure" in result["failures"][0]["error"]
    assert storage.rows[url]["deleted_at"] is None
    assert storage.memberships == {("ai", url), ("all", url)}
    assert worker._read_pending_ready(tmp_path, "china") == {"ai": [url], "all": [url]}
    assert worker._read_pending_cleanup(tmp_path, "china") == ["ai", "all"]
    assert set(managers[0].remove_calls) == {("ai", url), ("all", url)}


def test_unchanged_soft_deleted_content_uses_full_reactivation_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "capacity_status", lambda **_kwargs: {"blocked": False})
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    url = "https://example.test/reactivate-soft-deleted.pdf"
    item = _item(url, b"reactivation bytes", "Pricing models use AI methods.")
    storage = _FakeStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "markdown_content": item["markdown"],
        "published_time": None,
        "deleted_at": "2026-10-01T00:00:00+00:00",
        "category": "AI",
        "catalog_status": "deleted",
        "summary": "old summary",
        "keywords": ["old"],
        "bilingual_metadata": copy.deepcopy(item["bilingual_metadata"]),
    }
    storage.memberships.update({("ai", url), ("all", url)})

    result = _apply_payload(tmp_path, storage, "china", [item], [])

    assert result["failures"] == []
    assert result["acknowledgements"][0]["status"] == "written"
    assert storage.rows[url]["deleted_at"] is None
    assert storage.rows[url]["catalog_status"] == "ok"
    assert storage.memberships == {("ai", url), ("all", url)}


def test_changed_source_content_uses_new_bilingual_packages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(capacity, "capacity_status", lambda **_kwargs: {"blocked": False})
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    url = "https://example.test/replacement-bilingual-metadata.pdf"
    storage = _FakeStorage(tmp_path)
    ready_rows = []
    original = _item(url, b"old source bytes", "Old pricing research uses AI methods.", version=31)
    _apply_payload(tmp_path, storage, "china", [original], ready_rows)

    replacement = _item(url, b"new source bytes", "New model research uses AI methods.", version=32)
    replacement["title"] = "New source title"
    for language in ("zh", "en"):
        replacement["bilingual_metadata"][language].update(
            {
                "title": f"New {language} title",
                "summary": f"New {language} source-bound summary",
                "keywords": ["new-source-keyword"],
            }
        )
    _bind_item_enrichment(replacement)

    result = _apply_payload(tmp_path, storage, "china", [replacement], ready_rows)
    saved = storage.rows[url]["bilingual_metadata"]

    assert result["failures"] == []
    assert storage.rows[url]["sha256"] == replacement["raw_sha256"]
    assert saved["hub_enrichment"]["content_version_id"] == 32
    for language in ("zh", "en"):
        assert saved[language]["title"] == replacement["bilingual_metadata"][language]["title"]
        assert saved[language]["summary"] == replacement["bilingual_metadata"][language]["summary"]
        assert saved[language]["keywords"] == ["new-source-keyword"]


def test_unknown_date_backfill_rejects_concurrent_legacy_date_clear(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capacity, "capacity_status", lambda **_kwargs: {"blocked": False})
    url = "https://example.test/unknown-date-concurrent-clear.pdf"
    markdown = "Pricing models use AI methods."
    item = _item(url, b"unknown publication date bytes", markdown)
    record = _metadata_backfill_record(item, "2024-12")

    class DateClearedBeforeWriteStorage(_FakeStorage):
        cleared = False

        @contextmanager
        def transaction(self, **kwargs):
            if not self.cleared:
                self.rows[url]["published_time"] = None
                self.cleared = True
            with super().transaction(**kwargs):
                yield

    storage = DateClearedBeforeWriteStorage(tmp_path)
    storage.rows[url] = {
        "url": url,
        "sha256": item["raw_sha256"],
        "markdown_content": markdown,
        "published_time": "2024-12",
        "deleted_at": None,
        "category": "AI",
        "catalog_status": "ok",
        "summary": "legacy summary",
        "keywords": ["legacy"],
        "bilingual_metadata": {"en": {"legacy_note": "keep"}, "zh": {"legacy_note": "保留"}},
    }
    storage.memberships.add(("ai", url))

    result, _ = _run_metadata_backfill(tmp_path, storage, "overseas", [record], dry_run=False)

    assert result["backfill_status"] == "partial"
    assert "exact target precondition changed before write" in result["failures"][0]["error"]
    assert storage.cleared is True
    assert storage.rows[url]["published_time"] is None


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"),
    reason="real PostgreSQL cleanup lock test requires isolated POSTGRES_TEST_URL",
)
def test_cleanup_file_lock_serializes_concurrent_content_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    from ai_actuarial.rag.config import RAGConfig
    from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
    from ai_actuarial.storage import Storage
    from tests.postgres_helpers import postgres_url_for_path

    monkeypatch.setattr(capacity, "capacity_status", lambda **_kwargs: {"blocked": False})
    monkeypatch.setattr(capacity, "ensure_capacity", lambda **_kwargs: None)
    db_url = postgres_url_for_path(tmp_path / "cleanup-concurrency.db")
    data_root = tmp_path / "data"
    rag_config = RAGConfig(data_dir=str(tmp_path / "rag"))
    url = "https://example.test/postgres-cleanup-concurrency.pdf"
    original = b"approved PostgreSQL cleanup bytes"
    replacement = b"concurrent PostgreSQL replacement bytes"
    record = _cleanup_record(url, original)
    initial = Storage(db_url, data_root=data_root)
    try:
        setup_manager = KnowledgeBaseManager(initial, config=rag_config)
        setup_manager.create_kb(
            kb_id="ai",
            name="AI",
            kb_mode="manual",
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
            embedding_dimension=3072,
            embedding_identity_key="isolated-test-ai-3072",
        )
        old_sha = hashlib.sha256(original).hexdigest()
        initial.insert_file(
            url=url,
            sha256=old_sha,
            title="Approved source",
            source_site="test",
            source_page_url=url,
            original_filename="source.pdf",
            local_path=str(tmp_path / "source.pdf"),
            bytes=len(original),
            content_type="application/pdf",
        )
        initial.upsert_catalog_item(
            {
                "url": url,
                "sha256": old_sha,
                "category": "AI",
                "summary": "Approved source",
                "keywords": ["test"],
            },
            pipeline_version="cleanup-lock-test",
            status="ok",
        )
        setup_manager.add_files_to_kb("ai", [url])
    finally:
        initial.close()

    cleanup_has_lock = threading.Event()
    allow_cleanup_to_remove = threading.Event()
    writer_lock_attempted = threading.Event()
    writer_done = threading.Event()
    outcomes: dict[str, object] = {}
    writer_errors: list[str] = []
    writer_storage = Storage(db_url, data_root=data_root)
    writer_manager = KnowledgeBaseManager(writer_storage, config=rag_config)
    original_lock = writer_storage._lock_postgres_key

    def tracked_lock(namespace: str, key: str) -> None:
        if namespace == "file" and key == url:
            writer_lock_attempted.set()
        original_lock(namespace, key)

    writer_storage._lock_postgres_key = tracked_lock

    def cleanup_manager_factory(storage):
        delegate = KnowledgeBaseManager(storage, config=rag_config)

        class BlockingManager:
            def get_kb(self, kb_id):
                return delegate.get_kb(kb_id)

            def remove_files_from_kb(self, kb_id, urls):
                if not cleanup_has_lock.is_set():
                    cleanup_has_lock.set()
                    if not allow_cleanup_to_remove.wait(10):
                        raise TimeoutError("test did not release cleanup interleave")
                return delegate.remove_files_from_kb(kb_id, urls)

        return BlockingManager()

    def run_cleanup() -> None:
        try:
            outcomes["cleanup"] = worker.apply_cleanup(
                {
                    "schema_version": 1,
                    "target": "overseas",
                    "dry_run": False,
                    "records": [record],
                    "approved_categories": ["AI", "Pricing", "Other"],
                },
                runtime_factory=lambda: _FakeRuntime(data_root),
                storage_factory=lambda *_args, **_kwargs: Storage(db_url, data_root=data_root),
                manager_factory=cleanup_manager_factory,
                ready_builder=lambda *_args: {"index_version_id": "lock-test"},
            )
        except Exception as exc:
            outcomes["cleanup_error"] = f"{type(exc).__name__}: {exc}"

    def run_replacement() -> None:
        try:
            replacement_sha = hashlib.sha256(replacement).hexdigest()
            with writer_storage.transaction(immediate=True):
                writer_storage.upsert_file(
                    url,
                    replacement_sha,
                    "Replacement source",
                    "test",
                    url,
                    "replacement.pdf",
                    str(tmp_path / "replacement.pdf"),
                    len(replacement),
                    "application/pdf",
                    None,
                    None,
                    None,
                )
                writer_storage._conn.execute(
                    "UPDATE files SET deleted_at = NULL WHERE url = ?", (url,)
                )
                writer_storage.upsert_catalog_item(
                    {
                        "url": url,
                        "sha256": replacement_sha,
                        "category": "AI",
                        "summary": "Replacement source",
                        "keywords": ["replacement"],
                    },
                    pipeline_version="cleanup-lock-replacement-test",
                    status="ok",
                )
                writer_manager.add_files_to_kb("ai", [url])
        except Exception as exc:
            writer_errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            writer_done.set()

    cleanup_thread = threading.Thread(target=run_cleanup)
    writer_thread = threading.Thread(target=run_replacement)
    cleanup_thread.start()
    assert cleanup_has_lock.wait(10), "cleanup did not reach its locked membership-removal step"
    writer_thread.start()
    try:
        assert writer_lock_attempted.wait(10), "replacement did not attempt the native file lock"
        assert not writer_done.wait(0.25), "replacement passed cleanup's file lock"
    finally:
        allow_cleanup_to_remove.set()
        cleanup_thread.join(15)
        writer_thread.join(15)
        writer_storage.close()

    assert not cleanup_thread.is_alive()
    assert not writer_thread.is_alive()
    assert "cleanup_error" not in outcomes, outcomes.get("cleanup_error")
    assert writer_errors == []
    assert outcomes["cleanup"]["cleanup_status"] == "succeeded"
    final_storage = Storage(db_url, data_root=data_root)
    try:
        row = final_storage.get_file_with_catalog(url)
        memberships = sorted(
            item[0]
            for item in final_storage._conn.execute(
                "SELECT kb_id FROM rag_kb_files WHERE file_url = ?", (url,)
            ).fetchall()
        )
    finally:
        final_storage.close()
    assert row["sha256"] == hashlib.sha256(replacement).hexdigest()
    assert row["deleted_at"] is None
    assert row["catalog_status"] == "ok"
    assert memberships == ["ai"]


def _interpretation_draft() -> dict:
    from ai_actuarial import article_interpretations as articles

    messages = [{"role": "user", "content": "bounded evidence fixture"}]
    coverage = {"evidence": [{"id": f"E{i}"} for i in range(1, 6)]}
    raw_sha = "a" * 64
    markdown_sha = "b" * 64
    return {
        "interpretation_id": "interpretation-fixture-1",
        "file_url": "https://example.test/current.pdf",
        "raw_sha256": raw_sha,
        "markdown_sha256": markdown_sha,
        "content_key": articles._hash(raw_sha + markdown_sha),
        "source_key": "cas",
        "input_fingerprint": articles._hash(
            articles._json({"messages": messages, "coverage": coverage})
        ),
        "prompt_version": articles.PROMPT_VERSION,
        "status": "ready",
        "title_zh": "研究方法与应用边界",
        "body_markdown_zh": "## 研究解读\n\n依据原文证据形成的说明。",
        "coverage": coverage,
        "messages": messages,
        "references": {"authors": [], "evidence": coverage["evidence"]},
    }


class _InterpretationCursor:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _InterpretationConnection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.closed = False
        self.commits = 0
        self.rollbacks = 0
        self.read_only = False
        self.readback_queries = 0
        self.updates = 0

    def execute(self, statement, params=()):
        if (
            "input_fingerprint,status,payload_json FROM article_interpretations WHERE interpretation_id=?"
            in statement
            and " OR input_fingerprint=?" not in statement
        ):
            self.readback_queries += 1
            return _InterpretationCursor([row for row in self.rows if row[0] == params[0]])
        if statement.startswith("SELECT file_url,raw_sha256"):
            selected = [row for row in self.rows if row[0] == params[0]]
            return _InterpretationCursor(
                [(row[1], row[2], row[3], row[6], row[7]) for row in selected]
            )
        if statement.startswith("SELECT interpretation_id,file_url"):
            interpretation_id, input_fingerprint, content_key = params
            ready_content_only = "content_key=? AND status='ready'" in statement
            selected = [
                row
                for row in self.rows
                if row[0] == interpretation_id
                or row[5] == input_fingerprint
                or (row[4] == content_key and (not ready_content_only or row[6] == "ready"))
            ]
            return _InterpretationCursor(selected)
        if statement.startswith("INSERT INTO article_interpretations"):
            identity, url, raw_sha, markdown_sha, content_key, source_key, fp, payload = params
            self.rows.append(
                (
                    identity,
                    url,
                    raw_sha,
                    markdown_sha,
                    content_key,
                    fp,
                    "ready",
                    json.loads(payload),
                )
            )
            return _InterpretationCursor()
        if statement.startswith("UPDATE article_interpretations SET payload_json=jsonb_set"):
            self.updates += 1
            translation = json.loads(params[0])
            expected = tuple(params[1:])
            for index, row in enumerate(self.rows):
                if tuple(row[:6]) == expected and row[6] == "ready":
                    payload = dict(row[7])
                    payload["english_translation"] = translation
                    self.rows[index] = (*row[:7], payload)
                    break
            return _InterpretationCursor()
        return _InterpretationCursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _use_fake_interpretation_target(monkeypatch, connection):
    import ai_actuarial.capacity as capacity
    import ai_actuarial.postgres as postgres

    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(worker, "_interpretation_current_row", lambda *_args: None)
    monkeypatch.setattr(capacity, "capacity_status", lambda **_kwargs: {"blocked": False})
    monkeypatch.setattr(
        postgres,
        "PostgresConnection",
        lambda _database, read_only=False: _set_read_only(connection, read_only),
    )


def _set_read_only(connection, read_only):
    connection.read_only = read_only
    return connection


def test_interpretation_target_insert_is_exact_and_duplicate_reconciliation_is_idempotent(
    monkeypatch,
):
    draft = _interpretation_draft()
    draft["english_translation"] = {
        "status": "ready",
        "title_en": "Methods and application boundaries",
        "body_markdown_en": "## Research interpretation\n\nA concise evidence-based explanation.",
    }
    other_version = (
        "other-version",
        "https://example.test/other.pdf",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        "ready",
        {"interpretation_id": "other-version", "title_zh": "Keep this version"},
    )
    connection = _InterpretationConnection([other_version])
    _use_fake_interpretation_target(monkeypatch, connection)

    first = worker.apply_article_interpretation(
        {"target": "overseas", "locale": "zh", "draft": draft},
        runtime_factory=lambda: object(),
    )
    zh_duplicate = worker.apply_article_interpretation(
        {"target": "overseas", "locale": "zh", "draft": draft},
        runtime_factory=lambda: object(),
    )
    row_after_zh = dict(
        next(row for row in connection.rows if row[0] == draft["interpretation_id"])[7]
    )
    en_updated = worker.apply_article_interpretation(
        {"target": "overseas", "locale": "en", "draft": draft},
        runtime_factory=lambda: object(),
    )
    en_duplicate = worker.apply_article_interpretation(
        {"target": "overseas", "locale": "en", "draft": draft},
        runtime_factory=lambda: object(),
    )

    assert first["status"] == "inserted"
    assert zh_duplicate["status"] == "already_present"
    assert en_updated["status"] == "updated"
    assert en_duplicate["status"] == "already_present"
    assert first["identity"] == en_updated["identity"]
    assert first["identity"]["draft_sha256"]
    assert first["locale"] == "zh"
    assert first["reader_fields"]["locale"] == "zh"
    assert first["reader_fields"]["title"] == draft["title_zh"]
    assert first["reader_fields"]["body_chars"] == len(draft["body_markdown_zh"])
    assert (
        first["reader_fields"]["body_sha256"]
        == hashlib.sha256(draft["body_markdown_zh"].encode("utf-8")).hexdigest()
    )
    assert "english_translation" not in row_after_zh
    assert en_updated["locale"] == "en"
    assert en_updated["reader_fields"]["status"] == "ready"
    assert en_updated["reader_fields"]["title"] == "Methods and application boundaries"
    assert en_updated["reader_fields"]["body_chars"] == len(
        draft["english_translation"]["body_markdown_en"]
    )
    assert (
        en_updated["reader_fields"]["body_sha256"]
        == hashlib.sha256(
            draft["english_translation"]["body_markdown_en"].encode("utf-8")
        ).hexdigest()
    )
    assert "body_markdown_en" not in en_updated["reader_fields"]
    assert "body_markdown_zh" not in first["reader_fields"]
    assert connection.readback_queries == 4
    assert connection.read_only is False
    assert connection.commits == 4
    assert connection.updates == 1
    saved = next(row for row in connection.rows if row[0] == draft["interpretation_id"])
    assert len(connection.rows) == 2
    assert saved[7]["title_zh"] == row_after_zh["title_zh"]
    assert saved[7]["body_markdown_zh"] == row_after_zh["body_markdown_zh"]
    assert saved[7]["english_translation"] == draft["english_translation"]
    assert connection.rows[0] == other_version


def test_failed_historical_same_content_draft_does_not_block_ready_sync(monkeypatch):
    draft = _interpretation_draft()
    failed_payload = {**draft, "interpretation_id": "old-failed-draft", "status": "failed"}
    failed_row = (
        "old-failed-draft",
        draft["file_url"],
        draft["raw_sha256"],
        draft["markdown_sha256"],
        draft["content_key"],
        "c" * 64,
        "failed",
        failed_payload,
    )
    connection = _InterpretationConnection([failed_row])
    _use_fake_interpretation_target(monkeypatch, connection)

    inserted = worker.apply_article_interpretation(
        {"target": "overseas", "locale": "zh", "draft": draft},
        runtime_factory=lambda: object(),
    )
    duplicate = worker.apply_article_interpretation(
        {"target": "overseas", "locale": "zh", "draft": draft},
        runtime_factory=lambda: object(),
    )

    assert inserted["status"] == "inserted"
    assert duplicate["status"] == "already_present"
    assert len(connection.rows) == 2
    assert connection.rows[0][6] == "failed"
    assert connection.rows[1][6] == "ready"


def test_different_ready_draft_for_same_content_still_conflicts(monkeypatch):
    draft = _interpretation_draft()
    different_ready = (
        "other-ready-interpretation",
        draft["file_url"],
        draft["raw_sha256"],
        draft["markdown_sha256"],
        draft["content_key"],
        "c" * 64,
        "ready",
        {**draft, "interpretation_id": "other-ready-interpretation"},
    )
    connection = _InterpretationConnection([different_ready])
    _use_fake_interpretation_target(monkeypatch, connection)

    with pytest.raises(
        worker._InterpretationTargetFailure, match="interpretation_identity_conflict"
    ):
        worker.apply_article_interpretation(
            {"target": "overseas", "locale": "zh", "draft": draft},
            runtime_factory=lambda: object(),
        )
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    "mutation,expected_error",
    [
        ("source", "interpretation_identity_conflict"),
        ("zh_digest", "interpretation_chinese_locale_conflict"),
        ("references", "interpretation_source_projection_conflict"),
        ("ready_en", "interpretation_english_locale_conflict"),
    ],
)
def test_interpretation_en_only_update_rejects_identity_or_ready_conflicts(
    monkeypatch, mutation, expected_error
):
    draft = _interpretation_draft()
    draft["english_translation"] = {
        "status": "ready",
        "title_en": "Methods and application boundaries",
        "body_markdown_en": "English body.",
    }
    stored = dict(draft)
    if mutation == "source":
        stored["file_url"] = "https://example.test/other.pdf"
    elif mutation == "zh_digest":
        stored["title_zh"] = "Different Chinese title"
    elif mutation == "references":
        stored["references"] = {
            **stored["references"],
            "article_url": "https://example.test/other.pdf",
        }
    else:
        stored["english_translation"] = {
            "status": "ready",
            "title_en": "Different English title",
            "body_markdown_en": "Different English body.",
        }
    row = (
        draft["interpretation_id"],
        stored["file_url"],
        draft["raw_sha256"],
        draft["markdown_sha256"],
        draft["content_key"],
        draft["input_fingerprint"],
        "ready",
        stored,
    )
    connection = _InterpretationConnection([row])
    _use_fake_interpretation_target(monkeypatch, connection)

    with pytest.raises(worker._InterpretationTargetFailure, match=expected_error):
        worker.apply_article_interpretation(
            {"target": "overseas", "locale": "en", "draft": draft},
            runtime_factory=lambda: object(),
        )

    assert connection.updates == 0
    assert connection.rows[0][7] == stored


def test_interpretation_en_locale_not_ready_is_not_acknowledged(monkeypatch):
    draft = _interpretation_draft()
    connection = _InterpretationConnection()
    _use_fake_interpretation_target(monkeypatch, connection)

    with pytest.raises(
        worker._InterpretationTargetFailure, match="interpretation_locale_not_ready"
    ):
        worker.apply_article_interpretation(
            {"target": "overseas", "locale": "en", "draft": draft},
            runtime_factory=lambda: object(),
        )
    assert not connection.rows
    assert connection.updates == 0


def test_interpretation_target_rejects_conflict_not_ready_and_missing_evidence(monkeypatch):
    draft = _interpretation_draft()
    conflict = _InterpretationConnection(
        [
            (
                draft["interpretation_id"],
                draft["file_url"],
                "c" * 64,
                draft["markdown_sha256"],
                draft["content_key"],
                draft["input_fingerprint"],
                "ready",
                draft,
            )
        ]
    )
    _use_fake_interpretation_target(monkeypatch, conflict)
    with pytest.raises(
        worker._InterpretationTargetFailure, match="interpretation_identity_conflict"
    ):
        worker.apply_article_interpretation(
            {"target": "overseas", "locale": "zh", "draft": draft},
            runtime_factory=lambda: object(),
        )
    assert conflict.rollbacks == 1

    not_ready = {**draft, "status": "failed"}
    with pytest.raises(worker._InterpretationTargetFailure, match="interpretation_not_ready"):
        worker._interpretation_identity(not_ready)
    no_evidence = {**draft, "coverage": {"evidence": []}}
    with pytest.raises(
        worker._InterpretationTargetFailure, match="interpretation_validation_evidence_missing"
    ):
        worker._interpretation_identity(no_evidence)


def test_interpretation_target_china_ack_requires_exact_saved_identity(monkeypatch):
    draft = _interpretation_draft()
    changed = {**draft, "title_zh": "不同稿件"}
    connection = _InterpretationConnection(
        [
            (
                draft["interpretation_id"],
                draft["file_url"],
                draft["raw_sha256"],
                draft["markdown_sha256"],
                draft["content_key"],
                draft["input_fingerprint"],
                "ready",
                changed,
            )
        ]
    )
    _use_fake_interpretation_target(monkeypatch, connection)

    with pytest.raises(
        worker._InterpretationTargetFailure,
        match="interpretation_source_projection_readback_mismatch",
    ):
        worker.apply_article_interpretation(
            {"target": "china", "locale": "zh", "draft": draft},
            runtime_factory=lambda: object(),
        )
    assert connection.read_only is True
    assert not connection.commits


def test_interpretation_current_source_rejects_missing_stale_and_unknown_source(monkeypatch):
    from ai_actuarial import article_interpretations as articles

    draft = _interpretation_draft()
    identity = worker._interpretation_identity(draft)

    class Connection:
        source_status = ("active",)

        def execute(self, *_args, **_kwargs):
            return _InterpretationCursor([self.source_status])

    connection = Connection()
    monkeypatch.setattr(articles, "_load_file", lambda *_args: None)
    with pytest.raises(worker._InterpretationTargetFailure, match="source_missing"):
        worker._interpretation_current_row(connection, identity, "cas")

    current = {
        "url": draft["file_url"],
        "sha256": draft["raw_sha256"],
        "local_path": "fixture.pdf",
        "deleted_at": None,
        "status": "ok",
        "markdown_content": "different current version",
    }
    monkeypatch.setattr(articles, "_load_file", lambda *_args: current)
    with pytest.raises(worker._InterpretationTargetFailure, match="source_version_stale"):
        worker._interpretation_current_row(connection, identity, "cas")

    current["markdown_content"] = "same"
    monkeypatch.setattr(
        articles,
        "_identity",
        lambda row: {
            "file_url": identity["file_url"],
            "raw_sha256": identity["raw_sha256"],
            "markdown_sha256": identity["markdown_sha256"],
        },
    )
    connection.source_status = ("retired",)
    with pytest.raises(worker._InterpretationTargetFailure, match="canonical_source_missing"):
        worker._interpretation_current_row(connection, identity, "cas")


def test_article_interpretation_prompt_result_stream_and_optional_english_route(monkeypatch):
    import asyncio
    import time

    from ai_actuarial import storage as storage_module

    output = StringIO()

    class InputStream:
        def readline(self, _limit):
            prompt = json.loads(output.getvalue().splitlines()[-1])
            return (
                json.dumps(
                    {
                        "schema_version": 1,
                        "event": "result",
                        "request_id": prompt["request_id"],
                        "result": "validated local model result",
                    }
                )
                + "\n"
            )

    class FakeRuntime:
        data_root = Path("fixture-data")

        def _load_site_config(self):
            return {
                "article_interpretation": {
                    "english_translation": {"enabled": True},
                    "english_proxy": {"enabled": True},
                }
            }

    class FakeStorage:
        closed = False

        def close(self):
            self.closed = True

    fake_storage = FakeStorage()
    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(
        storage_module.Storage,
        "open_existing",
        lambda _database, data_root=None: fake_storage,
    )

    class FakeService:
        def __init__(self, _storage, *, generator, config):
            self.generator = generator
            assert config["environment"] == "china"

        def run(self, **_kwargs):
            result = asyncio.run(
                self.generator.generate(
                    [{"role": "user", "content": "Chinese draft prompt"}],
                    deadline=time.monotonic() + 30,
                )
            )
            assert result == "validated local model result"
            return {
                "status": "complete",
                "round_key": "2026-11-02",
                "receipt_type": "generation",
                "provider_calls": None,
                "outer_attempts": 1,
                "internal_provider_requests": "unknown/unmetered",
                "slots": [],
            }

    class FakeEnglishService:
        def __init__(self, _storage, *, generator):
            self.generator = generator

        def run(self, *, interpretation_ids):
            assert interpretation_ids == ["interpretation-fixture-1"]
            result = asyncio.run(
                self.generator.generate(
                    [{"role": "user", "content": "English translation prompt"}],
                    deadline=time.monotonic() + 30,
                )
            )
            assert result == "validated local model result"
            return {
                "status": "complete",
                "receipt_type": "english_translation",
                "provider_calls": 1,
                "outer_attempts": 1,
                "internal_provider_requests": "unknown/unmetered",
                "slots": [{"interpretation_id": "interpretation-fixture-1", "status": "ready"}],
            }

    class ReadyService(FakeService):
        def run(self, **kwargs):
            result = super().run(**kwargs)
            result["slots"] = [{"interpretation_id": "interpretation-fixture-1", "status": "ready"}]
            return result

    result = worker.run_article_interpretation_stream(
        {
            "schema_version": 1,
            "operation": "run_article_interpretation_stream",
            "target": "china",
            "round_key": "2026-11-02",
            "retry_id": None,
            "backend": "codex-cli",
            "requested_model": "gpt-6-luna",
            "reasoning_effort": "high",
        },
        input_stream=InputStream(),
        output_stream=output,
        runtime_factory=FakeRuntime,
        service_factory=ReadyService,
        english_service_factory=FakeEnglishService,
    )

    events = [json.loads(line) for line in output.getvalue().splitlines()]
    prompts = [event for event in events if event["event"] == "prompt"]
    assert [event["stage"] for event in prompts] == ["generation", "english_translation"]
    assert len({event["request_id"] for event in prompts}) == 2
    assert result["locale_settings"] == {
        "english_translation_enabled": True,
        "english_proxy_enabled": True,
    }
    assert result["route"]["requested_model"] == "gpt-6-luna"
    assert result["route"]["effective_model"] == "unreported"
    assert result["english_translation"]["internal_provider_requests"] == "unknown/unmetered"
    assert fake_storage.closed is True


@pytest.mark.parametrize("response_kind", ["eof", "malformed", "oversize", "mismatched_id"])
def test_article_interpretation_stream_rejects_bad_result_frames(response_kind):
    import asyncio
    import time

    from ai_actuarial import article_interpretations as articles

    output = StringIO()

    class InputStream:
        def readline(self, limit):
            if response_kind == "eof":
                return ""
            if response_kind == "malformed":
                return "{invalid json}\n"
            if response_kind == "oversize":
                return "x" * (worker.MAX_INTERPRETATION_EVENT_BYTES + 1)
            if response_kind == "mismatched_id":
                return json.dumps(
                    {
                        "schema_version": 1,
                        "event": "result",
                        "request_id": "0" * 32,
                        "result": "fixture",
                    }
                )
            raise AssertionError(response_kind)

    stream = worker._ArticleInterpretationPromptStream(
        articles.CodexArticleRuntime(
            backend="codex-cli", model="gpt-6-luna", reasoning_effort="high"
        ),
        InputStream(),
        output,
    )
    with pytest.raises(articles.ArticleStreamInterrupted):
        asyncio.run(
            stream.generate(
                [{"role": "user", "content": "fixture"}],
                deadline=time.monotonic() + 10,
            )
        )
    prompt = json.loads(output.getvalue().splitlines()[0])
    assert prompt["event"] == "prompt"
    assert prompt["schema_version"] == 1
    assert len(prompt["request_id"]) == 32


def test_article_interpretation_sync_candidate_scan_skips_conflict_only_history(monkeypatch):
    from ai_actuarial import postgres

    drafts = [
        {
            "interpretation_id": f"old-{index:03}",
            "status": "ready",
            "title_zh": "旧稿标题",
            "body_markdown_zh": "旧稿正文",
            "content_key": f"{index + 1:064x}",
        }
        for index in range(100)
    ] + [
        {
            "interpretation_id": "new-pending",
            "status": "ready",
            "title_zh": "新稿标题",
            "body_markdown_zh": "新稿正文",
            "content_key": f"{101:064x}",
        }
    ]
    identities = {
        draft["interpretation_id"]: {
            "interpretation_id": draft["interpretation_id"],
            "file_url": f"https://example.test/{draft['interpretation_id']}.pdf",
            "raw_sha256": f"{index + 1:064x}",
            "markdown_sha256": f"{index + 101:064x}",
            "content_key": draft["content_key"],
            "prompt_version": "article-interpretation-v8",
            "input_fingerprint": f"{index + 201:064x}",
            "draft_sha256": f"{index + 301:064x}",
        }
        for index, draft in enumerate(drafts)
    }
    receipts = {}
    for index, draft in enumerate(drafts[:-1]):
        identity = identities[draft["interpretation_id"]]
        source_identity = worker._interpretation_source_identity(identity, draft)
        reader_fields = worker._interpretation_reader_fields(draft, "zh")
        locale_digest = worker._interpretation_locale_digest(draft, "zh")
        for target in ("china", "overseas"):
            if index == 0 and target == "overseas":
                continue
            key = worker._interpretation_ack_key(target, source_identity, "zh")
            receipts[key] = {
                "receipt_type": "target_sync_locale",
                "target": target,
                "locale": "zh",
                "source_identity": source_identity,
                "locale_digest": "0" * 64 if index < 3 else locale_digest,
                "draft_sha256": identity["draft_sha256"],
                "status": "acknowledged",
                "reader_fields": reader_fields,
            }

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class Connection:
        closed = False

        def __init__(self):
            self.offsets = []

        def execute(self, statement, params=()):
            if statement.startswith("SELECT payload_json FROM article_interpretations"):
                offset = params[0]
                self.offsets.append(offset)
                return Cursor([(row,) for row in drafts[offset : offset + 100]])
            if statement.startswith("SELECT receipt_json FROM article_interpretation_rounds"):
                return Cursor([(receipts[params[0]],)] if params[0] in receipts else [])
            raise AssertionError(statement)

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(
        postgres,
        "PostgresConnection",
        lambda _database, read_only=False: connection,
    )
    monkeypatch.setattr(
        worker,
        "_interpretation_identity",
        lambda draft: identities[draft["interpretation_id"]],
    )
    monkeypatch.setattr(worker, "_interpretation_current_row", lambda *_args: None)

    result = worker.list_article_interpretation_sync_candidates(
        {
            "schema_version": 1,
            "operation": "list_article_interpretation_sync_candidates",
            "target": "china",
            "limit": 3,
        },
        runtime_factory=lambda: object(),
    )

    assert connection.read_only if hasattr(connection, "read_only") else True
    assert connection.offsets == [0, 100]
    assert [item["identity"]["interpretation_id"] for item in result["drafts"]] == [
        "old-000",
        "new-pending",
    ]
    assert list(result["drafts"][0]["locales"]) == ["zh"]
    assert result["drafts"][0]["targets"]["china"]["zh"]["status"] == "conflict"
    assert result["drafts"][0]["targets"]["overseas"]["zh"]["status"] == "pending"
    assert result["drafts"][1]["targets"]["china"]["zh"]["status"] == "pending"
    assert result["more_pending"] is False
    assert result["status"] == "partial"
    assert {
        (issue["interpretation_id"], issue["target"], issue["locale"]) for issue in result["issues"]
    } == {(f"old-{index:03}", target, "zh") for index in (1, 2) for target in ("china", "overseas")}
    assert all(
        issue["error"] == "target_locale_ack_projection_conflict" for issue in result["issues"]
    )
    assert connection.closed is True


def test_article_interpretation_sync_candidates_only_add_ready_english_locale(monkeypatch):
    from ai_actuarial import postgres

    draft = _interpretation_draft()
    source_identity = worker._interpretation_source_identity(
        worker._interpretation_identity(draft), draft
    )
    zh_digest = worker._interpretation_locale_digest(draft, "zh")
    zh_reader_fields = worker._interpretation_reader_fields(draft, "zh")
    receipts = {
        worker._interpretation_ack_key(target, source_identity, "zh"): {
            "receipt_type": "target_sync_locale",
            "target": target,
            "locale": "zh",
            "source_identity": source_identity,
            "locale_digest": zh_digest,
            "reader_fields": zh_reader_fields,
            "status": "acknowledged",
        }
        for target in ("china", "overseas")
    }

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class Connection:
        closed = False

        def execute(self, statement, params=()):
            if statement.startswith("SELECT payload_json FROM article_interpretations"):
                return Cursor([(draft,)])
            if statement.startswith("SELECT receipt_json FROM article_interpretation_rounds"):
                receipt = receipts.get(params[0])
                return Cursor([(receipt,)] if receipt else [])
            raise AssertionError(statement)

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(
        postgres,
        "PostgresConnection",
        lambda _database, read_only=False: connection,
    )
    monkeypatch.setattr(worker, "_interpretation_current_row", lambda *_args: None)

    before_translation = worker.list_article_interpretation_sync_candidates(
        {
            "schema_version": 1,
            "operation": "list_article_interpretation_sync_candidates",
            "target": "china",
            "limit": 3,
        },
        runtime_factory=lambda: object(),
    )
    assert before_translation["drafts"] == []
    assert before_translation["status"] == "no_candidates"

    draft["english_translation"] = {
        "status": "ready",
        "title_en": "Methods and application boundaries",
        "body_markdown_en": "## Research interpretation\n\nA concise evidence-based explanation.",
    }
    after_translation = worker.list_article_interpretation_sync_candidates(
        {
            "schema_version": 1,
            "operation": "list_article_interpretation_sync_candidates",
            "target": "china",
            "limit": 3,
        },
        runtime_factory=lambda: object(),
    )

    assert after_translation["status"] == "complete"
    assert len(after_translation["drafts"]) == 1
    candidate = after_translation["drafts"][0]
    assert candidate["identity"]["interpretation_id"] == draft["interpretation_id"]
    assert candidate["targets"]["china"]["zh"]["status"] == "acknowledged"
    assert candidate["targets"]["overseas"]["zh"]["status"] == "acknowledged"
    assert candidate["targets"]["china"]["en"]["status"] == "pending"
    assert candidate["targets"]["overseas"]["en"]["status"] == "pending"
    assert set(candidate["locales"]) == {"zh", "en"}
    assert connection.closed is True


@pytest.mark.parametrize("drift_locale", ["zh", "en"])
def test_article_interpretation_candidate_preserves_ack_on_locale_projection_drift(
    monkeypatch, drift_locale
):
    from ai_actuarial import postgres

    old_draft = _interpretation_draft()
    if drift_locale == "en":
        old_draft["english_translation"] = {
            "status": "ready",
            "title_en": "Original English title",
            "body_markdown_en": "Original English body.",
        }
    draft = json.loads(json.dumps(old_draft))
    if drift_locale == "zh":
        draft["title_zh"] = "Changed Chinese title"
        draft["english_translation"] = {
            "status": "ready",
            "title_en": "Methods and application boundaries",
            "body_markdown_en": "Newly ready English body.",
        }
    else:
        draft["english_translation"] = {
            "status": "ready",
            "title_en": "Changed English title",
            "body_markdown_en": "Changed English body.",
        }

    source_identity = worker._interpretation_source_identity(
        worker._interpretation_identity(draft), draft
    )
    receipts = {}
    for target in ("china", "overseas"):
        for locale in ("zh", "en"):
            if locale == "en" and drift_locale == "zh":
                continue
            receipt_draft = old_draft
            receipts[worker._interpretation_ack_key(target, source_identity, locale)] = {
                "receipt_type": "target_sync_locale",
                "target": target,
                "locale": locale,
                "source_identity": source_identity,
                "locale_digest": worker._interpretation_locale_digest(receipt_draft, locale),
                "draft_sha256": worker._interpretation_identity(receipt_draft)["draft_sha256"],
                "reader_fields": worker._interpretation_reader_fields(receipt_draft, locale),
                "status": "acknowledged",
            }
    receipts_before = json.loads(json.dumps(receipts))

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class Connection:
        closed = False

        def execute(self, statement, params=()):
            if statement.startswith("SELECT payload_json FROM article_interpretations"):
                return Cursor([(draft,)])
            if statement.startswith("SELECT receipt_json FROM article_interpretation_rounds"):
                receipt = receipts.get(params[0])
                return Cursor([(receipt,)] if receipt else [])
            raise AssertionError(f"unexpected write or query: {statement}")

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(
        postgres,
        "PostgresConnection",
        lambda _database, read_only=False: connection,
    )
    monkeypatch.setattr(worker, "_interpretation_current_row", lambda *_args: None)

    result = worker.list_article_interpretation_sync_candidates(
        {
            "schema_version": 1,
            "operation": "list_article_interpretation_sync_candidates",
            "target": "china",
            "limit": 3,
        },
        runtime_factory=lambda: object(),
    )

    if drift_locale == "en":
        assert result["drafts"] == []
        assert {
            (issue["target"], issue["locale"], issue["status"], issue["error"])
            for issue in result["issues"]
        } == {
            (target, "en", "conflict", "target_locale_ack_projection_conflict")
            for target in ("china", "overseas")
        }
    else:
        assert len(result["drafts"]) == 1
        candidate = result["drafts"][0]
        assert candidate["source_identity"] == source_identity
        for target in ("china", "overseas"):
            assert candidate["targets"][target]["zh"] == {
                "status": "conflict",
                "error": "target_locale_ack_projection_conflict",
            }
            assert candidate["targets"][target]["en"]["status"] == "pending"
        assert result["issues"] == []
    assert receipts == receipts_before
    assert connection.closed is True


def test_article_interpretation_target_ack_is_independent_and_idempotent(monkeypatch):
    from ai_actuarial import postgres

    draft = _interpretation_draft()
    identity = worker._interpretation_identity(draft)
    source_identity = worker._interpretation_source_identity(identity, draft)
    reader_fields = worker._interpretation_reader_fields(draft, "zh")
    locale_digest = worker._interpretation_locale_digest(draft, "zh")
    receipts = {}

    class Cursor:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        closed = False
        commits = 0
        rollbacks = 0

        def execute(self, statement, params=()):
            if statement.startswith("SELECT status,payload_json"):
                return Cursor(("ready", draft))
            if statement.startswith("SELECT receipt_json"):
                receipt = receipts.get(params[0])
                return Cursor((receipt,) if receipt else None)
            if statement.startswith("INSERT INTO article_interpretation_rounds"):
                receipts[params[0]] = json.loads(params[1])
                return Cursor()
            if statement.startswith("UPDATE article_interpretation_rounds"):
                receipts[params[1]] = json.loads(params[0])
                return Cursor()
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(
        postgres,
        "PostgresConnection",
        lambda _database, read_only=False: connection,
    )
    monkeypatch.setattr(worker, "_interpretation_identity", lambda _draft: identity)
    monkeypatch.setattr(worker, "_interpretation_current_row", lambda *_args: None)

    request = {
        "schema_version": 1,
        "operation": "record_article_interpretation_target_ack",
        "target": "overseas",
        "source_identity": source_identity,
        "locale": "zh",
        "locale_digest": locale_digest,
        "draft_sha256": identity["draft_sha256"],
        "status": "unknown",
        "error": "target_ack_unknown",
    }
    first = worker.record_article_interpretation_target_ack(
        request, runtime_factory=lambda: object()
    )
    success = worker.record_article_interpretation_target_ack(
        {
            **request,
            "status": "acknowledged",
            "error": None,
            "target_status": "inserted",
            "reader_fields": reader_fields,
        },
        runtime_factory=lambda: object(),
    )
    duplicate = worker.record_article_interpretation_target_ack(
        request, runtime_factory=lambda: object()
    )
    acknowledged_duplicate = worker.record_article_interpretation_target_ack(
        {
            **request,
            "status": "acknowledged",
            "error": None,
            "target_status": "already_present",
            "reader_fields": reader_fields,
        },
        runtime_factory=lambda: object(),
    )

    key = worker._interpretation_ack_key("overseas", source_identity, "zh")
    assert first["status"] == "unknown"
    assert success["status"] == "acknowledged"
    assert duplicate["status"] == "acknowledged"
    assert duplicate["preserved_ack"] is True
    assert duplicate["reader_fields"] == reader_fields
    assert acknowledged_duplicate["status"] == "acknowledged"
    assert acknowledged_duplicate["preserved_ack"] is True
    assert acknowledged_duplicate["target_status"] == "inserted"
    assert receipts[key]["source_identity"] == source_identity
    assert receipts[key]["locale"] == "zh"
    assert receipts[key]["locale_digest"] == locale_digest
    assert receipts[key]["reader_fields"] == reader_fields
    assert receipts[key]["draft_sha256"] == identity["draft_sha256"]
    assert receipts[key]["receipt_type"] == "target_sync_locale"
    assert receipts[key]["status"] == "acknowledged"
    assert [attempt["status"] for attempt in receipts[key]["attempts"]] == [
        "unknown",
        "acknowledged",
    ]
    assert connection.commits == 2
    assert connection.rollbacks == 2
    assert connection.closed is True


@pytest.mark.parametrize("incoming_status", ["unknown", "acknowledged"])
def test_article_interpretation_ack_writer_preserves_ack_on_projection_drift(
    monkeypatch, incoming_status
):
    from ai_actuarial import postgres

    old_draft = _interpretation_draft()
    draft = {**old_draft, "title_zh": "Changed projection, unchanged source identity"}
    old_identity = worker._interpretation_identity(old_draft)
    identity = worker._interpretation_identity(draft)
    source_identity = worker._interpretation_source_identity(identity, draft)
    old_locale_digest = worker._interpretation_locale_digest(old_draft, "zh")
    old_reader_fields = worker._interpretation_reader_fields(old_draft, "zh")
    locale_digest = worker._interpretation_locale_digest(draft, "zh")
    reader_fields = worker._interpretation_reader_fields(draft, "zh")
    key = worker._interpretation_ack_key("overseas", source_identity, "zh")
    receipts = {
        key: {
            "receipt_type": "target_sync_locale",
            "target": "overseas",
            "locale": "zh",
            "source_identity": source_identity,
            "locale_digest": old_locale_digest,
            "draft_sha256": old_identity["draft_sha256"],
            "reader_fields": old_reader_fields,
            "target_status": "inserted",
            "status": "acknowledged",
            "attempts": [{"status": "acknowledged", "locale_digest": old_locale_digest}],
        }
    }
    receipts_before = json.loads(json.dumps(receipts))

    class Cursor:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        closed = False
        commits = 0
        rollbacks = 0
        writes = []

        def execute(self, statement, params=()):
            if statement == "BEGIN" or statement.startswith("SELECT pg_advisory_xact_lock"):
                return Cursor()
            if statement.startswith("SELECT status,payload_json FROM article_interpretations"):
                return Cursor(("ready", draft))
            if statement.startswith("SELECT receipt_json FROM article_interpretation_rounds"):
                receipt = receipts.get(params[0])
                return Cursor((receipt,) if receipt else None)
            self.writes.append(statement)
            raise AssertionError("acknowledged projection must not be overwritten")

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(worker, "_article_interpretation_database", lambda _runtime: object())
    monkeypatch.setattr(
        postgres,
        "PostgresConnection",
        lambda _database, read_only=False: connection,
    )
    monkeypatch.setattr(worker, "_interpretation_current_row", lambda *_args: None)

    request = {
        "schema_version": 1,
        "operation": "record_article_interpretation_target_ack",
        "target": "overseas",
        "source_identity": source_identity,
        "locale": "zh",
        "locale_digest": locale_digest,
        "draft_sha256": identity["draft_sha256"],
        "status": incoming_status,
        "error": "target_ack_unknown" if incoming_status == "unknown" else None,
    }
    if incoming_status == "acknowledged":
        request.update(target_status="verified", reader_fields=reader_fields)

    with pytest.raises(
        worker._InterpretationTargetFailure,
        match="target_locale_ack_projection_conflict",
    ):
        worker.record_article_interpretation_target_ack(request, runtime_factory=lambda: object())

    assert receipts == receipts_before
    assert not connection.writes
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True


def test_locale_settings_probe_returns_only_the_two_authorized_booleans():
    class Runtime:
        def _load_site_config(self):
            return {
                "article_interpretation": {
                    "english_translation": {"enabled": True, "model": "not returned"},
                    "english_proxy": {"enabled": False, "origin": "not returned"},
                    "unrelated": {"secret": "not returned"},
                },
                "unrelated": {"secret": "not returned"},
            }

    result = worker.read_article_interpretation_locale_settings(
        {
            "schema_version": 1,
            "operation": "read_article_interpretation_locale_settings",
            "target": "china",
        },
        runtime_factory=Runtime,
    )
    assert result == {
        "schema_version": 1,
        "operation": "read_article_interpretation_locale_settings",
        "target": "china",
        "english_translation_enabled": True,
        "english_proxy_enabled": False,
    }

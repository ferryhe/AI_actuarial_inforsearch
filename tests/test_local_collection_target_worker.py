from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

import ai_actuarial.capacity as capacity
import ai_actuarial.local_collection_runtime as runtime
import ai_actuarial.local_collection_target_worker as worker


def _item(url: str, raw: bytes, markdown: str, *, version: int = 17) -> dict:
    md_sha = hashlib.sha256(markdown.encode()).hexdigest()
    raw_sha = hashlib.sha256(raw).hexdigest()
    return {
        "url": url,
        "raw_sha256": raw_sha,
        "raw_bytes_b64": __import__("base64").b64encode(raw).decode(),
        "markdown": markdown,
        "markdown_sha256": md_sha,
        "content_version_id": version,
        "markdown_text_variant_id": version + 100,
        "title": "Pricing AI paper",
        "source_site": "cas",
        "source_page_url": "https://example.test/research",
        "content_type": "application/pdf",
        "source_primary_category": "Pricing",
        "categories": [
            {"key": "Pricing", "evidence": ["Pricing models"]},
            {"key": "AI", "evidence": ["AI methods"]},
        ],
        "date_facts": {
            "publication_date": None,
            "revision_date": None,
            "document_version_date": None,
        },
        "date_review_status": "complete",
        "date_review_reason": None,
        "date_review_unresolved": [],
        "source_signature": "a" * 64,
        "result_sha256": "b" * 64,
        "bilingual_metadata": {
            language: {
                "title": "Pricing AI paper",
                "summary": "Pricing models use AI methods.",
                "category": "Pricing",
                "keywords": ["pricing", "AI"],
            }
            for language in ("zh", "en")
        },
    }


def test_target_item_preserves_secondary_ai_and_hash_bound_enrichment() -> None:
    raw = b"%PDF-1.7\nsource bytes"
    markdown = "Pricing models use AI methods."
    original = _item("https://example.test/pricing.pdf", raw, markdown)
    item = worker._normalize_item(original, "china", ["AI", "Pricing", "Other"])
    assert item["target_category"] == "AI"
    assert item["serving_metadata"]["hub_enrichment"]["source_primary_category"] == "Pricing"
    assert (
        item["serving_metadata"]["hub_enrichment"]["ordered_categories"] == original["categories"]
    )
    assert item["serving_metadata"]["zh"]["category"] == "AI"
    assert item["serving_metadata"]["hub_enrichment"]["source_primary_category"] == "Pricing"
    assert item["metadata_fingerprint"] == runtime._target_metadata_fingerprint(original)
    assert item["source_site"] == "cas"
    with pytest.raises(ValueError, match="including AI"):
        worker._normalize_item(
            {**original, "categories": [{"key": "Pricing", "evidence": ["Pricing models"]}]},
            "china",
            ["AI", "Pricing"],
        )


class _FakeConnection:
    def __init__(self, storage: "_FakeStorage") -> None:
        self.storage = storage

    def execute(self, statement: str, params: tuple):
        if "SELECT 1 FROM rag_kb_files" in statement:
            return _FakeCursor((params[0], params[1]) in self.storage.memberships)
        if "UPDATE files SET deleted_at = NULL" in statement:
            row = self.storage.rows.get(params[0])
            if row:
                row["deleted_at"] = None
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
        ("source_signature", "c" * 64),
        ("result_sha256", "d" * 64),
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
        self, data_root: Path, *, fail_chunk: bool = False, fail_ready: bool = False
    ) -> None:
        self.data_root = data_root
        self.fail_chunk = fail_chunk
        self.fail_ready = fail_ready
        self.task_types: list[str] = []

    def start_background_task(self, task_type: str, payload: dict, **_kwargs):
        self.task_types.append(task_type)
        if task_type == "chunk_generation":
            self.chunk_url = payload["files"][0]["file_url"]
            return "chunk"
        if task_type == "embedding_generation":
            return "embedding"
        if task_type == "rag_indexing":
            return "index"
        raise AssertionError(task_type)

    def _pipeline_task_status(self, task_id: str):
        return "error" if task_id == "chunk" and self.fail_chunk else "completed"

    def _pipeline_task_result(self, task_id: str):
        if task_id == "chunk":
            return {
                "type": "chunk_generation",
                "result": {"chunk_sets": [{"file_url": self.chunk_url, "chunk_set_id": "set-1"}]},
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
    assert worker._read_pending_ready(tmp_path, "overseas") == {}

    ready_only = _TaskRuntime(tmp_path)
    result = worker._refresh_ready(ready_only, storage, kb, [])
    assert ready_only.task_types == ["rag_indexing"]
    assert result["index_version_id"] == "index-1"

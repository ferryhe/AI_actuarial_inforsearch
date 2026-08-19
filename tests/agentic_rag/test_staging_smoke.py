from __future__ import annotations

import hashlib
import json
import multiprocessing
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.agentic_rag import ready_data_builder
from ai_actuarial.agentic_rag.staging_smoke import (
    STAGING_SMOKE_CONTRACT_VERSION,
    _assess_query_result,
    _query_process_entry,
    _run_offline_query,
    run_staging_smoke,
    select_staging_smoke_query,
)


def _build_source_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "source.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE files (
            url TEXT PRIMARY KEY,
            title TEXT,
            source_site TEXT,
            published_time TEXT
        );
        CREATE TABLE catalog_items (
            file_url TEXT PRIMARY KEY,
            status TEXT DEFAULT 'ok',
            summary TEXT,
            category TEXT,
            keywords TEXT,
            rag_chunk_count INTEGER DEFAULT 0,
            markdown_content TEXT
        );
        CREATE TABLE file_chunk_sets (
            chunk_set_id TEXT PRIMARY KEY,
            file_url TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ready'
        );
        CREATE TABLE global_chunks (
            chunk_id TEXT PRIMARY KEY,
            chunk_set_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER DEFAULT 0,
            section_hierarchy TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO files(url, title, source_site, published_time) VALUES (?, ?, ?, ?)",
        (
            "https://example.com/valuation-rule",
            "Deterministic Valuation Rule",
            "example.com",
            "2026-08-19",
        ),
    )
    conn.execute(
        """
        INSERT INTO catalog_items(
            file_url, status, summary, category, keywords,
            rag_chunk_count, markdown_content
        ) VALUES (?, 'ok', ?, ?, ?, 1, ?)
        """,
        (
            "https://example.com/valuation-rule",
            "A deterministic reserve valuation summary.",
            "regulation",
            '["reserve", "valuation"]',
            "# Reserve Formula\n| Item | Value |\n| --- | --- |\n| Reserve | 100 |",
        ),
    )
    conn.execute(
        "INSERT INTO file_chunk_sets(chunk_set_id, file_url, chunk_count) VALUES (?, ?, 1)",
        ("cs-smoke", "https://example.com/valuation-rule"),
    )
    conn.execute(
        """
        INSERT INTO global_chunks(
            chunk_id, chunk_set_id, chunk_index, content,
            token_count, section_hierarchy
        ) VALUES (?, ?, 0, ?, 12, ?)
        """,
        (
            "chunk-smoke",
            "cs-smoke",
            "Reserve = premium + interest. | Item | Value | Reserve | 100 |",
            "Reserve Formula > Calculation",
        ),
    )
    conn.commit()
    conn.close()
    return db_path


def _build_ready_data(tmp_path: Path, profile: str) -> Path:
    output_dir = tmp_path / profile
    manifest = ready_data_builder.build_l0(
        db_path=str(_build_source_db(tmp_path)),
        output_dir=str(output_dir),
        profile=profile,
    )
    assert manifest["doc_count"] == 1
    assert ready_data_builder.validate(str(output_dir))["valid"] is True
    return output_dir


@pytest.mark.parametrize("profile", ["general", "regulation", "formula"])
def test_non_empty_profiles_pass_real_catalog_backed_offline_smoke(
    tmp_path: Path,
    profile: str,
) -> None:
    output_dir = _build_ready_data(tmp_path, profile)

    result = run_staging_smoke(
        output_dir=str(output_dir),
        profile=profile,
        kb_id="kb-smoke",
        timeout_seconds=10,
    )

    assert result["contract_version"] == STAGING_SMOKE_CONTRACT_VERSION
    assert result["status"] == "passed"
    assert result["failure_reason"] == ""
    assert result["query_source"] == "title"
    assert result["query"] == "Deterministic Valuation Rule"
    assert result["query_sha256"] == hashlib.sha256(
        result["query"].encode("utf-8")
    ).hexdigest()
    assert result["matched_doc_id"] == "https://example.com/valuation-rule"
    assert result["matched_file_url"] == "https://example.com/valuation-rule"
    assert result["elapsed_ms"] >= 0
    assert result["checked_at"]
    assert "answer" not in result
    assert "evidence" not in result


def test_query_selection_is_stable_normalized_and_bounded(tmp_path: Path) -> None:
    output_dir = tmp_path / "candidate"
    output_dir.mkdir()
    rows = [
        {
            "doc_id": "z-doc",
            "file_url": "https://example.com/z",
            "title": "Later title",
            "summary": "Later summary",
            "headings": ["Later heading"],
        },
        {
            "doc_id": "a-doc",
            "file_url": "https://example.com/a",
            "title": "  Stable\u00a0\n  " + "query " * 80,
            "summary": "Fallback summary",
            "headings": ["Fallback heading"],
        },
    ]
    (output_dir / "doc_catalog.jsonl").write_text(
        "\n".join(json.dumps(row) for row in reversed(rows)) + "\n",
        encoding="utf-8",
    )

    first = select_staging_smoke_query(output_dir)
    second = select_staging_smoke_query(output_dir)

    assert first == second
    assert first["catalog_doc_count"] == 2
    assert first["catalog_doc_id"] == "a-doc"
    assert first["query_source"] == "title"
    assert first["query"].startswith("Stable query")
    assert "\n" not in first["query"]
    assert len(first["query"]) <= 160


@pytest.mark.parametrize(
    ("catalog_values", "section_values", "expected_source", "expected_query"),
    [
        (
            {"title": "Title query", "summary": "Summary query", "headings": ["Heading query"]},
            {"text": "Section query", "heading_path": ["Section heading"]},
            "title",
            "Title query",
        ),
        (
            {"title": "", "summary": "Summary query", "headings": ["Heading query"]},
            {"text": "Section query", "heading_path": ["Section heading"]},
            "summary",
            "Summary query",
        ),
        (
            {"title": "", "summary": "", "headings": ["Heading query"]},
            {"text": "Section query", "heading_path": ["Section heading"]},
            "heading",
            "Heading query",
        ),
        (
            {"title": "", "summary": "", "headings": []},
            {"text": "Section query", "heading_path": []},
            "section_text",
            "Section query",
        ),
    ],
)
def test_query_source_fallback_order(
    tmp_path: Path,
    catalog_values: dict[str, Any],
    section_values: dict[str, Any],
    expected_source: str,
    expected_query: str,
) -> None:
    output_dir = tmp_path / expected_source
    output_dir.mkdir()
    catalog = {
        "doc_id": "doc-1",
        "file_url": "https://example.com/1",
        **catalog_values,
    }
    section = {
        "section_id": "section-1",
        "doc_id": "doc-1",
        **section_values,
    }
    (output_dir / "doc_catalog.jsonl").write_text(
        json.dumps(catalog) + "\n",
        encoding="utf-8",
    )
    (output_dir / "sections.jsonl").write_text(
        json.dumps(section) + "\n",
        encoding="utf-8",
    )

    selection = select_staging_smoke_query(output_dir)

    assert selection["query_source"] == expected_source
    assert selection["query"] == expected_query


def test_empty_catalog_is_explicitly_skipped_without_fake_evidence(tmp_path: Path) -> None:
    output_dir = tmp_path / "empty"
    output_dir.mkdir()
    (output_dir / "doc_catalog.jsonl").write_text("", encoding="utf-8")

    result = run_staging_smoke(
        output_dir=str(output_dir),
        profile="general",
        kb_id="kb-empty",
        timeout_seconds=10,
    )

    assert result["status"] == "skipped_empty"
    assert result["query_source"] == "empty_catalog"
    assert result["query"] == ""
    assert result["matched_doc_id"] == ""
    assert result["matched_file_url"] == ""
    assert result["failure_reason"] == ""


def test_empty_evidence_fails_closed() -> None:
    selection = {
        "catalog_doc_ids": ["doc-1"],
        "catalog_file_urls": ["https://example.com/1"],
    }

    result = _assess_query_result(
        selection,
        {"status": "ok", "evidence_count": 0, "references": []},
    )

    assert result == {
        "passed": False,
        "failure_reason": "no_evidence",
        "matched_doc_id": "",
        "matched_file_url": "",
    }


def test_reference_outside_staging_catalog_fails_closed() -> None:
    selection = {
        "catalog_doc_ids": ["doc-1"],
        "catalog_file_urls": ["https://example.com/1"],
    }

    result = _assess_query_result(
        selection,
        {
            "status": "ok",
            "evidence_count": 1,
            "references": [
                {"doc_id": "foreign-doc", "file_url": "https://foreign.example/doc"}
            ],
        },
    )

    assert result["passed"] is False
    assert result["failure_reason"] == "catalog_reference_missing"


def test_long_reference_prefix_collision_does_not_match_catalog(tmp_path: Path) -> None:
    shared_prefix = "d" * 512
    output_dir = tmp_path / "long-identifiers"
    output_dir.mkdir()
    (output_dir / "doc_catalog.jsonl").write_text(
        json.dumps(
            {
                "doc_id": shared_prefix + "-catalog",
                "file_url": "https://example.com/catalog",
                "title": "Catalog title",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection = select_staging_smoke_query(output_dir)

    result = _assess_query_result(
        selection,
        {
            "status": "ok",
            "evidence_count": 1,
            "references": [
                {"doc_id": shared_prefix + "-foreign", "file_url": ""}
            ],
        },
    )

    assert result["passed"] is False
    assert result["failure_reason"] == "catalog_reference_missing"


def test_timeout_is_fail_closed_and_leaves_no_child_process(tmp_path: Path) -> None:
    output_dir = _build_ready_data(tmp_path, "general")
    before = {child.pid for child in multiprocessing.active_children()}

    result = run_staging_smoke(
        output_dir=str(output_dir),
        profile="general",
        kb_id="kb-timeout",
        timeout_seconds=0.000001,
    )

    after = {child.pid for child in multiprocessing.active_children()}
    assert result["status"] == "failed"
    assert result["failure_reason"] == "query_timed_out"
    assert after == before


def test_query_selection_runs_inside_the_timeout_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.agentic_rag.staging_smoke as smoke

    output_dir = _build_ready_data(tmp_path, "general")

    def fail_if_selected_in_parent(_output_dir: str | Path) -> dict[str, Any]:
        raise AssertionError("query selection escaped the timeout worker")

    monkeypatch.setattr(smoke, "select_staging_smoke_query", fail_if_selected_in_parent)

    result = run_staging_smoke(
        output_dir=str(output_dir),
        profile="general",
        kb_id="kb-selection-worker",
        timeout_seconds=10,
    )

    assert result["status"] == "passed"


def test_query_exception_is_bounded_and_does_not_leak_sensitive_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.agentic_rag.staging_smoke as smoke

    class RecordingConnection:
        payload: dict[str, Any] | None = None

        def send(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def close(self) -> None:
            return None

    def explode(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("secret document body must not be persisted")

    monkeypatch.setattr(smoke, "run_agentic_rag_loop", explode)
    connection = RecordingConnection()
    _query_process_entry(
        connection,
        {
            "query": "safe query",
            "output_dir": "unused",
            "profile": "general",
            "kb_id": "kb-error",
        },
    )

    assert connection.payload == {
        "status": "error",
        "failure_reason": "query_execution_failed",
    }
    assert "secret" not in json.dumps(connection.payload)


def test_offline_query_does_not_use_network_llm_embedding_or_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.ai_runtime as ai_runtime

    output_dir = _build_ready_data(tmp_path, "general")
    forbidden_calls: list[str] = []

    def forbidden(name: str):
        def fail(*_args: Any, **_kwargs: Any) -> Any:
            forbidden_calls.append(name)
            raise AssertionError(f"forbidden call: {name}")

        return fail

    monkeypatch.setattr(
        ai_runtime,
        "resolve_ai_function_runtime",
        forbidden("llm_provider"),
    )
    monkeypatch.setattr(
        ai_runtime,
        "build_embedding_fingerprint",
        forbidden("embedding"),
    )
    original_open = Path.open

    def guarded_open(path: Path, *args: Any, **kwargs: Any):
        lowered = path.name.lower()
        if "faiss" in lowered or lowered.endswith((".index", ".idx")):
            return forbidden("index")()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    payload = _run_offline_query(
        query="Deterministic Valuation Rule",
        output_dir=str(output_dir),
        profile="general",
        kb_id="kb-offline",
    )

    assert payload["status"] == "ok"
    assert payload["evidence_count"] >= 1
    assert forbidden_calls == []

"""Tests for Agentic RAG eval scaffolding (PR0)."""

from __future__ import annotations

import json

import pytest

from ai_actuarial.agentic_rag.eval import (
    CaseResult,
    EvalCase,
    EvalReport,
    RetrievedItem,
    RetrievalEvaluator,
    SimpleKeywordRetriever,
    load_cases,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


class FakeRetriever:
    """Configurable fake retriever for testing."""

    def __init__(self, results: list[RetrievedItem] | None = None):
        self._results = results or []
        self.last_query: str = ""
        self.last_top_k: int = 5

    def __call__(self, query: str, top_k: int = 5) -> list[RetrievedItem]:
        self.last_query = query
        self.last_top_k = top_k
        return self._results[:top_k]


# ── EvalCase ──────────────────────────────────────────────────────────────────


def test_eval_case_defaults():
    case = EvalCase(case_id="t1", query="test query")
    assert case.case_id == "t1"
    assert case.query == "test query"
    assert case.expected_doc_ids == []
    assert case.expected_categories == []
    assert case.min_hits == 1
    assert case.top_k == 5


# ── RetrievalEvaluator ────────────────────────────────────────────────────────


def test_evaluate_single_pass():
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_a", title="Doc A", category="AI")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c1",
        query="AI bulletin",
        expected_doc_ids=["doc_a"],
        expected_categories=["AI"],
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.hits == 1
    assert result.category_hits == 1


def test_evaluate_single_fail():
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_b", title="Doc B", category="general")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c2",
        query="specific query",
        expected_doc_ids=["doc_a"],
        expected_categories=["AI"],
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is False
    assert result.hits == 0


def test_evaluate_min_hits_2():
    retriever = FakeRetriever(
        [
            RetrievedItem(doc_id="doc_a", title="A"),
            RetrievedItem(doc_id="doc_b", title="B"),
        ]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c3",
        query="query",
        expected_doc_ids=["doc_a", "doc_b"],
        min_hits=2,
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.hits == 2


def test_evaluate_min_hits_not_met():
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_a", title="A")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c4",
        query="query",
        expected_doc_ids=["doc_a", "doc_b"],
        min_hits=2,
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is False
    assert result.hits == 1


def test_evaluate_empty_results():
    retriever = FakeRetriever([])
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c5",
        query="nonexistent",
        expected_doc_ids=["doc_x"],
        min_hits=0,  # expected no hits
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.hits == 0
    assert result.total_retrieved == 0


def test_evaluate_no_expected_doc_ids():
    """Case with no expected_doc_ids — auto-passes if min_hits=0."""
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_a", title="A", category="AI")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c6",
        query="any",
        expected_doc_ids=[],
        expected_categories=["AI"],
        min_hits=0,
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.category_hits == 1


# ── EvalReport ────────────────────────────────────────────────────────────────


def test_eval_report_aggregation():
    evaluator = RetrievalEvaluator(
        FakeRetriever([RetrievedItem(doc_id="doc_a", category="AI")])
    )
    cases = [
        EvalCase("t1", "q1", expected_doc_ids=["doc_a"], expected_categories=["AI"]),
        EvalCase("t2", "q2", expected_doc_ids=["doc_x"], expected_categories=["AI"]),
    ]
    report = evaluator.evaluate(cases)
    assert report.total_cases == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.doc_hit_rate == 0.5
    assert report.category_hit_rate == 1.0  # 2 hits from 2 expected ("AI" in both)


# ── load_cases ────────────────────────────────────────────────────────────────


def test_load_cases_from_jsonl(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "c1",
                "query": "test query",
                "expected_doc_ids": ["doc_a"],
                "expected_categories": ["AI"],
                "min_hits": 1,
                "top_k": 5,
                "notes": "test case",
            }
        )
        + "\n"
        + json.dumps(
            {
                "case_id": "c2",
                "query": "another",
                "expected_doc_ids": [],
                "expected_categories": [],
                "min_hits": 0,
            }
        )
        + "\n"
    )
    cases = load_cases(str(cases_path))
    assert len(cases) == 2
    assert cases[0].case_id == "c1"
    assert cases[0].expected_doc_ids == ["doc_a"]
    assert cases[1].case_id == "c2"
    assert cases[1].min_hits == 0


def test_load_cases_skips_comments(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        "# this is a comment\n"
        + json.dumps({"case_id": "c1", "query": "q"})
        + "\n"
        + "# another comment\n"
    )
    cases = load_cases(str(cases_path))
    assert len(cases) == 1


# ── SimpleKeywordRetriever ────────────────────────────────────────────────────


def test_simple_keyword_retriever_with_test_db(tmp_path):
    """Integration: retriever against a minimal SQLite DB."""
    import sqlite3

    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)

    conn.executescript(
        """
        CREATE TABLE files(url TEXT PRIMARY KEY, title TEXT, source_site TEXT, published_time TEXT);
        CREATE TABLE catalog_items(file_url TEXT PRIMARY KEY, status TEXT, summary TEXT, category TEXT, keywords TEXT, rag_chunk_count INTEGER);
        CREATE TABLE file_chunk_sets(chunk_set_id TEXT PRIMARY KEY, file_url TEXT, chunk_count INTEGER, status TEXT);
        CREATE TABLE global_chunks(chunk_id TEXT PRIMARY KEY, chunk_set_id TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT);
        CREATE TABLE rag_chunks(chunk_id TEXT PRIMARY KEY, kb_id TEXT, file_url TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT, embedding_hash TEXT, created_at TEXT);
    """
    )

    conn.execute(
        "INSERT INTO files(url,title,source_site) VALUES(?,?,?)",
        ("https://example.com/doc1", "Actuarial Intelligence Bulletin", "SOA"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords,rag_chunk_count) VALUES(?,?,?,?,?,?)",
        (
            "https://example.com/doc1",
            "ok",
            "Quarterly bulletin on AI in actuarial science",
            "AI",
            '["AI","actuarial","bulletin"]',
            5,
        ),
    )
    conn.execute(
        "INSERT INTO rag_chunks(chunk_id,kb_id,file_url,chunk_index,content,token_count) VALUES(?,?,?,?,?,?)",
        ("c1", "kb1", "https://example.com/doc2", 0, "machine learning for insurance", 10),
    )
    conn.commit()

    retriever = SimpleKeywordRetriever(db_path)
    results = retriever("actuarial bulletin", top_k=5)
    conn.close()

    assert len(results) >= 1
    doc_ids = {r.doc_id for r in results}
    assert "https://example.com/doc1" in doc_ids


def test_simple_keyword_retriever_no_match(tmp_path):
    """No results when query matches nothing."""
    import sqlite3

    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE catalog_items(file_url TEXT PRIMARY KEY, status TEXT, summary TEXT, category TEXT, keywords TEXT, rag_chunk_count INTEGER);
        CREATE TABLE files(url TEXT PRIMARY KEY, title TEXT, source_site TEXT, published_time TEXT);
        CREATE TABLE rag_chunks(chunk_id TEXT PRIMARY KEY, kb_id TEXT, file_url TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT, embedding_hash TEXT, created_at TEXT);
    """
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category) VALUES(?,?,?,?)",
        ("https://x.com/doc", "ok", "completely unrelated text", "general"),
    )
    conn.commit()

    retriever = SimpleKeywordRetriever(db_path)
    results = retriever("quantum physics", top_k=5)
    conn.close()

    assert results == []


def test_simple_keyword_retriever_deduplicates(tmp_path):
    """Multiple matches to same doc_id are deduplicated."""
    import sqlite3

    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE files(url TEXT PRIMARY KEY, title TEXT, source_site TEXT, published_time TEXT);
        CREATE TABLE catalog_items(file_url TEXT PRIMARY KEY, status TEXT, summary TEXT, category TEXT, keywords TEXT, rag_chunk_count INTEGER);
        CREATE TABLE rag_chunks(chunk_id TEXT PRIMARY KEY, kb_id TEXT, file_url TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT, embedding_hash TEXT, created_at TEXT);
    """
    )
    conn.execute(
        "INSERT INTO files(url,title) VALUES(?,?)",
        ("https://example.com/doc1", "Actuarial Report"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords) VALUES(?,?,?,?,?)",
        ("https://example.com/doc1", "ok", "actuarial report summary", "AI", '["actuarial"]'),
    )
    conn.execute(
        "INSERT INTO rag_chunks(chunk_id,kb_id,file_url,chunk_index,content,token_count) VALUES(?,?,?,?,?,?)",
        ("c1", "kb1", "https://example.com/doc1", 0, "actuarial report content", 5),
    )
    conn.execute(
        "INSERT INTO rag_chunks(chunk_id,kb_id,file_url,chunk_index,content,token_count) VALUES(?,?,?,?,?,?)",
        ("c2", "kb1", "https://example.com/doc1", 1, "more actuarial content", 5),
    )
    conn.commit()

    retriever = SimpleKeywordRetriever(db_path)
    results = retriever("actuarial", top_k=5)
    conn.close()

    # Should not return the same doc_id twice
    assert len(results) == 1
    assert results[0].doc_id == "https://example.com/doc1"


# ── CLI entry point smoke ─────────────────────────────────────────────────────


def test_main_help():
    """CLI --help works without crashing."""
    import os
    import subprocess
    import sys

    # Derive repo root from test file location so CI works
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    result = subprocess.run(
        [sys.executable, "-m", "ai_actuarial.agentic_rag.eval", "--help"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0
    assert "Run retrieval eval" in result.stdout

"""Tests for Agentic RAG eval scaffolding (PR0)."""

from __future__ import annotations

import json

import pytest

from ai_actuarial.agentic_rag.eval import (
    AgenticEvalCase,
    AgenticEvaluator,
    CaseResult,
    EvalCase,
    EvalReport,
    RetrievedItem,
    RetrievalEvaluator,
    SimpleKeywordRetriever,
    load_agentic_cases,
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


def test_evaluate_category_only_defaults_to_category_hit():
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_a", title="A", category="AI")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c6_default",
        query="any",
        expected_doc_ids=[],
        expected_categories=["AI"],
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.category_hits == 1


def test_evaluate_semicolon_separated_categories():
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_a", title="A", category="AI;regulation")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c7",
        query="ai regulation",
        expected_doc_ids=[],
        expected_categories=["AI"],
        min_hits=0,
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.category_hits == 1


def test_evaluate_semicolon_separated_expected_category_denominator():
    retriever = FakeRetriever(
        [RetrievedItem(doc_id="doc_a", title="A", category="AI;regulation")]
    )
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c7_expected",
        query="ai regulation",
        expected_doc_ids=[],
        expected_categories=["AI;regulation"],
        min_hits=0,
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.category_hits == 2
    assert result.details == "cat hits: 2/2"

    report = evaluator.evaluate([case])
    assert report.category_hit_rate == 1.0


def test_evaluate_reports_retrieved_ids_when_no_expectations():
    retriever = FakeRetriever([RetrievedItem(doc_id="doc_a", title="A")])
    evaluator = RetrievalEvaluator(retriever)
    case = EvalCase(
        case_id="c8",
        query="documented unsupported query",
        expected_doc_ids=[],
        expected_categories=[],
        min_hits=0,
    )
    result = evaluator.evaluate_case(case)
    assert result.passed is True
    assert result.total_retrieved == 1
    assert result.details == "retrieved: ['doc_a']"


def test_doc_hit_rate_ignores_category_only_failure():
    evaluator = RetrievalEvaluator(
        FakeRetriever([RetrievedItem(doc_id="doc_a", category="general")])
    )
    cases = [
        EvalCase(
            case_id="cat_only",
            query="q",
            expected_doc_ids=[],
            expected_categories=["AI"],
            min_hits=0,
        )
    ]
    report = evaluator.evaluate(cases)
    assert report.passed == 0
    assert report.failed == 1
    assert report.doc_hit_rate == 1.0
    assert report.category_hit_rate == 0.0


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


# ── Agentic answer/evidence evaluator ────────────────────────────────────────


def _write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_agentic_ready_data(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        output_dir / "doc_catalog.jsonl",
        [
            {
                "doc_id": "doc-reg",
                "file_url": "https://example.test/reg.pdf",
                "title": "Solvency Capital Regulation",
                "category": "regulation",
                "summary": "Article 19 defines required solvency capital factors.",
                "headings": ["Article 19"],
            },
            {
                "doc_id": "doc-formula",
                "file_url": "https://example.test/formula.pdf",
                "title": "Reserve Formula Note",
                "category": "formula",
                "summary": "Net premium formula documentation.",
                "headings": ["Net premium"],
            },
        ],
    )
    _write_jsonl(
        output_dir / "doc_summaries.jsonl",
        [
            {
                "doc_id": "doc-reg",
                "file_url": "https://example.test/reg.pdf",
                "title": "Solvency Capital Regulation",
                "category": "regulation",
                "summary": "Article 19 defines required solvency capital factors.",
            },
            {
                "doc_id": "doc-formula",
                "file_url": "https://example.test/formula.pdf",
                "title": "Reserve Formula Note",
                "category": "formula",
                "summary": "Net premium formula documentation.",
            },
        ],
    )
    _write_jsonl(
        output_dir / "sections.jsonl",
        [
            {
                "section_id": "doc-reg#article-19",
                "doc_id": "doc-reg",
                "heading_path": ["Article 19"],
                "text": "Article 19 defines required solvency capital factors.",
            }
        ],
    )
    _write_jsonl(
        output_dir / "sections_structured.jsonl",
        [
            {
                "section_id": "doc-reg#article-19",
                "doc_id": "doc-reg",
                "file_url": "https://example.test/reg.pdf",
                "title": "Solvency Capital Regulation",
                "heading_path": ["Article 19"],
                "heading": "Article 19",
                "text": "Article 19 defines required solvency capital factors.",
                "aliases": ["Article 19"],
            }
        ],
    )
    _write_jsonl(
        output_dir / "formula_cards.jsonl",
        [
            {
                "formula_id": "doc-formula#net-premium",
                "doc_id": "doc-formula",
                "file_url": "https://example.test/formula.pdf",
                "title": "Reserve Formula Note",
                "section_id": "doc-formula#net-premium",
                "heading_path": ["Net premium"],
                "heading": "Net premium",
                "formula_text": "Net Premium = PV Benefits / PV Premiums.",
                "context": "Net Premium = PV Benefits / PV Premiums.",
                "terms": ["Net Premium", "PV Benefits", "PV Premiums"],
            }
        ],
    )
    _write_jsonl(output_dir / "tables_structured.jsonl", [])
    _write_jsonl(output_dir / "calculation_terms.jsonl", [])
    (output_dir / "relations_graph.json").write_text(
        json.dumps(
            {
                "relations": [
                    {
                        "relation_type": "document_has_section",
                        "doc_id": "doc-reg",
                        "file_url": "https://example.test/reg.pdf",
                        "title": "Solvency Capital Regulation",
                        "section_id": "doc-reg#article-19",
                        "section_heading": "Article 19",
                        "target_type": "section",
                        "target_id": "doc-reg#article-19",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "ready_data_manifest.json").write_text(
        json.dumps(
            {
                "profile": "formula",
                "profile_version": "1",
                "artifact_files": [
                    "doc_catalog.jsonl",
                    "doc_summaries.jsonl",
                    "sections.jsonl",
                    "sections_structured.jsonl",
                    "formula_cards.jsonl",
                    "tables_structured.jsonl",
                    "calculation_terms.jsonl",
                    "relations_graph.json",
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_retrieval_eval_db(db_path):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE files(url TEXT PRIMARY KEY, title TEXT, source_site TEXT, published_time TEXT);
        CREATE TABLE catalog_items(file_url TEXT PRIMARY KEY, status TEXT, summary TEXT, category TEXT, keywords TEXT, rag_chunk_count INTEGER);
        CREATE TABLE rag_chunks(chunk_id TEXT PRIMARY KEY, kb_id TEXT, file_url TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT, embedding_hash TEXT, created_at TEXT);
    """
    )
    conn.execute(
        "INSERT INTO files(url,title,source_site) VALUES(?,?,?)",
        ("https://example.test/retrieval.pdf", "Retrieval Eval Bulletin", "SOA"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords,rag_chunk_count) VALUES(?,?,?,?,?,?)",
        (
            "https://example.test/retrieval.pdf",
            "ok",
            "Retrieval eval fixture for actuarial AI.",
            "AI",
            '["retrieval","eval","actuarial"]',
            1,
        ),
    )
    conn.commit()
    conn.close()


def test_agentic_evaluator_scores_evidence_citations_refusal_and_unsupported_guard(tmp_path):
    _write_agentic_ready_data(tmp_path)
    evaluator = AgenticEvaluator(output_dir=tmp_path, profile="formula", kb_id="kb-eval", limit=5)
    cases = [
        AgenticEvalCase(
            case_id="formula_evidence",
            query="How is net premium calculated?",
            expected_evidence_doc_ids=["doc-formula"],
            expected_evidence_sources=["formula_cards"],
            expected_citation_sources=["formula_cards"],
            forbidden_answer_terms=["guaranteed arbitrage"],
        ),
        AgenticEvalCase(
            case_id="regulation_evidence",
            query="How does Article 19 define solvency capital?",
            expected_evidence_doc_ids=["doc-reg"],
            expected_evidence_sources=["sections_structured"],
            expected_citation_sources=["sections_structured"],
        ),
        AgenticEvalCase(
            case_id="no_evidence_refusal",
            query="zzzxqv 2099 quantum rider",
            expect_no_evidence=True,
            min_evidence_hits=0,
        ),
    ]

    report = evaluator.evaluate(cases)

    assert report.total_cases == 3
    assert report.failed == 0
    assert report.evidence_hit_rate == 1.0
    assert report.citation_coverage_rate == 1.0
    assert report.no_evidence_refusal_rate == 1.0
    assert report.unsupported_answer_rate == 0.0
    assert report.per_case[0].passed is True
    assert report.per_case[0].evidence_hits == 1
    assert report.per_case[0].citation_coverage == 1.0
    assert report.per_case[0].citable_evidence >= 1
    assert report.per_case[2].refused_no_evidence is True


def test_agentic_evaluator_binds_doc_hits_to_expected_sources(tmp_path):
    _write_agentic_ready_data(tmp_path)
    evaluator = AgenticEvaluator(output_dir=tmp_path, profile="formula", limit=5)

    result = evaluator.evaluate_case(
        AgenticEvalCase(
            case_id="mixed_false_positive_guard",
            query="How is net premium calculated under Article 19?",
            expected_evidence_doc_ids=["doc-formula"],
            expected_evidence_sources=["sections_structured"],
            expected_citation_sources=["sections_structured"],
        )
    )

    assert result.passed is False
    assert result.evidence_hits == 0
    assert result.evidence_source_hits == 0
    assert result.citation_coverage == 0.0


def test_agentic_evaluator_flags_answer_without_evidence_anchor(monkeypatch, tmp_path):
    def fake_loop(**kwargs):
        return {
            "answer": "Found a claim that does not cite the grounded document.",
            "evidence": [
                {
                    "doc_id": "doc-grounded",
                    "title": "Grounded Reserve Note",
                    "source": "doc_summaries",
                    "sources": ["doc_summaries"],
                }
            ],
        }

    monkeypatch.setattr("ai_actuarial.agentic_rag.eval.run_agentic_rag_loop", fake_loop)
    evaluator = AgenticEvaluator(output_dir=tmp_path)

    result = evaluator.evaluate_case(
        AgenticEvalCase(
            case_id="ungrounded_answer",
            query="Explain reserves",
            expected_evidence_doc_ids=["doc-grounded"],
            expected_evidence_sources=["doc_summaries"],
        )
    )

    assert result.unsupported_answer is True
    assert result.passed is False


def test_agentic_evaluator_requires_citation_per_expected_doc_source_tuple(monkeypatch, tmp_path):
    def fake_loop(**kwargs):
        return {
            "answer": "Found 2 evidence item(s). Top evidence: Doc A; Doc B.",
            "evidence": [
                {
                    "doc_id": "doc-a",
                    "title": "Doc A",
                    "source": "doc_summaries",
                    "sources": ["doc_summaries"],
                },
                {
                    "doc_id": "doc-b",
                    "title": "Doc B",
                    "source": "doc_summaries",
                    "sources": ["doc_summaries"],
                },
            ],
            "citations": [
                {
                    "doc_id": "doc-a",
                    "title": "Doc A",
                    "source": "doc_summaries",
                    "sources": ["doc_summaries"],
                }
            ],
        }

    monkeypatch.setattr("ai_actuarial.agentic_rag.eval.run_agentic_rag_loop", fake_loop)
    evaluator = AgenticEvaluator(output_dir=tmp_path)

    result = evaluator.evaluate_case(
        AgenticEvalCase(
            case_id="partial_citation",
            query="Compare Doc A and Doc B",
            expected_evidence_doc_ids=["doc-a", "doc-b"],
            expected_evidence_sources=["doc_summaries"],
            expected_citation_sources=["doc_summaries"],
            min_evidence_hits=2,
        )
    )

    assert result.evidence_hits == 2
    assert result.citation_coverage == 0.5
    assert result.citable_evidence == 1
    assert result.passed is False


def test_load_agentic_cases_from_jsonl(tmp_path):
    cases_path = tmp_path / "agentic_cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "c1",
                "query": "How is net premium calculated?",
                "expected_evidence_doc_ids": ["doc-formula"],
                "expected_evidence_sources": ["formula_cards"],
                "expected_citation_sources": ["formula_cards"],
                "forbidden_answer_terms": ["unsupported"],
                "profile": "formula",
                "top_k": 3,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_agentic_cases(str(cases_path))

    assert cases == [
        AgenticEvalCase(
            case_id="c1",
            query="How is net premium calculated?",
            expected_evidence_doc_ids=["doc-formula"],
            expected_evidence_sources=["formula_cards"],
            expected_citation_sources=["formula_cards"],
            forbidden_answer_terms=["unsupported"],
            profile="formula",
            top_k=3,
        )
    ]


def test_load_agentic_cases_rejects_non_boolean_no_evidence_flag(tmp_path):
    cases_path = tmp_path / "agentic_cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "bad",
                "query": "bad case",
                "expect_no_evidence": "false",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expect_no_evidence must be a boolean"):
        load_agentic_cases(str(cases_path))


def test_agentic_cli_json_is_idempotent_and_ci_friendly(tmp_path):
    import os
    import subprocess
    import sys

    _write_agentic_ready_data(tmp_path)
    cases_path = tmp_path / "agentic_cases.jsonl"
    cases_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "formula_evidence",
                        "query": "How is net premium calculated?",
                        "expected_evidence_doc_ids": ["doc-formula"],
                        "expected_evidence_sources": ["formula_cards"],
                        "expected_citation_sources": ["formula_cards"],
                    }
                ),
                json.dumps(
                    {
                        "case_id": "no_evidence_refusal",
                        "query": "zzzxqv 2099 quantum rider",
                        "expect_no_evidence": True,
                        "min_evidence_hits": 0,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    command = [
        sys.executable,
        "-m",
        "ai_actuarial.agentic_rag.eval",
        "--mode",
        "agentic",
        "--cases",
        str(cases_path),
        "--output-dir",
        str(tmp_path),
        "--profile",
        "formula",
        "--json",
    ]

    first = subprocess.run(command, capture_output=True, text=True, cwd=repo_root)
    second = subprocess.run(command, capture_output=True, text=True, cwd=repo_root)

    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout)
    payload = json.loads(first.stdout)
    assert payload["mode"] == "agentic"
    assert payload["failed"] == 0
    assert payload["evidence_hit_rate"] == 1.0
    assert payload["citation_coverage_rate"] == 1.0
    assert payload["per_case"][0]["citable_evidence"] >= 1


def test_agentic_cli_json_returns_nonzero_on_failed_case(tmp_path):
    import os
    import subprocess
    import sys

    _write_agentic_ready_data(tmp_path)
    cases_path = tmp_path / "agentic_cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "wrong_source",
                "query": "How is net premium calculated under Article 19?",
                "expected_evidence_doc_ids": ["doc-formula"],
                "expected_evidence_sources": ["sections_structured"],
                "expected_citation_sources": ["sections_structured"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_actuarial.agentic_rag.eval",
            "--mode",
            "agentic",
            "--cases",
            str(cases_path),
            "--output-dir",
            str(tmp_path),
            "--profile",
            "formula",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failed"] == 1
    assert payload["per_case"][0]["passed"] is False


def test_retrieval_cli_json_with_temp_db(tmp_path):
    import os
    import subprocess
    import sys

    db_path = tmp_path / "retrieval.db"
    _write_retrieval_eval_db(db_path)
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "retrieval_fixture",
                "query": "retrieval eval actuarial",
                "expected_doc_ids": ["https://example.test/retrieval.pdf"],
                "expected_categories": ["AI"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_actuarial.agentic_rag.eval",
            "--mode",
            "retrieval",
            "--db",
            str(db_path),
            "--cases",
            str(cases_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] == 1
    assert payload["doc_hit_rate"] == 1.0


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

    conn.close()

    with SimpleKeywordRetriever(db_path) as retriever:
        results = retriever("actuarial bulletin", top_k=5)

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

    conn.close()

    with SimpleKeywordRetriever(db_path) as retriever:
        results = retriever("quantum physics", top_k=5)

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

    conn.close()

    with SimpleKeywordRetriever(db_path) as retriever:
        results = retriever("actuarial", top_k=5)

    # Should not return the same doc_id twice
    assert len(results) == 1
    assert results[0].doc_id == "https://example.com/doc1"


def test_simple_keyword_retriever_chunk_score_matches_ranking(tmp_path):
    """Chunk result score includes the same boost used for ranking."""
    import sqlite3

    db_path = str(tmp_path / "ranking.db")
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
        ("https://example.com/catalog", "Actuarial Catalog"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords) VALUES(?,?,?,?,?)",
        ("https://example.com/catalog", "ok", "actuarial", "AI", '["actuarial"]'),
    )
    conn.execute(
        "INSERT INTO rag_chunks(chunk_id,kb_id,file_url,chunk_index,content,token_count) VALUES(?,?,?,?,?,?)",
        ("c1", "kb1", "https://example.com/chunk", 0, "actuarial", 5),
    )
    conn.commit()
    conn.close()

    with SimpleKeywordRetriever(db_path) as retriever:
        results = retriever("actuarial", top_k=5)

    assert results[0].doc_id == "https://example.com/chunk"
    assert results[0].score == 1.5


def test_simple_keyword_retriever_context_manager_closes_connection(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "close.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE catalog_items(file_url TEXT PRIMARY KEY, status TEXT, summary TEXT, category TEXT, keywords TEXT, rag_chunk_count INTEGER);
        CREATE TABLE files(url TEXT PRIMARY KEY, title TEXT, source_site TEXT, published_time TEXT);
        CREATE TABLE rag_chunks(chunk_id TEXT PRIMARY KEY, kb_id TEXT, file_url TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT, embedding_hash TEXT, created_at TEXT);
    """
    )
    conn.commit()
    conn.close()

    with SimpleKeywordRetriever(db_path) as retriever:
        assert retriever("nothing", top_k=5) == []

    with pytest.raises(sqlite3.ProgrammingError):
        retriever("nothing", top_k=5)


def test_simple_keyword_retriever_top_k_zero_returns_empty(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "top_k.db")
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
        ("https://example.com/doc", "Actuarial Bulletin"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords) VALUES(?,?,?,?,?)",
        ("https://example.com/doc", "ok", "actuarial bulletin", "AI", '["actuarial"]'),
    )
    conn.commit()
    conn.close()

    with SimpleKeywordRetriever(db_path) as retriever:
        assert retriever("actuarial", top_k=0) == []
        assert retriever("actuarial", top_k=-1) == []


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

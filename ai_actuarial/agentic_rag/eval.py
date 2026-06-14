"""Eval scaffolding for Agentic RAG retrieval quality.

Defines eval case format, a configurable retrieval evaluator,
and metric computation. Does NOT depend on ready_data or vector
indexing — works against catalog_items and chunk data for the
first baseline measurement (PR0).

Usage (programmatic):
    from ai_actuarial.agentic_rag.eval import (
        EvalCase, RetrievalEvaluator, default_retriever, load_cases
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable, Protocol

logger = logging.getLogger(__name__)

# ── Data types ────────────────────────────────────────────────────────────────


@dataclass
class EvalCase:
    """A single retrieval eval case."""

    case_id: str
    query: str
    """Natural-language query the user might ask."""

    expected_doc_ids: list[str] = field(default_factory=list)
    """File URLs or doc_ids that should appear in top results."""

    expected_categories: list[str] = field(default_factory=list)
    """Categories (e.g. 'regulation', 'general') that results should match."""

    min_hits: int = 1
    """Minimum number of expected_doc_ids that must appear in top-k."""

    top_k: int = 5
    """Number of results to retrieve."""

    notes: str = ""
    """Human-readable explanation of what this case tests."""


@dataclass
class RetrievedItem:
    """A single retrieved item from any data source."""

    doc_id: str
    title: str = ""
    category: str = ""
    score: float = 0.0
    snippet: str = ""


@dataclass
class CaseResult:
    """Result of evaluating a single case."""

    case_id: str
    query: str
    hits: int = 0
    """Number of expected_doc_ids found in results."""

    category_hits: int = 0
    """Number of expected categories matched by retrieved items."""

    total_retrieved: int = 0
    passed: bool = False
    details: str = ""


@dataclass
class EvalReport:
    """Aggregated eval run report."""

    total_cases: int
    passed: int
    failed: int
    doc_hit_rate: float
    """Fraction of cases where at least min_hits expected_doc_ids were found."""

    category_hit_rate: float
    """Fraction of expected categories matched by retrieved items."""

    per_case: list[CaseResult] = field(default_factory=list)


# ── Retriever protocol ────────────────────────────────────────────────────────


class Retriever(Protocol):
    """Callable that takes a query and returns top-k RetrievedItems."""

    def __call__(self, query: str, top_k: int) -> list[RetrievedItem]: ...


# ── Simple keyword retriever (baseline) ───────────────────────────────────────


class SimpleKeywordRetriever:
    """Baseline retriever that searches catalog_items and rag_chunks in SQLite.

    This is intentionally simple — it represents the pre-ready_data baseline
    so we can measure improvement as agentic tools are added.
    """

    def __init__(self, db_path: str):
        import sqlite3

        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the SQLite connection held by this retriever."""
        self._conn.close()

    def __enter__(self) -> "SimpleKeywordRetriever":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __call__(self, query: str, top_k: int = 5) -> list[RetrievedItem]:
        import sqlite3

        terms = query.lower().split()
        results: list[tuple[float, RetrievedItem]] = []

        # Search catalog_items by title + summary + keywords
        try:
            rows = self._conn.execute(
                """SELECT c.file_url, f.title, c.category, c.summary, c.keywords
                   FROM catalog_items c
                   LEFT JOIN files f ON c.file_url = f.url
                   WHERE c.status = 'ok'"""
            ).fetchall()

            for row in rows:
                title = (row["title"] or row["file_url"] or "")
                summary = row["summary"] or ""
                keywords = row["keywords"] or ""
                category = row["category"] or "general"

                text = f"{title} {summary} {keywords}".lower()
                score = sum(1 for t in terms if t in text)
                if score > 0:
                    results.append(
                        (
                            score,
                            RetrievedItem(
                                doc_id=row["file_url"],
                                title=title,
                                category=category,
                                score=score,
                                snippet=summary[:200],
                            ),
                        )
                    )
        except sqlite3.OperationalError:
            pass

        # Search rag_chunks content
        try:
            chunk_rows = self._conn.execute(
                """SELECT c.chunk_id, c.file_url, c.content, c.section_hierarchy
                   FROM rag_chunks c"""
            ).fetchall()

            for row in chunk_rows:
                content = (row["content"] or "").lower()
                score = sum(1 for t in terms if t in content)
                if score > 0:
                    rank_score = score + 0.5
                    title = (row["section_hierarchy"] or "") or (row["file_url"] or "")
                    results.append(
                        (
                            rank_score,
                            RetrievedItem(
                                doc_id=row["file_url"],
                                title=title,
                                category="",
                                score=rank_score,
                                snippet=content[:200],
                            ),
                        )
                    )
        except sqlite3.OperationalError:
            pass

        # Sort descending by score, deduplicate by doc_id
        results.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        deduped: list[RetrievedItem] = []
        for _, item in results:
            if item.doc_id not in seen:
                seen.add(item.doc_id)
                deduped.append(item)
                if len(deduped) >= top_k:
                    break

        return deduped


# ── Evaluator ─────────────────────────────────────────────────────────────────


class RetrievalEvaluator:
    """Evaluates retrieval quality using a retriever and eval cases."""

    def __init__(self, retriever: Retriever):
        self._retriever = retriever

    def evaluate_case(self, case: EvalCase) -> CaseResult:
        """Evaluate a single case."""
        items = self._retriever(case.query, case.top_k)
        retrieved_ids = {item.doc_id for item in items}
        retrieved_cats = _category_labels(item.category for item in items)

        hit_ids = retrieved_ids & set(case.expected_doc_ids)
        hits = len(hit_ids)

        expected_cats = _category_labels(case.expected_categories)
        cat_hits = len(retrieved_cats & expected_cats) if expected_cats else 0

        passed = hits >= case.min_hits
        # When only categories are specified (no expected_doc_ids), require at least 1 category hit
        if not case.expected_doc_ids and case.expected_categories:
            if cat_hits == 0:
                passed = False
        details_parts: list[str] = []
        if hits > 0:
            details_parts.append(f"doc hits: {sorted(hit_ids)}")
        if not passed and case.expected_doc_ids:
            details_parts.append(f"expected: {case.expected_doc_ids}")
            details_parts.append(f"got top-{case.top_k}: {sorted(retrieved_ids)}")
        if case.expected_categories:
            details_parts.append(f"cat hits: {cat_hits}/{len(case.expected_categories)}")
        if not details_parts and items:
            details_parts.append(f"retrieved: {sorted(retrieved_ids)}")

        return CaseResult(
            case_id=case.case_id,
            query=case.query,
            hits=hits,
            category_hits=cat_hits,
            total_retrieved=len(items),
            passed=passed,
            details="; ".join(details_parts) if details_parts else "(no results)",
        )

    def evaluate(self, cases: list[EvalCase]) -> EvalReport:
        """Run all cases and produce a report."""
        results: list[CaseResult] = []
        for case in cases:
            result = self.evaluate_case(case)
            results.append(result)
            status = "✅" if result.passed else "❌"
            logger.info("%s %s: %s", status, case.case_id, result.details)

        passed = sum(1 for r in results if r.passed)
        total = len(results)

        # Doc hit rate: fraction of cases that met min_hits
        doc_hit_rate = passed / total if total > 0 else 0.0

        # Category hit rate across all results
        total_cat_expected = sum(len(c.expected_categories) for c in cases)
        total_cat_hits = sum(r.category_hits for r in results)
        cat_hit_rate = total_cat_hits / total_cat_expected if total_cat_expected > 0 else 0.0

        return EvalReport(
            total_cases=total,
            passed=passed,
            failed=total - passed,
            doc_hit_rate=doc_hit_rate,
            category_hit_rate=cat_hit_rate,
            per_case=results,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_cases(path: str) -> list[EvalCase]:
    """Load eval cases from a JSONL file."""
    cases: list[EvalCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            data = json.loads(line)
            cases.append(
                EvalCase(
                    case_id=data["case_id"],
                    query=data["query"],
                    expected_doc_ids=data.get("expected_doc_ids", []),
                    expected_categories=data.get("expected_categories", []),
                    min_hits=data.get("min_hits", 1),
                    top_k=data.get("top_k", 5),
                    notes=data.get("notes", ""),
                )
            )
    return cases


def _category_labels(categories: Iterable[str]) -> set[str]:
    labels: set[str] = set()
    for category in categories:
        labels.update(
            part.strip().casefold()
            for part in category.split(";")
            if part.strip()
        )
    return labels


def default_retriever(db_path: str | None = None) -> SimpleKeywordRetriever:
    """Create the default SimpleKeywordRetriever.

    Args:
        db_path: SQLite DB path. Defaults to env DB_PATH or data/index.db.
    """
    import os

    db_path = db_path or os.getenv("DB_PATH", "data/index.db")
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    return SimpleKeywordRetriever(db_path)


# ── CLI entry point ───────────────────────────────────────────────────────────


def main():
    """Run retrieval eval from the command line."""
    import argparse
    import os
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Run retrieval eval cases against the simple keyword retriever"
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Path to cases JSONL file (default: <repo_root>/eval/cases.jsonl)",
    )
    parser.add_argument("--db", default=None, help="SQLite DB path")
    parser.add_argument(
        "--json", action="store_true", help="Output report as JSON"
    )
    args = parser.parse_args()

    # Resolve cases path
    if args.cases:
        cases_path = args.cases
    else:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        cases_path = os.path.join(repo_root, "eval", "cases.jsonl")

    if not os.path.isfile(cases_path):
        print(f"Cases file not found: {cases_path}", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(cases_path)
    with default_retriever(args.db) as retriever:
        evaluator = RetrievalEvaluator(retriever)
        report = evaluator.evaluate(cases)

    if args.json:
        print(
            json.dumps(
                {
                    "total_cases": report.total_cases,
                    "passed": report.passed,
                    "failed": report.failed,
                    "doc_hit_rate": round(report.doc_hit_rate, 3),
                    "category_hit_rate": round(report.category_hit_rate, 3),
                    "per_case": [
                        {
                            "case_id": r.case_id,
                            "query": r.query,
                            "hits": r.hits,
                            "passed": r.passed,
                            "details": r.details,
                        }
                        for r in report.per_case
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(
            f"\n{'='*60}\n"
            f"Eval Report: {report.passed}/{report.total_cases} passed\n"
            f"Doc hit rate:   {report.doc_hit_rate:.1%}\n"
            f"Category hit rate: {report.category_hit_rate:.1%}\n"
            f"{'='*60}"
        )

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()

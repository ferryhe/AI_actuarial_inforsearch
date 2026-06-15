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
from pathlib import Path
from typing import Iterable, Protocol

from .agentic_loop import NO_EVIDENCE_ANSWER, run_agentic_rag_loop

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
    """Fraction of cases whose expected_doc_ids requirement was met."""

    category_hit_rate: float
    """Fraction of expected categories matched by retrieved items."""

    per_case: list[CaseResult] = field(default_factory=list)


@dataclass
class AgenticEvalCase:
    """A single deterministic Agentic RAG answer/evidence eval case."""

    case_id: str
    query: str
    expected_evidence_doc_ids: list[str] = field(default_factory=list)
    expected_evidence_sources: list[str] = field(default_factory=list)
    expected_citation_sources: list[str] = field(default_factory=list)
    forbidden_answer_terms: list[str] = field(default_factory=list)
    expect_no_evidence: bool = False
    min_evidence_hits: int = 1
    top_k: int = 5
    profile: str | None = None
    notes: str = ""


@dataclass
class AgenticCaseResult:
    """Result of evaluating one Agentic RAG loop response."""

    case_id: str
    query: str
    evidence_hits: int = 0
    evidence_source_hits: int = 0
    total_evidence: int = 0
    citation_coverage: float = 1.0
    citable_evidence: int = 0
    refused_no_evidence: bool = False
    unsupported_answer: bool = False
    passed: bool = False
    details: str = ""


@dataclass
class AgenticEvalReport:
    """Aggregated deterministic Agentic RAG eval report."""

    total_cases: int
    passed: int
    failed: int
    evidence_hit_rate: float
    citation_coverage_rate: float
    no_evidence_refusal_rate: float
    unsupported_answer_rate: float
    per_case: list[AgenticCaseResult] = field(default_factory=list)


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

        if top_k <= 0:
            return []

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
        expected_cat_count = len(expected_cats)
        cat_hits = len(retrieved_cats & expected_cats) if expected_cats else 0

        passed = hits >= case.min_hits
        # When only categories are specified (no expected_doc_ids), require at least 1 category hit
        if not case.expected_doc_ids and expected_cats:
            passed = cat_hits > 0
        details_parts: list[str] = []
        if hits > 0:
            details_parts.append(f"doc hits: {sorted(hit_ids)}")
        if not passed and case.expected_doc_ids:
            details_parts.append(f"expected: {case.expected_doc_ids}")
            details_parts.append(f"got top-{case.top_k}: {sorted(retrieved_ids)}")
        if case.expected_categories:
            details_parts.append(f"cat hits: {cat_hits}/{expected_cat_count}")
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

        # Doc hit rate: fraction of cases that met their doc expectation.
        # Cases without expected_doc_ids are not penalized by this metric.
        doc_met = [
            True if not case.expected_doc_ids else result.hits >= case.min_hits
            for case, result in zip(cases, results)
        ]
        doc_hit_rate = sum(1 for met in doc_met if met) / total if total > 0 else 0.0

        # Category hit rate across all expected category labels.
        total_cat_expected = sum(len(_category_labels(c.expected_categories)) for c in cases)
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


class AgenticEvaluator:
    """Evaluates deterministic Agentic RAG answer/evidence behavior."""

    def __init__(
        self,
        *,
        output_dir: str | Path,
        profile: str = "general",
        kb_id: str | None = None,
        limit: int = 10,
    ):
        self._output_dir = output_dir
        self._profile = profile
        self._kb_id = kb_id
        self._limit = limit

    def evaluate_case(self, case: AgenticEvalCase) -> AgenticCaseResult:
        response = run_agentic_rag_loop(
            query=case.query,
            output_dir=self._output_dir,
            profile=case.profile or self._profile,
            kb_id=self._kb_id,
            limit=case.top_k if case.top_k is not None else self._limit,
        )
        evidence = [item for item in response.get("evidence") or [] if isinstance(item, dict)]
        citations = [item for item in response.get("citations") or [] if isinstance(item, dict)]
        expected_doc_ids = set(case.expected_evidence_doc_ids)
        expected_sources = set(case.expected_evidence_sources)
        expected_citation_sources = set(case.expected_citation_sources or case.expected_evidence_sources)
        source_constraints = expected_sources or expected_citation_sources

        matched_evidence = _matching_evidence(
            evidence,
            expected_doc_ids=expected_doc_ids,
            expected_sources=source_constraints,
        )
        if expected_doc_ids:
            evidence_hits = len({_evidence_doc_id(item) for item in matched_evidence} & expected_doc_ids)
        else:
            evidence_hits = len(matched_evidence)
        matched_sources = _evidence_sources(matched_evidence)
        evidence_source_hits = len(matched_sources & expected_sources)
        matched_citations = _matching_evidence(
            citations,
            expected_doc_ids=expected_doc_ids,
            expected_sources=expected_citation_sources,
        )
        citable_evidence = [item for item in matched_citations if _has_citation_identity(item)]
        expected_citation_keys = _expected_identity_keys(
            expected_doc_ids=expected_doc_ids,
            expected_sources=expected_citation_sources,
        )
        citation_key_hits = _identity_key_hits(
            citable_evidence,
            expected_doc_ids=expected_doc_ids,
            expected_sources=expected_citation_sources,
        )
        citation_coverage = len(citation_key_hits) / len(expected_citation_keys) if expected_citation_keys else 1.0
        answer = str(response.get("answer") or "")
        refused_no_evidence = not evidence and answer == NO_EVIDENCE_ANSWER
        forbidden_terms = [term.casefold() for term in case.forbidden_answer_terms if term]
        unsupported_answer = (
            any(term in answer.casefold() for term in forbidden_terms)
            or (not evidence and answer != NO_EVIDENCE_ANSWER)
            or (bool(evidence) and not _answer_has_evidence_anchor(answer, evidence))
        )

        if case.expect_no_evidence:
            passed = refused_no_evidence and not unsupported_answer
        else:
            passed = (
                evidence_hits >= case.min_evidence_hits
                and evidence_source_hits >= len(expected_sources)
                and citation_coverage >= 1.0
                and not unsupported_answer
            )

        details_parts: list[str] = [
            f"evidence hits: {evidence_hits}/{len(expected_doc_ids)}",
            f"source hits: {evidence_source_hits}/{len(expected_sources)}",
            f"citation coverage: {citation_coverage:.3f}",
            f"citable evidence: {len(citable_evidence)}/{len(matched_evidence)}",
        ]
        if case.expect_no_evidence:
            details_parts.append(f"refused no-evidence: {refused_no_evidence}")
        if unsupported_answer:
            details_parts.append("unsupported answer terms found")

        return AgenticCaseResult(
            case_id=case.case_id,
            query=case.query,
            evidence_hits=evidence_hits,
            evidence_source_hits=evidence_source_hits,
            total_evidence=len(evidence),
            citation_coverage=citation_coverage,
            citable_evidence=len(citable_evidence),
            refused_no_evidence=refused_no_evidence,
            unsupported_answer=unsupported_answer,
            passed=passed,
            details="; ".join(details_parts),
        )

    def evaluate(self, cases: list[AgenticEvalCase]) -> AgenticEvalReport:
        results = [self.evaluate_case(case) for case in cases]
        total = len(results)
        passed = sum(1 for result in results if result.passed)
        evidence_cases = [case for case in cases if not case.expect_no_evidence]
        evidence_results = [
            result for case, result in zip(cases, results) if not case.expect_no_evidence
        ]
        no_evidence_results = [
            result for case, result in zip(cases, results) if case.expect_no_evidence
        ]
        evidence_hit_rate = (
            sum(
                1
                for case, result in zip(evidence_cases, evidence_results)
                if result.evidence_hits >= case.min_evidence_hits
            )
            / len(evidence_cases)
            if evidence_cases
            else 1.0
        )
        citation_coverage_rate = (
            sum(result.citation_coverage for result in evidence_results) / len(evidence_results)
            if evidence_results
            else 1.0
        )
        no_evidence_refusal_rate = (
            sum(1 for result in no_evidence_results if result.refused_no_evidence)
            / len(no_evidence_results)
            if no_evidence_results
            else 1.0
        )
        unsupported_answer_rate = (
            sum(1 for result in results if result.unsupported_answer) / total
            if total
            else 0.0
        )
        return AgenticEvalReport(
            total_cases=total,
            passed=passed,
            failed=total - passed,
            evidence_hit_rate=evidence_hit_rate,
            citation_coverage_rate=citation_coverage_rate,
            no_evidence_refusal_rate=no_evidence_refusal_rate,
            unsupported_answer_rate=unsupported_answer_rate,
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


def load_agentic_cases(path: str) -> list[AgenticEvalCase]:
    """Load deterministic Agentic RAG eval cases from JSONL."""
    cases: list[AgenticEvalCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            data = json.loads(line)
            case_id = _agentic_required_str(data, "case_id", path=path, line_no=line_no)
            cases.append(
                AgenticEvalCase(
                    case_id=case_id,
                    query=_agentic_required_str(data, "query", path=path, line_no=line_no),
                    expected_evidence_doc_ids=_agentic_str_list(data, "expected_evidence_doc_ids", path=path, line_no=line_no, case_id=case_id),
                    expected_evidence_sources=_agentic_str_list(data, "expected_evidence_sources", path=path, line_no=line_no, case_id=case_id),
                    expected_citation_sources=_agentic_str_list(data, "expected_citation_sources", path=path, line_no=line_no, case_id=case_id),
                    forbidden_answer_terms=_agentic_str_list(data, "forbidden_answer_terms", path=path, line_no=line_no, case_id=case_id),
                    expect_no_evidence=_agentic_bool(data, "expect_no_evidence", path=path, line_no=line_no, case_id=case_id, default=False),
                    min_evidence_hits=_agentic_int(data, "min_evidence_hits", path=path, line_no=line_no, case_id=case_id, default=1, minimum=0),
                    top_k=_agentic_int(data, "top_k", path=path, line_no=line_no, case_id=case_id, default=5, minimum=1),
                    profile=_agentic_optional_str(data, "profile", path=path, line_no=line_no, case_id=case_id),
                    notes=_agentic_optional_str(data, "notes", path=path, line_no=line_no, case_id=case_id) or "",
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


def _evidence_doc_id(item: dict[str, object]) -> str:
    return str(item.get("doc_id") or item.get("file_url") or "").strip()


def _item_sources(item: dict[str, object]) -> set[str]:
    sources: set[str] = set()
    raw_sources = item.get("sources")
    if isinstance(raw_sources, list):
        sources.update(str(source).strip() for source in raw_sources if str(source).strip())
    source = str(item.get("source") or "").strip()
    if source:
        sources.add(source)
    return sources


def _evidence_sources(evidence: Iterable[object]) -> set[str]:
    sources: set[str] = set()
    for raw in evidence:
        if not isinstance(raw, dict):
            continue
        sources.update(_item_sources(raw))
    return sources


def _matching_evidence(
    evidence: Iterable[dict[str, object]],
    *,
    expected_doc_ids: set[str],
    expected_sources: set[str],
) -> list[dict[str, object]]:
    matched: list[dict[str, object]] = []
    for item in evidence:
        doc_id = _evidence_doc_id(item)
        if expected_doc_ids and doc_id not in expected_doc_ids:
            continue
        if expected_sources and not (_item_sources(item) & expected_sources):
            continue
        matched.append(item)
    return matched


def _expected_identity_keys(*, expected_doc_ids: set[str], expected_sources: set[str]) -> set[tuple[str, str]]:
    if expected_doc_ids and expected_sources:
        return {(doc_id, source) for doc_id in expected_doc_ids for source in expected_sources}
    if expected_doc_ids:
        return {(doc_id, "") for doc_id in expected_doc_ids}
    if expected_sources:
        return {("", source) for source in expected_sources}
    return set()


def _identity_key_hits(
    evidence: Iterable[dict[str, object]],
    *,
    expected_doc_ids: set[str],
    expected_sources: set[str],
) -> set[tuple[str, str]]:
    hits: set[tuple[str, str]] = set()
    for item in evidence:
        doc_id = _evidence_doc_id(item)
        sources = _item_sources(item)
        if expected_doc_ids and expected_sources:
            for source in sources & expected_sources:
                if doc_id in expected_doc_ids:
                    hits.add((doc_id, source))
        elif expected_doc_ids:
            if doc_id in expected_doc_ids:
                hits.add((doc_id, ""))
        elif expected_sources:
            for source in sources & expected_sources:
                hits.add(("", source))
    return hits


def _has_citation_identity(item: dict[str, object]) -> bool:
    has_anchor = any(
        str(item.get(key) or "").strip()
        for key in (
            "doc_id",
            "file_url",
            "title",
            "section_id",
            "formula_id",
            "table_id",
            "term_id",
            "target_id",
        )
    )
    return has_anchor and bool(_item_sources(item))


def _answer_has_evidence_anchor(answer: str, evidence: Iterable[dict[str, object]]) -> bool:
    answer_lower = answer.casefold()
    if not answer_lower:
        return False
    for item in evidence:
        for key in (
            "title",
            "heading",
            "section_heading",
            "formula_id",
            "table_id",
            "term",
            "target_id",
            "doc_id",
            "file_url",
        ):
            value = str(item.get(key) or "").strip()
            if len(value) >= 4 and value.casefold() in answer_lower:
                return True
    return False


def _agentic_case_error(path: str, line_no: int, case_id: str | None, message: str) -> ValueError:
    prefix = f"{path}:{line_no}"
    if case_id:
        prefix += f" case {case_id}"
    return ValueError(f"{prefix}: {message}")


def _agentic_required_str(data: dict[str, object], key: str, *, path: str, line_no: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _agentic_case_error(path, line_no, None, f"{key} must be a non-empty string")
    return value


def _agentic_optional_str(
    data: dict[str, object],
    key: str,
    *,
    path: str,
    line_no: int,
    case_id: str,
) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _agentic_case_error(path, line_no, case_id, f"{key} must be a string")
    return value


def _agentic_str_list(
    data: dict[str, object],
    key: str,
    *,
    path: str,
    line_no: int,
    case_id: str,
) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _agentic_case_error(path, line_no, case_id, f"{key} must be a list of strings")
    return value


def _agentic_bool(
    data: dict[str, object],
    key: str,
    *,
    path: str,
    line_no: int,
    case_id: str,
    default: bool,
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise _agentic_case_error(path, line_no, case_id, f"{key} must be a boolean")
    return value


def _agentic_int(
    data: dict[str, object],
    key: str,
    *,
    path: str,
    line_no: int,
    case_id: str,
    default: int,
    minimum: int,
) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _agentic_case_error(path, line_no, case_id, f"{key} must be an integer >= {minimum}")
    return value


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
        description="Run retrieval eval or deterministic Agentic RAG answer/evidence eval cases"
    )
    parser.add_argument(
        "--mode",
        choices=["retrieval", "agentic"],
        default="retrieval",
        help="Eval mode to run (default: retrieval)",
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Path to cases JSONL file (default: <repo_root>/eval/cases.jsonl)",
    )
    parser.add_argument("--db", default=None, help="SQLite DB path")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Ready-data output directory for --mode agentic",
    )
    parser.add_argument("--profile", default="general", help="Ready-data profile for --mode agentic")
    parser.add_argument("--kb-id", default=None, help="Optional KB id included in Agentic loop output")
    parser.add_argument(
        "--json", action="store_true", help="Output report as JSON"
    )
    args = parser.parse_args()

    if args.cases:
        cases_path = args.cases
    else:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        filename = "agentic_cases.jsonl" if args.mode == "agentic" else "cases.jsonl"
        cases_path = os.path.join(repo_root, "eval", filename)

    if not os.path.isfile(cases_path):
        print(f"Cases file not found: {cases_path}", file=sys.stderr)
        sys.exit(1)

    if args.mode == "agentic":
        if not args.output_dir:
            print("--output-dir is required for --mode agentic", file=sys.stderr)
            sys.exit(2)
        cases = load_agentic_cases(cases_path)
        evaluator = AgenticEvaluator(
            output_dir=args.output_dir,
            profile=args.profile,
            kb_id=args.kb_id,
        )
        agentic_report = evaluator.evaluate(cases)
        if args.json:
            print(json.dumps(_agentic_report_payload(agentic_report), indent=2, ensure_ascii=False))
        else:
            print(
                f"\n{'='*60}\n"
                f"Agentic Eval Report: {agentic_report.passed}/{agentic_report.total_cases} passed\n"
                f"Evidence hit rate: {agentic_report.evidence_hit_rate:.1%}\n"
                f"Citation coverage: {agentic_report.citation_coverage_rate:.1%}\n"
                f"No-evidence refusal rate: {agentic_report.no_evidence_refusal_rate:.1%}\n"
                f"Unsupported answer rate: {agentic_report.unsupported_answer_rate:.1%}\n"
                f"{'='*60}"
            )
        sys.exit(0 if agentic_report.failed == 0 else 1)

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


def _agentic_report_payload(report: AgenticEvalReport) -> dict[str, object]:
    return {
        "mode": "agentic",
        "total_cases": report.total_cases,
        "passed": report.passed,
        "failed": report.failed,
        "evidence_hit_rate": round(report.evidence_hit_rate, 3),
        "citation_coverage_rate": round(report.citation_coverage_rate, 3),
        "no_evidence_refusal_rate": round(report.no_evidence_refusal_rate, 3),
        "unsupported_answer_rate": round(report.unsupported_answer_rate, 3),
        "per_case": [
            {
                "case_id": result.case_id,
                "query": result.query,
                "evidence_hits": result.evidence_hits,
                "evidence_source_hits": result.evidence_source_hits,
                "total_evidence": result.total_evidence,
                "citation_coverage": round(result.citation_coverage, 3),
                "citable_evidence": result.citable_evidence,
                "refused_no_evidence": result.refused_no_evidence,
                "unsupported_answer": result.unsupported_answer,
                "passed": result.passed,
                "details": result.details,
            }
            for result in report.per_case
        ],
    }


if __name__ == "__main__":
    main()

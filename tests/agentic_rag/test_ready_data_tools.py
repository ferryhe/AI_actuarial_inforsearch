from __future__ import annotations

import json
from pathlib import Path

from ai_actuarial.agentic_rag.ready_data_tools import (
    search_sections,
    search_summaries,
    search_titles,
    trace_relations,
)
from ai_actuarial.agentic_rag.tools import classify_question


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_ready_data(
    output_dir: Path,
    *,
    include_summaries: bool = True,
    summary_rows: list[dict[str, object]] | None = None,
    artifact_files: list[str] | dict[str, str] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs = [
        {
            "doc_id": "doc-capital",
            "file_url": "https://example.test/capital.pdf",
            "title": "Capital Adequacy Guideline",
            "category": "regulation",
            "summary": "Explains solvency capital requirements for insurers.",
            "headings": ["Capital requirement", "Risk charge"],
        },
        {
            "doc_id": "doc-reserve",
            "file_url": "https://example.test/reserve.pdf",
            "title": "Reserve Method Note",
            "category": "method",
            "summary": "Describes reserve calculation and liability assumptions.",
            "headings": ["Reserve calculation"],
        },
    ]
    _write_jsonl(output_dir / "doc_catalog.jsonl", docs)
    if include_summaries:
        _write_jsonl(
            output_dir / "doc_summaries.jsonl",
            summary_rows
            if summary_rows is not None
            else [
                {
                    "doc_id": "doc-capital",
                    "file_url": "https://example.test/capital.pdf",
                    "title": "Capital Adequacy Guideline",
                    "category": "regulation",
                    "summary": "Capital summary with solvency ratio and required capital.",
                },
                {
                    "doc_id": "doc-reserve",
                    "file_url": "https://example.test/reserve.pdf",
                    "title": "Reserve Method Note",
                    "category": "method",
                    "summary": "Reserve summary for actuarial liabilities.",
                },
            ],
        )
    _write_jsonl(
        output_dir / "sections.jsonl",
        [
            {
                "section_id": "s-capital",
                "doc_id": "doc-capital",
                "heading_path": ["Capital requirement"],
                "text": "Required capital is calibrated from risk charges.",
                "token_count": 10,
            },
            {
                "section_id": "s-reserve",
                "doc_id": "doc-reserve",
                "heading_path": ["Reserve calculation"],
                "text": "Reserve assumptions include discount rates.",
                "token_count": 9,
            },
        ],
    )
    (output_dir / "ready_data_manifest.json").write_text(
        json.dumps(
            {
                "profile": "general",
                "profile_version": "1",
                "artifact_files": artifact_files
                if artifact_files is not None
                else [
                    "doc_catalog.jsonl",
                    "doc_summaries.jsonl",
                    "sections.jsonl",
                    "ready_data_manifest.json",
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_search_summaries_ranks_summary_hits_and_limits(tmp_path: Path) -> None:
    _write_ready_data(tmp_path)

    results = search_summaries("solvency required capital", output_dir=str(tmp_path), limit=1)

    assert len(results) == 1
    assert results[0]["file_url"] == "https://example.test/capital.pdf"
    assert results[0]["title"] == "Capital Adequacy Guideline"
    assert results[0]["category"] == "regulation"
    assert results[0]["summary"].startswith("Capital summary")
    assert results[0]["score"] > 0
    assert results[0]["source"] == "doc_summaries"


def test_search_titles_scores_title_matches(tmp_path: Path) -> None:
    _write_ready_data(tmp_path)

    results = search_titles("reserve method", output_dir=str(tmp_path), limit=5)

    assert [item["file_url"] for item in results][:1] == ["https://example.test/reserve.pdf"]
    assert results[0]["title"] == "Reserve Method Note"
    assert results[0]["summary"]
    assert results[0]["source"] == "doc_catalog"


def test_search_titles_prefers_exact_alias_before_fallback_scoring(tmp_path: Path) -> None:
    _write_ready_data(tmp_path)
    _write_jsonl(
        tmp_path / "title_aliases.jsonl",
        [
            {
                "doc_id": "doc-reserve",
                "file_url": "https://example.test/reserve.pdf",
                "title": "Reserve Method Note",
                "aliases": ["RBC Rule 7", "Rule 7"],
                "identifiers": ["7"],
            }
        ],
    )
    manifest = json.loads((tmp_path / "ready_data_manifest.json").read_text(encoding="utf-8"))
    manifest["profile"] = "regulation"
    manifest["artifact_files"].append("title_aliases.jsonl")
    (tmp_path / "ready_data_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    results = search_titles("RBC Rule 7", output_dir=str(tmp_path), limit=5)

    assert results[0]["doc_id"] == "doc-reserve"
    assert results[0]["source"] == "title_aliases"
    assert results[0]["matched_alias"] == "RBC Rule 7"


def test_search_titles_does_not_match_short_numeric_alias_inside_longer_rule_number(tmp_path: Path) -> None:
    _write_ready_data(tmp_path)
    _write_jsonl(
        tmp_path / "title_aliases.jsonl",
        [
            {
                "doc_id": "doc-reserve",
                "file_url": "https://example.test/reserve.pdf",
                "title": "Reserve Method Note",
                "aliases": ["RBC Rule 7", "Rule 7"],
                "identifiers": ["7"],
                "rule_numbers": ["7"],
            },
            {
                "doc_id": "doc-capital",
                "file_url": "https://example.test/capital.pdf",
                "title": "RBC Rule 70 Capital Adequacy Guideline",
                "aliases": ["RBC Rule 70", "Rule 70"],
                "identifiers": ["70"],
                "rule_numbers": ["70"],
            },
        ],
    )
    manifest = json.loads((tmp_path / "ready_data_manifest.json").read_text(encoding="utf-8"))
    manifest["profile"] = "regulation"
    manifest["artifact_files"].append("title_aliases.jsonl")
    (tmp_path / "ready_data_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    results = search_titles("RBC Rule 70", output_dir=str(tmp_path), limit=5)

    assert results[0]["doc_id"] == "doc-capital"
    assert results[0]["matched_alias"] == "RBC Rule 70"
    assert all(not (item["doc_id"] == "doc-reserve" and item["source"] == "title_aliases") for item in results)


def test_search_sections_returns_stable_section_hits_from_l1_artifact(tmp_path: Path) -> None:
    _write_ready_data(tmp_path)
    _write_jsonl(
        tmp_path / "sections_structured.jsonl",
        [
            {
                "section_id": "doc-capital#article-19",
                "doc_id": "doc-capital",
                "file_url": "https://example.test/capital.pdf",
                "title": "Capital Adequacy Guideline",
                "heading_path": ["Chapter 2", "Article 19"],
                "heading": "Article 19",
                "text": "Article 19 defines solvency capital requirement factors.",
                "aliases": ["Article 19"],
            },
            {
                "section_id": "doc-reserve#article-5",
                "doc_id": "doc-reserve",
                "file_url": "https://example.test/reserve.pdf",
                "title": "Reserve Method Note",
                "heading_path": ["Article 5"],
                "heading": "Article 5",
                "text": "Discount assumptions support reserve calculations.",
            },
        ],
    )
    manifest = json.loads((tmp_path / "ready_data_manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_files"].append("sections_structured.jsonl")
    (tmp_path / "ready_data_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    results = search_sections("Article 19 solvency", output_dir=str(tmp_path), limit=1)

    assert results == [
        {
            "doc_id": "doc-capital",
            "file_url": "https://example.test/capital.pdf",
            "title": "Capital Adequacy Guideline",
            "section_id": "doc-capital#article-19",
            "heading_path": ["Chapter 2", "Article 19"],
            "heading": "Article 19",
            "text_snippet": "Article 19 defines solvency capital requirement factors.",
            "score": results[0]["score"],
            "source": "sections_structured",
        }
    ]
    assert results[0]["score"] > 0


def test_trace_relations_returns_alias_doc_section_edges(tmp_path: Path) -> None:
    _write_ready_data(tmp_path)
    (tmp_path / "relations_graph.json").write_text(
        json.dumps(
            {
                "relations": [
                    {
                        "relation_type": "alias_of",
                        "doc_id": "doc-capital",
                        "file_url": "https://example.test/capital.pdf",
                        "title": "Capital Adequacy Guideline",
                        "alias": "RBC Rule 3",
                        "target_type": "document",
                        "target_id": "doc-capital",
                    },
                    {
                        "relation_type": "document_has_section",
                        "doc_id": "doc-capital",
                        "file_url": "https://example.test/capital.pdf",
                        "title": "Capital Adequacy Guideline",
                        "section_id": "doc-capital#article-19",
                        "section_heading": "Article 19",
                        "target_type": "section",
                        "target_id": "doc-capital#article-19",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest = json.loads((tmp_path / "ready_data_manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_files"].append("relations_graph.json")
    (tmp_path / "ready_data_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    results = trace_relations("RBC Rule 3", output_dir=str(tmp_path), limit=5)

    assert [item["relation_type"] for item in results] == ["alias_of", "document_has_section"]
    assert all(item["doc_id"] == "doc-capital" for item in results)
    assert results[0]["source"] == "relations_graph"


def test_l1_tools_tolerate_missing_optional_artifacts(tmp_path: Path) -> None:
    _write_ready_data(tmp_path, include_summaries=False)

    assert search_sections("capital", output_dir=str(tmp_path), limit=3)[0]["source"] == "sections"
    assert trace_relations("capital", output_dir=str(tmp_path), limit=3) == []


def test_search_summaries_falls_back_to_catalog_summary_when_doc_summaries_missing(tmp_path: Path) -> None:
    _write_ready_data(tmp_path, include_summaries=False)

    results = search_summaries("liability assumptions", output_dir=str(tmp_path), limit=5)

    assert results[0]["file_url"] == "https://example.test/reserve.pdf"
    assert results[0]["summary"] == "Describes reserve calculation and liability assumptions."
    assert results[0]["source"] == "doc_catalog"


def test_search_summaries_keeps_catalog_docs_when_doc_summaries_are_partial(tmp_path: Path) -> None:
    _write_ready_data(
        tmp_path,
        summary_rows=[
            {
                "doc_id": "doc-capital",
                "file_url": "https://example.test/capital.pdf",
                "title": "Capital Adequacy Guideline",
                "category": "regulation",
                "summary": "Capital summary with solvency ratio.",
            }
        ],
    )

    results = search_summaries("liability assumptions", output_dir=str(tmp_path), limit=5)

    assert results[0]["file_url"] == "https://example.test/reserve.pdf"
    assert results[0]["summary"] == "Describes reserve calculation and liability assumptions."
    assert results[0]["source"] == "doc_catalog"


def test_search_tools_do_not_read_manifest_artifacts_outside_ready_data_dir(tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    _write_jsonl(
        outside,
        [
            {
                "doc_id": "outside",
                "file_url": "https://example.test/outside.pdf",
                "title": "Outside Secret",
                "category": "secret",
                "summary": "secret capital text",
            }
        ],
    )
    _write_ready_data(
        tmp_path,
        artifact_files={
            "doc_catalog.jsonl": "../outside.jsonl",
            "doc_summaries.jsonl": str(outside),
            "sections.jsonl": "sections.jsonl",
        },
    )

    title_results = search_titles("outside secret", output_dir=str(tmp_path), limit=5)
    summary_results = search_summaries("secret capital", output_dir=str(tmp_path), limit=5)

    assert all(item["file_url"] != "https://example.test/outside.pdf" for item in title_results)
    assert all(item["file_url"] != "https://example.test/outside.pdf" for item in summary_results)


def test_search_ready_data_missing_files_returns_empty_results(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)

    assert search_summaries("capital", output_dir=str(tmp_path)) == []
    assert search_titles("capital", output_dir=str(tmp_path)) == []


def test_classify_question_returns_l0_categories() -> None:
    assert classify_question("List all documents in the catalog") == "catalog"
    assert classify_question("Find the document titled Capital Adequacy Guideline") == "locate"
    assert classify_question("Summarize the reserve method note") == "summary"
    assert classify_question("How is required capital calculated?") == "document_qa"

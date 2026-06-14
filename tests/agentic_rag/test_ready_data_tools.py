from __future__ import annotations

import json
from pathlib import Path

from ai_actuarial.agentic_rag.ready_data_tools import search_summaries, search_titles
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

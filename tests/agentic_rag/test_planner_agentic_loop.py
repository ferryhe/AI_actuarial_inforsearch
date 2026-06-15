from __future__ import annotations

import json
from pathlib import Path

from ai_actuarial.agentic_rag.agentic_loop import run_agentic_rag_loop
from ai_actuarial.agentic_rag.planner import plan_tool_steps


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_ready_data(output_dir: Path, *, profile: str = "regulation", include_l1: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        output_dir / "doc_catalog.jsonl",
        [
            {
                "doc_id": "doc-capital",
                "file_url": "https://example.test/capital.pdf",
                "title": "Capital Adequacy Guideline",
                "category": "regulation",
                "summary": "Capital adequacy overview.",
                "headings": ["Capital", "Article 19"],
            },
            {
                "doc_id": "doc-reserve",
                "file_url": "https://example.test/reserve.pdf",
                "title": "Reserve Method Note",
                "category": "method",
                "summary": "Reserve method overview.",
                "headings": ["Reserve"],
            },
        ],
    )
    _write_jsonl(
        output_dir / "doc_summaries.jsonl",
        [
            {
                "doc_id": "doc-capital",
                "file_url": "https://example.test/capital.pdf",
                "title": "Capital Adequacy Guideline",
                "category": "regulation",
                "summary": "Article 19 solvency capital requirement summary.",
            },
            {
                "doc_id": "doc-reserve",
                "file_url": "https://example.test/reserve.pdf",
                "title": "Reserve Method Note",
                "category": "method",
                "summary": "Reserve assumptions summary.",
            },
        ],
    )
    _write_jsonl(
        output_dir / "sections.jsonl",
        [
            {
                "section_id": "doc-capital#1",
                "doc_id": "doc-capital",
                "heading_path": ["Capital"],
                "text": "Required capital appears in the solvency section.",
            }
        ],
    )
    artifact_files = ["doc_catalog.jsonl", "doc_summaries.jsonl", "sections.jsonl"]
    if include_l1:
        _write_jsonl(
            output_dir / "title_aliases.jsonl",
            [
                {
                    "doc_id": "doc-capital",
                    "file_url": "https://example.test/capital.pdf",
                    "title": "Capital Adequacy Guideline",
                    "aliases": ["RBC Rule 7", "Article 19 Capital Rule"],
                    "rule_numbers": ["7"],
                }
            ],
        )
        _write_jsonl(
            output_dir / "sections_structured.jsonl",
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
                }
            ],
        )
        (output_dir / "relations_graph.json").write_text(
            json.dumps(
                {
                    "relations": [
                        {
                            "relation_type": "document_has_section",
                            "doc_id": "doc-capital",
                            "file_url": "https://example.test/capital.pdf",
                            "title": "Capital Adequacy Guideline",
                            "section_id": "doc-capital#article-19",
                            "section_heading": "Article 19",
                            "target_type": "section",
                            "target_id": "doc-capital#article-19",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        artifact_files.extend(["title_aliases.jsonl", "sections_structured.jsonl", "relations_graph.json"])
    (output_dir / "ready_data_manifest.json").write_text(
        json.dumps({"profile": profile, "profile_version": "1", "artifact_files": artifact_files}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_planner_orders_locate_steps_before_summary_fallback() -> None:
    steps = plan_tool_steps("Find the document titled Capital Adequacy Guideline", profile="general")

    assert [step.tool_name for step in steps] == ["search_titles", "search_summaries"]
    assert all(step.category == "locate" for step in steps)


def test_planner_includes_regulation_tools_for_regulation_profile() -> None:
    steps = plan_tool_steps("How does Article 19 define solvency capital?", profile="regulation")

    assert [step.tool_name for step in steps] == [
        "search_sections",
        "search_summaries",
        "search_titles",
        "trace_relations",
    ]
    assert all(step.category == "document_qa" for step in steps)


def test_planner_includes_regulation_tools_when_l1_artifacts_are_available(tmp_path: Path) -> None:
    _write_ready_data(tmp_path, profile="general", include_l1=True)

    steps = plan_tool_steps("Summarize Article 19", profile="general", output_dir=tmp_path)

    assert [step.tool_name for step in steps] == [
        "search_summaries",
        "search_sections",
        "search_titles",
        "trace_relations",
    ]


def test_agentic_loop_returns_evidence_answer_and_trace_for_l1_regulation_tools(tmp_path: Path) -> None:
    _write_ready_data(tmp_path, profile="regulation", include_l1=True)

    response = run_agentic_rag_loop(
        query="How does Article 19 define solvency capital?",
        output_dir=tmp_path,
        profile="regulation",
        kb_id="kb-regulation",
        limit=3,
    )

    assert response["query"] == "How does Article 19 define solvency capital?"
    assert response["kb_id"] == "kb-regulation"
    assert response["profile"] == "regulation"
    assert response["output_dir"] == str(tmp_path)
    assert response["answer"].startswith("Found ")
    assert response["evidence"]
    assert response["results"] == response["evidence"]
    assert any(item["tool"] == "search_sections" for item in response["evidence"])
    assert any(item["tool"] == "trace_relations" for item in response["evidence"])
    tool_trace = response["metadata"]["tool_trace"]
    assert [step["tool_name"] for step in tool_trace] == [
        "search_sections",
        "search_summaries",
        "search_titles",
        "trace_relations",
    ]
    assert all(set(step) == {"tool_name", "status", "result_count", "error"} for step in tool_trace)
    assert all(step["status"] == "ok" for step in tool_trace)
    assert all(isinstance(step["result_count"], int) for step in tool_trace)


def test_agentic_loop_no_evidence_uses_clear_fallback_and_trace(tmp_path: Path) -> None:
    _write_ready_data(tmp_path, profile="general", include_l1=False)

    response = run_agentic_rag_loop(
        query="nonexistent phrase",
        output_dir=tmp_path,
        profile="general",
        limit=2,
    )

    assert response["evidence"] == []
    assert response["results"] == []
    assert response["answer"] == "No evidence found in ready_data for this query."
    assert response["metadata"]["evidence_count"] == 0
    assert response["metadata"]["tool_trace"]
    assert all(step["status"] == "ok" for step in response["metadata"]["tool_trace"])
    assert all(step["result_count"] == 0 for step in response["metadata"]["tool_trace"])

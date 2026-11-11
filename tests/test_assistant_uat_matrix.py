from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _normalize(question: str) -> str:
    return "".join(question.casefold().split())


def test_assistant_uat_matrix_is_independent_and_bilingual():
    matrix = json.loads((FIXTURES / "assistant_uat_questions.json").read_text(encoding="utf-8"))
    old_questions = json.loads(
        (FIXTURES / "assistant_help_questions.json").read_text(encoding="utf-8")
    )["questions"]
    question_rows, tasks = matrix["questions"], matrix["tasks"]

    assert matrix["gates"] == {
        "anchor_pass_percent": 100,
        "deterministic_pass_percent": 100,
        "held_out_route_and_target_percent": 90,
        "multi_turn_completion_percent": 90,
    }
    assert len({row["id"] for row in question_rows + tasks}) == len(question_rows) + len(tasks)
    assert Counter(row["language"] for row in question_rows) == {"zh": 32, "en": 32}
    assert Counter(row["language"] for row in tasks) == {"zh": 6, "en": 6}
    assert all(len(task["turns"]) >= 2 for task in tasks)

    question_texts = {_normalize(row["question"]) for row in question_rows}
    assert len(question_texts) == len(question_rows)
    assert question_texts.isdisjoint(_normalize(row["question"]) for row in old_questions)
    held_out = [row for row in question_rows if row["set"] == "held_out"]
    assert Counter(row["language"] for row in held_out) == {"zh": 12, "en": 12}
    prompt_files = [
        *(ROOT / "ai_actuarial" / "skills").glob("*/SKILL.md"),
        *(ROOT / "ai_actuarial" / "skills").glob("*/skill.json"),
        ROOT / "ai_actuarial" / "agent_runtime" / "loop.py",
        ROOT / "ai_actuarial" / "features" / "assistant" / "feature.py",
    ]
    for path in prompt_files:
        prompt = _normalize(path.read_text(encoding="utf-8"))
        assert all(_normalize(row["question"]) not in prompt for row in held_out), path

    assert {
        (row["question"], row["expect"]) for row in question_rows if row["set"] == "critical"
    }.issuperset({("SOA最近调研结果如何", "survey_findings"), ("怎么查看周报", "weekly_guide")})
    for expected in ("survey_findings", "weekly_guide"):
        for language in ("zh", "en"):
            assert any(
                row["expect"] == expected and row["language"] == language for row in held_out
            )


def test_assistant_uat_expectations_reference_current_tools_and_guide_sections():
    matrix = json.loads((FIXTURES / "assistant_uat_questions.json").read_text(encoding="utf-8"))
    expectations = matrix["expectations"]
    tools = {
        tool["tool_id"]
        for path in (ROOT / "ai_actuarial" / "skills").glob("*/skill.json")
        for tool in json.loads(path.read_text(encoding="utf-8"))["tools"]
    }
    for expectation in expectations.values():
        assert set(expectation) == {"tools", "target", "facts", "forbidden", "action", "date"}
        assert set(expectation["tools"]) <= tools

    guides = {
        language: (ROOT / "docs" / "help" / f"user-guide.{language}.md").read_text(encoding="utf-8")
        for language in ("zh", "en")
    }
    for row in matrix["questions"] + matrix["tasks"]:
        for turn in row.get("turns", [row]):
            assert 0 < len(turn["question"]) <= 4000
            expected = expectations[turn["expect"]]
            if "also_expect" in turn:
                assert turn["also_expect"] in expectations
            if turn["expect"] == "guide":
                assert turn["target"].startswith("guide:")
            target = turn.get("target", expected["target"])
            if target and target.startswith("guide:"):
                assert "{#" + target.removeprefix("guide:") + "}" in guides[row["language"]]


def test_assistant_uat_weekly_guide_scores_only_available_entries():
    matrix = json.loads((FIXTURES / "assistant_uat_questions.json").read_text(encoding="utf-8"))
    guide = matrix["expectations"]["weekly_guide"]
    tasks = {task["id"]: task for task in matrix["tasks"]}

    assert tasks["T03"]["scenario"] == "published_weekly"
    assert tasks["T03"]["turns"][0]["expect"] == "weekly_guide"
    assert tasks["T11"]["scenario"] == "no_weekly_snapshot"
    assert tasks["T11"]["turns"][1]["expect"] == "weekly_guide"
    assert tasks["T11"]["turns"][1]["also_expect"] == "weekly_data"

    assert (
        "If the Dashboard shows the weekly card, also describe Dashboard → View all → Weekly."
        in guide["facts"]
    )
    assert "A Dashboard View all entry when the weekly card is absent" in guide["forbidden"]
    assert "If no complete period has been published, say so." in guide["facts"]
    assert "older period" in guide["facts"]
    assert "/weekly" in guide["action"]
    assert "do not state zero additions" in tasks["T11"]["turns"][1]["require"]


def test_assistant_uat_t12_user_retry_is_a_separate_task_turn():
    matrix = json.loads((FIXTURES / "assistant_uat_questions.json").read_text(encoding="utf-8"))
    task = next(task for task in matrix["tasks"] if task["id"] == "T12")
    first, follow_up = task["turns"]

    assert task["scenario"] == "exhausted_quota"
    assert first["expect"] == follow_up["expect"] == "quota_exceeded"
    assert not first.get("user_requested_retry")
    assert follow_up["user_requested_retry"] is True
    assert "Read user guide (no AI)" in follow_up["before"]
    assert "Send a suggestion and cancel" in follow_up["before"]


def test_assistant_uat_soa_sources_distinguish_reachable_and_historical_urls():
    matrix = json.loads((FIXTURES / "assistant_uat_questions.json").read_text(encoding="utf-8"))
    spring = matrix["targets"]["soa_spring"]
    report_root = "https://www.soa.org/resources/research-reports"
    bulletin_path = (
        "/globalassets/assets/files/resources/research-report/2026/2026-03-ait170-ai-bulletin.pdf"
    )

    assert spring["source_url"] == f"{report_root}/soa-member-ai-survey/"
    assert (
        spring["unreachable_suggested_citation_url"] == f"{report_root}/2026/soa-member-ai-survey/"
    )
    assert spring["recruitment_url"] == f"https://www.soa.org{bulletin_path}"
    assert spring["unreachable_beta_recruitment_url"] == f"https://beta.soa.org{bulletin_path}"
    assert "source_alias" not in spring
    assert spring["publication_date"] == "2026-10-29"
    assert spring["stored_publication_date"] is None

    runbook = (ROOT / "docs" / "assistant-uat-gates.md").read_text(encoding="utf-8")
    for field in ("source_url", "recruitment_url"):
        assert f"]({spring[field]})" in runbook
    for field in ("unreachable_suggested_citation_url", "unreachable_beta_recruitment_url"):
        assert f"]({spring[field]})" not in runbook

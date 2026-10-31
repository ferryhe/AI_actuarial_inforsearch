from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ai_actuarial.api.services import weekly_explanations as weekly


def parse_source_response(raw, rows):
    return weekly._parse_reader_output(raw, [weekly._normalize_material_item(row) for row in rows])


def materials(count, *, long=False, summaries=True):
    return [
        {
            "url": f"https://example.org/{i}",
            "title": f"Study {i}",
            "summary": (
                (
                    f"A case study of method {i}. "
                    + ("\n\nDetails. " * 1000 if long else "Findings for practitioners.")
                )
                if summaries
                else ""
            ),
            "keywords": [f"topic-{i % 7}"],
            "first_seen": "2026-10-20T10:00:00+00:00",
        }
        for i in range(count)
    ]


def output(rows):
    articles = [
        {
            "url": row["url"],
            "excerpt": row["summary"][:100],
            "focus": row["keywords"][0] if row["summary"] else "",
        }
        for row in rows[:5]
    ]
    return json.dumps(
        {lang: {"themes": rows[0]["keywords"][:1], "articles": articles} for lang in ("zh", "en")}
    )


class Generator:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def generate(self, messages, *, timeout_seconds):
        self.calls.append((messages, timeout_seconds))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


class MemoryStorage:
    rows = []
    saved = None
    snapshot_id = "weekly-current"

    def __init__(self, _db):
        pass

    def close(self):
        pass

    def get_weekly_snapshot(self, **_kwargs):
        return {
            "id": self.snapshot_id,
            "file_count": len(self.rows),
            "period_start": "2026-10-19",
            "period_end": "2026-10-26",
        }

    def list_weekly_snapshot_files(self, *, offset=0, limit=500, **_kwargs):
        return self.rows[offset : offset + limit], len(self.rows)

    def get_weekly_explanation(self, **_kwargs):
        return self.saved

    def claim_weekly_explanation(self, attempt, **_kwargs):
        if (
            not _kwargs.get("force")
            and self.saved
            and (self.saved["status"] == "complete" or self.saved.get("error"))
            and self.saved["input_fingerprint"] == attempt["input_fingerprint"]
        ):
            return {"state": "complete", "explanation": self.saved}
        return {"state": "claimed", "claim_token": "claim"}

    def finalize_weekly_explanation(self, attempt, **_kwargs):
        type(self).saved = attempt
        return {"explanation": attempt}


@pytest.fixture
def memory(monkeypatch):
    MemoryStorage.rows = []
    MemoryStorage.saved = None
    MemoryStorage.snapshot_id = "weekly-current"
    monkeypatch.setattr(weekly, "Storage", MemoryStorage)
    runtime = SimpleNamespace(
        raw_config={"prompt": "Reader guide", "prompt_version": "v2", "timeout_seconds": 1000},
        stable_credential_id="",
        credential_id="",
        provider="test",
        model="test",
    )
    monkeypatch.setattr(weekly, "resolve_ai_function_runtime", lambda *_args, **_kwargs: runtime)
    return MemoryStorage


def test_empty_snapshot_never_resolves_or_calls_model(memory, monkeypatch):
    monkeypatch.setattr(
        weekly,
        "resolve_ai_function_runtime",
        lambda *_args, **_kwargs: pytest.fail("empty weeks must not resolve model runtime"),
    )
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=Generator([])
    )
    assert result["generation_mode"] == "empty"
    assert result["explanation_zh"] == "本周暂无新资料。"
    assert result["explanation_en"] == "No new material this week."


def test_bad_json_has_one_smaller_retry_then_readable_fallback(memory):
    memory.rows = materials(60, long=True)
    generator = Generator(["bad JSON", "bad JSON"])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["status"] == "failed"
    assert result["generation_mode"] == "fallback"
    assert "Study" in result["explanation_en"]
    assert len(generator.calls) == 2
    assert len(generator.calls[1][0][-1]["content"]) < len(generator.calls[0][0][-1]["content"])
    assert all(timeout <= 60 for _, timeout in generator.calls)
    assert memory.saved["coverage"]["call_count"] == 2


@pytest.mark.parametrize("count", [1, 5, 60, 216, 1116])
def test_selection_and_budgets(count):
    rows = materials(count, long=True)
    selected, audit = weekly._select_material(rows)
    assert len(selected) <= 60
    assert len(audit) == count
    messages, _, coverage, _ = weekly._build_generation_input(
        snapshot={"id": "current", "file_count": count},
        raw_material=selected,
        config={"prompt": "guide"},
        effective_credential_id="",
    )
    assert len(messages[1]["content"]) <= 26000
    assert sum(len(m["content"]) for m in messages) <= 32000
    assert coverage["material_chars"] <= 24000


def test_member_and_excerpt_validation():
    rows = materials(1)
    assert parse_source_response(output(rows), rows)[0]
    for field, value in [
        ("url", "https://example.org/previous-week"),
        ("excerpt", "Fabricated result"),
    ]:
        payload = json.loads(output(rows))
        payload["zh"]["articles"][0][field] = value
        with pytest.raises(ValueError):
            parse_source_response(json.dumps(payload), rows)


def test_identity_is_never_truncated():
    row = materials(1)[0]
    row["url"] += "?" + "a" * 800
    assert weekly._normalize_material_item(row)["url"] == row["url"]


def test_overlong_custom_prompt_falls_back_without_call(memory):
    memory.rows = materials(1)
    weekly.resolve_ai_function_runtime("", storage=None).raw_config["prompt"] = "x" * 33000
    generator = Generator([])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "fallback"
    assert not generator.calls


def test_focus_and_themes_cannot_invent_claims():
    rows = materials(1)
    for target, value in [("focus", "Invented topic"), ("themes", ["Invented topic"])]:
        payload = json.loads(output(rows))
        if target == "themes":
            payload["zh"][target] = value
        else:
            payload["zh"]["articles"][0][target] = value
        with pytest.raises(ValueError):
            parse_source_response(json.dumps(payload), rows)


def test_missing_summary_only_lists_title(memory):
    memory.rows = materials(1, summaries=False)
    generator = Generator([])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "fallback"
    assert generator.calls == []
    assert "Study 0" in result["explanation_en"]
    assert "For readers" not in result["explanation_en"]


def test_deadline_is_shared_across_both_calls(memory, monkeypatch):
    memory.rows = materials(5)
    now = [0.0]
    monkeypatch.setattr(weekly.time, "monotonic", lambda: now[0])

    class Slow:
        timeouts = []

        def generate(self, messages, *, timeout_seconds):
            self.timeouts.append(timeout_seconds)
            now[0] += 59.5
            return "not JSON"

    slow = Slow()
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=slow
    )
    assert result["generation_mode"] == "fallback"
    assert slow.timeouts == [60, 60]
    assert now[0] <= 120


def test_second_call_gets_only_remaining_deadline(memory, monkeypatch):
    memory.rows = materials(5)
    now = [0.0]
    monkeypatch.setattr(weekly.time, "monotonic", lambda: now[0])

    def call(generator, messages, timeout):
        generator.calls.append(timeout)
        now[0] += 60 if len(generator.calls) == 1 else 1
        if len(generator.calls) == 1:
            now[0] += 20  # parsing/recovery processing consumes the same deadline
        return "bad JSON"

    monkeypatch.setattr(weekly, "_call_with_deadline", call)
    generator = Generator([])
    weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert generator.calls == [60, 40]


def test_auth_and_configuration_do_not_retry(memory):
    from ai_actuarial.chatbot.exceptions import LLMAuthenticationError

    for error in (LLMAuthenticationError(), RuntimeError("Invalid model configuration")):
        memory.saved = None
        memory.rows = materials(1)
        generator = Generator([error])
        result = weekly.generate_weekly_explanation(
            db_path="fixture", snapshot_id="weekly-current", generator=generator
        )
        assert result["generation_mode"] == "fallback"
        assert len(generator.calls) == 1


def test_bounded_call_stops_waiting_for_generator_that_ignores_timeout():
    import time

    class Slow:
        def generate(self, *_args, **_kwargs):
            time.sleep(0.05)
            return "late"

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        weekly._call_with_deadline(Slow(), [], 0.005)
    assert time.monotonic() - started < 0.04


def test_output_tokens_and_small_model_context():
    assert weekly._output_tokens({}) == 2048
    assert weekly._output_tokens({"max_tokens": 9000}) == 4096
    assert weekly._output_tokens({"max_tokens": 9000, "model_max_output_tokens": 512}) == 512
    with pytest.raises(ValueError, match="context"):
        weekly._build_generation_input(
            snapshot={},
            raw_material=materials(1),
            config={"prompt": "guide", "model_context_tokens": 100},
            effective_credential_id="",
        )


def test_exact_old_default_migration_preserves_custom_prompt():
    from ai_actuarial.ai_runtime import (
        DEFAULT_WEEKLY_EXPLANATION_PROMPT,
        LEGACY_WEEKLY_EXPLANATION_PROMPT,
        get_ai_function_section,
    )

    legacy = get_ai_function_section(
        "weekly_explanation",
        yaml_config={
            "ai_config": {
                "weekly_explanation": {
                    "prompt": LEGACY_WEEKLY_EXPLANATION_PROMPT,
                    "prompt_version": "weekly-explanation-v1",
                }
            }
        },
    )
    assert legacy["prompt"] == DEFAULT_WEEKLY_EXPLANATION_PROMPT
    assert legacy["prompt_version"] == "weekly-reader-v2"
    custom = get_ai_function_section(
        "weekly_explanation",
        yaml_config={
            "ai_config": {
                "weekly_explanation": {
                    "prompt": LEGACY_WEEKLY_EXPLANATION_PROMPT + " ",
                    "prompt_version": "custom",
                }
            }
        },
    )
    assert custom["prompt"] == LEGACY_WEEKLY_EXPLANATION_PROMPT + " "
    assert custom["prompt_version"] == "custom"


def test_failed_fingerprint_cached_until_explicit_retry(memory):
    memory.rows = materials(1)
    failing = Generator(["bad JSON", "bad JSON"])
    first = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=failing
    )
    second = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=failing
    )
    assert first == second
    assert len(failing.calls) == 2
    successful = Generator([output(memory.rows)])
    retried = weekly.retry_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=successful
    )
    assert retried["generation_mode"] == "ai"
    assert (
        "Study 0"
        in weekly.get_weekly_explanation(db_path="fixture", snapshot_id="weekly-current")[
            "explanation_en"
        ]
    )


def test_preview_and_regenerate_preserve_snapshot_members(memory):
    memory.rows = materials(5)
    before = weekly.preview_weekly_explanation(db_path="fixture", snapshot_id="weekly-current")
    generator = Generator([output(memory.rows)])
    receipt = weekly.regenerate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    after = weekly.preview_weekly_explanation(db_path="fixture", snapshot_id="weekly-current")
    assert before["model_calls"] == after["model_calls"] == 0
    assert before["membership_sha256"] == after["membership_sha256"]
    assert receipt["receipt"]["before_membership_sha256"] == after["membership_sha256"]
    assert len(generator.calls) == 1


def test_cli_maintenance_preview_and_dry_run_are_gets(monkeypatch, capsys):
    from ai_actuarial import cli

    calls = []
    monkeypatch.setattr(
        cli,
        "_api_json_request",
        lambda *_args, **kwargs: calls.append((_args, kwargs)) or {"model_calls": 0},
    )
    for action, extra in (("preview", []), ("regenerate", ["--dry-run"])):
        args = cli.build_parser().parse_args(
            ["weekly", "explanation", action, "weekly-current", "--json", *extra]
        )
        assert args.func(args) == 0
        assert json.loads(capsys.readouterr().out)["model_calls"] == 0
        assert calls[-1][1]["method"] == "GET"
        assert calls[-1][0][1].endswith("/preview")


def test_overlong_output_gets_only_one_retry(memory):
    memory.rows = materials(5)
    generator = Generator(["x" * 21000, "x" * 21000])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "fallback"
    assert len(generator.calls) == 2
    assert memory.saved["coverage"]["error_category"] == "length"


def test_typed_schema_preserves_all_generation_modes():
    from ai_actuarial.api.routers.weekly_updates import WeeklyExplanationModel

    for mode, status in (("ai", "complete"), ("empty", "complete"), ("fallback", "failed")):
        parsed = WeeklyExplanationModel(
            snapshot_id="weekly-current",
            status=status,
            generation_mode=mode,
            explanation_zh="正文",
            explanation_en="Text",
            generated_at=None,
        )
        assert parsed.model_dump()["generation_mode"] == mode
        assert parsed.explanation_zh == "正文"
        assert parsed.explanation_en == "Text"
    assert (
        WeeklyExplanationModel(
            snapshot_id="weekly-current",
            status="missing",
            explanation_zh="",
            explanation_en="",
            generated_at=None,
        ).generation_mode
        is None
    )


def test_maintenance_routes_and_typed_preview_registered(memory):
    from ai_actuarial.api.routers.weekly_updates import (
        WeeklyExplanationMaintenancePreviewModel,
        api_weekly_explanation_preview,
        api_weekly_explanation_regenerate,
        router,
    )

    endpoints = [route.endpoint for route in router.routes]
    assert api_weekly_explanation_preview in endpoints
    assert api_weekly_explanation_regenerate in endpoints
    preview = WeeklyExplanationMaintenancePreviewModel.model_validate(
        weekly.preview_weekly_explanation(db_path="fixture", snapshot_id="weekly-current")
    )
    assert preview.budgets["snapshot_file_count"] == 0
    assert len(preview.membership_sha256) == 64


def test_candidate_selection_looks_beyond_ordinal_and_prefers_summaries():
    rows = materials(60, summaries=False) + materials(5)
    for i, row in enumerate(rows):
        row["url"] = f"https://example.org/{i}"
    selected, audit = weekly._select_material(rows)
    assert [row["url"] for row in selected[:5]] == [
        f"https://example.org/{i}" for i in range(60, 65)
    ]
    assert len(audit) == 65


def test_chat_model_limits_cannot_be_expanded_by_weekly_policy():
    from ai_actuarial.ai_runtime import get_ai_function_section

    section = get_ai_function_section(
        "weekly_explanation",
        yaml_config={
            "ai_config": {
                "chatbot": {"model_context_tokens": 1000, "model_max_output_tokens": 100},
                "weekly_explanation": {
                    "model_context_tokens": 4000,
                    "model_max_output_tokens": 1000,
                },
            }
        },
    )
    assert section["model_context_tokens"] == 1000
    assert section["model_max_output_tokens"] == 100


@pytest.mark.parametrize(
    ("summary", "excerpt"),
    [
        ("There is no evidence that this model is safe.", "this model is safe."),
        ("The model is not necessarily safe.", "safe."),
        ("目前没有证据证明该模型安全。", "该模型安全。"),
        ("Evidence does not establish safety", "safety"),
        (
            "One complete sentence. A second sentence. A third sentence.",
            "One complete sentence. A second sentence. A third sentence.",
        ),
    ],
)
def test_rejects_incomplete_or_more_than_two_source_sentences(summary, excerpt):
    rows = materials(1)
    rows[0]["summary"] = summary
    payload = json.loads(output(rows))
    for lang in ("zh", "en"):
        payload[lang]["articles"][0]["excerpt"] = excerpt
    with pytest.raises(ValueError):
        parse_source_response(json.dumps(payload), rows)


@pytest.mark.parametrize(
    ("summary", "excerpt"),
    [
        (
            "There is no evidence that this model is safe.",
            "There is no evidence that this model is safe.",
        ),
        (
            "Preliminary work is described. There is no evidence that this model is safe. More testing is required.",
            "There is no evidence that this model is safe. More testing is required.",
        ),
        ("目前没有证据证明该模型安全。仍需验证。", "目前没有证据证明该模型安全。仍需验证。"),
        ("Evidence does not establish safety", "Evidence does not establish safety"),
    ],
)
def test_accepts_complete_source_sentences_and_whole_short_paragraph(summary, excerpt):
    rows = materials(1)
    rows[0]["summary"] = summary
    payload = json.loads(output(rows))
    for lang in ("zh", "en"):
        payload[lang]["articles"][0]["excerpt"] = excerpt
    assert excerpt in parse_source_response(json.dumps(payload), rows)[1]


def test_incomplete_negation_excerpt_is_persisted_as_fallback(memory):
    memory.rows = materials(1)
    memory.rows[0]["summary"] = "There is no evidence that this model is safe."
    payload = json.loads(output(memory.rows))
    for lang in ("zh", "en"):
        payload[lang]["articles"][0]["excerpt"] = "this model is safe."
    generator = Generator([json.dumps(payload)])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["status"] == "failed"
    assert result["generation_mode"] == "fallback"
    assert "There is no evidence that this model is safe." in result["explanation_en"]
    assert memory.saved["coverage"]["error_category"] == "validation"
    assert len(generator.calls) == 1


@pytest.mark.parametrize("through_service", [False, True])
def test_multiple_country_abbreviations_use_conservative_fallback(memory, through_service):
    memory.rows = materials(1)
    sentence = "The report reviews U.S. insurers and U.K. insurers and compares their capital requirements."
    memory.rows[0]["summary"] = sentence
    payload = output(memory.rows)
    if through_service:
        result = weekly.generate_weekly_explanation(
            db_path="fixture", snapshot_id="weekly-current", generator=Generator([payload])
        )
        assert result["generation_mode"] == "fallback"
        assert result["status"] == "failed"
        assert "Study 0" in result["explanation_en"]
    else:
        with pytest.raises(ValueError):
            parse_source_response(payload, memory.rows)


def test_long_distinct_chinese_summaries_compact_before_exclusion(memory):
    import re

    from ai_actuarial.ai_runtime import DEFAULT_AI_FUNCTION_CONFIG

    topics = [
        ("风险定价", "研究使用历史理赔数据比较风险定价方法，并说明精算人员可复核的模型假设。"),
        ("准备金评估", "报告分析保险合同准备金的估计差异，并提供针对长期负债的情景测试方法。"),
        ("资本管理", "案例讨论不同保险业务的资本配置，并展示资本约束下调整资产组合的步骤。"),
        ("客户服务", "实验比较客户服务流程的响应质量，并列出人工复核保险答复时需要检查的项目。"),
        ("模型治理", "调查梳理模型治理过程中的责任分工，并提出审查数据变更和模型记录的方法。"),
    ]
    memory.rows = []
    for i, (topic, first_sentence) in enumerate(topics):
        prefix = first_sentence + f"本篇围绕{topic}提供独立的资料来源和应用背景。"
        summary = (
            prefix
            + f"附录说明{topic}的分析口径"
            + (topic * 300)[: 498 - len(prefix) - len(f"附录说明{topic}的分析口径") - 1]
            + "。"
        )
        memory.rows.append(
            {
                "url": f"https://example.org/long-{i}",
                "title": f"{topic}研究",
                "summary": summary,
                "keywords": [topic],
                "category": topic,
                "first_seen": "2026-10-20",
            }
        )
    assert len({row["summary"] for row in memory.rows}) == 5
    assert all(497 <= len(row["summary"]) <= 501 for row in memory.rows)
    runtime = weekly.resolve_ai_function_runtime("", storage=None)
    runtime.raw_config = dict(DEFAULT_AI_FUNCTION_CONFIG["weekly_explanation"])
    originals = {row["url"]: row for row in memory.rows}

    class Grounded:
        calls = []

        def generate(self, messages, *, timeout_seconds):
            self.calls.append(messages)
            rows = [
                json.loads(block)
                for block in re.findall(
                    r"BEGIN_UNTRUSTED_FILE_MATERIAL \d+\n(.*?)\nEND_UNTRUSTED_FILE_MATERIAL",
                    messages[-1]["content"],
                    re.S,
                )
            ]
            articles = [
                {
                    "url": row["url"],
                    "excerpt": originals[row["url"]]["summary"].split("。")[0] + "。",
                    "focus": row["keywords"][0],
                }
                for row in rows[:5]
            ]
            return json.dumps(
                {
                    lang: {"themes": [rows[0]["keywords"][0]], "articles": articles}
                    for lang in ("zh", "en")
                }
            )

    generator = Grounded()
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    audit = memory.saved["coverage"]
    assert result["generation_mode"] == "ai"
    assert audit["recommendation_count"] == 5
    assert audit["selected_count"] == 5
    assert 0 < audit["candidate_count"] <= 60
    assert 0 < audit["call_count"] <= 2
    assert len(generator.calls) == 1
    assert audit["material_chars"] <= 24000
    assert audit["user_chars"] <= 26000
    assert audit["all_message_chars"] <= 32000
    assert (
        audit["token_upper_bound"] + audit["max_output_tokens"] <= audit["context_tokens"] == 8000
    )
    assert audit["max_output_tokens"] == 2048
    assert audit["max_output_tokens"] <= 4096
    assert len(audit["material_compressions"]) == 5
    messages = generator.calls[0]
    rows = [
        json.loads(block)
        for block in re.findall(
            r"BEGIN_UNTRUSTED_FILE_MATERIAL \d+\n(.*?)\nEND_UNTRUSTED_FILE_MATERIAL",
            messages[-1]["content"],
            re.S,
        )
    ]
    assert len(rows) == 5
    for row in rows:
        assert len(json.dumps(row, ensure_ascii=False, sort_keys=True)) <= 2000
        assert row["url"] in originals
        assert row["summary"] in originals[row["url"]]["summary"]
        assert weekly._complete_source_excerpt(row["summary"], originals[row["url"]]["summary"])
        assert row["url"] in result["explanation_zh"]
        assert row["url"] in result["explanation_en"]


def test_abbreviation_handling_still_rejects_a_negation_fragment():
    rows = materials(1)
    rows[0][
        "summary"
    ] = "There is no evidence that U.S. insurers and U.K. insurers are safe. More validation is required."
    payload = json.loads(output(rows))
    for lang in ("zh", "en"):
        payload[lang]["articles"][0]["excerpt"] = "insurers are safe."
    with pytest.raises(ValueError):
        parse_source_response(json.dumps(payload), rows)


def test_budget_compaction_does_not_split_an_irreducible_paragraph_or_identity():
    from ai_actuarial.ai_runtime import DEFAULT_AI_FUNCTION_CONFIG

    rows = materials(5)
    for row in rows:
        row["summary"] = "保险风险评估" * 150
        row["url"] += "?reference=" + "a" * 400
    messages, _, coverage, _ = weekly._build_generation_input(
        snapshot={"file_count": 5},
        raw_material=rows,
        config=DEFAULT_AI_FUNCTION_CONFIG["weekly_explanation"],
        effective_credential_id="",
    )
    assert coverage["material_rows_included"] < 3
    assert coverage["material_compressions"] == []
    assert coverage["budget_exclusions"]
    assert coverage["token_upper_bound"] + coverage["max_output_tokens"] <= 8000
    for row in rows:
        assert row["summary"] == weekly._normalize_material_item(row)["summary"]
        if row["url"] not in {entry["url"] for entry in coverage["budget_exclusions"]}:
            assert row["url"] in messages[1]["content"]


@pytest.mark.parametrize(
    "summary",
    [
        "The report compares U.S. GAAP and U.K. GAAP capital requirements.",
        "The report evaluates U.S. GAAP. It provides worked examples for actuaries.",
    ],
)
@pytest.mark.parametrize("through_service", [False, True])
def test_gaap_ambiguity_above_two_potential_ends_uses_fallback(memory, summary, through_service):
    memory.rows = materials(1)
    memory.rows[0]["summary"] = summary
    payload = output(memory.rows)
    if through_service:
        result = weekly.generate_weekly_explanation(
            db_path="fixture", snapshot_id="weekly-current", generator=Generator([payload])
        )
        assert result["status"] == "failed"
        assert result["generation_mode"] == "fallback"
        assert "Study 0" in result["explanation_en"]
    else:
        with pytest.raises(ValueError):
            parse_source_response(payload, memory.rows)


@pytest.mark.parametrize(
    ("summary", "fragment"),
    [
        (
            "The report compares U.S. GAAP and U.K. GAAP capital requirements.",
            "GAAP and U.K. GAAP capital requirements.",
        ),
        ("There is no evidence that U.S. GAAP models are safe.", "GAAP models are safe."),
        (
            "The report evaluates U.S. GAAP. It gives examples. More work is required.",
            "The report evaluates U.S. GAAP. It gives examples. More work is required.",
        ),
    ],
)
def test_gaap_does_not_allow_sentence_head_or_negation_fragments(summary, fragment):
    rows = materials(1)
    rows[0]["summary"] = summary
    payload = json.loads(output(rows))
    for lang in ("zh", "en"):
        payload[lang]["articles"][0]["excerpt"] = fragment
    with pytest.raises(ValueError):
        parse_source_response(json.dumps(payload), rows)


def test_gaap_ambiguity_cannot_become_a_source_through_compaction():
    first = "The report compares U.S. GAAP and U.K. GAAP capital requirements."
    rows = materials(1)
    rows[0]["summary"] = first + " It gives worked examples. " + "Additional source detail. " * 30
    messages, _, audit, _ = weekly._build_generation_input(
        snapshot={"file_count": 1},
        raw_material=rows,
        config={"prompt": "Guide"},
        effective_credential_id="",
    )
    assert "BEGIN_UNTRUSTED_FILE_MATERIAL" not in messages[1]["content"]
    assert audit["budget_exclusions"][0]["reason"] == "summary_missing_or_incomplete"


@pytest.mark.parametrize("qualified_count", [1, 2])
def test_only_qualified_summaries_count_for_normal_reading_guide(memory, qualified_count):
    memory.rows = materials(5, summaries=False)
    for i in range(qualified_count):
        memory.rows[i]["summary"] = f"The study compares reserving methods for portfolio {i}."
    generator = Generator([output(memory.rows[:qualified_count])])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["status"] == "complete"
    assert result["generation_mode"] == "ai"
    assert memory.saved["coverage"]["recommendation_count"] == qualified_count
    assert memory.saved["coverage"]["qualified_count"] == qualified_count
    assert memory.saved["coverage"]["selected_count"] == qualified_count
    assert len(memory.rows) == 5
    for row in memory.rows[qualified_count:]:
        assert row["url"] not in generator.calls[0][0][1]["content"]


def test_empty_summaries_cannot_pad_the_normal_recommendation_count():
    rows = materials(5, summaries=False)
    rows[0]["summary"] = "The study compares reserving methods."
    payload = json.loads(output(rows[:3]))
    with pytest.raises(ValueError):
        parse_source_response(json.dumps(payload), rows)


def test_five_qualified_summaries_still_require_at_least_three():
    rows = materials(5)
    with pytest.raises(ValueError):
        parse_source_response(output(rows[:2]), rows)


def test_missing_summary_titles_remain_readable_in_fallback(memory):
    memory.rows = materials(5, summaries=False)
    memory.rows[0]["summary"] = "The study compares reserving methods."
    result = weekly.generate_weekly_explanation(
        db_path="fixture",
        snapshot_id="weekly-current",
        generator=Generator(["bad JSON", "bad JSON"]),
    )
    assert result["generation_mode"] == "fallback"
    assert "Study 4" in result["explanation_en"]
    assert "https://example.org/4" in result["explanation_en"]


@pytest.mark.parametrize(
    "chat_key,weekly_key",
    [
        ("max_context_tokens", "model_context_tokens"),
        ("model_context_tokens", "max_context_tokens"),
    ],
)
def test_real_resolver_service_enforces_cross_context_minimum(monkeypatch, chat_key, weekly_key):
    import re

    import tiktoken

    from config import yaml_config

    MemoryStorage.rows = materials(60)
    summary = (
        "This case study compares reserving methods on historical insurance claims. "
        "It presents the assumptions used in the analysis and explains the effect of different reporting periods. "
        "Worked examples show how actuaries can review model results and identify sources of estimation uncertainty."
    )
    for row in MemoryStorage.rows:
        row["summary"] = summary
    MemoryStorage.saved = None
    MemoryStorage.snapshot_id = "weekly-current"
    monkeypatch.setattr(weekly, "Storage", MemoryStorage)
    monkeypatch.setattr(
        yaml_config,
        "load_ai_config",
        lambda: {
            "chatbot": {"provider": "local", "model": "gpt-4o-mini", chat_key: 4096},
            "weekly_explanation": {weekly_key: 16000},
        },
    )

    class Grounded:
        calls = []

        def generate(self, messages, *, timeout_seconds):
            self.calls.append(messages)
            rows = [
                json.loads(block)
                for block in re.findall(
                    r"BEGIN_UNTRUSTED_FILE_MATERIAL \d+\n(.*?)\nEND_UNTRUSTED_FILE_MATERIAL",
                    messages[-1]["content"],
                    re.S,
                )
            ]
            articles = [
                {
                    "url": row["url"],
                    "excerpt": "This case study compares reserving methods on historical insurance claims.",
                    "focus": row["keywords"][0],
                }
                for row in rows[:3]
            ]
            return json.dumps(
                {
                    lang: {"themes": [rows[0]["keywords"][0]], "articles": articles}
                    for lang in ("zh", "en")
                }
            )

    generator = Grounded()
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["status"] == "complete"
    assert len(generator.calls) == 1
    encoding = tiktoken.encoding_for_model("gpt-4o-mini")
    actual = sum(len(encoding.encode(message["content"])) for message in generator.calls[0])
    audit = MemoryStorage.saved["coverage"]
    assert actual + audit["max_output_tokens"] <= 4096
    assert audit["context_tokens"] == 4096
    assert audit["token_upper_bound"] + audit["max_output_tokens"] <= 4096
    assert audit["candidate_count"] <= 60
    assert audit["user_chars"] <= 26000
    assert audit["all_message_chars"] <= 32000


def test_real_resolver_too_small_context_falls_back_before_generator(monkeypatch):
    from config import yaml_config

    MemoryStorage.rows = materials(5)
    MemoryStorage.saved = None
    MemoryStorage.snapshot_id = "weekly-current"
    monkeypatch.setattr(weekly, "Storage", MemoryStorage)
    monkeypatch.setattr(
        yaml_config,
        "load_ai_config",
        lambda: {
            "chatbot": {"provider": "local", "model": "gpt-4o-mini", "max_context_tokens": 2000},
            "weekly_explanation": {"model_context_tokens": 16000},
        },
    )
    generator = Generator([output(MemoryStorage.rows)])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert generator.calls == []
    assert result["generation_mode"] == "fallback"
    assert MemoryStorage.saved["coverage"]["error_category"] == "configuration"

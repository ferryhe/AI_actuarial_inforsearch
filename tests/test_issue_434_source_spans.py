from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from ai_actuarial.api.services import weekly_explanations as weekly
from tests.test_issue_434_weekly_reader import Generator, MemoryStorage, materials


def parse_source_response(raw, rows):
    return weekly._parse_reader_output(raw, [weekly._normalize_material_item(row) for row in rows])


def response(row, excerpt):
    return json.dumps(
        {
            lang: {
                "themes": row["keywords"][:1],
                "articles": [{"url": row["url"], "excerpt": excerpt, "focus": row["keywords"][0]}],
            }
            for lang in ("zh", "en")
        }
    )


@pytest.fixture
def span_memory(monkeypatch):
    MemoryStorage.rows = materials(1)
    MemoryStorage.saved = None
    MemoryStorage.snapshot_id = "weekly-current"
    monkeypatch.setattr(weekly, "Storage", MemoryStorage)
    runtime = SimpleNamespace(
        raw_config={"prompt": "Guide", "prompt_version": "span-test"},
        stable_credential_id="",
        credential_id="",
        provider="fixture",
        model="fixture",
    )
    monkeypatch.setattr(weekly, "resolve_ai_function_runtime", lambda *_args, **_kwargs: runtime)
    return MemoryStorage


@pytest.mark.parametrize(
    ("summary", "fragment"),
    [
        (
            "There is no evidence that U.S. Treasury bond portfolios are safe.",
            "Treasury bond portfolios are safe.",
        ),
        (
            "There is no evidence under Sec. 5 that portfolios are safe.",
            "5 that portfolios are safe.",
        ),
    ],
)
def test_ambiguous_period_never_creates_a_context_deleting_start(span_memory, summary, fragment):
    row = span_memory.rows[0]
    row["summary"] = summary
    with pytest.raises(ValueError):
        parse_source_response(response(row, fragment), [row])


@pytest.mark.parametrize("retry", [False, True])
def test_treasury_fragment_is_fallback_in_normal_and_retry_service(span_memory, retry):
    row = span_memory.rows[0]
    row["summary"] = "There is no evidence that U.S. Treasury bond portfolios are safe."
    replies = (["invalid JSON"] if retry else []) + [
        response(row, "Treasury bond portfolios are safe.")
    ]
    generator = Generator(replies)
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "fallback"
    assert result["status"] == "failed"
    assert len(generator.calls) == (2 if retry else 1)
    assert "There is no evidence" in result["explanation_en"]


def test_parser_cannot_accept_an_original_sentence_that_was_not_sent(span_memory):
    row = span_memory.rows[0]
    first = "The study " + "carefully " * 18 + "compares reserving methods."
    second = "The report " + "thoroughly " * 18 + "presents worked examples."
    unseen = "No evidence establishes that these portfolios are safe."
    row["summary"] = " ".join([first, second, unseen])
    generator = Generator([response(row, unseen)])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert unseen not in generator.calls[0][0][1]["content"]
    assert result["generation_mode"] == "fallback"
    assert span_memory.saved["coverage"]["error_category"] == "validation"


def test_builder_returns_the_actual_sent_material_and_original_span_identity():
    row = materials(1)[0]
    row["summary"] = (
        "The study compares reserving methods. It provides worked examples. It identifies limitations."
    )
    result = weekly._build_generation_input(
        snapshot={"file_count": 1},
        raw_material=[row],
        config={"prompt": "Guide"},
        effective_credential_id="",
    )
    assert len(result) == 4
    messages, _, _, sent = result
    payload = json.loads(
        re.search(
            r"BEGIN_UNTRUSTED_FILE_MATERIAL 1\n(.*?)\nEND_UNTRUSTED_FILE_MATERIAL",
            messages[1]["content"],
            re.S,
        ).group(1)
    )
    assert sent[0]["summary"] == payload["summary"]
    assert sent[0]["_source_summary"] == row["summary"]
    assert sent[0]["_spans"]
    assert all(
        row["summary"][span["start"] : span["end"]] == span["text"] for span in sent[0]["_spans"]
    )
    assert "_source_summary" not in payload


@pytest.mark.parametrize("limit", [1200, 600, 350])
def test_budget_fit_preserves_original_complete_spans(limit):
    row = materials(1)[0]
    row["summary"] = (
        "The study compares reserving methods. It provides worked examples. "
        + "It identifies practical limitations. " * 80
    )
    item = weekly._normalize_material_item(row)
    # Normalization must preserve the source, not establish its crop as a source.
    assert item["_source_summary"] == row["summary"]
    text = weekly._excerpt(row["summary"], limit)
    assert text in row["summary"]
    assert weekly._complete_source_excerpt(text, row["summary"])


@pytest.mark.parametrize(
    "summary",
    [
        "There is no evidence that U.S. insurers are safe.",
        "There is no evidence that U.S. GAAP portfolios are safe.",
        "There is no evidence under Sec. 5 that portfolios are safe.",
        "本研究说明：‘模型尚不可靠。’仍需验证。",
        "No evidence establishes safety",
    ],
)
def test_whole_allowed_source_keeps_its_qualifying_context(summary):
    row = materials(1)[0]
    row["summary"] = summary
    assert summary in parse_source_response(response(row, summary), [row])[1]


def test_real_three_sentence_abbreviation_paragraph_is_not_merged():
    row = materials(1)[0]
    row["summary"] = "The study uses data from the U.S. It covers the U.K. It finds limitations."
    with pytest.raises(ValueError):
        parse_source_response(response(row, row["summary"]), [row])


def test_ordinary_three_sentence_summary_allows_two_adjacent_complete_sentences():
    row = materials(1)[0]
    row["summary"] = (
        "The study compares reserving methods. It provides worked examples. It identifies practical limitations."
    )
    excerpt = "It provides worked examples. It identifies practical limitations."
    assert excerpt in parse_source_response(response(row, excerpt), [row])[1]


def test_parser_requires_original_source_span_identity():
    row = materials(1)[0]
    with pytest.raises(ValueError):
        weekly._parse_reader_output(response(row, row["summary"]), [row])


def test_two_thousand_character_budget_does_not_rebase_a_crop():
    row = materials(1)[0]
    row["url"] += "?reference=" + "x" * 1700
    row["summary"] = (
        "There is no evidence that U.S. Treasury " + "bond " * 110 + "portfolios are safe."
    )
    normalized = weekly._normalize_material_item(row)
    assert normalized["_source_summary"] == row["summary"]
    assert normalized["url"] == row["url"]
    assert (
        len(json.dumps(weekly._material_payload(normalized), ensure_ascii=False, sort_keys=True))
        <= 2000
    )
    assert normalized["summary"] == ""
    assert normalized["_spans"] == []
    with pytest.raises(ValueError):
        weekly._parse_reader_output(response(row, "portfolios are safe."), [normalized])


def test_unpunctuated_budget_cut_has_no_new_source_identity():
    row = materials(1)[0]
    row["summary"] = "No evidence establishes safety " + "without full validation " * 80
    normalized = weekly._normalize_material_item(row)
    assert normalized["_source_summary"] == row["summary"]
    assert normalized["summary"] == ""
    assert normalized["_spans"] == []


def test_retry_parser_receives_its_actual_sent_span_material(span_memory, monkeypatch):
    row = span_memory.rows[0]
    row["summary"] = (
        "The study compares reserving methods. It provides worked examples. It identifies practical limitations."
    )
    first = "The study compares reserving methods. It provides worked examples."
    generator = Generator(["bad JSON", response(row, first)])
    captured = []
    original = weekly._parse_reader_output

    def capture(raw, material):
        payload = json.loads(
            re.search(
                r"BEGIN_UNTRUSTED_FILE_MATERIAL 1\n(.*?)\nEND_UNTRUSTED_FILE_MATERIAL",
                generator.calls[-1][0][1]["content"],
                re.S,
            ).group(1)
        )
        captured.append((payload, material[0]))
        return original(raw, material)

    monkeypatch.setattr(weekly, "_parse_reader_output", capture)
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "ai"
    assert len(captured) == len(generator.calls) == 2
    for payload, actual in captured:
        assert payload["summary"] == actual["summary"]
        assert actual["_source_summary"] == row["summary"]
        assert all(span["text"] in payload["summary"] for span in actual["_spans"])


def test_uncertain_three_sentence_background_fallback_only_uses_titles(span_memory):
    row = span_memory.rows[0]
    row["summary"] = "The study uses data from the U.S. It covers the U.K. It finds limitations."
    generator = Generator([])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "fallback"
    assert generator.calls == []
    assert "Study 0" in result["explanation_en"]
    assert "It covers" not in result["explanation_en"]


def test_non_adjacent_source_sentences_cannot_be_joined():
    row = materials(1)[0]
    row["summary"] = (
        "The study compares reserving methods. It provides worked examples. It identifies practical limitations."
    )
    joined = "The study compares reserving methods. It identifies practical limitations."
    with pytest.raises(ValueError):
        parse_source_response(response(row, joined), [row])


def test_five_ordinary_sources_still_generate_five_supported_recommendations(span_memory):
    span_memory.rows = materials(5)
    for row in span_memory.rows:
        row["summary"] = (
            "The study compares reserving methods. It provides worked examples. It identifies practical limitations."
        )

    class Grounded:
        calls = []

        def generate(self, messages, *, timeout_seconds):
            self.calls.append(messages)
            rows = [
                json.loads(block)
                for block in re.findall(
                    r"BEGIN_UNTRUSTED_FILE_MATERIAL \d+\n(.*?)\nEND_UNTRUSTED_FILE_MATERIAL",
                    messages[1]["content"],
                    re.S,
                )
            ]
            articles = [
                {"url": row["url"], "excerpt": row["summary"], "focus": row["keywords"][0]}
                for row in rows[:5]
            ]
            return json.dumps(
                {
                    lang: {"themes": rows[0]["keywords"][:1], "articles": articles}
                    for lang in ("zh", "en")
                }
            )

    generator = Grounded()
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["generation_mode"] == "ai"
    assert span_memory.saved["coverage"]["recommendation_count"] == 5
    assert len(generator.calls) == 1


def test_ellipsis_cannot_hide_potential_sentence_ends():
    row = materials(1)[0]
    row["summary"] = "There is no evidence... Treasury bond portfolios are safe."
    with pytest.raises(ValueError):
        parse_source_response(response(row, "Treasury bond portfolios are safe."), [row])


def themed_response(rows, themes):
    articles = [
        {
            "url": row["url"],
            "excerpt": row["summary"],
            "focus": row["keywords"][0] if row["keywords"] else "",
        }
        for row in rows[:5]
    ]
    return json.dumps({lang: {"themes": themes, "articles": articles} for lang in ("zh", "en")})


@pytest.mark.parametrize("themes", [[], ["topic-0"]])
def test_normal_guide_requires_a_supported_nonempty_theme(themes):
    rows = materials(5)
    payload = themed_response(rows, themes)
    if themes:
        assert "topic-0" in parse_source_response(payload, rows)[1]
    else:
        with pytest.raises(ValueError):
            parse_source_response(payload, rows)


def test_empty_themes_cannot_be_saved_as_ai_when_source_topics_exist(span_memory):
    span_memory.rows = materials(5)
    generator = Generator([themed_response(span_memory.rows, [])])
    result = weekly.generate_weekly_explanation(
        db_path="fixture", snapshot_id="weekly-current", generator=generator
    )
    assert result["status"] == "failed"
    assert result["generation_mode"] == "fallback"
    assert len(generator.calls) == 1
    assert span_memory.saved["coverage"]["error_category"] == "validation"
    assert "Study 0" in result["explanation_en"]


def test_unavailable_source_topics_keep_a_truthful_fallback(span_memory):
    span_memory.rows = materials(5)
    for row in span_memory.rows:
        row["keywords"] = []
        row["category"] = ""
    result = weekly.generate_weekly_explanation(
        db_path="fixture",
        snapshot_id="weekly-current",
        generator=Generator([themed_response(span_memory.rows, [])]),
    )
    assert result["generation_mode"] == "fallback"
    assert result["status"] == "failed"
    assert "Study 0" in result["explanation_en"]
    assert span_memory.rows[0]["summary"] in result["explanation_en"]

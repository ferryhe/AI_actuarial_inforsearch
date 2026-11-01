from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from ai_actuarial import article_interpretation_english as english
from ai_actuarial import article_interpretations as articles
from ai_actuarial.api.routers import article_interpretations as api
from ai_actuarial.article_interpretation_english import (
    EnglishTranslationService,
    read_english_interpretations,
    validate_english_output,
)
from ai_actuarial.article_interpretations import ArticleRequestCleanupError
from ai_actuarial.chatbot.exceptions import LLMAuthenticationError
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path

ROLES = articles.SECTION_ROLES
URL = "https://cas.example/research/paper.pdf"
CHINA_URL = "https://aiactuary.cn/file-detail?file_id=3678"


def _draft(storage, *, url=URL, number="2", existing_translation=None):
    headings = ("摘要", "问题", "方法", "案例", "结果", "局限")
    source_text = "\n\n".join(f"## {heading}\n\nEvidence for this section." for heading in headings)
    source_text += "\n\nSource URL: " + url
    raw_sha = articles._hash(source_text)
    markdown_sha = articles._hash(source_text)
    content_key = articles._hash(raw_sha + markdown_sha)
    source_key = "cas"
    storage._conn.execute(
        "INSERT INTO canonical_sources VALUES (?,?,?,'active',NULL,'{}'::jsonb) ON CONFLICT (source_key) DO NOTHING",
        (source_key, "Casualty Actuarial Society", "Casualty Actuarial Society"),
    )
    storage._conn.execute(
        "INSERT INTO files(url,sha256,title,local_path,published_time,deleted_at) VALUES (?,?,?,?,?,NULL)",
        (url, raw_sha, "Insurance research", "fixture.pdf", "2025-04"),
    )
    storage._conn.execute(
        "INSERT INTO catalog_items(file_url,sha256,file_sha256,pipeline_version,status,markdown_content) "
        "VALUES (?,?,?,'fixture','ok',?)",
        (url, raw_sha, raw_sha, source_text),
    )
    evidence = []
    claims = []
    body = []
    for index, (role, heading) in enumerate(zip(ROLES, headings, strict=True), start=1):
        evidence_id = f"e{index}"
        # Avoid extra quantities in the source claim; only the first one is used by numeric tests.
        chinese_text = f"结果值为{number}" if index == 1 else "原文论述了这一研究内容"
        evidence.append({"id": evidence_id, "quote": "证据。", "section": heading})
        claims.append(
            {
                "text": chinese_text,
                "kind": "inference" if index == 2 else "example" if index == 3 else "source",
                "evidence_ids": [evidence_id],
                "section_role": role,
            }
        )
        body.extend([f"## {heading}", "中文正文。"])
    body.extend(
        [
            "## 原文出处与阅读",
            "",
            "原文日期：2025-04。",
            "",
            f"[原文]({url}) · [国内阅读]({CHINA_URL})",
        ]
    )
    interpretation_id = str(uuid.uuid4())
    references = {
        "original_url": url,
        "original_title": "Original research title",
        "source": {"name_zh": "北美产险精算协会", "name_en": "Casualty Actuarial Society"},
        "published_time": "2025-04",
        "china_article_url": CHINA_URL,
        "evidence": evidence,
        "authors": ["Researcher One", "Researcher Two"],
    }
    draft = {
        "interpretation_id": interpretation_id,
        "file_url": url,
        "raw_sha256": raw_sha,
        "markdown_sha256": markdown_sha,
        "content_key": content_key,
        "source_key": source_key,
        "input_fingerprint": "saved-chinese-fingerprint-" + articles._hash(url),
        "status": "ready",
        "title_zh": "研究解读",
        "body_markdown_zh": "\n\n".join(body),
        "claims": claims,
        "coverage": {"context_tokens": 40_000, "evidence": evidence},
        "references": references,
        "china_article_url": CHINA_URL,
        "generated_at": "2026-11-01T00:00:00+00:00",
        "attempts": [{"calls": [{"status": "valid"}]}],
    }
    if existing_translation:
        draft["english_translation"] = existing_translation
    storage._conn.execute(
        "INSERT INTO article_interpretations(interpretation_id,file_url,raw_sha256,markdown_sha256,"
        "content_key,source_key,input_fingerprint,status,payload_json) VALUES (?,?,?,?,?,?,?,'ready',?::jsonb)",
        (
            interpretation_id,
            url,
            raw_sha,
            markdown_sha,
            content_key,
            source_key,
            "saved-chinese-fingerprint-" + articles._hash(url),
            json.dumps(draft, ensure_ascii=False),
        ),
    )
    return draft


@pytest.fixture
def storage(tmp_path):
    value = Storage(postgres_url_for_path(tmp_path / "english-interpretation"))
    yield value
    value.close()


def _valid_response(messages, *, first_number="2"):
    material = json.loads(messages[1]["content"])
    sections = []
    claim_index = 0
    english_headings = ("Introduction", "Problem", "Method", "Case study", "Results", "Limitations")
    for index, section in enumerate(material["sections"], start=1):
        paragraphs = []
        for _claim in section["claims"]:
            claim_index += 1
            paragraphs.append(
                f"The result is {first_number}."
                if claim_index == 1
                else "The source discusses this research point."
            )
        sections.append(
            {
                "role": section["role"],
                "heading_en": english_headings[index - 1],
                "paragraphs": paragraphs,
            }
        )
    return json.dumps({"title_en": "Research interpretation", "sections": sections})


class Generator:
    def __init__(self, outputs=None, error=None, on_call=None):
        self.outputs = list(outputs or [])
        self.error = error
        self.on_call = on_call
        self.calls = []

    async def generate(self, messages, *, deadline):
        self.calls.append({"messages": messages, "deadline": deadline})
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        if self.outputs:
            output = self.outputs.pop(0)
            return output(messages) if callable(output) else output
        return _valid_response(messages)


def test_english_generator_uses_provider_specific_defaults(monkeypatch):
    runtime = SimpleNamespace(configured=True, provider="deepseek", model="deepseek-flash")
    monkeypatch.setattr(english, "resolve_ai_function_runtime", lambda *_args, **_kwargs: runtime)
    service = object.__new__(EnglishTranslationService)
    service.storage = object()
    service.generator = None

    generator, route = service._generator()

    assert route == {"provider": "deepseek", "model": "deepseek-flash"}
    assert generator.request_options == articles._request_options("deepseek")
    assert generator.request_options["extra_body"] == {"thinking": {"type": "disabled"}}


def test_saved_chinese_claims_translate_without_mutating_chinese_and_reader_hides_internals(
    storage,
):
    draft = _draft(storage)
    generator = Generator()
    receipt = EnglishTranslationService(storage, generator=generator).run(
        interpretation_ids=[draft["interpretation_id"]]
    )

    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    assert receipt["receipt_type"] == "english_translation"
    assert receipt["provider_calls"] == 1
    assert saved["status"] == "ready"
    assert saved["body_markdown_zh"] == draft["body_markdown_zh"]
    assert saved["attempts"] == draft["attempts"]
    assert saved["english_translation"]["status"] == "ready"
    assert "Interpretation:" in saved["english_translation"]["body_markdown_en"]
    assert "Illustrative example:" in saved["english_translation"]["body_markdown_en"]

    public = read_english_interpretations(storage.database, file_url=URL)
    assert len(public) == 1
    assert public[0]["title_en"] == "Research interpretation"
    assert public[0]["references"]["source"]["name_en"] == "Casualty Actuarial Society"
    assert "evidence" not in public[0]["references"]
    assert "english_translation" not in public[0]
    assert "attempts" not in public[0]


def test_translation_validation_rejects_changed_numbers_units_order_and_claim_count():
    source = {
        "title_zh": "研究方法",
        "sections": [
            {
                "role": "method",
                "heading_zh": "方法",
                "claims": [
                    {
                        "text": "试验持续12个月",
                        "evidence": [{"quote": "试验持续12个月。", "section": "方法"}],
                    }
                ],
            }
        ],
    }
    valid = {
        "title_en": "Research method",
        "sections": [
            {
                "role": "method",
                "heading_en": "Method",
                "paragraphs": ["The trial lasted 12 months."],
            }
        ],
    }
    assert validate_english_output(json.dumps(valid), source)["title_en"] == "Research method"

    marked_title = json.loads(json.dumps(valid))
    marked_title["title_en"] += " [e9]"
    marked_heading = json.loads(json.dumps(valid))
    marked_heading["sections"][0]["heading_en"] += " [E9]"
    marked_paragraph = json.loads(json.dumps(valid))
    marked_paragraph["sections"][0]["paragraphs"][0] += " [e9]"
    for marked in (marked_title, marked_heading, marked_paragraph):
        with pytest.raises(ValueError, match="unexpected_evidence_marker"):
            validate_english_output(json.dumps(marked), source)

    precision_source = {
        "title_zh": "成功率",
        "sections": [
            {
                "role": "method",
                "heading_zh": "成功率",
                "claims": [
                    {
                        "text": "成功率为12.00%",
                        "evidence": [{"quote": "成功率为12.00%。", "section": "方法"}],
                    }
                ],
            }
        ],
    }
    precision_valid = {
        "title_en": "Success rate",
        "sections": [
            {
                "role": "method",
                "heading_en": "Success rate",
                "paragraphs": ["The success rate was 12.00%."],
            }
        ],
    }
    assert validate_english_output(json.dumps(precision_valid), precision_source)
    lost_precision = json.loads(json.dumps(precision_valid))
    lost_precision["sections"][0]["paragraphs"][0] = "The success rate was 12%."
    with pytest.raises(ValueError, match="number_mismatch"):
        validate_english_output(json.dumps(lost_precision), precision_source)

    changed_number = json.loads(json.dumps(valid))
    changed_number["sections"][0]["paragraphs"][0] = "The trial lasted 13 months."
    with pytest.raises(ValueError, match="number_mismatch"):
        validate_english_output(json.dumps(changed_number), source)

    changed_unit = json.loads(json.dumps(valid))
    changed_unit["sections"][0]["paragraphs"][0] = "The trial lasted 12 years."
    with pytest.raises(ValueError, match="number_mismatch"):
        validate_english_output(json.dumps(changed_unit), source)

    changed_order = json.loads(json.dumps(valid))
    changed_order["sections"][0]["role"] = "results"
    with pytest.raises(ValueError, match="order_mismatch"):
        validate_english_output(json.dumps(changed_order), source)

    missing_claim = json.loads(json.dumps(valid))
    missing_claim["sections"][0]["paragraphs"] = []
    with pytest.raises(ValueError, match="paragraph_count_mismatch"):
        validate_english_output(json.dumps(missing_claim), source)

    formula_source = {
        "title_zh": "模型公式",
        "sections": [
            {
                "role": "method",
                "heading_zh": "公式",
                "claims": [
                    {
                        "text": "公式为 $E[X]=2$",
                        "evidence": [{"quote": "公式为 $E[X]=2$。", "section": "方法"}],
                    }
                ],
            }
        ],
    }
    formula_result = {
        "title_en": "Model formula",
        "sections": [
            {"role": "method", "heading_en": "Formula", "paragraphs": ["The formula is $E[X]=2$."]}
        ],
    }
    assert validate_english_output(json.dumps(formula_result), formula_source)
    formula_loss = json.loads(json.dumps(formula_result))
    formula_loss["sections"][0]["paragraphs"][0] = "The expected value is 2."
    with pytest.raises(ValueError, match="formula_missing"):
        validate_english_output(json.dumps(formula_loss), formula_source)


def test_translation_keeps_source_quotes_and_rejects_new_unsupported_quotes():
    source = {
        "title_zh": "研究结论",
        "sections": [
            {
                "role": "results",
                "heading_zh": "研究结论",
                "claims": [
                    {
                        "text": "作者将方法称为“low-cost feature engineering”。",
                        "evidence": [
                            {
                                "quote": "The paper calls the method a “low-cost feature engineering” approach and later a “novel pipeline”.",
                                "section": "Results",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = {
        "title_en": "Research conclusion",
        "sections": [
            {
                "role": "results",
                "heading_en": "Research conclusion",
                "paragraphs": [
                    "The authors describe it as a “low-cost feature engineering” method."
                ],
            }
        ],
    }
    assert validate_english_output(json.dumps(result), source)

    repeated_saved_quote = json.loads(json.dumps(result))
    repeated_saved_quote["sections"][0]["paragraphs"][
        0
    ] = "The authors describe it as a “low-cost feature engineering” method, a “low-cost feature engineering” method."
    with pytest.raises(ValueError, match="quote_mismatch"):
        validate_english_output(json.dumps(repeated_saved_quote), source)

    added_supported_quote = json.loads(json.dumps(result))
    added_supported_quote["sections"][0]["paragraphs"][
        0
    ] = "The authors describe it as a “low-cost feature engineering” method and a “novel pipeline”."
    assert validate_english_output(json.dumps(added_supported_quote), source)

    dropped_quote = json.loads(json.dumps(result))
    dropped_quote["sections"][0]["paragraphs"][
        0
    ] = "The authors describe it as a low-cost feature engineering method."
    with pytest.raises(ValueError, match="quote_mismatch"):
        validate_english_output(json.dumps(dropped_quote), source)

    replaced_quote = json.loads(json.dumps(result))
    replaced_quote["sections"][0]["paragraphs"][
        0
    ] = "The authors describe it as a “novel pipeline”."
    with pytest.raises(ValueError, match="quote_mismatch"):
        validate_english_output(json.dumps(replaced_quote), source)

    unsupported_quote = json.loads(json.dumps(result))
    unsupported_quote["sections"][0]["paragraphs"][
        0
    ] = "The authors describe it as a “miraculous” method."
    with pytest.raises(ValueError, match="quote_mismatch"):
        validate_english_output(json.dumps(unsupported_quote), source)


def test_quantity_validation_preserves_order_multiplicity_and_explicit_date_aliases():
    check = english._check_quantities
    check("ordered", "从2增加到5", "increased from 2 to 5")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("ordered", "从2增加到5", "decreased from 5 to 2")

    check("duplicate", "样本数为2个和2个", "There were 2 and 2 samples.")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("duplicate", "样本数为2个和2个", "There were 2 samples.")

    check("calendar", "2018年9月", "September 2018")
    check("calendar", "2018年9月", "2018-09")
    check("calendar_day", "2018年9月12日", "September 12, 2018")
    check(
        "repeated_date",
        "2018年9月和2018年9月",
        "September 2018 and September 2018",
    )
    with pytest.raises(ValueError, match="number_mismatch"):
        check("repeated_date", "2018年9月和2018年9月", "September 2018")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("calendar", "2018年9月", "October 2018")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("calendar", "2018年9月", "September 2019")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("calendar_day", "2018年9月12日", "September 13, 2018")
    with pytest.raises(ValueError, match="number_mismatch"):
        check(
            "calendar_order",
            "2018年9月到2019年10月",
            "October 2019, then September 2018",
        )

    # Four-digit sample ranges remain ordinary quantities without explicit date context.
    check(
        "sample_range",
        "保单数从2006增加到2010",
        "The number of policies increased from 2006 to 2010.",
    )
    check("scale", "数十亿美元", "billions of dollars")
    check("one_hot_encoding", "研究采用独热编码。", "The study uses one-hot encoding.")
    check(
        "one_hot_count",
        "研究使用1种独热编码。",
        "The study uses one feature and one-hot encoding.",
    )
    check(
        "selected_source_one_hot_vectors",
        "将类别变量编码为独热向量。",
        "They encoded the categorical variables using one-hot vectors.",
    )
    check(
        "one_hot_encoded",
        "类别变量采用独热编码。",
        "The categorical variables were one-hot encoded.",
    )
    check(
        "one_hot_term_and_count",
        "1个类别变量使用独热向量。",
        "One categorical variable is encoded using a one-hot vector.",
    )
    check("ordinary_hot_day_count", "发生了1个热天。", "There was one hot day.")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("ordinary_hot_day_wrong_count", "发生了1个热天。", "There were two hot days.")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("one_hot_fabricated", "研究采用2种独热编码。", "The study uses one-hot encoding.")

    check("ordinal", "第二阶段评估模型。", "The 2nd stage evaluates the model.")
    check(
        "ordinal_with_count",
        "第二阶段包含2个样本。",
        "The 2nd stage contains 2 samples.",
    )
    check(
        "ordinal_order_and_multiplicity",
        "第二阶段和第三阶段",
        "The 2nd stage and 3rd stage",
    )
    with pytest.raises(ValueError, match="number_mismatch"):
        check("ordinal_wrong_value", "第二阶段有3个样本", "The 3rd stage has 2 samples.")
    chinese_quantities = articles._quantities("第二阶段", strict=True)
    check("ordinal_default", "第二阶段", "2nd stage")
    assert articles._quantities("第二阶段", strict=True) == chinese_quantities

    for text in ("从2增加到5", "2018年9月", "数十亿美元"):
        collected = []
        assert articles._quantities(text, strict=True) == articles._quantities(
            text, strict=True, occurrences=collected
        )
        assert collected


def test_english_quantity_validation_handles_saved_som_decade_and_percent_range():
    check = english._check_quantities
    saved_decade_claim = "保险与金融领域三十年来积累的私有机器学习系统"
    saved_growth_paragraph = (
        "作者以马来西亚和印度尼西亚为例，指出该地区毛承保保费年增长5%至8%，"
        "市场扩张快、数据稀疏、历史经验有限，因此结构简单、定价透明的成数分保更具优势。"
    )

    check(
        "saved_som_decade",
        saved_decade_claim,
        "Private machine learning systems built over three decades.",
    )
    check(
        "saved_som_growth",
        saved_growth_paragraph,
        "Gross Underwritten Premium grew 5-to-8 percent annually in Malaysia and Indonesia.",
    )
    check("signed_percent_range", "从-5%到8%", "from -5% to 8%")

    with pytest.raises(ValueError, match="number_mismatch"):
        check("wrong_decade_value", "三十年来", "For two decades")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("years_are_not_decades", "三十年来", "For three years")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("wrong_percent_lower_bound", "年增长5%至8%", "5-to-6 percent")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("wrong_percent_upper_bound", "年增长5%至8%", "5-to-9 percent")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("percent_unit_missing", "年增长5%至8%", "5-to-8")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("percent_unit_changed", "年增长5%至8%", "5-to-8 USD")
    with pytest.raises(ValueError, match="number_mismatch"):
        check("percent_precision_changed", "年增长5%至8%", "5.0-to-8.0 percent")


def test_second_call_receives_bounded_correction_and_does_not_refresh_chinese_budget(storage):
    draft = _draft(storage)
    generator = Generator(outputs=[lambda messages: _valid_response(messages, first_number="999")])
    receipt = EnglishTranslationService(storage, generator=generator).run(
        interpretation_ids=[draft["interpretation_id"]]
    )
    assert len(generator.calls) == 2
    assert receipt["provider_calls"] == 2
    assert generator.calls[1]["messages"][-1]["content"].startswith(
        "Return the complete corrected English JSON from the saved Chinese material."
    )
    assert "english_claim_1_1_number_mismatch" in generator.calls[1]["messages"][-1]["content"]
    assert sum(len(message["content"]) for message in generator.calls[1]["messages"]) <= 32_000
    assert (
        sum(
            len(message["content"].encode("utf-8")) + 16
            for message in generator.calls[1]["messages"]
        )
        + 6_000
        <= 40_000
    )
    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    assert saved["status"] == "ready"
    assert saved["english_translation"]["status"] == "ready"
    repeated = EnglishTranslationService(storage, generator=generator).run(
        interpretation_ids=[draft["interpretation_id"]]
    )
    assert repeated["provider_calls"] == 2
    assert len(generator.calls) == 2


def test_false_evidence_marker_is_corrected_before_saved_ids_are_rendered(storage):
    draft = _draft(storage)

    def false_marker(messages):
        value = json.loads(_valid_response(messages))
        value["sections"][0]["paragraphs"][0] += " [e9]"
        return json.dumps(value)

    generator = Generator(outputs=[false_marker, _valid_response])
    receipt = EnglishTranslationService(storage, generator=generator).run(
        interpretation_ids=[draft["interpretation_id"]]
    )

    assert len(generator.calls) == 2
    assert receipt["provider_calls"] == 2
    assert receipt["slots"][0]["status"] == "ready"
    assert "unexpected_evidence_marker" in generator.calls[1]["messages"][-1]["content"]
    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    assert saved["status"] == "ready"
    assert saved["body_markdown_zh"] == draft["body_markdown_zh"]
    assert saved["claims"][0]["evidence_ids"] == ["e1"]
    body = saved["english_translation"]["body_markdown_en"]
    assert "[e1]" in body
    assert "[e9]" not in body
    assert len(saved["english_translation"]["attempts"][0]["calls"]) == 2


def test_failed_translation_and_same_content_replay_cannot_renew_two_call_budget(storage):
    draft = _draft(storage)
    generator = Generator(
        outputs=[lambda messages: _valid_response(messages, first_number="999") for _ in range(2)]
    )
    first = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])
    assert first["provider_calls"] == 2
    assert first["slots"][0]["status"] == "failed"
    second = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])
    assert second["provider_calls"] == 2
    assert len(generator.calls) == 2
    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    assert saved["english_translation"]["status"] == "failed"


def test_reserved_translation_call_survives_process_interruption_and_only_uses_remaining_call(
    storage, monkeypatch
):
    draft = _draft(storage)
    generator = Generator()
    with monkeypatch.context() as context:
        context.setattr(
            english,
            "_call_article_with_deadline",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(SystemExit("simulated interruption")),
        )
        with pytest.raises(SystemExit, match="simulated interruption"):
            EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])

    interrupted = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    assert interrupted["english_translation"]["attempts"][0]["calls"][0]["status"] == "reserved"
    resumed = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])
    assert resumed["provider_calls"] == 2
    assert len(generator.calls) == 1
    assert generator.calls[0]["messages"][-1]["role"] == "user"
    assert (
        "Return the complete corrected English JSON"
        not in generator.calls[0]["messages"][-1]["content"]
    )


def test_provider_cleanup_stops_batch_and_blocks_same_content_on_later_day(storage):
    first = _draft(storage)
    second_url = "https://cas.example/research/second.pdf"
    second = _draft(storage, url=second_url)
    first_day = articles.datetime(2026, 11, 1, 0, 0, tzinfo=articles.timezone.utc)
    generator = Generator(error=ArticleRequestCleanupError("owned client did not close"))
    first_receipt = EnglishTranslationService(
        storage, generator=generator, now=lambda: first_day
    ).run(file_urls=[URL, second_url])
    assert first_receipt["status"] == "provider_cleanup"
    assert first_receipt["provider_calls"] == 1
    assert len(first_receipt["slots"]) == 1
    assert first_receipt["slots"][0]["reason"] == "provider_cleanup"
    assert len(generator.calls) == 1
    assert not dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (second["interpretation_id"],),
        ).fetchone()[0]
    ).get("english_translation")

    same_day = EnglishTranslationService(storage, generator=generator, now=lambda: first_day).run(
        file_urls=[URL, second_url]
    )
    assert same_day["status"] == "provider_cleanup"
    assert len(generator.calls) == 1

    next_day = first_day.replace(day=2)
    later = EnglishTranslationService(storage, generator=generator, now=lambda: next_day).run(
        file_urls=[URL]
    )
    assert later["status"] == "provider_cleanup"
    assert later["provider_calls"] == 0
    assert len(generator.calls) == 1
    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (first["interpretation_id"],),
        ).fetchone()[0]
    )
    assert saved["status"] == "ready"
    assert saved["english_translation"]["error"] == "provider_cleanup"


def test_authentication_failure_stops_remaining_english_batch(storage):
    _draft(storage)
    _draft(storage, url="https://cas.example/research/second.pdf")
    generator = Generator(error=LLMAuthenticationError("not authorized"))
    receipt = EnglishTranslationService(storage, generator=generator).run(
        file_urls=[URL, "https://cas.example/research/second.pdf"]
    )
    assert receipt["status"] == "authentication"
    assert receipt["provider_calls"] == 1
    assert len(receipt["slots"]) == 1
    assert len(generator.calls) == 1


def test_correction_is_omitted_when_it_would_exceed_the_original_input_budget(storage):
    draft = _draft(storage)
    material = english._material(draft)
    messages = [
        {"role": "system", "content": english.PROMPT},
        {
            "role": "user",
            "content": json.dumps(material, ensure_ascii=False, separators=(",", ":")),
        },
    ]
    base_bytes = sum(len(message["content"].encode("utf-8")) + 16 for message in messages)
    draft["coverage"]["context_tokens"] = base_bytes + english.MAX_OUTPUT_TOKENS
    storage._conn.execute(
        "UPDATE article_interpretations SET payload_json=?::jsonb WHERE interpretation_id=?",
        (json.dumps(draft, ensure_ascii=False), draft["interpretation_id"]),
    )
    generator = Generator(outputs=[lambda request: _valid_response(request, first_number="999")])
    receipt = EnglishTranslationService(storage, generator=generator).run(
        interpretation_ids=[draft["interpretation_id"]]
    )
    assert len(generator.calls) == 1
    assert receipt["provider_calls"] == 1
    assert receipt["slots"][0]["reason"] == "english_correction_feedback_does_not_fit"
    assert len(generator.calls[0]["messages"]) == 2


def test_manual_ready_chinese_replay_translates_once_and_skips_hidden_or_stale(storage):
    draft = _draft(storage)
    generator = Generator()
    first = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])
    assert len(generator.calls) == 1
    again = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])
    assert len(generator.calls) == 1
    assert again["provider_calls"] == 1

    hidden_url = "https://cas.example/research/hidden.pdf"
    _draft(storage, url=hidden_url)
    storage._conn.execute("UPDATE files SET local_path='' WHERE url=?", (hidden_url,))
    skipped = EnglishTranslationService(storage, generator=generator).run(file_urls=[hidden_url])
    assert all(slot["file_url"] != hidden_url for slot in skipped["slots"])
    assert len(generator.calls) == 1
    assert draft["interpretation_id"] == first["slots"][0]["interpretation_id"]


def test_source_change_during_translation_does_not_make_a_second_call_or_ready_english(storage):
    draft = _draft(storage)
    generator = Generator(
        on_call=lambda: storage._conn.execute("UPDATE files SET local_path='' WHERE url=?", (URL,))
    )
    receipt = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])
    assert len(generator.calls) == 1
    assert receipt["slots"][0]["status"] == "skipped"
    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    assert saved["status"] == "ready"
    assert saved["english_translation"]["status"] == "failed"
    assert saved["english_translation"]["error"] == "source_version_no_longer_current"


@pytest.mark.parametrize("mutation", ["hidden", "markdown_changed"])
def test_invalid_translation_rechecks_source_before_reserving_second_call(storage, mutation):
    draft = _draft(storage)
    call_count = 0

    def change_source_on_first_call():
        nonlocal call_count
        call_count += 1
        if call_count != 1:
            return
        if mutation == "hidden":
            storage._conn.execute("UPDATE files SET local_path='' WHERE url=?", (URL,))
        else:
            markdown = storage._conn.execute(
                "SELECT markdown_content FROM catalog_items WHERE file_url=?", (URL,)
            ).fetchone()[0]
            storage._conn.execute(
                "UPDATE catalog_items SET markdown_content=? WHERE file_url=?",
                (markdown + "\nChanged source version.", URL),
            )

    generator = Generator(
        outputs=["{}", lambda messages: _valid_response(messages)],
        on_call=change_source_on_first_call,
    )
    receipt = EnglishTranslationService(storage, generator=generator).run(file_urls=[URL])

    assert len(generator.calls) == 1
    assert receipt["provider_calls"] == 1
    assert receipt["slots"][0]["status"] == "skipped"
    assert receipt["slots"][0]["reason"] == "source_version_no_longer_current"
    saved = dict(
        storage._conn.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (draft["interpretation_id"],),
        ).fetchone()[0]
    )
    translation = saved["english_translation"]
    assert translation["status"] == "failed"
    assert translation["error"] == "source_version_no_longer_current"
    assert len(translation["attempts"][0]["calls"]) == 1


def _request(*, database, config, file_url, locale="en"):
    return SimpleNamespace(
        query_params={"file_url": file_url, "locale": locale},
        app=SimpleNamespace(
            state=SimpleNamespace(database=database, db_path=database, site_config=config)
        ),
    )


def test_local_english_api_allowlists_reader_fields(storage):
    draft = _draft(storage)
    EnglishTranslationService(storage, generator=Generator()).run(
        interpretation_ids=[draft["interpretation_id"]]
    )
    response = api.api_article_interpretations(
        _request(database=storage.database, config={}, file_url=URL)
    )
    item = response["interpretations"][0]
    assert item["title_en"] == "Research interpretation"
    assert set(item) == {
        "interpretation_id",
        "title_en",
        "body_markdown_en",
        "generated_at",
        "file_url",
        "raw_sha256",
        "markdown_sha256",
        "china_article_url",
        "references",
    }
    assert "attempts" not in item and "english_translation" not in item


def test_overseas_proxy_requires_exact_current_identity_and_forwards_no_browser_credentials(
    monkeypatch,
):
    local_identity = {"file_url": URL, "raw_sha256": "raw", "markdown_sha256": "md"}
    monkeypatch.setattr(api, "read_current_article_identity", lambda _db, _url: local_identity)
    calls = []

    class Reply:
        status_code = 200

        def json(self):
            return {
                "interpretations": [
                    {
                        **local_identity,
                        "interpretation_id": "public-id",
                        "title_en": "English title",
                        "body_markdown_en": "English body",
                        "generated_at": "2026-11-01T00:00:00Z",
                        "china_article_url": CHINA_URL,
                        "references": {"original_title": "Original title", "evidence": ["private"]},
                        "attempts": ["private"],
                        "english_translation": {"state": "private"},
                    }
                ]
            }

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Reply()

    monkeypatch.setattr(api.requests, "get", get)
    config = {
        "article_interpretation": {
            "english_proxy": {"enabled": True, "china_origin": "https://aiactuary.cn"}
        }
    }
    response = api.api_article_interpretations(
        _request(database="local-test-db", config=config, file_url=URL)
    )
    assert len(response["interpretations"]) == 1
    assert "attempts" not in response["interpretations"][0]
    assert "english_translation" not in response["interpretations"][0]
    assert "evidence" not in response["interpretations"][0]["references"]
    url, kwargs = calls[0]
    assert url == "https://aiactuary.cn/api/article-interpretations"
    assert kwargs == {
        "params": {"file_url": URL, "locale": "en"},
        "timeout": (2.0, 2.0),
        "allow_redirects": False,
    }

    class Mismatch(Reply):
        def json(self):
            value = super().json()
            value["interpretations"][0]["markdown_sha256"] = "stale"
            return value

    monkeypatch.setattr(api.requests, "get", lambda *_args, **_kwargs: Mismatch())
    assert api.api_article_interpretations(
        _request(database="local-test-db", config=config, file_url=URL)
    ) == {"interpretations": []}


def test_overseas_proxy_fails_closed_for_hidden_article_or_untrusted_origin(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "read_current_article_identity", lambda _db, _url: None)
    monkeypatch.setattr(api.requests, "get", lambda *args, **kwargs: calls.append((args, kwargs)))
    config = {
        "article_interpretation": {
            "english_proxy": {"enabled": True, "china_origin": "https://aiactuary.cn"}
        }
    }
    assert api.api_article_interpretations(
        _request(database="local-test-db", config=config, file_url=URL)
    ) == {"interpretations": []}
    assert calls == []
    invalid = {
        "article_interpretation": {
            "english_proxy": {"enabled": True, "china_origin": "http://aiactuary.cn"}
        }
    }
    assert api.api_article_interpretations(
        _request(database="local-test-db", config=invalid, file_url=URL)
    ) == {"interpretations": []}
    assert calls == []

    config = {
        "article_interpretation": {
            "english_proxy": {"enabled": True, "china_origin": "https://aiactuary.cn"}
        }
    }
    monkeypatch.setattr(
        api,
        "read_current_article_identity",
        lambda _db, _url: {"file_url": URL, "raw_sha256": "raw", "markdown_sha256": "md"},
    )
    monkeypatch.setattr(
        api.requests, "get", lambda *_args, **_kwargs: (_ for _ in ()).throw(api.requests.Timeout())
    )
    assert api.api_article_interpretations(
        _request(database="local-test-db", config=config, file_url=URL)
    ) == {"interpretations": []}


def test_task_runtime_runs_enabled_translation_after_chinese_and_strips_scheduled_url(
    storage, tmp_path, monkeypatch
):
    from ai_actuarial import article_interpretation_english as en_articles
    from ai_actuarial import article_interpretations as cn_articles
    from ai_actuarial import task_runtime

    calls = []
    chinese_status = {"value": "complete"}

    class ChineseService:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, **kwargs):
            calls.append(("chinese", kwargs))
            return {
                "status": chinese_status["value"],
                "slots": [{"status": "ready", "interpretation_id": "current-cn"}],
            }

    class EnglishService:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, **kwargs):
            calls.append(("english", kwargs))
            return {"status": "complete", "receipt_type": "english_translation"}

    monkeypatch.setattr(cn_articles, "ArticleInterpretationService", ChineseService)
    monkeypatch.setattr(en_articles, "EnglishTranslationService", EnglishService)
    runtime = task_runtime.NativeTaskRuntime(
        ready_data_database=storage.database,
        data_root=tmp_path,
    )
    runtime._site_config_override = {
        "paths": {"download_dir": str(tmp_path)},
        "article_interpretation": {
            "environment": "china",
            "english_translation": {"enabled": True},
        },
    }
    runtime._stop_requested = lambda _task_id: False

    result = runtime._run_collection("manual-task", "article_interpretation", {"file_url": URL})
    assert result.success
    assert result.metadata["status"] == "complete"
    assert result.metadata["english_translation"]["receipt_type"] == "english_translation"
    assert calls[0] == ("chinese", {"retry_id": None, "file_url": URL})
    assert calls[1][0] == "english"
    assert calls[1][1]["interpretation_ids"] == ["current-cn"]
    assert calls[1][1]["file_urls"] == [URL]

    calls.clear()
    monkeypatch.setattr(
        "ai_actuarial.api.services.ops_read.get_schedule_status",
        lambda _scheduler: {"jobs": []},
    )
    runtime._run_collection(
        "scheduled-task",
        "article_interpretation",
        {"scheduled": True, "schedule_name": "daily", "file_url": URL},
    )
    assert calls[0] == ("chinese", {"retry_id": None, "file_url": None})
    assert calls[1][1]["file_urls"] == []

    calls.clear()
    runtime._site_config_override = {
        "paths": {"download_dir": str(tmp_path)},
        "article_interpretation": {
            "environment": "local",
            "english_translation": {"enabled": True},
        },
    }
    result = runtime._run_collection("local-task", "article_interpretation", {"file_url": URL})
    assert result.metadata.get("english_translation") is None
    assert [kind for kind, _kwargs in calls] == ["chinese"]

    calls.clear()
    chinese_status["value"] = "provider_cleanup"
    runtime._site_config_override["article_interpretation"]["environment"] = "china"
    result = runtime._run_collection("cleanup-task", "article_interpretation", {"file_url": URL})
    assert result.metadata.get("english_translation") is None
    assert [kind for kind, _kwargs in calls] == ["chinese"]

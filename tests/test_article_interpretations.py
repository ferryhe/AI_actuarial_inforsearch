from __future__ import annotations

import asyncio
import inspect
import json
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_actuarial import article_interpretations as articles
from ai_actuarial.postgres import PostgresConnection
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path


def source_body(label="research"):
    return "\n\n".join(
        f"## {heading}\n\n"
        + (
            f"This {label} research examines insurance estimation. "
            "The method estimates risk using observed claims and a regression model. "
            "The experiment compares the estimated risk with observed outcomes. "
            "Limitations require the same population and consistent data definitions. "
        )
        for heading in ("Abstract", "Problem", "Method", "Case study", "Results", "Limitations")
    )


def response(messages):
    material = json.loads(messages[-1]["content"])
    evidence = material["evidence"]
    text = (
        "研究围绕保险风险估计中的资料和方法展开。原文把观察资料作为模型估计的基础，"
        "并将估计结果与观察结果进行比较。对于精算工作，理解这种方法需要先确认资料口径，"
        "再区分模型所作的假设与实际观察到的现象。样本所属群体和数据定义构成适用条件，"
        "不能因为存在估计结果，就把方法理解成对所有业务都有效的保证。"
        "阅读这类研究时，需要把问题、方法、结果以及局限放在一起判断。"
    )
    return json.dumps(
        {
            "title_zh": "保险风险估计：从资料到方法的边界",
            "short_reason": "",
            "authors": [entry["name"] for entry in material.get("author_metadata", [])],
            "sections": [
                {
                    "role": role,
                    "heading": "研究解读",
                    "paragraphs": [
                        {"text": text + text, "kind": "source", "evidence_ids": [evidence[i]["id"]]}
                    ],
                }
                for i, role in enumerate(articles.SECTION_ROLES)
            ],
        },
        ensure_ascii=False,
    )


class Generator:
    def __init__(self, *, output=None, error=None, on_call=None):
        self.calls = []
        self.output, self.error, self.on_call = output, error, on_call

    async def generate(self, messages, *, deadline):
        self.calls.append({"messages": messages, "timeout_seconds": deadline - time.monotonic()})
        if self.on_call:
            result = self.on_call()
            if inspect.isawaitable(result):
                await result
        if self.error:
            raise self.error
        return self.output if self.output is not None else response(messages)


class Resolver:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def resolve(self, identity, *, timeout_seconds):
        self.calls.append((identity, timeout_seconds))
        if self.fail:
            raise ValueError("link unavailable")
        return {
            "link_identity": identity,
            "china_article_url": "https://aiactuary.cn/file-detail?file_id=1",
            "china_file_id": 1,
            "link_verified_at": "2026-10-31T00:00:00+00:00",
        }


@pytest.fixture
def storage(tmp_path):
    db = postgres_url_for_path(tmp_path / "article-test")
    value = Storage(db)
    for key in ("a", "b", "c", "d", "e", "f", "g"):
        value._conn.execute(
            "INSERT INTO canonical_sources VALUES (?,?,?,'active',NULL,'{}'::jsonb)",
            (key, key, key),
        )
        value._conn.execute(
            "INSERT INTO source_aliases VALUES (?,'hostname',?,'verified','{}'::jsonb)",
            (f"{key}.example", key),
        )
    yield value
    value.close()


def seed(
    storage,
    key,
    *,
    body=None,
    title="Research method insurance",
    date=None,
    deleted=None,
    path="fixture.pdf",
    status="ok",
    url=None,
):
    url = url or f"https://{key}.example/研究.pdf?q=中文&x=1"
    body = source_body(key) if body is None else body
    digest = articles._hash(body)
    storage._conn.execute(
        "INSERT INTO files(url,sha256,title,local_path,published_time,deleted_at) VALUES (?,?,?,?,?,?)",
        (url, digest, title, path, date, deleted),
    )
    storage._conn.execute(
        "INSERT INTO catalog_items(file_url,sha256,pipeline_version,status,markdown_content) VALUES (?,?,'fixture',?,?)",
        (url, digest, status, body),
    )
    return url


def service(storage, **kwargs):
    return articles.ArticleInterpretationService(
        storage,
        generator=kwargs.pop("generator", Generator()),
        resolver=kwargs.pop("resolver", Resolver()),
        **kwargs,
    )


def test_fair_three_source_rotation_and_old_success_dedupe(storage):
    for key in "abcdefg":
        seed(storage, key)
    generator = Generator()
    runner = service(storage, generator=generator)
    receipts = [runner.run(round_key=f"day-{i}") for i in range(3)]
    assert [[s["source_key"] for s in r["slots"]] for r in receipts] == [
        list("abc"),
        list("def"),
        list("gab"),
    ]
    assert all(r["status"] == "complete" for r in receipts)
    assert len(generator.calls) == 7
    assert (
        receipts[2]["slots"][1]["decisions"][0]["reason"] == "content_version_already_interpreted"
    )
    assert runner.run(round_key="day-0") == receipts[0]
    assert len(articles.read_interpretations(storage.database)) == 7


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"title": "Webinar registration"}, "notice_directory_or_promotion"),
        ({"body": ""}, "full_text_missing_or_size_limit"),
        ({"body": "extraction failed\n" + source_body()}, "extraction_failed"),
        ({"path": ""}, "not_current_visible"),
        ({"deleted": "yesterday"}, "not_current_visible"),
        ({"status": "failed"}, "not_current_visible"),
    ],
)
def test_rejected_material_decision_persisted_and_cursor_advances(storage, changes, reason):
    seed(storage, "a", **changes)
    receipt = service(storage).run(round_key="reject")
    assert receipt["slots"][0]["status"] == "skipped"
    assert receipt["slots"][0]["decisions"][0]["reason"] == reason
    assert (
        storage._conn.execute(
            "SELECT last_source_key FROM article_interpretation_state"
        ).fetchone()[0]
        == "c"
    )


def test_cross_source_content_dedup_and_unknown_historical_dates(storage):
    body = source_body()
    seed(storage, "a", body=body, date="1998")
    seed(storage, "b", body=body)
    generator = Generator()
    receipt = service(storage, generator=generator).run(round_key="dedup")
    assert len(generator.calls) == 1
    assert receipt["slots"][1]["status"] == "skipped"
    saved = articles.read_interpretations(storage.database)[0]
    assert saved["coverage"]["published_time"] == "1998"


def test_link_failure_retry_reuses_body_and_read_marks_changed_version(storage):
    url = seed(storage, "a")
    generator, resolver = Generator(), Resolver(fail=True)
    runner = service(storage, generator=generator, resolver=resolver)
    receipt = runner.run(round_key="link")
    identity = receipt["slots"][0]["interpretation_id"]
    draft = runner._get(identity)
    assert draft["status"] == "failed" and draft["error"] == "link_unavailable"
    assert draft["body_markdown_zh"]
    draft["references"] = {"authors": ["Verified Author"]}
    runner._save(draft)
    cursor = storage._conn.execute(
        "SELECT last_source_key FROM article_interpretation_state"
    ).fetchone()[0]
    resolver.fail = False
    result = runner.run(retry_id=identity)["interpretation"]
    assert result["status"] == "ready" and len(generator.calls) == 1
    assert result["references"]["authors"] == ["Verified Author"]
    assert (
        storage._conn.execute(
            "SELECT last_source_key FROM article_interpretation_state"
        ).fetchone()[0]
        == cursor
    )
    storage._conn.execute(
        "UPDATE catalog_items SET markdown_content=markdown_content || 'changed' WHERE file_url=?",
        (url,),
    )
    saved = articles.read_interpretations(storage.database)[0]
    assert saved["status"] == "ready" and not saved["is_current"] and not saved["reader_eligible"]


def test_stop_and_restart_keep_completed_slot_and_cursor(storage):
    for key in "abc":
        seed(storage, key)
    stopped = [False]
    generator = Generator(on_call=lambda: stopped.__setitem__(0, True))
    receipt = service(storage, generator=generator, stop_check=lambda: stopped[0]).run(
        round_key="stop"
    )
    assert receipt["status"] == "stopped" and len(generator.calls) == 1
    assert receipt["slots"][0]["status"] == "ready"
    assert (
        storage._conn.execute(
            "SELECT last_source_key FROM article_interpretation_state"
        ).fetchone()[0]
        == "a"
    )
    resumed = service(storage).run(round_key="next-day")
    assert resumed["round_key"] == "stop" and resumed["status"] == "complete"
    assert len(articles.read_interpretations(storage.database)) == 3


def test_crash_after_ready_before_cursor_resumes_without_provider_or_double_advance(
    storage, monkeypatch
):
    seed(storage, "a")
    generator = Generator()
    runner = service(storage, generator=generator)
    original = runner._advance
    monkeypatch.setattr(runner, "_advance", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        runner.run(round_key="crash")
    assert len(generator.calls) == 1
    monkeypatch.setattr(runner, "_advance", original)
    resumed = runner.run(round_key="crash")
    assert resumed["status"] == "complete" and len(generator.calls) == 1
    assert (
        storage._conn.execute(
            "SELECT last_source_key FROM article_interpretation_state"
        ).fetchone()[0]
        == "c"
    )


def test_concurrent_run_claim_is_exclusive(storage):
    seed(storage, "a")
    entered, release, result = threading.Event(), threading.Event(), []

    async def hold():
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.01)

    generator = Generator(on_call=hold)

    def run():
        local = Storage(storage.database)
        try:
            result.append(service(local, generator=generator).run(round_key="concurrent"))
        finally:
            local.close()

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(10)
    try:
        assert service(storage).run(round_key="concurrent")["status"] == "busy"
    finally:
        release.set()
        thread.join(10)
    assert len(generator.calls) == 1 and result[0]["status"] == "complete"


def test_invalid_output_two_calls_then_next_source(storage):
    seed(storage, "a")
    seed(storage, "b")
    generator = Generator(output="invalid")
    receipt = service(storage, generator=generator).run(round_key="invalid")
    assert len(generator.calls) == 4
    assert [s["status"] for s in receipt["slots"]] == ["failed", "failed", "skipped"]
    assert all(
        len(a["calls"]) == 2
        for d in articles.read_interpretations(storage.database)
        for a in d["attempts"]
    )


def test_slow_generator_and_article_deadline_with_fake_clock(storage):
    seed(storage, "a")
    clock = [0.0]
    generator = Generator(on_call=lambda: clock.__setitem__(0, clock[0] + 91))
    receipt = service(storage, generator=generator, clock=lambda: clock[0]).run(round_key="slow")
    assert receipt["slots"][0]["status"] == "failed"
    assert len(generator.calls) == 1 and 0 < generator.calls[0]["timeout_seconds"] <= 90
    assert articles.read_interpretations(storage.database)[0]["error"] == "timeout"


def test_long_evidence_covers_end_and_model_limits():
    body = (
        source_body()
        + "\n\n"
        + "\n\n".join(
            f"## Method section {i}\n\n"
            + ("A substantive method and experiment is described here. " * 20)
            for i in range(80)
        )
        + "\n\n## Final limitations\n\n"
        + "The limitations constrain model application. " * 12
    )
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": body}
    messages, coverage = articles.build_input(
        row, {"model_context_tokens": 16000, "model_max_output_tokens": 2000}, {}
    )
    assert coverage["source_chars"] <= 24000
    assert coverage["all_input_chars"] <= 32000
    assert coverage["input_token_upper_bound"] + coverage["max_output_tokens"] <= 16000
    assert coverage["max_output_tokens"] == 2000
    assert coverage["uncovered_sections"]
    assert any(e["section"] == "Final limitations" for e in coverage["evidence"])
    assert all(body[e["start"] : e["end"]] == e["quote"] for e in coverage["evidence"])
    assert sum(len(m["content"]) for m in messages) == coverage["all_input_chars"]


@pytest.mark.parametrize("failure", ["spa", "foreign", "hidden", "version", "unreachable"])
def test_domestic_resolver_blocks_wrong_identity_and_unreachable(storage, failure):
    url = seed(storage, "a")
    row = articles._load_file(storage._conn, url)
    identity = articles._identity(row)

    class Reply:
        status_code = 200
        headers = {"content-type": "text/html" if failure == "spa" else "application/json"}

        def json(self):
            return {"file": {"url": "https://overseas.example/x" if failure == "foreign" else url}}

    def get(*args, **kwargs):
        assert args[0] == "https://aiactuary.cn/api/files/detail"
        assert kwargs["params"] == {"file_id": row["id"]}
        if failure == "unreachable":
            raise OSError("network unavailable")
        return Reply()

    resolver = articles.DomesticLinkResolver(storage._conn, environment="china", get=get)
    if failure == "hidden":
        storage._conn.execute("UPDATE files SET local_path='' WHERE url=?", (url,))
    if failure == "version":
        identity["markdown_sha256"] = "b" * 64
    with pytest.raises((ValueError, OSError)):
        resolver.resolve(identity, timeout_seconds=2)


def test_domestic_resolver_uses_native_id_and_encoded_route(storage):
    url = seed(storage, "a")
    row = articles._load_file(storage._conn, url)

    class Reply:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"file": {"url": url}}

    resolver = articles.DomesticLinkResolver(
        storage._conn, environment="china", get=lambda *a, **k: Reply()
    )
    result = resolver.resolve(articles._identity(row), timeout_seconds=2)
    assert result["china_article_url"] == f"https://aiactuary.cn/file-detail?file_id={row['id']}"
    assert result["link_identity"] == articles._identity(row)
    with pytest.raises(ValueError):
        articles.DomesticLinkResolver(storage._conn, environment="overseas")


def test_schedules_default_off_and_domestic_singleton():
    articles.validate_schedules({})
    task = {
        "type": "article_interpretation",
        "enabled": True,
        "interval": "daily at 10:00",
        "timezone": "Asia/Shanghai",
    }
    for environment in ("local", "overseas"):
        with pytest.raises(ValueError):
            articles.validate_schedules(
                {"article_interpretation": {"environment": environment}, "scheduled_tasks": [task]}
            )
    config = {"article_interpretation": {"environment": "china"}, "scheduled_tasks": [task]}
    articles.validate_schedules(config)
    with pytest.raises(ValueError):
        articles.validate_schedules({**config, "scheduled_tasks": [task, task]})


def test_authentication_stops_without_advancing_failed_slot(storage):
    seed(storage, "a")
    seed(storage, "b")
    generator = Generator(error=articles.LLMAuthenticationError("not configured"))
    runner = service(storage, generator=generator)
    receipt = runner.run(round_key="auth")
    assert receipt["status"] == "authentication" and len(generator.calls) == 1
    assert (
        storage._conn.execute(
            "SELECT last_source_key FROM article_interpretation_state"
        ).fetchone()[0]
        == ""
    )


def test_owned_transport_cleanup_failure_stops_before_next_source(storage):
    seed(storage, "a")
    seed(storage, "b")
    generator = Generator(error=articles.ArticleRequestCleanupError("not closed"))
    receipt = service(storage, generator=generator).run(round_key="cleanup-failed")
    assert receipt["status"] == "provider_cleanup" and len(generator.calls) == 1
    assert receipt["provider_calls"] == 1
    draft = storage._conn.execute("SELECT payload_json FROM article_interpretations").fetchone()[0]
    call = draft["attempts"][-1]["calls"][0]
    assert call["status"] == "cleanup_failed"
    assert call["charged_provider_seconds"] == call["timeout_seconds"]
    assert (
        storage._conn.execute(
            "SELECT last_source_key FROM article_interpretation_state"
        ).fetchone()[0]
        == ""
    )


def test_saved_article_survives_new_connection(storage):
    seed(storage, "a")
    receipt = service(storage).run(round_key="persist")
    connection = PostgresConnection(storage.database, read_only=True)
    try:
        assert (
            connection.execute("SELECT receipt_json FROM article_interpretation_rounds").fetchone()[
                0
            ]
            == receipt
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM article_interpretations WHERE status='ready'"
            ).fetchone()[0]
            == 1
        )
    finally:
        connection.close()


def test_round_six_calls_and_budget_includes_validation_retry(storage):
    for key in "abc":
        seed(storage, key)
    clock = [0.0]
    generator = Generator(output="bad", on_call=lambda: clock.__setitem__(0, clock[0] + 89))
    receipt = service(storage, generator=generator, clock=lambda: clock[0]).run(
        round_key="six-calls"
    )
    assert receipt["provider_calls"] == 6 and len(generator.calls) == 6
    assert receipt["elapsed_seconds"] == 534
    drafts = articles.read_interpretations(storage.database)
    assert all(a["provider_seconds"] == 178 for d in drafts for a in d["attempts"])
    assert all(a["elapsed_seconds"] <= 240 for d in drafts for a in d["attempts"])


def test_expired_article_resumes_without_starting_provider(storage):
    seed(storage, "a")
    generator = Generator()
    runner = service(storage, generator=generator)
    row, decisions = runner._select("a")
    draft, _ = runner._prepare(row, "a", decisions[-1]["reason"])
    draft["selection_started_at"] = "2000-01-01T00:00:00+00:00"
    runner._save(draft)
    result = runner._generate(draft, round_deadline=runner.clock() + 900)
    assert result["error"] == "budget_exhausted" and not generator.calls


def test_round_budget_resume_does_not_start_next_source(storage):
    seed(storage, "a")
    runner = service(storage)
    receipt = {
        "round_key": "exhausted",
        "status": "stopped",
        "timezone": "Asia/Shanghai",
        "next_run": None,
        "elapsed_seconds": 900,
        "provider_calls": 0,
        "slots": [{"source_key": k, "status": "queued", "decisions": []} for k in "abc"],
    }
    storage._conn.execute(
        "INSERT INTO article_interpretation_rounds VALUES (?,?::jsonb, CURRENT_TIMESTAMP)",
        ("exhausted", articles._json(receipt)),
    )
    result = runner.run(round_key="next-day")
    assert result["status"] == "budget_exhausted" and result["provider_calls"] == 0
    next_day = runner.run(round_key="next-day")
    assert next_day["round_key"] == "next-day" and next_day["status"] == "complete"


def test_wall_clock_timeout_starts_no_retry_and_preserves_previous_ready(storage, monkeypatch):
    first_url = seed(storage, "a")
    service(storage).run(round_key="previous")
    previous = articles.read_interpretations(storage.database)[0]
    seed(storage, "d", body=source_body("updated"), url="https://d.example/updated.pdf")
    monkeypatch.setattr(articles, "MAX_CALL_SECONDS", 0.03)
    generator = Generator(on_call=lambda: asyncio.sleep(0.1))
    result = service(storage, generator=generator).run(round_key="slow-wall")
    assert len(generator.calls) == 1 and result["provider_calls"] == 1
    assert (
        next(
            d for d in articles.read_interpretations(storage.database) if d["file_url"] == first_url
        )
        == previous
    )


def test_output_rejects_unsupported_numbers_quotes_and_unlabelled_inference():
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    messages, coverage = articles.build_input(row, {}, {})
    original = json.loads(response(messages))
    for text, kind, error in (
        ("研究证明收益提高999%。", "source", "unsupported_number"),
        ("原文称“并不存在的引文”。", "source", "unsupported_quote"),
        ("我们可以因此断定可推广。", "inference", "unlabelled_inference"),
        ("公式 a=b。", "source", "formula_requires"),
    ):
        value = json.loads(json.dumps(original))
        value["sections"][0]["paragraphs"][0].update(text=text, kind=kind)
        with pytest.raises(ValueError, match=error):
            articles.validate_output(json.dumps(value), coverage)

    value = json.loads(json.dumps(original))
    value["authors"] = ["Unverified Person"]
    with pytest.raises(ValueError, match="author_metadata_mismatch"):
        articles.validate_output(json.dumps(value), coverage)


def test_title_page_author_extraction_is_explicit_and_bounded():
    france = (
        "Fidélisation des assurés\n\n###### Virginie Normand\n\n"
        "Responsable Domaine Décisionnel VIASANTE Mutuelle\n\n"
        "###### Léonard Fontaine\n\nAssocié Galea &amp; Associés\n\n"
        "# Main Article\n\n###### Incidental Person\n\nProfessor of Something\n\n" + source_body()
    )
    assert articles.extract_title_page_author_metadata(france) == [
        {
            "name": "Virginie Normand",
            "quote": "###### Virginie Normand\nResponsable Domaine Décisionnel VIASANTE Mutuelle",
        },
        {
            "name": "Léonard Fontaine",
            "quote": "###### Léonard Fontaine\nAssocié Galea &amp; Associés",
        },
    ]

    # These nonauthor names are in an acknowledgment section of the same saved
    # SOA source, after its contents boundary.
    soa = (Path(__file__).parent / "fixtures/article_interpretation_soa_title_page.md").read_text(
        encoding="utf-8"
    )
    soa_authors = articles.extract_title_page_author_metadata(soa)
    assert [entry["name"] for entry in soa_authors] == [
        "Satya Sai Mudigonda",
        "Pallav Kumar Baruah",
        "Phani Krishna Kandala",
        "Rohan Yashraj Gupta",
        "Srinand N Hegde",
        "Sumanth Chebrolu",
    ]
    assert "R. Dale Hall" not in {entry["name"] for entry in soa_authors}
    assert "Achilles Natsis" not in {entry["name"] for entry in soa_authors}

    assert articles.extract_title_page_author_metadata(
        "By the CAS Machine Learning Working Party\n\n# Main Article\n\n" + source_body()
    ) == [
        {
            "name": "CAS Machine Learning Working Party",
            "quote": "By the CAS Machine Learning Working Party",
        }
    ]
    assert (
        articles.extract_title_page_author_metadata(
            "Casualty Actuarial Society\n\n# Main Article\n\n" + source_body()
        )
        == []
    )
    assert (
        articles.extract_title_page_author_metadata(
            "By working with the research team\n\n# Main Article\n\n" + source_body()
        )
        == []
    )
    assert articles.extract_title_page_author_metadata(
        "R. Dale Hall, FSA, MAAA, Managing Director, Research\n"
        "Advisor Jane Smith, PhD, Senior Researcher\n"
        "Contact: Alex Example, Actuary\n\n"
        "Author: Verified Author, PhD, Professor of Statistics\n\n"
        "### Contents\n\n" + source_body()
    ) == [
        {
            "name": "Verified Author",
            "quote": "Author: Verified Author, PhD, Professor of Statistics",
        }
    ]

    assert (
        articles.extract_title_page_author_metadata(
            "# Main article\n\n###### Incidental Person\n\nProfessor of Mathematics\n\n"
            + source_body()
        )
        == []
    )


def test_article_adapter_closes_owned_client_and_preserves_length_metadata(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())),
        close=AsyncMock(),
        is_closed=lambda: True,
    )
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(articles.openai, "AsyncOpenAI", factory)
    runtime = SimpleNamespace(
        provider="deepseek", model="deepseek-flash", api_key="fixture", base_url=None
    )
    sdk.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length", message=SimpleNamespace(content="partial", refusal=None)
            )
        ],
        usage=SimpleNamespace(completion_tokens=6000),
    )
    adapter = articles.ChatArticleGenerator(runtime, 6000)
    with pytest.raises(ValueError, match="provider_output_truncated"):
        asyncio.run(
            adapter.generate([{"role": "user", "content": "JSON"}], deadline=time.monotonic() + 17)
        )
    assert factory.call_args.kwargs["max_retries"] == 0
    assert 0 < factory.call_args.kwargs["timeout"] <= 17
    assert adapter.last_call_metadata["finish_reason"] == "length"
    assert adapter.last_call_metadata["completion_tokens"] == 6000
    assert adapter.last_call_metadata["owned_client_closed"]
    sdk.close.assert_awaited_once()
    assert sdk.chat.completions.create.call_args.kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_blocking_sync_generator_is_explicitly_unsupported(storage):
    class Blocking:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("must never start blocking work")

    with pytest.raises(TypeError, match="requires_cancellable_async"):
        service(storage, generator=Blocking())


@pytest.mark.parametrize("close_error", [None, RuntimeError("close failed")])
def test_article_adapter_requires_confirmed_owned_transport_closure(monkeypatch, close_error):
    from unittest.mock import AsyncMock

    sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=None))),
        close=AsyncMock(side_effect=close_error),
        is_closed=lambda: False,
    )
    monkeypatch.setattr(articles.openai, "AsyncOpenAI", lambda **_: sdk)
    runtime = SimpleNamespace(
        provider="deepseek", model="deepseek-flash", api_key="fixture", base_url=None
    )
    adapter = articles.ChatArticleGenerator(runtime, 6000)
    with pytest.raises(articles.ArticleRequestCleanupError):
        asyncio.run(adapter.generate([], deadline=time.monotonic() + 2))
    sdk.close.assert_awaited_once()
    assert not adapter.last_call_metadata["owned_client_closed"]


def test_native_task_stop_history_and_restart(storage, tmp_path):
    from ai_actuarial.task_runtime import NativeTaskRuntime

    for key in "abc":
        seed(storage, key)
    runtime = NativeTaskRuntime(
        ready_data_database=storage.database,
        data_root=tmp_path,
        article_interpretation_resolver=Resolver(),
    )
    runtime._site_config_override = {"paths": {"download_dir": str(tmp_path)}}
    generator = Generator(on_call=lambda: runtime._update_task("stop-native", stop_requested=True))
    runtime._article_interpretation_generator = generator
    runtime.start_background_task("article_interpretation", {}, task_id="stop-native")
    deadline = time.monotonic() + 10
    while runtime.active_tasks and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not runtime.active_tasks and len(generator.calls) == 1
    assert runtime.task_history[0]["status"] == "stopped"
    reloaded = NativeTaskRuntime(ready_data_database=storage.database, data_root=tmp_path)
    assert reloaded.task_history[0]["status"] == "stopped"
    assert service(storage).run()["status"] == "complete"


def test_api_read_empty_and_cli_entry_contract(storage, tmp_path, monkeypatch):
    from ai_actuarial import cli
    from tests.test_fastapi_ops_read_endpoints import _build_test_client

    client, app, _ = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    response_data = client.get("/api/article-interpretations")
    assert response_data.status_code == 200 and response_data.json() == {"interpretations": []}
    requests = []
    monkeypatch.setattr(
        cli,
        "_api_json_request",
        lambda *args, **kwargs: requests.append((args, kwargs)) or {"success": True},
    )
    parser = cli.build_parser()
    for command in (
        ["article-interpretation", "run", "--json"],
        ["article-interpretation", "retry", "saved-id", "--json"],
        ["article-interpretation", "get", "saved-id", "--json"],
    ):
        args = parser.parse_args(command)
        assert args.func(args) == 0
    assert requests[0][0][1] == "/api/collections/run"
    assert requests[1][1]["payload"] == {"type": "article_interpretation", "retry_id": "saved-id"}
    assert requests[2][1]["method"] == "GET"
    help_result = subprocess.run(
        [sys.executable, "-m", "ai_actuarial.cli", "article-interpretation", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert help_result.returncode == 0 and "retry" in help_result.stdout


def test_reader_api_returns_only_current_public_latest_fields(tmp_path, monkeypatch):
    from ai_actuarial.api.routers import article_interpretations as reader_api
    from tests.test_fastapi_ops_read_endpoints import _build_test_client

    client, _, _ = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    public = {
        "interpretation_id": "current",
        "file_url": "https://example.test/article",
        "title_zh": "文章标题",
        "body_markdown_zh": "正文",
        "generated_at": "2026-10-30T00:00:00Z",
        "raw_sha256": "raw",
        "markdown_sha256": "markdown",
        "china_article_url": "https://aiactuary.cn/file-detail?file_id=1386",
        "references": {
            "published_time": "2026-10-01",
            "source": {"name_zh": "来源"},
            "authors": ["Verified Author"],
        },
        "provider": "private-provider",
        "error": "internal-error",
        "attempts": [{"credential": "private"}],
        "reader_eligible": True,
        "status": "ready",
    }
    monkeypatch.setattr(
        reader_api,
        "read_interpretations",
        lambda *a, **_kw: [
            {**public, "interpretation_id": "failed", "reader_eligible": False},
            public,
            {**public, "interpretation_id": "older"},
        ],
    )
    response = client.get(
        "/api/article-interpretations?file_url=https%3A%2F%2Fexample.test%2Farticle"
    )
    assert response.status_code == 200
    assert response.json() == {
        "interpretations": [
            {
                key: public[key]
                for key in (
                    "interpretation_id",
                    "title_zh",
                    "body_markdown_zh",
                    "generated_at",
                    "file_url",
                    "raw_sha256",
                    "markdown_sha256",
                    "china_article_url",
                    "references",
                )
            }
        ]
    }


def test_france_title_page_authors_reach_reader_api_from_saved_markdown(tmp_path, monkeypatch):
    from tests.test_fastapi_ops_read_endpoints import _build_test_client

    client, _, _ = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    database = postgres_url_for_path(tmp_path / "index.db")
    # This is the verbatim saved title-page excerpt; append only generic test prose
    # so the normal eligibility and generation path can run offline.
    saved_title_page = (
        Path(__file__).parent / "fixtures/article_interpretation_france_title_page.md"
    ).read_text(encoding="utf-8")
    saved_markdown = saved_title_page + "\n\n" + source_body("mutuelle")
    authors = [
        "Virginie Normand",
        "Léonard Fontaine",
        "Vincent Dalon",
        "Alexandre Eby",
    ]
    url = "https://www.institutdesactuaires.com/global/gene/link.php?doc_id=17510&fg=1"
    storage = Storage(database)
    try:
        storage._conn.execute(
            "INSERT INTO canonical_sources VALUES ('france','Institut des actuaires',"
            "'Institut des actuaires','active',NULL,'{}'::jsonb)"
        )
        storage._conn.execute(
            "INSERT INTO source_aliases VALUES "
            "('www.institutdesactuaires.com','hostname','france','verified','{}'::jsonb)"
        )
        seed(
            storage,
            "france",
            body=saved_markdown,
            title="Machine Learning for Health Insurance Member Retention: A Case Study",
            date="2022-09",
            url=url,
        )
        generator = Generator()
        resolver = Resolver(fail=True)
        runner = service(storage, generator=generator, resolver=resolver)
        receipt = runner.run(round_key="france-authors")
        assert receipt["status"] == "complete"
        assert len(generator.calls) == 1
        interpretation_id = receipt["slots"][0]["interpretation_id"]
        failed = runner._get(interpretation_id)
        assert failed["status"] == "failed" and failed["authors"] == authors
        resolver.fail = False
        retried = runner.run(retry_id=interpretation_id)["interpretation"]
        assert retried["status"] == "ready"
        assert retried["references"]["authors"] == authors
        assert len(generator.calls) == 1
        material = json.loads(generator.calls[0]["messages"][-1]["content"])
        assert [entry["name"] for entry in material["author_metadata"]] == authors
        assert all(
            name in "\n".join(entry["quote"] for entry in material["author_metadata"])
            for name in authors
        )
        assert "summary" not in material

        readback = articles.read_interpretations(database, file_url=url)
        assert len(readback) == 1 and readback[0]["reader_eligible"]
        assert [entry["name"] for entry in readback[0]["coverage"]["author_metadata"]] == authors
        assert readback[0]["authors"] == authors
        assert readback[0]["references"]["authors"] == authors
        assert readback[0]["coverage"]["all_input_chars"] == sum(
            len(message["content"]) for message in generator.calls[0]["messages"]
        )
        assert readback[0]["coverage"]["input_token_upper_bound"] == sum(
            len(message["content"].encode("utf-8")) + 16
            for message in generator.calls[0]["messages"]
        )
        public = client.get("/api/article-interpretations", params={"file_url": url})
        assert public.status_code == 200
        assert public.json()["interpretations"][0]["references"]["authors"] == authors
        assert public.json()["interpretations"][0]["references"]["published_time"] == "2022-09"
        current = storage._conn.execute(
            "SELECT markdown_content FROM catalog_items WHERE file_url=?", (url,)
        ).fetchone()[0]
        assert current == saved_markdown
    finally:
        storage.close()


def test_native_domestic_schedule_metadata_and_local_rejection(storage, tmp_path):
    from ai_actuarial.api.services.ops_read import get_schedule_status
    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime(ready_data_database=storage.database, data_root=tmp_path)
    runtime._scheduler_loop_started = True
    task = {
        "name": "Daily interpretation",
        "type": "article_interpretation",
        "enabled": True,
        "interval": "daily at 10:00",
        "timezone": "Asia/Shanghai",
    }
    runtime._site_config_override = {
        "article_interpretation": {"environment": "china"},
        "scheduled_tasks": [task],
    }
    runtime.init_scheduler(configured_only=True)
    job = get_schedule_status(runtime.scheduler)["jobs"][0]
    assert job["timezone"] == "Asia/Shanghai" and job["next_run"]
    runtime._site_config_override["article_interpretation"]["environment"] = "local"
    with pytest.raises(ValueError, match="china"):
        runtime.init_scheduler(configured_only=True)
    assert len(runtime.scheduler.jobs) == 1


def test_native_schema_dump_restore_contains_drafts_and_cursor(storage, tmp_path):
    """Exercise the same native clients as the application's schema backup."""
    from ai_actuarial.postgres import run_postgres_dump, run_postgres_restore

    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("native PostgreSQL clients not installed")
    seed(storage, "a")
    before = service(storage).run(round_key="backup")
    schema = storage._conn.execute("SELECT current_schema()").fetchone()[0]
    assert schema.startswith("test_")
    dump = tmp_path / "article-backup.dump"
    run_postgres_dump(storage.database, dump, schema=schema)
    storage._conn.execute("DROP SCHEMA " + schema + " CASCADE")
    storage._conn.execute("CREATE SCHEMA " + schema)
    run_postgres_restore(storage.database, dump, schema=schema)
    assert (
        storage._conn.execute("SELECT receipt_json FROM article_interpretation_rounds").fetchone()[
            0
        ]
        == before
    )
    assert articles.read_interpretations(storage.database)[0]["reader_eligible"]


def test_orphan_queued_draft_after_crash_is_reclaimed(storage, monkeypatch):
    seed(storage, "a")
    generator = Generator()
    runner = service(storage, generator=generator)
    original = runner._receipt

    def crash(receipt):
        if receipt["slots"][0].get("interpretation_id"):
            raise KeyboardInterrupt()
        original(receipt)

    monkeypatch.setattr(runner, "_receipt", crash)
    with pytest.raises(KeyboardInterrupt):
        runner.run(round_key="orphan")
    assert not generator.calls
    assert (
        storage._conn.execute("SELECT status FROM article_interpretations").fetchone()[0]
        == "queued"
    )
    monkeypatch.setattr(runner, "_receipt", original)
    resumed = runner.run(round_key="orphan")
    assert resumed["status"] == "complete" and len(generator.calls) == 1
    assert storage._conn.execute("SELECT count(*) FROM article_interpretations").fetchone()[0] == 1


def test_provider_metadata_retained_without_prompt_or_secret():
    from ai_actuarial.chatbot.llm import LLMClient

    client = LLMClient.__new__(LLMClient)
    client.config = SimpleNamespace(llm_provider="deepseek")
    response_data = SimpleNamespace(
        id="response-id",
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=6000,
            total_tokens=6100,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=5500),
        ),
    )
    client._log_response_metadata(
        response_data,
        model="deepseek-flash",
        finish_reason="length",
        classification="text",
        attempt=1,
        recovery=False,
        successful=True,
    )
    assert client.last_response_metadata == {
        "finish_reason": "length",
        "prompt_tokens": 100,
        "completion_tokens": 6000,
        "total_tokens": 6100,
        "reasoning_tokens": 5500,
    }


def test_declared_chat_model_limits_cannot_be_raised_by_article_settings(storage, monkeypatch):
    from ai_actuarial.ai_runtime import AIFunctionRuntime

    seed(storage, "a")
    runtime = AIFunctionRuntime(
        function_name="chatbot",
        provider="deepseek",
        model="fixture-model",
        configured=True,
        stable_credential_id="fixture-credential",
        raw_config={
            "model_context_tokens": 8000,
            "model_max_output_tokens": 2000,
            "max_tokens": 32,
        },
    )
    monkeypatch.setattr(articles, "resolve_ai_function_runtime", lambda *a, **k: runtime)
    runner = articles.ArticleInterpretationService(
        storage,
        resolver=Resolver(),
        config={
            "model_context_tokens": 999999,
            "model_max_output_tokens": 999999,
            "max_tokens": 999999,
        },
    )
    row, decisions = runner._select("a")
    draft, actual_runtime = runner._prepare(row, "a", decisions[-1]["reason"])
    assert draft["coverage"]["context_tokens"] == 8000
    assert draft["coverage"]["max_output_tokens"] == 2000
    assert draft["coverage"]["generation_options"]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert actual_runtime is runtime


@pytest.mark.parametrize("cap", [2000, 6000])
@pytest.mark.parametrize(
    "provider,model",
    [
        ("deepseek", "deepseek-flash"),
        ("qwen", "qwen-plus"),
        ("openai", "gpt-6"),
        ("openai", "gpt-5"),
    ],
)
def test_actual_async_sdk_request_reuses_chat_compatibility_kwargs(
    monkeypatch, cap, provider, model
):
    from unittest.mock import AsyncMock, Mock

    from ai_actuarial.chatbot.config import ChatbotConfig
    from ai_actuarial.chatbot.llm import LLMClient

    sdk = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(
                    return_value=SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                finish_reason="stop",
                                message=SimpleNamespace(content="{}", refusal=None),
                            )
                        ],
                        usage=SimpleNamespace(
                            prompt_tokens=100, completion_tokens=10, total_tokens=110
                        ),
                    )
                )
            )
        ),
        close=AsyncMock(),
        is_closed=lambda: True,
    )
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(articles.openai, "AsyncOpenAI", factory)
    runtime = SimpleNamespace(
        provider=provider, model=model, api_key="fixture", base_url="https://api.example.test"
    )
    adapter = articles.ChatArticleGenerator(runtime, cap)
    messages = [{"role": "user", "content": "Return JSON"}]
    assert asyncio.run(adapter.generate(messages, deadline=time.monotonic() + 73)) == "{}"
    # Construct no sync transport: exercise the unchanged Chat method with just its config.
    chat = LLMClient.__new__(LLMClient)
    chat.config = ChatbotConfig(
        llm_provider=provider, model=model, api_key="fixture", _apply_env_defaults=False
    )
    expected = chat._completion_request_kwargs(
        messages=messages,
        model=model,
        temperature=0.0,
        max_tokens=cap,
        stream=False,
        **articles._request_options(provider),
    )
    assert sdk.chat.completions.create.call_args.kwargs == expected
    assert factory.call_args.kwargs["api_key"] == "fixture"
    assert factory.call_args.kwargs["base_url"] == runtime.base_url
    assert factory.call_args.kwargs["max_retries"] == 0
    assert 0 < factory.call_args.kwargs["timeout"] <= 73
    sdk.close.assert_awaited_once()
    assert adapter.last_call_metadata["finish_reason"] == "stop"
    assert adapter.last_call_metadata["owned_client_closed"]


@pytest.mark.parametrize(
    "target,source",
    [
        ("64142起", "64,142 reported cases"),
        ("687亿美元", "68.7 billion USD"),
        ("0", "0.0"),
        ("1.6倍", "1,6 fois supérieur"),
        ("2018年9月", "September 2018"),
        ("0.142%", "0,142%"),
        ("1e-3", "0.001"),
        ("123456789012345678901234567890亿美元", "12345678901234567890123456789 billion USD"),
    ],
)
def test_numeric_normalization_accepts_only_exact_explicit_equivalence(target, source):
    assert articles._quantities(target, strict=True).issubset(articles._quantities(source))


@pytest.mark.parametrize(
    "target,source",
    [
        ("64143起", "64,142 reported cases"),
        ("688亿美元", "68.7 billion USD"),
        ("68.7亿美元", "68.7 billion USD"),
        ("687亿人民币", "68.7 billion USD"),
        ("0.01", "0.0"),
        ("1.7倍", "1,6 fois supérieur"),
        ("2018年8月", "September 2018"),
        ("5月", "The method may improve accuracy."),
        ("0.14%", "0,142%"),
        ("3.8%", "-3.8%"),
        ("73%", "0.73 probability"),
        ("123456789012345678901234567891亿美元", "12345678901234567890123456789 billion USD"),
    ],
)
def test_numeric_normalization_rejects_near_miss_wrong_dimension_and_rounding(target, source):
    assert not articles._quantities(target, strict=True).issubset(articles._quantities(source))


def test_unsupported_numeric_format_remains_rejected():
    with pytest.raises(ValueError, match="unsupported_number_format"):
        articles._quantities("1.234,567", strict=True)


@pytest.mark.parametrize(
    "target,source",
    [
        ("12年", "12 years"),
        ("12个月", "12 months"),
        ("12周", "12 weeks"),
        ("12天", "12 days"),
        ("12小时", "12 hours"),
        ("2022财年", "fiscal year 2022"),
        ("1,234", "1,234"),
    ],
)
def test_explicit_time_units_and_unchanged_ambiguous_spelling(target, source):
    assert articles._quantities(target, strict=True).issubset(articles._quantities(source))


@pytest.mark.parametrize(
    "target,source",
    [
        ("12个月", "12 years"),
        ("12年", "12 days"),
        ("12周", "12 hours"),
        ("12小时", "12 days"),
        ("12天", "12 months"),
        ("1234", "1,234"),
        ("1.234", "1,234"),
        ("1234 USD", "1,234 USD"),
        ("1234起", "1,234 expected cases"),
        ("10000欧元", "10000"),
    ],
)
def test_time_dimension_and_ambiguous_comma_do_not_get_guessed(target, source):
    assert not articles._quantities(target, strict=True).issubset(articles._quantities(source))


def test_current_registry_names_are_in_input_fingerprint_receipt_and_references(storage):
    seed(storage, "a")
    storage._conn.execute(
        "UPDATE canonical_sources SET name_zh=?,name_en=? WHERE source_key='a'",
        ("当前规范机构", "Current Registry Institution"),
    )
    generator = Generator()
    receipt = service(storage, generator=generator).run(round_key="source-names")
    source = {
        "source_key": "a",
        "name_zh": "当前规范机构",
        "name_en": "Current Registry Institution",
    }
    assert json.loads(generator.calls[0]["messages"][-1]["content"])["source"] == source
    slot = receipt["slots"][0]
    assert slot["source"] == source
    draft = articles.read_interpretations(storage.database)[0]
    assert draft["coverage"]["source"] == source and draft["references"]["source"] == source
    assert draft["canonical_source"] == source and "当前规范机构" in draft["body_markdown_zh"]
    assert slot["input_fingerprint"] == draft["input_fingerprint"]
    changed = {**draft["coverage"], "source": {**source, "name_zh": "另一个名字"}}
    assert (
        articles._hash(
            articles._json({"messages": generator.calls[0]["messages"], "coverage": changed})
        )
        != draft["input_fingerprint"]
    )
    storage._conn.execute(
        "UPDATE canonical_sources SET name_zh='更新后的名称' WHERE source_key='a'"
    )
    assert (
        articles.read_interpretations(storage.database)[0]["canonical_source"]["name_zh"]
        == "更新后的名称"
    )


@pytest.mark.parametrize("key,status", [("a", "retired"), ("pending", "active")])
def test_retired_and_pending_source_names_never_become_institution_fallback(storage, key, status):
    url = seed(storage, "a")
    if key == "pending":
        storage._conn.execute(
            "INSERT INTO canonical_sources VALUES ('pending','待确认','Pending','active',NULL,'{}'::jsonb)"
        )
    else:
        storage._conn.execute("UPDATE canonical_sources SET status='retired' WHERE source_key='a'")
    runner = service(storage)
    row = articles._load_file(storage._conn, url)
    with pytest.raises(ValueError, match="canonical_source_unavailable"):
        runner._prepare(row, key, "fixture")
    assert not articles._canonical_source(storage._conn, "pending")


def test_explicit_french_year_is_supported_without_guessing_counts():
    assert articles._quantities("2002年", strict=True).issubset(
        articles._quantities("introduit en 2002")
    )
    assert not articles._quantities("2003年", strict=True).issubset(
        articles._quantities("introduit en 2002")
    )
    assert ("year", articles.Decimal(2002)) not in articles._quantities("en 2002 cases")
    assert articles._quantities("12个月", strict=True).issubset(
        articles._quantities("12 mois d’ancienneté")
    )
    assert not articles._quantities("12年", strict=True).issubset(
        articles._quantities("12 mois d’ancienneté")
    )


@pytest.mark.parametrize("kind,label", [("example", "说明性例子"), ("inference", "解读推断")])
def test_supported_numeric_example_and_inference_are_allowed(kind, label):
    body = source_body().replace(
        "The experiment compares", "The experiment sets both flags to 1 and compares"
    )
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": body}
    messages, coverage = articles.build_input(row, {}, {})
    value = json.loads(response(messages))
    paragraph = value["sections"][0]["paragraphs"][0]
    paragraph.update(kind=kind, text=f"{label}：沿用原文的标志取值1来说明这一机制。")
    assert (
        articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)["claims"][0][
            "kind"
        ]
        == kind
    )
    paragraph["text"] = f"{label}：把标志改为2来说明这一机制。"
    with pytest.raises(ValueError, match="unsupported_number"):
        articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)


@pytest.mark.parametrize(
    "text",
    [
        "第一阶段进行训练。",
        "第二阶段进行解释。",
        "二次验证后使用。",
        "第三部分讨论限制。",
        "第一次调用。",
    ],
)
def test_unsupported_chinese_numeric_ordinals_and_counts_are_rejected(text):
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    messages, coverage = articles.build_input(row, {}, {})
    value = json.loads(response(messages))
    value["sections"][0]["paragraphs"][0]["text"] = text
    with pytest.raises(ValueError, match="unsupported_number"):
        articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)


@pytest.mark.parametrize(
    "text",
    [
        "一起判断并保持一致。",
        "统一口径，一方面核对数据，另一方面核对假设。",
        "一次性分类只是描述问题的形式。",
    ],
)
def test_non_counting_chinese_idioms_are_not_mistaken_for_numeric_claims(text):
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    messages, coverage = articles.build_input(row, {}, {})
    value = json.loads(response(messages))
    value["sections"][0]["paragraphs"][0]["text"] = text
    assert articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)["claims"]


def test_article_deadline_failure_advances_to_next_source(storage, monkeypatch):
    for key in "abc":
        seed(storage, key)
    generator = Generator()
    runner = service(storage, generator=generator)
    prepare = runner._prepare

    def expired(*args):
        draft, runtime = prepare(*args)
        if draft["source_key"] == "a":
            draft["selection_started_at"] = "2000-01-01T00:00:00+00:00"
            runner._save(draft)
        return draft, runtime

    monkeypatch.setattr(runner, "_prepare", expired)
    receipt = runner.run(round_key="expired-round")
    assert receipt["status"] == "complete" and len(generator.calls) == 2
    assert [s["status"] for s in receipt["slots"]] == ["failed", "ready", "ready"]
    assert receipt["slots"][0]["advanced"]


def test_round_receipt_counts_new_calls_not_prior_manual_retry_calls(storage):
    seed(storage, "a")
    generator = Generator(output="bad JSON")
    runner = service(storage, generator=generator)
    first = runner.run(round_key="old-failure")
    assert first["provider_calls"] == 2
    runner.run(retry_id=first["slots"][0]["interpretation_id"])
    assert len(generator.calls) == 2
    runner.run(round_key="middle")
    result = runner.run(round_key="reconsider")
    assert result["provider_calls"] == 0 and len(generator.calls) == 2


def test_generation_retry_preserves_attempt_and_origin_round_accounting(storage):
    seed(storage, "a")
    stopped = [False]
    generator = Generator(output="invalid", on_call=lambda: stopped.__setitem__(0, True))
    runner = service(storage, generator=generator, stop_check=lambda: stopped[0])
    first = runner.run(round_key="partial-origin")
    identity = first["slots"][0]["interpretation_id"]
    assert first["status"] == "stopped" and first["provider_calls"] == 1
    stopped[0] = False
    generator.on_call = None
    retried = runner.run(retry_id=identity)["interpretation"]
    assert len(generator.calls) == 2 and len(retried["attempts"]) == 1
    origin = runner._origin_receipt(runner._content_budget(retried["content_key"]))
    assert origin["provider_calls"] == 2 and origin["status"] == "stopped"
    resumed = runner.run(round_key="ignored-while-unfinished")
    assert resumed["round_key"] == "partial-origin" and resumed["provider_calls"] == 2
    assert resumed["status"] == "complete"
    runner.run(retry_id=identity)
    assert len(generator.calls) == 2


def test_same_content_new_prompt_and_route_fingerprint_cannot_renew_budget(storage, monkeypatch):
    seed(storage, "a")
    generator = Generator(output="invalid")
    runner = service(storage, generator=generator)
    first = runner.run(round_key="original")
    old = runner._get(first["slots"][0]["interpretation_id"])
    # A different recipe and provider produce a new generation fingerprint, not new content.
    monkeypatch.setattr(articles, "PROMPT_VERSION", "article-interpretation-test-new")
    generator.runtime = SimpleNamespace(
        provider="other",
        model="other-model",
        stable_credential_id="other-route",
        base_url=None,
        raw_config={},
    )
    row, decisions = runner._select("a")
    assert row is None and decisions[0]["reason"].startswith("content_")
    new, _ = runner._prepare(
        articles._load_file(storage._conn, old["file_url"]), "a", "manual fixture"
    )
    assert old["input_fingerprint"] != new["input_fingerprint"]
    assert old["content_key"] == new["content_key"]
    assert new["selection_started_at"] == old["selection_started_at"]
    assert new["origin_round_key"] == "original"
    result = runner._generate(new, round_deadline=runner.clock() + 900)
    assert result["error"] == "budget_exhausted" and result["attempts"] == []
    assert len(generator.calls) == 2
    assert runner._content_budget(new["content_key"])["calls"] == 2


@pytest.mark.parametrize("exhaustion", ["selection", "round_time", "round_calls", "provider_time"])
def test_generation_retry_cannot_refresh_any_original_budget(storage, exhaustion):
    seed(storage, "a")
    stopped = [False]
    generator = Generator(output="invalid", on_call=lambda: stopped.__setitem__(0, True))
    runner = service(storage, generator=generator, stop_check=lambda: stopped[0])
    receipt = runner.run(round_key="strict-origin")
    identity = receipt["slots"][0]["interpretation_id"]
    draft = runner._get(identity)
    if exhaustion == "selection":
        draft["selection_started_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=241)
        ).isoformat()
    elif exhaustion == "round_time":
        receipt["started_at"] = (datetime.now(timezone.utc) - timedelta(seconds=901)).isoformat()
        runner._receipt(receipt)
    elif exhaustion == "round_calls":
        receipt["provider_calls"] = 6
        runner._receipt(receipt)
    else:
        draft["attempts"][0]["provider_seconds"] = 180
    runner._save(draft)
    before = runner._get(identity)["attempts"]
    stopped[0] = False
    result = runner.run(retry_id=identity)["interpretation"]
    assert result["error"] == "budget_exhausted" and len(generator.calls) == 1
    assert result["attempts"] == before


def test_provider_seconds_and_calls_accumulate_across_legacy_attempts(storage):
    seed(storage, "a")
    runner = service(storage)
    row, audit = runner._select("a")
    draft, _ = runner._prepare(row, "a", audit[-1]["reason"])
    draft["attempts"] = [
        {
            "started_at": draft["selection_started_at"],
            "calls": [{"status": "failed"}],
            "provider_seconds": 89,
        },
        {
            "started_at": draft["selection_started_at"],
            "calls": [{"status": "failed"}],
            "provider_seconds": 90,
        },
    ]
    runner._save(draft)
    assert runner._content_budget(draft["content_key"])["provider_seconds"] == 179
    result = runner.run(retry_id=draft["interpretation_id"])["interpretation"]
    assert result["error"] == "budget_exhausted" and not runner.generator.calls
    assert len(result["attempts"]) == 2


def test_late_link_only_retry_has_independent_receipt_and_unchanged_generation(storage):
    seed(storage, "a")
    generator, resolver = Generator(), Resolver(fail=True)
    runner = service(storage, generator=generator, resolver=resolver)
    original = runner.run(round_key="link-origin")
    identity = original["slots"][0]["interpretation_id"]
    before = runner._get(identity)
    origin_before = runner._origin_receipt(runner._content_budget(before["content_key"]))
    resolver.fail = False
    late = service(
        storage,
        generator=generator,
        resolver=resolver,
        now=lambda: datetime.now(timezone.utc) + timedelta(days=2),
    )
    result = late.run(retry_id=identity)
    after, receipt = result["interpretation"], result["retry_receipt"]
    assert after["status"] == "ready" and len(generator.calls) == 1
    assert after["attempts"] == before["attempts"]
    assert after["generated_at"] == before["generated_at"]
    assert after["claims"] == before["claims"]
    assert receipt["receipt_type"] == "link_validation"
    assert receipt["provider_calls"] == receipt["provider_seconds"] == 0
    assert late._origin_receipt(late._content_budget(before["content_key"])) == origin_before
    saved = storage._conn.execute(
        "SELECT receipt_json FROM article_interpretation_rounds WHERE round_key=?",
        (receipt["round_key"],),
    ).fetchone()[0]
    assert saved == receipt
    assert (
        late.run(round_key="following-generation-round")["round_key"]
        == "following-generation-round"
    )


def test_api_different_client_round_keys_reuse_same_shanghai_day(storage, tmp_path, monkeypatch):
    from ai_actuarial.task_runtime import NativeTaskRuntime
    from tests.test_fastapi_ops_read_endpoints import _build_test_client

    for key in "abcdef":
        seed(storage, key)
    client, app, auth = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    generator = Generator()
    runtime = NativeTaskRuntime(
        ready_data_database=storage.database,
        data_root=tmp_path,
        article_interpretation_generator=generator,
        article_interpretation_resolver=Resolver(),
    )
    runtime._site_config_override = {"paths": {"download_dir": str(tmp_path)}}
    app.state.native_task_runtime = runtime
    app.state.start_background_task = runtime.start_background_task
    for key, zone in [("client-one", "Pacific/Honolulu"), ("client-two", "Asia/Tokyo")]:
        result = client.post(
            "/api/collections/run",
            json={
                "type": "article_interpretation",
                "round_key": key,
                "timezone": zone,
            },
            headers={"X-Auth-Token": str(auth["admin_token"])},
        )
        assert result.status_code == 200, result.text
        deadline = time.monotonic() + 10
        while runtime.active_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not runtime.active_tasks
    rows = storage._conn.execute(
        "SELECT round_key,receipt_json FROM article_interpretation_rounds"
    ).fetchall()
    assert len(rows) == 1 and len(generator.calls) == 3
    assert (
        rows[0][0]
        == datetime.now(timezone.utc)
        .astimezone(articles.ZoneInfo("Asia/Shanghai"))
        .date()
        .isoformat()
    )
    assert rows[0][1]["timezone"] == "Asia/Shanghai" and rows[0][1]["provider_calls"] == 3


def test_completed_round_generation_retry_cannot_reopen_generation_budget(storage):
    seed(storage, "a")
    generator = Generator(error=TimeoutError("fixture transport"))
    runner = service(storage, generator=generator)
    first = runner.run(round_key="completed-origin")
    assert first["status"] == "complete" and first["provider_calls"] == 1
    identity = first["slots"][0]["interpretation_id"]
    generator.error = None
    retried = runner.run(retry_id=identity)["interpretation"]
    origin = runner._origin_receipt(runner._content_budget(retried["content_key"]))
    assert retried["error"] == "budget_exhausted" and len(generator.calls) == 1
    assert origin["status"] == "complete" and origin["provider_calls"] == 1
    assert origin["slots"] == first["slots"]  # Historical selection/cursor is not reopened.
    assert origin["generation_retries"][-1]["status"] == "failed"
    assert len(retried["attempts"]) == 1 and len(retried["attempts"][0]["calls"]) == 1


def test_partial_provider_seconds_limit_lowers_retry_timeout(storage):
    seed(storage, "a")
    stopped = [False]
    clock = [0.0]
    generator = Generator(output="invalid", on_call=lambda: stopped.__setitem__(0, True))
    runner = service(
        storage, generator=generator, stop_check=lambda: stopped[0], clock=lambda: clock[0]
    )
    first = runner.run(round_key="seconds-origin")
    identity = first["slots"][0]["interpretation_id"]
    draft = runner._get(identity)
    draft["attempts"][0]["provider_seconds"] = 179
    runner._save(draft)
    stopped[0] = False
    generator.on_call = lambda: clock.__setitem__(0, clock[0] + 1)
    runner.run(retry_id=identity)
    assert len(generator.calls) == 2 and generator.calls[-1]["timeout_seconds"] == pytest.approx(
        1, abs=0.05
    )
    assert runner._content_budget(draft["content_key"])["provider_seconds"] == 180
    runner.run(retry_id=identity)
    assert len(generator.calls) == 2


def test_generation_deadline_includes_output_validation(storage, monkeypatch):
    seed(storage, "a")
    clock = [0.0]
    validator = articles.validate_output

    def delayed(*args):
        result = validator(*args)
        clock[0] = 241
        return result

    monkeypatch.setattr(articles, "validate_output", delayed)
    generator, resolver = Generator(), Resolver()
    runner = service(storage, generator=generator, resolver=resolver, clock=lambda: clock[0])
    result = runner.run(round_key="parse-deadline")
    draft = runner._get(result["slots"][0]["interpretation_id"])
    assert draft["error"] == "timeout" and not draft["body_markdown_zh"]
    assert len(generator.calls) == 1 and not resolver.calls


def test_late_link_only_deadline_does_not_touch_origin_or_provider(storage):
    seed(storage, "a")
    clock = [0.0]
    runner = service(storage, resolver=Resolver(fail=True), clock=lambda: clock[0])
    first = runner.run(round_key="bounded-link-origin")
    identity = first["slots"][0]["interpretation_id"]
    before = runner._get(identity)

    class SlowResolver(Resolver):
        def resolve(self, identity, *, timeout_seconds):
            assert timeout_seconds <= 5
            clock[0] += 241
            return super().resolve(identity, timeout_seconds=timeout_seconds)

    runner.resolver = SlowResolver()
    result = runner.run(retry_id=identity)
    assert result["retry_receipt"]["status"] == "failed"
    assert result["interpretation"]["status"] == "failed"
    assert result["interpretation"]["attempts"] == before["attempts"]
    assert result["retry_receipt"]["provider_calls"] == 0
    assert runner._origin_receipt(runner._content_budget(before["content_key"])) == first


@pytest.mark.parametrize("limit", ["calls", "provider_seconds", "selection_deadline"])
def test_article_local_budget_failure_does_not_starve_following_sources(
    storage, monkeypatch, limit
):
    for key in "abc":
        seed(storage, key)
    generator = Generator()
    runner = service(storage, generator=generator)
    prepare = runner._prepare

    def limited(*args):
        draft, runtime = prepare(*args)
        if draft["source_key"] == "a":
            if limit == "selection_deadline":
                draft["selection_started_at"] = "2000-01-01T00:00:00+00:00"
            else:
                draft["attempts"] = [
                    {
                        "started_at": draft["selection_started_at"],
                        "calls": [{"status": "failed"}] * (2 if limit == "calls" else 1),
                        "provider_seconds": 180 if limit == "provider_seconds" else 1,
                    }
                ]
            runner._save(draft)
        return draft, runtime

    monkeypatch.setattr(runner, "_prepare", limited)
    result = runner.run(round_key="local-" + limit)
    assert result["status"] == "complete"
    assert [slot["status"] for slot in result["slots"]] == ["failed", "ready", "ready"]
    assert len(generator.calls) == 2 and result["provider_calls"] == 2
    assert all(slot["advanced"] for slot in result["slots"])


@pytest.mark.parametrize("limit", ["round_calls", "round_seconds"])
def test_round_budget_exhaustion_starts_no_following_slot(storage, limit):
    seed(storage, "a")
    runner = service(storage)
    receipt = {
        "round_key": "global-" + limit,
        "status": "stopped",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": 900 if limit == "round_seconds" else 0,
        "provider_calls": 6 if limit == "round_calls" else 0,
        "slots": [{"source_key": key, "status": "queued", "decisions": []} for key in "abc"],
    }
    storage._conn.execute(
        "INSERT INTO article_interpretation_rounds(round_key,receipt_json) VALUES (?,?::jsonb)",
        (receipt["round_key"], articles._json(receipt)),
    )
    result = runner.run(round_key="unused")
    assert result["status"] == "budget_exhausted" and not runner.generator.calls
    assert all(slot["status"] == "queued" for slot in result["slots"])


def test_genuine_new_content_version_gets_its_own_budget(storage):
    url = seed(storage, "a")
    generator = Generator(output="invalid")
    runner = service(storage, generator=generator)
    first = runner.run(round_key="old-content")
    old = runner._get(first["slots"][0]["interpretation_id"])
    body = source_body("genuinely revised")
    digest = articles._hash(body)
    storage._conn.execute("UPDATE files SET sha256=? WHERE url=?", (digest, url))
    storage._conn.execute(
        "UPDATE catalog_items SET sha256=?,markdown_content=? WHERE file_url=?", (digest, body, url)
    )
    row, audit = runner._select("a")
    new, _ = runner._prepare(row, "a", audit[-1]["reason"])
    assert new["content_key"] != old["content_key"] and new["origin_round_key"] is None
    generator.output = None
    result = runner._generate(new, round_deadline=runner.clock() + 900)
    assert result["status"] == "ready" and len(generator.calls) == 3
    assert runner._content_budget(old["content_key"])["calls"] == 2
    assert runner._content_budget(new["content_key"])["calls"] == 1


def test_new_fingerprint_cannot_reopen_completed_origin_round(storage, monkeypatch):
    seed(storage, "a")
    generator = Generator(error=TimeoutError("first call failed"))
    runner = service(storage, generator=generator)
    old_round = runner.run(round_key="previous-recipe")
    old = runner._get(old_round["slots"][0]["interpretation_id"])
    assert old_round["provider_calls"] == 1
    monkeypatch.setattr(articles, "PROMPT_VERSION", "article-interpretation-changed-recipe")
    storage._conn.execute("UPDATE article_interpretation_state SET last_source_key='g'")
    generator.error = None
    current = runner.run(round_key="current-recipe")
    assert current["slots"][0]["status"] == "skipped"
    assert current["slots"][0]["decisions"][0]["reason"] == "content_origin_round_closed"
    new, _ = runner._prepare(
        articles._load_file(storage._conn, old["file_url"]), "a", "manual fixture"
    )
    new = runner._generate(new, round_deadline=runner.clock() + 900)
    assert new["input_fingerprint"] != old["input_fingerprint"]
    assert new["selection_started_at"] == old["selection_started_at"]
    assert new["origin_round_key"] == "previous-recipe"
    assert new["error"] == "budget_exhausted" and len(generator.calls) == 1
    assert current["status"] == "complete" and current["provider_calls"] == 0
    assert current["slots"][0]["advanced"]
    assert runner._origin_receipt(runner._content_budget(new["content_key"]))["provider_calls"] == 1
    assert runner.run(round_key="current-recipe")["provider_calls"] == 0


def test_citation_section_author_dot_year_is_supported_as_year_only_in_context():
    citation = "CAS. 2026. *The CAS AI Primer*. 2nd ed."
    supported = articles._quantities(citation, source_section="Recommended Citation:")
    assert articles._quantities("2026年第2版", strict=True).issubset(supported)
    assert not articles._quantities("2025年第2版", strict=True).issubset(supported)
    assert ("year", articles.Decimal(2026)) not in articles._quantities(citation)
    assert ("year", articles.Decimal(2026)) not in articles._quantities(
        citation, source_section="Study of citation counts"
    )


@pytest.mark.parametrize(
    "text,section",
    [
        ("The model processed 2026 claims.", "Recommended Citation:"),
        ("CAS. 2026 cases. A study.", "References"),
        ("CAS. 2026. A study.", "Results"),
        ("CAS. 2,026. A study.", "Recommended Citation:"),
        ("CAS. 2026.5. A study.", "Recommended Citation:"),
    ],
)
def test_citation_year_does_not_reclassify_counts_units_or_ambiguous_numbers(text, section):
    assert ("year", articles.Decimal(2026)) not in articles._quantities(
        text, source_section=section
    )


@pytest.mark.parametrize("year,accepted", [(2026, True), (2025, False)])
def test_output_citation_year_support_and_wrong_year_rejection(year, accepted):
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    messages, coverage = articles.build_input(row, {}, {})
    citation = coverage["evidence"][0]
    citation.update(
        quote="CAS. 2026. *The CAS AI Primer*. 2nd ed.", section="Recommended Citation:"
    )
    value = json.loads(response(messages))
    value["sections"][0]["paragraphs"][0]["text"] = f"该文的推荐引用注明{year}年第2版。"
    if accepted:
        assert articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)["claims"]
    else:
        with pytest.raises(ValueError, match="unsupported_number"):
            articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)


def test_citation_label_does_not_promote_other_evidence_four_digit_counts_to_years():
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    messages, coverage = articles.build_input(row, {}, {})
    coverage["evidence"][0].update(quote="CAS. 2026. *A study*.", section="Recommended Citation:")
    coverage["evidence"][1].update(quote="Claims. 2025. Observations.", section="Results")
    value = json.loads(response(messages))
    value["sections"][0]["paragraphs"][0].update(
        text="原文是在2025年发布。",
        evidence_ids=[coverage["evidence"][0]["id"], coverage["evidence"][1]["id"]],
    )
    with pytest.raises(ValueError, match="unsupported_number"):
        articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)


def test_prompt_v7_allows_source_supported_numerals_and_explicit_authors(monkeypatch):
    assert articles.PROMPT_VERSION == "article-interpretation-v7-authors"
    assert "精确数字优先使用Arabic digits" in articles.PROMPT
    assert "不得编成精确金额" in articles.PROMPT
    assert "author_metadata" in articles.PROMPT and "不能补充、删减或从正文推测" in articles.PROMPT
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    current_messages, current_coverage = articles.build_input(row, {}, {})
    with monkeypatch.context() as prior:
        prior.setattr(articles, "PROMPT_VERSION", "article-interpretation-v5")
        prior.setattr(articles, "PROMPT", "所有数值都用Arabic digits。")
        old_messages, old_coverage = articles.build_input(row, {}, {})
    assert current_coverage["prompt_version"] == "article-interpretation-v7-authors"
    assert old_coverage["prompt_version"] == "article-interpretation-v5"
    assert articles._hash(
        articles._json({"messages": current_messages, "coverage": current_coverage})
    ) != articles._hash(articles._json({"messages": old_messages, "coverage": old_coverage}))


def test_v7_prompt_version_is_persisted_in_draft_and_slot_receipt(storage):
    seed(storage, "a")
    runner = service(storage)
    receipt = runner.run(round_key="v7-recipe-fixture")
    slot = receipt["slots"][0]
    draft = runner._get(slot["interpretation_id"])
    assert (
        slot["prompt_version"]
        == draft["prompt_version"]
        == draft["coverage"]["prompt_version"]
        == "article-interpretation-v7-authors"
    )
    assert slot["input_fingerprint"] == draft["input_fingerprint"]
    assert receipt["provider_calls"] == 1


@pytest.mark.parametrize(
    "text,error",
    [
        ("原文提出四个层级。", None),
        ("原文提出5个层级。", "unsupported_number"),
        ("原文提出4个层级。", None),
    ],
)
def test_english_four_levels_supports_equivalent_chinese_and_exact_arabic_counts(text, error):
    row = {"url": "https://a.example/x", "sha256": "a" * 64, "markdown_content": source_body()}
    messages, coverage = articles.build_input(row, {}, {})
    coverage["evidence"][0]["quote"] = "The approach describes four levels."
    value = json.loads(response(messages))
    value["sections"][0]["paragraphs"][0]["text"] = text
    if error:
        with pytest.raises(ValueError, match=error):
            articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)
    else:
        assert articles.validate_output(json.dumps(value, ensure_ascii=False), coverage)["claims"]


@pytest.mark.parametrize(
    "target,source",
    [
        ("数十亿美元", "billions of dollars worldwide each year"),
        ("两种", "There are two main flavors"),
        ("第一步", "an important first step"),
        ("第1步", "the first step"),
        ("4种", "four different binning methods"),
        ("1维", "one-dimensional decision boundary"),
        ("4个", "four different datasets"),
        ("5个", "five financial ratios"),
        ("四个", "four levels"),
        ("十二个月", "12 months"),
        ("百分之二点五", "2.5%"),
        ("二点五亿美元", "250 million USD"),
        ("19个", "19 variables"),
        ("第1层", "Level 1: vendor products"),
    ],
)
def test_source_supported_chinese_numerals_and_english_words(target, source):
    claim = articles._quantities(target, strict=True)
    assert claim and claim.issubset(articles._quantities(source))


@pytest.mark.parametrize(
    "target,source",
    [
        ("三种", "two main flavors"),
        ("第二步", "an important first step"),
        ("第一年", "an important first step"),
        ("第一步", "one available model"),
        ("只有一个模型", "The model is useful."),
        ("数十亿欧元", "billions of dollars"),
        ("数十亿美元", "hundreds of billions of dollars"),
        ("数十亿美元", "tens of billions of dollars"),
        ("数亿元", "billions of dollars"),
        ("数百万美元", "billions of dollars"),
        ("数百亿美元", "billions of dollars"),
        ("十亿美元", "billions of dollars"),
        ("二十亿美元", "billions of dollars"),
        ("10 billion USD", "billions of dollars"),
        ("三种", "no numeric evidence"),
        ("十三种", "thirteen flavors"),
        ("两个月", "two years"),
        ("百分之二点五", "2.6%"),
        ("二点五亿欧元", "250 million USD"),
    ],
)
def test_source_supported_numerals_reject_wrong_value_unit_scale_and_precision(target, source):
    claim = articles._quantities(target, strict=True)
    assert claim and not claim.issubset(articles._quantities(source))


def test_indefinite_one_does_not_invent_numeric_claim_but_explicit_one_does():
    assert articles._quantities("原文的一个核心立场是部分依赖机器学习。", strict=True) == set()
    assert articles._quantities("只有一个模型", strict=True) == {("number", articles.Decimal(1))}
    assert articles._quantities("唯一一个模型", strict=True) == {("number", articles.Decimal(1))}


@pytest.mark.parametrize("text", ["二三种", "一百二种", "数万亿美元"])
def test_unrecognized_or_ambiguous_chinese_quantity_shapes_fail_closed(text):
    with pytest.raises(ValueError, match="unsupported_number_format"):
        articles._quantities(text, strict=True)


def test_vague_billion_support_never_contains_an_exact_money_point():
    supported = articles._quantities("billions of dollars")
    assert supported == {("USD:scale", "billion")}
    assert articles._quantities("数十亿美元", strict=True) == supported


@pytest.mark.parametrize(
    "text", ["thirteen flavors", "trillions of dollars", "one hundred cases", "one million USD"]
)
def test_unknown_english_numeric_claim_shapes_fail_closed(text):
    with pytest.raises(ValueError, match="unsupported_number_format"):
        articles._quantities(text, strict=True)
    assert ("number", articles.Decimal(1)) not in articles._quantities(text)


def test_chinese_vague_currency_codes_preserve_currency_dimension():
    assert articles._quantities("数十亿USD", strict=True) == articles._quantities(
        "billions of dollars"
    )
    assert not articles._quantities("数十亿EUR", strict=True).issubset(
        articles._quantities("billions of dollars")
    )


@pytest.mark.parametrize(
    "limit", ["calls", "provider_seconds", "selection_deadline", "origin_closed"]
)
def test_exhausted_candidate_advances_to_next_article_without_new_budget(storage, limit):
    first_url = seed(storage, "a", url="https://a.example/a1.pdf", body=source_body("first"))
    second_url = seed(storage, "a", url="https://a.example/a2.pdf", body=source_body("second"))
    generator = Generator()
    runner = service(storage, generator=generator)
    first, _ = runner._prepare(articles._load_file(storage._conn, first_url), "a", "fixture")
    if limit in {"calls", "provider_seconds"}:
        first["attempts"] = [
            {
                "started_at": first["selection_started_at"],
                "calls": [{"status": "failed"}, {"status": "failed"}],
                "provider_seconds": 180 if limit == "provider_seconds" else 10,
            }
        ]
    elif limit == "selection_deadline":
        first["selection_started_at"] = "2000-01-01T00:00:00+00:00"
    else:
        first["origin_round_key"] = "finished-origin"
        receipt = {
            "round_key": "finished-origin",
            "status": "complete",
            "provider_calls": 0,
            "elapsed_seconds": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "slots": [],
        }
        storage._conn.execute(
            "INSERT INTO article_interpretation_rounds(round_key,receipt_json) VALUES (?,?::jsonb)",
            (receipt["round_key"], articles._json(receipt)),
        )
    first.update(status="failed", error="fixture_failure")
    runner._save(first)
    before = runner._content_budget(first["content_key"])
    # A Registry/prompt-input change cannot make this consumed content selectable again.
    storage._conn.execute(
        "UPDATE canonical_sources SET name_zh='更新的规范来源名' WHERE source_key='a'"
    )
    selected, decisions = runner._select("a")
    print(
        json.dumps(
            {
                "limit": limit,
                "selected_url": selected["url"] if selected else None,
                "expected_url": second_url,
                "prior_budget": before,
                "provider_calls": len(generator.calls),
                "decisions": decisions,
            },
            ensure_ascii=False,
        )
    )
    assert selected["url"] == second_url
    assert decisions[0]["selected"] is False
    assert decisions[0]["reason"].startswith("content_")
    assert runner._content_budget(first["content_key"]) == before
    retried, _ = runner._prepare(articles._load_file(storage._conn, first_url), "a", "fixture")
    assert retried["input_fingerprint"] != first["input_fingerprint"]
    result = runner._generate(retried, round_deadline=runner.clock() + 900)
    assert result["error"] == "budget_exhausted" and not generator.calls
    after = runner._content_budget(first["content_key"])
    for field in ("calls", "provider_seconds", "selection_started_at", "origin_round_key"):
        assert after[field] == before[field]

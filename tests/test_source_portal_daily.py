from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from functools import partial

import psycopg2
import pytest

import ai_actuarial.content_hub as hub
import ai_actuarial.local_collection_runtime as runtime
from ai_actuarial.source_portal_daily import daily_description, validate_daily_evidence
from ai_actuarial.source_portals import SOURCE_PORTALS_BY_KEY, source_portal_for_observation
from tests.postgres_helpers import uninitialized_postgres_url_for_path


def _evidence(*, day="2026-11-02", hour=12, site="cia-ica", sha="a", url=None):
    captured_at = f"{day}T{hour:02}:00:00-05:00"
    return {
        "schema_version": 1,
        "portal_key": "cia-publications",
        "site_id": site,
        "run_id": hashlib.sha256(f"{site}|{captured_at}|{sha}".encode()).hexdigest(),
        "captured_at": captured_at,
        "acquired_on": day,
        "observations": [
            {
                "url": url or "https://www.cia-ica.ca/report.pdf",
                "raw_sha256": sha * 64,
                "kind": "file",
                "title": "AI mortality study",
                "source_page_url": "https://www.cia-ica.ca/publications",
            }
        ],
        "hub_results": [],
        "limits": {
            "request_count": 30,
            "request_limit": 30,
            "budget_exhausted": True,
            "frontier_remaining": 100,
            "source_error_count": 0,
            "finished": True,
        },
    }


def _database(tmp_path, name):
    url = uninitialized_postgres_url_for_path(tmp_path / name)
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = cursor.fetchone()[0]
    hub.apply_content_hub_schema(url, schema=schema)
    return url, schema


def test_collect_sites_have_cards_and_soa_topic_provenance_is_exact():
    for site in runtime.SITES.values():
        key = source_portal_for_observation(site.site_id, site.seeds[0] if site.seeds else "")
        assert (key is not None) == (site.action == "collect")
    general = "https://www.soa.org/research/general-mortality-study.pdf"
    ai = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"].url
    assert source_portal_for_observation("soa", general) == "soa-research-topics"
    assert source_portal_for_observation("soa", general, ai) == "soa-artificial-intelligence"
    assert source_portal_for_observation("soa", ai + "unrelated") == "soa-artificial-intelligence"
    assert (
        source_portal_for_observation("soa-ai-bulletin-focused", general)
        == "soa-artificial-intelligence"
    )


def test_daily_description_distinguishes_observation_change_import_and_backlog():
    previous = _evidence(day="2026-11-01")
    current = _evidence(sha="b")
    observed = current["observations"][0]
    current["hub_results"] = [
        {
            **{key: observed[key] for key in ("url", "raw_sha256", "source_page_url")},
            "content_version_id": "1",
            "status": "new",
        },
        {
            "url": "https://www.cia-ica.ca/older.pdf",
            "raw_sha256": "c" * 64,
            "source_page_url": "",
            "content_version_id": "2",
            "status": "new",
        },
    ]
    zh, en = daily_description([current, copy.deepcopy(current)], [previous])
    assert "网址0个" in zh and "1个网址的原始响应内容有变化" in zh
    assert "本日读到的内容1份、历史积压1份" in zh
    assert "first imports: 1 observed today and 1 from historical backlog" in en
    assert "AI mortality study" in zh and "AI mortality study" in en
    assert "不代表原站今日发布" in zh and "not a full-site scan" in en
    assert "预算用完" in zh and "request budget was exhausted" in en
    assert len(zh) <= 2000 and len(en) <= 2000
    # Reverting to an older known hash still differs from the last observed version.
    reverting = _evidence(sha="a", day="2026-11-03")
    assert "1个网址的原始响应内容有变化" in daily_description([reverting], [previous, current])[0]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e["observations"].clear(),
        lambda e: e.update(portal_key="soa-artificial-intelligence"),
        lambda e: e.update(acquired_on="2026-11-01"),
        lambda e: e["observations"][0].update(raw_sha256="bad"),
        lambda e: e["observations"].append(copy.deepcopy(e["observations"][0])),
        lambda e: e["limits"].update(request_count=31),
        lambda e: e["limits"].update(request_limit=60),
        lambda e: e["observations"][0].update(request_scope="not-a-scope-hash"),
    ],
)
def test_daily_evidence_rejects_empty_misattributed_or_unbounded_data(mutation):
    evidence = _evidence()
    mutation(evidence)
    with pytest.raises(ValueError):
        validate_daily_evidence(evidence)


@pytest.mark.parametrize(
    "site_id,kind,dimensions",
    [
        (
            "caa",
            "caa_shared",
            [
                {"parent_id": "research", "page": 1},
                {"parent_id": "research", "page": 2},
                {"parent_id": "standards", "page": 1},
            ],
        ),
        (
            "australia",
            "algolia",
            [
                {"content_type": "research", "page": 0},
                {"content_type": "research", "page": 1},
                {"content_type": "policy", "page": 0},
            ],
        ),
    ],
)
@pytest.mark.parametrize("same_response", [False, True])
def test_post_page_observations_keep_request_scopes_and_compare_only_matching_requests(
    tmp_path, monkeypatch, site_id, kind, dimensions, same_response
):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    endpoint = (
        "https://www.e-caa.org.cn/informationSharing/more"
        if site_id == "caa"
        else "https://www.actuaries.asn.au/fixture-search/query"
    )
    frontier = [{"url": endpoint, "kind": kind, **dimension} for dimension in dimensions]

    class PostCrawler(_Crawler):
        algolia_key = "fixture-public-search-key"

        def _request_post(self, url, form, _headers, **_kwargs):
            self.site_attempts += 1
            marker = "same response" if same_response else hashlib.sha256(form).hexdigest()
            return (
                json.dumps({"rows": [], "hits": [], "nbPages": 1, "marker": marker}).encode(),
                {"content-type": "application/json"},
                url,
            )

    state = {"articles": {}}
    captured = runtime._capture(
        runtime.SITES[site_id],
        state,
        PostCrawler(page=b"<main>Session bootstrap</main>"),
        tmp_path,
        {},
        request_limit=5,
        initial_frontier=frontier,
    )
    assert not captured["errors"]
    [run] = state["source_portal_daily_runs"].values()
    post_observations = [
        item for item in run["observations"] if item["url"] == runtime._canonical_url(endpoint)
    ]
    assert len(post_observations) == 3
    assert {item["request_scope"] for item in post_observations} == {
        hashlib.sha256(
            runtime._queue_identity({**item, "url": runtime._canonical_url(endpoint)}).encode()
        ).hexdigest()
        for item in frontier
    }
    assert len({item["raw_sha256"] for item in post_observations}) == (1 if same_response else 3)
    evidence = {
        "schema_version": 1,
        "portal_key": source_portal_for_observation(site_id, endpoint),
        **run,
    }
    for item in evidence["observations"]:
        item.pop("artifact_path")
    validate_daily_evidence(evidence)
    pages = 4 if site_id == "caa" else 3
    unique_urls = 2 if site_id == "caa" else 1
    zh, en = daily_description([evidence], [])
    assert f"{pages} page/API responses" in en
    assert f"{unique_urls} URLs were first recorded" in en
    assert "0个网址的原始响应内容有变化" in zh and "differed at 0 URLs" in en
    assert "differed at 0 URLs" in daily_description([evidence], [evidence])[1]
    post_index = next(
        index
        for index, item in enumerate(evidence["observations"])
        if item["url"] == runtime._canonical_url(endpoint)
    )
    # Another request scope is not another new URL, nor a comparable content change.
    other_scope = copy.deepcopy(evidence)
    other_scope["observations"][post_index]["request_scope"] = "e" * 64
    other_scope["observations"][post_index]["raw_sha256"] = "f" * 64
    assert "0 URLs were first recorded" in daily_description([other_scope], [evidence])[1]
    assert "differed at 0 URLs" in daily_description([other_scope], [evidence])[1]
    # Re-reading one existing request scope with different bytes is a verified change.
    changed = copy.deepcopy(evidence)
    changed["observations"][post_index]["raw_sha256"] = "f" * 64
    assert "differed at 1 URLs" in daily_description([changed], [evidence])[1]
    assert "differed at 1 URLs" in daily_description([evidence, changed], [])[1]


def test_legacy_page_evidence_retains_hash_and_url_history_without_comparing_unknown_scopes(
    tmp_path,
):
    url, schema = _database(tmp_path, "daily-legacy-request-scope")
    legacy = _evidence(day="2026-11-01", url="https://www.cia-ica.ca/api/pages")
    legacy["observations"][0]["kind"] = "page"
    digest = validate_daily_evidence(legacy)[2]
    record = partial(hub.content_hub_record_source_portal_daily, database_url=url, schema=schema)
    old = record(legacy)
    current = _evidence(url=legacy["observations"][0]["url"], sha="b")
    current["observations"][0].update(kind="page", request_scope="c" * 64)
    projected = record(current)
    assert "0 URLs were first recorded" in projected["description_en"]
    assert "differed at 0 URLs" in projected["description_en"]
    legacy_multiple = copy.deepcopy(legacy)
    legacy_multiple["observations"].append(
        {**legacy_multiple["observations"][0], "raw_sha256": "d" * 64}
    )
    assert "differed at 0 URLs" in daily_description([legacy_multiple], [])[1]
    saved = hub.content_hub_read_source_portal_capture(
        portal_key=legacy["portal_key"],
        capture_id=old["capture_id"],
        database_url=url,
        schema=schema,
    )
    assert saved["evidence_sha256"] == digest == validate_daily_evidence(legacy)[2]
    assert record(legacy)["duplicate"] is True
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT evidence_json FROM source_portal_captures WHERE capture_id = %s",
                (old["capture_id"],),
            )
            assert "request_scope" not in cursor.fetchone()[0]["observations"][0]


def test_hub_same_day_union_replay_conflict_and_separate_directory_scope(tmp_path):
    url, schema = _database(tmp_path, "daily-union")
    record_daily = partial(
        hub.content_hub_record_source_portal_daily, database_url=url, schema=schema
    )
    first = _evidence()
    one = record_daily(first)
    later = _evidence(hour=14, site="cia-research-publications", sha="b")
    two = record_daily(later)
    assert two["capture_id"] > one["capture_id"]
    assert "2 files" in two["description_en"]
    assert "1 URLs were first recorded" in two["description_en"]
    assert "1 URLs" in two["description_en"] and "content differed at 1" in two["description_en"]
    replay = record_daily(first)
    assert replay["duplicate"] is True and replay["capture_id"] == two["capture_id"]
    conflicting = copy.deepcopy(first)
    conflicting["limits"]["source_error_count"] = 1
    with pytest.raises(hub.ContentHubError, match="immutable daily evidence"):
        record_daily(conflicting)
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    hub.content_hub_record_source_portal_capture(
        portal_key=portal.portal_key,
        page_url=portal.url,
        scope_key=portal.scope_key,
        captured_at="2026-11-01T12:00:00-05:00",
        acquired_on="2026-11-01",
        page_sha256="e" * 64,
        entries=[
            {"url": "https://www.cia-ica.ca/old-directory-entry", "title": "Old directory study"}
        ],
        complete=True,
        intro_zh=portal.overview_zh,
        intro_en=portal.overview_en,
        database_url=url,
        schema=schema,
    )
    directory = hub.content_hub_record_source_portal_capture(
        portal_key=portal.portal_key,
        page_url=portal.url,
        scope_key=portal.scope_key,
        captured_at="2026-11-02T15:00:00-05:00",
        acquired_on="2026-11-02",
        page_sha256="d" * 64,
        entries=[{"url": "https://www.cia-ica.ca/directory-entry", "title": "Directory study"}],
        complete=True,
        intro_zh=portal.overview_zh,
        intro_en=portal.overview_en,
        database_url=url,
        schema=schema,
    )
    assert directory["superseded_by_daily"] is True
    assert "Directory study" in directory["description_en"]
    earlier_arrival = _evidence(hour=11, url="https://www.cia-ica.ca/other.pdf")
    three = record_daily(earlier_arrival)
    assert "3 files" in three["description_en"]
    assert "Complete directory snapshot" in three["description_en"]
    assert "Directory study" in three["description_en"]
    assert three["description_en"].startswith("Complete directory snapshot")
    assert "no longer lists “Old directory study”" in three["description_en"]
    assert three["captured_at"] == directory["captured_at"]
    assert three["capture_id"] > directory["capture_id"]
    read = hub.content_hub_read_source_portal_capture(
        portal_key=portal.portal_key,
        capture_id=three["capture_id"],
        database_url=url,
        schema=schema,
    )
    assert read["capture_kind"] == "daily_collection" and read["complete"] is False
    assert read["evidence_sha256"] == validate_daily_evidence(earlier_arrival)[2]
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM source_portal_captures")
            assert cursor.fetchone()[0] == 5
            cursor.execute(
                "UPDATE source_portal_captures SET evidence_sha256 = %s WHERE capture_id = %s",
                ("f" * 64, three["capture_id"]),
            )
    with pytest.raises(hub.ContentHubError, match="SHA verification"):
        hub.content_hub_read_source_portal_capture(
            portal_key=portal.portal_key,
            capture_id=three["capture_id"],
            database_url=url,
            schema=schema,
        )


class _Crawler:
    def __init__(self, *, fail=False, page=None):
        self.fail, self.page = fail, page
        self.site_attempts = 0

    def begin_site(self, budget):
        self.site_budget = budget

    def _request(self, url, **_kwargs):
        self.site_attempts += 1
        if self.fail:
            raise OSError("fixture source unavailable")
        return self.page, {"content-type": "text/html"}, url

    def _download_file(self, url, root, **_kwargs):
        self.site_attempts += 1
        if self.fail:
            raise OSError("fixture source unavailable")
        body = b"%PDF-1.4 verified test file"
        root.mkdir(parents=True, exist_ok=True)
        path = root / "test.pdf"
        path.write_bytes(body)
        return (
            path,
            {"content-type": "application/pdf"},
            url,
            hashlib.sha256(body).hexdigest(),
            len(body),
        )


def _processed():
    return {
        "candidate_count": 0,
        "pending_article_count": 0,
        "new_versions": 0,
        "duplicates": 0,
        "enriched": 0,
        "ai_candidates": 0,
        "article_errors": [],
        "target": {
            name: {"acknowledged": 0, "pending": 0, "failed": 0, "ready_status": "succeeded"}
            for name in ("china", "overseas")
        },
    }


def _patch_hub(monkeypatch, url, schema):
    for name in (
        "content_hub_record_source_portal_daily",
        "content_hub_record_source_portal_capture",
        "content_hub_read_source_portal_capture",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))


def test_runtime_file_only_partial_attempt_records_hub_before_digest_and_retries_failed_target(
    tmp_path, monkeypatch
):
    url, schema = _database(tmp_path, "daily-runtime")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(runtime, "_new_crawler", lambda _root: _Crawler())
    queue = [
        {
            "url": f"https://www.cia-ica.ca/report-{n}.pdf",
            "kind": "document",
            "title": f"Mortality study {n}",
            "referrer": "https://www.cia-ica.ca/publications",
        }
        for n in range(2)
    ]
    state = {"sites": {"cia-ica": {"queue": queue, "cursor": 0}}, "articles": {}}
    config = {
        "data_root": str(tmp_path / "data"),
        "state_root": str(tmp_path),
        "targets": {target: {"host": target} for target in ("china", "overseas")},
    }
    (tmp_path / "data").mkdir()
    captured = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        _Crawler(),
        tmp_path / "data",
        state["sites"]["cia-ica"],
        request_limit=1,
    )
    assert captured["budget_exhausted"] and len(captured["downloads"]) == 1, captured
    assert not captured["portal_captures"]
    monkeypatch.setattr(runtime, "_capture", lambda *_args, **_kwargs: captured)

    def process(site_id, state, *_args, **_kwargs):
        [article] = list(state["articles"].values())
        runtime._record_daily_hub_result(state, site_id, article, True, {"content_version_id": 7})
        runtime._record_daily_hub_result(
            state,
            site_id,
            {"url": "https://www.cia-ica.ca/historical.pdf", "raw_sha256": "c" * 64},
            True,
            {"content_version_id": 8},
        )
        return _processed()

    monkeypatch.setattr(runtime, "_process_articles", process)
    sent = []

    def stream(_config, target, updates):
        sent.append((target, copy.deepcopy(updates)))
        if target == "overseas" and len(sent) == 2:
            raise OSError("fixture target unavailable")
        return {"failures": []}

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    date_text = dt.datetime.now(runtime.TIME_ZONE).date().isoformat()
    receipt = runtime._run_site(
        "cia-ica",
        date_text,
        config,
        state,
        url,
        request_limit=1,
    )
    [update] = sent[0][1]
    assert (
        "Hub first imports: 1 observed today and 1 from historical backlog"
        in update["description_en"]
    )
    assert "Mortality study" in update["description_en"]
    assert any(
        "cia-publications" in item and "digest_count=1" in item and "overseas=pending" in item
        for item in receipt["evidence"]
    )
    assert not state["source_portal_daily_runs"]
    assert state["pending_source_portal_publications"]
    retry = runtime._sync_source_portals(state, config, url)
    assert retry["status"] == "succeeded"
    assert [target for target, _updates in sent] == ["china", "overseas", "overseas"]
    assert sent[-1][1][0]["capture_id"] == update["capture_id"]
    assert not state["pending_source_portal_publications"]
    runtime._sync_source_portals(state, config, url)
    assert len(sent) == 3


def test_partial_page_without_directory_entries_still_has_daily_digest(tmp_path, monkeypatch):
    url, schema = _database(tmp_path, "daily-page")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    crawler = _Crawler(page=b"<main><h1>Public materials</h1></main>")
    state = {"articles": {}}
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    captured = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        crawler,
        tmp_path,
        {},
        request_limit=1,
        initial_frontier=[{"url": portal.url, "kind": "page"}],
    )
    assert not captured["downloads"] and captured["portal_captures"][0]["complete"] is False
    sent = []
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, _target, updates: sent.extend(updates) or {"failures": []},
    )
    runtime._sync_source_portals(
        state, {"targets": {target: {"host": target} for target in ("china", "overseas")}}, url
    )
    assert len(sent) == 2
    assert "1 page/API responses and 0 files" in sent[0]["description_en"]
    assert "directory no longer" not in sent[0]["description_en"].lower()


def test_later_directory_retry_cannot_replace_a_daily_digest_and_bad_sha_blocks_retry(
    tmp_path, monkeypatch
):
    url, schema = _database(tmp_path, "daily-priority")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    evidence = _evidence()
    record = hub.content_hub_record_source_portal_daily(evidence, database_url=url, schema=schema)
    state = {"pending_source_portal_publications": {}}
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], evidence["portal_key"], record
    )
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    raw = b"verified directory page"
    artifact = tmp_path / "directory.html"
    artifact.write_bytes(raw)
    state["pending_source_portal_captures"] = [
        {
            "portal_key": portal.portal_key,
            "page_url": portal.url,
            "scope_key": portal.scope_key,
            "captured_at": "2026-11-02T16:00:00-05:00",
            "acquired_on": "2026-11-02",
            "page_sha256": hashlib.sha256(raw).hexdigest(),
            "artifact_path": str(artifact),
            "complete": True,
            "entries": [{"url": "https://www.cia-ica.ca/new.pdf", "title": "Directory-only title"}],
        }
    ]
    sent = []
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, _target, updates: sent.extend(copy.deepcopy(updates)) or {"failures": []},
    )
    config = {"targets": {target: {"host": target} for target in ("china", "overseas")}}
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    assert [item["capture_id"] for item in sent] == [record["capture_id"], record["capture_id"]]
    assert all("Directory-only title" not in item["description_en"] for item in sent)
    runtime._queue_source_portal_update(
        state["pending_source_portal_publications"], evidence["portal_key"], record
    )
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE source_portal_captures SET evidence_sha256 = %s WHERE capture_id = %s",
                ("f" * 64, record["capture_id"]),
            )
    result = runtime._sync_source_portals(state, config, url)
    assert result["status"] == "partial"
    assert "SHA verification" in result["errors"][0]
    assert state["pending_source_portal_publications"]
    assert len(sent) == 2


def test_failed_source_has_no_daily_evidence_or_fake_dynamic(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    state = {"articles": {}}
    captured = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        _Crawler(fail=True),
        tmp_path,
        {},
        request_limit=1,
        initial_frontier=[{"url": "https://www.cia-ica.ca/missing.pdf", "kind": "document"}],
    )
    assert captured["daily_run_id"] is None and captured["errors"]
    assert not state.get("source_portal_daily_runs")


@pytest.mark.parametrize("title", ["Download PDF", "report.pdf"])
def test_generic_download_label_is_not_presented_as_a_meaningful_title(
    tmp_path, monkeypatch, title
):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    state = {"articles": {}}
    runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        _Crawler(),
        tmp_path,
        {},
        request_limit=1,
        initial_frontier=[
            {"url": "https://www.cia-ica.ca/report.pdf", "kind": "document", "title": title}
        ],
    )
    [run] = state["source_portal_daily_runs"].values()
    assert run["observations"][0]["title"] == ""


def test_daily_original_sha_mismatch_keeps_evidence_pending_without_a_digest(tmp_path, monkeypatch):
    evidence = _evidence()
    artifact = tmp_path / "changed.pdf"
    artifact.write_bytes(b"a different original")
    run = {
        key: copy.deepcopy(value)
        for key, value in evidence.items()
        if key not in {"portal_key", "schema_version"}
    }
    run["observations"][0]["artifact_path"] = str(artifact)
    state = {"source_portal_daily_runs": {run["run_id"]: run}}
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(
        runtime,
        "content_hub_record_source_portal_daily",
        lambda *_args, **_kwargs: pytest.fail("unverified bytes must not reach Hub"),
    )
    digests, errors = runtime._persist_daily_source_portals(state, "unused-hub")
    assert not digests and "SHA-256 verification" in errors[0]
    assert state["source_portal_daily_runs"] and not state.get("pending_source_portal_publications")


def test_daily_checkpoint_replays_after_hub_commit_before_publication(tmp_path, monkeypatch):
    url, schema = _database(tmp_path, "daily-crash")
    _patch_hub(monkeypatch, url, schema)
    evidence = _evidence()
    run = {
        key: value for key, value in evidence.items() if key not in {"portal_key", "schema_version"}
    }
    run["evidence"] = [evidence]
    state = {"source_portal_daily_runs": {evidence["run_id"]: run}}
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    record = runtime.content_hub_record_source_portal_daily

    def crash_after_commit(*args, **kwargs):
        record(*args, **kwargs)
        raise OSError("fixture crash after Hub commit")

    monkeypatch.setattr(runtime, "content_hub_record_source_portal_daily", crash_after_commit)
    assert runtime._persist_daily_source_portals(state, url)[1]
    assert state["source_portal_daily_runs"]
    monkeypatch.setattr(runtime, "content_hub_record_source_portal_daily", record)
    digests, errors = runtime._persist_daily_source_portals(state, url)
    assert len(digests) == 1 and not errors
    assert not state["source_portal_daily_runs"]
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM source_portal_captures")
            assert cursor.fetchone()[0] == 1


@pytest.mark.parametrize("already_frozen", [False, True])
def test_cia_two_referrers_deduplicate_before_hub_and_replay_after_commit(
    tmp_path, monkeypatch, already_frozen
):
    url, schema = _database(tmp_path, "daily-cia-two-referrers")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]

    class RedirectCrawler(_Crawler):
        def _request(self, requested_url, **kwargs):
            body, headers, _url = super()._request(requested_url, **kwargs)
            return body, headers, portal.url + "/"

    state = {"articles": {}}
    site_state = {
        "queue": [{"url": portal.url + "/", "kind": "page", "referrer": portal.url + "/"}],
        "cursor": 0,
    }
    captured = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        RedirectCrawler(page=b"<main><h1>Public materials</h1></main>"),
        tmp_path,
        site_state,
        request_limit=2,
        refresh_portal_roots=True,
    )
    assert captured["request_count"] == 2 and not captured["errors"]
    [run] = state["source_portal_daily_runs"].values()
    assert len(run["observations"]) == 2
    assert {item["source_page_url"] for item in run["observations"]} == {
        portal.url,
        portal.url + "/",
    }
    assert (
        len(
            {
                (item["url"], item["raw_sha256"], item["request_scope"])
                for item in run["observations"]
            }
        )
        == 1
    )
    if already_frozen:
        run["evidence"] = [
            {
                "schema_version": 1,
                "portal_key": portal.portal_key,
                **{key: copy.deepcopy(value) for key, value in run.items()},
            }
        ]
        for item in run["evidence"][0]["observations"]:
            item.pop("artifact_path")
        with pytest.raises(ValueError, match="duplicate items"):
            validate_daily_evidence(run["evidence"][0])
    record = runtime.content_hub_record_source_portal_daily

    def crash_after_commit(*args, **kwargs):
        record(*args, **kwargs)
        raise OSError("fixture crash after Hub commit")

    monkeypatch.setattr(runtime, "content_hub_record_source_portal_daily", crash_after_commit)
    digests, errors = runtime._persist_daily_source_portals(state, url)
    assert not digests and "fixture crash after Hub commit" in errors[0]
    [evidence] = run["evidence"]
    assert len(evidence["observations"]) == 1
    frozen_sha = validate_daily_evidence(evidence)[2]
    checkpoint = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(runtime, "content_hub_record_source_portal_daily", record)
    digests, errors = runtime._persist_daily_source_portals(checkpoint, url)
    assert len(digests) == 1 and not errors and not checkpoint["source_portal_daily_runs"]
    assert len(checkpoint["pending_source_portal_publications"]) == 1
    assert runtime._persist_daily_source_portals(checkpoint, url) == ([], [])
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT evidence_json, evidence_sha256 FROM source_portal_captures")
            [row] = cursor.fetchall()
            assert len(row[0]["observations"]) == 1 and row[1].strip() == frozen_sha


def test_daily_deduplication_preserves_separate_portal_attribution(tmp_path, monkeypatch):
    url, schema = _database(tmp_path, "daily-per-portal-deduplication")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    raw = b"one verified report observed through two topic cards"
    artifact = tmp_path / "shared.html"
    artifact.write_bytes(raw)
    run = {
        key: value
        for key, value in _evidence().items()
        if key not in {"schema_version", "portal_key"}
    }
    run.update(site_id="soa", observations=[], hub_results=[])
    for portal_key in ("soa-research-topics", "soa-artificial-intelligence"):
        portal = SOURCE_PORTALS_BY_KEY[portal_key]
        for referrer in (portal.url, portal.url + "?page=2"):
            item = {
                "url": "https://www.soa.org/research/shared-report",
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "source_page_url": referrer,
            }
            run["observations"].append(
                {
                    **item,
                    "kind": "page",
                    "title": "",
                    "request_scope": "a" * 64,
                    "artifact_path": str(artifact),
                }
            )
            run["hub_results"].append({**item, "content_version_id": "7", "status": "new"})
    state = {"source_portal_daily_runs": {run["run_id"]: run}}
    digests, errors = runtime._persist_daily_source_portals(state, url)
    assert not errors and {item["portal_key"] for item in digests} == {
        "soa-research-topics",
        "soa-artificial-intelligence",
    }
    assert len(state["pending_source_portal_publications"]) == 2
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT portal_key, evidence_json FROM source_portal_captures")
            rows = cursor.fetchall()
    assert len(rows) == 2
    for portal_key, evidence in rows:
        validate_daily_evidence(evidence)
        assert len(evidence["observations"]) == len(evidence["hub_results"]) == 1
        assert (
            evidence["observations"][0]["source_page_url"] == SOURCE_PORTALS_BY_KEY[portal_key].url
        )


def test_migration_keeps_v5_directory_rows_and_enforces_daily_nullability(tmp_path, monkeypatch):
    url = uninitialized_postgres_url_for_path(tmp_path / "v5-upgrade")
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            schema = cursor.fetchone()[0]
    migrations = hub._migrations
    with monkeypatch.context() as patch:
        patch.setattr(hub, "_migrations", lambda: migrations()[:5])
        assert hub.apply_content_hub_schema(url, schema=schema)["version"] == 5
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO source_portal_captures (portal_key, page_url, scope_key, captured_at, acquired_on, page_sha256, complete, description_zh, description_en) VALUES ('cia-publications', 'https://www.cia-ica.ca/publications', 'legacy', '2026-11-01T12:00:00-05:00', '2026-11-01', %s, FALSE, '保留的旧动态', 'Preserved old update') RETURNING capture_id",
                ("a" * 64,),
            )
            capture_id = cursor.fetchone()[0]
    assert hub.apply_content_hub_schema(url, schema=schema)["version"] == 6
    assert hub.content_hub_schema_plan(url, schema=schema)["pending"] == []
    old = hub.content_hub_read_source_portal_capture(
        portal_key="cia-publications", capture_id=capture_id, database_url=url, schema=schema
    )
    assert old["capture_kind"] == "directory" and old["description_en"] == "Preserved old update"
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            with pytest.raises(psycopg2.IntegrityError):
                cursor.execute(
                    "UPDATE source_portal_captures SET page_url = NULL WHERE capture_id = %s",
                    (capture_id,),
                )

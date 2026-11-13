from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import psycopg2
import pytest

import ai_actuarial.content_hub as hub
import ai_actuarial.local_collection_runtime as runtime
from ai_actuarial.source_portal_daily import daily_description as _daily_description
from ai_actuarial.source_portal_daily import validate_daily_evidence
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


def _describe_as_ai(current, previous=()):
    materials = {
        (item["url"], item["raw_sha256"]) for run in current for item in run["observations"]
    }
    return _daily_description(current, list(previous), ai_materials=materials)


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


def test_daily_description_lists_first_new_material_and_suppresses_backlog():
    previous = _evidence(day="2026-11-01")
    current = _evidence(sha="b")
    previous["observations"].append(
        {
            "url": "https://www.cia-ica.ca/publications",
            "raw_sha256": "a" * 64,
            "source_page_url": "https://www.cia-ica.ca/publications",
            "title": "Publications",
            "kind": "page",
            "request_scope": "d" * 64,
        }
    )
    current["observations"].append(
        {
            "url": "https://www.cia-ica.ca/publications",
            "raw_sha256": "b" * 64,
            "source_page_url": "https://www.cia-ica.ca/publications",
            "title": "Publications",
            "kind": "page",
            "request_scope": "d" * 64,
        }
    )
    observed = current["observations"][0]
    discovered = {
        **observed,
        "url": "https://www.cia-ica.ca/new-mortality-study.pdf",
        "title": "New mortality study",
    }
    current["observations"].append(discovered)
    current["hub_results"] = [
        {
            **{key: observed[key] for key in ("url", "raw_sha256", "source_page_url")},
            "content_version_id": "1",
            "status": "new",
        },
        {
            **{key: discovered[key] for key in ("url", "raw_sha256", "source_page_url")},
            "content_version_id": "3",
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
    zh, en = _describe_as_ai([current, copy.deepcopy(current)], [previous])
    assert "新发现1份AI资料：「New mortality study」" in zh
    assert "Found 1 new AI material: “New mortality study”." in en
    assert "New mortality study" in en and "AI mortality study" not in en and "older.pdf" not in en
    assert "不代表全站扫描" not in zh and "full-site scan" not in en
    assert "预算用完" not in zh and "request budget" not in en
    assert len(zh) <= 2000 and len(en) <= 2000
    # A different file version remains known by URL on later daily runs.
    reverting = _evidence(sha="a", day="2026-11-03")
    assert _describe_as_ai([reverting], [previous, current])[0] == "未发现新的AI资料。"


@pytest.mark.parametrize("title", ["Download the full report", "Download PDF", "Read more"])
def test_daily_description_replaces_legacy_generic_titles_with_url_filename(title):
    evidence = _evidence()
    evidence["observations"][0]["title"] = title
    zh, en = _describe_as_ai([evidence], [])
    assert "report.pdf" in zh and "report.pdf" in en
    assert title not in zh and title not in en


def test_daily_description_states_remaining_title_count_clearly_in_chinese():
    evidence = _evidence()
    first = evidence["observations"][0]
    for index in range(1, 9):
        evidence["observations"].append(
            {
                **first,
                "url": f"https://www.cia-ica.ca/report-{index}.pdf",
                "raw_sha256": f"{index:064x}",
                "title": f"Mortality study {index}",
            }
        )
    zh, _en = _describe_as_ai([evidence], [])
    assert "，另有1份AI资料" in zh
    assert "等1份" not in zh


def test_daily_description_reports_observed_file_without_hub_import_result():
    evidence = _evidence()
    evidence["observations"][0]["title"] = "Observed study"
    zh, en = _describe_as_ai([evidence], [])
    assert "新发现1份AI资料：「Observed study」" in zh
    assert "Found 1 new AI material: “Observed study”." in en

    evidence["hub_results"] = [
        {
            **{
                key: evidence["observations"][0][key]
                for key in ("url", "raw_sha256", "source_page_url")
            },
            "content_version_id": "1",
            "status": "existing",
        }
    ]
    assert "未发现新的AI资料" in _describe_as_ai([evidence], [])[0]


def test_daily_description_requires_exact_ai_identity_without_title_keyword_guessing():
    evidence = _evidence()
    observation = evidence["observations"][0]
    observation["title"] = "Governance study"
    identity = (observation["url"], observation["raw_sha256"])

    assert "Governance study" in _daily_description([evidence], [], ai_materials={identity})[0]
    assert _daily_description([evidence], [], ai_materials=set())[0] == "未发现新的AI资料。"
    assert (
        _daily_description([evidence], [], ai_materials={(identity[0], "f" * 64)})[0]
        == "未发现新的AI资料。"
    )


def test_daily_description_uses_first_daily_observation_to_identify_known_materials():
    def evidence_with_status(hour, sha, status):
        evidence = _evidence(hour=hour, sha=sha)
        item = evidence["observations"][0]
        evidence["hub_results"] = [
            {
                **{key: item[key] for key in ("url", "raw_sha256", "source_page_url")},
                "content_version_id": str(hour),
                "status": status,
            }
        ]
        validate_daily_evidence(evidence)
        return evidence

    known = evidence_with_status(12, "a", "existing")
    updated = evidence_with_status(14, "b", "new")
    for runs in ([known, updated], [updated, known]):
        assert "未发现新的AI资料" in _describe_as_ai(list(runs), [])[0]

    discovered = evidence_with_status(12, "a", "new")
    retry = evidence_with_status(14, "a", "existing")
    for runs in ([discovered, retry], [retry, discovered]):
        zh, en = _describe_as_ai(list(runs), [])
        assert "新发现1份AI资料" in zh and "Found 1 new AI material" in en


def test_daily_description_excludes_materials_in_previous_and_same_day_backlog_hub_results():
    prior = _evidence(day="2026-11-01", url="https://www.cia-ica.ca/other.pdf")
    prior["hub_results"] = [
        {
            "url": "https://www.cia-ica.ca/report.pdf",
            "raw_sha256": "a" * 64,
            "source_page_url": "https://www.cia-ica.ca/publications",
            "content_version_id": "1",
            "status": "new",
        }
    ]
    current = _evidence(day="2026-11-02", sha="b")
    current["hub_results"] = [
        {
            **{
                key: current["observations"][0][key]
                for key in ("url", "raw_sha256", "source_page_url")
            },
            "content_version_id": "2",
            "status": "new",
        }
    ]
    assert "未发现新的AI资料" in _describe_as_ai([current], [prior])[0]

    backlog = _evidence(hour=12, url="https://www.cia-ica.ca/other.pdf")
    backlog["observations"][0].update(kind="page", title="", request_scope="c" * 64)
    backlog["hub_results"] = [prior["hub_results"][0]]
    current["captured_at"] = "2026-11-02T14:00:00-05:00"
    current["run_id"] = hashlib.sha256(current["captured_at"].encode()).hexdigest()
    for runs in ([backlog, current], [current, backlog]):
        assert "未发现新的AI资料" in _describe_as_ai(list(runs), [])[0]


def test_daily_description_excludes_materials_known_only_through_previous_hub_history():
    previous = _evidence(day="2026-11-01", url="https://www.cia-ica.ca/other.pdf")
    previous["hub_results"] = [
        {
            "url": "https://www.cia-ica.ca/report.pdf",
            "raw_sha256": "a" * 64,
            "source_page_url": "https://www.cia-ica.ca/publications",
            "content_version_id": "1",
            "status": "existing",
        }
    ]
    current = _evidence(day="2026-11-02", sha="b")
    current["hub_results"] = [
        {
            **{
                key: current["observations"][0][key]
                for key in ("url", "raw_sha256", "source_page_url")
            },
            "content_version_id": "2",
            "status": "new",
        }
    ]
    assert "未发现新的AI资料" in _describe_as_ai([current], [previous])[0]


@pytest.mark.parametrize("kind", ["page", "file"])
def test_daily_description_uses_general_wording_for_partial_read_failures(kind):
    evidence = _evidence()
    evidence["observations"][0]["kind"] = kind
    if kind == "page":
        evidence["observations"][0]["request_scope"] = "d" * 64
    evidence["limits"]["source_error_count"] = 1
    zh, en = _describe_as_ai([evidence], [])
    assert "部分内容暂时无法查看；本次汇报只包含已成功查看的内容。" in zh
    assert "Some content could not be checked; this report covers only successful reads." in en
    assert "网页暂时无法查看" not in zh and "pages could not be checked" not in en


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e["observations"].clear(),
        lambda e: e.update(portal_key="soa-artificial-intelligence"),
        lambda e: e.update(acquired_on="2026-11-01"),
        lambda e: e["observations"][0].update(raw_sha256="bad"),
        lambda e: e["observations"].append(copy.deepcopy(e["observations"][0])),
        lambda e: e["observations"][0].update(kind="page", request_scope="d" * 64, is_article=1),
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
def test_post_page_observations_preserve_request_scopes_and_hashes(
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
    _zh, en = _describe_as_ai([evidence], [])
    assert "No new AI materials were found." in en
    assert "checked" not in en and "page changed" not in en
    assert all("is_article" not in item for item in evidence["observations"])


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
    assert projected["description_en"] == "No new AI materials were found."
    legacy_multiple = copy.deepcopy(legacy)
    legacy_multiple["observations"].append(
        {**legacy_multiple["observations"][0], "raw_sha256": "d" * 64}
    )
    assert _describe_as_ai([legacy_multiple], [])[1] == "No new AI materials were found."
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
    assert two["description_en"] == "No new AI materials were found."
    assert "AI mortality study" not in two["description_en"]
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
    assert three["description_en"] == "No new AI materials were found."
    assert "Directory study" not in three["description_en"]
    assert "Old directory study" not in three["description_en"]
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


def test_hub_daily_description_only_lists_exact_ai_first_enrichment(tmp_path):
    url, schema = _database(tmp_path, "daily-ai-material-filter")
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]

    def version(slug, title, markdown, *, primary=None, categories=None):
        canonical_url = f"https://www.cia-ica.ca/research/{slug}.pdf"
        imported = hub.ingest_live_article(
            canonical_url=canonical_url,
            source_site="cia-ica",
            source_page_url=portal.url,
            title=title,
            raw_bytes=f"{slug} source bytes".encode(),
            markdown=markdown,
            content_type="application/pdf",
            data_root=tmp_path / "live-data",
            database_url=url,
            schema=schema,
        )
        if primary:
            package = {
                "title": title,
                "summary": f"Summary for {title}",
                "category": primary,
                "keywords": [primary],
            }
            hub.save_live_enrichment(
                content_version_id=imported["content_version_id"],
                markdown_text_variant_id=imported["markdown_text_variant_id"],
                markdown_sha256=imported["markdown_sha256"],
                primary_category=primary,
                bilingual_metadata={"zh": package, "en": package},
                categories=categories,
                date_facts={
                    "publication_date": None,
                    "revision_date": None,
                    "document_version_date": None,
                },
                date_review_status="complete",
                date_review_reason=None,
                date_review_unresolved=[],
                recipe="daily-description-test",
                run_id=f"daily-{slug}",
                database_url=url,
                schema=schema,
            )
        return {"url": canonical_url, **imported}

    ai = version(
        "governance",
        "Governance study",
        "AI governance evidence supports this study.",
        primary="AI",
        categories=[{"key": "AI", "evidence": ["AI governance evidence"]}],
    )
    secondary = version(
        "pricing",
        "Pricing with AI",
        "Pricing analysis discusses AI tools.",
        primary="Pricing",
        categories=[
            {"key": "Pricing", "evidence": ["Pricing analysis"]},
            {"key": "AI", "evidence": ["AI tools"]},
        ],
    )
    unclassified = version("unclassified", "Unclassified AI survey", "Unreviewed survey.")
    mismatch = version(
        "version-mismatch",
        "Version changed AI overview",
        "AI overview evidence for the stored version.",
        primary="AI",
        categories=[{"key": "AI", "evidence": ["AI overview evidence"]}],
    )
    excluded = version(
        "excluded",
        "Excluded AI survey",
        "AI evidence for an excluded source.",
        primary="AI",
        categories=[{"key": "AI", "evidence": ["AI evidence"]}],
    )
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO excluded_urls (url_identity_sha256, url_value_json, reason) "
                "VALUES (%s, %s, 'tender')",
                (hashlib.sha256(excluded["url"].encode()).hexdigest(), json.dumps(excluded["url"])),
            )

    directory = hub.content_hub_record_source_portal_capture(
        portal_key=portal.portal_key,
        page_url=portal.url,
        scope_key=portal.scope_key,
        captured_at="2026-11-02T10:00:00-05:00",
        acquired_on="2026-11-02",
        page_sha256="e" * 64,
        entries=[{"url": secondary["url"], "title": "Unrelated finance item"}],
        complete=True,
        intro_zh="目录前言和无关资料清单",
        intro_en="Directory introduction and unrelated material list.",
        database_url=url,
        schema=schema,
    )
    evidence = _evidence()
    evidence["observations"] = [
        {
            "url": item["url"],
            "raw_sha256": raw_sha or item["raw_sha256"],
            "source_page_url": portal.url,
            "title": title,
            "kind": "file",
        }
        for item, raw_sha, title in (
            (ai, None, "Governance study"),
            (secondary, None, "Pricing with AI"),
            (unclassified, None, "Unclassified AI survey"),
            (mismatch, "f" * 64, "Version changed AI overview"),
            (excluded, None, "Excluded AI survey"),
        )
    ]

    daily = hub.content_hub_record_source_portal_daily(evidence, database_url=url, schema=schema)
    assert daily["description_zh"] == "新发现1份AI资料：「Governance study」。"
    assert daily["description_en"] == "Found 1 new AI material: “Governance study”."
    assert "Unrelated finance item" not in daily["description_en"]
    assert "Pricing with AI" not in daily["description_en"]
    assert "Unclassified AI survey" not in daily["description_en"]
    assert "Version changed AI overview" not in daily["description_en"]
    assert "Excluded AI survey" not in daily["description_en"]
    assert "Directory introduction" not in daily["description_en"]
    assert directory["description_en"] != daily["description_en"]


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
        if "/wp-json/wp/v2/news" in url:
            return b"[]", {"content-type": "application/json"}, url
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


@pytest.mark.parametrize(
    "article_label,expected_title",
    [
        ("Annual Mortality Study", "Annual Mortality Study"),
        ("Download PDF", "Annual Mortality Study"),
        ("Download the full report", "Annual Mortality Study"),
        ("Read more", "Annual Mortality Study"),
    ],
)
def test_capture_reports_qualified_html_articles_but_not_navigation_pages(
    tmp_path, monkeypatch, article_label, expected_title
):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(runtime, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(runtime, "_persist_cas", lambda _root, _body, sha: tmp_path / sha)
    article_url = "https://www.cia-ica.ca/research/annual-mortality-study"
    article_body = (
        b"<html><body><main><h1>Annual Mortality Study</h1>"
        b"<p>Research findings and methods for actuaries. "
        b"This article contains enough substantive text to qualify as an HTML publication "
        b"and be extracted as a local article record for the daily digest.</p></main></body></html>"
    )
    state = {"articles": {}}
    captured = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        _Crawler(page=article_body),
        tmp_path,
        {},
        request_limit=1,
        initial_frontier=[
            {
                "url": article_url,
                "kind": "page",
                "depth": 1,
                "referrer": "https://www.cia-ica.ca/publications",
                "title": article_label,
            }
        ],
    )
    assert len(captured["downloads"]) == 1
    [run] = state["source_portal_daily_runs"].values()
    [article_observation] = run["observations"]
    assert article_observation["kind"] == "page"
    assert article_observation["is_article"] is True
    assert article_observation["title"] == (
        "Annual Mortality Study" if expected_title == "Annual Mortality Study" else ""
    )
    evidence = {"schema_version": 1, "portal_key": "cia-publications", **copy.deepcopy(run)}
    for observation in evidence["observations"]:
        observation.pop("artifact_path")
    validate_daily_evidence(evidence)
    zh, en = _describe_as_ai([evidence], [])
    assert f"新发现1份AI资料：「{expected_title}" in zh
    assert expected_title in en and "Found 1 new AI material" in en
    if article_label != "Annual Mortality Study":
        assert article_label not in zh and article_label not in en
    assert "未发现新的AI资料" in _describe_as_ai([evidence], [evidence])[0]

    navigation_state = {"articles": {}}
    runtime._capture(
        runtime.SITES["cia-ica"],
        navigation_state,
        _Crawler(page=article_body),
        tmp_path,
        {},
        request_limit=1,
        initial_frontier=[
            {
                "url": "https://www.cia-ica.ca/about",
                "kind": "page",
                "depth": 1,
                "referrer": "https://www.cia-ica.ca/publications",
                "title": "About the Association",
            }
        ],
    )
    [navigation_run] = navigation_state["source_portal_daily_runs"].values()
    assert not navigation_state["articles"]
    assert "is_article" not in navigation_run["observations"][0]
    navigation_evidence = {
        "schema_version": 1,
        "portal_key": "cia-publications",
        **copy.deepcopy(navigation_run),
    }
    for observation in navigation_evidence["observations"]:
        observation.pop("artifact_path")
    validate_daily_evidence(navigation_evidence)
    assert "未发现新的AI资料" in _describe_as_ai([navigation_evidence], [])[0]


@pytest.mark.parametrize(
    "source_markup,expected_title",
    [
        ("<title>Metadata Mortality Study</title>", "Metadata Mortality Study"),
        ("", "annual-mortality-study"),
    ],
)
def test_capture_uses_html_article_title_when_link_label_is_generic(
    tmp_path, monkeypatch, source_markup, expected_title
):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(runtime, "_state_path_for_data", lambda _state: tmp_path / "state.json")
    monkeypatch.setattr(runtime, "_persist_cas", lambda _root, _body, sha: tmp_path / sha)
    article_url = "https://www.cia-ica.ca/research/annual-mortality-study"
    article_body = (
        f"<html><head>{source_markup}</head><body><main>"
        "<p>Research findings and methods for actuaries. This HTML publication has enough "
        "substantive content to qualify as a captured article.</p>"
        "</main></body></html>"
    ).encode()
    state = {"articles": {}}
    captured = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        _Crawler(page=article_body),
        tmp_path,
        {},
        request_limit=1,
        initial_frontier=[
            {
                "url": article_url,
                "kind": "page",
                "depth": 1,
                "referrer": "https://www.cia-ica/publications",
                "title": "Read more",
            }
        ],
    )
    assert len(captured["downloads"]) == 1
    [article] = captured["downloads"]
    [run] = state["source_portal_daily_runs"].values()
    [observation] = run["observations"]
    assert article["title"] == expected_title
    assert observation["title"] == ("Metadata Mortality Study" if source_markup else "")
    evidence = {"schema_version": 1, "portal_key": "cia-publications", **copy.deepcopy(run)}
    for item in evidence["observations"]:
        item.pop("artifact_path")
    description_zh, _description_en = _describe_as_ai([evidence], [])
    assert expected_title in description_zh
    assert "Read more" not in description_zh


@pytest.mark.parametrize(
    "titles",
    [
        ("Annual Mortality Study", "Download PDF"),
        ("Download PDF", "Annual Mortality Study"),
        ("Annual Mortality Study", "Read more"),
        ("Read more", "Annual Mortality Study"),
    ],
)
def test_capture_duplicate_article_aliases_keep_first_useful_title(tmp_path, monkeypatch, titles):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(runtime, "_state_path_for_data", lambda _state: tmp_path / "state.json")
    monkeypatch.setattr(runtime, "_persist_cas", lambda _root, _body, sha: tmp_path / sha)
    final_url = "https://www.cia-ica.ca/research/annual-mortality-study"
    body = (
        b"<html><body><main><h1>Annual Mortality Study</h1>"
        b"<p>Research findings and methods for actuaries. This article contains sufficient "
        b"substantive text to qualify as an HTML publication.</p></main></body></html>"
    )

    class AliasCrawler(_Crawler):
        def _request(self, requested_url, **_kwargs):
            self.site_attempts += 1
            return body, {"content-type": "text/html"}, final_url

    referrer = "https://www.cia-ica.ca/publications"
    aliases = [
        (final_url, titles[0]),
        (final_url + "-alias", titles[1]),
    ]
    state = {"articles": {}}
    runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        AliasCrawler(),
        tmp_path,
        {},
        request_limit=2,
        initial_frontier=[
            {"url": url, "kind": "page", "depth": 1, "referrer": referrer, "title": title}
            for url, title in aliases
        ],
    )
    [run] = state["source_portal_daily_runs"].values()
    [observation] = run["observations"]
    assert observation["is_article"] is True
    assert observation["title"] == "Annual Mortality Study"
    evidence = {"schema_version": 1, "portal_key": "cia-publications", **copy.deepcopy(run)}
    for item in evidence["observations"]:
        item.pop("artifact_path")
    description_zh, _description_en = _describe_as_ai([evidence], [])
    assert "Annual Mortality Study" in description_zh
    assert "annual-mortality-study" not in description_zh


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


@pytest.mark.parametrize("already_frozen", [False, True])
@pytest.mark.parametrize("first_article", [False, True])
def test_daily_persistence_merges_article_marker_when_duplicate_referrers_collapse(
    tmp_path, monkeypatch, already_frozen, first_article
):
    url, schema = _database(tmp_path, f"daily-article-duplicate-{already_frozen}")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    final_url = "https://www.cia-ica.ca/research/annual-mortality-study"
    article_url = "https://www.cia-ica.ca/research/annual-mortality-study-alias"
    body = (
        b"<html><body><main><h1>Annual Mortality Study</h1>"
        b"<p>Research findings and methods for actuaries. This HTML article contains enough "
        b"substantive text to qualify as a captured publication record.</p></main></body></html>"
    )

    class AliasCrawler(_Crawler):
        def _request(self, requested_url, **_kwargs):
            self.site_attempts += 1
            return body, {"content-type": "text/html"}, final_url

    state = {"articles": {}}
    capture = runtime._capture(
        runtime.SITES["cia-ica"],
        state,
        AliasCrawler(),
        tmp_path,
        {},
        request_limit=2,
        initial_frontier=[
            {
                "url": final_url,
                "kind": "page",
                "depth": 0,
                "referrer": portal.url,
                "title": "",
            },
            {
                "url": article_url,
                "kind": "page",
                "depth": 1,
                "referrer": portal.url + "/alias",
                "title": "Annual Mortality Study",
            },
        ],
    )
    assert not capture["errors"] and len(capture["downloads"]) == 1
    [run] = state["source_portal_daily_runs"].values()
    assert len(run["observations"]) == 2
    if first_article:
        run["observations"][0].update(is_article=True, title="")
    assert run["observations"][0].get("is_article", False) is first_article
    assert run["observations"][1]["is_article"] is True
    assert (
        len(
            {
                (item["url"], item["raw_sha256"], item["request_scope"])
                for item in run["observations"]
            }
        )
        == 1
    )
    state["active_source_portal_daily_run"] = capture["daily_run_id"]
    runtime._record_daily_hub_result(
        state, "cia-ica", capture["downloads"][0], True, {"content_version_id": 1}
    )
    state.pop("active_source_portal_daily_run")
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

    digests, errors = runtime._persist_daily_source_portals(state, url)
    assert len(digests) == 1 and not errors
    [evidence] = run["evidence"]
    assert len(evidence["observations"]) == 1
    assert evidence["observations"][0]["is_article"] is True
    assert evidence["observations"][0]["title"] == "Annual Mortality Study"
    assert evidence["observations"][0]["source_page_url"] == portal.url
    validate_daily_evidence(evidence)
    description_zh, description_en = _describe_as_ai([evidence], [])
    assert "新发现1份AI资料：「Annual Mortality Study」" in description_zh
    assert (
        "Annual Mortality Study" in description_en and "Found 1 new AI material" in description_en
    )
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT evidence_json, evidence_sha256 FROM source_portal_captures WHERE capture_id = %s",
                (digests[0]["capture_id"],),
            )
            [stored, stored_sha] = cursor.fetchone()
    assert stored["observations"][0]["is_article"] is True
    assert stored["observations"][0]["title"] == "Annual Mortality Study"
    assert stored_sha.strip() == validate_daily_evidence(evidence)[2]
    replay = hub.content_hub_record_source_portal_daily(
        copy.deepcopy(evidence), database_url=url, schema=schema
    )
    assert replay["duplicate"] is True and replay["capture_id"] == digests[0]["capture_id"]
    replayed_capture = hub.content_hub_read_source_portal_capture(
        portal_key=portal.portal_key,
        capture_id=replay["capture_id"],
        database_url=url,
        schema=schema,
    )
    assert replayed_capture["evidence_sha256"] == stored_sha.strip()


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
        request_limit=2,
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
    assert update["description_en"] == "No new AI materials were found."
    assert "Mortality study" not in update["description_en"]
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


def test_completed_duplicate_existing_result_only_marks_soa_ai_card(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    raw_sha = hashlib.sha256(b"%PDF-1.4 verified test file").hexdigest()
    ai_portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    topics_portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    sources = [
        ("https://www.soa.org/research/ai-pricing-study.pdf", ai_portal.url),
        ("https://www.soa.org/research/general-mortality-study.pdf", topics_portal.url),
    ]
    state = {"sites": {"soa": {}}, "articles": {}}
    for version_id, (url, referrer) in enumerate(sources, start=1):
        state["articles"][runtime._file_key(url, raw_sha)] = {
            "url": url,
            "raw_sha256": raw_sha,
            "source_page_url": referrer,
            "site_id": "soa",
            "stage": "complete",
            "content_version_id": version_id,
            "discovery_sites": ["soa"],
        }
    captured = runtime._capture(
        runtime.SITES["soa"],
        state,
        _Crawler(),
        tmp_path,
        state["sites"]["soa"],
        request_limit=2,
        initial_frontier=[
            {"url": url, "kind": "document", "referrer": referrer, "title": "Study"}
            for url, referrer in sources
        ],
    )
    assert len(captured["downloads"]) == 2
    monkeypatch.setattr(runtime, "_capture", lambda *_args, **_kwargs: captured)
    monkeypatch.setattr(runtime, "_new_crawler", lambda _root: _Crawler())
    monkeypatch.setattr(runtime, "_process_articles", lambda *_args, **_kwargs: _processed())
    monkeypatch.setattr(
        runtime,
        "_sync_source_portals",
        lambda *_args: {"status": "succeeded", "targets": {}, "digests": [], "errors": []},
    )
    config = {"data_root": str(tmp_path), "state_root": str(tmp_path), "targets": {}}
    runtime._run_site(
        "soa", dt.datetime.now(runtime.TIME_ZONE).date().isoformat(), config, state, None
    )
    [run] = state["source_portal_daily_runs"].values()
    assert [(item["url"], item["status"]) for item in run["hub_results"]] == [
        (sources[0][0], "existing")
    ]


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
    assert sent[0]["description_en"] == "No new AI materials were found."
    assert "checked" not in sent[0]["description_en"]
    assert "directory no longer" not in sent[0]["description_en"].lower()


def test_soa_ai_collection_baseline_and_unchanged_runs_do_not_publish_daily_updates(
    tmp_path, monkeypatch
):
    url, schema = _database(tmp_path, "soa-ai-daily-silence")
    _patch_hub(monkeypatch, url, schema)
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state.json")
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    site = runtime.SITES["soa-ai-bulletin-focused"]
    old_pdf = (
        "https://www.soa.org/globalassets/assets/files/resources/research-report/old-ai-report.pdf"
    )
    new_pdf = (
        "https://www.soa.org/globalassets/assets/files/resources/research-report/new-ai-report.pdf"
    )
    baseline = (
        f'<section class="nextsteps-block"><a href="{old_pdf}">Old AI report</a></section>'.encode()
    )
    changed = baseline.replace(
        b"</section>", f'<a href="{new_pdf}">New AI report</a></section>'.encode()
    )

    class FrozenDateTime(dt.datetime):
        current = dt.datetime(2026, 11, 10, 12, tzinfo=runtime.TIME_ZONE)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    clock = SimpleNamespace(**vars(dt))
    clock.datetime = FrozenDateTime
    monkeypatch.setattr(runtime, "dt", clock)
    sent = []
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, _target, updates: sent.extend(copy.deepcopy(updates)) or {"failures": []},
    )
    state = {"articles": {}}
    config = {"targets": {"china": {"host": "china"}, "overseas": {"host": "overseas"}}}

    def collect_and_sync(body, day, request_limit):
        FrozenDateTime.current = dt.datetime(2026, 11, day, 12, tzinfo=runtime.TIME_ZONE)
        captured = runtime._capture(
            site,
            state,
            _Crawler(page=body),
            tmp_path / "data",
            {},
            request_limit=request_limit,
            initial_frontier=[{"url": portal.url, "kind": "page", "referrer": portal.url}],
        )
        assert captured["portal_captures"]
        return captured

    collect_and_sync(baseline, 10, 1)
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    assert sent == []
    collect_and_sync(baseline, 11, 1)
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    assert sent == []
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT description_en FROM source_portal_captures "
                "WHERE portal_key = %s AND capture_kind = 'daily_collection' ORDER BY capture_id",
                (portal.portal_key,),
            )
            assert cursor.fetchall() == [(None,), (None,)]

    captured = collect_and_sync(changed, 12, 3)
    new_capture = next(item for item in captured["downloads"] if item["url"] == new_pdf)
    imported = hub.ingest_live_article(
        canonical_url=new_pdf,
        source_site=site.site_id,
        source_page_url=portal.url,
        title="New AI report",
        raw_bytes=Path(new_capture["artifact_path"]).read_bytes(),
        markdown="AI research evidence for a new actuarial report.",
        content_type="application/pdf",
        data_root=tmp_path / "live-data",
        database_url=url,
        schema=schema,
    )
    package = {
        "title": "New AI report",
        "summary": "New AI report",
        "category": "AI",
        "keywords": ["AI"],
    }
    hub.save_live_enrichment(
        content_version_id=imported["content_version_id"],
        markdown_text_variant_id=imported["markdown_text_variant_id"],
        markdown_sha256=imported["markdown_sha256"],
        primary_category="AI",
        bilingual_metadata={"zh": package, "en": package},
        categories=[{"key": "AI", "evidence": ["AI research evidence"]}],
        date_facts={"publication_date": None, "revision_date": None, "document_version_date": None},
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="soa-ai-daily-test",
        run_id="soa-ai-new-report",
        database_url=url,
        schema=schema,
    )
    assert runtime._sync_source_portals(state, config, url)["status"] == "succeeded"
    assert len(sent) == 2
    assert all("Found 1 new AI material" in update["description_en"] for update in sent)
    assert all("New AI report" in update["description_en"] for update in sent)


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
    news_poll = next(
        item
        for item in runtime._initial_frontier(runtime.SITES["cia-ica"])
        if item.get("collection") == "news"
    )

    class RedirectCrawler(_Crawler):
        def _request(self, requested_url, **kwargs):
            body, headers, _url = super()._request(requested_url, **kwargs)
            return body, headers, portal.url + "/"

    state = {"articles": {}}
    site_state = {
        "queue": [
            {"url": portal.url + "/", "kind": "page", "referrer": portal.url + "/"},
            news_poll,
        ],
        "cursor": 0,
        "visited": [runtime._queue_identity(news_poll)],
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
    assert set(state["pending_source_portal_publications"]) == {"soa-research-topics|2026-11-02"}
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

from __future__ import annotations

import datetime as dt
import hashlib
import json
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
import pytest

import ai_actuarial.content_hub as hub
import ai_actuarial.local_collection_runtime as runtime
from ai_actuarial.content_hub import (
    ContentHubError,
    apply_content_hub_schema,
    content_hub_read_source_portal_capture,
    content_hub_record_source_portal_capture,
)
from ai_actuarial.source_portals import (
    SOURCE_PORTAL_URLS,
    SOURCE_PORTALS,
    SOURCE_PORTALS_BY_KEY,
    SOURCE_PORTALS_BY_URL,
)
from tests.postgres_helpers import uninitialized_postgres_url_for_path


def _database_schema(tmp_path: Path, name: str) -> tuple[str, str]:
    url = uninitialized_postgres_url_for_path(tmp_path / f"{name}.db")
    connection = psycopg2.connect(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            return url, str(cursor.fetchone()[0])
    finally:
        connection.close()


def test_catalog_urls_are_exact_runtime_site_seeds_and_aliases() -> None:
    assert SOURCE_PORTAL_URLS
    assert len(SOURCE_PORTALS) == 30
    represented = {site_id for portal in SOURCE_PORTALS for site_id in portal.site_ids}
    assert set(runtime.SITES) - represented == set()
    for portal in SOURCE_PORTALS:
        assert set(portal.site_ids) <= set(runtime.SITES)
        assert portal.extraction_source_id in runtime.SITES
        site = runtime.SITES[portal.extraction_source_id]
        assert runtime._allowed_host(portal.capture_urls[0], site)
        assert runtime._allowed_path(portal.capture_urls[0], site)
        for url in (portal.url, *portal.capture_urls):
            assert SOURCE_PORTALS_BY_URL[url] == portal
        assert SOURCE_PORTALS_BY_KEY[portal.portal_key] == portal
    assert SOURCE_PORTALS_BY_URL["https://www.casact.org/publications-research"].portal_key == (
        "cas-publications-research"
    )
    assert SOURCE_PORTALS_BY_URL["https://www.cia-ica.ca/publications/"].portal_key == (
        "cia-publications"
    )
    assert (
        SOURCE_PORTALS_BY_URL["https://www.actuaries.jp/english/lib/index.html"].portal_key
        == "japan-library"
    )
    assert SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"].extraction_source_id == (
        "soa-ai-topic-landing"
    )
    assert "https://www.actuaries.org.uk/insight/" in SOURCE_PORTAL_URLS


def test_soa_ai_card_entries_and_fixed_collection_sources() -> None:
    from ai_actuarial.source_portals import SOA_AI_ENTRY_LINKS

    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    assert [entry["url"] for entry in SOA_AI_ENTRY_LINKS] == [
        "https://www.soa.org/programs/ai-resources/",
        "https://www.soa.org/research/topics/artificial-intelligence-res-report-list/",
        "https://www.soa.org/resources/research-reports/2025/research-ai-bulletin/",
    ]
    assert all(entry["title_zh"] and entry["title_en"] for entry in SOA_AI_ENTRY_LINKS)
    assert portal.capture_urls == (SOA_AI_ENTRY_LINKS[0]["url"],)
    assert runtime.SITES[portal.extraction_source_id].seeds == portal.capture_urls
    assert SOA_AI_ENTRY_LINKS[1]["url"] in runtime.SITES["soa-ai-bulletin-focused"].seeds
    assert (
        "https://www.soa.org/research/topics/artificial-intelligence-topic-landing/"
        in SOURCE_PORTAL_URLS
    )
    assert len(runtime.SITES) == 32


def test_ai_resources_capture_uses_live_section_shape_and_partial_safety() -> None:
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    at = dt.datetime(2026, 11, 13, 12, tzinfo=ZoneInfo("America/New_York"))
    body = (
        '<nav><a href="/research/unrelated">Navigation</a></nav>'
        '<main><a href="/research/unrelated-main-link">Unrelated main link</a></main>'
        '<section class="nextsteps-block soa-redesign"><h2>Explore AI Resources</h2>'
        '<a class="nextsteps-block-item" href="/research/topics/artificial-intelligence-res-report-list/">'
        "<h4>AI Research Reports</h4></a>"
        '<a class="nextsteps-block-item" href="/prof-dev/pdopportunities/">'
        "<h4>AI Webcasts</h4></a>"
        '<a class="nextsteps-block-item" href="https://getpluggedin.libsyn.com/">'
        "<h4>AI Insights Podcast</h4></a></section>"
    ).encode()
    observed = runtime._source_portal_observation(portal, portal.url, body, at)
    assert observed["complete"] is True
    assert observed["entries"] == [
        {"url": "https://getpluggedin.libsyn.com/", "title": "AI Insights Podcast"},
        {"url": "https://www.soa.org/prof-dev/pdopportunities/", "title": "AI Webcasts"},
        {
            "url": "https://www.soa.org/research/topics/artificial-intelligence-res-report-list/",
            "title": "AI Research Reports",
        },
    ]
    assert (
        runtime._source_portal_observation(portal, portal.url, body[:-10], at)["complete"] is False
    )
    unrelated = b'<main><a href="/research/unrelated-main-link">Unrelated main link</a></main>'
    unrelated_observation = runtime._source_portal_observation(portal, portal.url, unrelated, at)
    assert unrelated_observation["entries"] == []
    assert unrelated_observation["complete"] is False


def test_soa_report_directory_preserves_year_month_and_one_document_identity() -> None:
    from ai_actuarial.local_collection_runtime import _SoaAiReportsParser

    parser = _SoaAiReportsParser()
    parser.feed(
        '<nav><ul><li><a href="/about/nav">Navigation</a></li></ul></nav>'
        '<main><div class="card__text"><h3>2026</h3><ul class="no_bullet">'
        '<li><strong><a href="/resources/research-reports/soa-member-ai-survey/">'
        "SOA Member AI Survey: Spring 2026</a></strong><br><strong>October</strong></li>"
        '<li><a href="/resources/research-reports/soa-member-ai-survey/">'
        "SOA Member AI Survey: Spring 2026</a><br><strong>October</strong></li>"
        '<li><a href="/resources/research-reports/2025/research-ai-bulletin/">'
        "<b>Actuarial Intelligence Bulletin</b></a><br><b>September</b></li>"
        '</ul><ul><li><a href="/about/other">Other list</a></li></ul></div></main>'
        '<footer><ul><li><a href="/about/footer">Footer</a></li></ul></footer>'
    )
    assert parser.report_links == [
        (
            "/resources/research-reports/soa-member-ai-survey/",
            "SOA Member AI Survey: Spring 2026",
            "2026-10",
        ),
        (
            "/resources/research-reports/2025/research-ai-bulletin/",
            "Actuarial Intelligence Bulletin",
            "2026-09",
        ),
    ]


def test_report_from_directory_and_bulletin_is_collected_once_with_official_period(
    tmp_path: Path, monkeypatch
) -> None:
    site = runtime.SITES["soa-ai-bulletin-focused"]
    directory, bulletin = site.seeds
    report = "https://www.soa.org/resources/research-reports/soa-member-ai-survey/"
    pdf = "https://www.soa.org/globalassets/assets/files/resources/research-report/ai-survey.pdf"
    pages = {
        directory: (
            '<main><div class="card__text"><h3>2026</h3><ul class="no_bullet">'
            f'<li><strong><a href="{report}">SOA Member AI Survey: Spring 2026</a></strong>'
            "<br><strong>October</strong></li></ul></div></main>"
        ).encode(),
        bulletin: f'<main><a href="{report}">SOA Member AI Survey: Spring 2026</a><a href="{pdf}">Survey PDF</a></main>'.encode(),
        report: f'<article><h1>SOA Member AI Survey: Spring 2026</h1><p>Published on: October 29, 2026</p><a href="{pdf}">Survey PDF</a></article>'.encode(),
    }

    class Crawler:
        site_attempts = 0
        site_budget = 4
        caa_cookie = None
        algolia_key = None
        requested: list[str] = []

        def begin_site(self, budget: int) -> None:
            self.site_budget = budget

        def _request(self, url: str, **_kwargs):
            self.site_attempts += 1
            self.requested.append(url)
            return pages[url], {"content-type": "text/html"}, url

        def _download_file(self, url: str, root: Path, **_kwargs):
            self.site_attempts += 1
            self.requested.append(url)
            root.mkdir(parents=True, exist_ok=True)
            raw = b"%PDF-1.4\nNo embedded publication date.\n%%EOF"
            path = root / "survey.pdf"
            path.write_bytes(raw)
            return (
                path,
                {"content-type": "application/pdf"},
                url,
                hashlib.sha256(raw).hexdigest(),
                len(raw),
            )

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    monkeypatch.setattr(
        runtime.WebPageCollector,
        "_extract_text",
        lambda *_args: "Published on: October 29, 2026. " * 8,
    )
    state = {"articles": {}}
    crawler = Crawler()
    result = runtime._capture(site, state, crawler, tmp_path / "data", {}, request_limit=4)
    assert result["errors"] == []
    assert crawler.requested == [directory, bulletin, report, pdf]
    assert len(result["downloads"]) == 2
    assert result["downloads"][0]["discovery_metadata"]["date_hint"] == "2026-10"
    assert result["downloads"][0]["discovery_metadata"]["date_hint_source_page_url"] == directory
    assert b"October 29, 2026" in Path(result["downloads"][0]["artifact_path"]).read_bytes()
    assert result["downloads"][1]["url"] == pdf
    assert result["downloads"][1]["discovery_metadata"]["date_hint"] == "2026-10"
    assert result["downloads"][1]["discovery_metadata"]["date_hint_source_page_url"] == directory


def test_report_directory_period_reaches_hub_capture_metadata(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    monkeypatch.setattr(runtime, "ingest_live_article", lambda **kwargs: captured.update(kwargs))
    runtime._ingest_live_capture(
        {
            "url": "https://www.soa.org/resources/research-reports/soa-member-ai-survey/",
            "site_id": "soa-ai-bulletin-focused",
            "source_page_url": "https://www.soa.org/research/topics/artificial-intelligence-res-report-list/",
            "title": "SOA Member AI Survey: Spring 2026",
            "content_type": "text/html",
            "discovery_metadata": {"date_hint": "2026-10"},
        },
        {"data_root": str(tmp_path)},
        object(),
        b"report",
        None,
    )
    assert captured["metadata"]["date_hint"] == "2026-10"


def test_report_without_embedded_date_keeps_directory_period_in_hub(tmp_path: Path) -> None:
    hub_url, _schema = _database_schema(tmp_path, "soa-report-period")
    apply_content_hub_schema(hub_url)
    raw = b"%PDF-1.4\nNo publication date in this file.\n%%EOF"
    runtime._ingest_live_capture(
        {
            "url": "https://www.soa.org/resources/research-reports/no-date-report.pdf",
            "site_id": "soa-ai-bulletin-focused",
            "source_page_url": "https://www.soa.org/research/topics/artificial-intelligence-res-report-list/",
            "title": "Undated report",
            "content_type": "application/pdf",
            "discovery_metadata": {"date_hint": "2026-10"},
        },
        {"data_root": str(tmp_path)},
        hub_url,
        raw,
        None,
    )
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_metadata_json::jsonb->>'date_hint' FROM content_hub.source_record_map "
                "WHERE source_table = 'files' AND source_metadata_json::jsonb->>'title' = 'Undated report'"
            )
            assert cursor.fetchone()[0] == "2026-10"
    finally:
        connection.close()


@pytest.mark.parametrize("kind", ["pdf", "html"])
@pytest.mark.parametrize("existing_hint", [None, "2026-09"])
def test_later_directory_period_reaches_completed_duplicate_without_reprocessing(
    tmp_path: Path, monkeypatch, kind: str, existing_hint: str | None
) -> None:
    hub_url, schema = _database_schema(tmp_path, f"late-period-{kind}-{existing_hint}")
    apply_content_hub_schema(hub_url, schema=schema)
    for name in (
        "ingest_live_article",
        "content_hub_record_source_portal_daily",
        "content_hub_record_source_portal_capture",
        "content_hub_read_source_portal_capture",
    ):
        monkeypatch.setattr(runtime, name, partial(getattr(hub, name), schema=schema))
    site = runtime.SITES["soa-ai-bulletin-focused"]
    directory, bulletin = site.seeds
    report_url = (
        "https://www.soa.org/globalassets/assets/files/resources/research-report/late-ai-study.pdf"
        if kind == "pdf"
        else "https://www.soa.org/resources/research-reports/late-ai-study/"
    )
    directory_link = (
        "https://www.soa.org/resources/research-reports/late-ai-study/"
        if kind == "pdf"
        else report_url
    )
    raw = (
        b"%PDF-1.4\nPublished January 15, 2026.\n%%EOF"
        if kind == "pdf"
        else b"<article><h1>Late AI Study</h1><p>Published January 15, 2026. Actuarial research findings and analysis with substantial source text for the collector.</p></article>"
    )
    markdown = "Published January 15, 2026. Actuarial AI research findings and analysis."
    config = {
        "data_root": str(tmp_path / "data"),
        "state_root": str(tmp_path / "state"),
        "targets": {name: {"host": name} for name in ("china", "overseas")},
    }
    for path in (tmp_path / "data", tmp_path / "state"):
        path.mkdir()
    digest = hashlib.sha256(raw).hexdigest()
    first_site = "soa" if kind == "html" else site.site_id
    prior = {
        "site_id": first_site,
        "url": report_url,
        "source_page_url": (
            SOURCE_PORTALS_BY_KEY["soa-research-topics"].url if kind == "html" else bulletin
        ),
        "title": "Late AI Study",
        "raw_sha256": digest,
        "artifact_path": str(runtime._persist_cas(tmp_path / "data", raw, digest)),
        "content_type": "application/pdf" if kind == "pdf" else "text/html",
        "detected_kind": kind,
        "stage": "complete",
        "discovery_sites": [first_site],
        "discovery_metadata": {"date_hint": existing_hint} if existing_hint else {},
    }
    first = runtime._ingest_live_capture(prior, config, hub_url, raw, markdown)
    prior["content_version_id"] = first["content_version_id"]
    date_facts = {
        "publication_date": {
            "value": "2026-01-15",
            "precision": "day",
            "semantic": "publication",
            "evidence": "Published January 15, 2026",
            "location": "report",
        },
        "revision_date": None,
        "document_version_date": None,
    }
    package = {
        "title": "Late AI Study",
        "summary": "AI research study",
        "category": "AI",
        "keywords": ["AI"],
    }
    hub.save_live_enrichment(
        content_version_id=first["content_version_id"],
        markdown_text_variant_id=first["markdown_text_variant_id"],
        markdown_sha256=first["markdown_sha256"],
        primary_category="AI",
        bilingual_metadata={"zh": package, "en": package},
        categories=[{"key": "AI", "evidence": ["Actuarial AI research findings"]}],
        date_facts=date_facts,
        date_review_status="complete",
        date_review_reason=None,
        date_review_unresolved=[],
        recipe="late-directory-period-test",
        run_id=f"late-period-{kind}-{existing_hint}",
        database_url=hub_url,
        schema=schema,
    )
    original = hub.content_hub_read_version(report_url, digest, hub_url, schema=schema)
    directory_body = (
        '<main><div class="card__text"><h3>2026</h3><ul class="no_bullet">'
        f'<li><strong><a href="{directory_link}">Late AI Study</a></strong>'
        "<br><strong>October</strong></li></ul></div></main>"
    ).encode()
    report_body = f'<main><a href="{report_url}">Download PDF</a></main>'.encode()

    class Crawler:
        site_attempts = 0
        site_budget = 2
        caa_cookie = None
        algolia_key = None

        def begin_site(self, budget: int) -> None:
            self.site_budget = budget

        def _request(self, url: str, **_kwargs):
            self.site_attempts += 1
            body = directory_body if url == directory else report_body if kind == "pdf" else raw
            return body, {"content-type": "text/html"}, url

        def _download_file(self, url: str, root: Path, **_kwargs):
            self.site_attempts += 1
            root.mkdir(parents=True, exist_ok=True)
            path = root / "late.pdf"
            path.write_bytes(raw)
            return path, {"content-type": "application/pdf"}, url, digest, len(raw)

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "state" / "runtime.json")
    monkeypatch.setattr(runtime, "_new_crawler", lambda _root: Crawler())
    monkeypatch.setattr(
        runtime.WebPageCollector,
        "_extract_text",
        lambda *_args: markdown * 3 if kind == "html" else "",
    )
    monkeypatch.setattr(
        runtime, "_run_model", lambda *_args, **_kwargs: pytest.fail("enrichment repeated")
    )
    published = []
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda _config, _target, updates: published.extend(updates) or {"failures": []},
    )
    monkeypatch.setattr(
        runtime, "_stream_target", lambda *_args: pytest.fail("article republished")
    )
    state = {
        "articles": {runtime._file_key(report_url, digest): prior},
        "sites": {
            site.site_id: {
                "queue": [{"url": directory, "kind": "page", "depth": 0, "referrer": directory}],
                "cursor": 0,
                "visited": [],
            }
        },
        "target_acks": {},
    }
    if kind == "pdf" and existing_hint is None:
        ingest = runtime.ingest_live_article
        attempts = 0

        def fail_once(**kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("temporary Hub failure")
            return ingest(**kwargs)

        monkeypatch.setattr(runtime, "ingest_live_article", fail_once)
    runtime._run_site(
        site.site_id, "2026-11-13", config, state, hub_url, request_limit=3 if kind == "pdf" else 2
    )
    if kind == "pdf" and existing_hint is None:
        assert prior["source_provenance_pending"] is True
        assert not published
        runtime._run_site(site.site_id, "2026-11-13", config, state, hub_url, request_limit=1)
    assert len(state["articles"]) == 1
    assert prior["stage"] == "complete"
    assert prior["discovery_metadata"]["date_hint"] == (existing_hint or "2026-10")
    if existing_hint is None:
        assert prior["discovery_metadata"]["date_hint_source_site"] == site.site_id
        assert prior["discovery_metadata"]["date_hint_source_page_url"] == directory
    assert not published
    assert "source_provenance_pending" not in prior
    current = hub.content_hub_read_version(report_url, digest, hub_url, schema=schema)
    assert current["content_version_id"] == original["content_version_id"]
    assert current["annotation"] == original["annotation"]
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_metadata_json::jsonb->>'date_hint', "
                "source_metadata_json::jsonb->>'source_site', "
                "source_metadata_json::jsonb->>'source_page_url' FROM source_record_map "
                "WHERE content_version_id = %s ORDER BY source_snapshot_id DESC",
                (first["content_version_id"],),
            )
            rows = cursor.fetchall()
            assert rows[0] == (
                existing_hint or "2026-10",
                first_site if existing_hint else site.site_id,
                prior["source_page_url"] if existing_hint else directory,
            )
            assert len(rows) == (1 if existing_hint else 2)
            if existing_hint is None:
                assert rows[-1] == (None, first_site, prior["source_page_url"])


def test_ai_resources_baseline_change_rerun_and_independent_target_retry(
    tmp_path: Path, monkeypatch
) -> None:
    hub_url, schema = _database_schema(tmp_path, "soa-ai-resources")
    apply_content_hub_schema(hub_url, schema=schema)
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    at = dt.datetime(2026, 11, 10, 12, tzinfo=ZoneInfo("America/New_York"))
    base = b'<section class="nextsteps-block"><a href="/research/ai-report">AI report</a></section>'
    changed = base.replace(
        b"</section>", b'<a href="/research/new-ai-report">New AI report</a></section>'
    )
    config = {"targets": {"china": {"host": "china"}, "overseas": {"host": "overseas"}}}
    state: dict = {}
    sent: list[tuple[str, list[dict]]] = []
    fail_overseas = True

    def stream(_config, target, updates):
        sent.append((target, updates))
        if target == "overseas" and updates and fail_overseas:
            raise RuntimeError("temporary target failure")
        return {"failures": []}

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "_stream_source_portals", stream)

    def capture(body: bytes, when: dt.datetime, *, complete: bool = True) -> dict:
        observed = runtime._source_portal_observation(portal, portal.url, body, when)
        record = content_hub_record_source_portal_capture(
            portal_key=portal.portal_key,
            page_url=portal.url,
            scope_key=portal.scope_key,
            captured_at=when,
            acquired_on=when.date(),
            page_sha256=observed["page_sha256"],
            entries=observed["entries"],
            complete=complete and observed["complete"],
            intro_zh=portal.overview_zh,
            intro_en=portal.overview_en,
            database_url=hub_url,
            schema=schema,
        )
        runtime._queue_source_portal_update(
            state.setdefault("pending_source_portal_publications", {}), portal.portal_key, record
        )
        return record

    baseline = capture(base, at)
    assert baseline["description_en"] is None
    assert state["pending_source_portal_publications"] == {}
    unrelated = b'<main><a href="/research/unrelated-main-link">Unrelated main link</a></main>'
    unrelated_observation = runtime._source_portal_observation(
        portal, portal.url, unrelated, at + dt.timedelta(days=1)
    )
    assert unrelated_observation["complete"] is False
    assert capture(unrelated, at + dt.timedelta(days=1))["description_en"] is None
    assert state["pending_source_portal_publications"] == {}
    assert (
        capture(base[:-10], at + dt.timedelta(days=1, hours=1), complete=False)["description_en"]
        is None
    )
    update = capture(changed, at + dt.timedelta(days=2))
    assert "New AI report" in update["description_en"]
    assert capture(changed, at + dt.timedelta(days=2, hours=1))["description_en"] is None
    assert capture(changed, at + dt.timedelta(days=3))["description_en"] is None
    assert capture(changed, at + dt.timedelta(days=3))["duplicate"] is True
    assert len(state["pending_source_portal_publications"]) == 1

    first = runtime._sync_source_portals(state, config, object())
    assert first["targets"]["china"]["status"] == "succeeded"
    assert first["targets"]["overseas"]["status"] == "pending"
    fail_overseas = False
    second = runtime._sync_source_portals(state, config, object())
    assert second["status"] == "succeeded"
    assert [target for target, updates in sent if updates] == ["china", "overseas", "overseas"]
    assert state["pending_source_portal_publications"] == {}


@pytest.mark.parametrize(
    "silent_daily_same_day", [False, True], ids=["next-day", "same-day-after-silent-daily"]
)
def test_ai_resources_real_hub_projects_one_update_to_two_isolated_targets(
    tmp_path: Path, monkeypatch, silent_daily_same_day: bool
) -> None:
    from ai_actuarial.api.services.read import list_source_portals
    from ai_actuarial.local_collection_target_worker import apply_source_portals
    from ai_actuarial.storage import Storage

    hub_url, _schema = _database_schema(tmp_path, "soa-ai-hub-to-targets")
    apply_content_hub_schema(hub_url)
    target_urls = {
        target: uninitialized_postgres_url_for_path(tmp_path / f"soa-ai-{target}.db")
        for target in ("china", "overseas")
    }
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    at = dt.datetime(2026, 11, 10, 12, tzinfo=ZoneInfo("America/New_York"))
    base = b'<section class="nextsteps-block"><a href="/research/ai-report">AI report</a></section>'
    changed = base.replace(
        b"</section>", b'<a href="/research/new-ai-report">New AI report</a></section>'
    )
    state: dict = {}
    sent: list[tuple[str, int]] = []

    def stream(_config, target, updates):
        sent.append((target, len(updates)))
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(target_urls[target]),
        )

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    config = {"targets": {target: {"host": target} for target in target_urls}}

    def sync(body: bytes, when: dt.datetime) -> None:
        observed = runtime._source_portal_observation(portal, portal.url, body, when)
        artifact = tmp_path / f"capture-{when.day}-{when.hour}.html"
        artifact.write_bytes(body)
        observed["artifact_path"] = str(artifact)
        state.setdefault("pending_source_portal_captures", []).append(observed)
        result = runtime._sync_source_portals(state, config, hub_url)
        assert result["status"] == "succeeded", result["errors"]

    sync(base, at)
    for target_url in target_urls.values():
        card = next(
            c
            for c in list_source_portals(db_path=target_url)["portals"]
            if c["portal_key"] == portal.portal_key
        )
        assert card["url"] == portal.url
        assert len(card["entry_links"]) == 3
        assert card["updates"] == []

    if silent_daily_same_day:
        raw_sha = hashlib.sha256(base).hexdigest()
        artifact = tmp_path / "daily-baseline.html"
        artifact.write_bytes(base)
        run_id = hashlib.sha256(b"soa-ai-silent-daily").hexdigest()
        state.setdefault("source_portal_daily_runs", {})[run_id] = {
            "site_id": "soa-ai-topic-landing",
            "run_id": run_id,
            "captured_at": (at + dt.timedelta(hours=1)).isoformat(),
            "acquired_on": at.date().isoformat(),
            "observations": [
                {
                    "url": portal.url,
                    "raw_sha256": raw_sha,
                    "kind": "page",
                    "title": "",
                    "source_page_url": portal.url,
                    "request_scope": "a" * 64,
                    "artifact_path": str(artifact),
                }
            ],
            "hub_results": [],
            "limits": {
                "request_count": 1,
                "request_limit": 1,
                "budget_exhausted": False,
                "frontier_remaining": 0,
                "source_error_count": 0,
                "finished": True,
            },
        }
        assert runtime._sync_source_portals(state, config, hub_url)["status"] == "succeeded"
        assert not state["pending_source_portal_publications"]
        with psycopg2.connect(hub_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT description_zh, description_en FROM content_hub.source_portal_captures "
                    "WHERE portal_key = %s AND capture_kind = 'daily_collection'",
                    (portal.portal_key,),
                )
                assert cursor.fetchall() == [(None, None)]
    changed_at = at + (dt.timedelta(hours=2) if silent_daily_same_day else dt.timedelta(days=1))
    sync(changed, changed_at)
    sync(changed, changed_at + dt.timedelta(hours=1))
    assert sent == [("china", 0), ("overseas", 0), ("china", 1), ("overseas", 1)]
    for target_url in target_urls.values():
        card = next(
            c
            for c in list_source_portals(db_path=target_url)["portals"]
            if c["portal_key"] == portal.portal_key
        )
        assert len(card["updates"]) == 1
        assert "New AI report" in card["updates"][0]["description_en"]


def test_ai_resources_failed_baseline_holds_later_capture_until_hub_recovers(
    tmp_path: Path, monkeypatch
) -> None:
    from ai_actuarial.api.services.read import list_source_portals
    from ai_actuarial.local_collection_target_worker import apply_source_portals
    from ai_actuarial.storage import Storage

    hub_url, _schema = _database_schema(tmp_path, "soa-ai-retry-hub")
    apply_content_hub_schema(hub_url)
    target_urls = {
        target: uninitialized_postgres_url_for_path(tmp_path / f"soa-ai-retry-{target}.db")
        for target in ("china", "overseas")
    }
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    at = dt.datetime(2026, 11, 10, 10, tzinfo=ZoneInfo("America/New_York"))
    base = b'<section class="nextsteps-block"><a href="/research/ai-report">AI report</a></section>'
    changed = base.replace(
        b"</section>", b'<a href="/research/new-ai-report">New AI report</a></section>'
    )
    state: dict = {}
    sent: list[tuple[str, int]] = []
    attempts: list[str] = []
    hub_failed = True
    record_capture = runtime.content_hub_record_source_portal_capture

    def persist(**values):
        attempts.append(values["captured_at"])
        if hub_failed and values["captured_at"] == at.isoformat():
            raise RuntimeError("temporary Hub failure")
        return record_capture(**values)

    def stream(_config, target, updates):
        sent.append((target, len(updates)))
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(target_urls[target]),
        )

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "content_hub_record_source_portal_capture", persist)
    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    config = {"targets": {target: {"host": target} for target in target_urls}}

    def queue(body: bytes, when: dt.datetime) -> None:
        observed = runtime._source_portal_observation(portal, portal.url, body, when)
        assert observed["complete"] is True
        artifact = tmp_path / f"retry-{when.hour}.html"
        artifact.write_bytes(body)
        observed["artifact_path"] = str(artifact)
        state.setdefault("pending_source_portal_captures", []).append(observed)

    queue(base, at)
    first = runtime._sync_source_portals(state, config, hub_url)
    assert first["status"] == "partial"
    assert first["captures_persisted"] == 0
    queue(changed, at + dt.timedelta(hours=1))
    second = runtime._sync_source_portals(state, config, hub_url)
    assert second["status"] == "partial"
    assert second["captures_persisted"] == 0
    assert attempts == [at.isoformat(), at.isoformat()]
    assert len(state["pending_source_portal_captures"]) == 2
    assert state["pending_source_portal_publications"] == {}

    hub_failed = False
    state["pending_source_portal_captures"].reverse()
    recovered = runtime._sync_source_portals(state, config, hub_url)
    assert recovered["status"] == "succeeded", recovered["errors"]
    assert recovered["captures_persisted"] == 2
    assert attempts[-2:] == [at.isoformat(), (at + dt.timedelta(hours=1)).isoformat()]
    assert state["pending_source_portal_captures"] == []
    assert state["pending_source_portal_publications"] == {}
    assert [(target, count) for target, count in sent if count] == [
        ("china", 1),
        ("overseas", 1),
    ]
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT description_en FROM content_hub.source_portal_captures "
                "WHERE portal_key = %s AND capture_kind = 'directory' ORDER BY captured_at",
                (portal.portal_key,),
            )
            descriptions = [row[0] for row in cursor.fetchall()]
    assert descriptions[0] is None
    assert "New AI report" in descriptions[1]

    queue(changed, at + dt.timedelta(hours=1))
    rerun = runtime._sync_source_portals(state, config, hub_url)
    assert rerun["status"] == "succeeded", rerun["errors"]
    assert state["pending_source_portal_captures"] == []
    for target_url in target_urls.values():
        card = next(
            c
            for c in list_source_portals(db_path=target_url)["portals"]
            if c["portal_key"] == portal.portal_key
        )
        assert len(card["updates"]) == 1
        assert "New AI report" in card["updates"][0]["description_en"]


def test_ai_resources_shared_href_keeps_each_label_and_projects_both_changes(
    tmp_path: Path, monkeypatch
) -> None:
    from ai_actuarial.api.services.read import list_source_portals
    from ai_actuarial.local_collection_target_worker import apply_source_portals
    from ai_actuarial.storage import Storage

    hub_url, schema = _database_schema(tmp_path, "soa-ai-shared-href")
    apply_content_hub_schema(hub_url, schema=schema)
    targets = {
        name: uninitialized_postgres_url_for_path(tmp_path / f"shared-href-{name}.db")
        for name in ("china", "overseas")
    }
    portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    at = dt.datetime(2026, 11, 20, 10, tzinfo=ZoneInfo("America/New_York"))

    def page(labels, pd_edge_href="/prof-dev/pd-edge/"):
        return (
            '<section class="nextsteps-block">'
            + "".join(
                f'<a href="{pd_edge_href if label == "PD Edge +" else "/prof-dev/pd-edge/"}">{label}</a>'
                for label in labels
            )
            + "</section>"
        ).encode()

    state: dict = {}
    sent: list[tuple[str, int]] = []

    def stream(_config, target, updates):
        sent.append((target, len(updates)))
        return apply_source_portals(
            {"target": target, "cards": runtime.source_portal_cards(), "updates": updates},
            storage_factory=lambda: Storage(targets[target]),
        )

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    config = {"targets": {name: {"host": name} for name in targets}}

    def capture(labels, when, pd_edge_href="/prof-dev/pd-edge/"):
        body = page(labels, pd_edge_href)
        observed = runtime._source_portal_observation(portal, portal.url, body, when)
        assert observed["complete"] is True
        record = content_hub_record_source_portal_capture(
            portal_key=portal.portal_key,
            page_url=portal.url,
            scope_key=portal.scope_key,
            captured_at=when,
            acquired_on=when.date(),
            page_sha256=observed["page_sha256"],
            entries=observed["entries"],
            complete=True,
            intro_zh=portal.overview_zh,
            intro_en=portal.overview_en,
            database_url=hub_url,
            schema=schema,
        )
        runtime._queue_source_portal_update(
            state.setdefault("pending_source_portal_publications", {}), portal.portal_key, record
        )
        assert runtime._sync_source_portals(state, config, hub_url)["status"] == "succeeded"
        return observed, record

    baseline, first = capture(["PD Edge +", "AI Insights Symposium"], at)
    assert len(baseline["entries"]) == 2
    assert first["description_en"] is None
    with psycopg2.connect(hub_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT title FROM source_portal_entries WHERE capture_id = %s AND entry_url = %s",
                (first["capture_id"], "https://www.soa.org/prof-dev/pd-edge/"),
            )
            assert json.loads(cursor.fetchone()[0]) == ["AI Insights Symposium", "PD Edge +"]
    removed, second = capture(["AI Insights Symposium"], at + dt.timedelta(days=1))
    assert len(removed["entries"]) == 1
    assert "PD Edge +" in second["description_en"]
    assert "no longer lists" in second["description_en"]
    _, third = capture(["PD Edge +", "AI Insights Symposium"], at + dt.timedelta(days=2))
    assert "PD Edge +" in third["description_en"]
    assert "now includes" in third["description_en"]
    _, moved = capture(
        ["PD Edge +", "AI Insights Symposium"],
        at + dt.timedelta(days=3),
        pd_edge_href="/prof-dev/pd-edge-new/",
    )
    assert "PD Edge +" in moved["description_en"]
    assert "now includes" in moved["description_en"]
    assert "no longer lists" in moved["description_en"]
    assert [item for item in sent if item[1]] == [
        ("china", 1),
        ("overseas", 1),
        ("china", 1),
        ("overseas", 1),
        ("china", 1),
        ("overseas", 1),
    ]
    _, replay = capture(
        ["PD Edge +", "AI Insights Symposium"],
        at + dt.timedelta(days=3),
        pd_edge_href="/prof-dev/pd-edge-new/",
    )
    assert replay["duplicate"] is True
    for url in targets.values():
        card = next(
            item
            for item in list_source_portals(db_path=url)["portals"]
            if item["portal_key"] == portal.portal_key
        )
        assert len(card["updates"]) == 3
        assert all("PD Edge +" in item["description_en"] for item in card["updates"])


def test_portal_parser_uses_only_main_entries_and_marks_partial_sections() -> None:
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    page = (
        '<nav><a href="/research/nav-report">Navigation research</a></nav>'
        "<main><h1>Research directory</h1>"
        '<a href="/research/ai-pricing-paper">AI pricing paper</a></main>'
        '<footer><a href="/research/footer-report">Footer research</a></footer>'
    ).encode()
    captured_at = dt.datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York"))
    observation = runtime._source_portal_observation(portal, portal.url, page, captured_at)
    assert observation["complete"] is True
    assert observation["entries"] == [
        {"url": "https://www.soa.org/research/ai-pricing-paper", "title": "AI pricing paper"}
    ]

    paginated = page.replace(
        b"</main>",
        b'<a class="next page-numbers" href="?page=2">\xe2\x80\xba</a></main>',
    )
    incomplete = runtime._source_portal_observation(portal, portal.url, paginated, captured_at)
    assert incomplete["complete"] is False
    assert all("page=2" not in entry["url"] for entry in incomplete["entries"])
    truncated = runtime._source_portal_observation(
        portal,
        portal.url,
        b'<main><a href="/research/ai-pricing-paper">AI pricing paper</a>',
        captured_at,
    )
    assert truncated["entries"] == observation["entries"]
    assert truncated["complete"] is False
    no_semantic_section = runtime._source_portal_observation(
        portal,
        portal.url,
        b'<div><a href="/research/ai-paper">AI research paper</a></div>',
        captured_at,
    )
    assert no_semantic_section["complete"] is False


def test_portal_parser_excludes_nested_navigation_and_uses_fixed_portal_policy() -> None:
    captured_at = dt.datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York"))
    topics = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    nested_navigation = (
        "<main><nav><a href='/research/breadcrumb'>Research home</a></nav>"
        "<section></section></main>"
    ).encode()
    empty = runtime._source_portal_observation(topics, topics.url, nested_navigation, captured_at)
    assert empty["entries"] == []
    assert empty["complete"] is False

    page = (
        "<main><nav><a href='/research/breadcrumb'>Research home</a></nav>"
        "<section><a href='/research/ai-pricing-paper'>AI pricing paper</a></section>"
        "<footer><a href='/research/footer-paper'>Footer paper</a></footer></main>"
    ).encode()
    observed = runtime._source_portal_observation(topics, topics.url, page, captured_at)
    assert observed["complete"] is True
    assert observed["entries"] == [
        {"url": "https://www.soa.org/research/ai-pricing-paper", "title": "AI pricing paper"}
    ]

    ai_portal = SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"]
    ai_body = (
        "<section class='nextsteps-block'>"
        "<a href='/research/topics/ai-newsletter'>AI newsletter</a>"
        "<a href='/research/topics/ai-governance-paper'>AI governance paper</a>"
        "<a href='/research/topics/ai-study'>AI study</a>"
        "</section>"
    ).encode()
    ai_observation = runtime._source_portal_observation(
        ai_portal, ai_portal.url, ai_body, captured_at
    )
    assert ai_observation["complete"] is True
    assert [entry["title"] for entry in ai_observation["entries"]] == [
        "AI governance paper",
        "AI newsletter",
        "AI study",
    ]


def test_portal_parser_preserves_long_title_through_hub_member_evidence(tmp_path: Path) -> None:
    hub_url, schema = _database_schema(tmp_path, "source-portal-long-parser-title")
    apply_content_hub_schema(hub_url, schema=schema)
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    title = ("Long actuarial research title " + ("Evidence " * 30)).strip()
    captured_at = dt.datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York"))
    body = ("<main><a href='/research/long-title-paper'>" + title + "</a></main>").encode()
    observation = runtime._source_portal_observation(portal, portal.url, body, captured_at)
    assert observation["entries"] == [
        {"url": "https://www.soa.org/research/long-title-paper", "title": title}
    ]

    record = content_hub_record_source_portal_capture(
        portal_key=portal.portal_key,
        page_url=observation["page_url"],
        scope_key=observation["scope_key"],
        captured_at=observation["captured_at"],
        acquired_on=observation["acquired_on"],
        page_sha256=observation["page_sha256"],
        entries=observation["entries"],
        complete=observation["complete"],
        intro_zh=portal.overview_zh,
        intro_en=portal.overview_en,
        database_url=hub_url,
        schema=schema,
    )
    persisted = content_hub_read_source_portal_capture(
        portal_key=portal.portal_key,
        capture_id=record["capture_id"],
        database_url=hub_url,
        schema=schema,
    )
    assert persisted["complete"] is True
    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT title FROM source_portal_entries WHERE capture_id = %s",
                (record["capture_id"],),
            )
            stored_title = cursor.fetchone()[0]
    finally:
        connection.close()
    assert stored_title == title


@pytest.mark.parametrize(
    ("control", "expected_complete"),
    [
        ('<button class="load-more">Load more</button>', False),
        ("<button>Load more</button>", False),
        ('<button aria-label="Load more">More</button>', False),
        ('<nav class="pagination"><a href="?page=1">1</a><a href="?page=2">2</a></nav>', False),
        ('<a aria-label="Next page" href="?page=2">›</a>', False),
        ('<a rel="next" href="?page=2">Next</a>', False),
        ("<button>Subscribe</button>", True),
    ],
)
def test_portal_pagination_signals_exclude_controls_but_keep_ordinary_entries(
    control: str, expected_complete: bool
) -> None:
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    body = (
        '<main><a href="/research/ai-pricing-paper">AI pricing paper</a>' f"{control}</main>"
    ).encode()

    observation = runtime._source_portal_observation(
        portal,
        portal.url,
        body,
        dt.datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York")),
    )

    assert observation["complete"] is expected_complete
    assert observation["entries"] == [
        {"url": "https://www.soa.org/research/ai-pricing-paper", "title": "AI pricing paper"}
    ]


def test_collection_refreshes_visited_portal_root_without_classifying_it_as_an_article(
    tmp_path: Path, monkeypatch
) -> None:
    portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    site = runtime.SITES["cia-ica"]
    body = b"<html><main><h1>Publications</h1></main></html>"

    class PortalCrawler:
        site_attempts = 0
        site_budget = 1
        caa_cookie = None
        algolia_key = None
        requests: list[str] = []

        def begin_site(self, budget: int) -> None:
            self.site_budget = budget

        def _request(self, url: str, **_kwargs):
            self.site_attempts += 1
            self.requests.append(url)
            if "/wp-json/wp/v2/news" in url:
                return b"[]", {"content-type": "application/json"}, url
            return body, {"content-type": "text/html"}, url

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    prior_documents = [
        {
            "url": f"https://www.cia-ica.ca/public-research/report-{index}.pdf",
            "kind": "document",
            "depth": 1,
            "title": f"Research report {index}",
            "referrer": portal.url,
        }
        for index in range(35)
    ]
    site_state = {
        "queue": prior_documents,
        "cursor": 0,
        "visited": [runtime._queue_identity({"url": portal.url, "kind": "page"})],
    }
    state = {"articles": {}, "sites": {site.site_id: site_state}}
    crawler = PortalCrawler()

    result = runtime._capture(
        site,
        state,
        crawler,
        tmp_path / "data",
        site_state,
        request_limit=2,
        refresh_portal_roots=True,
    )

    assert result["request_count"] == 2
    assert result["portal_captures"], (result["errors"], site_state)
    assert result["portal_captures"][0]["portal_key"] == portal.portal_key
    assert result["portal_captures"][0]["page_sha256"] == hashlib.sha256(body).hexdigest()
    assert result["downloads"] == []
    assert "/wp-json/wp/v2/news" in crawler.requests[0]
    assert crawler.requests[1] == portal.capture_urls[0]
    assert result["portal_captures"][0]["page_url"] == portal.capture_urls[0]


def test_ordinary_standalone_html_remains_a_captured_material(tmp_path: Path, monkeypatch) -> None:
    site = runtime.SITES["soa"]
    article_url = "https://www.soa.org/research/ordinary-html-research-paper/"

    class ArticleCrawler:
        site_attempts = 0
        site_budget = 1
        caa_cookie = None
        algolia_key = None

        def begin_site(self, budget: int) -> None:
            self.site_budget = budget

        def _request(self, url: str, **_kwargs):
            self.site_attempts += 1
            return (
                b"<html><article><h1>Ordinary HTML paper</h1><p>Research details.</p></article></html>",
                {"content-type": "text/html"},
                url,
            )

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", tmp_path / "runtime-state.json")
    monkeypatch.setattr(runtime, "_relevant_page", lambda _url, _label, _site: True)
    monkeypatch.setattr(
        runtime.WebPageCollector,
        "_extract_text",
        lambda *_args: "Actuarial research material. " * 10,
    )
    state = {"articles": {}}
    site_state: dict = {}
    result = runtime._capture(
        site,
        state,
        ArticleCrawler(),
        tmp_path / "data",
        site_state,
        initial_frontier=[{"url": article_url, "kind": "page", "depth": 1}],
        request_limit=1,
    )

    assert result["errors"] == [], result["errors"]
    assert len(result["downloads"]) == 1
    assert result["downloads"][0]["url"] == article_url
    assert result["downloads"][0]["detected_kind"] == "html"
    assert result["portal_captures"] == []


def test_hub_portal_captures_are_append_only_idempotent_and_compare_only_complete_same_scope(
    tmp_path: Path,
) -> None:
    hub_url, schema = _database_schema(tmp_path, "source-portal-hub")
    apply_content_hub_schema(hub_url, schema=schema)
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    first_time = dt.datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York"))
    first_entries = [{"url": "https://www.soa.org/research/ai-paper", "title": "AI paper"}]

    def record(
        acquired_at: dt.datetime,
        page: bytes,
        entries: list[dict[str, str]],
        *,
        complete: bool = True,
    ) -> dict:
        return content_hub_record_source_portal_capture(
            portal_key=portal.portal_key,
            page_url=portal.url,
            scope_key=portal.scope_key,
            captured_at=acquired_at,
            acquired_on=acquired_at.date(),
            page_sha256=hashlib.sha256(page).hexdigest(),
            entries=entries,
            complete=complete,
            intro_zh=portal.overview_zh,
            intro_en=portal.overview_en,
            database_url=hub_url,
            schema=schema,
        )

    first = record(first_time, b"first page", first_entries)
    assert first["acquired_on"] == "2026-10-31"
    assert "这里可以找到" in first["description_zh"]
    same_day_retry = record(first_time, b"first page", first_entries)
    assert same_day_retry["duplicate"] is True
    assert same_day_retry["capture_id"] == first["capture_id"]
    with pytest.raises(ContentHubError, match="immutable acquisition evidence"):
        record(
            first_time,
            b"first page",
            [{"url": "https://www.soa.org/research/other-paper", "title": "Other paper"}],
        )

    next_time = dt.datetime(2026, 11, 1, 12, tzinfo=ZoneInfo("America/New_York"))
    second_entries = first_entries + [
        {"url": "https://www.soa.org/research/new-paper", "title": "New paper"}
    ]
    second = record(next_time, b"second page", second_entries)
    assert second["acquired_on"] == "2026-11-01"
    assert "这次多了" in second["description_zh"]
    changed_same_day = record(
        next_time + dt.timedelta(hours=3),
        b"second page changed",
        second_entries
        + [{"url": "https://www.soa.org/research/new-paper-two", "title": "New paper two"}],
    )
    assert "New paper" in changed_same_day["description_en"]
    assert len(changed_same_day["description_en"]) <= 2000
    final_a = record(next_time + dt.timedelta(hours=6), b"first page", first_entries)
    assert final_a["duplicate"] is False
    assert final_a["capture_id"] > changed_same_day["capture_id"]

    next_day = record(
        next_time + dt.timedelta(days=1),
        b"third page",
        first_entries + [{"url": "https://www.soa.org/research/c-next", "title": "C next"}],
    )
    assert "C next" in next_day["description_en"]
    assert "New paper" not in next_day["description_en"]
    assert "New paper two" not in next_day["description_en"]
    truncated_body = b'<main><a href="/research/ai-paper">AI paper</a>'
    truncated_observation = runtime._source_portal_observation(
        portal,
        portal.url,
        truncated_body,
        next_time + dt.timedelta(days=2),
    )
    assert truncated_observation["complete"] is False
    assert truncated_observation["entries"] == first_entries
    partial = record(
        next_time + dt.timedelta(days=2),
        truncated_body,
        truncated_observation["entries"],
        complete=truncated_observation["complete"],
    )
    assert partial["description_zh"] is None
    assert partial["description_en"] is None
    load_more_body = (
        b'<main><a href="/research/ai-paper">AI paper</a>'
        b'<button class="load-more">Load more</button></main>'
    )
    load_more_observation = runtime._source_portal_observation(
        portal,
        portal.url,
        load_more_body,
        next_time + dt.timedelta(days=2, hours=1),
    )
    assert load_more_observation["complete"] is False
    assert load_more_observation["entries"] == first_entries
    load_more_partial = record(
        next_time + dt.timedelta(days=2, hours=1),
        load_more_body,
        load_more_observation["entries"],
        complete=load_more_observation["complete"],
    )
    assert load_more_partial["description_zh"] is None
    assert load_more_partial["description_en"] is None
    complete_after_partial = record(next_time + dt.timedelta(days=3), b"fourth page", first_entries)
    assert "这次没有列在入口中" in complete_after_partial["description_zh"]
    assert "C next" in complete_after_partial["description_en"]
    nav_only_body = b"<main><nav><a href='/research/'>Research</a></nav><section></section></main>"
    nav_only = runtime._source_portal_observation(
        portal, portal.url, nav_only_body, next_time + dt.timedelta(days=4)
    )
    assert nav_only["entries"] == []
    assert nav_only["complete"] is False
    nav_only_record = record(
        next_time + dt.timedelta(days=4),
        nav_only_body,
        nav_only["entries"],
        complete=nav_only["complete"],
    )
    assert nav_only_record["description_zh"] is None
    assert nav_only_record["description_en"] is None

    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute("SELECT count(*) FROM source_portal_captures")
            assert cursor.fetchone()[0] == 9
            cursor.execute(
                "SELECT count(*) FROM source_portal_entries WHERE capture_id = %s",
                (partial["capture_id"],),
            )
            assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def test_hub_baseline_uses_actual_capture_time_when_persistence_is_out_of_order(
    tmp_path: Path,
) -> None:
    hub_url, schema = _database_schema(tmp_path, "source-portal-out-of-order-hub")
    apply_content_hub_schema(hub_url, schema=schema)
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    earlier_time = dt.datetime(2026, 10, 31, 13, tzinfo=ZoneInfo("America/New_York"))
    later_time = earlier_time + dt.timedelta(hours=1)
    earlier_entries = [{"url": "https://www.soa.org/research/earlier", "title": "Earlier"}]
    later_entries = [{"url": "https://www.soa.org/research/later", "title": "Later"}]

    def record(at: dt.datetime, page: bytes, entries: list[dict[str, str]]) -> dict:
        return content_hub_record_source_portal_capture(
            portal_key=portal.portal_key,
            page_url=portal.url,
            scope_key=portal.scope_key,
            captured_at=at,
            acquired_on=at.date(),
            page_sha256=hashlib.sha256(page).hexdigest(),
            entries=entries,
            complete=True,
            intro_zh=portal.overview_zh,
            intro_en=portal.overview_en,
            database_url=hub_url,
            schema=schema,
        )

    later_persisted_first = record(later_time, b"later acquisition", later_entries)
    earlier_persisted_second = record(earlier_time, b"earlier acquisition", earlier_entries)
    assert later_persisted_first["capture_id"] < earlier_persisted_second["capture_id"]

    next_date = record(
        later_time + dt.timedelta(days=1),
        b"next date",
        later_entries + [{"url": "https://www.soa.org/research/new", "title": "New"}],
    )
    assert "New" in next_date["description_en"]
    assert "Earlier" not in next_date["description_en"]
    assert "no longer lists" not in next_date["description_en"]


def test_portal_descriptions_fit_transport_limit_and_keep_full_member_evidence(
    tmp_path: Path,
) -> None:
    hub_url, schema = _database_schema(tmp_path, "source-portal-long-titles")
    apply_content_hub_schema(hub_url, schema=schema)
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    previous_entries = [
        {"url": "https://www.soa.org/research/unchanged", "title": "Unchanged"},
        *[
            {
                "url": f"https://www.soa.org/research/rename-{index}",
                "title": f"Old renamed title {index} " + ("A" * 210),
            }
            for index in range(3)
        ],
        *[
            {
                "url": f"https://www.soa.org/research/removed-{index}",
                "title": f"Removed title {index} " + ("B" * 210),
            }
            for index in range(3)
        ],
    ]
    current_entries = [
        {"url": "https://www.soa.org/research/unchanged", "title": "Unchanged"},
        *[
            {
                "url": f"https://www.soa.org/research/rename-{index}",
                "title": f"New renamed title {index} " + ("C" * 210),
            }
            for index in range(3)
        ],
        *[
            {
                "url": f"https://www.soa.org/research/added-{index}",
                "title": f"Added title {index} " + ("D" * 210),
            }
            for index in range(3)
        ],
    ]

    def record(at: dt.datetime, page: bytes, entries: list[dict[str, str]]) -> dict:
        return content_hub_record_source_portal_capture(
            portal_key=portal.portal_key,
            page_url=portal.url,
            scope_key=portal.scope_key,
            captured_at=at,
            acquired_on=at.date(),
            page_sha256=hashlib.sha256(page).hexdigest(),
            entries=entries,
            complete=True,
            intro_zh=portal.overview_zh,
            intro_en=portal.overview_en,
            database_url=hub_url,
            schema=schema,
        )

    first_time = dt.datetime(2026, 10, 30, 12, tzinfo=ZoneInfo("America/New_York"))
    current_time = first_time + dt.timedelta(days=1)
    record(first_time, b"previous page", previous_entries)
    current = record(current_time, b"current page", current_entries)

    assert "这次多了" in current["description_zh"]
    assert "现在以" in current["description_zh"]
    assert "没有列在入口中" in current["description_zh"]
    assert "includes" in current["description_en"]
    assert "is now listed as" in current["description_en"]
    assert "no longer lists" in current["description_en"]
    assert len(current["description_zh"]) <= 2000
    assert len(current["description_en"]) <= 2000

    connection = psycopg2.connect(hub_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.execute(
                "SELECT title FROM source_portal_entries WHERE capture_id = %s "
                "AND entry_url = %s",
                (current["capture_id"], "https://www.soa.org/research/added-0"),
            )
            full_title = cursor.fetchone()[0]
    finally:
        connection.close()
    assert len(full_title) == len(current_entries[-3]["title"])


def test_pending_portal_projection_uses_capture_time_when_persistence_is_out_of_order(
    tmp_path: Path, monkeypatch
) -> None:
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    captures = []
    for label, captured_at in (
        ("newer", "2026-10-31T14:00:00-04:00"),
        ("older", "2026-10-31T13:00:00-04:00"),
    ):
        raw = f"<main>{label}</main>".encode()
        path = tmp_path / f"{label}.html"
        path.write_bytes(raw)
        captures.append(
            {
                "portal_key": portal.portal_key,
                "page_url": portal.url,
                "scope_key": portal.scope_key,
                "captured_at": captured_at,
                "acquired_on": "2026-10-31",
                "page_sha256": hashlib.sha256(raw).hexdigest(),
                "entries": [{"url": f"https://www.soa.org/research/{label}", "title": label}],
                "complete": True,
                "artifact_path": str(path),
            }
        )

    def record_capture(**values):
        newer = values["captured_at"].endswith("14:00:00-04:00")
        return {
            "capture_id": 10 if newer else 20,
            "captured_at": values["captured_at"],
            "acquired_on": "2026-10-31",
            "description_zh": "较新的观察。" if newer else "较早的观察。",
            "description_en": "Newer observation." if newer else "Older observation.",
        }

    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "content_hub_record_source_portal_capture", record_capture)
    streamed: list[dict] = []

    def stream(config, target, updates):
        streamed.append({"target": target, "updates": updates})
        return {"failures": []}

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    state = {"pending_source_portal_captures": captures}
    config = {"targets": {"china": {"host": "china"}, "overseas": {"host": "overseas"}}}

    result = runtime._sync_source_portals(state, config, object())

    assert result["status"] == "succeeded"
    assert result["captures_persisted"] == 2
    assert len(streamed) == 2
    for target_batch in streamed:
        [update] = target_batch["updates"]
        assert update["capture_id"] == 10
        assert update["captured_at"] == "2026-10-31T14:00:00-04:00"
        assert update["description_en"] == "Newer observation."


def test_legacy_pending_portal_updates_backfill_only_from_matching_hub_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    hub_url, schema = _database_schema(tmp_path, "source-portal-legacy-pending")
    apply_content_hub_schema(hub_url, schema=schema)
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    captured_at = dt.datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York"))
    capture = content_hub_record_source_portal_capture(
        portal_key=portal.portal_key,
        page_url=portal.url,
        scope_key=portal.scope_key,
        captured_at=captured_at,
        acquired_on=captured_at.date(),
        page_sha256=hashlib.sha256(b"saved legacy capture").hexdigest(),
        entries=[{"url": "https://www.soa.org/research/saved", "title": "Saved research"}],
        complete=True,
        intro_zh=portal.overview_zh,
        intro_en=portal.overview_en,
        database_url=hub_url,
        schema=schema,
    )
    missing_portal = SOURCE_PORTALS_BY_KEY["cia-publications"]
    acquired_on = "2026-10-31"
    valid_key = f"{portal.portal_key}|{acquired_on}"
    missing_key = f"{missing_portal.portal_key}|{acquired_on}"
    pending_updates = {
        valid_key: {
            "portal_key": portal.portal_key,
            "capture_id": capture["capture_id"],
            "acquired_on": acquired_on,
            "description_zh": capture["description_zh"],
            "description_en": capture["description_en"],
        },
        missing_key: {
            "portal_key": missing_portal.portal_key,
            "capture_id": capture["capture_id"] + 1000,
            "acquired_on": acquired_on,
            "description_zh": "已保存但缺少来源证据。",
            "description_en": "Saved without matching source evidence.",
        },
    }
    state_path = tmp_path / "runtime-state.json"
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", state_path)

    def read_capture(*, portal_key, capture_id, database_url):
        return content_hub_read_source_portal_capture(
            portal_key=portal_key,
            capture_id=capture_id,
            database_url=hub_url,
            schema=schema,
        )

    monkeypatch.setattr(runtime, "content_hub_read_source_portal_capture", read_capture)
    streamed: list[dict] = []

    def stream(_config, target, updates):
        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        saved_updates = saved_state["pending_source_portal_publications"]
        assert saved_updates[valid_key]["captured_at"] == capture["captured_at"]
        assert "captured_at" not in saved_updates[missing_key]
        streamed.append({"target": target, "updates": updates})
        return {"failures": []}

    monkeypatch.setattr(runtime, "_stream_source_portals", stream)
    config = {"targets": {"china": {"host": "china"}, "overseas": {"host": "overseas"}}}
    state = {"pending_source_portal_publications": pending_updates}

    result = runtime._sync_source_portals(state, config, hub_url)

    assert result["status"] == "partial"
    assert result["updates_pending"] == 1
    assert valid_key not in state["pending_source_portal_publications"]
    assert "captured_at" not in state["pending_source_portal_publications"][missing_key]
    assert "matching Content Hub capture was not found" in result["errors"][0]
    assert len(streamed) == 2
    for target_batch in streamed:
        assert len(target_batch["updates"]) == 1
        assert target_batch["updates"][0]["capture_id"] == capture["capture_id"]
        assert target_batch["updates"][0]["captured_at"] == capture["captured_at"]


def test_source_portal_app_sync_and_database_role_filter(tmp_path: Path) -> None:
    from ai_actuarial.api.services.files_write import _query_files_for_export
    from ai_actuarial.api.services.read import (
        list_categories,
        list_files,
        list_source_portals,
        list_sources,
        parse_file_list_query,
    )
    from ai_actuarial.local_collection_target_worker import apply_source_portals
    from ai_actuarial.source_portals import source_portal_cards
    from ai_actuarial.storage import Storage

    app_url = uninitialized_postgres_url_for_path(tmp_path / "source-portal-app.db")
    portal = SOURCE_PORTALS_BY_KEY["soa-research-topics"]
    update_rows = [
        {
            "portal_key": portal.portal_key,
            "capture_id": 12,
            "captured_at": "2026-10-31T16:00:00+00:00",
            "acquired_on": "2026-10-31",
            "description_zh": "本次记录了入口当前列出的内容。",
            "description_en": "This record covers the current directory entries.",
        },
        {
            "portal_key": portal.portal_key,
            "capture_id": 13,
            "captured_at": "2026-11-01T17:00:00+00:00",
            "acquired_on": "2026-11-01",
            "description_zh": "上次介绍的内容这次都还在，也没有看到新的资料。",
            "description_en": "Everything listed last time is still here, and no new materials were listed.",
        },
    ]
    payload = {
        "target": "china",
        "cards": source_portal_cards(),
        "updates": update_rows,
    }
    first_sync = apply_source_portals(payload, storage_factory=lambda: Storage(app_url))
    retry_sync = apply_source_portals(payload, storage_factory=lambda: Storage(app_url))
    assert first_sync["updates_synced"] == retry_sync["updates_synced"] == 2
    latest_same_day = {
        **update_rows[1],
        "capture_id": 14,
        "captured_at": "2026-11-01T18:00:00+00:00",
        "description_zh": "这次多了「研究新进展」，可以从入口继续阅读。",
        "description_en": "This time, “New research” was added and can be opened from the directory.",
    }
    apply_source_portals(
        {**payload, "updates": [latest_same_day]},
        storage_factory=lambda: Storage(app_url),
    )
    older_arrival = {
        **latest_same_day,
        "capture_id": 15,
        "captured_at": "2026-11-01T17:30:00+00:00",
        "description_zh": "这次多了较早到达的更新。",
        "description_en": "This older acquisition arrived later.",
    }
    apply_source_portals(
        {**payload, "updates": [older_arrival]},
        storage_factory=lambda: Storage(app_url),
    )

    storage = Storage(app_url)
    try:
        latest_row = storage._conn.execute(
            "SELECT capture_id, captured_at FROM source_portal_updates "
            "WHERE portal_key = ? AND acquired_on = ?",
            (portal.portal_key, "2026-11-01"),
        ).fetchone()
        rows = (
            (
                portal.url,
                "legacy portal directory",
                "SOA",
                "portal.html",
                "Research Portal Only",
                "Portal directory page.",
            ),
            (
                "https://www.soa.org/research/ai-pricing-study",
                "AI pricing study",
                "SOA",
                "study.html",
                "AI",
                "Standalone HTML research content.",
            ),
        )
        for url, title, source, filename, category, summary in rows:
            digest = hashlib.sha256(url.encode()).hexdigest()
            storage.insert_file(
                url=url,
                sha256=digest,
                title=title,
                source_site=source,
                source_page_url=portal.url,
                original_filename=filename,
                local_path=f"/tmp/{filename}",
                bytes=10,
                content_type="text/html",
            )
            storage.upsert_catalog_item(
                item={
                    "url": url,
                    "sha256": digest,
                    "category": category,
                    "summary": summary,
                    "keywords": ["research"],
                },
                pipeline_version="source-portals-test",
            )
    finally:
        storage.close()
    assert latest_row[0] == 14
    assert latest_row[1] == dt.datetime(2026, 11, 1, 18, tzinfo=dt.timezone.utc)

    visible = list_files(db_path=app_url, query=parse_file_list_query({}))
    assert visible["total"] == 1
    assert [row["url"] for row in visible["files"]] == [
        "https://www.soa.org/research/ai-pricing-study"
    ]
    assert list_sources(db_path=app_url)["source_options"][0]["count"] == 1
    assert list_categories(db_path=app_url, mode="used")["categories"] == ["AI"]
    storage = Storage(app_url)
    try:
        assert storage.get_file_count(exclude_urls=SOURCE_PORTAL_URLS) == 1
        exported = _query_files_for_export(
            storage, query=parse_file_list_query({}), include_deleted=False
        )
    finally:
        storage.close()
    assert [row["url"] for row in exported] == ["https://www.soa.org/research/ai-pricing-study"]

    source_portals = list_source_portals(db_path=app_url)["portals"]
    synced = next(item for item in source_portals if item["portal_key"] == portal.portal_key)
    assert [item["acquired_on"] for item in synced["updates"]] == ["2026-11-01", "2026-10-31"]
    assert "capture_id" not in synced["updates"][0]
    assert "added" in synced["updates"][0]["description_en"]
    assert "Portal directory page" not in [file["summary"] for file in visible["files"]]


def test_source_portal_worker_fails_without_reader_migration() -> None:
    from ai_actuarial.local_collection_target_worker import apply_source_portals
    from ai_actuarial.source_portals import source_portal_cards

    class MissingConnection:
        @staticmethod
        def table_exists(_table: str) -> bool:
            return False

    class MissingStorage:
        _conn = MissingConnection()
        closed = False

        def close(self) -> None:
            self.closed = True

    storage = MissingStorage()
    with pytest.raises(RuntimeError, match="migration 6"):
        apply_source_portals(
            {"target": "china", "cards": source_portal_cards(), "updates": []},
            storage_factory=lambda: storage,
        )
    assert storage.closed is True


def test_deferred_portal_projection_is_receipt_evidence_without_failing_article_work(
    tmp_path: Path, monkeypatch
) -> None:
    ordinary_url = "https://www.cia-ica.ca/research/ordinary-actuarial-paper/"
    captured = {
        "downloads": [{"url": ordinary_url}],
        "errors": [],
        "request_count": 1,
        "request_limit": 30,
        "budget_exhausted": False,
        "frontier_remaining": 0,
    }
    processed = {
        "candidate_count": 1,
        "pending_article_count": 0,
        "new_versions": 1,
        "duplicates": 0,
        "enriched": 0,
        "ai_candidates": 0,
        "article_errors": [],
        "target": {
            name: {
                "acknowledged": 0,
                "pending": 0,
                "failed": 0,
                "ready_status": "succeeded",
            }
            for name in ("china", "overseas")
        },
    }
    monkeypatch.setattr(runtime, "_ACTIVE_STATE_PATH", None)
    monkeypatch.setattr(runtime, "_new_crawler", lambda _root: object())
    monkeypatch.setattr(runtime, "_capture", lambda *_args, **_kwargs: captured)
    monkeypatch.setattr(runtime, "_process_articles", lambda *_args, **_kwargs: processed)
    monkeypatch.setattr(
        runtime,
        "_stream_source_portals",
        lambda *_args, **_kwargs: pytest.fail(
            "portal updates must not be sent without both targets"
        ),
    )
    saved_receipt: dict[str, object] = {}

    def save_receipt(_root, _date, _site, stages, evidence, reason, _telemetry=None):
        saved_receipt.update(stages=stages, evidence=evidence, reason=reason)
        return saved_receipt

    monkeypatch.setattr(runtime, "_write_receipt", save_receipt)

    state = {
        "sites": {},
        "articles": {},
        "target_acks": {},
        "pending_source_portal_publications": {
            "soa-research-topics|2026-11-01": {
                "portal_key": "soa-research-topics",
                "capture_id": 9,
                "acquired_on": "2026-11-01",
                "description_zh": "这次多了研究论文。",
                "description_en": "The directory now includes a research paper.",
            }
        },
    }
    config = {
        "state_root": str(tmp_path),
        "receipts_root": str(tmp_path / "receipts"),
        "data_root": str(tmp_path / "data"),
        "targets": {"china": {"host": "reader.example.cn"}},
    }

    result = runtime._run_site("cia-ica", "2026-11-01", config, state, "unused-hub")

    assert result["stages"]["downloaded"]["status"] == "succeeded"
    assert result["stages"]["new_versions"]["status"] == "succeeded"
    portal_evidence = next(
        item
        for item in saved_receipt["evidence"]
        if "Source portal reader projection is deferred" in item
    )
    assert "1 update(s) remain pending" in portal_evidence
    assert "overseas" in portal_evidence
    assert "no serving target received them" in portal_evidence

"""Issue #478 built-in skill contracts and current-data adapters."""

from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from ai_actuarial.agent_runtime import Registry
from ai_actuarial.assistant.help import load_help_sections
from ai_actuarial.skills.document_research.manifest import MANIFEST as RESEARCH
from ai_actuarial.skills.feedback import executors as feedback
from ai_actuarial.skills.feedback.manifest import MANIFEST as FEEDBACK
from ai_actuarial.skills.resources_updates import executors as resources
from ai_actuarial.skills.resources_updates.manifest import MANIFEST as RESOURCES
from ai_actuarial.skills.usage_navigation import executors as usage
from ai_actuarial.skills.usage_navigation.manifest import MANIFEST as USAGE
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path


def test_four_packages_are_independent_and_disable_separately():
    skills = (USAGE, RESOURCES, RESEARCH, FEEDBACK)
    executors = frozenset(tool.executor for skill in skills for tool in skill.tools)
    registry = Registry(skills, executors)
    assert {item["skill_id"] for item in registry.descriptions()} == {
        "usage_navigation",
        "resources_updates",
        "document_research",
        "feedback",
    }
    disabled = Registry((USAGE, replace(RESOURCES, enabled=False), RESEARCH, FEEDBACK), executors)
    assert "resources_updates" not in {item["skill_id"] for item in disabled.descriptions()}
    assert disabled.tool("document_research", "document_research.find_documents")


def test_usage_weekly_returns_exact_current_reference_and_action():
    result = usage.guide({"query": "How do I use the weekly report?", "language": "en"})
    weekly = next(
        item
        for item in result.data["sections"]
        if item["reference"]["section_id"] == "weekly-reports"
    )
    reference = weekly["reference"]
    assert weekly["action"] == "/weekly"
    assert urlsplit(weekly["link"]).path == "/api/assistant/help/section"
    assert parse_qs(urlsplit(weekly["link"]).query)["content_hash"] == [reference["content_hash"]]
    current = next(
        item
        for item in load_help_sections()
        if item.doc_id == reference["doc_id"] and item.section_id == reference["section_id"]
    )
    assert current.content_hash == reference["content_hash"]
    assert "published" in weekly["content"]


def test_usage_weekly_updates_phrase_finds_weekly_action():
    result = usage.guide({"query": "How do I view weekly updates?", "language": "en"})
    assert any(item["action"] == "/weekly" for item in result.data["sections"])


def test_recent_can_filter_source_outside_global_top_three():
    assert RESOURCES.tools[1].arguments.model_validate({"source": "SOA"}).source == "SOA"

    class Storage:
        def query_files_with_catalog(self, **kwargs):
            if kwargs.get("source") == "SOA":
                return (
                    [
                        {
                            "title": "SOA report",
                            "url": "https://soa.example/report",
                            "source_name_en": "SOA",
                            "first_seen": "2026-10-01",
                        }
                    ],
                    1,
                )
            return ([{"title": f"CAS {i}", "url": f"https://cas.example/{i}"} for i in range(3)], 3)

    result = resources.recent(SimpleNamespace(storage=Storage()), {"source": "SOA"})
    assert result.data["total"] == 1
    assert result.data["source_filter"] == "SOA"
    assert result.data["files"][0]["source"] == "SOA"


def test_catalog_search_matches_public_metadata_but_not_raw_markdown(tmp_path):
    url = "https://example.test/report.pdf"
    body_only = "body-only-search-needle"
    storage = Storage(postgres_url_for_path(tmp_path / "db"))
    try:
        storage.insert_file(
            url=url,
            sha256="catalog-test",
            title="Public Report",
            source_site="example.test",
            source_page_url=url,
            original_filename="public-report.pdf",
            local_path=str(tmp_path / "report.pdf"),
            bytes=100,
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            {
                "url": url,
                "sha256": "catalog-test",
                "keywords": ["metadata test"],
                "summary": "Public summary for catalog search.",
                "category": "Testing",
            },
            pipeline_version="test",
        )
        storage.update_file_markdown(url, f"Body text contains {body_only} only.")

        assert storage.query_files_with_catalog(query=body_only)[1] == 1
        body_result = resources.catalog_search(
            SimpleNamespace(storage=storage), {"query": body_only}
        )
        assert body_result.status == "not_found" and body_result.data["total"] == 0

        metadata_result = resources.catalog_search(
            SimpleNamespace(storage=storage), {"query": "Public summary"}
        )
        assert metadata_result.status == "ok" and metadata_result.data["total"] == 1
        assert metadata_result.data["files"][0]["title"] == "Public Report"
    finally:
        storage.close()


@pytest.mark.parametrize("count,locale", [(13, "en"), (13, "zh"), (2, "en")])
def test_source_list_discloses_truncation_and_full_portal(count, locale):
    options = [
        {
            "source_key": f"source-{i}",
            "source_name_en": f"Source {i}",
            "source_name_zh": f"来源 {i}",
            "count": 1,
        }
        for i in range(count)
    ]
    facade = SimpleNamespace(storage=SimpleNamespace(get_source_options=lambda **_: options))
    result = resources.sources(facade, {})
    answer = resources.grounded_answer("resources_updates.sources", result.data, locale)
    assert result.data["total"] == count
    assert len(result.data["sources"]) == min(count, 12)
    if count > 12:
        assert "12" in answer and "13" in answer
        assert "](/source-portals)" in answer
    else:
        assert "Source 1" in answer
        assert "](/source-portals)" not in answer


def test_resources_use_current_source_catalog_and_weekly_snapshot():
    calls = []

    class Storage:
        def get_source_options(self, **kwargs):
            calls.append(("sources", kwargs))
            return [
                {
                    "source_key": "soa",
                    "source_name_en": "SOA",
                    "source_name_zh": "北美精算师协会",
                    "count": 2,
                }
            ]

        def query_files_with_catalog(self, **kwargs):
            calls.append(("recent", kwargs))
            return (
                [
                    {
                        "title": "Survey",
                        "url": "https://soa.example/survey",
                        "source_name_en": "SOA",
                        "published_time": "2026-06-01",
                        "first_seen": "2026-07-01",
                    }
                ],
                1,
            )

        def get_latest_weekly_snapshot(self, **kwargs):
            calls.append(("weekly", kwargs))
            return {
                "id": "week-1",
                "period_start": "2026-10-26",
                "period_end": "2026-11-02",
                "file_count": 0,
            }

        def list_weekly_snapshot_files(self, **kwargs):
            calls.append(("members", kwargs))
            return [], 0

    facade = SimpleNamespace(storage=Storage())
    sources = resources.sources(facade, {})
    recent = resources.recent(facade, {})
    catalog = resources.catalog_search(facade, {"query": "Survey"})
    weekly = resources.weekly(facade, {})
    assert sources.data["sources"][0]["count"] == 2
    assert recent.data["files"][0]["first_seen"] == "2026-07-01"
    assert recent.data["date_meaning"].startswith("first_seen")
    assert catalog.data["files"][0]["source_url"] == "https://soa.example/survey"
    assert "not body evidence" in catalog.data["note"]
    assert weekly.data["action"] == "/weekly" and weekly.data["total"] == 0
    assert "No newly" in weekly.data["message"]
    assert calls[1][1]["order_by"] == "first_seen"
    assert calls[4][1]["snapshot_id"] == "week-1"


def test_resources_no_weekly_snapshot_and_feedback_draft_are_explicit():
    facade = SimpleNamespace(storage=SimpleNamespace(get_latest_weekly_snapshot=lambda **_: None))
    result = resources.weekly(facade, {})
    assert result.status == "ok" and result.data["snapshot"] is None
    assert result.data["action"] == "/weekly"
    draft = feedback.draft({"text": "Keep my exact words 中文"})
    assert draft.data == {
        "draft": "Keep my exact words 中文",
        "status": "not_submitted",
        "next_step": "Review, edit and confirm in the existing feedback form.",
    }


def test_document_dates_separate_publication_collection_membership_and_revision():
    class Connection:
        def execute(self, sql, values):
            assert "SELECT added_at FROM rag_kb_files" in sql
            assert values == ("public", "https://soa.example/survey")
            return SimpleNamespace(fetchone=lambda: ("2026-07-02",))

    document = SimpleNamespace(
        publication_date="2026-06-01",
        system_first_seen="2026-07-01",
        model_dump=lambda: {"title": "Survey"},
    )
    facade = SimpleNamespace(
        _document=lambda target: document,
        storage=SimpleNamespace(_conn=Connection()),
    )
    result = resources.document_dates(
        facade, {"kb_id": "public", "file_id": "https://soa.example/survey"}
    )
    assert result.data["publication_date"] == "2026-06-01"
    assert result.data["system_first_seen"] == "2026-07-01"
    assert result.data["kb_added_at"] == "2026-07-02"
    assert result.data["content_revision"] == "not recorded"

from __future__ import annotations

import json
import sqlite3
import time
from types import SimpleNamespace

import pytest

from ai_actuarial.agent_runtime import Registry, RunContext, ToolResult, run
from ai_actuarial.api.deps import AuthContext
from ai_actuarial.api.routers.assistant_runtime import RuntimePayload
from ai_actuarial.assistant.document_research import (
    DocumentResearch,
    SelectedTarget,
)
from ai_actuarial.skills.document_research import executors
from ai_actuarial.skills.document_research.manifest import MANIFEST, FindArgs

SURVEY = "https://www.soa.org/resources/research-reports/soa-member-ai-survey/"
BULLETIN = "https://www.soa.org/resources/bulletin/old-ai-survey/"
ASHK = "https://www.ashk.org.hk/questionnaire/"
CONTINGENCIES = "https://contingencies.org/ai-survey/"
KEY_FINDINGS = (
    "Key Findings. Members are using AI in actuarial work, while many organizations "
    "are still developing governance and training for responsible adoption."
)


def test_runtime_request_carries_only_bounded_target_ids():
    payload = RuntimePayload.model_validate(
        {
            "message": "What were its findings?",
            "selected_target": {"kb_id": "public", "file_id": SURVEY},
        }
    )
    assert payload.selected_target == SelectedTarget(kb_id="public", file_id=SURVEY)
    with pytest.raises(ValueError):
        RuntimePayload.model_validate(
            {
                "message": "follow-up",
                "selected_target": {"kb_id": "public", "file_id": SURVEY, "excerpt": "old body"},
            }
        )


class Storage:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.executescript(
            """CREATE TABLE files(url TEXT, title TEXT, published_time TEXT, first_seen TEXT, deleted_at TEXT);
            CREATE TABLE rag_kb_files(kb_id TEXT, file_url TEXT);
            CREATE TABLE rag_knowledge_bases(kb_id TEXT, manifest_profile TEXT, index_path TEXT);"""
        )
        self._conn.execute("INSERT INTO rag_knowledge_bases VALUES ('public', 'general', 'index')")
        self.rows = [
            (SURVEY, "SOA Member AI Survey: Spring 2026", "Society of Actuaries", "2026-06-01"),
            (BULLETIN, "SOA Bulletin: Old AI Survey", "Society of Actuaries", "2024-01-01"),
            (ASHK, "ASHK Member AI Questionnaire", "ASHK", "2025-01-01"),
            (CONTINGENCIES, "Contingencies AI Survey", "Contingencies", "2025-01-01"),
        ]
        for url, title, _, date in self.rows:
            self._conn.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?, NULL)",
                (url, title, None if url == SURVEY else date, "2026-07-01"),
            )
            self._conn.execute("INSERT INTO rag_kb_files VALUES ('public', ?)", (url,))

    def search_catalog_projection(self, terms, *, limit=5, kb_ids=None):
        if kb_ids is not None and "public" not in kb_ids:
            return []
        results = []
        for url, title, org, date in self.rows:
            if not terms or any(term in (title + org).casefold() for term in terms):
                results.append(
                    {
                        "file_url": url,
                        "title": title,
                        "organization": org,
                        "summary": "Survey of AI use among actuarial members",
                        "date": date,
                    }
                )
        return results[:limit]

    def close(self):
        self._conn.close()


@pytest.fixture
def research(monkeypatch):
    from ai_actuarial.agentic_rag import ready_data_tools
    from ai_actuarial.assistant import document_research

    storage = Storage()
    allowed = ["public"]
    state = {
        "ready": True,
        "stale": False,
        "severity": "none",
        "sections": [
            {
                "file_url": SURVEY,
                "section_id": "key-findings",
                "heading": "Key Findings",
                "text_snippet": KEY_FINDINGS,
            }
        ],
    }

    def snapshot(*args, **kwargs):
        return {
            "manifest": {
                "usable": state["ready"],
                "output_dir": "isolated-ready",
                "publication_id": "ready-v1",
                "index_version_id": "idx-v1",
                "serving_stale": state["stale"],
                "stale_severity": state["severity"],
                "built_at": "2026-10-01",
            }
        }

    monkeypatch.setattr(document_research, "read_public_ready_data_snapshot", snapshot)
    monkeypatch.setattr(
        ready_data_tools,
        "_load_ready_data",
        lambda output_dir: {
            "catalog": [],
            "sections_structured": [],
            "sections": [
                {
                    "doc_id": row["file_url"],
                    "file_url": row["file_url"],
                    "section_id": row.get("section_id"),
                    "text": row.get("text_snippet"),
                }
                for row in state["sections"]
            ],
        },
    )
    monkeypatch.setattr(
        ready_data_tools,
        "search_sections",
        lambda query, *, file_urls, **kwargs: [
            row for row in state["sections"] if row["file_url"] in file_urls
        ],
    )
    facade = DocumentResearch(
        storage, authorized_kbs=lambda: allowed[:], deadline=time.monotonic() + 60
    )
    yield facade, storage, allowed, state
    storage._conn.close()


@pytest.mark.parametrize(
    "query",
    [
        "SOA Member AI Survey: Spring 2026 key findings",
        "What did the latest SOA member AI survey find?",
        "请总结精算师协会会员人工智能调查的主要发现，2026年春季",
    ],
)
def test_bilingual_target_ranks_before_old_and_neighboring_reports(research, query):
    facade, _, _, _ = research
    documents = facade.find_documents(query)
    assert documents[0].target == SelectedTarget(kb_id="public", file_id=SURVEY)
    assert documents[0].publication_date is None
    assert documents[0].system_first_seen == "2026-07-01"
    assert documents[0].source_url == SURVEY


def test_exact_identifier_survives_broad_catalog_terms(research, monkeypatch):
    facade, storage, _, _ = research
    base_search = storage.search_catalog_projection
    terms_seen = []

    def search(terms, **kwargs):
        terms_seen.extend(terms)
        if "2025/1234" in terms:
            return [
                {
                    "file_url": ASHK,
                    "title": "Final instrument",
                    "summary": "Text of 2025/1234",
                }
            ]
        return base_search(terms, **kwargs)

    monkeypatch.setattr(storage, "search_catalog_projection", search)
    documents = facade.find_documents("SOA AI survey 2025/1234")
    assert "2025/1234" in terms_seen
    assert documents[0].target.file_id == ASHK


def test_body_tool_bounds_metadata_and_preserves_excerpt_ids():
    from ai_actuarial.assistant.document_research import SectionEvidence

    target = SelectedTarget(kb_id="public", file_id="https://example.test/" + "p" * 300)
    evidence = [
        SectionEvidence(
            target=target,
            section_id=f"{target.file_id}#section-{index}",
            title="Long document " + "t" * 170,
            publication_date="2025-06-20",
            excerpt="a" * 1200,
            source_url=target.file_id,
            retrieval="ready",
        )
        for index in (1, 2)
    ]
    facade = SimpleNamespace(
        read_document_sections=lambda *_args, **_kwargs: (evidence, "available")
    )
    result = executors.read_document_sections(facade, {**target.model_dump(), "query": "policy"})
    assert result.status == "ok"
    assert len(json.dumps(result.data, ensure_ascii=False)) <= 4000
    assert len(result.data["sections"]) == len(result.evidence_ids) >= 1
    assert result.data["sections"][0]["publication_date"] == "2025-06-20"
    assert result.data["sections"][0]["excerpt"] == evidence[0].excerpt


def test_topic_search_uses_current_publication_and_authorized_membership(research, monkeypatch):
    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.assistant import document_research

    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        document_research.read_public_ready_data_snapshot,
    )
    facade, _, _, state = research
    facade.config = SimpleNamespace(top_k=5)
    state["sections"] = [
        {
            "file_url": BULLETIN,
            "section_id": "historical",
            "text_snippet": "A consultation paper discussed the committee's proposal.",
        },
        {
            "file_url": SURVEY,
            "section_id": "current",
            "text_snippet": "Final instrument 2025/1234 requires documented annual review.",
        },
        {
            "file_url": "https://example.test/not-a-member",
            "section_id": "private",
            "text_snippet": "2025/1234 requires something different.",
        },
    ]
    result = executors.search_topic(facade, {"query": "final instrument 2025/1234"})
    assert result.status == "ok"
    sections = result.data["sections"]
    assert sections[0]["target"]["file_id"] == SURVEY
    assert sections[0]["section_id"] == "current"
    assert sections[0]["source_version"] == "ready-v1"
    assert all(section["section_id"] != "private" for section in sections)
    excluded = executors.search_topic(
        facade, {"query": "final instrument 2025/1234", "exclude_file_url": SURVEY}
    )
    assert all(
        section["target"]["file_id"] != SURVEY for section in excluded.data.get("sections", [])
    )
    with pytest.raises(PermissionError):
        executors.search_topic(facade, {"query": "2025/1234", "kb_id": "private"})


@pytest.mark.parametrize("bulk_in_public_kb", [False, True])
def test_scoped_catalog_keeps_old_member_ahead_of_newer_less_relevant_matches(
    tmp_path, bulk_in_public_kb
):
    from ai_actuarial.storage import Storage as DatabaseStorage
    from tests.postgres_helpers import postgres_url_for_path

    storage = DatabaseStorage(postgres_url_for_path(tmp_path / "catalog.db"))
    try:
        storage._conn.execute("""INSERT INTO rag_knowledge_bases
               (kb_id, name, embedding_model, chunk_size, chunk_overlap, index_type, created_at, updated_at)
               VALUES ('public', 'Public', 'test', 100, 0, 'test', 'now', 'now')""")
        for index, (url, title, last_seen, member) in enumerate(
            [
                (SURVEY, "SOA Member AI Survey: Spring 2026", "2000-01-01", True),
                ("https://example.org/overview", "General AI survey overview", "2099-01-01", True),
                *[
                    (
                        f"https://private.example/doc/{number}",
                        f"Private item {number}",
                        "2099-01-01",
                        bulk_in_public_kb,
                    )
                    for number in range(50)
                ],
            ]
        ):
            storage._conn.execute(
                """INSERT INTO files (url, title, original_filename, source_site, local_path, first_seen, last_seen)
                   VALUES (?, ?, ?, 'fixture', ?, '2026-01-01', ?)""",
                (url, title, f"item-{index}.md", f"/fixture/{index}.md", last_seen),
            )
            storage._conn.execute(
                """INSERT INTO catalog_items
                   (file_url, sha256, pipeline_version, summary, category, bilingual_metadata_json, catalog_version)
                   VALUES (?, 'fixture', 'fixture', 'SOA member AI survey', 'research', '{}', 'v1')""",
                (url,),
            )
            if member:
                storage._conn.execute(
                    "INSERT INTO rag_kb_files (kb_id, file_url, added_at) VALUES ('public', ?, 'now')",
                    (url,),
                )
        documents = DocumentResearch(storage, authorized_kbs=lambda: ["public"]).find_documents(
            "SOA member AI survey"
        )
        assert [item.target.file_id for item in documents[:2]] == [
            SURVEY,
            "https://example.org/overview",
        ]
        if not bulk_in_public_kb:
            assert len(documents) == 2
        assert all(item.target.kb_id == "public" for item in documents)
    finally:
        storage.close()


def test_explicit_ashk_correction_outranks_generic_soa_boost(research):
    facade, _, _, _ = research
    assert (
        facade.find_documents("I meant the ASHK member AI questionnaire")[0].target.file_id == ASHK
    )
    assert (
        facade.find_documents("Not SOA; I meant the ASHK member AI questionnaire")[0].target.file_id
        == ASHK
    )
    assert facade.find_documents("不是SOA，是ASHK问卷")[0].target.file_id == ASHK
    assert facade.find_documents("最新SOA会员AI调查")[0].target.file_id == SURVEY


@pytest.mark.parametrize(
    "query,expected",
    [
        ("I meant the old SOA Bulletin AI survey", BULLETIN),
        ("No, the old SOA Bulletin AI survey", BULLETIN),
        ("No, the old SOA Bulletin", BULLETIN),
        ("Not SOA; I meant the Contingencies AI survey", CONTINGENCIES),
    ],
)
def test_explicit_correction_ranks_requested_report_first(research, query, expected):
    facade, _, _, _ = research
    assert facade.find_documents(query)[0].target.file_id == expected


def test_exact_key_findings_ready_soft_stale_and_quote_validation(research):
    facade, _, _, state = research
    target = SelectedTarget(kb_id="public", file_id=SURVEY)
    state.update(stale=True, severity="soft_stale")
    evidence, status = facade.read_document_sections(target, query="请总结主要发现")
    assert status == "available" and len(evidence) == 1
    assert evidence[0].excerpt == KEY_FINDINGS
    assert evidence[0].source_url == SURVEY
    assert evidence[0].section_id == "key-findings"
    assert evidence[0].source_version == "ready-v1"
    assert evidence[0].serving_stale and evidence[0].stale_severity == "soft_stale"


def test_readiness_requires_sections_for_the_target(research):
    facade, storage, _, state = research
    state.update(stale=True, severity="soft_stale")
    assert (
        facade.readiness(SelectedTarget(kb_id="public", file_id=BULLETIN))["status"]
        == "standard_index_present"
    )
    storage._conn.execute("UPDATE rag_knowledge_bases SET index_path = NULL")
    survey = facade.readiness(SelectedTarget(kb_id="public", file_id=SURVEY))
    bulletin = facade.readiness(SelectedTarget(kb_id="public", file_id=BULLETIN))
    assert survey["status"] == "ready_publication_usable"
    assert survey["serving_stale"] is True and survey["stale_severity"] == "soft_stale"
    assert bulletin["status"] == "body_unavailable"
    assert facade.read_document_sections(
        SelectedTarget(kb_id="public", file_id=BULLETIN), query="Key Findings"
    ) == ([], "body_unavailable")


def test_readiness_uses_published_target_url_after_title_changes(tmp_path, monkeypatch):
    from ai_actuarial.agentic_rag.ready_data_tools import search_sections
    from ai_actuarial.assistant import document_research

    (tmp_path / "ready_data_manifest.json").write_text(
        json.dumps({"artifact_files": []}), encoding="utf-8"
    )
    (tmp_path / "doc_catalog.jsonl").write_text(
        json.dumps(
            {"doc_id": SURVEY, "file_url": SURVEY, "title": "SOA Member AI Survey: Spring 2026"}
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "sections.jsonl").write_text(
        json.dumps(
            {
                "doc_id": SURVEY,
                "file_url": SURVEY,
                "section_id": "key-findings",
                "heading": "Key Findings",
                "text": KEY_FINDINGS,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "usable": True,
        "output_dir": str(tmp_path),
        "publication_id": "ready-v1",
        "index_version_id": "idx-v1",
        "serving_stale": True,
        "stale_severity": "soft_stale",
    }
    monkeypatch.setattr(
        document_research,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {"manifest": manifest},
    )
    storage = Storage()
    try:
        storage._conn.execute(
            "UPDATE files SET title = 'Renamed Metadata Label' WHERE url = ?", (SURVEY,)
        )
        storage._conn.execute("UPDATE rag_knowledge_bases SET index_path = NULL")
        facade = DocumentResearch(storage, authorized_kbs=lambda: ["public"])
        target = SelectedTarget(kb_id="public", file_id=SURVEY)
        assert (
            search_sections(
                "Renamed Metadata Label", output_dir=tmp_path, file_urls={SURVEY}, limit=1
            )
            == []
        )
        sections, status = facade.read_document_sections(target, query="Key Findings")
        assert status == "available" and sections[0].source_url == SURVEY
        readiness = facade.readiness(target)
        assert readiness["status"] == "ready_publication_usable"
        assert readiness["serving_stale"] is True
        assert readiness["stale_severity"] == "soft_stale"
        manifest["usable"] = False
        assert facade.readiness(target)["status"] == "body_unavailable"
    finally:
        storage.close()


def test_acknowledgements_cannot_replace_key_findings(research):
    facade, _, _, state = research
    state["sections"] = [
        {
            "file_url": SURVEY,
            "section_id": "thanks",
            "heading": "Acknowledgements",
            "text_snippet": "We thank the survey team.",
        }
    ]
    facade.storage._conn.execute("UPDATE rag_knowledge_bases SET index_path = NULL")
    evidence, status = facade.search_knowledge(
        SelectedTarget(kb_id="public", file_id=SURVEY), "请总结主要发现"
    )
    assert evidence == [] and status == "body_unavailable"


def test_child_acknowledgements_under_key_findings_is_not_finding(research):
    facade, _, _, state = research
    state["sections"] = [
        {
            "file_url": SURVEY,
            "section_id": "key-findings",
            "heading": "Key Findings",
            "heading_path": ["Key Findings"],
            "text_snippet": KEY_FINDINGS,
        },
        {
            "file_url": SURVEY,
            "section_id": "acknowledgements",
            "heading": "Acknowledgements",
            "heading_path": ["Key Findings", "Acknowledgements"],
            "text_snippet": "We thank the people who supported the survey.",
        },
    ]
    evidence, status = facade.search_knowledge(
        SelectedTarget(kb_id="public", file_id=SURVEY), "请总结主要发现"
    )
    assert status == "available"
    assert [item.section_id for item in evidence] == ["key-findings"]


def test_ready_missing_target_falls_back_to_same_file_and_kb(research, monkeypatch):
    from ai_actuarial.chatbot import retrieval

    facade, _, _, state = research
    state["sections"] = [
        {
            "file_url": BULLETIN,
            "section_id": "other",
            "heading": "Key Findings",
            "text_snippet": "Old report",
        }
    ]
    calls = []

    class Retriever:
        def __init__(self, *args, **kwargs):
            self.embedding_generator = type("Embedding", (), {"openai_client": None})()

        def _get_vector_store(self, kb_id):
            calls.append(("index", kb_id))

        def retrieve(self, query, *, kb_ids, top_k, file_urls, candidate_filter=None):
            calls.append(("retrieve", kb_ids, file_urls))
            return [
                {"metadata": {"file_url": BULLETIN, "chunk_id": "wrong"}, "content": "Wrong"},
                {
                    "metadata": {
                        "file_url": SURVEY,
                        "chunk_id": "right",
                        "index_version_id": "idx-v1",
                    },
                    "content": "## Key Findings\n" + KEY_FINDINGS,
                },
            ]

    monkeypatch.setattr(retrieval, "RAGRetriever", Retriever)
    evidence, status = facade.read_document_sections(
        SelectedTarget(kb_id="public", file_id=SURVEY), query="Key Findings"
    )
    assert calls == [("index", "public"), ("retrieve", ["public"], {SURVEY})]
    assert status == "available" and [row.section_id for row in evidence] == ["right"]


@pytest.mark.parametrize(
    "content,expected",
    [
        (
            "## Acknowledgements\nThanks to contributors.\n\n## Key Findings\nMembers use AI.\n\n## Limitations\nSmall sample.",
            "## Key Findings\nMembers use AI.",
        ),
        (
            "## Key Findings\nMembers use AI.\n### Governance\nControls grow.\n## Acknowledgements\nThanks.",
            "## Key Findings\nMembers use AI.\n### Governance\nControls grow.",
        ),
        ("## Acknowledgements\nThe Key Findings section was prepared here.", None),
        ("Key Findings\nMembers use AI.", None),
        ("## Key Findings", None),
        ("```md\n## Key Findings\nFabricated.\n```\n## Acknowledgements\nThanks.", None),
        ("## Key Findings\nFirst.\n## Key Findings\nSecond.", None),
    ],
)
def test_standard_findings_require_markdown_heading_boundaries(
    research, monkeypatch, content, expected
):
    from ai_actuarial.chatbot import retrieval

    facade, _, _, state = research
    state["sections"] = []

    class Retriever:
        def __init__(self, *args, **kwargs):
            self.embedding_generator = SimpleNamespace(openai_client=None)

        def _get_vector_store(self, kb_id):
            assert kb_id == "public"

        def retrieve(self, query, *, kb_ids, top_k, file_urls, candidate_filter=None):
            assert kb_ids == ["public"] and file_urls == {SURVEY}
            return [
                {
                    "metadata": {
                        "file_url": SURVEY,
                        "chunk_id": "mixed",
                        "section_hierarchy": "Acknowledgements > Key Findings",
                    },
                    "content": content,
                }
            ]

    monkeypatch.setattr(retrieval, "RAGRetriever", Retriever)
    evidence, status = facade.read_document_sections(
        SelectedTarget(kb_id="public", file_id=SURVEY), query="Key Findings"
    )
    assert status == ("available" if expected else "body_unavailable")
    assert [item.excerpt for item in evidence] == ([expected] if expected else [])


def test_standard_findings_filter_before_five_result_budget(research, monkeypatch):
    from ai_actuarial.chatbot import retrieval

    facade, _, _, state = research
    state["sections"] = []
    rows = [
        {
            "metadata": {
                "file_url": SURVEY,
                "chunk_id": f"ack-{index}",
                "content": "## Acknowledgements\nThe Key Findings section was prepared here.",
            },
            "score": 0.9 - index * 0.01,
        }
        for index in range(5)
    ]
    rows.append(
        {
            "metadata": {
                "file_url": SURVEY,
                "chunk_id": "key-findings",
                "content": "## Key Findings\nMembers use AI in actuarial work.",
            },
            "score": 0.84,
        }
    )
    search_sizes = []
    embeddings = []
    vector_store = SimpleNamespace(
        metadata=[row["metadata"] for row in rows],
        search=lambda query_vector, *, k, similarity_threshold: (
            search_sizes.append(k) or rows[:k]
        ),
    )
    retriever = object.__new__(retrieval.RAGRetriever)
    retriever.kb_manager = SimpleNamespace(
        get_kb=lambda kb_id: SimpleNamespace(kb_id=kb_id, name="Public")
    )
    retriever.config = SimpleNamespace(top_k=5, similarity_threshold=0.5)
    retriever.embedding_generator = SimpleNamespace(
        generate_single=lambda query: embeddings.append(query) or [0.1, 0.2],
        openai_client=None,
    )
    retriever.get_current_embedding_metadata = lambda: {"provider": "test", "model": "test"}
    retriever._ensure_kb_embedding_compatibility = lambda kb, current: None
    retriever._get_vector_store = lambda kb_id: vector_store
    retriever._index_source_cache = {"public": {"index_version_id": "idx-v1"}}
    monkeypatch.setattr(retrieval, "RAGRetriever", lambda *args, **kwargs: retriever)

    evidence, status = facade.read_document_sections(
        SelectedTarget(kb_id="public", file_id=SURVEY), query="Key Findings"
    )
    assert status == "available"
    assert [item.section_id for item in evidence] == ["key-findings"]
    assert evidence[0].excerpt == "## Key Findings\nMembers use AI in actuarial work."
    assert search_sizes == [5, 6]
    assert len(embeddings) == 1


def test_hard_stale_and_missing_index_give_bounded_status(research):
    facade, storage, _, state = research
    target = SelectedTarget(kb_id="public", file_id=SURVEY)
    state.update(ready=False, severity="hard_stale")
    storage._conn.execute("UPDATE rag_knowledge_bases SET index_path = NULL")
    evidence, status = facade.read_document_sections(target, query="findings")
    assert evidence == [] and status == "body_unavailable"
    assert facade.find_documents("SOA Member AI Survey")[0].source_url == SURVEY


def test_embedding_mismatch_fails_closed_after_ready_miss(research, monkeypatch):
    from ai_actuarial.chatbot import retrieval
    from ai_actuarial.chatbot.exceptions import EmbeddingConfigurationMismatchException

    facade, _, _, state = research
    state["sections"] = []

    class Retriever:
        def __init__(self, *args, **kwargs):
            self.embedding_generator = type("Embedding", (), {"openai_client": None})()

        def _get_vector_store(self, kb_id):
            return None

        def retrieve(self, *args, **kwargs):
            raise EmbeddingConfigurationMismatchException(
                "mismatch",
                kb_id="public",
                current_provider="test",
                current_model="test",
                current_dimension=1,
                index_provider="other",
                index_model="other",
                index_dimension=2,
            )

    monkeypatch.setattr(retrieval, "RAGRetriever", Retriever)
    assert facade.search_knowledge(
        SelectedTarget(kb_id="public", file_id=SURVEY), "Key Findings"
    ) == ([], "index_mismatch")


def test_followup_rechecks_target_membership_deletion_and_allowlist(research):
    facade, storage, allowed, state = research
    target = facade.find_documents("SOA Member AI Survey: Spring 2026")[0].target
    first, _ = facade.search_knowledge(target, "Key Findings")
    state["sections"][0]["text_snippet"] = "Fresh evidence on this turn."
    second, _ = facade.search_knowledge(target, "What about its findings?")
    assert first[0].excerpt == KEY_FINDINGS
    assert second[0].excerpt == "Fresh evidence on this turn."
    assert facade.find_documents("ASHK questionnaire")[0].target.file_id == ASHK
    assert len(facade.find_documents("AI survey")) > 1
    allowed.clear()
    with pytest.raises(PermissionError):
        facade.search_knowledge(target, "findings")
    allowed.append("public")
    storage._conn.execute("DELETE FROM rag_kb_files WHERE file_url = ?", (SURVEY,))
    assert facade.search_knowledge(target, "findings") == ([], "not_found")
    storage._conn.execute("INSERT INTO rag_kb_files VALUES ('public', ?)", (SURVEY,))
    storage._conn.execute("UPDATE files SET deleted_at = 'now' WHERE url = ?", (SURVEY,))
    assert facade.search_knowledge(target, "findings") == ([], "not_found")
    with pytest.raises(PermissionError):
        facade.readiness(SelectedTarget(kb_id="staff", file_id=SURVEY))


def test_skill_contract_and_host_rejects_forged_quote(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    target = SelectedTarget(kb_id="public", file_id=SURVEY)

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    actions = iter(
        [
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.read_document_sections",
                "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
            },
            {
                "action": "finish",
                "answer": "unsupported",
                "evidence_ids": ["unused"],
                "findings": [],
            },
        ]
    )
    prompts = []

    def model(prompt, remaining):
        prompts.append(json.loads(prompt))
        action = next(actions)
        if action["action"] == "finish":
            action["evidence_ids"] = [prompts[-1]["observations"][0]["evidence_ids"][0]]
            action["findings"] = [
                {
                    "evidence_id": action["evidence_ids"][0],
                    "quote": "fabricated",
                    "summary": "伪造结论",
                }
            ]
        return json.dumps(action)

    result = run(
        message="请总结主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=execute,
        selected_target=target.model_dump(),
    )
    assert result.error_code == "NO_EVIDENCE"
    assert prompts[0]["prompt"]
    assert '"selected_target"' in prompts[0]["prompt"]


def test_skill_host_builds_chinese_answer_from_current_exact_quote(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    actions = [
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.read_document_sections",
            "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
        },
    ]

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        if actions:
            return json.dumps(actions.pop(0))
        if len(json.loads(prompt).get("items", [])) == 1:
            return json.dumps({"supported": [True]})
        identifier = json.loads(prompt)["observations"][0]["evidence_ids"][0]
        return json.dumps(
            {
                "action": "finish",
                "answer": "ignored model prose",
                "evidence_ids": [identifier],
                "findings": [
                    {
                        "evidence_id": identifier,
                        "quote": "Members are using AI in actuarial work",
                        "summary": "会员已在精算工作中使用人工智能。",
                    }
                ],
            }
        )

    result = run(
        message="请总结主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=execute,
    )
    assert result.kind == "finish"
    assert "会员已在精算工作中使用人工智能" in result.answer
    assert "Members are using AI in actuarial work" in result.answer
    assert SURVEY in result.answer
    assert "ignored model prose" not in result.answer
    assert result.model_attempts == 3


@pytest.mark.parametrize("with_readiness", [False, True])
def test_findings_route_verifies_after_optional_readiness(research, with_readiness):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    actions = [
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.find_documents",
            "args": {"query": "SOA Member AI Survey: Spring 2026"},
        },
        *(
            [
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.readiness",
                    "args": {"kb_id": "public", "file_id": SURVEY},
                }
            ]
            if with_readiness
            else []
        ),
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.read_document_sections",
            "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
        },
    ]
    verified = []

    def model(prompt, remaining):
        data = json.loads(prompt)
        if data.get("items"):
            verified.append(data["items"])
            return json.dumps({"supported": [True]})
        if actions:
            return json.dumps(actions.pop(0))
        identifier = data["observations"][-1]["evidence_ids"][0]
        return json.dumps(
            {
                "action": "finish",
                "answer": "unused",
                "evidence_ids": [identifier],
                "findings": [
                    {
                        "evidence_id": identifier,
                        "quote": "Members are using AI in actuarial work",
                        "summary": "会员正在精算工作中使用人工智能。",
                    }
                ],
            }
        )

    result = run(
        message="请总结SOA会员人工智能调查的主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(
            principal="test",
            scopes=frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
        ),
        model=model,
        execute=lambda tool, args, context, remaining: getattr(
            executors, tool.executor.split(".")[1]
        )(facade, args),
    )
    assert result.model_attempts == (5 if with_readiness else 4)
    assert result.tool_attempts == (3 if with_readiness else 2)
    assert result.availability == "available" and result.error_code is None
    assert len(verified) == 1
    assert "会员正在精算工作中使用人工智能" in result.answer
    assert "Members are using AI in actuarial work" in result.answer
    assert SURVEY in result.answer


@pytest.mark.parametrize("finding_count", [1, 2])
@pytest.mark.parametrize("recover", [False, True])
def test_guarded_single_ready_finding_uses_current_quote_and_host_source(
    research, finding_count, recover
):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    calls = []
    context = RunContext(
        principal="test",
        scopes=frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )

    def model(prompt, remaining):
        data = json.loads(prompt)
        calls.append(data)
        context.take_provider_request(prepaid=True)
        if len(calls) == 1:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "SOA Member AI Survey: Spring 2026"},
                }
            )
        if len(calls) == 2:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        if len(calls) == 3:
            assert context.reserve_verifier
            if recover:
                context.take_provider_request()
            assert set(data) == {"instruction", "question", "locale", "excerpt"}
            assert data["excerpt"] == KEY_FINDINGS and data["locale"] == "zh"
            assert "skills" not in prompt and BULLETIN not in prompt
            findings = [
                {
                    "quote": "Members are using AI in actuarial work",
                    "summary": "会员正在精算工作中使用人工智能。",
                }
            ]
            if finding_count == 2:
                findings.append(
                    {
                        "quote": "many organizations are still developing governance and training",
                        "summary": "许多机构仍在发展治理与培训。",
                    }
                )
            return json.dumps({"findings": findings})
        assert not context.reserve_verifier
        assert [item["excerpt"] for item in data["items"]] == [
            "Members are using AI in actuarial work",
            *(
                ["many organizations are still developing governance and training"]
                if finding_count == 2
                else []
            ),
        ]
        return json.dumps({"supported": [True] * finding_count})

    def resolve(target):
        document = facade._document(SelectedTarget.model_validate(target))
        return document.model_dump() if document else None

    result = run(
        message="请简要总结SOA会员人工智能调查的主要发现",
        locale="zh",
        registry=registry,
        context=context,
        model=model,
        execute=lambda tool, args, context, remaining: getattr(
            executors, tool.executor.split(".")[1]
        )(facade, args),
        resolve_selected_document=resolve,
    )
    assert result.kind == "finish" and result.availability == "available", (result, calls)
    assert result.model_attempts == 4 + int(recover) and result.tool_attempts == 2
    assert context.provider_requests == result.model_attempts
    assert len(result.evidence_ids) == 1
    assert "会员正在精算工作中使用人工智能" in result.answer
    assert "Members are using AI in actuarial work" in result.answer
    assert SURVEY in result.answer and BULLETIN not in result.answer
    if finding_count == 2:
        assert "许多机构仍在发展治理与培训" in result.answer


def test_explicit_original_quote_request_uses_current_guarded_excerpt(research):
    facade, _, _, state = research
    state["sections"][0]["section_id"] = SURVEY + "#cs_fixture:1"
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    calls = []
    observed_ids = []

    def execute(tool, args, context, remaining):
        observed = getattr(executors, tool.executor.split(".")[1])(facade, args)
        if tool.tool_id == "document_research.read_document_sections":
            observed_ids.extend(observed.evidence_ids)
        return observed

    def model(prompt, remaining):
        data = json.loads(prompt)
        calls.append(data)
        if len(calls) == 1:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "SOA Member AI Survey: Spring 2026"},
                }
            )
        if len(calls) == 2:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {
                        "kb_id": "public",
                        "file_id": SURVEY,
                        "query": "Key Findings",
                        "section": "Key Findings",
                    },
                }
            )
        if len(calls) == 3:
            if "excerpt" in data:
                assert data["excerpt"] == KEY_FINDINGS
                return json.dumps(
                    {
                        "findings": [
                            {
                                "quote": "Members are using AI in actuarial work",
                                "summary": "会员正在精算工作中使用人工智能。",
                            }
                        ]
                    }
                )
            section_id = data["observations"][-1]["data"]["sections"][0]["section_id"]
            return json.dumps(
                {
                    "action": "finish",
                    "answer": "model prose",
                    "evidence_ids": [section_id],
                    "findings": [
                        {
                            "evidence_id": section_id,
                            "quote": "Members have fully automated all actuarial work.",
                            "summary": "所有精算工作已经自动化。",
                        }
                    ],
                }
            )
        return json.dumps({"supported": [True]})

    def resolve(target):
        document = facade._document(SelectedTarget.model_validate(target))
        return document.model_dump() if document else None

    result = run(
        message="请查找《SOA Member AI Survey: Spring 2026》，并读取章节“Key Findings”，引用其中一句原文并用中文说明。",
        locale="zh",
        registry=registry,
        context=RunContext(
            principal="test",
            scopes=frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
        ),
        model=model,
        execute=execute,
        resolve_selected_document=resolve,
    )
    assert result.kind == "finish" and result.availability == "available", result
    assert result.evidence_ids == tuple(observed_ids)
    assert len(calls) == 4
    assert "Members are using AI in actuarial work" in result.answer
    assert SURVEY in result.answer


def test_body_findings_prompt_distinguishes_evidence_id_from_section_id(research):
    prompt_seen = []

    def model(prompt, remaining):
        prompt_seen.append(json.loads(json.loads(prompt)["prompt"])["instruction"])
        return json.dumps({"action": "clarify", "question": "Which report?"})

    run(
        message="请引用 Key Findings 原文并用中文说明。",
        locale="zh",
        registry=Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools)),
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=lambda *_: pytest.fail("clarify must not call a tool"),
    )
    assert "observations[].evidence_ids" in prompt_seen[0]
    assert "sections[].section_id" in prompt_seen[0]


@pytest.mark.parametrize(
    "mode,expected_code,expected_calls",
    [
        ("old_quote", "NO_EVIDENCE", 3),
        ("wrong_id", "NO_EVIDENCE", 3),
        ("wrong_url", "NO_EVIDENCE", 3),
        ("summary_url", "NO_EVIDENCE", 3),
        ("empty_summary", "NO_EVIDENCE", 3),
        ("long_summary", "NO_EVIDENCE", 3),
        ("three_findings", "NO_EVIDENCE", 3),
        ("removed", "NO_EVIDENCE", 3),
        ("numeric_claim", "SUMMARY_UNVERIFIED", 4),
        ("verification_false", "SUMMARY_UNVERIFIED", 4),
        ("verification_error", "SUMMARY_UNVERIFIED", 4),
        ("empty_output", "INVALID_MODEL_RESPONSE", 3),
        ("provider_length", "PROVIDER_UNAVAILABLE", 3),
    ],
)
def test_guarded_finding_never_promotes_invalid_or_unverified_content(
    research, mode, expected_code, expected_calls
):
    facade, storage, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    calls = []
    quote = "Members are using AI in actuarial work"
    summary = "会员正在精算工作中使用人工智能。"

    def model(prompt, remaining):
        data = json.loads(prompt)
        calls.append(data)
        if len(calls) == 1:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "SOA Member AI Survey: Spring 2026"},
                }
            )
        if len(calls) == 2:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        if len(calls) == 3:
            assert set(data) == {"instruction", "question", "locale", "excerpt"}
            if mode == "empty_output":
                return ""
            if mode == "provider_length":
                raise RuntimeError("length with no visible content")
            if mode == "removed":
                storage._conn.execute("DELETE FROM rag_kb_files WHERE file_url = ?", (SURVEY,))
            finding = {"quote": quote, "summary": summary}
            if mode == "old_quote":
                finding["quote"] = "SOA Bulletin: Old AI Survey"
            elif mode == "wrong_id":
                finding["evidence_id"] = "old-catalog-id"
            elif mode == "empty_summary":
                finding["summary"] = ""
            elif mode == "long_summary":
                finding["summary"] = "字" * 301
            elif mode == "numeric_claim":
                finding["summary"] = "共有12,345名受访者。"
            elif mode == "summary_url":
                finding["summary"] = f"会员正在使用人工智能。来源：{BULLETIN}"
            output = {"findings": [finding] * (3 if mode == "three_findings" else 1)}
            if mode == "wrong_url":
                output["source_url"] = BULLETIN
            return json.dumps(output)
        assert data["items"][0]["excerpt"] == quote
        if mode == "verification_error":
            raise RuntimeError("verification failed")
        return json.dumps({"supported": [mode != "verification_false"]})

    def resolve(target):
        document = facade._document(SelectedTarget.model_validate(target))
        return document.model_dump() if document else None

    result = run(
        message="请简要总结SOA会员人工智能调查的主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(
            principal="test",
            scopes=frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
        ),
        model=model,
        execute=lambda tool, args, context, remaining: getattr(
            executors, tool.executor.split(".")[1]
        )(facade, args),
        resolve_selected_document=resolve,
    )
    assert result.error_code == expected_code
    assert result.availability != "available" and summary not in result.answer
    assert result.model_attempts == expected_calls and result.tool_attempts == 2
    if expected_code == "SUMMARY_UNVERIFIED":
        assert quote in result.answer and SURVEY in result.answer
    else:
        assert result.answer == ""


@pytest.mark.parametrize(
    "mode",
    [
        "two_sections",
        "non_key_findings",
        "standard",
        "stale",
        "hard_gate",
        "wrong_target",
        "wrong_source",
        "comparison",
        "sample",
        "date",
        "source_link",
        "status",
        "no_resolver",
    ],
)
def test_guarded_route_leaves_other_questions_and_evidence_on_existing_path(research, mode):
    facade, storage, _, state = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    if mode == "two_sections":
        state["sections"].append(
            {
                "file_url": SURVEY,
                "section_id": "another-finding",
                "heading": "Key Findings",
                "text_snippet": "Organizations are developing training.",
            }
        )
    if mode == "stale":
        state.update(stale=True, severity="soft_stale")
    if mode == "hard_gate":
        state["ready"] = False
        storage._conn.execute("UPDATE rag_knowledge_bases SET index_path = NULL")
    message = {
        "comparison": "请总结主要发现并比较ASHK问卷",
        "sample": "请总结主要发现和样本数",
        "date": "请总结主要发现和发布日期",
        "source_link": "请总结主要发现并给原文链接",
        "status": "请总结主要发现和Ready状态",
    }.get(mode, "请简要总结SOA会员人工智能调查的主要发现")
    calls = []

    def model(prompt, remaining):
        data = json.loads(prompt)
        calls.append(data)
        if len(calls) <= 2:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": (
                        "document_research.find_documents"
                        if len(calls) == 1
                        else "document_research.read_document_sections"
                    ),
                    "args": (
                        {"query": "SOA Member AI Survey: Spring 2026"}
                        if len(calls) == 1
                        else {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"}
                    ),
                }
            )
        assert set(data) == {"prompt", "observations"}
        assert "skills" in data["prompt"]
        return json.dumps({"action": "clarify", "question": "legacy route"})

    def execute(tool, args, context, remaining):
        observed = getattr(executors, tool.executor.split(".")[1])(facade, args)
        if tool.tool_id == "document_research.read_document_sections" and mode in {
            "non_key_findings",
            "standard",
            "wrong_target",
            "wrong_source",
        }:
            section = dict(observed.data["sections"][0])
            if mode == "non_key_findings":
                section["heading"] = "Limitations"
            elif mode == "standard":
                section["retrieval"] = "standard"
            elif mode == "wrong_target":
                section["target"] = {"kb_id": "public", "file_id": BULLETIN}
            else:
                section["source_url"] = BULLETIN
            return ToolResult("ok", {**observed.data, "sections": [section]}, observed.evidence_ids)
        return observed

    def resolve(target):
        document = facade._document(SelectedTarget.model_validate(target))
        return document.model_dump() if document else None

    result = run(
        message=message,
        locale="zh",
        registry=registry,
        context=RunContext(
            principal="test",
            scopes=frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
        ),
        model=model,
        execute=execute,
        resolve_selected_document=None if mode == "no_resolver" else resolve,
    )
    assert result.kind == "clarify" and result.answer == "legacy route"
    assert result.model_attempts == 3 and result.tool_attempts == 2


def test_catalog_candidates_without_a_selected_read_keep_general_prompt(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    prompts = []

    def model(prompt, remaining):
        data = json.loads(prompt)
        prompts.append(data)
        return json.dumps(
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.find_documents",
                "args": {"query": "SOA Member AI Survey: Spring 2026"},
            }
            if len(prompts) == 1
            else {"action": "clarify", "question": "choose a report"}
        )

    result = run(
        message="请简要总结主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(
            principal="test", scopes=frozenset({"chat.query", "catalog.read", "files.read"})
        ),
        model=model,
        execute=lambda tool, args, context, remaining: executors.find_documents(facade, args),
    )
    assert result.kind == "clarify" and result.tool_attempts == 1
    assert set(prompts[1]) == {"prompt", "observations"}


@pytest.mark.parametrize("revoke", [False, True])
def test_guarded_feature_rechecks_body_scope_before_releasing_summary(
    research, monkeypatch, revoke
):
    from ai_actuarial.features.assistant import feature as host

    _, storage, _, _ = research
    auth = AuthContext(
        {"id": 7, "group_name": "registered"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    current_auth = [auth]
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_path="isolated", assistant_public_kb_ids=["public"], assistant_staff_kb_ids=[]
            )
        ),
        state=SimpleNamespace(),
    )
    monkeypatch.setattr(host.chat, "Storage", lambda database: storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("test", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **kwargs: None)
    monkeypatch.setattr(host.deps, "get_auth_context", lambda request: current_auth[0])
    monkeypatch.setattr(storage, "close", lambda: None)
    calls = []

    def model(prompt, remaining):
        data = json.loads(prompt)
        calls.append(data)
        if len(calls) <= 2:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": (
                        "document_research.find_documents"
                        if len(calls) == 1
                        else "document_research.read_document_sections"
                    ),
                    "args": (
                        {"query": "SOA Member AI Survey: Spring 2026"}
                        if len(calls) == 1
                        else {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"}
                    ),
                }
            )
        if len(calls) == 3:
            assert set(data) == {"instruction", "question", "locale", "excerpt"}
            if revoke:
                current_auth[0] = AuthContext(
                    auth.token, frozenset({"chat.query", "catalog.read", "files.read"})
                )
            return json.dumps(
                {
                    "findings": [
                        {
                            "quote": "Members are using AI in actuarial work",
                            "summary": "会员正在精算工作中使用人工智能。",
                        }
                    ]
                }
            )
        assert data["items"][0]["excerpt"] == "Members are using AI in actuarial work"
        return json.dumps({"supported": [True]})

    outcome = host.AssistantFeature().query(
        request=request,
        auth=auth,
        message="请简要总结SOA会员人工智能调查的主要发现",
        locale="zh",
        model=model,
    )
    if revoke:
        assert outcome.runtime.error_code == "NO_EVIDENCE"
        assert outcome.runtime.answer == "" and outcome.runtime.model_attempts == 3
    else:
        assert outcome.runtime.availability == "available"
        assert outcome.runtime.model_attempts == 4
        assert "会员正在精算工作中使用人工智能" in outcome.runtime.answer
        assert SURVEY in outcome.runtime.answer and BULLETIN not in outcome.runtime.answer
    assert outcome.runtime.tool_attempts == 2


def test_findings_and_readiness_descriptions_keep_separate_routes(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    description = registry.descriptions()[0]
    tools = {item["tool_id"]: item for item in description["tools"]}
    assert "findings: find, then read" in description["description"].lower()
    assert (
        "without a separate readiness call"
        in tools["document_research.read_document_sections"]["description"].lower()
    )
    assert (
        "explicit status questions" in tools["document_research.readiness"]["description"].lower()
    )
    assert registry.tool("document_research", "document_research.readiness").required_scopes == {
        "chat.query",
        "markdown.read",
    }
    observed = executors.readiness(facade, {"kb_id": "public", "file_id": SURVEY})
    assert observed.status == "ok"
    assert observed.data["status"] == "ready_publication_usable"
    assert observed.data["publication_id"] == "ready-v1"
    assert observed.data["index_version"] == "idx-v1"
    assert observed.data["document"]["source_url"] == SURVEY


def test_host_answers_usable_ready_and_soft_stale_status(research):
    facade, _, _, state = research
    state.update(stale=True, severity="soft_stale")
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    actions = [
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.readiness",
            "args": {"kb_id": "public", "file_id": SURVEY},
        }
    ]

    def model(prompt, remaining):
        if actions:
            return json.dumps(actions.pop(0))
        identifier = json.loads(prompt)["observations"][0]["evidence_ids"][0]
        return json.dumps({"action": "finish", "answer": "unused", "evidence_ids": [identifier]})

    result = run(
        message="Is this survey Ready, and is it stale?",
        locale="en",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=lambda tool, args, context, remaining: executors.readiness(facade, args),
    )
    assert result.kind == "finish" and result.availability == "available"
    assert "Ready" in result.answer and "soft-stale" in result.answer
    assert SURVEY in result.answer
    assert "body finding" not in result.answer.lower()
    assert "unused" not in result.answer
    assert result.tool_attempts == 1 and result.model_attempts == 2


def test_host_renders_only_supported_finding_from_two_current_sections(research):
    facade, _, _, state = research
    state["sections"] = [
        {
            "file_url": SURVEY,
            "section_id": "finding-one",
            "heading": "Key Findings",
            "text_snippet": "Members are using AI in actuarial work.",
        },
        {
            "file_url": SURVEY,
            "section_id": "finding-two",
            "heading": "Key Findings",
            "text_snippet": "Organizations are developing training.",
        },
    ]
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        data = json.loads(prompt)
        if data.get("items"):
            assert [item["excerpt"] for item in data["items"]] == [
                "Members are using AI",
                "Organizations are developing training",
            ]
            return json.dumps({"supported": [True, False]})
        if not data["observations"]:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        first, second = data["observations"][0]["evidence_ids"]
        return json.dumps(
            {
                "action": "finish",
                "answer": "unused",
                "evidence_ids": [first, second],
                "findings": [
                    {
                        "evidence_id": first,
                        "quote": "Members are using AI",
                        "summary": "会员正在使用人工智能。",
                    },
                    {
                        "evidence_id": second,
                        "quote": "Organizations are developing training",
                        "summary": "样本总数为12,345人。",
                    },
                ],
            }
        )

    result = run(
        message="请总结主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=execute,
    )
    assert result.kind == "finish" and result.availability == "available"
    assert "会员正在使用人工智能" in result.answer
    assert "12,345" not in result.answer
    assert len(result.evidence_ids) == 1


def test_host_verifies_summary_against_displayed_quote(research):
    facade, _, _, state = research
    state["sections"][0]["text_snippet"] = "There were 1000 respondents. Members use AI."
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        data = json.loads(prompt)
        if data.get("items"):
            assert data["items"][0]["excerpt"] == "Members use AI."
            return json.dumps({"supported": [True]})
        if not data["observations"]:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        identifier = data["observations"][0]["evidence_ids"][0]
        return json.dumps(
            {
                "action": "finish",
                "answer": "unused",
                "evidence_ids": [identifier],
                "findings": [
                    {
                        "evidence_id": identifier,
                        "quote": "Members use AI.",
                        "summary": "有1000名受访者。",
                    }
                ],
            }
        )

    result = run(
        message="请总结主要发现",
        locale="zh",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=execute,
    )
    assert result.error_code == "SUMMARY_UNVERIFIED"
    assert "1000" not in result.answer
    assert "Members use AI." in result.answer


def test_host_keeps_only_complete_cited_findings_near_answer_limit(research):
    facade, _, _, state = research
    quotes = [f"Finding {index} " + "x" * 1090 for index in range(4)]
    state["sections"] = [
        {
            "file_url": SURVEY if index < 2 else BULLETIN,
            "section_id": f"finding-{index}",
            "heading": "Key Findings",
            "text_snippet": quote,
        }
        for index, quote in enumerate(quotes)
    ]
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    targets = [SURVEY, BULLETIN]
    observed_ids = []

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        data = json.loads(prompt)
        if data.get("items"):
            assert len(data["items"]) == 4
            return json.dumps({"supported": [True] * 4})
        observations = data["observations"]
        if len(observations) < 2:
            target = targets[len(observations)]
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": target, "query": "Key Findings"},
                }
            )
        observed_ids[:] = [identifier for row in observations for identifier in row["evidence_ids"]]
        return json.dumps(
            {
                "action": "finish",
                "answer": "unused",
                "evidence_ids": observed_ids,
                "findings": [
                    {"evidence_id": identifier, "quote": quote, "summary": f"Finding {index}."}
                    for index, (identifier, quote) in enumerate(zip(observed_ids, quotes))
                ],
            }
        )

    result = run(
        message="Summarize the Key Findings",
        locale="en",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=model,
        execute=execute,
    )
    assert result.availability == "available"
    assert result.model_attempts == 4 and result.tool_attempts == 2
    assert result.evidence_ids == tuple(observed_ids[:3])
    assert len(result.answer) <= 4000
    assert result.answer.count("[https://") == 3
    assert all(quote in result.answer for quote in quotes[:3])
    assert quotes[3] not in result.answer


@pytest.mark.parametrize(
    "summary,verification,used_attempts",
    [
        ("该调查共有12,345名受访者。", '{"supported":[false]}', 0),
        ("该调查共有12,345名受访者。", '{"supported":[true]}', 0),
        ("所有受访者都反对人工智能。", '{"supported":[false]}', 0),
        ("该调查共有12,345名受访者。", "malformed", 0),
        ("该调查共有12,345名受访者。", "provider_error", 0),
        ("该调查共有12,345名受访者。", "budget_exhausted", 4),
    ],
)
def test_host_omits_unverified_summary_but_keeps_exact_excerpt(
    research, summary, verification, used_attempts
):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    calls = []

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        calls.append(json.loads(prompt))
        if len(calls) == 1:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        if len(calls) == 2:
            identifier = calls[-1]["observations"][0]["evidence_ids"][0]
            return json.dumps(
                {
                    "action": "finish",
                    "answer": "unused",
                    "evidence_ids": [identifier],
                    "findings": [
                        {
                            "evidence_id": identifier,
                            "quote": "Members are using AI",
                            "summary": summary,
                        }
                    ],
                }
            )
        if verification == "provider_error":
            raise RuntimeError("test provider error")
        return verification

    context = RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"}))
    context.model_attempts = used_attempts
    result = run(
        message="请总结主要发现",
        locale="zh",
        registry=registry,
        context=context,
        model=model,
        execute=execute,
    )
    assert result.error_code == "SUMMARY_UNVERIFIED"
    assert summary not in result.answer
    assert "Members are using AI" in result.answer and SURVEY in result.answer
    assert len(calls) == (2 if verification == "budget_exhausted" else 3)


def test_late_verification_result_cannot_publish_summary(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    context = RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"}))

    def execute(tool, args, run_context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        data = json.loads(prompt)
        if data.get("items"):
            context.deadline = time.monotonic() - 1
            return json.dumps({"supported": [True]})
        if not data["observations"]:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        identifier = data["observations"][0]["evidence_ids"][0]
        return json.dumps(
            {
                "action": "finish",
                "answer": "unused",
                "evidence_ids": [identifier],
                "findings": [
                    {
                        "evidence_id": identifier,
                        "quote": "Members are using AI",
                        "summary": "会员正在使用人工智能。",
                    }
                ],
            }
        )

    result = run(
        message="请总结主要发现",
        locale="zh",
        registry=registry,
        context=context,
        model=model,
        execute=execute,
    )
    assert result.error_code == "ASSISTANT_TIMEOUT"
    assert result.answer == ""
    assert result.model_attempts == 3


def test_catalog_only_finish_names_found_report_and_public_link(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    actions = [
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.find_documents",
            "args": {"query": "SOA Member AI Survey: Spring 2026"},
        },
    ]

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        if actions:
            return json.dumps(actions.pop(0))
        identifier = json.loads(prompt)["observations"][0]["evidence_ids"][0]
        return json.dumps(
            {"action": "finish", "answer": "invented sample", "evidence_ids": [identifier]}
        )

    result = run(
        message="Find SOA Member AI Survey: Spring 2026",
        locale="en",
        registry=registry,
        context=RunContext(
            principal="test", scopes=frozenset({"chat.query", "catalog.read", "files.read"})
        ),
        model=model,
        execute=execute,
    )
    assert result.kind == "finish" and result.availability == "unavailable"
    assert "SOA Member AI Survey: Spring 2026" in result.answer
    assert SURVEY in result.answer
    assert "invented sample" not in result.answer


@pytest.mark.parametrize(
    "catalog_count,read_file,duplicate_target",
    [
        (0, SURVEY, False),
        (1, SURVEY, False),
        (1, BULLETIN, False),
        (2, SURVEY, False),
        (2, SURVEY, True),
    ],
)
def test_body_read_error_preserves_only_unique_found_report(
    catalog_count, read_file, duplicate_target
):
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    actions = iter(
        [
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.find_documents",
                "args": {"query": "SOA Member AI Survey"},
            },
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.read_document_sections",
                "args": {"kb_id": "public", "file_id": read_file, "query": "Key Findings"},
            },
        ]
    )
    documents = [
        {
            "target": {"kb_id": "public", "file_id": SURVEY},
            "title": "SOA Member AI Survey: Spring 2026",
            "source_url": SURVEY,
            "summary": "1000 invented findings",
        },
        {
            "target": {"kb_id": "public", "file_id": BULLETIN},
            "title": "SOA Bulletin: Old AI Survey",
            "source_url": BULLETIN,
            "summary": "another report",
        },
    ][:catalog_count]
    if duplicate_target:
        documents[1]["target"] = {"kb_id": "public", "file_id": SURVEY}

    def execute(tool, args, context, remaining):
        if tool.tool_id == "document_research.find_documents":
            return ToolResult(
                "ok" if documents else "not_found",
                {"documents": documents},
                tuple(f"catalog-{index}" for index in range(len(documents))),
            )
        raise RuntimeError("body read failed")

    result = run(
        message="Please read the report and summarize its findings",
        locale="en",
        registry=registry,
        context=RunContext(principal="test", scopes=frozenset({"chat.query", "markdown.read"})),
        model=lambda prompt, remaining: json.dumps(next(actions)),
        execute=execute,
    )
    assert [(item.tool_id, item.status) for item in result.trace] == [
        ("document_research.find_documents", "ok" if documents else "not_found"),
        ("document_research.read_document_sections", "error"),
    ]
    assert result.tool_attempts == 2 and result.model_attempts == 2
    if catalog_count and read_file == SURVEY and not duplicate_target:
        assert result.kind == "finish" and result.availability == "unavailable"
        assert result.error_code == "TOOL_UNAVAILABLE"
        assert result.evidence_ids == ("catalog-0",)
        assert "SOA Member AI Survey: Spring 2026" in result.answer
        assert SURVEY in result.answer
        assert BULLETIN not in result.answer
        assert "Body" in result.answer and "read" in result.answer
        assert "1000" not in result.answer and "findings" not in result.answer
    else:
        assert result.kind == "error" and result.error_code == "TOOL_UNAVAILABLE"
        assert result.answer == "" and result.evidence_ids == ()


@pytest.mark.parametrize(
    "failure_mode", ["none", "membership_removed", "deleted", "scope_revoked", "identity_changed"]
)
def test_followup_body_read_error_uses_only_current_valid_target(
    research, monkeypatch, failure_mode
):
    from ai_actuarial.features.assistant import feature as host

    _, storage, _, _ = research
    auth = AuthContext(
        {"id": 7, "group_name": "registered"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    current_auth = [auth]
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_path="isolated", assistant_public_kb_ids=["public"], assistant_staff_kb_ids=[]
            )
        ),
        state=SimpleNamespace(),
    )
    monkeypatch.setattr(host.chat, "Storage", lambda database: storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("test", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **kwargs: None)
    monkeypatch.setattr(host.deps, "get_auth_context", lambda request: current_auth[0])
    monkeypatch.setattr(storage, "close", lambda: None)

    def fail_read(facade, args):
        if failure_mode == "membership_removed":
            storage._conn.execute("DELETE FROM rag_kb_files WHERE file_url = ?", (SURVEY,))
        elif failure_mode == "deleted":
            storage._conn.execute("UPDATE files SET deleted_at = 'now' WHERE url = ?", (SURVEY,))
        elif failure_mode == "scope_revoked":
            current_auth[0] = AuthContext(auth.token, frozenset({"chat.query", "files.read"}))
        elif failure_mode == "identity_changed":
            current_auth[0] = AuthContext({"id": 8}, auth.permissions)
        raise RuntimeError("body read failed")

    feature = host.AssistantFeature()
    feature.executors["document_research.read_document_sections"] = fail_read
    outcome = feature.query(
        request=request,
        auth=auth,
        message="What did this report find?",
        selected_target=SelectedTarget(kb_id="public", file_id=SURVEY),
        model=lambda prompt, remaining: json.dumps(
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.read_document_sections",
                "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
            }
        ),
    )
    assert outcome.runtime.model_attempts == 1 and outcome.runtime.tool_attempts == 1
    assert outcome.runtime.error_code == "TOOL_UNAVAILABLE"
    if failure_mode == "none":
        assert outcome.runtime.kind == "finish" and outcome.runtime.availability == "unavailable"
        assert "SOA Member AI Survey: Spring 2026" in outcome.runtime.answer
        assert SURVEY in outcome.runtime.answer
        assert "Body read failed" in outcome.runtime.answer
        assert "Members are using AI" not in outcome.runtime.answer
    else:
        assert outcome.runtime.kind == "error"
        assert outcome.runtime.answer == "" and outcome.runtime.evidence_ids == ()


@pytest.mark.parametrize("failure_mode", ["not_found", "read_error"])
def test_feature_rejects_removed_catalog_evidence(research, monkeypatch, failure_mode):
    from ai_actuarial.agentic_rag import ready_data_tools
    from ai_actuarial.features.assistant import feature as host

    _, storage, _, _ = research
    auth = AuthContext(
        {"id": 7, "group_name": "registered"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_path="isolated", assistant_public_kb_ids=["public"], assistant_staff_kb_ids=[]
            )
        ),
        state=SimpleNamespace(),
    )
    monkeypatch.setattr(host.chat, "Storage", lambda database: storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("test", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **kwargs: None)
    monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    monkeypatch.setattr(storage, "close", lambda: None)

    if failure_mode == "read_error":

        def fail_after_initial_membership_check(*args, **kwargs):
            storage._conn.execute("DELETE FROM rag_kb_files WHERE file_url = ?", (SURVEY,))
            raise RuntimeError("Ready read failed")

        monkeypatch.setattr(
            ready_data_tools, "search_sections", fail_after_initial_membership_check
        )

    def model(prompt, remaining):
        observations = json.loads(prompt)["observations"]
        if not observations:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "SOA Member AI Survey: Spring 2026"},
                }
            )
        if len(observations) == 1:
            if failure_mode == "not_found":
                storage._conn.execute("DELETE FROM rag_kb_files WHERE file_url = ?", (SURVEY,))
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        return json.dumps(
            {
                "action": "finish",
                "answer": "removed survey",
                "evidence_ids": [observations[0]["evidence_ids"][0]],
            }
        )

    outcome = host.AssistantFeature().query(
        request=request, auth=auth, message="What did the survey find?", model=model
    )
    assert [item.status for item in outcome.runtime.trace] == [
        "ok",
        "not_found" if failure_mode == "not_found" else "error",
    ]
    assert outcome.runtime.error_code == (
        "NO_EVIDENCE" if failure_mode == "not_found" else "TOOL_UNAVAILABLE"
    )
    assert outcome.runtime.answer == "" and outcome.runtime.evidence_ids == ()
    assert outcome.response.selected_target is None


def test_loop_invalidates_catalog_id_after_target_not_found(research):
    facade, storage, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))

    def model(prompt, remaining):
        observations = json.loads(prompt)["observations"]
        if not observations:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "SOA Member AI Survey: Spring 2026"},
                }
            )
        if len(observations) == 1:
            storage._conn.execute("DELETE FROM rag_kb_files WHERE file_url = ?", (SURVEY,))
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                }
            )
        return json.dumps(
            {
                "action": "finish",
                "answer": "removed survey",
                "evidence_ids": [observations[0]["evidence_ids"][0]],
            }
        )

    result = run(
        message="What did the survey find?",
        locale="en",
        registry=registry,
        context=RunContext(
            principal="test",
            scopes=frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
        ),
        model=model,
        execute=lambda tool, args, context, remaining: getattr(
            executors, tool.executor.split(".")[1]
        )(facade, args),
    )
    assert result.error_code == "NO_EVIDENCE"
    assert result.answer == "" and result.evidence_ids == ()


def test_publication_date_answer_uses_only_stored_date_and_labels_first_seen(research):
    facade, _, _, _ = research
    registry = Registry((MANIFEST,), frozenset(tool.executor for tool in MANIFEST.tools))
    actions = [
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.find_documents",
            "args": {"query": "SOA Member AI Survey: Spring 2026"},
        },
    ]

    def execute(tool, args, context, remaining):
        return getattr(executors, tool.executor.split(".")[1])(facade, args)

    def model(prompt, remaining):
        if actions:
            return json.dumps(actions.pop(0))
        identifier = json.loads(prompt)["observations"][0]["evidence_ids"][0]
        return json.dumps(
            {"action": "finish", "answer": "published Spring 2026", "evidence_ids": [identifier]}
        )

    result = run(
        message="SOA Member AI Survey: Spring 2026 的发布日期？",
        locale="zh",
        registry=registry,
        context=RunContext(
            principal="test", scopes=frozenset({"chat.query", "catalog.read", "files.read"})
        ),
        model=model,
        execute=execute,
    )
    assert "发布日期：未知" in result.answer
    assert "系统首次收录：2026-07-01" in result.answer
    assert "2026-10-01" not in result.answer
    assert "published Spring 2026" not in result.answer


def test_feature_rechecks_auth_between_skill_calls(research, monkeypatch):
    from ai_actuarial.features.assistant import feature as host

    facade, storage, _, _ = research
    full = AuthContext(
        {"id": 7, "group_name": "registered"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    revoked = AuthContext(
        {"id": 7, "group_name": "registered"},
        frozenset({"chat.query", "catalog.read", "files.read"}),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_path="isolated", assistant_public_kb_ids=["public"], assistant_staff_kb_ids=[]
            )
        ),
        state=SimpleNamespace(),
    )
    monkeypatch.setattr(host.chat, "Storage", lambda database: storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("test", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **kwargs: None)
    current = iter([full, full, revoked])
    monkeypatch.setattr(host.deps, "get_auth_context", lambda request: next(current))
    actions = iter(
        [
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.find_documents",
                "args": {"query": "SOA Member AI Survey: Spring 2026"},
            },
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.read_document_sections",
                "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
            },
        ]
    )
    result = host.AssistantFeature().query(
        request=request,
        auth=full,
        message="Summarize the SOA Member AI Survey",
        model=lambda prompt, remaining: json.dumps(next(actions)),
        selected_target=SelectedTarget(kb_id="public", file_id=SURVEY),
    )
    assert result.response.error_code == "SCOPE_REVOKED"
    assert result.response.selected_target is None
    assert [item.status for item in result.runtime.trace] == ["ok"]


def test_feature_target_roundtrip_refresh_and_correction(research, monkeypatch):
    from ai_actuarial.features.assistant import feature as host

    _, storage, _, state = research
    auth = AuthContext(
        {"id": 7, "group_name": "registered"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_path="isolated", assistant_public_kb_ids=["public"], assistant_staff_kb_ids=[]
            )
        ),
        state=SimpleNamespace(),
    )
    monkeypatch.setattr(host.chat, "Storage", lambda database: storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("test", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **kwargs: None)
    monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    monkeypatch.setattr(storage, "close", lambda: None)
    feature = host.AssistantFeature()

    def model_for(actions):
        pending = list(actions)

        def model(prompt, remaining):
            if pending:
                return json.dumps(pending.pop(0))
            if len(json.loads(prompt).get("items", [])) == 1:
                return json.dumps({"supported": [True]})
            identifier = json.loads(prompt)["observations"][-1]["evidence_ids"][0]
            return json.dumps(
                {
                    "action": "finish",
                    "answer": "model prose",
                    "evidence_ids": [identifier],
                    "findings": [
                        {
                            "evidence_id": identifier,
                            "quote": (
                                "Fresh"
                                if "Fresh" in state["sections"][0]["text_snippet"]
                                else "Members"
                            ),
                            "summary": "有依据的中文摘要。",
                        }
                    ],
                }
            )

        return model

    first = feature.query(
        request=request,
        auth=auth,
        message="SOA Member AI Survey Spring 2026 findings",
        model=model_for(
            [
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "SOA Member AI Survey Spring 2026"},
                },
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
                },
            ]
        ),
    )
    assert first.response.selected_target == {"kb_id": "public", "file_id": SURVEY}
    assert "Members" in first.response.answer
    assert first.runtime.model_attempts == 4
    state["sections"][0].update(
        heading="Sample", text_snippet="Fresh current sample evidence on the second turn."
    )
    second = feature.query(
        request=request,
        auth=auth,
        message="样本多少？",
        selected_target=SelectedTarget.model_validate(first.response.selected_target),
        model=model_for(
            [
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": SURVEY, "query": "样本多少"},
                },
            ]
        ),
    )
    assert second.response.selected_target == first.response.selected_target
    assert "Fresh" in second.response.answer and "Members" not in second.response.answer

    def corrected_model(prompt, remaining):
        observations = json.loads(prompt)["observations"]
        if not observations:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.find_documents",
                    "args": {"query": "I meant the ASHK member AI questionnaire"},
                }
            )
        documents = observations[0]["data"]["documents"]
        assert len(documents) > 1
        identifier = next(
            evidence_id
            for evidence_id, document in zip(observations[0]["evidence_ids"], documents)
            if document["target"]["file_id"] == ASHK
        )
        return json.dumps({"action": "finish", "answer": "link", "evidence_ids": [identifier]})

    corrected = feature.query(
        request=request,
        auth=auth,
        message="I meant the ASHK member AI questionnaire",
        selected_target=SelectedTarget.model_validate(first.response.selected_target),
        model=corrected_model,
    )
    assert corrected.response.selected_target == {"kb_id": "public", "file_id": ASHK}
    assert corrected.response.availability == "unavailable"
    state["sections"] = [
        {
            "file_url": ASHK,
            "section_id": "ashk-findings",
            "heading": "Key Findings",
            "text_snippet": "Fresh ASHK findings on this turn.",
        }
    ]

    def ashk_model(prompt, remaining):
        data = json.loads(prompt)
        if data.get("items"):
            return json.dumps({"supported": [True]})
        if not data["observations"]:
            return json.dumps(
                {
                    "action": "call",
                    "skill_id": "document_research",
                    "tool_id": "document_research.read_document_sections",
                    "args": {"kb_id": "public", "file_id": ASHK, "query": "Key Findings"},
                }
            )
        identifier = data["observations"][0]["evidence_ids"][0]
        return json.dumps(
            {
                "action": "finish",
                "answer": "unused",
                "evidence_ids": [identifier],
                "findings": [
                    {
                        "evidence_id": identifier,
                        "quote": "Fresh ASHK findings",
                        "summary": "ASHK问卷的新证据。",
                    }
                ],
            }
        )

    next_turn = feature.query(
        request=request,
        auth=auth,
        message="What did it find?",
        selected_target=SelectedTarget.model_validate(corrected.response.selected_target),
        model=ashk_model,
    )
    assert next_turn.response.selected_target == {"kb_id": "public", "file_id": ASHK}
    assert "Fresh ASHK findings" in next_turn.response.answer
    assert ASHK in next_turn.response.answer and SURVEY not in next_turn.response.answer


@pytest.mark.parametrize(
    "skill_id,tool_id,executor_id",
    [
        (
            "resources_updates",
            "resources_updates.find_documents",
            "resources_updates.find_documents",
        ),
        ("test_catalog_alias", "test_catalog_alias.locate", "test_catalog_alias.locate"),
    ],
)
def test_discovery_contract_read_and_follow_up_share_host_provenance(
    research, monkeypatch, skill_id, tool_id, executor_id
):
    from ai_actuarial.features.assistant import AssistantFeature
    from ai_actuarial.features.assistant import feature as host
    from ai_actuarial.skills.document_research import executors as research_executors

    _facade, storage, _allowed, _state = research
    storage.close = lambda: None  # Keep the task fixture alive across two request turns.
    auth = AuthContext(
        {"subject": "operator"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    monkeypatch.setattr(host.chat, "Storage", lambda _database: storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda request, auth: ("operator", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **kwargs: None)
    monkeypatch.setattr(host.deps, "get_auth_context", lambda request: auth)
    monkeypatch.setattr(host, "permitted_kbs", lambda request, auth: ["public"])
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_path="test-db")),
        state=SimpleNamespace(),
    )
    feature = AssistantFeature()
    if skill_id == "test_catalog_alias":
        feature.executors[executor_id] = research_executors.find_documents
        test_skill = Registry.load_skill("tests.catalog_discovery_skill", {"FindArgs": FindArgs})
        feature.registry = Registry(
            (*feature.registry.skills.values(), test_skill), frozenset(feature.executors)
        )

    contexts = []
    locator = feature.executors[executor_id]
    reader = feature.executors["document_research.read_document_sections"]

    def track(executor):
        def call(facade, args):
            contexts.append(request.state.assistant_runtime_context)
            return executor(facade, args)

        return call

    feature.executors[executor_id] = track(locator)
    feature.executors["document_research.read_document_sections"] = track(reader)

    def scripted_model(actions, prompts):
        def model(prompt, _remaining):
            data = json.loads(prompt)
            if "items" in data:
                return json.dumps({"supported": [True]})
            prompts.append(data)
            if actions:
                return json.dumps(actions.pop(0))
            evidence_id = data["observations"][-1]["evidence_ids"][0]
            return json.dumps(
                {
                    "action": "finish",
                    "answer": "unused",
                    "evidence_ids": [evidence_id],
                    "findings": [
                        {
                            "evidence_id": evidence_id,
                            "quote": "Members are using AI in actuarial work",
                            "summary": "Members are using AI in actuarial work.",
                        }
                    ],
                }
            )

        return model

    first_prompts = []
    first_actions = [
        {
            "action": "call",
            "skill_id": skill_id,
            "tool_id": tool_id,
            "args": {"query": "SOA Member AI Survey: Spring 2026"},
        },
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.read_document_sections",
            "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
        },
    ]
    first = feature.query(
        request=request,
        auth=auth,
        message="What did the latest SOA member AI survey find?",
        model=scripted_model(first_actions, first_prompts),
    )
    assert first.runtime.kind == "finish" and first.runtime.error_code is None
    assert [item.tool_id for item in first.runtime.trace] == [
        tool_id,
        "document_research.read_document_sections",
    ]
    assert first.response.selected_target == {"kb_id": "public", "file_id": SURVEY}
    assert "Members are using AI in actuarial work" in first.response.answer
    assert SURVEY in first.response.answer
    assert first.runtime.tool_attempts == 2 and first.runtime.model_attempts == 4
    assert contexts[0] is contexts[1]
    assert contexts[0].principal == "operator"
    assert contexts[0].scopes == auth.permissions

    follow_prompts = []
    follow_actions = [
        {
            "action": "call",
            "skill_id": "document_research",
            "tool_id": "document_research.read_document_sections",
            "args": {"kb_id": "public", "file_id": SURVEY, "query": "Key Findings"},
        }
    ]
    follow = feature.query(
        request=request,
        auth=auth,
        message="Quote that report and give its original link.",
        selected_target=SelectedTarget.model_validate(first.response.selected_target),
        model=scripted_model(follow_actions, follow_prompts),
    )
    assert follow.runtime.kind == "finish" and follow.runtime.error_code is None
    assert follow.response.selected_target == first.response.selected_target
    assert "Members are using AI in actuarial work" in follow.response.answer
    assert SURVEY in follow.response.answer
    assert follow.runtime.tool_attempts == 1 and follow.runtime.model_attempts == 3
    assert contexts[2] is request.state.assistant_runtime_context
    assert contexts[2] is not contexts[0]
    assert follow_prompts[0]["observations"] == []
    assert (
        json.loads(follow_prompts[0]["prompt"])["selected_target"] == first.response.selected_target
    )
    assert follow.runtime.evidence_ids != ()

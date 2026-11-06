from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import openai
import pytest

from ai_actuarial.api.deps import AuthContext
from ai_actuarial.assistant import knowledge, query
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.embeddings import EmbeddingGenerator

pytest_plugins = ("tests.test_assistant_routing",)


def evidence(kind="kb", text="Mortality improvement is 2%."):
    return knowledge.Evidence(
        knowledge.SourceCitation(
            source_type=kind,
            file_id="https://source/doc",
            section_id="section-1",
            kb_id="public" if kind == "kb" else None,
            title="Current document",
            link="/file-detail?url=https%3A%2F%2Fsource%2Fdoc",
            source_version="published-v1",
            stale=True,
        ),
        text,
    )


@pytest.mark.parametrize(
    "identity,expected",
    [
        (None, ["public"]),
        ({"group_name": "registered"}, ["public"]),
        ({"group_name": "operator"}, ["public", "staff"]),
        ({"group_name": "admin"}, ["public", "staff"]),
    ],
)
def test_allowlist_intersection(runtime, identity, expected):
    from ai_actuarial.shared_auth import permissions_for_group

    state = runtime.request.app.state
    state.assistant_public_kb_ids = ["public"]
    state.assistant_staff_kb_ids = ["staff", "public"]
    auth = AuthContext(
        identity, permissions_for_group(identity["group_name"]) if identity else frozenset()
    )
    assert knowledge.permitted_kbs(runtime.request, auth) == expected
    # A permission without an authenticated identity grants no internal access.
    assert knowledge.permitted_kbs(
        runtime.request, AuthContext(None, frozenset({"assistant.internal"}))
    ) == ["public"]


def test_explicit_empty_scope_precedes_every_runtime_action(runtime):
    result = runtime.run(mode="knowledge")
    assert result.error_code == "KNOWLEDGE_SCOPE_EMPTY"
    assert result.generation_attempts == result.embedding_attempts == 0
    assert not runtime.quota and runtime.initialized == 0


def test_catalog_permission_is_not_inherited_from_chat_token(runtime):
    result = runtime.run(
        mode="catalog", auth=AuthContext({"group_name": "registered"}, frozenset({"chat.query"}))
    )
    assert result.error_code == "CATALOG_FORBIDDEN"
    assert not runtime.quota and not runtime.calls


@pytest.mark.parametrize("mode", ["catalog", "knowledge"])
def test_real_evidence_only_one_answer_generation_and_actual_citation(runtime, monkeypatch, mode):
    runtime.request.app.state.assistant_public_kb_ids = ["public"]
    item = evidence("catalog" if mode == "catalog" else "kb")
    seen = []

    def body(storage, message, kb_ids, **kwargs):
        seen.extend(kb_ids)
        kwargs["on_embedding"]()
        return [item], None

    monkeypatch.setattr(query, "body_evidence", body)
    monkeypatch.setattr(query, "catalog_evidence", lambda *args, **kwargs: [item])
    runtime.outputs = [json.dumps({"steps": [{"source": 0, "quote": item.content}]})]
    result = runtime.run("Mortality", mode=mode)
    assert result.citations == [item.citation]
    assert result.generation_attempts == result.answer_generation_attempts == 1
    assert result.routing_generation_attempts == 0
    assert result.embedding_attempts == (mode == "knowledge")
    sent = json.loads(runtime.calls[0]["messages"][1]["content"])
    assert sent["sources"] == [{"citation": item.citation.model_dump(), "content": item.content}]
    assert seen == (["public"] if mode == "knowledge" else [])


@pytest.mark.parametrize(
    "failure", ["KNOWLEDGE_NOT_FOUND", "INDEX_MISMATCH", "KNOWLEDGE_UNAVAILABLE"]
)
def test_no_body_evidence_has_no_answer_generation_and_preserves_embedding_count(
    runtime, monkeypatch, failure
):
    runtime.request.app.state.assistant_public_kb_ids = ["public"]

    def no_evidence(*args, **kwargs):
        kwargs["on_embedding"]()
        return [], failure

    monkeypatch.setattr(query, "body_evidence", no_evidence)
    result = runtime.run("Mortality", mode="knowledge")
    assert result.error_code == failure
    assert result.generation_attempts == result.answer_generation_attempts == 0
    assert result.embedding_attempts == 1 and not result.citations


def test_auto_denied_keeps_legal_routing_attempt(runtime):
    runtime.outputs = ['{"intent":"knowledge"}']
    result = runtime.run("Mortality")
    assert result.error_code == "KNOWLEDGE_SCOPE_EMPTY"
    assert result.generation_attempts == result.routing_generation_attempts == 1
    assert result.embedding_attempts == result.answer_generation_attempts == 0


def test_answer_failure_preserves_prior_counts(runtime, monkeypatch):
    runtime.request.app.state.assistant_public_kb_ids = ["public"]

    def body(*args, **kwargs):
        kwargs["on_embedding"]()
        return [evidence()], None

    monkeypatch.setattr(query, "body_evidence", body)
    runtime.outputs = ['{"intent":"knowledge"}', "malformed"]
    result = runtime.run("Mortality")
    assert result.error_code == "INVALID_MODEL_RESPONSE"
    assert (
        result.routing_generation_attempts,
        result.answer_generation_attempts,
        result.embedding_attempts,
    ) == (1, 1, 1)


class BodyStorage:
    def __init__(self):
        self._conn = self
        self.selected = []

    def execute(self, sql, params):
        self.selected.append(params)
        self.sql = sql
        return self

    def fetchone(self):
        return ("general", "index.faiss")

    def fetchall(self):
        return [("member", "Member title", "2026-11-06")]

    def get_kb_composition_status(self, kb_id):
        return {"latest_index": {"built_at": "2026-11-05"}, "needs_reindex": True}


@pytest.mark.parametrize("stale", [False, True])
def test_usable_ready_data_serves_exact_publication_and_never_standard(monkeypatch, stale):
    from ai_actuarial.agentic_rag import ready_data_tools
    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.chatbot import retrieval

    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {
            "manifest": {
                "usable": True,
                "output_dir": "current-publication",
                "publication_id": "current-id",
                "serving_stale": stale,
            }
        },
    )
    searched = []

    def search(*args, **kwargs):
        searched.append(kwargs["output_dir"])
        return [
            {"doc_id": "member", "section_id": "actual-section", "text_snippet": "actual body"},
            {"doc_id": "removed", "section_id": "bad", "text_snippet": "forbidden"},
        ]

    monkeypatch.setattr(ready_data_tools, "search_sections", search)
    monkeypatch.setattr(
        retrieval,
        "RAGRetriever",
        lambda *args, **kwargs: pytest.fail("No Standard fallback for usable Ready Data"),
    )
    result, failure = knowledge.body_evidence(
        BodyStorage(),
        "body",
        ["allowed"],
        config=ChatbotConfig(),
        deadline=time.monotonic() + 30,
        on_embedding=lambda: pytest.fail("no embedding"),
    )
    assert searched == ["current-publication"]
    assert len(result) == 1 and failure is None
    assert result[0].content == "actual body"
    assert result[0].citation.source_version == "current-id"
    assert result[0].citation.stale == stale


def test_hard_stale_falls_back_only_same_kb_and_current_membership(monkeypatch):
    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.chatbot import retrieval

    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {"manifest": {"usable": False}},
    )
    seen = []

    class Retriever:
        embedding_generator = SimpleNamespace(openai_client=None)

        def __init__(self, storage, config, **kwargs):
            assert kwargs["embedding_deadline"] > time.monotonic()

        def _get_vector_store(self, kb_id):
            seen.append(kb_id)

        def retrieve(self, message, *, kb_ids, **kwargs):
            seen.extend(kb_ids)
            return [
                {"content": "body", "metadata": {"file_url": file, "chunk_id": "chunk"}}
                for file in ("member", "removed")
            ]

    monkeypatch.setattr(retrieval, "RAGRetriever", Retriever)
    result, failure = knowledge.body_evidence(
        BodyStorage(),
        "body",
        ["allowed"],
        config=ChatbotConfig(),
        deadline=time.monotonic() + 30,
        on_embedding=lambda: None,
    )
    assert seen == ["allowed", "allowed"]
    assert len(result) == 1 and result[0].citation.file_id == "member" and failure is None


def test_standard_constructor_failure_does_not_discard_other_ready_evidence(monkeypatch):
    from ai_actuarial.agentic_rag import ready_data_tools
    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.chatbot import retrieval

    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda storage, *, kb_id, **kwargs: {
            "manifest": {"usable": kb_id == "ready", "output_dir": "active", "publication_id": "v1"}
        },
    )
    monkeypatch.setattr(
        ready_data_tools,
        "search_sections",
        lambda *args, **kwargs: [
            {"doc_id": "member", "section_id": "ready-section", "text_snippet": "Available body"}
        ],
    )
    monkeypatch.setattr(
        retrieval,
        "RAGRetriever",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("missing embedding key")),
    )
    result, failure = knowledge.body_evidence(
        BodyStorage(),
        "body",
        ["ready", "broken-standard"],
        config=ChatbotConfig(),
        deadline=time.monotonic() + 30,
        on_embedding=lambda: pytest.fail("No provider attempt"),
    )
    assert len(result) == 1 and result[0].citation.kb_id == "ready"
    assert failure == "KNOWLEDGE_UNAVAILABLE"


def test_ready_membership_filter_precedes_result_budget(monkeypatch, tmp_path):
    from ai_actuarial.api.services import ready_data_publication

    (tmp_path / "ready_data_manifest.json").write_text('{"profile":"general"}', encoding="utf-8")
    docs = [{"doc_id": f"removed-{i}", "title": "reserve reserve"} for i in range(5)] + [
        {"doc_id": "member", "title": "Current report"}
    ]
    sections = [
        {
            "doc_id": row["doc_id"],
            "section_id": f"section-{i}",
            "text": "reserve reserve" if i < 5 else "The reserve is 37.",
        }
        for i, row in enumerate(docs)
    ]
    for name, rows in (("doc_catalog.jsonl", docs), ("sections.jsonl", sections)):
        (tmp_path / name).write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )
    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {
            "manifest": {"usable": True, "output_dir": str(tmp_path), "publication_id": "active"}
        },
    )
    result, _ = knowledge.body_evidence(
        BodyStorage(),
        "reserve",
        ["allowed"],
        config=ChatbotConfig(),
        deadline=time.monotonic() + 30,
        on_embedding=lambda: pytest.fail("No embedding"),
    )
    assert len(result) == 1 and result[0].citation.file_id == "member"


@pytest.mark.parametrize("current_vectors", [1, 6])
def test_standard_membership_filter_fills_budget_from_rank_six(monkeypatch, current_vectors):
    import numpy as np

    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.chatbot import retrieval
    from ai_actuarial.rag.vector_store import VectorStore

    vector_store = VectorStore(
        2, config=RAGConfig(embedding_provider="local", embedding_cache_enabled=False)
    )
    vectors = np.array(
        [[1.0, 0.0]] * 5
        + [[np.cos(0.1 + i * 0.01), np.sin(0.1 + i * 0.01)] for i in range(current_vectors)]
    )
    metadata = [
        {"file_url": f"removed-{i}", "chunk_id": f"removed-{i}", "content": "Removed body"}
        for i in range(5)
    ] + [
        {"file_url": "member", "chunk_id": f"current-{i}", "content": f"Current reserve body {i}"}
        for i in range(current_vectors)
    ]
    vector_store.add_vectors(vectors, metadata)
    first_five = vector_store.search(np.array([1.0, 0.0]), k=5, similarity_threshold=0.5)
    assert len(first_five) == 5 and all(
        row["metadata"]["file_url"].startswith("removed-") for row in first_five
    )
    retriever = retrieval.RAGRetriever.__new__(retrieval.RAGRetriever)
    retriever.storage = BodyStorage()
    retriever.config = ChatbotConfig(top_k=5, similarity_threshold=0.5)
    kb = SimpleNamespace(
        kb_id="allowed",
        name="KB",
        embedding_provider="local",
        embedding_model="custom",
        embedding_dimension=2,
    )
    retriever.kb_manager = SimpleNamespace(get_kb=lambda kb_id: kb)
    retriever._vector_store_cache = {"allowed": vector_store}
    retriever._index_source_cache = {
        "allowed": {
            "index_version_id": "served-c4",
            "index_built_at": "2026-01-01",
            "index_stale": False,
        }
    }
    attempts = []

    def generate(text):
        attempts.append(text)
        return [1.0, 0.0]

    retriever.embedding_generator = SimpleNamespace(
        provider="local",
        config=SimpleNamespace(embedding_model="custom"),
        get_embedding_dimension=lambda: 2,
        generate_single=generate,
        openai_client=None,
    )
    monkeypatch.setattr(retrieval, "RAGRetriever", lambda *args, **kwargs: retriever)
    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {"manifest": {"usable": False}},
    )
    result, _ = knowledge.body_evidence(
        BodyStorage(),
        "reserve",
        ["allowed"],
        config=retriever.config,
        deadline=time.monotonic() + 30,
        on_embedding=lambda: None,
    )
    assert len(result) == min(5, current_vectors)
    assert all(
        item.citation.file_id == "member" and item.citation.source_version == "served-c4"
        for item in result
    )
    assert all("Removed" not in item.content for item in result)
    assert attempts == ["reserve"]


def test_standard_citation_uses_served_index_snapshot(monkeypatch):
    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.chatbot import retrieval

    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {"manifest": {"usable": False}},
    )

    class Retriever:
        embedding_generator = SimpleNamespace(openai_client=None)

        def __init__(self, *args, **kwargs):
            pass

        def _get_vector_store(self, kb_id):
            pass

        def retrieve(self, *args, **kwargs):
            return [
                {
                    "content": "Served body",
                    "metadata": {
                        "file_url": "member",
                        "chunk_id": "chunk-A",
                        "index_version_id": "served-A",
                        "index_built_at": "2026-01-01",
                        "index_stale": False,
                    },
                }
            ]

    monkeypatch.setattr(retrieval, "RAGRetriever", Retriever)
    result, _ = knowledge.body_evidence(
        BodyStorage(),
        "body",
        ["allowed"],
        config=ChatbotConfig(),
        deadline=time.monotonic() + 30,
        on_embedding=lambda: None,
    )
    assert result[0].citation.source_version == "served-A"
    assert result[0].citation.source_date == "2026-01-01"
    assert result[0].citation.stale is False


def test_loaded_standard_store_keeps_its_version_when_new_index_is_committed(monkeypatch, tmp_path):
    from contextlib import nullcontext

    from ai_actuarial.chatbot import retrieval

    path = tmp_path / "served.faiss"
    path.write_bytes(b"synthetic-index")
    current = {"version": "A"}

    class Connection:
        def execute(self, sql, params):
            self.version_query = "FROM kb_index_versions" in sql
            return self

        def fetchone(self):
            return (current["version"], "2026-01-01", 2) if self.version_query else (str(path),)

    class Store:
        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return [
                {
                    "score": 0.9,
                    "metadata": {"content": "body-A", "file_url": "member", "chunk_id": "chunk-A"},
                }
            ]

    monkeypatch.setattr(retrieval, "VectorStore", Store)
    retriever = retrieval.RAGRetriever.__new__(retrieval.RAGRetriever)
    retriever.storage = SimpleNamespace(
        _conn=Connection(),
        transaction=lambda **kwargs: nullcontext(),
        get_kb_composition_status=lambda kb: {"needs_reindex": current["version"] != "A"},
    )
    retriever.kb_manager = SimpleNamespace(
        get_kb=lambda kb: SimpleNamespace(name="KB", embedding_dimension=2, embedding_model="test")
    )
    retriever._vector_store_cache = {}
    retriever._index_source_cache = {}
    retriever._get_vector_store("allowed")
    current["version"] = "B"
    result = retriever._retrieve_from_kb("allowed", [0.1, 0.2], 5, 0.5)
    assert result[0]["content"] == "body-A"
    assert result[0]["metadata"]["index_version_id"] == "A"
    assert result[0]["metadata"]["index_stale"] is False


@pytest.mark.parametrize("background_repeats", [0, 1200])
def test_ready_answer_excerpt_follows_match_in_same_publication(
    runtime, monkeypatch, tmp_path, background_repeats
):
    from ai_actuarial.agentic_rag.ready_data_tools import search_sections
    from ai_actuarial.api.services import ready_data_publication

    question = "What is the lapse shock?"
    quote = "The lapse shock is 37%."
    intro = "This annual reserve report describes a closed block of long-term insurance contracts. The valuation uses the approved year-end asset data and reconciles the opening and closing balances. The following analysis presents the key assumptions used for the base calculation and the sensitivity tests. Results are shown before management actions, tax adjustments and changes to the investment strategy. All amounts use the same reporting currency and the same portfolio boundary."
    body = (
        intro
        + " Background context without the requested assumption." * background_repeats
        + "\n\n"
        + quote
    )
    if background_repeats:
        body += "\n\n" + "Closing background note. " * 200
    assert body.index(quote) > (10000 if background_repeats else 240)
    active = tmp_path / "active-publication"
    newer = tmp_path / "not-serving-publication"
    for output, text in ((active, body), (newer, "The lapse shock is 99%.")):
        output.mkdir()
        (output / "ready_data_manifest.json").write_text('{"profile":"general"}', encoding="utf-8")
        (output / "doc_catalog.jsonl").write_text(
            json.dumps({"doc_id": "member", "file_url": "member", "title": "Reserve report"})
            + "\n",
            encoding="utf-8",
        )
        (output / "sections.jsonl").write_text(
            json.dumps({"doc_id": "member", "section_id": "lapse-section", "text": text}) + "\n",
            encoding="utf-8",
        )
    assert quote not in search_sections(question, output_dir=active)[0]["text_snippet"]
    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda *args, **kwargs: {
            "manifest": {
                "usable": True,
                "output_dir": str(active),
                "publication_id": "serving-r6-v1",
                "serving_stale": True,
            }
        },
    )
    monkeypatch.setattr(
        query,
        "body_evidence",
        lambda storage, message, kb_ids, **kwargs: knowledge.body_evidence(
            BodyStorage(), message, kb_ids, **kwargs
        ),
    )
    runtime.request.app.state.assistant_public_kb_ids = ["allowed"]
    runtime.outputs = [json.dumps({"steps": [{"source": 0, "quote": quote}]})]
    result = runtime.run(question, mode="knowledge")
    source = json.loads(runtime.calls[0]["messages"][1]["content"])["sources"][0]
    assert quote in source["content"]
    assert len(source["content"]) <= 1600
    assert source["content"] in body
    assert source["citation"]["file_id"] == "member"
    assert source["citation"]["section_id"] == "lapse-section"
    assert source["citation"]["source_version"] == "serving-r6-v1"
    assert source["citation"]["stale"] is True
    assert result.availability == "available" and quote in result.answer
    assert result.citations[0].model_dump() == source["citation"]
    assert result.generation_attempts == 1 and result.embedding_attempts == 0


@pytest.mark.parametrize("mode", ["ready", "standard", "mixed"])
@pytest.mark.parametrize("public_kb_count", [1, 5])
def test_operator_staff_evidence_survives_full_public_batch_in_prompt(
    runtime, monkeypatch, tmp_path, mode, public_kb_count
):
    from ai_actuarial.agentic_rag import ready_data_tools
    from ai_actuarial.api.services import ready_data_publication
    from ai_actuarial.chatbot import retrieval
    from ai_actuarial.shared_auth import permissions_for_group

    state = runtime.request.app.state
    state.assistant_public_kb_ids = [f"public-{i}" for i in range(public_kb_count)]
    state.assistant_staff_kb_ids = ["staff"]
    support = "The staff reserve is 464."
    searched = []

    def rows(kb_id):
        return (
            [support]
            if kb_id == "staff"
            else [
                f"Generic reserve discussion {i}." for i in range(5 if public_kb_count == 1 else 1)
            ]
        )

    for kb_id in state.assistant_public_kb_ids + ["staff"]:
        output = tmp_path / kb_id
        output.mkdir()
        (output / "ready_data_manifest.json").write_text('{"profile":"general"}', encoding="utf-8")
        (output / "doc_catalog.jsonl").write_text(
            json.dumps({"doc_id": "member", "file_url": "member", "title": "Reserve report"})
            + "\n",
            encoding="utf-8",
        )
        (output / "sections.jsonl").write_text(
            "\n".join(
                json.dumps({"doc_id": "member", "section_id": f"{kb_id}-{i}", "text": text})
                for i, text in enumerate(rows(kb_id))
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        ready_data_publication,
        "read_public_ready_data_snapshot",
        lambda storage, *, kb_id, **kwargs: {
            "manifest": {
                "usable": mode == "ready" or (mode == "mixed" and kb_id == "staff"),
                "output_dir": str(tmp_path / kb_id),
                "publication_id": f"{kb_id}-v1",
            }
        },
    )
    real_search = ready_data_tools.search_sections
    ready_scores = {}

    def search(message, *, output_dir, **kwargs):
        kb_id = next(
            kb
            for kb in state.assistant_public_kb_ids + ["staff"]
            if str(tmp_path / kb) == output_dir
        )
        searched.append(kb_id)
        found = real_search(message, output_dir=output_dir, **kwargs)
        ready_scores[kb_id] = found[0]["keyword_relevance_100"]
        return found

    monkeypatch.setattr(
        ready_data_tools,
        "search_sections",
        search,
    )

    class Retriever:
        embedding_generator = SimpleNamespace(openai_client=None)

        def __init__(self, *args, **kwargs):
            pass

        def _get_vector_store(self, kb_id):
            pass

        def retrieve(self, message, *, kb_ids, **kwargs):
            assert len(kb_ids) == 1
            searched.extend(kb_ids)
            return [
                {
                    "content": text,
                    "metadata": {
                        "file_url": "member",
                        "chunk_id": f"{kb_ids[0]}-{5 - i}",
                        "similarity_score": 0.95 if kb_ids[0] == "staff" else 0.75,
                    },
                }
                for i, text in enumerate(rows(kb_ids[0]))
            ]

    monkeypatch.setattr(retrieval, "RAGRetriever", Retriever)
    monkeypatch.setattr(
        query,
        "body_evidence",
        lambda storage, message, kb_ids, **kwargs: knowledge.body_evidence(
            BodyStorage(), message, kb_ids, **kwargs
        ),
    )
    runtime.outputs = [json.dumps({"steps": [{"source": 0, "quote": support}]})]
    result = runtime.run(
        "What is the staff reserve?",
        mode="knowledge",
        auth=AuthContext({"group_name": "operator"}, permissions_for_group("operator")),
    )
    prompt = json.loads(runtime.calls[0]["messages"][1]["content"])
    assert searched == state.assistant_public_kb_ids + ["staff"]
    if mode != "standard":
        assert ready_scores["staff"] == 7
    assert len(prompt["sources"]) == 5
    assert any(source["content"] == support for source in prompt["sources"])
    assert prompt["sources"][0]["content"] == support
    assert prompt["sources"][0]["citation"]["kb_id"] == "staff"
    assert support in result.answer
    assert result.citations[0].kb_id == "staff"
    assert result.citations[0].file_id == "member"
    assert result.citations[0].section_id.startswith("staff-")
    assert result.generation_attempts == 1
    if public_kb_count == 1:
        assert [
            source["content"]
            for source in prompt["sources"]
            if source["citation"]["kb_id"] != "staff"
        ] == [f"Generic reserve discussion {i}." for i in range(4)]


def test_embedding_provider_attempts_include_dimension_probe_and_bounded_retries(monkeypatch):
    from ai_actuarial.rag import embeddings

    requests = []
    attempts = []
    always_fail = False

    def transport(request):
        requests.append(request)
        if always_fail or len(requests) == 2:
            return httpx.Response(429, json={"error": {"message": "busy", "type": "rate_limit"}})
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                "model": "custom",
                "object": "list",
            },
        )

    sdk = openai.OpenAI(
        api_key="unit-test-only",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    monkeypatch.setattr(embeddings, "OpenAI", lambda **kwargs: sdk)
    monkeypatch.setattr(embeddings.time, "sleep", lambda delay: None)
    config = RAGConfig(
        api_key="unit-test-only",
        embedding_model="custom-unknown",
        embedding_cache_enabled=False,
        openai_max_retries=99,
    )
    generator = EmbeddingGenerator(
        config, deadline=time.monotonic() + 10, on_attempt=lambda: attempts.append(1)
    )
    try:
        assert generator.get_embedding_dimension() == 2
        assert generator.generate_single("query") == [0.1, 0.2]
        assert len(requests) == len(attempts) == 3
        assert all(request.extensions["timeout"]["read"] <= 10 for request in requests)
        always_fail = True
        requests.clear()
        attempts.clear()
        with pytest.raises(Exception, match="after 3 retries"):
            generator.generate_single("failing query")
        assert len(requests) == len(attempts) == 3
        generator.deadline = time.monotonic() - 1
        requests.clear()
        attempts.clear()
        with pytest.raises(TimeoutError):
            generator.generate_single("expired query")
        assert not requests and not attempts
    finally:
        sdk.close()


def test_catalog_projection_never_searches_markdown_or_exposes_internal_fields(tmp_path):
    from ai_actuarial.storage import Storage
    from tests.postgres_helpers import postgres_url_for_path

    storage = Storage(postgres_url_for_path(tmp_path / "catalog.db"))
    try:
        storage._conn.execute(
            "INSERT INTO files (url, title, local_path, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
            ("source", "Mortality", "private-path", "now", "now"),
        )
        storage._conn.execute(
            "INSERT INTO catalog_items (file_url, sha256, pipeline_version, summary, markdown_content, catalog_version) VALUES (?, ?, ?, ?, ?, ?)",
            ("source", "test-hash", "v1", "Public summary", "private-body-only-marker", "v1"),
        )
        storage._conn.commit()
        assert storage.search_catalog_projection(["private-body-only-marker"]) == []
        result = knowledge.catalog_evidence(storage, "What materials about mortality?", zh=False)
        assert len(result) == 1 and result[0].citation.source_type == "catalog"
        assert "Public summary" in result[0].content
        assert "private" not in result[0].content and "markdown" not in result[0].content
        assert len(knowledge.catalog_evidence(storage, "有哪些资料", zh=True)) == 1
        questions = (
            "List documents",
            "List all documents",
            "What materials are available?",
            "Show me all documents",
            "Please list all documents",
            "Which materials do we have?",
            "Could you please list all documents?",
            "Would you show me all documents?",
        )
        listings = {
            question: [
                item.citation.file_id
                for item in knowledge.catalog_evidence(storage, question, zh=False)
            ]
            for question in questions
        }
        assert listings == {question: ["source"] for question in questions}
        for question in (
            "Show me all mortality documents",
            "Please list all mortality documents",
            "Which materials do we have about mortality?",
        ):
            assert len(knowledge.catalog_evidence(storage, question, zh=False)) == 1, question
        assert (
            knowledge.catalog_evidence(storage, "Please list all climate documents", zh=False) == []
        )
        assert knowledge.catalog_evidence(storage, "Show me all US documents", zh=False) == []
    finally:
        storage.close()

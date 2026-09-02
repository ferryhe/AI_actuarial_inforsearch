from __future__ import annotations

import math

import pytest

from ai_actuarial.agentic_rag import agentic_loop
from ai_actuarial.agentic_rag.ready_data_tools import (
    _tokens,
    search_calculation_terms,
    search_formula_cards,
    search_sections,
    search_structured_tables,
    search_summaries,
    search_titles,
    trace_relations,
)
from ai_actuarial.api.services import chat as chat_service
from ai_actuarial.retrieval_indicators import (
    build_retrieval_indicators,
    normalize_keyword_relevance,
    normalize_retrieval_method,
    normalize_semantic_relevance,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (-0.1, 0),
        (0, 0),
        (0.834, 83),
        (1, 100),
        (1.2, 100),
        (math.nan, None),
        (None, None),
        ("not-a-score", None),
    ],
)
def test_semantic_relevance_normalizes_only_finite_similarity_scores(raw, expected) -> None:
    assert normalize_semantic_relevance(raw) == expected


@pytest.mark.parametrize(
    ("source", "tool", "expected"),
    [
        ("vector", None, "vector"),
        ("similarity", None, "vector"),
        ("doc_summaries", None, "summaries"),
        ("doc_catalog", "search_summaries", "summaries"),
        ("sections", "search_summaries", "sections"),
        ("title_aliases", None, "titles"),
        ("doc_catalog", "search_titles", "titles"),
        ("sections", None, "sections"),
        ("sections_structured", None, "sections"),
        ("relations_graph", None, "relations"),
        ("formula_cards", None, "formulas"),
        ("tables_structured", None, "tables"),
        ("calculation_terms", None, "calculation_terms"),
        ("future_source", None, "other"),
        ("doc_catalog", None, "other"),
    ],
)
def test_retrieval_method_mapping_is_stable_and_ambiguous_catalog_is_safe(
    source, tool, expected
) -> None:
    assert normalize_retrieval_method(source=source, tool=tool) == expected


def test_explicit_retrieval_method_has_priority_over_source_and_tool() -> None:
    assert (
        normalize_retrieval_method(
            source="sections",
            tool="search_summaries",
            method="vector",
        )
        == "vector"
    )


@pytest.mark.parametrize(
    ("name", "token_count", "weight_sum", "boost"),
    [
        ("summaries", 2, 8.75, 3.0),
        ("titles", 2, 7.75, 4.0),
        ("sections", 2, 13.0, 3.0),
        ("formulas", 2, 16.5, 4.0),
        ("tables", 2, 13.0, 4.0),
        ("calculation_terms", 2, 11.5, 6.0),
        ("relations", 2, 2.0, 5.0),
    ],
)
def test_seven_weighted_tools_normalize_zero_mid_max_and_over_max(
    name: str,
    token_count: int,
    weight_sum: float,
    boost: float,
) -> None:
    theoretical_max = token_count * weight_sum + boost
    assert normalize_keyword_relevance(0, theoretical_max) == 0, name
    assert normalize_keyword_relevance(theoretical_max / 2, theoretical_max) == 50, name
    assert normalize_keyword_relevance(theoretical_max, theoretical_max) == 100, name
    assert normalize_keyword_relevance(theoretical_max * 2, theoretical_max) == 100, name


def test_keyword_relevance_needs_query_context_and_title_alias_keeps_native_scale() -> None:
    assert normalize_keyword_relevance(20, None) is None
    assert normalize_keyword_relevance(88.5, 100) == 88
    assert normalize_keyword_relevance(100, 100) == 100
    assert normalize_keyword_relevance(math.nan, 100) is None


def test_cjk_bigram_token_context_contributes_to_theoretical_maximum() -> None:
    tokens = _tokens("最低资本")
    assert tokens == ["最低资本", "最低", "低资", "资本"]
    theoretical_max = len(tokens) * 8.75 + 3.0
    assert normalize_keyword_relevance(theoretical_max, theoretical_max) == 100


@pytest.mark.parametrize(
    "tool",
    [
        search_summaries,
        search_titles,
        search_sections,
        search_formula_cards,
        search_structured_tables,
        search_calculation_terms,
        trace_relations,
    ],
)
def test_empty_query_does_not_fabricate_keyword_relevance(tool, tmp_path) -> None:
    assert tool("   ", output_dir=tmp_path) == []


def test_shared_builder_returns_nullable_contract_without_mixing_raw_score_as_similarity() -> None:
    assert build_retrieval_indicators(
        similarity_score=None,
        keyword_score=16.5,
        keyword_max=33.0,
        source="formula_cards",
    ) == {
        "semantic_relevance_100": None,
        "keyword_relevance_100": 50,
        "retrieval_method": "formulas",
    }


def test_shared_builder_prefers_explicit_canonical_semantic_relevance() -> None:
    assert (
        build_retrieval_indicators(
            similarity_score=0.2,
            semantic_relevance_100=73,
            source="vector",
        )["semantic_relevance_100"]
        == 73
    )
    assert (
        build_retrieval_indicators(
            similarity_score=0.9,
            semantic_relevance_100=math.nan,
            source="vector",
        )["semantic_relevance_100"]
        is None
    )


def test_standard_chat_serializer_preserves_only_canonical_semantic_relevance() -> None:
    citations, blocks = chat_service._serialize_citations(
        [
            {
                "content": "canonical vector chunk",
                "metadata": {
                    "filename": "vector.pdf",
                    "semantic_relevance_100": 73,
                    "source": "vector",
                },
            }
        ]
    )

    assert [item["semantic_relevance_100"] for item in [*citations, *blocks]] == [73, 73]


@pytest.mark.parametrize(
    ("similarity_score", "expected_method"),
    [
        (math.nan, "other"),
        ("not-a-score", "other"),
        (0, "vector"),
        (0.9, "vector"),
    ],
)
def test_standard_chat_infers_vector_only_from_finite_similarity(
    similarity_score, expected_method
) -> None:
    citations, blocks = chat_service._serialize_citations(
        [
            {
                "content": "legacy vector chunk",
                "metadata": {"similarity_score": similarity_score},
            }
        ]
    )

    for item in [*citations, *blocks]:
        assert item["retrieval_method"] == expected_method
        if expected_method == "other":
            assert item["semantic_relevance_100"] is None


@pytest.mark.parametrize(
    "document_sources",
    [
        [],
        [
            {
                "content": "Explicit document source",
                "filename": "explicit.pdf",
                "file_url": "/api/files/2",
            }
        ],
    ],
)
def test_direct_document_chunks_do_not_fabricate_retrieval_indicators(
    document_sources,
) -> None:
    chunks, _notice = chat_service._prepare_document_source_chunks(
        document_content="Direct document content",
        document_filename="direct.pdf",
        document_file_url="/api/files/1",
        document_sources=document_sources,
    )

    citations, blocks = chat_service._serialize_citations(chunks)

    for item in [*citations, *blocks]:
        assert item["similarity_score"] == 1.0
        assert item["semantic_relevance_100"] is None
        assert item["keyword_relevance_100"] is None
        assert item["retrieval_method"] == "other"


def test_standard_chat_serializer_suppresses_stale_direct_document_indicators() -> None:
    citations, blocks = chat_service._serialize_citations(
        [
            {
                "content": "Direct document content",
                "metadata": {
                    "kb_id": "document_explanation",
                    "similarity_score": 1.0,
                    "semantic_relevance_100": 100,
                    "keyword_relevance_100": 88,
                    "retrieval_method": "vector",
                },
            }
        ]
    )

    for item in [*citations, *blocks]:
        assert item["similarity_score"] == 1.0
        assert item["semantic_relevance_100"] is None
        assert item["keyword_relevance_100"] is None
        assert item["retrieval_method"] == "other"


def test_agentic_serializer_preserves_only_canonical_semantic_relevance() -> None:
    citations, blocks = chat_service._serialize_agentic_evidence(
        [
            {
                "file_url": "https://example.com/formula.pdf",
                "semantic_relevance_100": 73,
                "source": "formula_cards",
            }
        ],
        kb_id="kb-1",
    )

    assert [item["semantic_relevance_100"] for item in [*citations, *blocks]] == [73, 73]


def test_history_backfill_preserves_only_canonical_semantic_relevance() -> None:
    messages = [
        {
            "citations": [{"semantic_relevance_100": 73, "source": "vector"}],
            "metadata": {"retrieved_blocks": [{"semantic_relevance_100": 73, "source": "vector"}]},
        }
    ]

    chat_service._backfill_retrieval_indicators(messages)

    assert messages[0]["citations"][0]["semantic_relevance_100"] == 73
    assert messages[0]["metadata"]["retrieved_blocks"][0]["semantic_relevance_100"] == 73


@pytest.mark.parametrize(
    ("similarity_score", "expected_method"),
    [
        (math.nan, "other"),
        ("not-a-score", "other"),
        (0, "vector"),
        (0.9, "vector"),
    ],
)
def test_history_infers_vector_only_from_finite_similarity(
    similarity_score, expected_method
) -> None:
    messages = [{"citations": [{"similarity_score": similarity_score}]}]

    chat_service._backfill_retrieval_indicators(messages)

    citation = messages[0]["citations"][0]
    assert citation["retrieval_method"] == expected_method
    if expected_method == "other":
        assert citation["semantic_relevance_100"] is None


def test_history_suppresses_document_explanation_retrieval_indicators() -> None:
    messages = [
        {
            "citations": [
                {
                    "kb_id": "document_explanation",
                    "similarity_score": 1.0,
                    "semantic_relevance_100": 100,
                    "keyword_relevance_100": 88,
                    "retrieval_method": "vector",
                }
            ],
            "metadata": {
                "retrieved_blocks": [
                    {
                        "kb_id": "document_explanation",
                        "similarity_score": 1.0,
                        "semantic_relevance_100": 100,
                        "keyword_relevance_100": 88,
                        "retrieval_method": "vector",
                    }
                ]
            },
        }
    ]

    chat_service._backfill_retrieval_indicators(messages)

    references = [
        messages[0]["citations"][0],
        messages[0]["metadata"]["retrieved_blocks"][0],
    ]
    for reference in references:
        assert reference["similarity_score"] == 1.0
        assert reference["retrieval_method"] == "other"
        assert reference["semantic_relevance_100"] is None
        assert reference["keyword_relevance_100"] is None


def test_explicit_similarity_source_maps_to_vector_without_a_score() -> None:
    citations, blocks = chat_service._serialize_citations(
        [{"content": "explicit vector source", "metadata": {"source": "similarity"}}]
    )
    messages = [{"citations": [{"source": "similarity"}]}]
    chat_service._backfill_retrieval_indicators(messages)

    assert all(item["retrieval_method"] == "vector" for item in [*citations, *blocks])
    assert messages[0]["citations"][0]["retrieval_method"] == "vector"


def test_agentic_citation_preserves_only_canonical_semantic_relevance() -> None:
    citation = agentic_loop._citation_record(
        {
            "doc_id": "doc-1",
            "source": "sections_structured",
            "semantic_relevance_100": 73,
        }
    )

    assert citation is not None
    assert citation["semantic_relevance_100"] == 73


def test_chat_vector_and_agentic_serializers_share_indicator_contract() -> None:
    citations, blocks = chat_service._serialize_citations(
        [
            {
                "content": "vector chunk",
                "metadata": {
                    "filename": "vector.pdf",
                    "similarity_score": 0.834,
                    "source": "similarity",
                },
            }
        ]
    )
    for item in [*citations, *blocks]:
        assert item["semantic_relevance_100"] == 83
        assert item["keyword_relevance_100"] is None
        assert item["retrieval_method"] == "vector"
        assert item["similarity_score"] == 0.834

    citations, blocks = chat_service._serialize_agentic_evidence(
        [
            {
                "file_url": "https://example.com/formula.pdf",
                "score": 16.5,
                "keyword_relevance_100": 50,
                "retrieval_method": "formulas",
                "source": "formula_cards",
            }
        ],
        kb_id="kb-1",
    )
    for item in [*citations, *blocks]:
        assert item["semantic_relevance_100"] is None
        assert item["keyword_relevance_100"] == 50
        assert item["retrieval_method"] == "formulas"
        assert item["score"] == 16.5
        assert "similarity_score" not in item


def test_agentic_synthesis_chunks_do_not_relabel_raw_keyword_score_as_similarity() -> None:
    chunks = chat_service._agentic_blocks_to_llm_chunks(
        [
            {
                "filename": "formula.pdf",
                "content": "formula evidence",
                "score": 16.5,
                "semantic_relevance_100": None,
                "keyword_relevance_100": 50,
                "retrieval_method": "formulas",
            }
        ]
    )

    metadata = chunks[0]["metadata"]
    assert metadata["score"] == 16.5
    assert metadata["semantic_relevance_100"] is None
    assert metadata["keyword_relevance_100"] == 50
    assert metadata["retrieval_method"] == "formulas"
    assert "similarity_score" not in metadata


def test_history_backfill_keeps_legacy_messages_open_without_inventing_keyword_score() -> None:
    messages = [
        {
            "citations": [
                {"similarity_score": 0.9},
                {"score": 16.5, "source": "formula_cards"},
                {"score": 88.5, "source": "future_source"},
            ],
            "metadata": {
                "retrieved_blocks": [
                    {"similarity_score": math.nan, "source": "similarity"},
                    {"score": 100, "source": "title_aliases"},
                ]
            },
        }
    ]
    chat_service._backfill_retrieval_indicators(messages)

    vector, formula, unknown = messages[0]["citations"]
    assert vector["semantic_relevance_100"] == 90
    assert vector["keyword_relevance_100"] is None
    assert vector["retrieval_method"] == "vector"
    assert formula["semantic_relevance_100"] is None
    assert formula["keyword_relevance_100"] is None
    assert formula["retrieval_method"] == "formulas"
    assert unknown["retrieval_method"] == "other"
    assert unknown["keyword_relevance_100"] is None

    nan_vector, title = messages[0]["metadata"]["retrieved_blocks"]
    assert nan_vector["semantic_relevance_100"] is None
    assert title["keyword_relevance_100"] is None
    assert title["retrieval_method"] == "titles"


def test_agentic_response_citation_preserves_all_three_indicators() -> None:
    citation = agentic_loop._citation_record(
        {
            "doc_id": "doc-1",
            "source": "sections_structured",
            "score": 12.5,
            "semantic_relevance_100": None,
            "keyword_relevance_100": 72,
            "retrieval_method": "sections",
        }
    )
    assert citation is not None
    assert citation["semantic_relevance_100"] is None
    assert citation["keyword_relevance_100"] == 72
    assert citation["retrieval_method"] == "sections"
    assert citation["score"] == 12.5

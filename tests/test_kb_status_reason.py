"""Regression coverage for #349's KB serving/operations separation."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_actuarial.kb_status import KB_STATUS_REASONS, classify_kb_status


@pytest.mark.parametrize(
    ("name", "composition", "compatible", "kwargs", "reason", "serving"),
    [
        ("embedding", {"has_index": True}, False, {}, "embedding_incompatible", False),
        ("content", {"has_index": True, "pending_file_count": 1}, True, {}, "content_dirty", True),
        (
            "binding",
            {"has_index": True, "outdated_binding_count": 1},
            True,
            {},
            "binding_dirty",
            True,
        ),
        ("missing", {"has_index": False}, True, {}, "index_missing", False),
        (
            "building",
            {"has_index": True, "latest_index": {"status": "building"}},
            True,
            {},
            "index_building",
            False,
        ),
        ("publish", {"has_index": True}, True, {"publish_failed": True}, "publish_failed", True),
        (
            "disabled",
            {"has_index": True},
            True,
            {"serving_enabled": False},
            "serving_disabled",
            False,
        ),
        ("healthy", {"has_index": True}, True, {}, "healthy", True),
    ],
)
def test_kb_status_reason_is_explicit_and_keeps_serving_separate(
    name: str,
    composition: dict[str, object],
    compatible: bool,
    kwargs: dict[str, object],
    reason: str,
    serving: bool,
) -> None:
    del name
    status = classify_kb_status(
        composition=composition,
        embedding_compatible=compatible,
        **kwargs,
    )

    assert status["reason"] == reason
    assert status["serving"] is serving
    assert status["needs_reembed"] is (reason == "embedding_incompatible")


def test_all_shipped_reason_values_are_covered() -> None:
    assert KB_STATUS_REASONS == {
        "embedding_incompatible",
        "content_dirty",
        "binding_dirty",
        "index_missing",
        "index_building",
        "publish_failed",
        "serving_disabled",
        "healthy",
    }


def test_frontend_maps_every_reason_and_uses_serving_for_ask_ai() -> None:
    root = Path(__file__).resolve().parents[1] / "client" / "src"
    helper = (root / "lib" / "kb-status.ts").read_text(encoding="utf-8")
    knowledge = (root / "pages" / "Knowledge.tsx").read_text(encoding="utf-8")
    detail = (root / "pages" / "KBDetail.tsx").read_text(encoding="utf-8")
    chat = (root / "pages" / "Chat.tsx").read_text(encoding="utf-8")
    i18n = (root / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")

    for reason in KB_STATUS_REASONS:
        assert f'"{reason}"' in helper
        assert f'"knowledge.kb_status.{reason}"' in i18n
    assert 'return kb.reason === "embedding_incompatible";' in helper
    assert "kb.serving ?? kb.usable" in helper
    assert "isAskAiAvailable(kb)" in knowledge
    assert "isAskAiAvailable(meta)" in detail
    assert "knowledge.kb_status.${kb.reason}" in chat


def test_three_healthy_kbs_with_generic_reindex_are_still_ask_ai_servable() -> None:
    # Production regression: all/regulation/ai reported generic reindex work
    # while their compatible completed index and embeddings remained usable.
    for kb_id in ("all", "regulation", "ai"):
        status = classify_kb_status(
            composition={
                "has_index": True,
                "needs_reindex": True,
                "latest_index": {"status": "ready"},
            },
            embedding_compatible=True,
        )
        assert kb_id
        assert status == {
            "reason": "content_dirty",
            "needs_reembed": False,
            "serving": True,
            "availability": "ready",
        }

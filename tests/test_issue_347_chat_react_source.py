from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_failure_is_single_structured_failed_turn_with_retry() -> None:
    source = (ROOT / "client/src/pages/Chat.tsx").read_text(encoding="utf-8")
    failure = (ROOT / "client/src/pages/chat/failure.tsx").read_text(encoding="utf-8")
    assert 'status !== "failed"' in failure
    assert "retryFailedMessage" in source
    assert 't("chat.retry")' in failure
    assert (
        'const assistantMsg: Message = {\n        role: "assistant",\n        content: errorDetail'
        not in source
    )


def test_chat_maps_stable_provider_codes_to_localized_copy() -> None:
    source = (ROOT / "client/src/pages/chat/failure.tsx").read_text(encoding="utf-8")
    for code in (
        "CHAT_CONTEXT_TOO_LARGE",
        "CHAT_PROVIDER_TIMEOUT",
        "CHAT_PROVIDER_UPSTREAM",
        "CHAT_KB_UNAVAILABLE",
        "CHAT_CONVERSATION_FAILED",
        "CHAT_AGENTIC_UNAVAILABLE",
        "CHAT_PROCESSING_FAILED",
    ):
        assert code in source
    locale = (ROOT / "client/src/hooks/use-i18n.ts").read_text(encoding="utf-8")
    assert locale.count('"chat.error.context_too_large"') == 2
    assert locale.count('"chat.error.provider_timeout"') == 2
    assert locale.count('"chat.error.provider_upstream"') == 2
    assert locale.count('"chat.error.kb_unavailable"') == 2
    assert locale.count('"chat.error.conversation_failed"') == 2
    assert locale.count('"chat.error.agentic_unavailable"') == 2
    assert locale.count('"chat.error.processing_failed"') == 2

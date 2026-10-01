from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import APITimeoutError, BadRequestError, InternalServerError

from ai_actuarial.api.services import chat as chat_service
from ai_actuarial.chatbot import exceptions
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.conversation import ConversationManager
from ai_actuarial.chatbot.llm import LLMClient
from ai_actuarial.chatbot.prompts import build_full_prompt
from ai_actuarial.chatbot.retrieval import RAGRetriever
from ai_actuarial.chatbot.router import QueryRouter
from ai_actuarial.rag.knowledge_base import KnowledgeBase
from ai_actuarial.storage import Storage


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(expose_error_details=True)),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={},
        cookies={},
    )


def _config() -> ChatbotConfig:
    return ChatbotConfig(
        api_key="local-test-key",
        model="gpt-4",
        max_context_tokens=1260,
        max_tokens=60,
        length_recovery_enabled=False,
        max_retries=3,
        retry_delay=0,
        _apply_env_defaults=False,
    )


def _missing_provider_key_config() -> ChatbotConfig:
    return ChatbotConfig(
        api_key=None,
        llm_provider="mistral",
        model="mistral-large-latest",
        max_context_tokens=1260,
        max_tokens=60,
        length_recovery_enabled=False,
        max_retries=3,
        retry_delay=0,
        _apply_env_defaults=False,
    )


def _install_chat_modules(
    monkeypatch,
    llm_client_class,
    config: ChatbotConfig,
    retriever_class=None,
    router_class=None,
) -> None:
    class ConfigModule:
        class ChatbotConfig:
            @staticmethod
            def from_config(storage=None, default_mode="expert"):
                return config

    class Retriever:
        last_effective_threshold = 0.35

        def __init__(self, storage, _active_config):
            pass

        def retrieve(self, query, kb_ids):
            return [
                {
                    "content": "ordinary Standard RAG evidence",
                    "metadata": {
                        "filename": "standard.pdf",
                        "file_url": "https://example.test/standard",
                    },
                }
            ]

    monkeypatch.setattr(chat_service, "_enforce_chat_quota", lambda **kwargs: None)
    monkeypatch.setattr(
        chat_service, "_resolve_chat_user", lambda request, auth: ("user-347", None)
    )
    monkeypatch.setattr(
        chat_service,
        "_full_chat_modules",
        lambda: {
            "config": ConfigModule,
            "conversation": SimpleNamespace(ConversationManager=ConversationManager),
            "exceptions": exceptions,
            "retrieval": SimpleNamespace(RAGRetriever=retriever_class or Retriever),
            "llm": SimpleNamespace(LLMClient=llm_client_class),
            "router": SimpleNamespace(QueryRouter=router_class or (lambda *args, **kwargs: None)),
        },
    )


class BudgetLLMClient:
    generated_messages: list[list[dict[str, str]]] = []
    standard_histories: list[list[dict[str, str]]] = []

    def __init__(self, config, storage=None):
        self.config = config

    def count_tokens(self, text: str, model=None) -> int:
        # Deliberately expensive Chinese tokenization exposes the old character cap.
        return sum(1 if "\u4e00" <= char <= "\u9fff" else 0.25 for char in text).__ceil__()

    def generate(self, messages):
        type(self).generated_messages.append(messages)
        return "Bounded explanation"

    def generate_response(self, query, chunks, mode, conversation_history):
        type(self).standard_histories.append(conversation_history)
        return "Standard RAG answer"


class HistoryBudgetLLMClient(BudgetLLMClient):
    generated_messages: list[list[dict[str, str]]] = []
    reject_once = False

    def generate(self, messages):
        type(self).generated_messages.append(messages)
        if type(self).reject_once and len(type(self).generated_messages) == 1:
            raise exceptions.LLMContextLengthError()
        return "Tiny document explanation"


def test_direct_document_budget_drops_oldest_history_before_tiny_evidence(
    tmp_path, monkeypatch
) -> None:
    HistoryBudgetLLMClient.generated_messages = []
    HistoryBudgetLLMClient.reject_once = True
    config = ChatbotConfig(
        api_key="local-test-key",
        model="gpt-4o-mini",
        max_context_tokens=8000,
        max_tokens=1000,
        length_recovery_enabled=True,
        length_recovery_max_tokens=4000,
        max_messages=2,
        max_retries=0,
        retry_delay=0,
        _apply_env_defaults=False,
    )
    _install_chat_modules(monkeypatch, HistoryBudgetLLMClient, config)
    db_path = str(tmp_path / "chat.db")
    storage = Storage(db_path)
    try:
        manager = ConversationManager(storage, config)
        conversation_id = manager.create_conversation(user_id="user-347", mode="expert")
        manager.add_message(
            conversation_id,
            "user",
            "旧问题",
            metadata={"status": "succeeded"},
        )
        manager.add_message(
            conversation_id,
            "assistant",
            "精算监管要求" * 900,
            metadata={"status": "succeeded"},
        )
        manager.add_message(
            conversation_id,
            "user",
            "失败历史",
            metadata={"status": "failed"},
        )
        manager.add_message(
            conversation_id,
            "assistant",
            "等待历史",
            metadata={"status": "pending"},
        )
        manager.add_message(
            conversation_id,
            "user",
            "最近问题",
            metadata={"status": "succeeded"},
        )
        manager.add_message(
            conversation_id,
            "assistant",
            "最新有用历史",
            metadata={"status": "succeeded"},
        )
    finally:
        storage.close()

    result, _session = chat_service.query_chat(
        db_path=db_path,
        request=_request(),
        auth=None,
        payload={
            "conversation_id": conversation_id,
            "message": "解释短文件",
            "document_content": "短文件证据",
            "document_filename": "tiny.md",
            "document_file_url": "https://example.test/tiny.md",
        },
    )

    assert result["data"]["response"] == "Tiny document explanation"
    assert result["data"]["citations"][0]["file_url"] == "https://example.test/tiny.md"
    assert len(HistoryBudgetLLMClient.generated_messages) == 2
    for sent_messages in HistoryBudgetLLMClient.generated_messages:
        sent_prompt = json.dumps(sent_messages, ensure_ascii=False)
        assert "[Document 1]" in sent_prompt
        assert "UNTRUSTED CONTEXT FROM KNOWLEDGE BASE" in sent_prompt
        assert "最新有用历史" in sent_prompt
        assert "精算监管要求" * 900 not in sent_prompt
        assert (
            chat_service._estimated_message_tokens(
                HistoryBudgetLLMClient(config), sent_messages, config.model
            )
            + config.length_recovery_max_tokens
            <= config.max_context_tokens
        )
    assert "短文件证据" in json.dumps(
        HistoryBudgetLLMClient.generated_messages[0], ensure_ascii=False
    )


def test_standard_rag_uses_newest_successful_history_after_effective_limit(
    tmp_path, monkeypatch
) -> None:
    BudgetLLMClient.standard_histories = []
    config = _config()
    config.max_messages = 2
    _install_chat_modules(monkeypatch, BudgetLLMClient, config)
    db_path = str(tmp_path / "chat.db")
    storage = Storage(db_path)
    try:
        manager = ConversationManager(storage, config)
        conversation_id = manager.create_conversation(user_id="user-347", mode="expert")
        manager.add_message(
            conversation_id,
            "assistant",
            "过时成功历史",
            metadata={"status": "succeeded"},
        )
        manager.add_message(
            conversation_id,
            "user",
            "失败历史",
            metadata={"status": "failed"},
        )
        manager.add_message(
            conversation_id,
            "assistant",
            "等待历史",
            metadata={"status": "pending"},
        )
        manager.add_message(
            conversation_id,
            "user",
            "最近成功问题",
            metadata={"status": "succeeded"},
        )
        manager.add_message(
            conversation_id,
            "assistant",
            "最新成功回答",
            metadata={"status": "succeeded"},
        )
        assert [
            message["content"] for message in manager.get_messages(conversation_id, limit=3)
        ] == ["等待历史", "最近成功问题", "最新成功回答"]
    finally:
        storage.close()

    result, _session = chat_service.query_chat(
        db_path=db_path,
        request=_request(),
        auth=None,
        payload={
            "conversation_id": conversation_id,
            "message": "继续检索",
            "kb_ids": ["kb-1"],
        },
    )

    assert result["data"]["response"] == "Standard RAG answer"
    assert BudgetLLMClient.standard_histories == [
        [
            {"role": "user", "content": "最近成功问题"},
            {"role": "assistant", "content": "最新成功回答"},
        ]
    ]


def test_direct_document_budget_counts_full_prompt_and_preserves_untrusted_boundary(
    tmp_path, monkeypatch
) -> None:
    BudgetLLMClient.generated_messages = []
    config = _config()
    _install_chat_modules(monkeypatch, BudgetLLMClient, config)
    document = "精算" * 500

    result, _session = chat_service.query_chat(
        db_path=str(tmp_path / "chat.db"),
        request=_request(),
        auth=None,
        payload={
            "message": "请解释这份文件",
            "document_content": document,
            "document_filename": "长文档.md",
            "document_file_url": "https://example.test/long-cn",
        },
    )

    metadata = result["data"]["metadata"]
    diagnostic = metadata["context_notice"]
    sent = json.dumps(
        BudgetLLMClient.generated_messages[0], ensure_ascii=False, separators=(",", ":")
    )
    assert (
        BudgetLLMClient(config).count_tokens(sent, config.model) + config.max_tokens
        <= config.max_context_tokens
    )
    assert diagnostic["original_chars"] == len(document)
    assert diagnostic["used_chars"] < len(document)
    assert (
        diagnostic["estimated_prompt_tokens"] + diagnostic["output_reserve"]
        <= config.max_context_tokens
    )
    assert diagnostic["model"] == config.model
    assert "UNTRUSTED CONTEXT" in sent
    assert result["data"]["citations"][0]["filename"] == "长文档.md"


def test_context_rejection_retries_once_then_persists_safe_failed_turn(
    tmp_path, monkeypatch, caplog
) -> None:
    secret_document = "SENSITIVE-DOCUMENT-BODY-347-" + ("中" * 400)

    class RejectingClient(BudgetLLMClient):
        calls: list[int] = []

        def generate(self, messages):
            serialized = json.dumps(messages, ensure_ascii=False)
            type(self).calls.append(len(serialized))
            raise exceptions.LLMException(
                "safe context rejection",
                code="LLM_CONTEXT_LENGTH",
                classification="context_length",
                retryable=True,
            )

    RejectingClient.calls = []
    _install_chat_modules(monkeypatch, RejectingClient, _config())

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={
                "message": "Explain safely",
                "document_content": secret_document,
                "document_filename": "safe.md",
                "document_file_url": "https://example.test/safe",
            },
        )

    error = exc_info.value
    assert error.payload["code"] == "CHAT_CONTEXT_TOO_LARGE"
    assert error.payload["retryable"] is True
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert error.payload["conversation_id"] == error.payload["data"]["conversation_id"]
    assert error.payload["message_id"] == error.payload["data"]["message_id"]
    assert len(RejectingClient.calls) == 2
    assert RejectingClient.calls[1] < RejectingClient.calls[0]

    storage = Storage(str(tmp_path / "chat.db"))
    try:
        rows = storage._conn.execute(
            "SELECT role, content, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0:2] == ("user", "Explain safely")
    failed = json.loads(rows[0][2])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "CHAT_CONTEXT_TOO_LARGE"
    assert failed["retryable"] is True
    assert failed["retry_request"]["document_sources"] == [
        {"filename": "safe.md", "title": "", "file_url": "https://example.test/safe"}
    ]
    persisted = json.dumps(failed)
    assert secret_document not in persisted
    assert "local-test-key" not in persisted
    assert secret_document not in caplog.text
    assert "local-test-key" not in caplog.text


def test_standard_rag_path_keeps_existing_generate_response_contract(tmp_path, monkeypatch) -> None:
    BudgetLLMClient.generated_messages = []
    _install_chat_modules(monkeypatch, BudgetLLMClient, _config())

    result, _session = chat_service.query_chat(
        db_path=str(tmp_path / "chat.db"),
        request=_request(),
        auth=None,
        payload={"message": "ordinary question", "kb_ids": ["kb-1"]},
    )

    assert result["data"]["response"] == "Standard RAG answer"
    assert result["data"]["citations"][0]["filename"] == "standard.pdf"
    assert BudgetLLMClient.generated_messages == []


def test_failed_turn_is_not_replayed_to_direct_document_llm_but_success_history_is(
    tmp_path, monkeypatch
) -> None:
    query = "Explain retry history exactly once"

    class RecordingClient(BudgetLLMClient):
        calls: list[list[dict[str, str]]] = []

        def generate(self, messages):
            type(self).calls.append(messages)
            if len(type(self).calls) == 1:
                raise exceptions.LLMUpstreamError("temporary provider failure")
            return "Recovered explanation"

    RecordingClient.calls = []
    _install_chat_modules(monkeypatch, RecordingClient, _config())
    db_path = str(tmp_path / "chat.db")
    document_payload = {
        "message": query,
        "document_content": "ALPHA actuarial evidence",
        "document_filename": "alpha.md",
        "document_file_url": "https://example.test/alpha",
    }

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=db_path,
            request=_request(),
            auth=None,
            payload=document_payload,
        )
    conversation_id = exc_info.value.payload["data"]["conversation_id"]

    retry, _session = chat_service.query_chat(
        db_path=db_path,
        request=_request(),
        auth=None,
        payload={**document_payload, "conversation_id": conversation_id},
    )
    followup, _session = chat_service.query_chat(
        db_path=db_path,
        request=_request(),
        auth=None,
        payload={
            **document_payload,
            "conversation_id": conversation_id,
            "message": "Summarize the recovered answer",
        },
    )

    retry_prompt = json.dumps(RecordingClient.calls[1], ensure_ascii=False)
    followup_prompt = json.dumps(RecordingClient.calls[2], ensure_ascii=False)
    assert retry_prompt.count(query) == 1
    assert followup_prompt.count(query) == 1
    assert "Recovered explanation" in followup_prompt
    assert retry["data"]["conversation_id"] == conversation_id
    assert followup["data"]["conversation_id"] == conversation_id

    storage = Storage(db_path)
    try:
        messages = ConversationManager(storage, _config()).get_messages(
            conversation_id, include_metadata=True
        )
    finally:
        storage.close()

    assert [message["metadata"]["status"] for message in messages if message["role"] == "user"] == [
        "failed",
        "succeeded",
        "succeeded",
    ]


def test_real_retriever_logs_only_safe_error_classification(monkeypatch, caplog) -> None:
    secret_query = "SENSITIVE-QUESTION-BODY-347"
    secret_path = "C:/SENSITIVE/INDEX/PATH-347"
    retriever = object.__new__(RAGRetriever)
    retriever.config = SimpleNamespace(
        top_k=3,
        similarity_threshold=0.35,
        min_results_per_kb=1,
    )
    kb = SimpleNamespace(kb_id="kb-1", name="Safe KB")
    retriever.kb_manager = SimpleNamespace(
        get_kb=lambda _kb_id: kb,
        list_kbs=lambda: [kb],
    )
    retriever.embedding_generator = SimpleNamespace(generate_single=lambda _query: [0.0])
    retriever.get_current_embedding_metadata = lambda: {
        "provider": "test",
        "model": "test",
        "dimension": 1,
    }
    retriever._ensure_kb_embedding_compatibility = lambda *_args: None

    def fail_retrieval(*_args):
        raise OSError(secret_path)

    retriever._retrieve_from_kb = fail_retrieval
    caplog.set_level(logging.INFO, logger="ai_actuarial.chatbot.retrieval")

    with pytest.raises(exceptions.RetrievalException) as exc_info:
        retriever.retrieve(secret_query, ["kb-1"])

    assert str(exc_info.value) == "Knowledge retrieval failed"
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "error_type=OSError" in caplog.text
    assert "classification=retrieval" in caplog.text
    assert secret_query not in caplog.text
    assert secret_path not in caplog.text


def test_multi_kb_with_one_successful_empty_read_keeps_no_results_semantics(caplog) -> None:
    raw_error = "SENSITIVE-PARTIAL-READ-ERROR-347"
    retriever = object.__new__(RAGRetriever)
    retriever.config = SimpleNamespace(
        top_k=3,
        similarity_threshold=0.35,
        min_results_per_kb=1,
    )
    retriever.last_effective_threshold = None
    kb = lambda kb_id: SimpleNamespace(kb_id=kb_id, name="Safe KB")
    retriever.kb_manager = SimpleNamespace(
        get_kb=lambda kb_id: kb(kb_id),
        list_kbs=lambda: [],
    )
    retriever.embedding_generator = SimpleNamespace(generate_single=lambda _query: [0.0])
    retriever.get_current_embedding_metadata = lambda: {
        "provider": "test",
        "model": "test",
        "dimension": 1,
    }
    retriever._ensure_kb_embedding_compatibility = lambda *_args: None

    def retrieve_one(kb_id, *_args):
        if kb_id == "kb-broken":
            raise OSError(raw_error)
        return []

    retriever._retrieve_from_kb = retrieve_one

    with pytest.raises(exceptions.NoResultsException):
        retriever.retrieve("safe query", ["kb-broken", "kb-empty"])

    assert raw_error not in caplog.text


def test_standard_rag_retrieval_failure_persists_retryable_failed_turn(
    tmp_path, monkeypatch, caplog
) -> None:
    raw_detail = "SENSITIVE-RETRIEVAL-INDEX-PATH-347"

    class FailingRetriever:
        def __init__(self, storage, config):
            pass

        def retrieve(self, query, kb_ids):
            raise exceptions.RetrievalException(raw_detail)

    _install_chat_modules(
        monkeypatch,
        BudgetLLMClient,
        _config(),
        retriever_class=FailingRetriever,
    )

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={"message": "Find indexed evidence", "kb_ids": ["kb-1"]},
        )

    error = exc_info.value
    assert error.status_code == 502
    assert error.payload["code"] == "CHAT_RETRIEVAL_FAILED"
    assert error.payload["retryable"] is True
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert raw_detail not in json.dumps(error.payload)
    assert raw_detail not in caplog.text

    storage = Storage(str(tmp_path / "chat.db"))
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    failed = json.loads(rows[0][1])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "CHAT_RETRIEVAL_FAILED"
    assert failed["retryable"] is True
    assert failed["retry_request"]["kb_ids"] == ["kb-1"]


def test_auto_kb_selection_failure_persists_nonretryable_failed_turn(
    tmp_path, monkeypatch, caplog
) -> None:
    raw_detail = "SENSITIVE-DELETED-AUTO-KB-347"

    class DeletedKBRouter:
        def __init__(self, storage, config):
            pass

        def select_kb(self, query):
            raise exceptions.InvalidKBException(raw_detail)

    _install_chat_modules(
        monkeypatch,
        BudgetLLMClient,
        _config(),
        router_class=DeletedKBRouter,
    )
    db_path = str(tmp_path / "chat.db")

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=db_path,
            request=_request(),
            auth=None,
            payload={"message": "Use the best knowledge base", "kb_ids": "auto"},
        )

    error = exc_info.value
    assert error.status_code == 409
    assert error.payload["code"] == "CHAT_KB_UNAVAILABLE"
    assert error.payload["retryable"] is False
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert raw_detail not in json.dumps(error.payload)
    assert raw_detail not in caplog.text

    storage = Storage(db_path)
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    metadata = json.loads(rows[0][1])
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "CHAT_KB_UNAVAILABLE"
    assert metadata["retryable"] is False


def test_assistant_persistence_conversation_failure_finalizes_real_user_turn(
    tmp_path, monkeypatch, caplog
) -> None:
    raw_detail = "SENSITIVE-CONVERSATION-WRITE-DETAIL-347"
    original_add_message = ConversationManager.add_message

    def fail_assistant(self, conversation_id, role, content, *args, **kwargs):
        if role == "assistant":
            raise exceptions.ConversationException(raw_detail)
        return original_add_message(self, conversation_id, role, content, *args, **kwargs)

    monkeypatch.setattr(ConversationManager, "add_message", fail_assistant)
    _install_chat_modules(monkeypatch, BudgetLLMClient, _config())
    db_path = str(tmp_path / "chat.db")

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=db_path,
            request=_request(),
            auth=None,
            payload={"message": "Persist my answer", "kb_ids": ["kb-1"]},
        )

    error = exc_info.value
    assert error.status_code == 500
    assert error.payload["code"] == "CHAT_CONVERSATION_FAILED"
    assert error.payload["retryable"] is True
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert raw_detail not in json.dumps(error.payload)
    assert raw_detail not in caplog.text

    storage = Storage(db_path)
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    metadata = json.loads(rows[0][1])
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "CHAT_CONVERSATION_FAILED"
    assert metadata["retryable"] is True


def test_agentic_ready_data_failure_finalizes_real_user_turn(tmp_path, monkeypatch, caplog) -> None:
    from ai_actuarial.api.services import agentic_rag as agentic_service

    raw_detail = "SENSITIVE-VANISHED-READY-DATA-347"

    def fail_agentic(**kwargs):
        raise agentic_service.AgenticRagError(raw_detail, status_code=404)

    _install_chat_modules(monkeypatch, BudgetLLMClient, _config())
    monkeypatch.setattr(
        chat_service, "_agentic_source_fallback_reason", lambda storage, **kwargs: None
    )
    monkeypatch.setattr(agentic_service, "chat_agentic_rag", fail_agentic)
    db_path = str(tmp_path / "chat.db")

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=db_path,
            request=_request(),
            auth=None,
            payload={
                "message": "Use ready data",
                "kb_ids": ["kb-1"],
                "rag_mode": "agentic",
            },
        )

    error = exc_info.value
    assert error.status_code == 503
    assert error.payload["code"] == "CHAT_AGENTIC_UNAVAILABLE"
    assert error.payload["retryable"] is True
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert raw_detail not in json.dumps(error.payload)
    assert raw_detail not in caplog.text

    storage = Storage(db_path)
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()
    assert len(rows) == 1
    assert rows[0][0] == "user"
    metadata = json.loads(rows[0][1])
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "CHAT_AGENTIC_UNAVAILABLE"
    assert metadata["retryable"] is True


def test_unknown_post_insert_failure_uses_safe_structured_finalizer(
    tmp_path, monkeypatch, caplog
) -> None:
    raw_detail = "SENSITIVE-UNKNOWN-PROCESSING-347"

    class FailingRetriever:
        def __init__(self, storage, config):
            pass

        def retrieve(self, query, kb_ids):
            raise RuntimeError(raw_detail)

    _install_chat_modules(
        monkeypatch,
        BudgetLLMClient,
        _config(),
        retriever_class=FailingRetriever,
    )
    db_path = str(tmp_path / "chat.db")

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=db_path,
            request=_request(),
            auth=None,
            payload={"message": "Process safely", "kb_ids": ["kb-1"]},
        )

    error = exc_info.value
    assert error.status_code == 500
    assert error.payload["code"] == "CHAT_PROCESSING_FAILED"
    assert error.payload["retryable"] is True
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert raw_detail not in json.dumps(error.payload)
    assert raw_detail not in caplog.text

    storage = Storage(db_path)
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()
    assert len(rows) == 1
    assert rows[0][0] == "user"
    metadata = json.loads(rows[0][1])
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "CHAT_PROCESSING_FAILED"
    assert metadata["retryable"] is True


def test_real_auto_query_router_logs_only_query_shape(tmp_path, monkeypatch, caplog) -> None:
    sentinel = "SENSITIVE-ROUTER-QUERY-347"

    class FakeKBManager:
        def __init__(self, storage):
            pass

        def list_kbs(self):
            return [KnowledgeBase("kb-1", "General Knowledge", description="general")]

        def get_kb_categories(self, kb_id):
            return ["general"]

    monkeypatch.setattr("ai_actuarial.chatbot.router.KnowledgeBaseManager", FakeKBManager)
    _install_chat_modules(
        monkeypatch,
        BudgetLLMClient,
        _config(),
        router_class=QueryRouter,
    )

    with caplog.at_level(logging.DEBUG, logger="ai_actuarial.chatbot.router"):
        result, _session = chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={"message": f"{sentinel} risk regulation", "kb_ids": "auto"},
        )

    assert result["success"] is True
    assert sentinel not in caplog.text
    assert "query_length=" in caplog.text
    assert "keyword_count=" in caplog.text
    assert "entity_count=" in caplog.text
    assert "category_count=" in caplog.text


@pytest.mark.parametrize("direct_document", [False, True], ids=["standard-rag", "direct-document"])
def test_missing_provider_key_is_nonretryable_auth_failed_turn_before_provider_call(
    tmp_path, monkeypatch, caplog, direct_document
) -> None:
    secret_document = "SENSITIVE-DOCUMENT-BODY-347"
    config = _missing_provider_key_config()
    _install_chat_modules(monkeypatch, LLMClient, config)
    provider_factory = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr("ai_actuarial.chatbot.llm.openai.OpenAI", provider_factory)
    payload = {"message": "Explain safely", "kb_ids": ["kb-1"]}
    if direct_document:
        payload = {
            "message": "Explain safely",
            "document_content": secret_document,
            "document_filename": "safe.md",
            "document_file_url": "https://example.test/safe",
        }

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload=payload,
        )

    error = exc_info.value
    assert error.status_code == 502
    assert error.payload["code"] == "CHAT_PROVIDER_AUTH"
    assert error.payload["retryable"] is False
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert provider_factory.call_count == 0

    storage = Storage(str(tmp_path / "chat.db"))
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    failed = json.loads(rows[0][1])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "CHAT_PROVIDER_AUTH"
    assert failed["retryable"] is False
    assert secret_document not in caplog.text
    assert "MISTRAL_API_KEY" not in caplog.text


def test_unsupported_chat_provider_is_nonretryable_configuration_error(monkeypatch) -> None:
    config = ChatbotConfig(
        api_key="unused-provider-key",
        llm_provider="anthropic",
        _apply_env_defaults=False,
    )
    provider_factory = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr("ai_actuarial.chatbot.llm.openai.OpenAI", provider_factory)

    with pytest.raises(exceptions.LLMAuthenticationError) as exc_info:
        LLMClient(config)

    assert exc_info.value.code == "CHAT_PROVIDER_AUTH"
    assert exc_info.value.retryable is False
    assert provider_factory.call_count == 0


@pytest.mark.parametrize(
    ("overrides", "raw_value"),
    [
        ({"temperature": 347.125}, "347.125"),
        ({"max_tokens": -347}, "-347"),
        (
            {"length_recovery_enabled": True, "length_recovery_max_tokens": 60},
            "60 <= 60",
        ),
        ({"similarity_threshold": 347.25}, "347.25"),
        ({"default_mode": "SENSITIVE-MODE-347"}, "SENSITIVE-MODE-347"),
    ],
)
def test_all_invalid_chatbot_config_values_are_safe_nonretryable_configuration_errors(
    monkeypatch, overrides, raw_value
) -> None:
    config = _config()
    for field, value in overrides.items():
        setattr(config, field, value)
    provider_factory = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr("ai_actuarial.chatbot.llm.openai.OpenAI", provider_factory)

    with pytest.raises(exceptions.LLMAuthenticationError) as exc_info:
        LLMClient(config)

    assert exc_info.value.code == "CHAT_PROVIDER_AUTH"
    assert exc_info.value.retryable is False
    assert raw_value not in str(exc_info.value)
    assert "local-test-key" not in str(exc_info.value)
    assert provider_factory.call_count == 0


def test_injected_invalid_chatbot_config_persists_nonretryable_auth_failed_turn(
    tmp_path, monkeypatch, caplog
) -> None:
    config = _config()
    config.temperature = 347.125
    _install_chat_modules(monkeypatch, LLMClient, config)
    provider_factory = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr("ai_actuarial.chatbot.llm.openai.OpenAI", provider_factory)

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={"message": "Use configured chat", "kb_ids": ["kb-1"]},
        )

    error = exc_info.value
    assert error.status_code == 502
    assert error.payload["code"] == "CHAT_PROVIDER_AUTH"
    assert error.payload["retryable"] is False
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert provider_factory.call_count == 0
    assert "347.125" not in json.dumps(error.payload)
    assert "347.125" not in caplog.text
    assert "local-test-key" not in caplog.text

    storage = Storage(str(tmp_path / "chat.db"))
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    metadata = json.loads(rows[0][1])
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "CHAT_PROVIDER_AUTH"
    assert metadata["retryable"] is False


def test_embedding_mismatch_keeps_actionable_nonretryable_failed_turn(
    tmp_path, monkeypatch
) -> None:
    class MismatchRetriever:
        last_effective_threshold = 0.35

        def __init__(self, storage, config):
            pass

        def retrieve(self, query, kb_ids):
            raise exceptions.EmbeddingConfigurationMismatchException(
                "raw embedding mismatch detail",
                kb_id="kb-1",
                current_provider="mistral",
                current_model="mistral-embed",
                current_dimension=None,
                index_provider="openai",
                index_model="text-embedding-3-large",
                index_dimension=3072,
                needs_reindex=True,
            )

    _install_chat_modules(
        monkeypatch,
        BudgetLLMClient,
        _config(),
        retriever_class=MismatchRetriever,
    )

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={"message": "Explain the indexed evidence", "kb_ids": ["kb-1"]},
        )

    error = exc_info.value
    assert error.status_code == 409
    assert error.payload["code"] == "KB_EMBEDDING_MISMATCH"
    assert error.payload["retryable"] is False
    assert "Reindex the knowledge base" in error.payload["error"]
    assert "raw embedding mismatch detail" not in json.dumps(error.payload)
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert error.payload["conversation_id"] == error.payload["data"]["conversation_id"]
    assert error.payload["message_id"] == error.payload["data"]["message_id"]

    storage = Storage(str(tmp_path / "chat.db"))
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    failed = json.loads(rows[0][1])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "KB_EMBEDDING_MISMATCH"
    assert failed["retryable"] is False


@pytest.mark.parametrize(
    ("llm_code", "classification", "api_code", "status_code"),
    [
        ("LLM_PROVIDER_TIMEOUT", "timeout", "CHAT_PROVIDER_TIMEOUT", 504),
        ("LLM_PROVIDER_UNAVAILABLE", "upstream", "CHAT_PROVIDER_UPSTREAM", 502),
    ],
)
def test_provider_failures_map_to_stable_api_codes_and_persist_identity(
    tmp_path, monkeypatch, llm_code, classification, api_code, status_code
) -> None:
    class FailingClient(BudgetLLMClient):
        def generate_response(self, query, chunks, mode, conversation_history):
            raise exceptions.LLMException(
                "raw provider detail",
                code=llm_code,
                classification=classification,
                retryable=True,
            )

    _install_chat_modules(monkeypatch, FailingClient, _config())

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={"message": "ordinary failure", "kb_ids": ["kb-1"]},
        )

    error = exc_info.value
    assert error.status_code == status_code
    assert error.payload["code"] == api_code
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert "raw provider detail" not in json.dumps(error.payload)


def _openai_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "https://api.openai.test/v1/chat/completions"),
    )


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "expected_calls"),
    [
        (
            BadRequestError(
                "SENSITIVE-DOCUMENT-BODY context overflow",
                response=_openai_response(400),
                body={"error": {"code": "context_length_exceeded", "message": "SENSITIVE-PAYLOAD"}},
            ),
            "LLM_CONTEXT_LENGTH",
            1,
        ),
        (
            APITimeoutError(request=httpx.Request("POST", "https://api.openai.test")),
            "LLM_PROVIDER_TIMEOUT",
            3,
        ),
        (
            InternalServerError(
                "SENSITIVE-UPSTREAM-5XX",
                response=_openai_response(500),
                body={"error": {"message": "SENSITIVE-PAYLOAD"}},
            ),
            "LLM_PROVIDER_UNAVAILABLE",
            3,
        ),
    ],
)
def test_provider_errors_have_stable_codes_and_safe_logs(
    provider_error, expected_code, expected_calls, caplog
) -> None:
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = provider_error
    with patch("openai.OpenAI", return_value=mock_client):
        client = LLMClient(_config())
        with pytest.raises(exceptions.LLMException) as exc_info:
            client.generate([{"role": "user", "content": "safe prompt"}])

    assert exc_info.value.code == expected_code
    assert mock_client.chat.completions.create.call_count == expected_calls
    assert "SENSITIVE" not in str(exc_info.value)
    assert "SENSITIVE" not in caplog.text


def test_empty_direct_markdown_has_stable_error_before_provider(tmp_path, monkeypatch) -> None:
    _install_chat_modules(monkeypatch, BudgetLLMClient, _config())

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={
                "message": "Explain empty markdown",
                "document_content": "   ",
                "document_filename": "empty.md",
                "document_file_url": "https://example.test/empty",
            },
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.payload["code"] == "CHAT_DOCUMENT_EMPTY"


def test_explicit_document_sources_never_borrow_top_level_content() -> None:
    chunks, notice = chat_service._prepare_document_source_chunks(
        document_content="ALPHA",
        document_filename="fallback.md",
        document_file_url="https://example.test/fallback",
        document_sources=[
            {
                "content": "ALPHA",
                "filename": "a.md",
                "file_url": "https://example.test/a",
            },
            {
                "content": "   ",
                "filename": "empty.md",
                "file_url": "https://example.test/empty",
            },
        ],
    )

    assert [chunk["metadata"]["filename"] for chunk in chunks] == ["a.md"]
    assert [chunk["content"] for chunk in chunks] == ["ALPHA"]
    assert notice["original_chars"] == len("ALPHA")


def test_mixed_explicit_document_sources_fail_without_false_citation(tmp_path, monkeypatch) -> None:
    BudgetLLMClient.generated_messages = []
    _install_chat_modules(monkeypatch, BudgetLLMClient, _config())

    with pytest.raises(chat_service.ChatApiError) as exc_info:
        chat_service.query_chat(
            db_path=str(tmp_path / "chat.db"),
            request=_request(),
            auth=None,
            payload={
                "message": "Explain both files",
                "document_content": "ALPHA",
                "document_filename": "fallback.md",
                "document_file_url": "https://example.test/fallback",
                "document_sources": [
                    {
                        "content": "ALPHA",
                        "filename": "a.md",
                        "file_url": "https://example.test/a",
                    },
                    {
                        "content": "   ",
                        "filename": "empty.md",
                        "file_url": "https://example.test/empty",
                    },
                ],
            },
        )

    error = exc_info.value
    assert error.status_code == 422
    assert error.payload["code"] == "CHAT_DOCUMENT_EMPTY"
    assert error.payload["data"]["conversation_id"]
    assert error.payload["data"]["message_id"]
    assert BudgetLLMClient.generated_messages == []

    storage = Storage(str(tmp_path / "chat.db"))
    try:
        rows = storage._conn.execute(
            "SELECT role, metadata, citations FROM messages ORDER BY created_at"
        ).fetchall()
    finally:
        storage.close()

    assert len(rows) == 1
    assert rows[0][0] == "user"
    metadata = json.loads(rows[0][1])
    assert metadata["status"] == "failed"
    assert metadata["error_code"] == "CHAT_DOCUMENT_EMPTY"
    assert rows[0][2] in (None, "[]")

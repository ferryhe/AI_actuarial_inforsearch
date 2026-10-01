import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const testState = vi.hoisted(() => ({
  activeConversationId: null as string | null,
  messages: [] as Array<Record<string, unknown>>,
  initialActiveConversationId: null as string | null,
  initialMessages: [] as Array<Record<string, unknown>>,
  language: "en" as "en" | "zh",
  navigate: vi.fn(),
  loadConversations: vi.fn(),
  resetSession: vi.fn(),
  loadConversation: vi.fn(),
  createConversation: vi.fn(),
  removeConversation: vi.fn(),
  routeState: {
    explainDocument: {
      file_url: "https://example.test/empty.md",
      filename: "empty.md",
      title: "Empty report",
      category: "Reports",
      keywords: [],
    },
  } as unknown,
}));

vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      en: {
        "chat.explain_document": "Explain document",
        "chat.document_fallback": "Document",
        "chat.document_content_unavailable": "Document markdown content is unavailable.",
        "chat.error.embedding_mismatch": "Knowledge base embedding settings changed. Reindex the knowledge base before asking again.",
        "chat.error.provider_auth": "The AI provider is configured incorrectly. Contact an administrator.",
        "chat.error.retrieval_failed": "Knowledge retrieval failed. Retry, or ask an administrator to rebuild the knowledge base index.",
        "chat.error.kb_unavailable": "The selected knowledge base is no longer available. Select another knowledge base.",
        "chat.error.agentic_unavailable": "Agentic ready data is temporarily unavailable. Retry, or contact an administrator.",
        "chat.error.processing_failed": "Chat processing failed. Please retry.",
        "chat.error_sending": "Failed to send message. Please try again.",
        "chat.input_placeholder": "Type your message…",
        "chat.retry": "Retry",
        "a11y.send_message": "Send message",
      },
      zh: {
        "chat.explain_document": "解释文档",
        "chat.document_fallback": "文档",
        "chat.document_content_unavailable": "文档没有可用的 Markdown 内容。",
        "chat.error.embedding_mismatch": "知识库的嵌入设置已更改。请先重建知识库索引，再重新提问。",
        "chat.error.provider_auth": "AI 服务配置错误，请联系管理员。",
        "chat.error.retrieval_failed": "知识库检索失败。请重试，或联系管理员重建知识库索引。",
        "chat.error.kb_unavailable": "所选知识库已不可用。请选择其他知识库。",
        "chat.error.agentic_unavailable": "智能检索就绪数据暂时不可用。请重试，或联系管理员。",
        "chat.error.processing_failed": "聊天处理失败，请重试。",
        "chat.error_sending": "发送消息失败，请重试。",
        "chat.input_placeholder": "输入您的消息…",
        "chat.retry": "重试",
        "a11y.send_message": "发送消息",
      },
    }[testState.language] as Record<string, string>)[key] || key,
  }),
}));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: { role: "registered" },
    isLoggedIn: true,
    permissions: ["chat.conversations"],
    isLoading: false,
  }),
}));

vi.mock("wouter", () => ({
  useLocation: () => ["/chat", testState.navigate],
}));

vi.mock("wouter/use-browser-location", () => ({
  useHistoryState: () => testState.routeState,
}));

vi.mock("@/lib/navigation", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/navigation")>(),
  useRawSearch: () => "",
}));

vi.mock("./api", () => ({
  fetchAvailableDocuments: vi.fn().mockResolvedValue([]),
  fetchDocumentCategories: vi.fn().mockResolvedValue([]),
  fetchDocumentMarkdown: vi.fn(),
  fetchKnowledgeBases: vi.fn().mockResolvedValue([]),
  queryChat: vi.fn(),
}));

vi.mock("./useChatSession", async () => {
  const React = await import("react");
  return {
    useChatSession: () => {
      const [messages, setMessages] = React.useState<Array<Record<string, unknown>>>(
        testState.initialMessages,
      );
      const [activeConvId, setActiveConvId] = React.useState<string | null>(
        testState.initialActiveConversationId,
      );
      testState.messages = messages;
      testState.activeConversationId = activeConvId;
      return {
        conversations: [],
        activeConvId,
        setActiveConvId,
        messages,
        setMessages,
        loadingConvs: false,
        resetSession: testState.resetSession,
        loadConversations: testState.loadConversations,
        loadConversation: testState.loadConversation,
        createConversation: testState.createConversation,
        removeConversation: testState.removeConversation,
      };
    },
  };
});

import { ApiError } from "@/lib/api";
import Chat from "../Chat";
import { fetchDocumentMarkdown, queryChat } from "./api";

beforeEach(() => {
  vi.clearAllMocks();
  testState.activeConversationId = null;
  testState.messages = [];
  testState.initialActiveConversationId = null;
  testState.initialMessages = [];
  testState.language = "en";
  testState.routeState = {
    explainDocument: {
      file_url: "https://example.test/empty.md",
      filename: "empty.md",
      title: "Empty report",
      category: "Reports",
      keywords: [],
    },
  };
  vi.mocked(fetchDocumentMarkdown).mockResolvedValue({
    success: true,
    markdown: { markdown_content: "  \n\t " },
  });
  vi.mocked(queryChat).mockRejectedValue(new ApiError(
    "Document markdown content is unavailable.",
    422,
    "Document markdown content is unavailable.",
    {
      success: false,
      code: "CHAT_DOCUMENT_EMPTY",
      error: "Document markdown content is unavailable.",
      retryable: true,
      data: { conversation_id: "conv-empty", message_id: "msg-empty" },
    },
  ));
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe("Issue 347 empty Markdown Chat flow", () => {
  it("lets the backend persist and classify an empty referenced document once", async () => {
    render(<Chat />);

    await waitFor(() => expect(queryChat).toHaveBeenCalledTimes(1));
    expect(queryChat).toHaveBeenCalledWith(expect.objectContaining({
      document_content: "",
      document_filename: "empty.md",
      document_file_url: "https://example.test/empty.md",
    }));

    await waitFor(() => expect(testState.activeConversationId).toBe("conv-empty"));
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-empty",
      metadata: {
        status: "failed",
        error_code: "CHAT_DOCUMENT_EMPTY",
        retryable: true,
      },
    });
    expect(screen.getAllByText("Document markdown content is unavailable.")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(1);
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("keeps a genuine Markdown transport failure on the client path", async () => {
    vi.mocked(fetchDocumentMarkdown).mockRejectedValueOnce(new Error("Markdown transport failed"));

    render(<Chat />);

    expect(await screen.findByText("Markdown transport failed")).toBeInTheDocument();
    expect(queryChat).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("keeps an embedding mismatch in the persisted conversation without retry", async () => {
    testState.routeState = null;
    vi.mocked(queryChat).mockRejectedValueOnce(new ApiError(
      "Knowledge base embedding settings changed. Reindex the knowledge base before asking again.",
      409,
      "Knowledge base embedding settings changed. Reindex the knowledge base before asking again.",
      {
        success: false,
        code: "KB_EMBEDDING_MISMATCH",
        error: "Knowledge base embedding settings changed. Reindex the knowledge base before asking again.",
        retryable: false,
        conversation_id: "conv-mismatch",
        message_id: "msg-mismatch",
        data: {
          kb_id: "kb-1",
          needs_reindex: true,
        },
      },
    ));
    const user = userEvent.setup();

    render(<Chat />);
    await user.type(screen.getByTestId("input-chat-message"), "Explain indexed evidence");
    await user.click(screen.getByTestId("button-send-message"));

    expect(await screen.findByText(
      "Knowledge base embedding settings changed. Reindex the knowledge base before asking again.",
    )).toBeInTheDocument();
    await waitFor(() => expect(testState.activeConversationId).toBe("conv-mismatch"));
    expect(testState.loadConversations).toHaveBeenCalledTimes(2);
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-mismatch",
      metadata: {
        status: "failed",
        error_code: "KB_EMBEDDING_MISMATCH",
        retryable: false,
      },
    });
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByText("Failed to send message. Please try again.")).not.toBeInTheDocument();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders a Chinese provider configuration failure once without retry", async () => {
    testState.language = "zh";
    testState.routeState = null;
    vi.mocked(queryChat).mockRejectedValueOnce(new ApiError(
      "The AI provider is not configured correctly. Contact an administrator.",
      502,
      "The AI provider is not configured correctly. Contact an administrator.",
      {
        success: false,
        code: "CHAT_PROVIDER_AUTH",
        error: "The AI provider is not configured correctly. Contact an administrator.",
        retryable: false,
        data: { conversation_id: "conv-auth", message_id: "msg-auth" },
      },
    ));
    const user = userEvent.setup();

    render(<Chat />);
    await user.type(screen.getByTestId("input-chat-message"), "解释这份文件");
    await user.click(screen.getByTestId("button-send-message"));

    expect(await screen.findByText("AI 服务配置错误，请联系管理员。")).toBeInTheDocument();
    expect(screen.getAllByText("AI 服务配置错误，请联系管理员。")).toHaveLength(1);
    await waitFor(() => expect(testState.activeConversationId).toBe("conv-auth"));
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-auth",
      metadata: {
        status: "failed",
        error_code: "CHAT_PROVIDER_AUTH",
        retryable: false,
      },
    });
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    expect(screen.queryByText(/not configured correctly/i)).not.toBeInTheDocument();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders the same Chinese provider configuration failure from History", () => {
    testState.language = "zh";
    testState.routeState = null;
    testState.initialActiveConversationId = "conv-auth";
    testState.initialMessages = [{
      role: "user",
      content: "解释这份文件",
      message_id: "msg-auth",
      metadata: {
        status: "failed",
        error_code: "CHAT_PROVIDER_AUTH",
        retryable: false,
      },
    }];

    render(<Chat />);

    expect(screen.getAllByText("AI 服务配置错误，请联系管理员。")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    expect(queryChat).not.toHaveBeenCalled();
  });

  it("renders a Standard RAG retrieval failure once and keeps its conversation active", async () => {
    testState.routeState = null;
    vi.mocked(queryChat).mockRejectedValueOnce(new ApiError(
      "Knowledge retrieval failed.",
      502,
      "Knowledge retrieval failed.",
      {
        success: false,
        code: "CHAT_RETRIEVAL_FAILED",
        error: "Knowledge retrieval failed.",
        retryable: true,
        data: { conversation_id: "conv-retrieval", message_id: "msg-retrieval" },
      },
    ));
    const user = userEvent.setup();

    render(<Chat />);
    await user.type(screen.getByTestId("input-chat-message"), "Find indexed evidence");
    await user.click(screen.getByTestId("button-send-message"));

    const localized = "Knowledge retrieval failed. Retry, or ask an administrator to rebuild the knowledge base index.";
    expect(await screen.findByText(localized)).toBeInTheDocument();
    expect(screen.getAllByText(localized)).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(1);
    await waitFor(() => expect(testState.activeConversationId).toBe("conv-retrieval"));
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-retrieval",
      metadata: {
        status: "failed",
        error_code: "CHAT_RETRIEVAL_FAILED",
        retryable: true,
      },
    });
    expect(screen.queryByText("Knowledge retrieval failed.")).not.toBeInTheDocument();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders and retries the same localized retrieval failure from History", async () => {
    testState.language = "zh";
    testState.routeState = null;
    testState.initialActiveConversationId = "conv-retrieval";
    testState.initialMessages = [{
      role: "user",
      content: "查找索引证据",
      message_id: "msg-retrieval",
      metadata: {
        status: "failed",
        error_code: "CHAT_RETRIEVAL_FAILED",
        retryable: true,
        retry_request: {
          mode: "expert",
          rag_mode: "standard",
          kb_ids: ["kb-1"],
          document_sources: [],
        },
      },
    }];
    vi.mocked(queryChat).mockResolvedValueOnce({
      success: true,
      data: {
        conversation_id: "conv-retrieval",
        response: "已恢复回答",
        citations: [],
      },
    });
    const user = userEvent.setup();

    render(<Chat />);

    const localized = "知识库检索失败。请重试，或联系管理员重建知识库索引。";
    expect(screen.getAllByText(localized)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => expect(queryChat).toHaveBeenCalledWith(expect.objectContaining({
      conversation_id: "conv-retrieval",
      message: "查找索引证据",
      kb_ids: ["kb-1"],
      mode: "expert",
    })));
    expect(testState.activeConversationId).toBe("conv-retrieval");
    expect(await screen.findByText("已恢复回答")).toBeInTheDocument();
    expect(screen.getAllByText(localized)).toHaveLength(1);
  });

  it("renders a deleted selected KB once without retry or a fake assistant", async () => {
    testState.routeState = null;
    vi.mocked(queryChat).mockRejectedValueOnce(new ApiError(
      "The selected knowledge base is no longer available.",
      409,
      "The selected knowledge base is no longer available.",
      {
        success: false,
        code: "CHAT_KB_UNAVAILABLE",
        error: "The selected knowledge base is no longer available.",
        retryable: false,
        data: { conversation_id: "conv-kb-gone", message_id: "msg-kb-gone" },
      },
    ));
    const user = userEvent.setup();

    render(<Chat />);
    await user.type(screen.getByTestId("input-chat-message"), "Use my old selection");
    await user.click(screen.getByTestId("button-send-message"));

    const localized = "The selected knowledge base is no longer available. Select another knowledge base.";
    expect(await screen.findByText(localized)).toBeInTheDocument();
    expect(screen.getAllByText(localized)).toHaveLength(1);
    await waitFor(() => expect(testState.activeConversationId).toBe("conv-kb-gone"));
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-kb-gone",
      metadata: {
        status: "failed",
        error_code: "CHAT_KB_UNAVAILABLE",
        retryable: false,
      },
    });
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByText("The selected knowledge base is no longer available.")).not.toBeInTheDocument();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders the same deleted-KB failure from Chinese History without retry", () => {
    testState.language = "zh";
    testState.routeState = null;
    testState.initialActiveConversationId = "conv-kb-gone";
    testState.initialMessages = [{
      role: "user",
      content: "使用旧选择",
      message_id: "msg-kb-gone",
      metadata: {
        status: "failed",
        error_code: "CHAT_KB_UNAVAILABLE",
        retryable: false,
      },
    }];

    render(<Chat />);

    expect(screen.getAllByText("所选知识库已不可用。请选择其他知识库。")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    expect(queryChat).not.toHaveBeenCalled();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders an agentic ready-data failure once with retry and identity", async () => {
    testState.routeState = null;
    vi.mocked(queryChat).mockRejectedValueOnce(new ApiError(
      "Agentic ready data is temporarily unavailable.",
      503,
      "Agentic ready data is temporarily unavailable.",
      {
        success: false,
        code: "CHAT_AGENTIC_UNAVAILABLE",
        error: "Agentic ready data is temporarily unavailable.",
        retryable: true,
        data: { conversation_id: "conv-agentic", message_id: "msg-agentic" },
      },
    ));
    const user = userEvent.setup();

    render(<Chat />);
    await user.type(screen.getByTestId("input-chat-message"), "Use ready data");
    await user.click(screen.getByTestId("button-send-message"));

    const localized = "Agentic ready data is temporarily unavailable. Retry, or contact an administrator.";
    expect(await screen.findByText(localized)).toBeInTheDocument();
    expect(screen.getAllByText(localized)).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(1);
    await waitFor(() => expect(testState.activeConversationId).toBe("conv-agentic"));
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-agentic",
      metadata: {
        status: "failed",
        error_code: "CHAT_AGENTIC_UNAVAILABLE",
        retryable: true,
      },
    });
    expect(screen.queryByText("Agentic ready data is temporarily unavailable.")).not.toBeInTheDocument();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders the same localized agentic failure from Chinese History", () => {
    testState.language = "zh";
    testState.routeState = null;
    testState.initialActiveConversationId = "conv-agentic";
    testState.initialMessages = [{
      role: "user",
      content: "使用就绪数据",
      message_id: "msg-agentic",
      metadata: {
        status: "failed",
        error_code: "CHAT_AGENTIC_UNAVAILABLE",
        retryable: true,
      },
    }];

    render(<Chat />);

    expect(screen.getAllByText("智能检索就绪数据暂时不可用。请重试，或联系管理员。")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "重试" })).toHaveLength(1);
    expect(queryChat).not.toHaveBeenCalled();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });

  it("renders an unknown structured processing failure once without a fake assistant", async () => {
    testState.routeState = null;
    vi.mocked(queryChat).mockRejectedValueOnce(new ApiError(
      "Chat processing failed.",
      500,
      "Chat processing failed.",
      {
        success: false,
        code: "CHAT_PROCESSING_FAILED",
        error: "Chat processing failed.",
        retryable: true,
        data: { conversation_id: "conv-processing", message_id: "msg-processing" },
      },
    ));
    const user = userEvent.setup();

    render(<Chat />);
    await user.type(screen.getByTestId("input-chat-message"), "Process safely");
    await user.click(screen.getByTestId("button-send-message"));

    expect(await screen.findByText("Chat processing failed. Please retry.")).toBeInTheDocument();
    expect(screen.getAllByText("Chat processing failed. Please retry.")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(1);
    await waitFor(() => expect(testState.activeConversationId).toBe("conv-processing"));
    expect(testState.messages).toHaveLength(1);
    expect(testState.messages[0]).toMatchObject({
      role: "user",
      message_id: "msg-processing",
      metadata: {
        status: "failed",
        error_code: "CHAT_PROCESSING_FAILED",
        retryable: true,
      },
    });
    expect(screen.queryByText("Chat processing failed.")).not.toBeInTheDocument();
    expect(testState.messages.some((message) => message.role === "assistant")).toBe(false);
  });
});

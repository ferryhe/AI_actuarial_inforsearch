import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      en: {
        "chat.error.context_too_large": "This document is still too large for the active AI model. Try a shorter file or select a relevant section.",
        "chat.error.provider_timeout": "The AI provider timed out. Please retry.",
        "chat.error.provider_upstream": "The AI provider is temporarily unavailable. Please retry.",
        "chat.retry": "Retry",
      },
      zh: {
        "chat.error.context_too_large": "该文档对于当前 AI 模型仍然过长。请缩短文件或仅选择相关章节。",
        "chat.error.provider_timeout": "AI 服务响应超时，请稍后重试。",
        "chat.error.provider_upstream": "AI 服务暂时不可用，请稍后重试。",
        "chat.retry": "重试",
      },
    }[localStorage.getItem("lang") || "en"] as Record<string, string>)[key] || key,
  }),
}));

import { ApiError } from "@/lib/api";
import { FailedTurn, chatFailurePayload } from "./failure";
import { queryChat } from "./api";

beforeEach(() => localStorage.setItem("lang", "en"));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Issue 347 failed chat turns", () => {
  it("preserves the structured API body and renders one retryable failed user turn", async () => {
    const body = {
      success: false,
      code: "CHAT_CONTEXT_TOO_LARGE",
      error: "safe generic copy",
      retryable: true,
      data: { conversation_id: "conv-347", message_id: "msg-347" },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), {
      status: 422,
      headers: { "content-type": "application/json" },
    })));

    let caught: unknown;
    try {
      await queryChat({ message: "Explain this file" });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect(chatFailurePayload(caught)).toEqual(body);

    const retry = vi.fn();
    const user = userEvent.setup();
    render(
      <FailedTurn
        message={{
          role: "user",
          content: "Explain this file",
          metadata: {
            status: "failed",
            error_code: "CHAT_CONTEXT_TOO_LARGE",
            retryable: true,
            retry_request: {
              mode: "expert",
              rag_mode: "standard",
              document_sources: [{ filename: "report.md", title: "Report", file_url: "https://example.test/report" }],
            },
          },
        }}
        onRetry={retry}
      />
    );

    expect(screen.getByText(
      "This document is still too large for the active AI model. Try a shorter file or select a relevant section.",
    )).toBeInTheDocument();
    expect(screen.getAllByText(/too large/i)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("localizes timeout and upstream failures without exposing provider payload", () => {
    localStorage.setItem("lang", "zh");
    const { rerender } = render(
      <FailedTurn
        message={{ role: "user", content: "问题", metadata: { status: "failed", error_code: "CHAT_PROVIDER_TIMEOUT", retryable: true } }}
        onRetry={vi.fn()}
      />
    );
    expect(screen.getByText("AI 服务响应超时，请稍后重试。")).toBeInTheDocument();

    rerender(
      <FailedTurn
        message={{ role: "user", content: "问题", metadata: { status: "failed", error_code: "CHAT_PROVIDER_UPSTREAM", retryable: true } }}
        onRetry={vi.fn()}
      />
    );
    expect(screen.getByText("AI 服务暂时不可用，请稍后重试。")).toBeInTheDocument();
    expect(screen.queryByText(/payload|provider down/i)).not.toBeInTheDocument();
  });
});

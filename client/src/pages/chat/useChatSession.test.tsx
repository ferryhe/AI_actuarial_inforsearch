import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createChatConversation: vi.fn(),
  deleteChatConversation: vi.fn(),
  fetchChatConversation: vi.fn(),
  fetchChatConversations: vi.fn(),
}));

vi.mock("./api", () => api);

import { useChatSession } from "./useChatSession";

const sourceA = { file_url: "https://example.test/a.pdf", filename: "a.pdf", title: "Document A" };
const sourceB = { file_url: "https://example.test/b.pdf", filename: "b.pdf", title: "Document B" };

beforeEach(() => {
  vi.resetAllMocks();
  api.fetchChatConversation.mockImplementation(async (id: string) => ({
    messages: [{ role: "user", content: `Message ${id}` }],
    documentScope: [id === "conversation-a" ? sourceA : sourceB],
  }));
});

afterEach(() => vi.restoreAllMocks());

describe("useChatSession document scope lifecycle", () => {
  it("restores a document scope with its conversation and clears it for a new conversation", async () => {
    api.createChatConversation.mockResolvedValue("conversation-new");
    const { result } = renderHook(() => useChatSession({
      canUseConversations: true,
      initialLoading: false,
      newConversationTitle: "New conversation",
      getMode: () => "expert",
    }));

    await act(async () => result.current.loadConversation("conversation-a"));
    expect(result.current.documentScope).toEqual([sourceA]);
    expect(result.current.messages[0].content).toBe("Message conversation-a");

    await act(async () => { await result.current.createConversation(); });
    expect(result.current.activeConvId).toBe("conversation-new");
    expect(result.current.documentScope).toEqual([]);
    expect(result.current.messages).toEqual([]);
  });

  it("keeps a failed restore blocked until retry succeeds or the user starts a new conversation", async () => {
    api.fetchChatConversation.mockRejectedValueOnce(new Error("HTTP 500"));
    api.createChatConversation.mockResolvedValue("conversation-new");
    const { result } = renderHook(() => useChatSession({
      canUseConversations: true,
      initialLoading: false,
      newConversationTitle: "New conversation",
      getMode: () => "expert",
    }));

    await act(async () => result.current.loadConversation("conversation-a"));
    expect(result.current.activeConvId).toBe("conversation-a");
    expect(result.current.conversationLoadError).toBe(true);
    expect(result.current.documentScope).toEqual([]);

    await act(async () => result.current.loadConversation("conversation-a"));
    expect(result.current.conversationLoadError).toBe(false);
    expect(result.current.documentScope).toEqual([sourceA]);

    api.fetchChatConversation.mockRejectedValueOnce(new Error("HTTP 500"));
    await act(async () => result.current.loadConversation("conversation-a"));
    expect(result.current.conversationLoadError).toBe(true);
    await act(async () => { await result.current.createConversation(); });
    expect(result.current.activeConvId).toBe("conversation-new");
    expect(result.current.conversationLoadError).toBe(false);
    expect(result.current.documentScope).toEqual([]);
  });

  it("does not let a slow delete clear the newly selected conversation", async () => {
    let finishDelete!: () => void;
    api.deleteChatConversation.mockImplementation(() => new Promise<void>((resolve) => {
      finishDelete = resolve;
    }));
    const { result } = renderHook(() => useChatSession({
      canUseConversations: true,
      initialLoading: false,
      newConversationTitle: "New conversation",
      getMode: () => "expert",
    }));

    await act(async () => result.current.loadConversation("conversation-a"));
    let removePromise!: Promise<void>;
    act(() => { removePromise = result.current.removeConversation("conversation-a"); });
    await act(async () => result.current.loadConversation("conversation-b"));

    await act(async () => finishDelete());
    await act(async () => removePromise);
    await waitFor(() => expect(result.current.activeConvId).toBe("conversation-b"));
    expect(result.current.documentScope).toEqual([sourceB]);
    expect(result.current.messages[0].content).toBe("Message conversation-b");
  });
});

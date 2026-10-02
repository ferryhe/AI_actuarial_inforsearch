import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const viewport = vi.hoisted(() => ({
  mobile: true,
  listeners: new Set<(event: MediaQueryListEvent) => void>(),
  session: {
    setActiveConvId: vi.fn(), setMessages: vi.fn(), resetSession: vi.fn(), loadConversations: vi.fn(),
    loadConversation: vi.fn(), createConversation: vi.fn(), removeConversation: vi.fn(),
  },
}));

vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      "a11y.open_chat_sidebar": "Open chat sidebar",
      "a11y.close_chat_sidebar": "Close chat sidebar",
      "a11y.send_message": "Send message",
      "chat.show_sidebar": "Show sidebar",
      "chat.input_placeholder": "Type your message",
    }[key] || key),
  }),
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { role: "registered" }, isLoggedIn: true, permissions: ["chat.conversations"], isLoading: false }),
}));
vi.mock("wouter", () => ({ useLocation: () => ["/chat", vi.fn()] }));
vi.mock("wouter/use-browser-location", () => ({ useHistoryState: () => null }));
vi.mock("@/lib/navigation", async (original) => ({ ...await original<typeof import("@/lib/navigation")>(), useRawSearch: () => "" }));
vi.mock("./api", () => ({
  fetchAvailableDocuments: vi.fn().mockResolvedValue([]),
  fetchDocumentCategories: vi.fn().mockResolvedValue([]),
  fetchDocumentMarkdown: vi.fn(),
  fetchKnowledgeBases: vi.fn().mockResolvedValue([]),
  queryChat: vi.fn(),
}));
vi.mock("./useChatSession", () => ({
  useChatSession: () => ({
    conversations: [], activeConvId: null, messages: [], loadingConvs: false, ...viewport.session,
  }),
}));

import Chat from "../Chat";

function setViewport(mobile: boolean) {
  viewport.mobile = mobile;
  viewport.listeners.forEach((listener) => listener({ matches: mobile } as MediaQueryListEvent));
}

beforeEach(() => {
  viewport.mobile = true;
  viewport.listeners.clear();
  window.matchMedia = vi.fn().mockImplementation(() => ({
    get matches() { return viewport.mobile; },
    addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => viewport.listeners.add(listener),
    removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => viewport.listeners.delete(listener),
  }));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

describe("Issue 351 mobile Chat drawer", () => {
  it("starts closed on mobile, overlays without leaking state across breakpoints, and restores focus", async () => {
    const user = userEvent.setup();
    render(<Chat />);

    const open = screen.getByRole("button", { name: "Open chat sidebar" });
    expect(screen.queryByRole("button", { name: "Close chat sidebar" })).not.toBeInTheDocument();
    await user.click(open);
    expect(screen.getByTestId("chat-sidebar-backdrop")).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");
    const close = screen.getByRole("button", { name: "Close chat sidebar" });
    await waitFor(() => expect(document.activeElement).toBe(close));

    await user.click(screen.getByTestId("chat-sidebar-backdrop"));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Close chat sidebar" })).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open chat sidebar" })));

    await user.click(screen.getByRole("button", { name: "Open chat sidebar" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Close chat sidebar" })).not.toBeInTheDocument());

    setViewport(false);
    expect(await screen.findByRole("button", { name: "Close chat sidebar" })).toBeInTheDocument();
    setViewport(true);
    expect(await screen.findByRole("button", { name: "Open chat sidebar" })).toBeInTheDocument();
  });
});

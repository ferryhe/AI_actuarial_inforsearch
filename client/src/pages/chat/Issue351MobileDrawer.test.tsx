import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const viewport = vi.hoisted(() => ({
  mobile: true,
  listeners: new Set<(event: MediaQueryListEvent) => void>(),
  session: {
    setActiveConvId: vi.fn(), setMessages: vi.fn(), setDocumentScope: vi.fn(), documentScope: [], loadingConversation: false, resetSession: vi.fn(), loadConversations: vi.fn(),
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
  fetchAvailableDocuments: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 }),
  fetchDocumentCategories: vi.fn().mockResolvedValue([]),
  fetchDocumentMarkdown: vi.fn(),
  clearChatDocumentScope: vi.fn(),
  fetchKnowledgeBases: vi.fn().mockResolvedValue([]),
  queryChat: vi.fn(),
}));
vi.mock("./useChatSession", () => ({
  useChatSession: () => ({
    conversations: [], activeConvId: null, messages: [], loadingConvs: false, ...viewport.session,
  }),
}));

import Chat from "../Chat";
import { fetchKnowledgeBases } from "./api";

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
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

  it("bounds the mobile drawer and backdrop to a panned visual viewport", async () => {
    vi.mocked(fetchKnowledgeBases).mockResolvedValue([]);
    const visualViewport = Object.assign(new EventTarget(), { offsetTop: 680, height: 152 });
    vi.stubGlobal("visualViewport", visualViewport);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 49, bottom: 781 } as DOMRect);
    const user = userEvent.setup();
    render(<Chat />);
    const open = screen.getByRole("button", { name: "Open chat sidebar" });
    await user.click(open);
    const close = screen.getByRole("button", { name: "Close chat sidebar" });
    const panel = screen.getByTestId("chat-viewport");

    expect(panel.style.getPropertyValue("--chat-drawer-top")).toBe("680px");
    expect(panel.style.getPropertyValue("--chat-drawer-height")).toBe("152px");
    expect(panel).toHaveAttribute("data-short-drawer");
    expect(close.closest(".fixed")).toHaveClass("group-data-[short-drawer]/chat-viewport:overflow-y-auto");
    for (const layer of [close.closest(".fixed"), screen.getByTestId("chat-sidebar-backdrop")]) {
      expect(layer).toHaveClass("top-[var(--chat-drawer-top,0px)]", "h-[var(--chat-drawer-height,100vh)]");
    }
    await waitFor(() => expect(close).toHaveFocus());
    await user.click(close);
    await waitFor(() => expect(screen.getByRole("button", { name: "Open chat sidebar" })).toHaveFocus());
  });
});

it("keeps the composer in the visible viewport when a keyboard resizes or pans it", () => {
  const visualViewport = Object.assign(new EventTarget(), { height: 740, offsetTop: 0 });
  vi.stubGlobal("visualViewport", visualViewport);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 56, bottom: 740 } as DOMRect);
  const { unmount } = render(<Chat />);
  const chat = screen.getByTestId("chat-viewport");
  const composer = chat.querySelector("[data-chat-composer]");
  const history = screen.getByTestId("chat-history");
  expect(chat.style.getPropertyValue("--chat-visible-height")).toBe("684px");
  expect(chat).not.toHaveAttribute("data-compact-chat");
  expect(history).toHaveClass("min-h-0", "overflow-y-auto");
  expect(history).not.toContainElement(composer as HTMLElement);
  expect(composer).toHaveClass("shrink-0");

  act(() => {
    visualViewport.height = 200;
    visualViewport.dispatchEvent(new Event("resize"));
  });
  expect(chat.style.getPropertyValue("--chat-visible-height")).toBe("144px");
  expect(chat).toHaveAttribute("data-compact-chat");

  act(() => {
    visualViewport.offsetTop = 42;
    visualViewport.dispatchEvent(new Event("scroll"));
  });
  expect(chat.style.getPropertyValue("--chat-visible-height")).toBe("186px");

  unmount();
  visualViewport.offsetTop = 80;
  visualViewport.dispatchEvent(new Event("scroll"));
  expect(chat.style.getPropertyValue("--chat-visible-height")).toBe("186px");
});

it("intersects a stable Chat frame while a short visual viewport pans and returns", () => {
  const visualViewport = Object.assign(new EventTarget(), { height: 200, offsetTop: 0 });
  vi.stubGlobal("visualViewport", visualViewport);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 49, bottom: 296 } as DOMRect);
  render(<Chat />);
  const chat = screen.getByTestId("chat-viewport");
  const expected = [
    { top: 0, offset: "0px", height: "151px" },
    { top: 150, offset: "101px", height: "146px" },
    { top: 175, offset: "126px", height: "121px" },
    { top: 0, offset: "0px", height: "151px" },
  ];

  for (const frame of expected) {
    act(() => {
      visualViewport.offsetTop = frame.top;
      visualViewport.dispatchEvent(new Event("scroll"));
    });
    expect(chat.style.getPropertyValue("--chat-visible-offset")).toBe(frame.offset);
    expect(chat.style.getPropertyValue("--chat-visible-height")).toBe(frame.height);
    expect(chat).toHaveAttribute("data-compact-chat");
  }
});

it("moves controls into history when composer growth uses the remaining reading space", () => {
  vi.stubGlobal("visualViewport", Object.assign(new EventTarget(), { height: 320, offsetTop: 480 }));
  let resize: (() => void) | undefined;
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: () => void) { resize = callback; }
    observe() {}
    disconnect() {}
  });
  let composerHeight = 150;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const height = this.hasAttribute("data-chat-composer") ? composerHeight :
      this.classList.contains("flow-root") && this.querySelector("[data-testid='button-open-chat-sidebar']")
        ? 100 : 0;
    return { top: 49, bottom: 781, height } as DOMRect;
  });
  render(<Chat />);
  const chat = screen.getByTestId("chat-viewport");
  const history = screen.getByTestId("chat-history");
  const sidebar = () => screen.getByTestId("button-open-chat-sidebar");
  expect(chat.style.getPropertyValue("--chat-visible-height")).toBe("301px");
  expect(chat).not.toHaveAttribute("data-compact-chat");
  expect(history).not.toContainElement(sidebar());

  act(() => {
    composerHeight = 199;
    resize?.();
  });
  expect(chat).toHaveAttribute("data-compact-chat");
  expect(history).toContainElement(sidebar());

  act(() => resize?.());
  expect(chat).toHaveAttribute("data-compact-chat");
  act(() => {
    composerHeight = 150;
    resize?.();
  });
  expect(chat).not.toHaveAttribute("data-compact-chat");
  expect(history).not.toContainElement(sidebar());
});

it("moves only the options when the fixed composer would leave too little history", () => {
  const viewport = Object.assign(new EventTarget(), { height: 145, offsetTop: 230 });
  vi.stubGlobal("visualViewport", viewport);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const height = this.hasAttribute("data-chat-options") ? 32 :
      this.hasAttribute("data-chat-composer") ? (this.querySelector("[data-chat-options]") ? 84 : 52) : 0;
    return { top: 49, bottom: 312, height } as DOMRect;
  });
  render(<Chat />);
  const history = screen.getByTestId("chat-history");
  const input = screen.getByRole("textbox");
  const send = screen.getByRole("button", { name: "Send message" });
  expect(history).toContainElement(screen.getByTestId("button-mode-selector"));
  expect(history).not.toContainElement(input);
  expect(history).not.toContainElement(send);
  act(() => {
    viewport.height = 200;
    viewport.offsetTop = 175;
    viewport.dispatchEvent(new Event("resize"));
  });
  expect(history).not.toContainElement(screen.getByTestId("button-mode-selector"));
  expect(screen.getByRole("textbox")).toBe(input);
  expect(screen.getByRole("button", { name: "Send message" })).toBe(send);
});

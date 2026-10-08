import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  apiGet: vi.fn(), apiDelete: vi.fn(), kbId: "kb-350",
  session: { setActiveConvId: vi.fn(), setMessages: vi.fn(), setDocumentScope: vi.fn(), documentScope: [], loadingConversation: false, resetSession: vi.fn(), loadConversations: vi.fn(),
    loadConversation: vi.fn(), createConversation: vi.fn(), removeConversation: vi.fn() },
}));
vi.mock("@/components/Layout", () => ({ useTranslation: () => ({ t: (key: string) => key === "chat.compare_selected_count" ? "{count} selected" : key }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["catalog.read", "catalog.write"], isLoading: false }) }));
vi.mock("wouter", () => ({ useLocation: () => ["/knowledge/kb-350", vi.fn()], useRoute: () => [true, { kbId: state.kbId }] }));
vi.mock("wouter/use-browser-location", () => ({ useHistoryState: () => null }));
vi.mock("@/lib/navigation", async (original) => ({ ...await original<typeof import("@/lib/navigation")>(), useRawSearch: () => "" }));
vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), apiGet: state.apiGet,
  apiDelete: state.apiDelete, apiPost: vi.fn(), apiPut: vi.fn() }));
vi.mock("./chat/useChatSession", () => ({ useChatSession: () => ({
  conversations: [], activeConvId: null, messages: [], loadingConvs: false, ...state.session,
}) }));

import KBDetail from "./KBDetail";
import Chat from "./Chat";

const fixture = Array.from({ length: 1101 }, (_, i) => ({
  file_url: `https://fixture.test/${String(i).padStart(4, "0")}.pdf`,
  title: `Report ${String(i).padStart(4, "0")}`, filename: `${i}.pdf`, category: i % 2 ? "B" : "A", keywords: [],
}));
let files = [...fixture];
function page(url: URL) {
  const query = url.searchParams.get("query") || "";
  const category = url.searchParams.get("category");
  const matches = files.filter((file) => file.title.toLowerCase().includes(query.toLowerCase()) && (!category || file.category === category));
  const offset = Number(url.searchParams.get("offset") || 0);
  const limit = Number(url.searchParams.get("limit") || 50);
  return { items: matches.slice(offset, offset + limit), total: matches.length, offset, limit };
}
function respond(rawUrl: string) {
  const url = new URL(rawUrl, "https://fixture.test");
  if (url.pathname.endsWith("/files")) return page(url);
  if (url.pathname.endsWith("available-documents")) return { data: page(url) };
  if (url.pathname.endsWith("/kb-350")) return { knowledge_base: { kb_id: "kb-350", name: "Large fixture", kb_mode: "manual", chunk_profile_id: "p" } };
  if (url.pathname.endsWith("/categories")) return { categories: [{ name: "A" }, { name: "B" }] };
  return {};
}
beforeEach(() => {
  files = [...fixture];
  state.kbId = "kb-350";
  state.apiGet.mockReset().mockImplementation(async (url: string) => respond(url));
  state.apiDelete.mockReset().mockImplementation(async (url: string) => {
    const fileUrl = decodeURIComponent(url.split("/files/")[1]);
    files = files.filter((file) => file.file_url !== fileUrl);
  });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

it("bounds KB rows and Remove buttons to 50; pages and removes using the stable URL", async () => {
  const user = userEvent.setup();
  render(<KBDetail />);
  await screen.findByText("Report 0000");
  expect(screen.getAllByTestId(/^row-kb-file-/)).toHaveLength(50);
  expect(screen.getAllByTestId(/^button-remove-file-/)).toHaveLength(50);
  expect(screen.queryByText("Report 0050")).not.toBeInTheDocument();
  await user.click(screen.getByTestId("kb-file-pagination-next"));
  await screen.findByText("Report 0050");
  expect(screen.getByTestId("row-kb-file-0")).toHaveAttribute("data-file-url", fixture[50].file_url);
  await user.click(screen.getByTestId("button-remove-file-0"));
  await screen.findByText("Report 0100");
  expect(state.apiDelete).toHaveBeenCalledWith(`/api/rag/knowledge-bases/kb-350/files/${encodeURIComponent(fixture[50].file_url)}`);
  expect(screen.queryByText("Report 0050")).not.toBeInTheDocument();
  expect(screen.getAllByTestId(/^button-remove-file-/)).toHaveLength(50);
  await user.type(screen.getByTestId("input-search-kb-files"), "Report 1100");
  await screen.findByText("Report 1100");
  expect(screen.getAllByTestId(/^row-kb-file-/)).toHaveLength(1);
  const searchCalls = state.apiGet.mock.calls.filter(([url]) => String(url).includes("query="));
  expect(searchCalls).toHaveLength(1);
  expect(String(searchCalls[0][0])).toContain("offset=0");
});

it("cancels an in-flight filter request and ignores its late response", async () => {
  const user = userEvent.setup();
  let staleSignal: AbortSignal | undefined;
  let finishStale: ((value: unknown) => void) | undefined;
  state.apiGet.mockImplementation((url: string, options?: RequestInit) => {
    if (url.includes("query=stale")) {
      staleSignal = options?.signal as AbortSignal;
      return new Promise((resolve) => { finishStale = resolve; });
    }
    return Promise.resolve(respond(url));
  });
  render(<KBDetail />);
  await screen.findByText("Report 0000");
  const input = screen.getByTestId("input-search-kb-files");
  await user.type(input, "stale");
  await waitFor(() => expect(staleSignal).toBeDefined());
  await user.clear(input);
  await user.type(input, "Report 1100");
  expect(staleSignal?.aborted).toBe(true);
  await screen.findByText("Report 1100");
  await act(async () => { finishStale?.({ items: [fixture[0]], total: 1, offset: 0, limit: 50 }); });
  expect(screen.queryByText("Report 0000")).not.toBeInTheDocument();
  expect(screen.getByText("Report 1100")).toBeInTheDocument();
});

it("keeps Chat comparison selection by URL across pages and server filters", async () => {
  const user = userEvent.setup();
  render(<Chat />);
  await screen.findByText("Report 0000");
  expect(screen.getAllByTestId(/^document-\d+$/)).toHaveLength(50);
  await user.click(screen.getByTestId("button-toggle-compare-document-0"));
  await user.click(screen.getByTestId("chat-document-pagination-next"));
  await screen.findByText("Report 0050");
  await user.click(screen.getByTestId("button-toggle-compare-document-0"));
  expect(screen.getByTestId("compare-selected-count")).toHaveTextContent("2 selected");
  await user.click(screen.getByTestId("chat-document-pagination-prev"));
  await screen.findByText("Report 0000");
  expect(screen.getByTestId("button-toggle-compare-document-0").querySelector(".lucide-check")).not.toBeNull();
  // Toggle only the first page's document; the other selection must survive.
  await user.click(screen.getByTestId("button-toggle-compare-document-0"));
  expect(screen.getByTestId("compare-selected-count")).toHaveTextContent("1 selected");
  await user.click(screen.getByTestId("chat-document-pagination-next"));
  await screen.findByText("Report 0050");
  expect(screen.getByTestId("button-toggle-compare-document-0").querySelector(".lucide-check")).not.toBeNull();
  await user.type(screen.getByTestId("input-doc-search"), "Report 1100");
  await screen.findByText("Report 1100");
  expect(screen.getByTestId("compare-selected-count")).toHaveTextContent("1 selected");
  expect(screen.getByTestId("button-toggle-compare-document-0").querySelector(".lucide-check")).toBeNull();
  await user.click(screen.getByTestId("button-toggle-compare-document-0"));
  expect(screen.getByTestId("compare-selected-count")).toHaveTextContent("2 selected");
});

it("cancels the previous KB's page request when the route changes", async () => {
  let oldSignal: AbortSignal | undefined;
  let finishOld: ((value: unknown) => void) | undefined;
  state.apiGet.mockImplementation((url: string, options?: RequestInit) => {
    if (url.includes("kb-350/files?")) {
      oldSignal = options?.signal as AbortSignal;
      return new Promise((resolve) => { finishOld = resolve; });
    }
    if (url.includes("/kb-other/files?")) return Promise.resolve({ items: [{ ...fixture[100], title: "Other KB file" }], total: 1, limit: 50, offset: 0 });
    if (url.endsWith("/kb-other")) return Promise.resolve({ knowledge_base: { kb_id: "kb-other", name: "Other KB", kb_mode: "manual" } });
    return Promise.resolve(respond(url));
  });
  const view = render(<KBDetail />);
  await waitFor(() => expect(oldSignal).toBeDefined());
  state.kbId = "kb-other";
  view.rerender(<KBDetail />);
  await screen.findByText("Other KB file");
  expect(oldSignal?.aborted).toBe(true);
  await act(async () => { finishOld?.({ items: [fixture[0]], total: 1101, limit: 50, offset: 0 }); });
  expect(screen.queryByText("Report 0000")).not.toBeInTheDocument();
  expect(screen.getByText("Other KB file")).toBeInTheDocument();
});

it("returns to the previous page after removing the last file on a page", async () => {
  files = fixture.slice(0, 51);
  const user = userEvent.setup();
  render(<KBDetail />);
  await screen.findByText("Report 0000");
  await user.click(screen.getByTestId("kb-file-pagination-next"));
  await screen.findByText("Report 0050");
  expect(screen.getAllByTestId(/^row-kb-file-/)).toHaveLength(1);
  await user.click(screen.getByTestId("button-remove-file-0"));
  await screen.findByText("Report 0000");
  expect(screen.getAllByTestId(/^row-kb-file-/)).toHaveLength(50);
  expect(screen.queryByText("Report 0050")).not.toBeInTheDocument();
  expect(screen.queryByTestId("kb-file-pagination")).not.toBeInTheDocument();
});

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  apiGet: vi.fn(),
  fetchChatKnowledgeBases: vi.fn(),
  navigate: vi.fn(),
  permissions: [] as string[],
  translate: (key: string) => key,
}));

vi.mock("@/components/Layout", () => ({
  useTranslation: () => ({ t: state.translate, lang: "en" }),
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ permissions: state.permissions, isLoading: false }),
}));
vi.mock("@/lib/api", () => ({
  apiGet: state.apiGet,
  apiPost: vi.fn().mockResolvedValue({}),
  apiDelete: vi.fn().mockResolvedValue({}),
  formatApiErrorDetail: (error: unknown) => error instanceof Error ? error.message : String(error),
}));
vi.mock("./chat/api", () => ({ fetchKnowledgeBases: state.fetchChatKnowledgeBases }));
vi.mock("wouter", async (original) => ({
  ...await original<typeof import("wouter")>(),
  useLocation: () => ["/categories", state.navigate],
}));

import Categories from "./Categories";
import Knowledge from "./Knowledge";

beforeEach(() => {
  state.permissions = [];
  state.apiGet.mockReset();
  state.fetchChatKnowledgeBases.mockReset();
  state.navigate.mockReset();
});
afterEach(() => cleanup());

it("renders category cards before delayed KB lookups and later applies the exact Ask AI mapping", async () => {
  state.permissions = ["catalog.read", "chat.view", "chat.query"];
  let resolveMapping!: (value: unknown) => void;
  let resolveReadiness!: (value: unknown) => void;
  state.apiGet.mockImplementation((url: string) => {
    if (url === "/api/categories?mode=used") {
      return Promise.resolve({ categories: [{ name: "AI", count: 3 }, { name: "Database", count: 5 }] });
    }
    if (url === "/api/rag/knowledge-bases?include_diagnostics=false") {
      return new Promise((resolve) => { resolveMapping = resolve; });
    }
    return Promise.resolve({});
  });
  state.fetchChatKnowledgeBases.mockImplementation(() => new Promise((resolve) => { resolveReadiness = resolve; }));

  render(<Categories />);
  expect(await screen.findByTestId("categories-grid")).toBeInTheDocument();
  expect(screen.getByTestId("button-ask-ai-category-AI")).toBeDisabled();
  expect(state.apiGet).toHaveBeenCalledWith("/api/rag/knowledge-bases?include_diagnostics=false");

  resolveMapping({ knowledge_bases: [{ kb_id: "kb-ai", categories: ["AI"] }] });
  resolveReadiness([{ kb_id: "kb-ai", usable: true, serving: true, reason: "healthy" }]);
  await waitFor(() => expect(screen.getByTestId("button-ask-ai-category-AI")).toBeEnabled());
  expect(screen.getByTestId("button-ask-ai-category-Database")).toBeDisabled();

  const user = userEvent.setup();
  await user.type(screen.getByTestId("input-category-search"), "database");
  expect(screen.getAllByTestId("category-card-title")).toHaveLength(1);
  expect(screen.getByRole("link", { name: "categories.open" })).toHaveAttribute(
    "href",
    "/database?category=Database",
  );
});

it("does not request KB data or Chat readiness for users without Ask AI permissions", async () => {
  state.permissions = ["catalog.read"];
  state.apiGet.mockResolvedValue({ categories: [{ name: "AI" }] });
  state.fetchChatKnowledgeBases.mockResolvedValue([]);

  render(<Categories />);
  expect(await screen.findByTestId("categories-grid")).toBeInTheDocument();
  expect(state.apiGet.mock.calls.map(([url]) => url)).toEqual(["/api/categories?mode=used"]);
  expect(state.fetchChatKnowledgeBases).not.toHaveBeenCalled();
});

it("shows category and KB list failures separately and retries without presenting failure as empty", async () => {
  state.permissions = ["catalog.read"];
  let categoryAttempts = 0;
  state.apiGet.mockImplementation((url: string) => {
    if (url === "/api/categories?mode=used") {
      return categoryAttempts++ === 0
        ? Promise.reject(new Error("category service unavailable"))
        : Promise.resolve({ categories: [] });
    }
    return Promise.resolve({});
  });
  const categoryPage = render(<Categories />);
  expect(await screen.findByTestId("categories-error")).toHaveTextContent("category service unavailable");
  expect(screen.queryByTestId("categories-empty")).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(within(screen.getByTestId("categories-error")).getByRole("button"));
  expect(await screen.findByTestId("categories-empty")).toBeInTheDocument();
  expect(screen.queryByTestId("categories-error")).not.toBeInTheDocument();
  expect(state.apiGet).toHaveBeenCalledTimes(2);
  categoryPage.unmount();

  let kbAttempts = 0;
  state.apiGet.mockImplementation((url: string) => {
    if (url === "/api/rag/knowledge-bases" && kbAttempts++ === 0) {
      return Promise.reject(new Error("KB service unavailable"));
    }
    if (url === "/api/rag/knowledge-bases") {
      return Promise.resolve({ knowledge_bases: [{ id: "kb-recovered", kb_id: "kb-recovered", name: "Recovered KB" }] });
    }
    return Promise.resolve({ categories: [] });
  });
  render(<Knowledge />);
  expect(await screen.findByTestId("knowledge-list-error")).toHaveTextContent("KB service unavailable");
  expect(screen.queryByTestId("text-no-kbs")).not.toBeInTheDocument();
  await user.click(within(screen.getByTestId("knowledge-list-error")).getByRole("button"));
  expect(await screen.findByText("Recovered KB")).toBeInTheDocument();
  expect(screen.queryByTestId("knowledge-list-error")).not.toBeInTheDocument();
});

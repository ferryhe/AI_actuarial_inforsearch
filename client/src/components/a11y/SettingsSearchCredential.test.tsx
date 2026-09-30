import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Layout from "@/components/Layout";
import Settings from "@/pages/Settings";

const { apiDelete, apiGet, apiPost } = vi.hoisted(() => ({
  apiDelete: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ apiDelete, apiGet, apiPost }));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    isLoggedIn: false,
    logout: vi.fn(),
    permissions: [],
  }),
}));

vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
}));

beforeEach(() => {
  localStorage.setItem("lang", "en");
  window.scrollTo = vi.fn();
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/backend-settings") return Promise.resolve({ defaults: {} });
    if (url === "/api/config/search-engines") {
      return Promise.resolve({ engines: [{ id: "brave", name: "Brave Search", configured: false }] });
    }
    if (url === "/api/config/providers") return Promise.resolve({ providers: [] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [] });
    return Promise.resolve({});
  });
  apiDelete.mockResolvedValue({});
  apiPost.mockResolvedValue({});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openSearchCredentialEditor() {
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-search"));
  await user.click(await screen.findByTestId("button-edit-search-brave"));
}

describe("search credential save button", () => {
  it("includes the engine target in its English accessible name", async () => {
    await openSearchCredentialEditor();
    expect(screen.getByRole("button", { name: "Save search credential Brave Search" })).toBeInTheDocument();
  });

  it("includes the engine target in its Chinese accessible name", async () => {
    localStorage.setItem("lang", "zh");
    await openSearchCredentialEditor();
    expect(screen.getByRole("button", { name: "保存搜索凭据 Brave Search" })).toBeInTheDocument();
  });
});

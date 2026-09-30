import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Layout from "@/components/Layout";
import Tasks from "@/pages/Tasks";

const { activeTask, apiGet, apiPost } = vi.hoisted(() => ({
  activeTask: {
    id: "task-42",
    name: "Rebuild SOA",
    type: "catalog",
    status: "running",
    progress: 25,
    started_at: "2026-09-29T12:00:00Z",
    current_activity: "Indexing",
    items_processed: 1,
    items_total: 4,
  },
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ apiGet, apiPost }));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    isLoggedIn: false,
    logout: vi.fn(),
    permissions: ["tasks.run", "tasks.stop"],
  }),
}));

vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
}));

beforeEach(() => {
  localStorage.setItem("lang", "en");
  activeTask.name = "Rebuild SOA";
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/tasks/active") {
      return Promise.resolve({ tasks: [{ ...activeTask }] });
    }
    if (url.startsWith("/api/tasks/history")) return Promise.resolve({ tasks: [] });
    if (url === "/api/config/sites") return Promise.resolve({ sites: [] });
    return Promise.resolve({});
  });
  apiPost.mockResolvedValue({});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("task stop confirmation", () => {
  it("identifies the same task as the dangerous stop control", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    render(<Layout><Tasks /></Layout>);

    const stop = await screen.findByRole("button", { name: "Stop task Rebuild SOA" });
    await user.click(stop);

    await waitFor(() => expect(confirm).toHaveBeenCalledWith("Stop task Rebuild SOA?"));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("interpolates the task target in Chinese", async () => {
    localStorage.setItem("lang", "zh");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    render(<Layout><Tasks /></Layout>);

    const stop = await screen.findByRole("button", { name: "停止任务 Rebuild SOA" });
    await user.click(stop);

    await waitFor(() => expect(confirm).toHaveBeenCalledWith("确定要停止任务 Rebuild SOA 吗？"));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it.each([
    ["empty", ""],
    ["whitespace", "   "],
  ])("falls back to the task ID when its display name is %s", async (_case, name) => {
    activeTask.name = name;
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    render(<Layout><Tasks /></Layout>);

    await user.click(await screen.findByRole("button", { name: "Stop task task-42" }));

    await waitFor(() => expect(confirm).toHaveBeenCalledWith("Stop task task-42?"));
    expect(apiPost).not.toHaveBeenCalled();
  });
});

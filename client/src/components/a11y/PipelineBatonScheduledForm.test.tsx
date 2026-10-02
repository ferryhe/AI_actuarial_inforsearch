import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import { PipelineBaton } from "@/pages/tasks/PipelineBaton";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["tasks.run", "schedule.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const pipelineView = {
  config: { overrides: {} }, state: { round_status: "idle" },
  summary: { status: "idle", successful_stages: 0, failed_stages: 0, stopped_stages: 0, latest_failure: null },
  stages: [{ step: "scheduled", status: "idle", tasks: [], failures: [] }],
};

it("labels Pipeline Baton scheduled site settings and has no axe violations", async () => {
  apiGet.mockImplementation((url: string) => Promise.resolve(url === "/api/scheduled-tasks"
    ? { tasks: [{ name: "Scheduled Collection", type: "scheduled", interval: "daily at 02:00", enabled: true, params: { site: "https://smoke.example", max_pages: 20, max_depth: 2 } }] }
    : pipelineView
  ));
  const user = userEvent.setup();
  render(<Layout><PipelineBaton onViewLog={vi.fn()} /></Layout>);
  await user.click(await screen.findByTestId("button-pipeline-stage-scheduled"));
  const site = screen.getByTestId("input-pipeline-scheduled-site") as HTMLInputElement;
  const maxPages = screen.getByTestId("input-pipeline-scheduled-max-pages") as HTMLInputElement;
  const maxDepth = screen.getByTestId("input-pipeline-scheduled-max-depth") as HTMLInputElement;
  for (const input of [site, maxPages, maxDepth]) expect(input.labels?.[0]?.textContent?.trim()).not.toBe("");
  expect((await axe.run(site.closest(".grid")!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("describes only the Pipeline Baton action whose start or scheduled save failed", async () => {
  apiGet.mockImplementation((url: string) => Promise.resolve(url === "/api/scheduled-tasks"
    ? { tasks: [{ name: "Scheduled Collection", type: "scheduled", interval: "daily at 02:00", enabled: true, params: {} }] }
    : pipelineView
  ));
  apiPost.mockRejectedValue(new Error("pipeline failed"));
  const user = userEvent.setup();
  render(<Layout><PipelineBaton onViewLog={vi.fn()} /></Layout>);
  const start = await screen.findByTestId("button-start-pipeline-baton");
  expect(start).toHaveClass("min-h-[48px]");
  expect(screen.getByTestId("button-refresh-pipeline-baton")).toHaveClass("min-h-[48px]", "min-w-[48px]");
  await user.click(start);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-pipeline-baton");
  expect(start).toHaveAttribute("aria-describedby", "error-pipeline-baton");
  await user.click(screen.getByTestId("button-pipeline-stage-scheduled"));
  const save = screen.getByTestId("button-save-pipeline-scheduled");
  await user.click(save);
  expect(save).toHaveAttribute("aria-describedby", "error-pipeline-baton");
  expect(start).not.toHaveAttribute("aria-describedby");
  await user.click(screen.getByTestId("button-pipeline-stage-rag_indexing"));
  const overrideSave = screen.getByTestId("button-run-task-rag_indexing");
  await user.click(overrideSave);
  expect(overrideSave).toHaveAttribute("aria-describedby", "error-pipeline-baton");
  expect(save).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(screen.getByTestId("pipeline-baton"), { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("describes a refresh failure only through Refresh", async () => {
  let failRefresh = false;
  apiGet.mockImplementation((url: string) => {
    if (failRefresh && url === "/api/pipeline/status") return Promise.reject(new Error("refresh failed"));
    return Promise.resolve(url === "/api/scheduled-tasks" ? { tasks: [] } : pipelineView);
  });
  const user = userEvent.setup();
  render(<Layout><PipelineBaton onViewLog={vi.fn()} /></Layout>);
  const refresh = await screen.findByTestId("button-refresh-pipeline-baton");
  failRefresh = true;
  await user.click(refresh);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-pipeline-baton");
  expect(refresh).toHaveAttribute("aria-describedby", "error-pipeline-baton");
  expect(screen.getByTestId("button-start-pipeline-baton")).not.toHaveAttribute("aria-describedby");
});

it("keeps Run test IDs unique when two failed pipeline stages are expanded", async () => {
  apiGet.mockImplementation((url: string) => Promise.resolve(url === "/api/scheduled-tasks" ? { tasks: [] } : {
    ...pipelineView,
    summary: { ...pipelineView.summary, status: "failed", failed_stages: 2 },
    stages: [
      { step: "catalog", status: "failed", tasks: [], failures: [] },
      { step: "chunk_generation", status: "failed", tasks: [], failures: [] },
    ],
  }));
  render(<Layout><PipelineBaton onViewLog={vi.fn()} /></Layout>);
  await screen.findByTestId("button-run-task-catalog");
  await screen.findByTestId("button-run-task-chunk_generation");
  const testIds = Array.from(document.querySelectorAll("[data-testid]"), (node) => node.getAttribute("data-testid"));
  expect(new Set(testIds).size).toBe(testIds.length);
});

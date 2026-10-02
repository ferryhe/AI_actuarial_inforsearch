import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import { ScheduledTasksSection } from "@/pages/tasks/ScheduledTasksSection";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, apiDelete: vi.fn().mockResolvedValue({}), formatApiErrorDetail: (error: { message?: string }) => error.message || "" }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["schedule.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("labels the real scheduled-task form and has no axe violations", async () => {
  apiGet.mockResolvedValue({ tasks: [] }); apiPost.mockResolvedValue({});
  const user = userEvent.setup();
  render(<Layout><ScheduledTasksSection initialScheduleStatus={{ count: 0, jobs: [] }} initialScheduledTasks={[]} initialLoading={false} canManageScheduleOverride /></Layout>);
  await user.click(await screen.findByTestId("button-add-scheduled-task"));
  const form = screen.getByTestId("form-scheduled-task");
  for (const id of ["input-sched-name", "select-sched-type", "select-sched-frequency", "input-sched-time", "select-sched-timezone"]) {
    expect((screen.getByTestId(id) as HTMLInputElement).labels?.[0]?.textContent?.trim()).not.toBe("");
  }
  expect((await axe.run(form, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates a failed scheduler reinitialize with only Reinitialize", async () => {
  apiGet.mockResolvedValue({ tasks: [] }); apiPost.mockRejectedValue(new Error("reinit failed"));
  const user = userEvent.setup();
  render(<Layout><ScheduledTasksSection initialScheduleStatus={{ count: 0, jobs: [] }} initialScheduledTasks={[]} initialLoading={false} canManageScheduleOverride /></Layout>);
  const reinit = await screen.findByTestId("button-reinit-scheduler");
  await user.click(reinit);
  const alert = await screen.findByTestId("text-scheduled-error");
  expect(alert).toHaveAttribute("role", "alert");
  expect(reinit).toHaveAttribute("aria-describedby", "error-scheduled-task");
});

it("gives the populated delete-confirm Cancel control a two-dimensional touch target", async () => {
  const task = { name: "Smoke schedule", type: "scheduled", interval: "daily", enabled: true, params: {} };
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("/api/schedule/status") ? { count: 1, jobs: [] } : { tasks: [task] })); apiPost.mockResolvedValue({});
  const user = userEvent.setup();
  render(<Layout><ScheduledTasksSection initialScheduleStatus={{ count: 1, jobs: [] }} initialScheduledTasks={[task]} initialLoading={false} canManageScheduleOverride /></Layout>);
  await user.click(await screen.findByTestId("button-delete-sched-Smoke schedule"));
  const cancel = screen.getByRole("button", { name: "Cancel" });
  expect(cancel).toHaveClass("min-h-[48px]", "min-w-[48px]");
  expect((await axe.run(cancel.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

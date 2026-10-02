import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import { SiteConfigForm } from "@/pages/tasks/SiteConfigForm";

vi.mock("@/lib/api", () => ({ apiGet: vi.fn().mockResolvedValue({}), apiPost: vi.fn().mockResolvedValue({}), getStoredAuthToken: vi.fn() }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["sites.write", "schedule.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
afterEach(cleanup);

it("labels the real site editor and has no axe violations", async () => {
  const user = userEvent.setup();
  render(<Layout><SiteConfigForm sites={[]} onSubmit={vi.fn()} submitting={false} onSitesChanged={vi.fn()} /></Layout>);
  await user.click(screen.getByTestId("button-add-site"));
  const form = screen.getByTestId("form-site");
  for (const id of ["input-site-url", "input-site-name", "input-site-goal"]) {
    expect((screen.getByTestId(id) as HTMLInputElement).labels?.[0]?.textContent?.trim()).not.toBe("");
  }
  expect((await axe.run(form, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("describes a Tasks-level run failure from the primary Run action", async () => {
  const user = userEvent.setup();
  render(<Layout><p id="error-task-submit" role="alert">run failed</p><SiteConfigForm sites={[]} onSubmit={vi.fn()} submitting={false} onSitesChanged={vi.fn()} errorDescribedBy="error-task-submit" /></Layout>);
  const run = screen.getByTestId("button-run-task");
  await user.click(run);
  expect(run).toHaveAttribute("aria-describedby", "error-task-submit");
  expect((await axe.run(run.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("uses 48px targets for populated site and backup controls", async () => {
  render(<Layout><SiteConfigForm sites={[{ name: "Smoke", url: "https://smoke.example" }]} onSubmit={vi.fn()} submitting={false} onSitesChanged={vi.fn()} /></Layout>);
  for (const id of ["button-toggle-site-Smoke", "button-toggle-backups"]) expect(screen.getByTestId(id)).toHaveClass("min-h-[48px]");
});

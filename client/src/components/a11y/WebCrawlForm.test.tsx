import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import { WebCrawlForm } from "@/pages/tasks/WebCrawlForm";
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["schedule.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
it("labels real crawl fields, links hints, and has no axe violations", async () => {
  const { container } = render(<Layout><WebCrawlForm onSubmit={vi.fn()} submitting={false} /></Layout>);
  for (const id of ["input-crawl-url", "input-crawl-name", "input-crawl-max-pages", "input-crawl-max-depth"]) expect((screen.getByTestId(id) as HTMLInputElement).labels?.[0]?.textContent?.trim()).not.toBe("");
  for (const id of ["input-crawl-name", "input-crawl-max-pages", "input-crawl-max-depth"]) expect(screen.getByTestId(id)).toHaveAttribute("aria-describedby", `hint-${id}`);
  expect(screen.getByTestId("input-crawl-url")).toHaveClass("min-h-[48px]");
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("connects the file-extension label to TagSelect's custom input and touch targets", async () => {
  cleanup();
  const user = userEvent.setup();
  render(<Layout><WebCrawlForm onSubmit={vi.fn()} submitting={false} /></Layout>);
  const tags = screen.getByTestId("input-crawl-file-exts");
  const add = screen.getByTestId("input-crawl-file-exts-add-custom");
  expect(add).toHaveClass("min-h-[48px]", "min-w-[48px]");
  for (const preset of screen.getAllByTestId(/input-crawl-file-exts-tag-/)) expect(preset).toHaveClass("min-h-[48px]", "min-w-[48px]");
  await user.click(add);
  const custom = screen.getByTestId("input-crawl-file-exts-custom-input");
  expect(custom).toHaveAttribute("aria-labelledby", "label-input-crawl-file-exts");
  expect(document.getElementById("label-input-crawl-file-exts")?.textContent?.trim()).not.toBe("");
  expect(custom).toHaveAttribute("aria-describedby", "hint-input-crawl-file-exts");
  expect(custom).toHaveClass("min-h-[48px]");
  expect(tags).toHaveAttribute("aria-labelledby", "label-input-crawl-file-exts");
  await user.type(custom, ".custom{Enter}");
  const remove = screen.getByTestId("input-crawl-file-exts-remove-.custom");
  expect(remove).toHaveAccessibleName("Remove .custom");
  expect(remove).toHaveClass("min-h-[48px]", "min-w-[48px]");
  expect((await axe.run(tags.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("connects the ordinary Run action to the Tasks-level failure message", async () => {
  cleanup();
  render(<Layout><WebCrawlForm onSubmit={vi.fn()} submitting={false} errorDescribedBy="error-task-submit" /></Layout>);
  expect(screen.getByTestId("button-run-task")).toHaveAttribute("aria-describedby", "error-task-submit");
});

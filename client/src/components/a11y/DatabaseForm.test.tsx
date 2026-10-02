import "@testing-library/jest-dom/vitest";
import axe from "axe-core";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import DatabasePage from "@/pages/Database";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["catalog.read", "files.delete", "files.download"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
beforeEach(() => { window.scrollTo = vi.fn(); apiGet.mockImplementation((url: string) => Promise.resolve(url.includes("/sources") ? { sources: ["Smoke"] } : url.includes("/categories") ? { categories: ["General"] } : { files: [], total: 40 })); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("labels the real Database search and filter controls with no axe violations", async () => {
  const user = userEvent.setup(); const { container } = render(<Layout><DatabasePage /></Layout>);
  await user.click(screen.getByTestId("button-toggle-filters"));
  for (const id of ["input-search", "select-source", "select-category", "select-sort"]) {
    const control = screen.getByTestId(id) as HTMLInputElement;
    expect(control.labels?.[0]?.textContent?.trim()).not.toBe("");
  }
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("keeps clear search and page-jump controls at the mobile target class", async () => {
  const user = userEvent.setup(); render(<Layout><DatabasePage /></Layout>);
  await user.type(await screen.findByTestId("input-search"), "smoke");
  for (const id of ["button-clear-search", "input-page-jump", "button-page-jump"]) expect(screen.getByTestId(id)).toHaveClass("min-h-[48px]");
  expect(screen.getByTestId("button-page-jump")).toHaveClass("min-w-[48px]");
});

it("gives populated mobile selection, row, and pagination actions 48px targets", async () => {
  apiGet.mockImplementation((url: string) => Promise.resolve(url.includes("/sources") ? { sources: ["Smoke"] } : url.includes("/categories") ? { categories: ["General"] } : { files: [{ url: "file-smoke", title: "Smoke", original_filename: "smoke.pdf", markdown_status: "ready", source_site: "Smoke", first_seen: "2026-01-01T00:00:00Z" }], total: 40 }));
  render(<Layout><DatabasePage /></Layout>);
  await screen.findByTestId("button-select-all-visible");
  for (const id of ["button-select-all-visible", "button-bulk-delete", "checkbox-select-mobile-0", "button-ai-explain-mobile-0", "button-preview-mobile-0", "button-download-mobile-0", "button-prev-page", "button-next-page"]) expect(screen.getByTestId(id)).toHaveClass("min-h-[48px]");
  expect(screen.getByTestId("checkbox-select-mobile-0")).toHaveClass("min-w-[48px]");
});

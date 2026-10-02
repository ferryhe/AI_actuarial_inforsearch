import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import FileDetail from "@/pages/FileDetail";
const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, apiDelete: vi.fn() }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["catalog.write", "catalog.read", "tasks.run", "config.read", "files.delete", "files.write", "markdown.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
beforeEach(() => { window.scrollTo = vi.fn(); window.history.pushState({}, "", "/file-detail?url=file-smoke"); apiGet.mockImplementation((url) => Promise.resolve(url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt", category: "General", summary: "Summary", keywords: ["actuarial"] } } : url.includes("/markdown") ? { markdown: { markdown_content: "text", markdown_source: "manual" } } : url.includes("chunk-sets") ? { chunk_sets: [] } : url.includes("categories") ? { categories: { General: [] } } : url.includes("chunk/profiles") ? { profiles: [{ profile_id: "p", name: "Default" }] } : { tasks: [] })); });
afterEach(cleanup);
it("labels real file-detail edit and catalog forms with no axe violations", async () => {
  const user = userEvent.setup(); const { container } = render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-edit"));
  for (const id of ["input-title", "input-summary", "input-keywords"]) expect((screen.getByTestId(id) as HTMLInputElement).labels?.[0]?.textContent?.trim()).not.toBe("");
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  await user.click(screen.getByTestId("button-cancel"));
  await user.click(screen.getByTestId("button-catalog")); const source = await screen.findByTestId("select-catalog-source");
  expect(source).toHaveAttribute("aria-describedby", "hint-catalog-source"); expect(document.getElementById("hint-catalog-source")?.textContent?.trim()).not.toBe("");
  expect((await axe.run(source.closest(".space-y-4")!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("uses a visible Markdown editor label", async () => {
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-md-edit"));
  const markdown = screen.getByTestId("input-markdown") as HTMLTextAreaElement;
  expect(markdown.labels?.[0]?.textContent?.trim()).not.toBe("");
  expect(markdown.labels?.[0]).not.toHaveClass("sr-only");
});

it("describes a rejected chunk submission from Submit, not the profile selector", async () => {
  apiPost.mockResolvedValueOnce({});
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-modify-chunk"));
  await user.click(screen.getByTestId("button-submit-chunk"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-file-chunk-submit");
  expect(screen.getByTestId("button-submit-chunk")).toHaveAttribute("aria-describedby", "error-file-chunk-submit");
  expect(screen.getByTestId("select-file-chunk-profile")).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(screen.getByTestId("button-submit-chunk").closest('[role="dialog"]') || screen.getByTestId("button-submit-chunk").parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("describes a rejected edit save from the initiating action", async () => {
  apiPost.mockRejectedValueOnce(new Error("save failed"));
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-edit"));
  await user.click(screen.getByTestId("button-save"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-file-detail-mutation");
  expect(screen.getByTestId("button-save")).toHaveAttribute("aria-describedby", "error-file-detail-mutation");
  expect((await axe.run(alert.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("describes a rejected delete from the confirmed delete action", async () => {
  apiPost.mockRejectedValueOnce(new Error("delete failed"));
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-delete"));
  await user.type(screen.getByTestId("input-confirm-delete"), "confirm delete");
  await user.click(screen.getByTestId("button-execute-delete"));
  const alert = await screen.findByRole("alert");
  const execute = screen.getByTestId("button-execute-delete");
  expect(alert).toHaveAttribute("id", "error-confirm-delete");
  expect(execute).toHaveAttribute("aria-describedby", "error-confirm-delete");
  expect((await axe.run(screen.getByTestId("input-confirm-delete").closest(".space-y-2")!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

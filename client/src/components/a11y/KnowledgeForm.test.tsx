import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import Knowledge from "@/pages/Knowledge";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, apiDelete: vi.fn(), formatApiErrorDetail: (error: { detail?: string }) => error.detail || "" }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: null, isLoggedIn: true, logout: vi.fn(), permissions: ["catalog.read", "catalog.write", "config.write", "tasks.run"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
beforeEach(() => { window.scrollTo = vi.fn(); });
afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.setItem("lang", "en"); });

it("labels the real create knowledge-base form and has no axe violations", async () => {
  apiGet.mockResolvedValue({ knowledge_bases: [], profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }], categories: [] });
  const user = userEvent.setup();
  render(<Layout><Knowledge /></Layout>);
  await user.click(await screen.findByTestId("button-create-kb"));
  const name = screen.getByTestId("input-kb-name") as HTMLInputElement;
  expect(name.labels).toHaveLength(1);
  expect(name.labels?.[0]).toHaveAttribute("for", name.id);
  expect(name.labels?.[0]?.textContent?.trim()).not.toBe("");
  for (const [testId, hintId] of [["input-kb-id", "hint-kb-id"], ["select-kb-mode", "hint-kb-mode"], ["select-kb-embedding-identity", "hint-kb-embedding-identity"]]) {
    expect(screen.getByTestId(testId)).toHaveAttribute("aria-describedby", hintId);
    expect(document.getElementById(hintId)?.textContent?.trim()).not.toBe("");
  }
  expect((await axe.run(name.closest(".rounded-xl")!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("keeps the Chinese Create knowledge-base action at the mobile target floor", async () => {
  localStorage.setItem("lang", "zh");
  apiGet.mockResolvedValue({ knowledge_bases: [], profiles: [], categories: [] });
  render(<Layout><Knowledge /></Layout>);
  expect(await screen.findByTestId("button-create-kb")).toHaveClass("min-h-[48px]");
});

it("gives category choices a two-dimensional mobile target", async () => {
  apiGet.mockResolvedValue({ knowledge_bases: [], profiles: [{ profile_id: "p", name: "Default" }], categories: ["General"] });
  const user = userEvent.setup();
  render(<Layout><Knowledge /></Layout>);
  await user.click(await screen.findByTestId("button-create-kb"));
  await user.selectOptions(screen.getByTestId("select-kb-mode"), "category");
  expect(await screen.findByTestId("button-toggle-kb-category-General")).toHaveClass("min-h-[44px]", "min-w-[44px]");
});

it("keeps chunk-profile controls operable and describes a failed knowledge-base create", async () => {
  apiGet.mockResolvedValue({ knowledge_bases: [], profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }], categories: [] });
  apiPost.mockRejectedValue({ detail: "create failed" });
  const user = userEvent.setup();
  render(<Layout><Knowledge /></Layout>);

  await user.click(await screen.findByTestId("button-create-profile"));
  const profileClose = screen.getByTestId("button-close-create-profile");
  const profileDelete = screen.getByTestId("button-delete-profile-0");
  expect(profileClose).toHaveAccessibleName();
  expect(profileClose).toHaveClass("min-h-[48px]", "min-w-[48px]");
  expect(profileDelete).toHaveAccessibleName();
  expect(profileDelete).toHaveClass("min-h-[48px]", "min-w-[48px]");
  await user.click(profileClose);

  await user.click(screen.getByTestId("button-create-kb"));
  await user.type(screen.getByTestId("input-kb-name"), "Smoke KB");
  await user.selectOptions(screen.getByTestId("select-kb-mode"), "all");
  await user.click(screen.getByTestId("button-submit-kb"));
  const alert = await screen.findByTestId("alert-kb-action-error");
  expect(alert).toHaveAttribute("role", "alert");
  expect(screen.getByTestId("button-submit-kb")).toHaveAttribute("aria-describedby", "error-kb-action");
  expect(alert).toHaveAttribute("id", "error-kb-action");
});

it("describes a failed chunk-profile create from its submit action", async () => {
  apiGet.mockResolvedValue({ knowledge_bases: [], profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }], categories: [] });
  apiPost.mockRejectedValueOnce(new Error("profile create failed"));
  const user = userEvent.setup();
  render(<Layout><Knowledge /></Layout>);
  await user.click(await screen.findByTestId("button-create-profile"));
  await user.type(screen.getByTestId("input-profile-name"), "Smoke profile");
  await user.click(screen.getByTestId("button-submit-profile"));
  const alert = await screen.findByRole("alert");
  const submit = screen.getByTestId("button-submit-profile");
  expect(alert).toHaveAttribute("id", "error-profile-create");
  expect(submit).toHaveAttribute("aria-describedby", "error-profile-create");
  expect((await axe.run(submit.closest(".rounded-xl") || submit.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  await user.click(screen.getByTestId("button-cancel-profile"));
  await user.click(screen.getByTestId("button-create-profile"));
  expect(screen.queryByTestId("error-profile-create")).not.toBeInTheDocument();
  expect(screen.getByTestId("button-submit-profile")).not.toHaveAttribute("aria-describedby");
});

it("describes a failed create-and-index action without describing Create", async () => {
  apiGet.mockResolvedValue({ knowledge_bases: [], profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }], categories: [] });
  apiPost.mockRejectedValue({ detail: "index failed" });
  const user = userEvent.setup();
  render(<Layout><Knowledge /></Layout>);
  await user.click(await screen.findByTestId("button-create-kb"));
  await user.type(screen.getByTestId("input-kb-name"), "Smoke KB");
  await user.selectOptions(screen.getByTestId("select-kb-mode"), "all");
  expect(screen.getByTestId("button-submit-kb-index")).toHaveClass("min-h-[48px]");
  await user.click(screen.getByTestId("button-submit-kb-index"));
  await screen.findByTestId("alert-kb-action-error");
  expect(screen.getByTestId("button-submit-kb-index")).toHaveAttribute("aria-describedby", "error-kb-action");
  expect(screen.getByTestId("button-submit-kb")).not.toHaveAttribute("aria-describedby");
});

it("describes manifest and re-embed errors only on their matching card actions", async () => {
  apiGet.mockResolvedValue({
    knowledge_bases: [
      { kb_id: "manifest-kb", name: "Manifest KB", status: "ready", embedding_model: "smoke" },
      { kb_id: "reembed-kb", name: "Reembed KB", status: "ready", embedding_model: "smoke", reason: "embedding_incompatible" },
    ],
    profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }],
    categories: [],
  });
  apiPost.mockRejectedValue({ detail: "operation failed" });
  const user = userEvent.setup();
  render(<Layout><Knowledge /></Layout>);
  const manifest = await screen.findByTestId("button-build-agentic-manifest-manifest-kb");
  const reembed = screen.getByTestId("button-reembed-kb-reembed-kb");
  expect(reembed).toHaveClass("min-h-[48px]");
  await user.click(screen.getByTestId("button-toggle-cleanup"));
  expect(screen.getByTestId("input-cleanup-days")).toHaveClass("min-h-[48px]");
  expect(screen.getByTestId("label-cleanup-dryrun")).toHaveClass("min-h-[48px]");
  expect(screen.getByTestId("button-run-cleanup")).toHaveClass("min-h-[48px]");
  await user.click(manifest);
  await screen.findByTestId("alert-kb-action-error");
  expect(manifest).toHaveAttribute("aria-describedby", "error-kb-action");
  expect(reembed).not.toHaveAttribute("aria-describedby");
  await user.click(reembed);
  expect(reembed).toHaveAttribute("aria-describedby", "error-kb-action");
  expect(manifest).not.toHaveAttribute("aria-describedby");
});

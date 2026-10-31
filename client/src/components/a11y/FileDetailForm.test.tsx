import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import FileDetail, { buildInterpretationHtml, buildInterpretationMarkdown, interpretationBody } from "@/pages/FileDetail";
const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
const reviewedFranceAuthors = ["Virginie Normand", "Léonard Fontaine", "Vincent Dalon", "Alexandre Eby"];
vi.mock("@/lib/api", () => ({ apiGet, apiPost, apiDelete: vi.fn() }));
vi.mock("@/hooks/use-task-options", () => ({ useTaskOptions: () => ({ catalogProviders: ["OpenAI"], conversionToolsInfo: [{ name: "local", provider: "local", displayName: "Local" }] }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ permissions: ["catalog.write", "catalog.read", "tasks.run", "config.read", "files.delete", "files.write", "markdown.write"] }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
beforeEach(() => { window.scrollTo = vi.fn(); window.history.pushState({}, "", "/file-detail?url=file-smoke"); apiGet.mockImplementation((url) => Promise.resolve(url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt", category: "General", summary: "Summary", keywords: ["actuarial"] } } : url.includes("/markdown") ? { markdown: { markdown_content: "text", markdown_source: "manual" } } : url.includes("chunk-sets") ? { chunk_sets: [] } : url.includes("categories") ? { categories: { General: [] } } : url.includes("chunk/profiles") ? { profiles: [{ profile_id: "p", name: "Default" }] } : { tasks: [] })); });
afterEach(() => { cleanup(); localStorage.removeItem("lang"); });
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

it("shows the current Chinese interpretation above Markdown and hides it in English", async () => {
  localStorage.setItem("lang", "zh");
  const originalUrl = "https://www.institutdesactuaires.com/global/gene/link.php?doc_id=17510&fg=1";
  const savedUrl = "https://aiactuary.cn/file-detail?file_id=2823";
  const readyBody = `解读正文\n\n## 原文出处与阅读\n\n原文日期：2022-09。\n\n[原文](${originalUrl}) · [国内阅读](${savedUrl})\n\n规范来源：法国精算师协会（Institut des actuaires）。\n\n未覆盖章节：结论`;
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("article-interpretations")
    ? { interpretations: [{ interpretation_id: "v1", title_zh: "解读标题", body_markdown_zh: readyBody, generated_at: "2026-10-30T00:00:00Z", file_url: originalUrl, raw_sha256: "rawhash", markdown_sha256: "mdhash", china_article_url: savedUrl, references: { original_title: "Machine Learning for Health Insurance Member Retention: A Case Study", published_time: "2022-09", source: { name_zh: "法国精算师协会" }, authors: reviewedFranceAuthors } }] }
    : url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt" } }
      : url.includes("/markdown") ? { markdown: { markdown_content: "原文内容", markdown_source: "manual" } }
        : url.includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  const toggle = await screen.findByTestId("button-interpretation-toggle");
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByTestId("article-interpretation").compareDocumentPosition(screen.getByText("Markdown 内容")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  toggle.focus();
  await user.keyboard("{Enter}");
  expect(await screen.findByText("解读正文")).toBeInTheDocument();
  expect(screen.queryByText("原文出处与阅读")).not.toBeInTheDocument();
  expect(screen.queryByText(/原文日期：2022-09/)).not.toBeInTheDocument();
  expect(screen.getByText("原文标题: Machine Learning for Health Insurance Member Retention: A Case Study")).toBeInTheDocument();
  expect(screen.getByText(`作者: ${reviewedFranceAuthors.join("、")}`)).toBeInTheDocument();
  expect(screen.getByTestId("article-interpretation")).toHaveTextContent("发表日期: 2022-09");
  expect(screen.getByTestId("article-interpretation")).toHaveTextContent("法国精算师协会");
  expect(screen.getByTestId("article-interpretation").querySelectorAll(`a[href="${originalUrl}"]`)).toHaveLength(1);
  expect(screen.getByTestId("article-interpretation").querySelectorAll(`a[href="${savedUrl}"]`)).toHaveLength(1);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  await user.click(screen.getByTitle("Switch language"));
  await waitFor(() => expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument());
  expect(apiGet.mock.calls.filter(([url]) => String(url).includes("article-interpretations"))).toHaveLength(1);
  await user.click(screen.getByTitle("Switch language"));
  expect(await screen.findByTestId("article-interpretation")).toBeInTheDocument();
  expect(apiGet.mock.calls.filter(([url]) => String(url).includes("article-interpretations"))).toHaveLength(2);
});

it("keeps Markdown available when the interpretation read fails", async () => {
  localStorage.setItem("lang", "zh");
  apiGet.mockImplementation((url) => url.includes("article-interpretations")
    ? Promise.reject(new Error("reader unavailable"))
    : Promise.resolve(url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt" } }
      : url.includes("/markdown") ? { markdown: { markdown_content: "原文仍可阅读", markdown_source: "manual" } }
        : url.includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  render(<Layout><FileDetail /></Layout>);
  expect(await screen.findByText("原文仍可阅读")).toBeInTheDocument();
  expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument();
});

it("ignores a late interpretation response after the route changes to another article", async () => {
  localStorage.setItem("lang", "zh");
  const articleA = "https://example.test/article-A";
  const articleB = "https://example.test/article-B";
  const user = userEvent.setup();
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleA)}`);

  let resolveA!: (value: { interpretations: Array<Record<string, unknown>> }) => void;
  let resolveB!: (value: { interpretations: Array<Record<string, unknown>> }) => void;
  let requestAStarted = false;
  let requestBStarted = false;
  apiGet.mockImplementation((url) => {
    if (String(url).includes("article-interpretations")) {
      const requestedUrl = new URLSearchParams(String(url).split("?")[1] || "").get("file_url");
      if (requestedUrl === articleA) {
        requestAStarted = true;
        return new Promise((resolve) => { resolveA = resolve; });
      }
      if (requestedUrl === articleB) {
        requestBStarted = true;
        return new Promise((resolve) => { resolveB = resolve; });
      }
    }
    return Promise.resolve(String(url).includes("/detail")
      ? { file: { url: String(url).includes(encodeURIComponent(articleB)) ? articleB : articleA, title: "Route file", original_filename: "route.pdf", source_site: "test", content_type: "text/plain", bytes: 1, local_path: "/tmp/route.txt" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Route markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] });
  });

  render(<Layout><FileDetail /></Layout>);
  await waitFor(() => expect(requestAStarted).toBe(true));
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleB)}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
  await waitFor(() => expect(requestBStarted).toBe(true));

  await act(async () => {
    resolveA({ interpretations: [{ interpretation_id: "a-v1", title_zh: "Article A interpretation", body_markdown_zh: "Article A private body", generated_at: "2026-10-30T00:00:00Z", file_url: articleA, raw_sha256: "a-raw", markdown_sha256: "a-md", china_article_url: "https://aiactuary.cn/file-detail?file_id=1001" }] });
  });
  expect(screen.queryByText("Article A interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Article A private body")).not.toBeInTheDocument();

  await act(async () => {
    resolveB({ interpretations: [{ interpretation_id: "b-v1", title_zh: "Article B interpretation", body_markdown_zh: "Article B current body", generated_at: "2026-10-30T00:00:00Z", file_url: articleB, raw_sha256: "b-raw", markdown_sha256: "b-md", china_article_url: "https://aiactuary.cn/file-detail?file_id=1002" }] });
  });
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  expect(await screen.findByText("Article B interpretation")).toBeInTheDocument();
  expect(await screen.findByText("Article B current body")).toBeInTheDocument();
  expect(screen.queryByText("Article A interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Article A private body")).not.toBeInTheDocument();
});

it("re-reads and removes an interpretation after a successful Markdown save", async () => {
  localStorage.setItem("lang", "zh");
  let readCount = 0;
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("article-interpretations")
    ? { interpretations: ++readCount === 1 ? [{ interpretation_id: "v1", title_zh: "Old interpretation", body_markdown_zh: "Old body", generated_at: "2026-10-30T00:00:00Z", file_url: "https://example.test/paper", raw_sha256: "rawhash", markdown_sha256: "oldhash", china_article_url: "https://aiactuary.cn/file-detail?file_id=1386" }] : [] }
    : url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt" } }
      : url.includes("/markdown") ? { markdown: { markdown_content: "Old markdown", markdown_source: "manual" } }
        : url.includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  apiPost.mockResolvedValueOnce({ markdown: { markdown_content: "Updated markdown", markdown_source: "manual" } });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  expect(await screen.findByTestId("article-interpretation")).toBeInTheDocument();
  await user.click(await screen.findByTestId("button-md-edit"));
  await user.clear(screen.getByTestId("input-markdown"));
  await user.type(screen.getByTestId("input-markdown"), "Updated markdown");
  await user.click(screen.getByTestId("button-save-md"));
  await waitFor(() => expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument());
  expect(readCount).toBe(2);
});

it("keeps a current interpretation when saving Markdown fails", async () => {
  localStorage.setItem("lang", "zh");
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("article-interpretations")
    ? { interpretations: [{ interpretation_id: "v1", title_zh: "Current interpretation", body_markdown_zh: "Body", generated_at: "2026-10-30T00:00:00Z", file_url: "https://example.test/paper", raw_sha256: "rawhash", markdown_sha256: "mdhash", china_article_url: "https://aiactuary.cn/file-detail?file_id=1386" }] }
    : url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt" } }
      : url.includes("/markdown") ? { markdown: { markdown_content: "Markdown", markdown_source: "manual" } }
        : url.includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  apiPost.mockRejectedValueOnce(new Error("save rejected"));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  expect(await screen.findByTestId("article-interpretation")).toBeInTheDocument();
  await user.click(await screen.findByTestId("button-md-edit"));
  await user.click(screen.getByTestId("button-save-md"));
  await screen.findByRole("alert");
  expect(screen.getByTestId("article-interpretation")).toBeInTheDocument();
});

it("re-reads an interpretation when Markdown conversion completes", async () => {
  localStorage.setItem("lang", "zh");
  let readCount = 0;
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("article-interpretations")
    ? { interpretations: ++readCount === 1 ? [{ interpretation_id: "v1", title_zh: "Old interpretation", body_markdown_zh: "Body", generated_at: "2026-10-30T00:00:00Z", file_url: "https://example.test/paper", raw_sha256: "rawhash", markdown_sha256: "oldhash", china_article_url: "https://aiactuary.cn/file-detail?file_id=1386" }] : [] }
    : url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt" } }
      : url.includes("/markdown") ? { markdown: { markdown_content: "Converted markdown", markdown_source: "converted_local" } }
        : url.includes("tasks/active") ? { tasks: [] }
          : url.includes("tasks/history") ? { tasks: [{ id: "conversion-job", status: "completed" }] }
            : url.includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  apiPost.mockResolvedValueOnce({ job_id: "conversion-job" });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  expect(await screen.findByTestId("article-interpretation")).toBeInTheDocument();
  await user.click(await screen.findByTestId("button-md-edit"));
  await user.click(await screen.findByTestId("button-convert"));
  await waitFor(() => expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument());
  expect(readCount).toBe(2);
});

it("uses saved original titles and authors in Markdown and HTML exports, with a title fallback", () => {
  const originalUrl = "https://www.institutdesactuaires.com/global/gene/link.php?doc_id=17510&fg=1";
  const domesticUrl = "https://aiactuary.cn/file-detail?file_id=2823";
  const item = { interpretation_id: "v1", title_zh: "解读", body_markdown_zh: `正文\n\n## 原文出处与阅读\n\n原文日期：2022-09。\n\n[原文](${originalUrl}) · [国内阅读](${domesticUrl})\n\n规范来源：法国精算师协会（Institut des actuaires）。\n\n未覆盖章节：结论`, generated_at: "2026-10-30", file_url: originalUrl, raw_sha256: "raw", markdown_sha256: "md", china_article_url: domesticUrl, references: { original_title: "France title", published_time: "2022-09", source: { name_zh: "法国精算师协会" }, authors: reviewedFranceAuthors } };
  const markdown = buildInterpretationMarkdown(item, "Current file title");
  const html = buildInterpretationHtml(item, "Current file title");
  expect(markdown).toContain("原文：France title");
  expect(markdown).toContain(`作者：${reviewedFranceAuthors.join("、")}`);
  expect(markdown).not.toContain("原文出处与阅读");
  expect(markdown).not.toContain("未覆盖章节");
  expect(markdown.split(originalUrl)).toHaveLength(2);
  expect(markdown.split(domesticUrl)).toHaveLength(2);
  expect(markdown).toContain("发表日期：2022-09");
  expect(html).toContain("<p>原文：France title</p>");
  expect(html).toContain(`<p>作者：${reviewedFranceAuthors.join("、")}</p>`);
  expect(html).not.toContain("原文出处与阅读");
  expect(html).not.toContain("未覆盖章节");
  expect(html.split(originalUrl.replace(/&/g, "&amp;")).length).toBe(2);
  expect(html.split(domesticUrl).length).toBe(2);
  expect(html).toContain("<p>发表日期：2022-09</p>");
  expect(html).toContain("法国精算师协会");
  const fallback = { ...item, references: { authors: reviewedFranceAuthors } };
  expect(buildInterpretationMarkdown(fallback, "Current file title")).toContain("原文：Current file title");
  expect(buildInterpretationHtml(fallback, "Current file title")).toContain("<p>原文：Current file title</p>");
  const saved = { ...item, references: { ...item.references, original_title: "Saved original title", author: "Saved Author" } };
  expect(buildInterpretationMarkdown(saved, "Fallback title")).toContain("原文：Saved original title");
  expect(buildInterpretationHtml(saved, "Fallback title")).toContain("作者：Saved Author");

  const ordinaryCitationBody = `正文保留同链接的讨论。\n\n## 原文出处与阅读\n\n相关原文链接：[原文](${originalUrl}) · [国内阅读](${domesticUrl})`;
  const ordinaryCitation = { ...item, body_markdown_zh: ordinaryCitationBody };
  expect(interpretationBody(ordinaryCitation)).toBe(ordinaryCitationBody);
  expect(buildInterpretationMarkdown(ordinaryCitation, "Current file title")).toContain("正文保留同链接的讨论。");
  expect(buildInterpretationMarkdown(ordinaryCitation, "Current file title")).toContain("相关原文链接");
  expect(buildInterpretationHtml(ordinaryCitation, "Current file title")).toContain("相关原文链接");
});

it("submits bilingual catalog generation from the file-detail entry point", async () => {
  apiPost.mockResolvedValueOnce({ job_id: "catalog-job" });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-catalog"));
  expect(screen.getByTestId("text-catalog-language-mode")).toHaveTextContent("Chinese and English");
  await user.click(screen.getByTestId("button-submit-catalog"));
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/api/collections/run", expect.objectContaining({
    type: "catalog",
    output_language: "bilingual",
  })));
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
  await user.click(screen.getByTestId("button-cancel"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await user.click(screen.getByTestId("button-edit"));
  expect(screen.getByTestId("button-save")).not.toHaveAttribute("aria-describedby");
});

it("saves an edit through the legacy contract when the selected language package is incomplete", async () => {
  apiGet.mockReset();
  apiPost.mockReset();
  const file = {
    url: "file-smoke",
    title: "Legacy title",
    original_filename: "smoke.pdf",
    source_site: "smoke",
    content_type: "text/plain",
    bytes: 12,
    local_path: "/tmp/smoke.txt",
    category: "Life",
    summary: "Legacy summary",
    keywords: ["legacy"],
    bilingual_metadata: {
      zh: { title: "中文标题", summary: "中文摘要", category: "Life", keywords: ["中文"] },
    },
  };
  apiGet.mockImplementation((url) => Promise.resolve(
    url.includes("/detail") ? { file }
      : url.includes("/markdown") ? { markdown: { markdown_content: "text", markdown_source: "manual" } }
        : url.includes("categories") ? { categories: { Life: [] } }
          : { chunk_sets: [] },
  ));
  const savedFile = { ...file, title: "Edited legacy title" };
  apiPost.mockResolvedValueOnce({ file: savedFile });

  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-edit"));
  await user.clear(screen.getByTestId("input-title"));
  await user.type(screen.getByTestId("input-title"), "Edited legacy title");
  await user.click(screen.getByTestId("button-save"));

  await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/api/files/update", expect.objectContaining({
    url: "file-smoke",
    title: "Edited legacy title",
  })));
  expect(apiPost.mock.calls.at(-1)?.[1]).not.toHaveProperty("lang");
  expect(await screen.findByTestId("text-file-title")).toHaveTextContent("Edited legacy title");
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

it("clears a rejected delete error when the confirmation is closed and reopened", async () => {
  apiPost.mockRejectedValueOnce(new Error("delete failed"));
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-delete"));
  await user.type(screen.getByTestId("input-confirm-delete"), "confirm delete");
  await user.click(screen.getByTestId("button-execute-delete"));
  await screen.findByRole("alert");
  await user.click(screen.getByTestId("button-cancel-delete"));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  await user.click(screen.getByTestId("button-delete"));
  expect(screen.getByTestId("button-execute-delete")).not.toHaveAttribute("aria-describedby");
});

it("clears a rejected Markdown save error when editing is cancelled", async () => {
  apiPost.mockRejectedValueOnce(new Error("markdown failed"));
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-md-edit"));
  await user.click(screen.getByTestId("button-save-md"));
  await screen.findByRole("alert");
  await user.click(screen.getByTestId("button-cancel-md"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await user.click(screen.getByTestId("button-md-edit"));
  expect(screen.getByTestId("button-save-md")).not.toHaveAttribute("aria-describedby");
});

it("clears a rejected Catalog error when the modal is cancelled and reopened", async () => {
  apiPost.mockRejectedValueOnce(new Error("catalog failed"));
  const user = userEvent.setup(); render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-catalog"));
  await user.click(await screen.findByTestId("button-submit-catalog"));
  await screen.findByRole("alert");
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  await user.click(screen.getByTestId("button-catalog"));
  expect(screen.getByTestId("button-submit-catalog")).not.toHaveAttribute("aria-describedby");
});


it("renders the canonical publisher in both languages while retaining raw provenance only in data", async () => {
  localStorage.setItem("lang", "en");
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("/detail") ? { file: { url: "file-smoke", title: "Publisher fixture", source_site: "local_docling", source_key: "cas", source_name_zh: "北美产险精算协会", source_name_en: "Casualty Actuarial Society (CAS)" } } : { tasks: [], profiles: [], chunk_sets: [], markdown: null }));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  expect(await screen.findByTestId("text-source")).toHaveTextContent("Casualty Actuarial Society (CAS)");
  expect(screen.queryByText("local_docling")).toBeNull();
  await user.click(screen.getByTestId("toggle-lang"));
  expect(screen.getByTestId("text-source")).toHaveTextContent("北美产险精算协会");
  localStorage.setItem("lang", "en");
});

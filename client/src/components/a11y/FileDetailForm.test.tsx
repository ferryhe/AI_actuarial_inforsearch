import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import FileDetail from "@/pages/FileDetail";
import { buildInterpretationHtml, buildInterpretationMarkdown, interpretationBody } from "@/lib/article-interpretation-format";
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

it("shows only the current locale's interpretation above Markdown", async () => {
  localStorage.setItem("lang", "zh");
  const originalUrl = "https://www.institutdesactuaires.com/global/gene/link.php?doc_id=17510&fg=1";
  const savedUrl = "https://aiactuary.cn/file-detail?file_id=2823";
  const readyBody = `解读正文\n\n## 原文出处与阅读\n\n原文日期：2022-09。\n\n[原文](${originalUrl}) · [国内阅读](${savedUrl})\n\n规范来源：法国精算师协会（Institut des actuaires）。\n\n未覆盖章节：结论`;
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("article-interpretations")
    ? { interpretations: [{ interpretation_id: "v1", title_zh: "解读标题", body_markdown_zh: readyBody, title_en: "Interpreting Health Insurance Member Retention", body_markdown_en: "English interpretation body", generated_at: "2026-10-30T00:00:00Z", file_url: originalUrl, raw_sha256: "rawhash", markdown_sha256: "mdhash", china_article_url: savedUrl, references: { original_title: "Machine Learning for Health Insurance Member Retention: A Case Study", published_time: "2022-09", source: { name_zh: "法国精算师协会", name_en: "Institut des actuaires" }, authors: reviewedFranceAuthors } }] }
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
  expect(await screen.findByTestId("article-interpretation")).toBeInTheDocument();
  expect(apiGet.mock.calls.filter(([url]) => String(url).includes("article-interpretations") && String(url).includes("locale=en")).length).toBeGreaterThan(0);
  expect(apiGet.mock.calls.some(([url]) => String(url).includes("locale=en"))).toBe(true);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  expect(await screen.findByText("Interpreting Health Insurance Member Retention")).toBeInTheDocument();
  expect(await screen.findByText("English interpretation body")).toBeInTheDocument();
  expect(screen.queryByText("解读正文")).not.toBeInTheDocument();
  await user.click(screen.getByTitle("Switch language"));
  expect(await screen.findByTestId("article-interpretation")).toBeInTheDocument();
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  expect(await screen.findByText("解读正文")).toBeInTheDocument();
  expect(screen.queryByText("English interpretation body")).not.toBeInTheDocument();
  expect(apiGet.mock.calls.some(([url]) => String(url).includes("locale=zh"))).toBe(true);
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

it("does not fall back to a Chinese-only interpretation on the English site", async () => {
  localStorage.setItem("lang", "en");
  apiGet.mockImplementation((url) => Promise.resolve(url.includes("article-interpretations")
    ? { interpretations: [{ interpretation_id: "zh-only", title_zh: "Chinese title", body_markdown_zh: "Chinese interpretation body", generated_at: "2026-10-30T00:00:00Z", file_url: "https://example.test/paper", raw_sha256: "rawhash", markdown_sha256: "mdhash", china_article_url: "https://aiactuary.cn/file-detail?file_id=1386" }] }
    : url.includes("/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt" } }
      : url.includes("/markdown") ? { markdown: { markdown_content: "Original Markdown remains available", markdown_source: "manual" } }
        : url.includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  render(<Layout><FileDetail /></Layout>);
  expect(await screen.findByText("Original Markdown remains available")).toBeInTheDocument();
  expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Chinese title")).not.toBeInTheDocument();
  expect(screen.queryByText("Chinese interpretation body")).not.toBeInTheDocument();
  expect(apiGet.mock.calls.some(([url]) => String(url).includes("locale=en"))).toBe(true);
});

it("ignores a late Chinese interpretation response after switching to English", async () => {
  localStorage.setItem("lang", "zh");
  const articleUrl = "https://example.test/locale-race";
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleUrl)}`);
  let resolveChinese!: (value: { interpretations: Array<Record<string, unknown>> }) => void;
  let chineseStarted = false;
  let englishStarted = false;
  apiGet.mockImplementation((url) => {
    if (String(url).includes("article-interpretations")) {
      const locale = new URLSearchParams(String(url).split("?")[1] || "").get("locale");
      if (locale === "zh") {
        chineseStarted = true;
        return new Promise((resolve) => { resolveChinese = resolve; });
      }
      englishStarted = locale === "en";
      return Promise.resolve({ interpretations: [{
        interpretation_id: "en-current",
        title_en: "Current English interpretation",
        body_markdown_en: "Current English body",
        generated_at: "2026-11-01T00:00:00Z",
        file_url: articleUrl,
        raw_sha256: "raw-current",
        markdown_sha256: "markdown-current",
        china_article_url: "https://aiactuary.cn/file-detail?file_id=3678",
      }] });
    }
    return Promise.resolve(String(url).includes("/detail")
      ? { file: { url: articleUrl, title: "Locale race", original_filename: "race.pdf", source_site: "test", content_type: "text/plain", bytes: 1, local_path: "/tmp/race.txt" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Race markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] });
  });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await waitFor(() => expect(chineseStarted).toBe(true));
  await user.click(screen.getByTitle("Switch language"));
  await waitFor(() => expect(englishStarted).toBe(true));
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  expect(await screen.findByText("Current English body")).toBeInTheDocument();
  await act(async () => {
    resolveChinese({ interpretations: [{
      interpretation_id: "zh-stale",
      title_zh: "Stale Chinese interpretation",
      body_markdown_zh: "Stale Chinese body",
      generated_at: "2026-11-01T00:00:00Z",
      file_url: articleUrl,
      raw_sha256: "raw-current",
      markdown_sha256: "markdown-current",
      china_article_url: "https://aiactuary.cn/file-detail?file_id=3678",
    }] });
  });
  expect(screen.queryByText("Stale Chinese interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Stale Chinese body")).not.toBeInTheDocument();
  expect(screen.getByText("Current English body")).toBeInTheDocument();
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


it("edits, previews, cancels, and saves only the Chinese interpretation body", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const articleUrl = "https://example.test/editable-paper";
  const body = "Existing Chinese body.";
  const current = {
    interpretation_id: "edit-v1",
    title_zh: "Editable interpretation",
    body_markdown_zh: body,
    title_en: "Existing English title",
    body_markdown_en: "Existing English body.",
    generated_at: "2026-11-04T00:00:00Z",
    file_url: articleUrl,
    raw_sha256: "a".repeat(64),
    markdown_sha256: "b".repeat(64),
    body_sha256: "c".repeat(64),
    china_article_url: "https://aiactuary.cn/file-detail?file_id=4001",
  };
  let persisted = current;
  apiGet.mockImplementation((url) => Promise.resolve(String(url).includes("article-interpretations")
    ? String(url).includes("locale=en") ? { interpretations: [] } : { interpretations: [persisted] }
    : String(url).includes("/detail") ? { file: { url: articleUrl, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original source markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  expect(editor.value).toBe(body);
  await user.clear(editor);
  await user.type(editor, "Edited Chinese **body**.");
  await user.click(screen.getByTestId("button-interpretation-preview"));
  expect(await screen.findByTestId("interpretation-markdown-preview")).toHaveTextContent("Edited Chinese body.");
  await user.click(screen.getByTestId("button-interpretation-edit-mode"));
  await user.click(screen.getByTestId("button-cancel-interpretation"));
  expect(await screen.findByText(body)).toBeInTheDocument();
  expect(screen.queryByTestId("input-interpretation-markdown")).not.toBeInTheDocument();
  expect(apiPost).not.toHaveBeenCalled();

  await user.click(screen.getByTestId("button-interpretation-edit"));
  const secondEditor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(secondEditor);
  await user.type(secondEditor, "Saved Chinese body.");
  apiPost.mockImplementationOnce((_url, payload) => {
    persisted = { ...current, body_markdown_zh: payload.body_markdown_zh as string };
    return Promise.resolve({ success: true, body_sha256: "d".repeat(64) });
  });
  await user.click(screen.getByTestId("button-save-interpretation"));
  await waitFor(() => expect(screen.getByText("Saved Chinese body.")).toBeInTheDocument());
  expect(screen.queryByText("Existing English body.")).not.toBeInTheDocument();
  expect(apiPost).toHaveBeenCalledWith(`/api/article-interpretations/${current.interpretation_id}/body`, {
    file_url: articleUrl,
    raw_sha256: current.raw_sha256,
    markdown_sha256: current.markdown_sha256,
    expected_body_sha256: current.body_sha256,
    body_markdown_zh: "Saved Chinese body.",
  });
  await user.click(screen.getByTitle("Switch language"));
  await waitFor(() => expect(apiGet.mock.calls.some(([url]) => String(url).includes("locale=en"))).toBe(true));
  expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Existing English title")).not.toBeInTheDocument();
});

it("keeps edited Markdown visible when interpretation save fails or conflicts", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const current = {
    interpretation_id: "edit-v2", title_zh: "Current interpretation", body_markdown_zh: "Current body.",
    generated_at: "2026-11-04T00:00:00Z", file_url: "https://example.test/conflict-paper",
    raw_sha256: "a".repeat(64), markdown_sha256: "b".repeat(64), body_sha256: "c".repeat(64),
    china_article_url: "https://aiactuary.cn/file-detail?file_id=4002",
  };
  apiGet.mockImplementation((url) => Promise.resolve(String(url).includes("article-interpretations")
    ? { interpretations: [current] }
    : String(url).includes("/detail") ? { file: { url: current.file_url, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(editor);
  await user.type(editor, "Keep this user edit.");
  apiPost.mockRejectedValueOnce(Object.assign(new Error("version conflict"), { status: 409 }));
  await user.click(screen.getByTestId("button-save-interpretation"));
  expect(await screen.findByTestId("interpretation-edit-error")).toHaveTextContent("已在其他位置更新");
  expect((screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement).value).toBe("Keep this user edit.");
});

it("locks the interpretation editor while a save is pending", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const current = {
    interpretation_id: "pending-save-v1", title_zh: "Pending save", body_markdown_zh: "Original body.",
    generated_at: "2026-11-04T00:00:00Z", file_url: "https://example.test/pending-save",
    raw_sha256: "a".repeat(64), markdown_sha256: "b".repeat(64), body_sha256: "c".repeat(64),
    china_article_url: "https://aiactuary.cn/file-detail?file_id=4010",
  };
  let persisted = current;
  apiGet.mockImplementation((url) => Promise.resolve(String(url).includes("article-interpretations")
    ? { interpretations: [persisted] }
    : String(url).includes("/detail") ? { file: { url: current.file_url, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] }));
  let resolveSave!: (value: { success: boolean; body_sha256: string }) => void;
  apiPost.mockReturnValueOnce(new Promise((resolve) => {
    resolveSave = (result) => {
      persisted = { ...current, body_markdown_zh: "Submitted body." };
      resolve(result);
    };
  }));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(editor);
  await user.type(editor, "Submitted body.");
  await user.click(screen.getByTestId("button-save-interpretation"));
  await waitFor(() => expect(editor).toBeDisabled());
  expect(editor.value).toBe("Submitted body.");
  await act(async () => resolveSave({ success: true, body_sha256: "d".repeat(64) }));
  await waitFor(() => expect(screen.queryByTestId("input-interpretation-markdown")).not.toBeInTheDocument());
  expect(await screen.findByText("Submitted body.")).toBeInTheDocument();
});

it("restores unsaved interpretation Markdown after a language switch", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const articleUrl = "https://example.test/language-switch-edit";
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleUrl)}`);
  const chinese = {
    interpretation_id: "language-edit-v1", title_zh: "中文解读", body_markdown_zh: "Original Chinese body.",
    generated_at: "2026-11-04T00:00:00Z", file_url: articleUrl,
    raw_sha256: "a".repeat(64), markdown_sha256: "b".repeat(64), body_sha256: "c".repeat(64),
    china_article_url: "https://aiactuary.cn/file-detail?file_id=4011",
  };
  const english = { ...chinese, title_en: "English interpretation", body_markdown_en: "English body." };
  apiGet.mockImplementation((url) => {
    if (String(url).includes("article-interpretations")) {
      return Promise.resolve({ interpretations: [String(url).includes("locale=en") ? english : chinese] });
    }
    return Promise.resolve(String(url).includes("/detail")
      ? { file: { url: articleUrl, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] });
  });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(editor);
  await user.type(editor, "Unsaved Chinese revision.");
  await user.click(screen.getByTitle("Switch language"));
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  expect(await screen.findByText("English interpretation")).toBeInTheDocument();
  expect(screen.queryByTestId("input-interpretation-markdown")).not.toBeInTheDocument();
  await user.click(screen.getByTitle("Switch language"));
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  const restored = await screen.findByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  expect(restored.value).toBe("Unsaved Chinese revision.");
});

it("uses the original edit CAS baseline after a concurrent writer saves during a language switch", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const articleUrl = "https://example.test/language-switch-conflict";
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleUrl)}`);
  const original = {
    interpretation_id: "language-conflict-v1", title_zh: "中文解读", body_markdown_zh: "Original Chinese body.",
    title_en: "English interpretation", body_markdown_en: "English body.",
    generated_at: "2026-11-04T00:00:00Z", file_url: articleUrl,
    raw_sha256: "a".repeat(64), markdown_sha256: "b".repeat(64), body_sha256: "c".repeat(64),
    china_article_url: "https://aiactuary.cn/file-detail?file_id=4012",
  };
  const concurrent = { ...original, body_markdown_zh: "Other author's saved body.", body_sha256: "d".repeat(64) };
  let latestChinese = original;
  apiGet.mockImplementation((url) => {
    if (String(url).includes("article-interpretations")) {
      return Promise.resolve({ interpretations: [String(url).includes("locale=en") ? original : latestChinese] });
    }
    return Promise.resolve(String(url).includes("/detail")
      ? { file: { url: articleUrl, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] });
  });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(editor);
  await user.type(editor, "My unsaved revision.");
  await user.click(screen.getByTitle("Switch language"));
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  expect(await screen.findByText("English body.")).toBeInTheDocument();

  latestChinese = concurrent;
  await user.click(screen.getByTitle("Switch language"));
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  const restored = await screen.findByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  expect(restored.value).toBe("My unsaved revision.");
  apiPost.mockRejectedValueOnce(Object.assign(new Error("version conflict"), { status: 409 }));
  await user.click(screen.getByTestId("button-save-interpretation"));
  await screen.findByTestId("interpretation-edit-error");

  expect(apiPost).toHaveBeenCalledWith(`/api/article-interpretations/${original.interpretation_id}/body`, {
    file_url: original.file_url,
    raw_sha256: original.raw_sha256,
    markdown_sha256: original.markdown_sha256,
    expected_body_sha256: original.body_sha256,
    body_markdown_zh: "My unsaved revision.",
  });
  expect((screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement).value)
    .toBe("My unsaved revision.");
});

it("keeps a conflicted draft visible and copyable when the current interpretation disappears", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const articleUrl = "https://example.test/source-changed-during-edit";
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleUrl)}`);
  const original = {
    interpretation_id: "source-conflict-v1", title_zh: "Original interpretation",
    body_markdown_zh: "Original Chinese body.", generated_at: "2026-11-04T00:00:00Z",
    file_url: articleUrl, raw_sha256: "a".repeat(64), markdown_sha256: "b".repeat(64),
    body_sha256: "c".repeat(64), china_article_url: "https://aiactuary.cn/file-detail?file_id=4021",
  };
  let sourceStillCurrent = true;
  apiGet.mockImplementation((url) => {
    if (String(url).includes("article-interpretations")) {
      const locale = new URLSearchParams(String(url).split("?")[1] || "").get("locale");
      return Promise.resolve({ interpretations: locale === "zh" && sourceStillCurrent ? [original] : [] });
    }
    return Promise.resolve(String(url).includes("/detail")
      ? { file: { url: articleUrl, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] });
  });
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(editor);
  await user.type(editor, "Preserve this conflicted draft.");
  sourceStillCurrent = false;
  await user.click(screen.getByTitle("Switch language"));
  await user.click(screen.getByTitle("Switch language"));

  const draftCard = await screen.findByTestId("article-interpretation-draft");
  const restored = within(draftCard).getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  expect(restored.value).toBe("Preserve this conflicted draft.");
  expect(within(draftCard).getByTestId("button-copy-interpretation-draft")).toBeEnabled();

  apiPost.mockRejectedValueOnce(Object.assign(new Error("source conflict"), { status: 409 }));
  await user.click(within(draftCard).getByTestId("button-save-interpretation-draft"));
  expect(await within(draftCard).findByTestId("interpretation-edit-error"))
    .toHaveTextContent("已在其他位置更新");
  expect(apiPost).toHaveBeenCalledWith(`/api/article-interpretations/${original.interpretation_id}/body`, {
    file_url: original.file_url,
    raw_sha256: original.raw_sha256,
    markdown_sha256: original.markdown_sha256,
    expected_body_sha256: original.body_sha256,
    body_markdown_zh: "Preserve this conflicted draft.",
  });
  expect((within(draftCard).getByTestId("input-interpretation-markdown") as HTMLTextAreaElement).value)
    .toBe("Preserve this conflicted draft.");
});

it("invalidates an in-flight English read after a Chinese save completes", async () => {
  apiPost.mockClear();
  localStorage.setItem("lang", "zh");
  const articleUrl = "https://example.test/save-language-race";
  window.history.pushState({}, "", `/file-detail?url=${encodeURIComponent(articleUrl)}`);
  const chinese = {
    interpretation_id: "save-language-v1", title_zh: "中文解读", body_markdown_zh: "Original Chinese body.",
    generated_at: "2026-11-04T00:00:00Z", file_url: articleUrl,
    raw_sha256: "a".repeat(64), markdown_sha256: "b".repeat(64), body_sha256: "c".repeat(64),
    china_article_url: "https://aiactuary.cn/file-detail?file_id=4022",
  };
  const staleEnglish = {
    ...chinese, title_en: "Old English interpretation", body_markdown_en: "Old English body.",
  };
  let englishRequests = 0;
  let resolveFirstEnglish!: (value: { interpretations: Array<Record<string, unknown>> }) => void;
  apiGet.mockImplementation((url) => {
    if (String(url).includes("article-interpretations")) {
      if (String(url).includes("locale=en")) {
        englishRequests += 1;
        if (englishRequests === 1) {
          return new Promise((resolve) => { resolveFirstEnglish = resolve; });
        }
        return Promise.resolve({ interpretations: [] });
      }
      return Promise.resolve({ interpretations: [chinese] });
    }
    return Promise.resolve(String(url).includes("/detail")
      ? { file: { url: articleUrl, title: "Paper", original_filename: "paper.pdf", source_site: "test", content_type: "application/pdf", bytes: 1, local_path: "/tmp/paper.pdf" } }
      : String(url).includes("/markdown") ? { markdown: { markdown_content: "Original markdown", markdown_source: "manual" } }
        : String(url).includes("chunk-sets") ? { chunk_sets: [] } : { tasks: [] });
  });
  let resolveSave!: (value: { success: boolean; body_sha256: string }) => void;
  apiPost.mockReturnValueOnce(new Promise((resolve) => { resolveSave = resolve; }));
  const user = userEvent.setup();
  render(<Layout><FileDetail /></Layout>);
  await user.click(await screen.findByTestId("button-interpretation-toggle"));
  await user.click(await screen.findByTestId("button-interpretation-edit"));
  const editor = screen.getByTestId("input-interpretation-markdown") as HTMLTextAreaElement;
  await user.clear(editor);
  await user.type(editor, "Saved Chinese revision.");
  await user.click(screen.getByTestId("button-save-interpretation"));
  await waitFor(() => expect(apiPost).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByTestId("input-interpretation-markdown")).toBeDisabled());
  await user.click(screen.getByTitle("Switch language"));
  await waitFor(() => expect(englishRequests).toBe(1));

  await act(async () => resolveSave({ success: true, body_sha256: "d".repeat(64) }));
  await waitFor(() => expect(englishRequests).toBeGreaterThan(1));
  await waitFor(() => expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument());
  await act(async () => resolveFirstEnglish({ interpretations: [staleEnglish] }));
  expect(screen.queryByTestId("article-interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Old English interpretation")).not.toBeInTheDocument();
  expect(screen.queryByText("Old English body.")).not.toBeInTheDocument();
});

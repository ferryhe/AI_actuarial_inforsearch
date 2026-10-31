import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const base = process.env.SMOKE_URL || "http://127.0.0.1:5184";
try {
  for (const lang of ["en", "zh"]) {
    for (const pending of [false, true]) {
      const page = await browser.newPage();
      await page.addInitScript((language) => localStorage.setItem("lang", language), lang);
      const source = {
        source_key: pending ? "pending" : "cas",
        source_name_zh: pending ? "来源待确认" : "北美产险精算协会",
        source_name_en: pending ? "Source pending confirmation" : "Casualty Actuarial Society (CAS)",
      };
      const file = {
        url: pending ? "https://cdn.example/paper.pdf" : "https://www.casact.org/paper.pdf",
        title: "Source fixture",
        original_filename: "paper.pdf",
        source_site: pending ? "local_docling" : "Quick Check",
        first_seen: "2026-01-01T00:00:00Z",
        ...source,
      };
      await page.route("**/api/**", (route) => {
        const url = new URL(route.request().url());
        const body = url.pathname === "/api/auth/me"
          ? { data: { require_auth: false, authenticated: true, user: { id: 1, role: "admin", is_active: true }, permissions: ["files.read", "catalog.read", "files.download", "catalog.write", "config.read"] } }
          : url.pathname === "/api/sources" ? { sources: [source.source_key], source_options: [{ ...source, count: 1, aliases: pending ? [] : ["casualty actuarial society", "casualty actuarial society (cas)"] }] }
          : url.pathname === "/api/files/detail" ? { file }
          : url.pathname === "/api/files" ? { files: url.searchParams.get("source") === "task" ? [] : [file], total: url.searchParams.get("source") === "task" ? 0 : 1 }
          : url.pathname === "/api/rag/knowledge-bases" ? { knowledge_bases: [{ kb_id: "kb-smoke", name: "Smoke KB", kb_mode: "manual", chunk_profile_id: "p", file_count: 1 }] }
          : url.pathname === "/api/rag/knowledge-bases/kb-smoke" ? { knowledge_base: { kb_id: "kb-smoke", name: "Smoke KB", kb_mode: "manual", chunk_profile_id: "p", file_count: 1 } }
          : url.pathname === "/api/rag/files/selectable" || url.pathname.endsWith("/files") ? { files: [{ ...file, file_url: file.url, chunk_set_id: "set", chunk_profile_id: "p" }], total: 1 }
          : url.pathname.endsWith("/stats") ? { file_count: 1, pending_count: 0 }
          : url.pathname === "/api/chunk/profiles" ? { profiles: [{ profile_id: "p", name: "Fixture profile", chunk_size: 512, chunk_overlap: 50 }] }
          : url.pathname === "/api/config/categories" ? { categories: { General: [] } }
          : url.pathname === "/api/rag/categories/mapping" ? { categories: ["General"] }
          : url.pathname === "/api/categories" ? { categories: [] }
          : { tasks: [], profiles: [], markdown: null };
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
      });
      const label = lang === "zh" ? source.source_name_zh : source.source_name_en;
      await page.goto(`${base}/database`);
      await page.getByText(label, { exact: true }).first().waitFor();
      assert.equal(await page.getByText(file.source_site, { exact: true }).count(), 0);
      await page.getByTestId("button-toggle-filters").click();
      const option = page.getByTestId("select-source").locator(`option[value="${source.source_key}"]`);
      assert.equal(await option.textContent(), label);
      await Promise.all([
        page.waitForRequest((request) => {
          const url = new URL(request.url());
          return url.pathname === "/api/files" && url.searchParams.get("source") === source.source_key;
        }),
        page.getByTestId("select-source").selectOption(source.source_key),
      ]);
      await page.goto(`${base}/file-detail?url=${encodeURIComponent(file.url)}`);
      await page.getByTestId("text-source").waitFor();
      assert.ok((await page.getByTestId("text-source").textContent()).includes(label));
      assert.equal(await page.getByText(file.source_site, { exact: true }).count(), 0);
      await page.goto(`${base}/knowledge`);
      await page.getByTestId("button-create-kb").click();
      await page.getByTestId("select-kb-mode").selectOption("manual");
      await page.getByText(label, { exact: true }).first().waitFor();
      assert.equal(await page.getByText(file.source_site, { exact: true }).count(), 0);
      await page.goto(`${base}/knowledge/kb-smoke`);
      await page.getByTestId("button-bind-files").click();
      await page.getByText(label, { exact: true }).first().waitFor();
      assert.equal(await page.getByText(file.source_site, { exact: true }).count(), 0);
      if (!pending) {
        await page.goto(`${base}/database?source=${encodeURIComponent("Casualty Actuarial Society")}`);
        await page.waitForFunction(() => new URL(location.href).searchParams.get("source") === "cas");
        await page.getByTestId("button-toggle-filters").click();
        assert.equal(await page.getByTestId("select-source").inputValue(), "cas");
        await page.goto(`${base}/database?source=task`);
        await page.getByTestId("button-toggle-filters").click();
        assert.equal(await page.getByTestId("select-source").inputValue(), "task");
        assert.ok((await page.getByTestId("select-source").locator('option:checked').textContent()).includes(lang === "zh" ? "待确认" : "Unrecognized"));
        assert.equal(new URL(page.url()).searchParams.get("source"), "task");
      }
      await page.close();
      console.log(JSON.stringify({ lang, source_key: source.source_key, database: "pass", file_detail: "pass", knowledge: "pass", kb_detail: "pass", exact_filter_key: "pass", old_bookmark: pending ? "not_applicable" : "exact_alias_migrates_and_ambiguous_stays_zero" }));
    }
  }
} finally {
  await browser.close();
}

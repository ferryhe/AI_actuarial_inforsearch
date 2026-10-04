import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5180";
const fixture = Array.from({ length: 1101 }, (_, i) => ({
  file_url: `https://fixture.test/${String(i).padStart(4, "0")}.pdf`,
  title: `Report ${String(i).padStart(4, "0")}`, filename: `${i}.pdf`, category: i % 2 ? "B" : "A", keywords: [],
}));
const kb = { kb_id: "kb-350", name: "Large fixture", kb_mode: "manual", chunk_profile_id: "p", file_count: 1101 };
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true,
});
const results = [];
try {
  for (const surface of ["kb", "chat"]) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    let files = [...fixture];
    const listRequests = [];
    const removed = [];
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      let body = {};
      if (path === "/api/auth/me") body = { data: { authenticated: true, require_auth: true, user: { id: 1, role: "operator", email: "smoke@example.test" }, permissions: ["catalog.read", "catalog.write"] } };
      else if (route.request().method() === "DELETE" && path.includes("/files/")) {
        const target = decodeURIComponent(path.split("/files/")[1]);
        removed.push(target);
        files = files.filter((file) => file.file_url !== target);
      } else if (path.endsWith("/files") || path.endsWith("/available-documents")) {
        const query = url.searchParams.get("query") || "";
        const category = url.searchParams.get("category");
        const offset = Number(url.searchParams.get("offset"));
        const limit = Number(url.searchParams.get("limit"));
        assert.equal(limit, 50);
        const matches = files.filter((file) => file.title.toLowerCase().includes(query.toLowerCase()) && (!category || file.category === category));
        const data = { items: matches.slice(offset, offset + limit), total: matches.length, offset, limit };
        listRequests.push({ query, category, offset, returned: data.items.length, total: data.total });
        body = path.endsWith("/available-documents") ? { success: true, data } : data;
      } else if (path.endsWith("/kb-350")) body = { knowledge_base: kb };
      else if (path.endsWith("/stats")) body = { file_count: files.length };
      else if (path.endsWith("/categories")) body = { categories: path === "/api/categories" ? ["A", "B"] : [{ name: "A" }, { name: "B" }] };
      else if (path.endsWith("/knowledge-bases")) body = { success: true, data: { knowledge_bases: [] }, knowledge_bases: [kb] };
      await route.fulfill({ json: body });
    });
    const firstRow = surface === "kb" ? "row-kb-file-0" : "document-0";
    const firstView = async (warm) => {
      const started = performance.now();
      if (warm) await page.reload({ waitUntil: "domcontentloaded" });
      else await page.goto(`${baseUrl}/${surface === "kb" ? "knowledge/kb-350" : "chat"}`, { waitUntil: "domcontentloaded" });
      await page.getByTestId(firstRow).waitFor();
      const elapsed = performance.now() - started;
      assert.ok(elapsed < (warm ? 2500 : 5000), `${surface} ${warm ? "warm" : "cold"} first view ${elapsed.toFixed(0)}ms`);
      assert.equal(listRequests.at(-1).returned, 50);
      assert.equal(listRequests.at(-1).total, 1101);
      results.push({ surface, temperature: warm ? "warm" : "cold", firstViewMs: Math.round(elapsed) });
    };
    await firstView(false);
    await firstView(true);
    const rowPattern = surface === "kb" ? /^row-kb-file-/ : /^document-\d+$/;
    assert.equal(await page.getByTestId(rowPattern).count(), 50);
    if (surface === "kb") assert.equal(await page.getByTestId(/^button-remove-file-/).count(), 50);
    // Scroll the real page list to its last mounted row before changing page.
    await page.getByTestId(surface === "kb" ? "row-kb-file-49" : "document-49").scrollIntoViewIfNeeded();
    assert.equal(await page.getByTestId(rowPattern).count(), 50);
    if (surface === "chat") await page.getByTestId("button-toggle-compare-document-0").click();
    await page.getByTestId(`${surface === "kb" ? "kb-file" : "chat-document"}-pagination-next`).click();
    await page.waitForFunction((id) => document.querySelector(`[data-testid="${id}"]`)?.getAttribute("data-file-url") === "https://fixture.test/0050.pdf", firstRow);
    if (surface === "kb") {
      await page.getByTestId("button-remove-file-0").click();
      await page.waitForFunction(() => document.querySelector('[data-testid="row-kb-file-0"]')?.getAttribute("data-file-url") === "https://fixture.test/0051.pdf");
      assert.deepEqual(removed, [fixture[50].file_url]);
      assert.equal(await page.getByTestId(/^button-remove-file-/).count(), 50);
    } else {
      await page.getByTestId("button-toggle-compare-document-0").click();
      assert.match(await page.getByTestId("compare-selected-count").innerText(), /2/);
      await page.getByTestId("chat-document-pagination-prev").click();
      await page.waitForFunction(() => document.querySelector('[data-testid="document-0"]')?.getAttribute("data-file-url") === "https://fixture.test/0000.pdf");
      assert.equal(await page.getByTestId("button-toggle-compare-document-0").locator(".lucide-check").count(), 1);
      await page.getByTestId("button-toggle-compare-document-0").click();
      assert.match(await page.getByTestId("compare-selected-count").innerText(), /1/);
    }
    const search = page.getByTestId(surface === "kb" ? "input-search-kb-files" : "input-doc-search");
    await search.fill("Report 10");
    await search.fill("Report 110");
    await search.fill("Report 1100");
    await page.waitForFunction((id) => document.querySelector(`[data-testid="${id}"]`)?.getAttribute("data-file-url") === "https://fixture.test/1100.pdf", firstRow);
    const searches = listRequests.filter((request) => request.query);
    assert.deepEqual(searches.map((request) => request.query), ["Report 1100"]);
    assert.equal(searches[0].offset, 0);
    assert.equal(await page.getByTestId(rowPattern).count(), 1);
    if (surface === "chat") {
      assert.match(await page.getByTestId("compare-selected-count").innerText(), /1/);
      assert.equal(await page.getByTestId("button-toggle-compare-document-0").locator(".lucide-check").count(), 0);
      await page.getByTestId("button-toggle-compare-document-0").click();
      assert.match(await page.getByTestId("compare-selected-count").innerText(), /2/);
    }
    if (surface === "kb") {
      await search.fill("");
      await page.getByTestId("select-kb-file-category").selectOption("B");
      await page.waitForFunction(() => document.querySelector('[data-testid="row-kb-file-0"]')?.getAttribute("data-file-url") === "https://fixture.test/0001.pdf");
      assert.equal(listRequests.at(-1).category, "B");
    }
    results.push({ surface, fixtureFiles: 1101, maxRows: 50, searchRows: 1, stableIdentity: "pass", scroll: "pass" });
    await context.close();
  }
  console.log(JSON.stringify({ chromium: "pass", backend: "local fixtures; real UI and API client", results }));
} finally {
  await browser.close();
}

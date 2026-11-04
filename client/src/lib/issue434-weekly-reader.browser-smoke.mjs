import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
const results = [];
const longSummary = "A real first sentence. " + "Further source detail. ".repeat(40);
try {
  for (const width of [1280, 390]) for (const lang of ["zh", "en"]) for (const path of ["/", "/weekly"]) for (const mode of ["empty", "fallback", "ai", "legacy_long"]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    await context.addInitScript((value) => localStorage.setItem("lang", value), lang);
    const page = await context.newPage();
    const calls = [];
    const count = mode === "empty" ? 0 : 7;
    const snapshot = { id: "weekly-fixture", period_start: "2026-10-19T00:00:00Z", period_end: "2026-10-26T00:00:00Z", generated_at: "2026-10-26T00:00:00Z", status: "published", file_count: count, metadata: {} };
    const files = Array.from({ length: count }, (_, i) => ({ url: `https://example.org/study-${i}`, title: `Study ${i}`, summary: mode === "legacy_long" && i === 0 ? longSummary : `Source case study ${i}.`, first_seen: "2026-10-20T00:00:00Z", category: i % 2 ? "Risk" : "Insurance", bilingual_metadata: {
      en: { title: `Study ${i}`, summary: mode === "legacy_long" && i === 0 ? longSummary : `Source case study ${i}.`, category: i % 2 ? "Risk" : "Insurance", keywords: ["Insurance AI"] },
      zh: { title: `研究 ${i}`, summary: `中文研究摘要 ${i}。`, category: i % 2 ? "Risk" : "Insurance", keywords: ["保险AI"] },
    }, keywords: ["Insurance AI"] }));
    const savedGuide = (lang) => (lang === "zh" ? "本周关注保险AI。" : "This week focuses on insurance AI.") + "\n\n" + [6, 1, 4].map(i => `- [Study ${i}](https://example.org/study-${i})\n  Source case study ${i}.`).join("\n\n");
    await page.route("**/api/**", async route => {
      const request = route.request();
      calls.push({ method: request.method(), path: new URL(request.url()).pathname });
      const url = new URL(request.url());
      let payload = {};
      if (url.pathname === "/api/auth/me") payload = { data: { require_auth: false, permissions: ["stats.read", "files.read"], authenticated: false } };
      else if (url.pathname === "/api/weekly-updates/latest") payload = { summary: snapshot };
      else if (url.pathname === "/api/weekly-updates") payload = { summaries: [snapshot], total: 1, limit: 100, offset: 0 };
      else if (url.pathname.endsWith("/files")) {
        const limit = Number(url.searchParams.get("limit"));
        const offset = Number(url.searchParams.get("offset"));
        payload = { snapshot_id: snapshot.id, files: files.slice(offset, offset + limit), total: count, limit, offset };
      }
      else if (url.pathname.endsWith("/explanation")) payload = { explanation: { snapshot_id: snapshot.id, status: ["fallback", "legacy_long"].includes(mode) ? "failed" : "complete", generation_mode: mode === "legacy_long" ? undefined : mode, explanation_zh: mode === "ai" ? savedGuide("zh") : "", explanation_en: mode === "ai" ? savedGuide("en") : "", generated_at: snapshot.generated_at } };
      else if (url.pathname === `/api/weekly-updates/${snapshot.id}`) payload = { summary: snapshot };
      else if (url.pathname.includes("stats")) payload = { total_files: count, total_sources: 1 };
      else if (url.pathname.includes("categories")) payload = { categories: [] };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    });
    await page.goto((process.env.SMOKE_URL || "http://127.0.0.1:5434") + path, { waitUntil: "networkidle" });
    const state = ["fallback", "legacy_long"].includes(mode) ? "failed" : mode === "ai" ? "complete" : "empty";
    const guide = page.getByTestId(`weekly-explanation-${state}`);
    await guide.waitFor({ state: "visible" });
    const text = await guide.innerText();
    if (mode === "empty") assert.equal(text, lang === "zh" ? "本周暂无新资料。" : "No new material this week.");
    else {
      assert.ok(text.includes(lang === "zh" ? "本周发现 7 篇文章" : "discovered 7 articles"));
      assert.equal(await guide.locator("ol li").count(), 3);
      const rows = page.locator('[data-testid^="weekly-file-row-"]');
      assert.equal(await rows.count(), path === "/" ? 6 : 7);
      const expected = mode === "ai" ? [6, 1, 4] : [0, 1, 2];
      for (const [index, id] of expected.entries()) {
        assert.ok((await rows.nth(index).innerText()).includes(lang === "zh" ? `研究 ${id}` : `Study ${id}`));
      }
      assert.equal(await guide.locator("a").count(), 0);
    }
    if (mode === "legacy_long" && lang === "en") assert.ok((await page.getByTestId("weekly-summary-0").innerText()).replace(/\s+/g, " ").includes(longSummary.trim()));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    assert.ok(calls.every(call => call.method === "GET" && !/generate|retry/.test(call.path)));
    if (process.env.REPORT_DIR) {
      await guide.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${process.env.REPORT_DIR}/${width}-${lang}-${path === "/" ? "home" : "detail"}-${mode}.png`, fullPage: true });
    }
    results.push({ width, lang, path, mode, modelCalls: 0, pass: true });
    await context.close();
  }
  console.log(JSON.stringify({ fixtureOnly: true, cases: results }, null, 2));
} finally {
  await browser.close();
}

import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
const results = [];
const longSummary = "A real first sentence. " + "Further source detail. ".repeat(40);
try {
  for (const lang of ["zh", "en"]) for (const path of ["/", "/weekly"]) for (const mode of ["empty", "fallback", "ai", "legacy_long"]) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.addInitScript((value) => localStorage.setItem("lang", value), lang);
    const page = await context.newPage();
    const calls = [];
    const count = mode === "empty" ? 0 : 5;
    const snapshot = { id: "weekly-fixture", period_start: "2026-10-19T00:00:00Z", period_end: "2026-10-26T00:00:00Z", generated_at: "2026-10-26T00:00:00Z", status: "published", file_count: count, metadata: {} };
    const files = Array.from({ length: count }, (_, i) => ({ url: `https://example.org/study-${i}`, title: `Study ${i}`, summary: mode === "legacy_long" && i === 0 ? longSummary : `Source case study ${i}.`, first_seen: "2026-10-20T00:00:00Z", keywords: ["Insurance AI"] }));
    await page.route("**/api/**", async route => {
      const request = route.request();
      calls.push({ method: request.method(), path: new URL(request.url()).pathname });
      const url = new URL(request.url());
      let payload = {};
      if (url.pathname === "/api/auth/me") payload = { data: { require_auth: false, permissions: ["stats.read", "files.read"], authenticated: false } };
      else if (url.pathname === "/api/weekly-updates/latest") payload = { summary: snapshot };
      else if (url.pathname === "/api/weekly-updates") payload = { summaries: [snapshot], total: 1, limit: 100, offset: 0 };
      else if (url.pathname.endsWith("/files")) payload = { snapshot_id: snapshot.id, files, total: count, limit: 500, offset: 0 };
      else if (url.pathname.endsWith("/explanation")) payload = { explanation: { snapshot_id: snapshot.id, status: ["fallback", "legacy_long"].includes(mode) ? "failed" : "complete", generation_mode: mode === "legacy_long" ? undefined : mode, explanation_zh: mode === "ai" ? "本周关注保险AI。\n\n- [Study 0](https://example.org/study-0)\n  Source case study 0.\n  适合关注保险AI方法的读者。" : "", explanation_en: mode === "ai" ? "This week focuses on insurance AI.\n\n- [Study 0](https://example.org/study-0)\n  Source case study 0.\n  For readers following insurance AI methods." : "", generated_at: snapshot.generated_at } };
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
      assert.ok(text.includes("Study 0"));
      assert.ok(await guide.locator('a[href="https://example.org/study-0"]').count() === 1);
    }
    if (mode === "legacy_long") assert.ok(text.replace(/\s+/g, " ").includes(longSummary.trim()));
    assert.ok(calls.every(call => call.method === "GET" && !/generate|retry/.test(call.path)));
    if (process.env.REPORT_DIR) await page.screenshot({ path: `${process.env.REPORT_DIR}/${lang}-${path === "/" ? "home" : "detail"}-${mode}.png`, fullPage: true });
    results.push({ lang, path, mode, modelCalls: 0, pass: true });
    await context.close();
  }
  console.log(JSON.stringify({ fixtureOnly: true, cases: results }, null, 2));
} finally {
  await browser.close();
}

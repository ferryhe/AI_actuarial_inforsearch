import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { chromium } from "playwright-core";

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
const base = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const target = { kb_id: "public", file_id: "soa-report" };
const source = { source_type: "catalog", file_id: "soa-report", section_id: "", kb_id: "public", title: "Current SOA report", link: "/file-detail?url=https%3A%2F%2Fexample.org%2Fsoa.pdf", source_version: null, source_date: "2026-11-01", stale: false };
const answer = (text, extra = {}) => ({ schema_version: "1.0", intent: "answer", answer: text, citations: [], evidence_ids: [], selected_target: null, feedback_draft: null, availability: "available", error_code: null, stop_reason: "finish", ...extra });

async function setup(page, language, responses) {
  const requests = [];
  await page.addInitScript((lang) => localStorage.setItem("lang", lang), language);
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { success: true, data: { require_auth: false, authenticated: true, user: { id: 7, email: "reader@example.org", display_name: "Reader", role: "registered", is_active: true }, permissions: ["chat.query", "files.read", "catalog.read", "markdown.read", "stats.read"] } } });
    if (url.pathname === "/api/support/capabilities") return route.fulfill({ json: { assistant_enabled: true, feedback_enabled: true } });
    if (url.pathname === "/api/weekly-updates/latest") return route.fulfill({ json: { summary: null } });
    if (url.pathname === "/api/files/detail") return route.fulfill({ json: { file: { url: "https://example.org/soa.pdf", title: "Current SOA report", original_filename: "soa.pdf", source_site: "SOA", content_type: "application/pdf", bytes: 1234, summary: "A stubbed report for navigation testing." } } });
    if (url.pathname.includes("/markdown")) return route.fulfill({ json: { markdown: { markdown_content: "# Current SOA report\n\nStubbed report body.", markdown_source: "test" } } });
    if (url.pathname === "/api/chat/knowledge-bases") return route.fulfill({ json: { success: true, data: { knowledge_bases: [] } } });
    if (url.pathname === "/api/assistant/v1/query" && route.request().method() === "POST") {
      requests.push(route.request().postDataJSON());
      return route.fulfill({ json: responses.shift() });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto(`${base}/chat`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("support-widget-trigger").click();
  await page.locator("#assistant-message").waitFor();
  return requests;
}

async function ask(page, text, count) {
  await page.locator("#assistant-message").fill(text);
  await page.locator('#assistant-panel form button[type="submit"]').click();
  await page.locator("#assistant-panel article").nth(count - 1).waitFor();
}

try {
  const soa = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const soaRequests = await setup(soa, "en", [
    answer("Found the latest SOA report.", { selected_target: target, citations: [source], evidence_ids: ["catalog:soa"] }),
    answer("The report body was read for this answer.", { selected_target: target, citations: [{ ...source, source_type: "kb", section_id: "findings", source_version: "published-1" }], evidence_ids: ["body:soa"] }),
    answer("The same current report remains the source.", { selected_target: target, citations: [source], evidence_ids: ["catalog:soa"] }),
  ]);
  await ask(soa, "Latest SOA material", 1);
  await soa.locator("#assistant-panel article").first().getByRole("link", { name: /Current SOA report/ }).click();
  await soa.waitForURL("**/file-detail?url=*");
  await soa.locator("main").getByText("Current SOA report").first().waitFor();
  assert.equal(await soa.locator("#assistant-panel article").count(), 1, "file navigation must retain the assistant conversation");
  await ask(soa, "Read this report", 2);
  await ask(soa, "What is its source?", 3);
  assert.deepEqual(soaRequests[1].selected_target, target);
  assert.deepEqual(soaRequests[2].selected_target, target);
  assert.deepEqual(soaRequests[2].recent_questions, ["Latest SOA material", "Read this report"]);
  assert.equal(soaRequests[2].mode, undefined);
  assert.equal(await soa.locator("#assistant-panel article").last().getByRole("link", { name: /Current SOA report/ }).count(), 1);
  await soa.screenshot({ path: process.env.SOA_SCREENSHOT_PATH || "soa-conversation.png" });

  const weekly = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const weeklyRequests = await setup(weekly, "zh", [
    answer("网站提供资料检索、知识库和周报。"),
    answer("打开[周报](/weekly)，查看完整已发布周期。"),
    answer("本周新增请查看当前已发布周报；没有完整周期时不会声称已有新增。"),
  ]);
  await ask(weekly, "网站有哪些功能？", 1);
  await ask(weekly, "周报怎么用？", 2);
  await weekly.locator("#assistant-panel article").nth(1).getByRole("link", { name: "周报" }).click();
  await weekly.waitForURL("**/weekly");
  assert.equal(await weekly.locator("#assistant-panel article").count(), 2);
  assert.equal(await weekly.getByTestId("weekly-page").count(), 1);
  await ask(weekly, "这周新增了什么？", 3);
  assert.deepEqual(weeklyRequests[2].recent_questions, ["网站有哪些功能？", "周报怎么用？"]);
  assert.equal(weeklyRequests[2].locale, "zh");
  await weekly.screenshot({ path: process.env.WEEKLY_SCREENSHOT_PATH || "weekly-conversation.png" });

  const portals = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const portalRequests = await setup(portals, "en", [
    answer("Showing 12 of 13 sources; open [Source Portals](/source-portals)."),
    answer("Recent SOA report.", { citations: [source], selected_target: target, evidence_ids: ["resource:recent"] }),
    answer("The same report remains selected.", { selected_target: target }),
  ]);
  await ask(portals, "Which sources are available?", 1);
  await portals.locator("#assistant-panel article").first().getByRole("link", { name: "Source Portals" }).click();
  await portals.waitForURL("**/source-portals");
  await portals.getByTestId("source-portals-title").waitFor();
  assert.equal(await portals.locator("#assistant-panel article").count(), 1);
  await ask(portals, "Show recent SOA material", 2);
  await portals.locator("#assistant-panel article").nth(1).getByRole("link", { name: /Current SOA report/ }).click();
  await portals.waitForURL("**/file-detail?url=*");
  assert.equal(await portals.locator("#assistant-panel article").count(), 2);
  await ask(portals, "Where did that report come from?", 3);
  assert.deepEqual(portalRequests[2].selected_target, target);
  assert.deepEqual(portalRequests[2].recent_questions, ["Which sources are available?", "Show recent SOA material"]);

  const evidence = { transport: "/api/assistant/v1/query", provider: "stub", device: "Chromium 390x844 and desktop; not physical iOS", soa: { requests: soaRequests, path: new URL(soa.url()).pathname, sourceLink: source.link }, weekly: { requests: weeklyRequests, path: new URL(weekly.url()).pathname }, sourcePortals: { requests: portalRequests, path: new URL(portals.url()).pathname } };
  await writeFile(process.env.SMOKE_EVIDENCE_PATH || "issue479-conversation.json", `${JSON.stringify(evidence, null, 2)}\n`);
  console.log("Issue #479 browser conversation flows passed");
} finally {
  await browser.close();
}

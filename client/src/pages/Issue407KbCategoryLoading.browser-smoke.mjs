import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";
import { fileURLToPath } from "node:url";

const baseUrl = process.env.SMOKE_URL || "http://issue407.local";
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const assetDir = path.join(repoRoot, "dist", "public", "assets");
const indexHtml = await readFile(path.join(repoRoot, "dist", "public", "index.html"), "utf8");
const assetNames = new Set(await readdir(assetDir));
const categories = [
  { name: "AI", count: 3 },
  { name: "Database", count: 5 },
  ...Array.from({ length: 14 }, (_, index) => ({ name: `Category ${index + 3}`, count: index + 1 })),
];
const permissions = {
  guest: ["files.read"],
  registered: ["files.read", "catalog.read", "chat.view", "chat.query"],
  admin: ["files.read", "catalog.read", "catalog.write", "chat.view", "chat.query", "tasks.run", "config.write"],
};
const mapping = { knowledge_bases: [{ kb_id: "kb-ai", categories: ["AI"] }] };
const chatKnowledgeBases = [{ kb_id: "kb-ai", usable: true, serving: true, reason: "healthy" }];
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const browser = await chromium.launch({ executablePath: chromePath, headless: true });
const measurements = [];

async function makeFixturePage(role, { retryScenario = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const apiCalls = [];
  let activeApiRoutes = 0;
  let idleWaiters = [];
  let mappingRequests = 0;
  let kbListRequests = 0;

  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== baseUrl) {
      await route.abort();
      return;
    }
    if (url.pathname.startsWith("/assets/")) {
      const name = path.basename(url.pathname);
      if (!assetNames.has(name)) {
        await route.fulfill({ status: 404, body: "fixture asset not found" });
        return;
      }
      const body = await readFile(path.join(assetDir, name));
      const contentType = name.endsWith(".css") ? "text/css" : "text/javascript";
      await route.fulfill({ status: 200, contentType, body });
      return;
    }
    await route.fulfill({ status: 200, contentType: "text/html", body: indexHtml });
  });

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const startedAt = performance.now();
    const call = { path: url.pathname, query: Object.fromEntries(url.searchParams), startedAt };
    apiCalls.push(call);
    activeApiRoutes += 1;
    try {
      let status = 200;
      let body = {};
      let delayMs = 15;
      if (url.pathname === "/api/auth/me") {
        body = {
          data: {
            require_auth: role !== "guest",
            authenticated: role !== "guest",
            user: role === "guest" ? null : { id: 1, email: `${role}@fixture.test`, display_name: role, role, is_active: true },
            permissions: permissions[role],
          },
        };
      } else if (url.pathname === "/api/categories") {
        body = { categories };
        delayMs = 60;
      } else if (url.pathname === "/api/rag/knowledge-bases" && url.searchParams.has("include_diagnostics")) {
        mappingRequests += 1;
        delayMs = role === "registered" ? 1_300 : 800;
        if (retryScenario && mappingRequests === 1) {
          status = 502;
          body = { detail: "fixture KB mapping failure" };
        } else {
          body = mapping;
        }
      } else if (url.pathname === "/api/chat/knowledge-bases") {
        delayMs = role === "registered" ? 1_600 : 1_100;
        body = { knowledge_bases: chatKnowledgeBases };
      } else if (url.pathname === "/api/rag/knowledge-bases") {
        kbListRequests += 1;
        delayMs = 30;
        status = retryScenario && kbListRequests === 1 ? 502 : 200;
        body = status === 200 ? { knowledge_bases: [] } : { detail: "fixture KB list failure" };
      } else if (url.pathname === "/api/chunk/profiles") {
        body = { profiles: [] };
      } else if (url.pathname === "/api/rag/categories/mapping") {
        body = { categories: [] };
      } else if (url.pathname === "/api/sources") {
        body = { sources: [] };
      } else if (url.pathname === "/api/files") {
        body = {
          files: [{
            url: "https://fixture.test/database.pdf",
            title: "Database report",
            original_filename: "database.pdf",
            source_site: "fixture.test",
            content_type: "application/pdf",
            first_seen: "2026-10-01T00:00:00Z",
            last_seen: "2026-10-02T00:00:00Z",
            category: "Database",
            keywords: [],
            summary: null,
            has_markdown: false,
            markdown_source: null,
            bytes: 128,
            deleted_at: null,
          }],
          total: 1,
          limit: 20,
          offset: 0,
        };
      }
      await sleep(delayMs);
      const serialized = JSON.stringify(body);
      call.delayMs = delayMs;
      call.status = status;
      call.bytes = Buffer.byteLength(serialized);
      await route.fulfill({ status, contentType: "application/json", body: serialized });
    } finally {
      call.completedAt = performance.now();
      activeApiRoutes -= 1;
      if (activeApiRoutes === 0) {
        for (const resolve of idleWaiters) resolve();
        idleWaiters = [];
      }
    }
  });

  return {
    apiCalls,
    context,
    page,
    waitForApiIdle: () => activeApiRoutes === 0
      ? Promise.resolve()
      : new Promise((resolve) => idleWaiters.push(resolve)),
    getMappingRequests: () => mappingRequests,
  };
}

function summarizeNavigation(role, temperature, apiCalls, uiReadyMs) {
  const start = Math.min(...apiCalls.map((call) => call.startedAt));
  const end = Math.max(...apiCalls.map((call) => call.completedAt));
  const categoriesCall = apiCalls.find((call) => call.path === "/api/categories");
  assert.ok(categoriesCall, `${role} did not request categories`);
  return {
    role,
    fixtureCategories: categories.length,
    temperature,
    apiRequestCount: apiCalls.length,
    categoryTtfbMs: Math.round(categoriesCall.completedAt - categoriesCall.startedAt),
    apiDurationMs: Math.round(end - start),
    responseBytes: apiCalls.reduce((total, call) => total + call.bytes, 0),
    uiReadyMs: Math.round(uiReadyMs),
  };
}

try {
  for (const role of ["guest", "registered", "admin"]) {
    const fixture = await makeFixturePage(role);
    const { page, apiCalls, waitForApiIdle } = fixture;
    for (const temperature of ["cold", "warm"]) {
      const navigationStart = apiCalls.length;
      const start = performance.now();
      if (temperature === "cold") {
        await page.goto(`${baseUrl}/categories`, { waitUntil: "domcontentloaded" });
      } else {
        await page.reload({ waitUntil: "domcontentloaded" });
      }
      await page.getByTestId("categories-grid").waitFor();
      const uiReadyMs = performance.now() - start;
      await waitForApiIdle();
      const navigationCalls = apiCalls.slice(navigationStart);
      const sample = summarizeNavigation(role, temperature, navigationCalls, uiReadyMs);
      assert.ok(sample.uiReadyMs < 900, `${role} ${temperature} grid exceeded the 900ms local fixture budget`);
      assert.ok(sample.categoryTtfbMs < 300, `${role} ${temperature} category response exceeded local TTFB budget`);
      measurements.push(sample);
    }

    const mappingCalls = apiCalls.filter((call) => call.path === "/api/rag/knowledge-bases" && "include_diagnostics" in call.query);
    const chatCalls = apiCalls.filter((call) => call.path === "/api/chat/knowledge-bases");
    if (role === "guest") {
      assert.equal(mappingCalls.length, 0);
      assert.equal(chatCalls.length, 0);
    } else {
      assert.equal(mappingCalls.length, 2);
      assert.ok(mappingCalls.every((call) => call.query.include_diagnostics === "false"));
      assert.equal(chatCalls.length, 2);
    }

    if (role === "registered") {
      await page.getByTestId("input-category-search").fill("Database");
      assert.equal(await page.getByTestId("category-card-title").count(), 1);
      const databaseLink = page.locator('a[href="/database?category=Database"]');
      const fileResponse = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return url.pathname === "/api/files" && url.searchParams.get("category") === "Database";
      });
      await Promise.all([fileResponse, databaseLink.click()]);
      await page.waitForTimeout(100);
      const browsedUrl = new URL(page.url());
      assert.equal(browsedUrl.pathname, "/database");
      assert.equal(browsedUrl.searchParams.get("category"), "Database");
      const fileCall = apiCalls.find((call) => call.path === "/api/files");
      assert.equal(fileCall.query.category, "Database");
    }
    await fixture.context.close();
  }

  const adminRetry = await makeFixturePage("admin", { retryScenario: true });
  await adminRetry.page.goto(`${baseUrl}/categories`, { waitUntil: "domcontentloaded" });
  await adminRetry.page.getByTestId("categories-grid").waitFor();
  await adminRetry.page.getByTestId("categories-kb-error").waitFor();
  assert.equal(await adminRetry.page.getByTestId("button-ask-ai-category-AI").isEnabled(), false);
  await adminRetry.page.getByTestId("categories-kb-error").getByRole("button").click();
  await adminRetry.page.getByTestId("button-ask-ai-category-AI").waitFor({ state: "visible" });
  await adminRetry.waitForApiIdle();
  assert.equal(await adminRetry.page.getByTestId("categories-kb-error").count(), 0);
  assert.equal(await adminRetry.page.getByTestId("button-ask-ai-category-AI").isEnabled(), true);
  measurements.push({ role: "admin", flow: "category-mapping-failure-retry", mappingRequests: adminRetry.getMappingRequests(), result: "passed" });

  let kbAttempts = 0;
  await adminRetry.page.route("**/api/rag/knowledge-bases", async (route) => {
    kbAttempts += 1;
    const status = kbAttempts === 1 ? 502 : 200;
    const body = status === 200 ? { knowledge_bases: [] } : { detail: "fixture KB list failure" };
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await adminRetry.page.goto(`${baseUrl}/knowledge`, { waitUntil: "domcontentloaded" });
  await adminRetry.page.getByTestId("knowledge-list-error").waitFor();
  assert.equal(await adminRetry.page.getByTestId("text-no-kbs").count(), 0);
  await adminRetry.page.getByTestId("knowledge-list-error").getByRole("button").click();
  await adminRetry.page.getByTestId("text-no-kbs").waitFor();
  assert.equal(kbAttempts, 2);
  measurements.push({ role: "admin", flow: "KB-error-retry-valid-empty", requests: kbAttempts, result: "passed" });
  await adminRetry.context.close();

  console.log(JSON.stringify({
    browser: "Chromium",
    source: "built local UI bundle with intercepted API fixtures",
    localUiReadyBudgetMs: 900,
    delayedSupplementaryBudgetMs: { registeredMapping: 1300, chatReadiness: 1600 },
    measurements,
  }, null, 2));
} finally {
  await browser.close();
}

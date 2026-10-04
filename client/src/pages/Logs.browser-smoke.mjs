import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const cases = [
  { role: "registered", permissions: ["tasks.view", "logs.task.read"] },
  { role: "operator", permissions: ["tasks.view", "tasks.run", "logs.task.read"] },
  { role: "admin", permissions: ["tasks.view", "logs.task.read", "logs.system.read"] },
];
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});

try {
  for (const userCase of cases) {
    const page = await browser.newPage();
    const apiRequests = [];
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      apiRequests.push(url.pathname + url.search);
      if (url.pathname === "/api/auth/me") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: {
              require_auth: true,
              authenticated: true,
              user: {
                id: 1,
                email: userCase.role + "@example.test",
                display_name: userCase.role,
                role: userCase.role,
                is_active: true,
              },
              permissions: userCase.permissions,
            },
          }),
        });
      } else if (url.pathname === "/api/logs/global") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ logs: "INFO ordinary entry\nERROR needle entry" }),
        });
      } else if (url.pathname === "/api/tasks/history") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            tasks: [
              { id: "task-1", name: "Smoke task", type: "mystery_internal_type", status: "mystery_internal_status", started_at: "2026-09-30T12:00:00", items_processed: 1 },
              { id: "task-2", name: "Known task", type: "catalog", status: "completed", started_at: "2026-09-30T12:00:00", items_processed: 1 },
              { id: "task-3", name: "Embedding task", type: "embedding_generation", status: "queued", started_at: "2026-09-30T12:00:00", items_processed: 0 },
              { id: "task-4", name: "Ready data task", type: "ready_data_build", status: "stopping", started_at: "2026-09-30T12:00:00", items_processed: 0 },
            ],
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
      }
    });

    await page.addInitScript(() => localStorage.setItem("lang", "zh"));
    await page.goto(baseUrl + "/logs", { waitUntil: "networkidle" });
    await page.getByTestId("text-logs-title").waitFor();
    const globalRequests = () => apiRequests.filter((url) => url === "/api/logs/global").length;

    if (userCase.role === "admin") {
      await page.getByTestId("section-system-logs").waitFor();
      assert.ok(globalRequests() > 0, "admin did not request global logs");
      await page.getByTestId("button-filter-error").click();
      assert.doesNotMatch(await page.getByTestId("container-log-entries").textContent(), /ordinary entry/);
      await page.getByTestId("button-filter-all").click();
      await page.getByTestId("input-log-search").fill("needle");
      assert.doesNotMatch(await page.getByTestId("container-log-entries").textContent(), /ordinary entry/);
      const beforeRefresh = globalRequests();
      const refreshRequest = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/logs/global");
      await page.getByTestId("button-refresh-logs").click();
      await refreshRequest;
      assert.ok(globalRequests() > beforeRefresh, "admin refresh did not request global logs");
    } else {
      const row = page.getByTestId("row-history-task-task-1");
      const knownRow = page.getByTestId("row-history-task-task-2");
      const embeddingRow = page.getByTestId("row-history-task-task-3");
      const readyDataRow = page.getByTestId("row-history-task-task-4");
      await row.waitFor();
      await knownRow.waitFor();
      await embeddingRow.waitFor();
      await readyDataRow.waitFor();
      assert.match(await row.textContent(), /未知状态/);
      assert.match(await knownRow.textContent(), /编目/);
      assert.match(await knownRow.textContent(), /已完成/);
      assert.match(await embeddingRow.textContent(), /分块与嵌入/);
      assert.match(await embeddingRow.textContent(), /排队中/);
      assert.match(await readyDataRow.textContent(), /就绪数据构建/);
      assert.match(await readyDataRow.textContent(), /正在停止/);
      if (userCase.role === "registered") {
        assert.doesNotMatch(await row.innerHTML(), /mystery_internal_(?:type|status)/);
        assert.equal(await row.locator("details").count(), 0);
      } else {
        assert.equal(await row.locator("details").count(), 2);
        assert.ok(await row.locator("details").nth(0).textContent().then((text) => text.includes("mystery_internal_type")));
        assert.ok(await row.locator("details").nth(1).textContent().then((text) => text.includes("mystery_internal_status")));
        assert.equal(await row.locator("details[open]").count(), 0);
        await row.locator("details summary").nth(0).click();
        await page.waitForFunction(() => document.querySelector('[data-testid="row-history-task-task-1"] details')?.open === true);
        assert.equal(await page.getByTestId("modal-task-log").count(), 0, "opening type diagnostics opened the task log");
        await row.locator("details summary").nth(1).click();
        await page.waitForFunction(() => document.querySelectorAll('[data-testid="row-history-task-task-1"] details[open]').length === 2);
        assert.equal(await page.getByTestId("modal-task-log").count(), 0, "opening status diagnostics opened the task log");
      }
      await page.getByTestId("toggle-lang").click();
      await page.waitForFunction(() => document.documentElement.lang === "en");
      assert.match(await row.textContent(), /Unknown status/);
      assert.doesNotMatch(await row.textContent(), /未知状态/);
      assert.match(await knownRow.textContent(), /Catalog/);
      assert.match(await knownRow.textContent(), /Completed/);
      assert.match(await embeddingRow.textContent(), /Chunk & Embedding/);
      assert.match(await embeddingRow.textContent(), /Queued/);
      assert.match(await readyDataRow.textContent(), /Ready Data Build/);
      assert.match(await readyDataRow.textContent(), /Stopping/);
      assert.equal(globalRequests(), 0, userCase.role + " requested global logs");
      assert.equal(await page.getByTestId("section-system-logs").count(), 0, userCase.role + " mounted system logs");
      assert.equal(await page.getByTestId("button-refresh-logs").count(), 0, userCase.role + " mounted global controls");
      assert.equal(await page.getByTestId("input-log-search").count(), 0, userCase.role + " mounted global search");
      assert.equal(await page.getByTestId("button-filter-error").count(), 0, userCase.role + " mounted global filters");
    }

    console.log(JSON.stringify({ role: userCase.role, globalLogRequests: globalRequests(), apiRequests }));
    await page.close();
  }
} finally {
  await browser.close();
}

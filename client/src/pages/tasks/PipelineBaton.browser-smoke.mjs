import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const projectedErrorCodes = [
  ["orchestration", "orchestration_error", "Pipeline orchestration failed", "流程编排失败"],
  ["invalid-index", "invalid_index_result", "Invalid index result", "索引结果无效"],
  ["ready-launch", "ready_launch_failed", "Ready Data launch failed", "就绪数据启动失败"],
  ["generic-error", "error", "Error", "错误"],
];

try {
  for (const role of ["registered", "operator", "admin"]) {
    const page = await browser.newPage();
    await page.addInitScript(() => localStorage.setItem("lang", "zh"));
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let body = {};
      if (path === "/api/auth/me") {
        body = { data: { authenticated: true, require_auth: true, user: { id: 1, email: `${role}@example.test`, display_name: role, role, is_active: true }, permissions: ["tasks.view", ...(role === "operator" || role === "admin" ? ["tasks.run"] : [])] } };
      } else if (path === "/api/pipeline/status") {
        body = {
          config: { overrides: {} },
          state: { round_status: "private_phase" },
          summary: { status: "private_phase", successful_stages: 0, failed_stages: 1, stopped_stages: 0, latest_failure: { task_id: null, stage: "rag_indexing", error_count: 1, first_error_code: "", summary: "build_failure: Ready Data artifact digest mismatch" } },
          stages: [
            { step: "scheduled", status: "private_phase", tasks: [], failures: [] },
            { step: "markdown_conversion", status: "idle", tasks: [], failures: [] },
            { step: "catalog", status: "idle", tasks: [], failures: [] },
            { step: "chunk_generation", status: "idle", tasks: [], failures: [] },
            { step: "rag_indexing", status: "failed", tasks: projectedErrorCodes.map(([id, code]) => ({ task_id: id, status: "failed", error_count: 1, first_error_code: code, first_error_summary: "", failed_items: 1, label: code })), failures: [{ task_id: null, first_error_code: "", first_error_summary: "build_failure: Ready Data artifact digest mismatch" }] },
          ],
        };
      } else if (path === "/api/scheduled-tasks") body = { tasks: [] };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });

    await page.goto(`${baseUrl}/tasks`, { waitUntil: "domcontentloaded" });
    await page.getByTestId("tab-pipeline-baton").click();
    const summary = page.getByTestId("pipeline-display-status");
    const stage = page.getByTestId("pipeline-step-scheduled");
    const latestFailure = page.getByTestId("pipeline-latest-failure");
    const launchFailure = page.getByTestId("pipeline-failure-rag_indexing-0");
    await summary.waitFor();
    assert.match(await summary.textContent(), /未知状态/);
    assert.match(await stage.getByTestId("pipeline-stage-status-scheduled").textContent(), /未知状态/);
    assert.match(await latestFailure.textContent(), /就绪数据处理失败/);
    assert.match(await launchFailure.textContent(), /就绪数据处理失败/);
    for (const [id, , , zhLabel] of projectedErrorCodes) {
      assert.match(await page.getByTestId(`button-pipeline-task-log-${id}`).textContent(), new RegExp(zhLabel));
    }

    if (role === "registered") {
      assert.doesNotMatch(await summary.innerHTML(), /private_phase/);
      assert.doesNotMatch(await latestFailure.innerHTML(), /build_failure|Ready Data artifact digest mismatch/);
      assert.doesNotMatch(await launchFailure.innerHTML(), /build_failure|Ready Data artifact digest mismatch/);
      assert.equal(await page.locator("details").count(), 0);
    } else {
      assert.equal(await page.locator("details").count(), 8);
      assert.equal(await page.locator("details[open]").count(), 0);
      const stageButton = stage.getByTestId("button-pipeline-stage-scheduled");
      const priorExpanded = await stageButton.getAttribute("aria-expanded");
      const ragButton = page.getByTestId("button-pipeline-stage-rag_indexing");
      const ragPriorExpanded = await ragButton.getAttribute("aria-expanded");
      await latestFailure.locator("details summary").click();
      assert.equal(await latestFailure.locator("details").evaluate((details) => details.open), true);
      assert.match(await latestFailure.locator("details").textContent(), /build_failure: Ready Data artifact digest mismatch/);
      await launchFailure.locator("details summary").click();
      assert.equal(await launchFailure.locator("details").evaluate((details) => details.open), true);
      assert.equal(await ragButton.getAttribute("aria-expanded"), ragPriorExpanded);
      await summary.locator("details summary").click();
      assert.equal(await summary.locator("details").evaluate((details) => details.open), true);
      assert.equal(await stageButton.getAttribute("aria-expanded"), priorExpanded);
      await stage.locator("details summary").click();
      assert.equal(await stage.locator("details").evaluate((details) => details.open), true);
      assert.equal(await stageButton.getAttribute("aria-expanded"), priorExpanded);
      assert.equal(await page.getByTestId("modal-task-log").count(), 0);
    }

    await page.getByTestId("toggle-lang").click();
    await page.waitForFunction(() => document.documentElement.lang === "en");
    assert.match(await summary.textContent(), /Unknown status/);
    assert.match(await stage.getByTestId("pipeline-stage-status-scheduled").textContent(), /Unknown status/);
    assert.match(await latestFailure.textContent(), /Ready Data operation failed/);
    assert.match(await launchFailure.textContent(), /Ready Data operation failed/);
    for (const [id, , enLabel] of projectedErrorCodes) {
      assert.match(await page.getByTestId(`button-pipeline-task-log-${id}`).textContent(), new RegExp(enLabel));
    }
    console.log(JSON.stringify({ role, diagnostics: await page.locator("details").count() }));
    await page.close();
  }
} finally {
  await browser.close();
}

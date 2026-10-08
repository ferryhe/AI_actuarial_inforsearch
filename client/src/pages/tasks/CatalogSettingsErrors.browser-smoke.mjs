import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5186";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const taskId = "task_123_0123456789abcdef";
// These API fixtures exercise the confirmed UI targets; backend tests cover full digest matching.
const examples = [["1710b9c445ac", 793], ["664ceca4aa6a", 735], ["09897b3e032e", 351]];
const errors = examples.map(([digest, id]) => ({ object_id: `file:${digest.padEnd(64, "0")}`, display_name: `File ${digest}`, stage: "catalog", code: "catalog_failed", summary: "Catalog processing failed.", file_id: String(id), context_url: `/file-detail?file_id=${id}` }));
errors.push({ object_id: `file:${"f".repeat(64)}`, display_name: "File unmatched", stage: "catalog", code: "catalog_failed", summary: "Catalog processing failed." });

try {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const requests = [];
    let candidateCount = 4;
    await page.addInitScript(() => localStorage.setItem("lang", "zh"));
    await page.route("**/api/**", async route => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      requests.push({ path, search: url.search, method: request.method(), body: request.postDataJSON() });
      let body = {};
      if (path === "/api/auth/me") body = { data: { require_auth: true, authenticated: true, user: { id: 1, email: "smoke@example.test", display_name: "Smoke", role: "admin", is_active: true }, permissions: ["tasks.run", "tasks.view", "schedule.write", "config.read", "config.write", "catalog.read", "catalog.write", "files.read", "markdown.read"] } };
      if (path === "/api/config/llm-providers") body = { providers: [{ name: "openai", status: "configured", decrypt_ok: true }] };
      if (path === "/api/config/ai-models") body = { current: { catalog: { provider: "openai", model: "smoke" } }, available: { openai: [{ name: "smoke", types: ["chat"] }] } };
      if (path === "/api/categories") body = { categories: ["General"] };
      if (path === "/api/catalog/stats") body = { total_local_files: 30, total_catalog_ok: 26, candidate_total: candidateCount, first_candidate_index: 27 };
      if (path === "/api/config/backend-settings") body = { defaults: {}, features: { enable_file_deletion: false, require_auth: true, sources: { require_auth: "env" } }, runtime: { require_auth: true } };
      if (path === "/api/tasks/active") body = { tasks: [] };
      if (path === "/api/tasks/history") body = { tasks: [{ id: taskId, name: "Catalog smoke", type: "catalog", status: "completed", started_at: "2026-10-08T12:00:00Z", failed_items: 4, item_errors: errors }] };
      if (path === "/api/files/detail") {
        const id = url.searchParams.get("file_id");
        body = { file: { id: Number(id), url: `https://example.test/${id}.pdf`, title: `File ${id}`, content_type: "application/pdf", has_markdown: true, bytes: 1 } };
      }
      if (path.endsWith("/markdown")) body = { markdown: { markdown_content: "# Smoke document", markdown_source: "local" } };
      if (path.endsWith("/chunk-sets")) body = { chunk_sets: [] };
      if (path === "/api/collections/run") body = { success: true, task_id: taskId };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });

    await page.goto(`${baseUrl}/tasks`, { waitUntil: "networkidle" });
    await page.getByTestId("button-start-catalog").click();
    await page.getByTestId("text-provider-info").waitFor();
    assert.equal(await page.getByTestId("input-start-index").count(), 0);
    assert.equal(await page.getByText("首个待处理 #", { exact: true }).count(), 0);
    await page.getByTestId("input-scan-count").fill("3");
    await page.getByTestId("button-run-task").click();
    await page.waitForFunction(() => !document.querySelector('[data-testid="input-scan-count"]'));
    const submitted = requests.find(r => r.path === "/api/collections/run" && r.method === "POST");
    assert.equal(submitted.body.scan_start_index, 1);
    assert.equal(submitted.body.scan_count, 3);
    candidateCount = 0;
    await page.getByTestId("button-start-catalog").click();
    await page.getByText("没有需要编目的文件", { exact: true }).waitFor();

    await page.goto(`${baseUrl}/settings`, { waitUntil: "networkidle" });
    await page.getByTestId("tab-system").click();
    const toggle = page.getByTestId("toggle-system-flag-enable_file_deletion");
    await toggle.waitFor();
    assert.equal(await page.getByTestId("toggle-system-flag-require_auth").count(), 0);
    assert.equal(await page.getByTestId("button-save-system").count(), 0);
    const geometry = async () => toggle.evaluate(button => {
      const track = button.firstElementChild;
      const knob = track.firstElementChild;
      const rect = node => { const r = node.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
      return { button: rect(button), track: rect(track), knob: rect(knob), background: getComputedStyle(button).backgroundColor };
    });
    for (const expected of ["false", "true", "false"]) {
      await page.waitForFunction(value => document.querySelector('[data-testid="toggle-system-flag-enable_file_deletion"]')?.getAttribute("aria-checked") === value, expected);
      // Wait for the actual CSS movement, without a fixed delay.
      await page.waitForFunction(value => {
        const button = document.querySelector('[data-testid="toggle-system-flag-enable_file_deletion"]');
        const track = button.firstElementChild.getBoundingClientRect();
        const knob = button.firstElementChild.firstElementChild.getBoundingClientRect();
        const onRight = knob.x + knob.width / 2 > track.x + track.width / 2;
        return onRight === (value === "true") && knob.x >= track.x && knob.x + knob.width <= track.x + track.width && knob.y >= track.y && knob.y + knob.height <= track.y + track.height;
      }, expected);
      const g = await geometry();
      assert.ok(g.button.width >= 44 && g.button.height >= 44);
      assert.ok(g.track.width > g.track.height, JSON.stringify(g));
      assert.equal(g.background, "rgba(0, 0, 0, 0)");
      assert.equal(await toggle.getAttribute("role"), "switch");
      await toggle.focus();
      await page.keyboard.press(expected === "true" ? "Enter" : "Space");
    }
    assert.equal(await page.getByTestId("button-save-system").count(), 1);
    assert.equal(requests.some(r => r.path === "/api/config/backend-settings" && r.method !== "GET"), false);

    for (const [digest, id] of examples) {
      await page.goto(`${baseUrl}/tasks`, { waitUntil: "networkidle" });
      await page.getByTestId("button-view-log-0").click();
      const details = page.getByTestId("task-item-errors");
      await details.waitFor();
      assert.equal(await details.getByText("File unmatched", { exact: true }).evaluate(node => node.closest("a") === null), true);
      const link = details.getByRole("link", { name: `File ${digest}`, exact: true });
      assert.equal(await link.getAttribute("href"), `/file-detail?file_id=${id}`);
      await link.click();
      await page.getByTestId("text-file-title").waitFor();
      assert.equal(await page.getByTestId("text-file-title").textContent(), `File ${id}`);
      await page.reload({ waitUntil: "networkidle" });
      assert.equal(await page.getByTestId("text-file-title").textContent(), `File ${id}`);
      assert.ok(requests.some(r => r.path === "/api/files/detail" && r.search === `?file_id=${id}`));
      assert.ok(requests.some(r => r.path.endsWith("/markdown") && r.path.includes(encodeURIComponent(`https://example.test/${id}.pdf`))));
    }
    console.log(`PASS viewport=${width}: Catalog default/empty, capsule states/keyboard/lock/pending save, three file detail links/reload`);
    await page.close();
  }
} finally {
  await browser.close();
}

import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const evidenceDir = process.env.SMOKE_EVIDENCE_DIR || "reports/issue-460/browser";
const executablePath = process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const routes = ["/", "/database", "/file-detail?file_id=1", "/chat"];
const locales = ["en", "zh"];
const themes = ["light", "dark"];
const viewports = [{ name: "desktop", width: 1280, height: 900 }, { name: "mobile390", width: 390, height: 844 }];
const smoke = { matrix: [], capabilities: [], lazyLoad: [], faults: [], api: [], generationCalls: 0, axeViolations: [] };

await mkdir(evidenceDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
try {
  for (const viewport of viewports) {
    for (const route of routes) {
      for (const lang of locales) {
        for (const theme of themes) {
          const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
          page.on("request", (request) => {
            if (request.method() === "POST" && /\/api\/(chat\/query|assistant\/)/.test(new URL(request.url()).pathname)) smoke.generationCalls += 1;
          });
          await page.addInitScript(({ nextLang, nextTheme }) => {
            localStorage.setItem("lang", nextLang);
            localStorage.setItem("theme", nextTheme);
          }, { nextLang: lang, nextTheme: theme });
          const capabilityResponsePromise = page.waitForResponse((response) => response.url().includes("/api/support/capabilities"));
          await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });
          const capabilityResponse = await capabilityResponsePromise;
          assert.equal(capabilityResponse.status(), 200);
          const capabilities = await capabilityResponse.json();
          assert.deepEqual(capabilities, { feedback_enabled: true, assistant_enabled: false });
          smoke.capabilities.push({ route, viewport: viewport.name, lang, theme, ...capabilities });
          const trigger = page.getByTestId("support-widget-trigger");
          await trigger.waitFor({ state: "visible", timeout: 15000 });
          assert.equal(await trigger.getAttribute("aria-label"), lang === "zh" ? "打开帮助与反馈" : "Open help and feedback");
          await page.waitForFunction((expected) => document.documentElement.lang === expected, lang);
          assert.equal(await page.locator("html").evaluate((el) => el.classList.contains("dark")), theme === "dark");
          await trigger.click();
          const panel = page.locator("#feedback-panel");
          await panel.waitFor({ state: "visible" });
          const textarea = page.getByLabel(lang === "zh" ? "反馈内容" : "Your feedback");
          await textarea.waitFor({ state: "visible" });
          await page.waitForFunction((id) => document.activeElement?.id === id, "feedback-content");
          assert.equal(await textarea.evaluate((el) => document.activeElement === el), true);
          const panelBox = await panel.boundingBox();
          assert.ok(panelBox && panelBox.width <= 360 && panelBox.x >= 0 && panelBox.y >= 0 && panelBox.x + panelBox.width <= viewport.width && panelBox.y + panelBox.height <= viewport.height, JSON.stringify(panelBox));
          assert.equal(await page.getByLabel(lang === "zh" ? "建议类型" : "Suggestion type").count(), 1);
          assert.equal(await page.getByText(route.startsWith("/file-detail") ? "/file-detail" : route.split("?")[0], { exact: false }).count() > 0, true);
          let askAgentUncovered = null;
          let mainScrollAvailable = null;
          if (route === "/" && viewport.width >= 1280) {
            const askAgent = page.getByText(lang === "zh" ? "询问 Agent" : "Ask Agent", { exact: true }).locator("xpath=ancestor::a[1]");
            const askBox = await askAgent.boundingBox();
            assert.ok(askBox, "Ask Agent link should be visible on the homepage");
            askAgentUncovered = !(askBox.x < panelBox.x + panelBox.width && askBox.x + askBox.width > panelBox.x && askBox.y < panelBox.y + panelBox.height && askBox.y + askBox.height > panelBox.y);
            assert.equal(askAgentUncovered, true, `Ask Agent card is covered: ${JSON.stringify({ askBox, panelBox })}`);
          }
          if (route === "/" && viewport.name === "mobile390") {
            const main = page.locator("main");
            const sizes = await main.evaluate((el) => ({ height: el.clientHeight, scrollHeight: el.scrollHeight, before: el.scrollTop }));
            assert.ok(sizes.scrollHeight > sizes.height, `homepage should have a scrollable main area: ${JSON.stringify(sizes)}`);
            await main.evaluate((el) => { el.scrollTop = Math.min(240, el.scrollHeight - el.clientHeight); });
            await page.waitForFunction(() => document.querySelector("main").scrollTop > 0);
            const scrolledPanel = await panel.boundingBox();
            assert.ok(scrolledPanel && scrolledPanel.x >= 0 && scrolledPanel.y >= 0 && scrolledPanel.x + scrolledPanel.width <= viewport.width && scrolledPanel.y + scrolledPanel.height <= viewport.height);
            mainScrollAvailable = true;
          }

          const triggerBox = await trigger.boundingBox();
          assert.ok(triggerBox && triggerBox.width >= 44 && triggerBox.height >= 44, JSON.stringify(triggerBox));
          const targets = await panel.locator("button, select, textarea").evaluateAll((elements) => elements.map((element) => {
            const rect = element.getBoundingClientRect();
            return { tag: element.tagName.toLowerCase(), width: rect.width, height: rect.height };
          }));
          assert.equal(targets.length, 4);
          assert.ok(targets.every((target) => target.width >= 44 && target.height >= 44), JSON.stringify(targets));
          if (route === "/" && lang === "en" && theme === "light") {
            await page.screenshot({ path: path.join(evidenceDir, `${viewport.name}-home-en-light.png`), fullPage: false });
          }

          await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
          const axe = await page.evaluate(async () => {
            const result = await window.axe.run(document.querySelector("#feedback-panel"));
            return result.violations.map(({ id, impact, description, nodes }) => ({ id, impact, description, count: nodes.length }));
          });
          smoke.axeViolations.push(...axe.map((item) => ({ ...item, viewport: viewport.name, route, lang, theme })));
          await page.keyboard.press("Escape");
          await page.waitForFunction(() => !document.querySelector("#feedback-panel"));
          await page.waitForFunction(() => document.activeElement?.getAttribute("data-testid") === "support-widget-trigger");

          await page.getByTestId("toggle-lang").click();
          const toggledLang = lang === "zh" ? "en" : "zh";
          await page.waitForFunction((expected) => document.documentElement.lang === expected, toggledLang);
          await page.getByTestId("toggle-theme").click();
          assert.equal(await page.locator("html").evaluate((el) => el.classList.contains("dark")), theme !== "dark");
          smoke.matrix.push({ route, viewport: viewport.name, size: `${viewport.width}x${viewport.height}`, lang, theme, opened: true, closedByEscape: true, focusEntered: true, focusRestored: true, labels: true, triggerTarget44px: true, allPanelTargets44px: true, panelWithinViewport: true, askAgentUncovered, mainScrollAvailable, languageToggle: true, themeToggle: true });
          await page.close();
        }
      }
    }
  }

  const disabled = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await disabled.route("**/api/support/capabilities", (route) => route.fulfill({ json: { feedback_enabled: false, assistant_enabled: false } }));
  let disabledPosts = 0;
  disabled.on("request", (request) => { if (request.method() === "POST" && request.url().includes("/api/feedback")) disabledPosts += 1; });
  let disabledModules = 0;
  disabled.on("request", (request) => { if (/feedbackform|features\/feedback/i.test(request.url())) disabledModules += 1; });
  await disabled.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await disabled.waitForTimeout(250);
  assert.equal(await disabled.getByTestId("support-widget-trigger").count(), 0);
  assert.equal(disabledPosts, 0);
  assert.equal(disabledModules, 0);
  smoke.lazyLoad.push({ state: "feedback disabled", moduleRequests: disabledModules, feedbackPosts: disabledPosts });
  smoke.faults.push({ name: "feedback disabled / assistant disabled", widgetHidden: true, feedbackPosts: disabledPosts });
  await disabled.close();

  const failedCapabilities = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await failedCapabilities.route("**/api/support/capabilities", (route) => route.abort("failed"));
  let failedCapabilitiesModules = 0;
  failedCapabilities.on("request", (request) => { if (/feedbackform|features\/feedback/i.test(request.url())) failedCapabilitiesModules += 1; });
  await failedCapabilities.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await failedCapabilities.waitForTimeout(250);
  assert.equal(await failedCapabilities.getByTestId("support-widget-trigger").count(), 0);
  assert.equal(failedCapabilitiesModules, 0);
  smoke.lazyLoad.push({ state: "capabilities failed", moduleRequests: failedCapabilitiesModules });
  smoke.faults.push({ name: "capabilities network failure", widgetHidden: true });
  await failedCapabilities.close();

  const submission = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await submission.addInitScript(() => { localStorage.setItem("lang", "zh"); localStorage.setItem("theme", "light"); });
  submission.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/(chat\/query|assistant\/)/.test(new URL(request.url()).pathname)) smoke.generationCalls += 1;
  });
  await submission.goto(`${baseUrl}/database?private=synthetic`, { waitUntil: "domcontentloaded" });
  await submission.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await submission.getByTestId("support-widget-trigger").click();
  const textArea = submission.getByLabel("反馈内容");
  const synthetic = `Issue460 isolated browser acceptance ${crypto.randomUUID()}`;
  await textArea.fill(synthetic);
  let interceptedCount = 0;
  let lostResponseReceipt = null;
  const injectedFailures = new Map([
    ["network", async (route) => {
      const committed = await route.fetch();
      assert.equal(committed.status(), 201);
      lostResponseReceipt = await committed.json();
      await route.abort("failed");
    }],
    ["500", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { code: "FEEDBACK_UNAVAILABLE", message: "test injection" } }) })],
    ["429", (route) => route.fulfill({ status: 429, headers: { "Retry-After": "1" }, contentType: "application/json", body: JSON.stringify({ error: { code: "RATE_LIMITED", message: "test injection" } }) })],
  ]);
  for (const [name, fail] of injectedFailures) {
    await textArea.fill(`${synthetic} ${name}`);
    const priorCount = interceptedCount;
    await submission.route("**/api/feedback", async (route) => {
      interceptedCount += 1;
      if (interceptedCount === priorCount + 1) await fail(route);
      else await route.continue();
    });
    const outgoing = [];
    const onRequest = (request) => { if (request.method() === "POST" && request.url().includes("/api/feedback")) outgoing.push(request.postDataJSON()); };
    submission.on("request", onRequest);
    await submission.getByRole("button", { name: "提交反馈" }).click();
    await submission.getByRole("alert").waitFor({ state: "visible" });
    assert.equal(await textArea.inputValue(), `${synthetic} ${name}`);
    const firstId = outgoing.at(-1).client_request_id;
    await submission.unroute("**/api/feedback");
    const success = submission.waitForResponse((response) => response.url().includes("/api/feedback") && response.request().method() === "POST");
    await submission.getByRole("button", { name: "提交反馈" }).click();
    const response = await success;
    assert.equal(response.status(), 201);
    const receipt = await response.json();
    await submission.getByRole("status").waitFor({ state: "visible" });
    assert.ok((await submission.getByRole("status").innerText()).includes(receipt.feedback_id));
    const retryId = response.request().postDataJSON().client_request_id;
    assert.equal(response.request().postDataJSON().page_path, "/database");
    assert.equal(response.request().postDataJSON().content, `${synthetic} ${name}`);
    assert.equal(retryId, firstId);
    if (name === "network") assert.equal(receipt.feedback_id, lostResponseReceipt.feedback_id);
    smoke.api.push({ failure: name, request_id: firstId, retry_request_id: retryId, content: `${synthetic} ${name}`, status: response.status(), feedback_id: receipt.feedback_id, committed_before_response_drop: name === "network" ? lostResponseReceipt.feedback_id : null, text_retained: true, same_id_retry: true, same_receipt_replay: name !== "network" || receipt.feedback_id === lostResponseReceipt.feedback_id });
    smoke.faults.push({ name: `injected ${name} failure then real retry`, firstAttemptNoClientReceipt: true, committedBeforeResponseDrop: name === "network", textRetained: true, retrySucceeded: true });
    submission.off("request", onRequest);
    await textArea.fill(`${synthetic} ${name} edited`);
    const editedResponseWait = submission.waitForResponse((responseItem) => responseItem.url().includes("/api/feedback") && responseItem.request().method() === "POST");
    await submission.getByRole("button", { name: "提交反馈" }).click();
    const editedResponse = await editedResponseWait;
    assert.equal(editedResponse.status(), 201);
    const editedReceipt = await editedResponse.json();
    const editedId = editedResponse.request().postDataJSON().client_request_id;
    smoke.api.push({ failure: `${name}-edited-payload`, retry_request_id: editedId, content: `${synthetic} ${name} edited`, feedback_id: editedReceipt.feedback_id, status: editedResponse.status(), editedPayloadNewId: editedId !== firstId });
  }

  const doubleClickText = `${synthetic} double click`;
  await textArea.fill(doubleClickText);
  let doubleClickRequests = 0;
  await submission.route("**/api/feedback", async (route) => { doubleClickRequests += 1; await new Promise((resolve) => setTimeout(resolve, 400)); await route.continue(); });
  const doubleClickResponse = submission.waitForResponse((response) => response.url().includes("/api/feedback") && response.request().method() === "POST");
  await submission.getByRole("button", { name: "提交反馈" }).dblclick();
  const finalResponse = await doubleClickResponse;
  await submission.waitForTimeout(150);
  assert.equal(finalResponse.status(), 201);
  assert.equal(doubleClickRequests, 1);
  const finalReceipt = await finalResponse.json();
  await submission.unroute("**/api/feedback");
  smoke.api.push({ failure: "double click", status: finalResponse.status(), feedback_id: finalReceipt.feedback_id, request_id: finalResponse.request().postDataJSON().client_request_id, content: doubleClickText, interceptedWrites: doubleClickRequests });
  smoke.faults.push({ name: "double click while pending", browserRequests: doubleClickRequests, apiStatus: finalResponse.status() });

  smoke.axeViolations = smoke.axeViolations.slice(0, 100);
  assert.equal(smoke.matrix.length, 32);
  assert.equal(smoke.axeViolations.length, 0, JSON.stringify(smoke.axeViolations.slice(0, 4)));
  const resultPath = process.env.SMOKE_RESULT_PATH || path.join(evidenceDir, "issue460-browser-smoke.json");
  await writeFile(resultPath, `${JSON.stringify(smoke, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ matrix: smoke.matrix.length, axeViolations: smoke.axeViolations.length, faults: smoke.faults.length, apiReceipts: smoke.api.length, generationCalls: smoke.generationCalls, evidence: resultPath }));
  await submission.close();
} finally {
  await browser.close();
}

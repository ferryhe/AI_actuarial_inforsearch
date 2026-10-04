import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const kb = { kb_id: "kb-smoke", name: "Smoke KB", availability: "ready", usable: true, serving: true };

async function fixtureApi(route, requests) {
  const url = new URL(route.request().url());
  const { pathname, searchParams } = url;
  const method = route.request().method();
  requests.push({ method, path: `${pathname}${url.search}` });
  if (pathname === "/api/auth/me") return route.fulfill({ json: { data: { require_auth: true, authenticated: true, user: { id: 1, email: "smoke@example.test", role: "registered" }, permissions: ["chat.conversations"] } } });
  if (pathname === "/api/chat/conversations" && method === "GET") return route.fulfill({ json: { success: true, data: { conversations: [] } } });
  if (pathname === "/api/chat/conversations" && method === "POST") {
    assert.equal(route.request().postDataJSON().mode, "expert");
    return route.fulfill({ json: { success: true, data: { conversation_id: "conv-smoke" } } });
  }
  if (pathname === "/api/chat/knowledge-bases") return route.fulfill({ json: { success: true, data: { knowledge_bases: [kb] } } });
  if (pathname === "/api/categories") return route.fulfill({ json: { categories: ["Reserving"] } });
  if (pathname === "/api/chat/available-documents") {
    assert.ok([null, "reserve"].includes(searchParams.get("query")));
    return route.fulfill({ json: { success: true, data: { items: [{ file_url: "smoke-file", filename: "smoke.pdf", title: "Reserve evidence", category: "Reserving", keywords: ["reserve"] }], total: 1, offset: 0, limit: 50 } } });
  }
  if (pathname === "/api/chat/query") {
    const body = route.request().postDataJSON();
    assert.equal(body.message, "Reply with a brief smoke-test acknowledgement.");
    assert.deepEqual(body.kb_ids, ["kb-smoke"]);
    return route.fulfill({ json: { success: true, data: { conversation_id: "conv-smoke", response: "Smoke-test acknowledgement.", citations: [] } } });
  }
  throw new Error(`Unexpected API request: ${method} ${pathname}`);
}
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  headless: true,
});

try {
  const results = [];
  for (const width of [320, 360, 390, 414]) {
    const requests = [];
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    await page.route("**/api/**", (route) => fixtureApi(route, requests));
    await page.goto(`${baseUrl}/chat`, { waitUntil: "networkidle" });
    const priorBodyOverflow = await page.locator("body").evaluate((node) => node.style.overflow);
    const open = page.getByTestId("button-open-chat-sidebar");
    await open.waitFor();
    const openBox = await open.boundingBox();
    assert.ok(openBox && openBox.width >= 44 && openBox.height >= 44, `${width}: ${JSON.stringify(openBox)}`);
    assert.equal(await open.getAttribute("aria-label"), "Open chat sidebar");
    await open.click();
    const close = page.getByTestId("button-close-chat-sidebar");
    await close.waitFor();
    const closeBox = await close.boundingBox();
    assert.ok(closeBox && closeBox.width >= 44 && closeBox.height >= 44, `${width}: ${JSON.stringify(closeBox)}`);
    assert.equal(await close.getAttribute("aria-label"), "Close chat sidebar");
    await page.getByTestId("chat-sidebar-backdrop").waitFor();
    assert.equal(await page.getByTestId("chat-sidebar-backdrop").evaluate((node) => getComputedStyle(node).position), "fixed");
    assert.equal(await page.locator("body").evaluate((node) => getComputedStyle(node).overflow), "hidden");
    const scrollTop = await page.evaluate(() => {
      const target = document.scrollingElement;
      return target && target.scrollHeight > target.clientHeight ? target.scrollTop : null;
    });
    if (scrollTop !== null) {
      await page.getByTestId("chat-sidebar-backdrop").hover();
      await page.mouse.wheel(0, 400);
      assert.equal(await page.evaluate(() => document.scrollingElement?.scrollTop), scrollTop);
    }
    await page.getByTestId("button-new-conversation").click();
    await page.getByTestId("conversation-conv-smoke").waitFor();
    await page.getByTestId("button-toggle-documents-panel").click();
    await page.getByTestId("input-doc-search").fill("reserve");
    await page.getByTestId("button-doc-search").click();
    await page.getByText("Reserve evidence").waitFor();
    await page.getByTestId("kb-sidebar-option-kb-smoke").click();
    assert.match(await page.getByTestId("kb-sidebar-option-kb-smoke").getAttribute("class"), /bg-primary/);
    await page.keyboard.press("Escape");
    await open.waitFor();
    await page.waitForFunction(() => document.activeElement?.getAttribute("data-testid") === "button-open-chat-sidebar");
    assert.equal(await page.locator("body").evaluate((node) => node.style.overflow), priorBodyOverflow);

    for (const zoom of ["100%", "200%"]) {
      await page.evaluate((fontSize) => { document.documentElement.style.fontSize = fontSize; }, zoom);
      const measurements = await page.evaluate(() => {
        const ids = ["input-chat-message", "button-send-message", "button-mode-selector", "button-kb-selector"];
        const controls = Object.fromEntries(ids.map((id) => {
          const box = document.querySelector(`[data-testid="${id}"]`)?.getBoundingClientRect();
          return [id, box && { left: box.left, right: box.right, width: box.width, height: box.height }];
        }));
        return { scrollWidth: document.documentElement.scrollWidth, viewport: innerWidth, controls };
      });
      assert.ok(measurements.scrollWidth <= measurements.viewport, `${width}/${zoom}: ${JSON.stringify(measurements)}`);
      for (const [id, box] of Object.entries(measurements.controls)) {
        assert.ok(box && box.width > 0 && box.left >= 0 && box.right <= width, `${width}/${zoom} ${id}: ${JSON.stringify(box)}`);
      }
      results.push({ width, zoom, ...measurements });
    }
    assert.ok(requests.some((request) => request.path === "/api/chat/available-documents?limit=50&offset=0&query=reserve"));
    await page.close();
  }
  const requests = [];
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route("**/api/**", (route) => fixtureApi(route, requests));
  await page.goto(`${baseUrl}/chat`, { waitUntil: "networkidle" });
  await page.getByTestId("button-open-chat-sidebar").click();
  await page.getByTestId("kb-sidebar-option-kb-smoke").click();
  await page.keyboard.press("Escape");
  await page.getByTestId("input-chat-message").fill("Reply with a brief smoke-test acknowledgement.");
  const [response] = await Promise.all([
    page.waitForResponse((candidate) => candidate.url().includes("/api/chat/query") && candidate.request().method() === "POST"),
    page.getByTestId("button-send-message").click(),
  ]);
  assert.equal(response.ok(), true, `send request failed: ${response.status()}`);
  const replyBox = await page.getByText("Smoke-test acknowledgement.", { exact: true }).boundingBox();
  assert.ok(replyBox && replyBox.width > 0, `invisible assistant reply: ${JSON.stringify(replyBox)}`);
  assert.ok(requests.some((request) => request.path === "/api/chat/query"));
  console.log(JSON.stringify({ chromium: "pass", backend: "fixtures only; real Chat UI and frontend API client", viewports: results, send: { status: response.status(), replyWidth: replyBox.width } }));
  await page.close();
} finally {
  await browser.close();
}

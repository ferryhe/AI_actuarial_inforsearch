import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
try {
  for (const language of ["en", "zh"]) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, timezoneId: "America/New_York" });
    const page = await context.newPage();
    const requests = [];
    const rows = [
      { id: 1, subject: "Ordinary admin", group_name: "admin", token_type: "standard", status: "active", is_active: true, revoked_at: null, created_at: "2026-01-01T12:00:00+00:00", expires_at: "2030-01-01T12:00:00+00:00", last_used_at: "2026-01-02T12:00:00+00:00" },
      { id: 2, subject: "Automation", group_name: "admin", token_type: "service", status: "revoked", is_active: false, revoked_at: "2026-01-03T12:00:00+00:00", created_at: "2026-01-01T12:00:00+00:00", expires_at: null, last_used_at: null },
      { id: 3, subject: "Expired worker", group_name: "operator", token_type: "standard", status: "expired", is_active: true, revoked_at: null, created_at: "2026-01-01T12:00:00+00:00", expires_at: "2026-01-03T12:00:00+00:00", last_used_at: null },
    ];
    await page.addInitScript(lang => localStorage.setItem("lang", lang), language);
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      let body = {};
      if (path === "/api/auth/me") body = { data: { authenticated: true, require_auth: true, user: { id: 1, email: "admin@example.test", display_name: "Admin", role: "admin", is_active: true }, permissions: ["tokens.manage", "config.read", "config.write"] } };
      if (path === "/api/auth/tokens") {
        if (route.request().method() === "POST") {
          requests.push(route.request().postDataJSON());
          body = { success: true, token: "one-time-secret", metadata: rows[0] };
        } else body = { success: true, tokens: rows };
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto(baseUrl + "/settings", { waitUntil: "networkidle" });
    await page.getByTestId("tab-tokens").click();
    await page.getByTestId("token-row-1").waitFor();
    const text = await page.getByTestId("token-row-1").textContent();
    assert.match(text, /Ordinary admin/);
    assert.match(text, /admin/);
    const renderedDate = await page.getByTestId("token-row-1").locator("time").first().textContent();
    assert.equal(renderedDate, await page.evaluate(() => new Date("2026-01-01T12:00:00Z").toLocaleString()));
    assert.equal(await page.getByTestId("token-row-1").locator("time").first().getAttribute("title"), "2026-01-01T12:00:00.000Z (UTC)");
    assert.match(await page.getByTestId("token-row-2").textContent(), language === "en" ? /Service.*Revoked.*No expiry/ : /服务.*已撤销.*永不过期/);
    assert.match(await page.getByTestId("token-row-3").textContent(), language === "en" ? /Expired/ : /已过期/);
    await page.getByTestId("button-create-token").click();
    await page.getByTestId("input-token-subject").fill("Smoke");
    assert.deepEqual(await page.getByTestId("select-token-group").locator("option").evaluateAll(opts => opts.map(o => o.value)), ["registered", "premium", "operator", "admin"]);
    await page.getByTestId("select-token-group").selectOption("admin");
    assert.equal(await page.getByTestId("select-token-expiry").inputValue(), "7");
    for (const days of ["1", "7", "30"]) {
      await page.getByTestId("select-token-expiry").selectOption(days);
      const pending = page.waitForResponse(r => r.url().endsWith("/api/auth/tokens") && r.request().method() === "POST");
      await page.getByTestId("button-submit-token").click();
      await pending;
      await page.getByTestId("text-created-token").waitFor();
      assert.equal(requests.at(-1).group_name, "admin");
      assert.equal(requests.at(-1).token_type, "standard");
      assert.equal(Math.round((Date.parse(requests.at(-1).expires_at) - Date.now()) / 86400000), Number(days));
    }
    await page.getByTestId("select-token-expiry").selectOption("custom");
    assert.equal(await page.getByTestId("button-submit-token").isDisabled(), true);
    await page.getByTestId("input-token-expiry").fill("2030-01-01T12:00");
    await page.getByTestId("button-submit-token").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="button-submit-token"]')?.disabled === false);
    assert.equal(requests.at(-1).expires_at, "2030-01-01T17:00:00.000Z");
    await page.getByTestId("select-token-type").selectOption("service");
    await page.getByTestId("token-service-warning").waitFor();
    assert.equal(await page.getByTestId("button-submit-token").isDisabled(), true);
    await page.getByTestId("confirm-service-token").check();
    await page.getByTestId("button-submit-token").click();
    await page.waitForFunction(() => document.querySelector('[data-testid="button-submit-token"]')?.disabled === false);
    assert.deepEqual(requests.at(-1), { subject: "Smoke", group_name: "admin", token_type: "service", expires_at: null, confirm_service: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    assert.equal(overflow, false, "Settings token form overflows mobile screen");
    await context.close();
  }
  console.log("Issue #359 Settings Chromium smoke passed (English/Chinese, New York local time, mobile).");
} finally { await browser.close(); }

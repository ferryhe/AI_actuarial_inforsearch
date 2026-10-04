import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5184";
const release = "fixture-browser-release";
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
try {
  for (const lang of ["en", "zh"]) {
    const context = await browser.newContext();
    const page = await context.newPage();
    let backendRelease = "fixture-other-release";
    await page.addInitScript(value => localStorage.setItem("lang", value), lang);
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      const body = path === "/api/auth/me" ? { data: { authenticated: true, user: { id: 1, role: "admin", email: "fixture@example.test" }, permissions: ["config.read", "config.write", "logs.system.read"] } }
        : path === "/api/health" ? { status: "ok", build_info: { release_manifest_id: backendRelease, git_sha: "aaaaaaa" } } : {};
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto(baseUrl + "/settings", { waitUntil: "networkidle" });
    assert.equal(await page.getByTestId("frontend-release").textContent(), release);
    const alert = page.getByTestId("build-info").getByRole("alert");
    await alert.waitFor();
    assert.match(await alert.textContent(), lang === "en" ? /releases differ/ : /版本不一致/);
    assert.equal(await page.getByTestId("tab-system").isEnabled(), true);
    // A local canary fixture switches the API identity; rollback returns to the built frontend ID.
    backendRelease = release;
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.getByTestId("api-release").textContent(), release);
    assert.equal(await page.getByTestId("build-info").getByRole("alert").count(), 0);
    assert.match(await page.getByTestId("build-info").textContent(), lang === "en" ? /releases match/ : /版本一致/);
    await context.close();
  }
  console.log("Build provenance browser smoke passed: English/Chinese mismatch and rollback identity.");
} finally { await browser.close(); }

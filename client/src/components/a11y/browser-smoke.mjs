import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  headless: true,
});

try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(process.env.SMOKE_URL || "http://127.0.0.1:5173/", { waitUntil: "networkidle" });

  await page.locator("body").click({ position: { x: 380, y: 830 } });
  await page.keyboard.press("Tab");
  const open = page.getByRole("button", { name: "Open navigation" });
  assert.equal(await open.evaluate((button) => document.activeElement === button), true);
  assert.equal(await open.evaluate((button) => getComputedStyle(button).boxShadow !== "none"), true);
  const openBox = await open.boundingBox();
  assert.ok(openBox && openBox.width >= 44 && openBox.height >= 44, JSON.stringify(openBox));

  await page.keyboard.press("Enter");
  const close = page.getByRole("button", { name: "Close navigation" });
  await close.waitFor({ state: "visible" });
  const closeBox = await close.boundingBox();
  assert.ok(closeBox && closeBox.width >= 44 && closeBox.height >= 44, JSON.stringify(closeBox));
  const testIds = await page.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(testIds).size, testIds.length);

  await close.evaluate((button) => button.focus());
  await page.keyboard.press("Space");
  await close.waitFor({ state: "detached" });
  await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Open navigation");
  assert.equal(await open.evaluate((button) => document.activeElement === button), true);

  await page.evaluate(() => localStorage.setItem("lang", "zh"));
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await page.getByRole("button", { name: "打开导航" }).count(), 1);

  console.log(JSON.stringify({ chromium: "pass", viewport: "390x844", keyboard: ["Tab", "Enter", "Space"], focusRecovery: true, duplicateTestIds: false, locales: ["en", "zh"] }));
} finally {
  await browser.close();
}

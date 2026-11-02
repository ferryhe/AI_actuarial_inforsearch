import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const base = process.env.SMOKE_URL || "http://127.0.0.1:5185";
const portals = Array.from({ length: 21 }, (_, index) => {
  const number = index + 1;
  return {
    portal_key: `source-${number}`,
    url: `https://example.org/research/source-${number}`,
    title_zh: `研究入口 ${number}`,
    title_en: `Research Topic ${number}`,
    institution_zh: number === 21 ? "特别机构" : `机构 ${number}`,
    institution_en: number === 21 ? "Special Target Institution" : `Institution ${number}`,
    overview_zh: `第 ${number} 个资料入口的简短介绍。`,
    overview_en: `Brief overview for source ${number}.`,
    updates: number === 20 ? [] : [{
      acquired_on: "2026-11-01",
      description_zh: `动态全文 ${number}，详情页才会显示。`,
      description_en: `Full update prose for source ${number}, shown only on its detail page.`,
    }],
  };
});

try {
  for (const language of ["en", "zh"]) {
    for (const viewport of [{ width: 1280, height: 800 }, { width: 375, height: 812 }]) {
      const page = await browser.newPage({ viewport });
      await page.addInitScript((value) => localStorage.setItem("lang", value), language);
      await page.route("**/api/**", (route) => {
        const { pathname } = new URL(route.request().url());
        const body = pathname === "/api/auth/me"
          ? { data: { require_auth: false, authenticated: true, user: { id: 1, role: "admin", is_active: true }, permissions: ["files.read"] } }
          : pathname === "/api/source-portals" ? { portals } : {};
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
      });

      await page.goto(`${base}/source-portals`);
      await page.getByTestId("source-portals-title").waitFor();
      await page.getByTestId("source-portals-list").waitFor();
      assert.equal(await page.getByTestId("source-portal-row").count(), 20);
      if (viewport.width >= 640) {
        assert.equal(await page.getByRole("columnheader").count(), 4);
      }
      assert.equal(await page.getByText(language === "zh" ? "动态全文 1，详情页才会显示。" : "Full update prose for source 1, shown only on its detail page.").count(), 0);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      if (viewport.width === 375) {
        const row = page.getByTestId("source-portal-row").nth(19);
        const cells = row.locator(":scope > [role='cell']");
        const [rowBox, titleBox, overviewBox, statusBox] = await Promise.all([
          row.boundingBox(),
          cells.nth(0).boundingBox(),
          cells.nth(2).boundingBox(),
          cells.nth(3).boundingBox(),
        ]);
        assert.ok(rowBox && titleBox && overviewBox && statusBox);
        assert.ok(titleBox.width >= rowBox.width * 0.85);
        assert.ok(statusBox.width >= rowBox.width * 0.85);
        assert.ok(titleBox.y < overviewBox.y && overviewBox.y < statusBox.y);
        assert.equal((await cells.nth(3).innerText()).trim(), language === "zh" ? "暂无动态" : "No updates yet");
      }

      await page.getByTestId("source-portals-pagination-next").click();
      await page.waitForURL(/\/source-portals\?page=2$/);
      await page.getByTestId("source-portal-row").first().waitFor({ state: "visible" });
      assert.equal(await page.getByTestId("source-portal-row").count(), 1);
      const targetTitle = language === "zh" ? "研究入口 21" : "Research Topic 21";
      await page.getByRole("link", { name: targetTitle }).focus();
      await page.keyboard.press("Enter");
      await page.getByTestId("source-portal-detail-title").waitFor();
      await page.waitForURL(/\/source-portals\/source-21\?page=2$/);
      assert.equal(await page.getByTestId("source-portal-original-link").getAttribute("href"), portals[20].url);
      assert.equal(await page.getByText(language === "zh" ? "动态全文 21，详情页才会显示。" : "Full update prose for source 21, shown only on its detail page.").count(), 1);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.getByTestId("source-portal-back").click();
      await page.waitForURL(/\/source-portals\?page=2$/);
      await page.getByRole("link", { name: targetTitle }).waitFor({ state: "visible" });

      const search = page.getByTestId("input-source-portal-search");
      await search.fill("Special Target Institution");
      await page.waitForURL(/\/source-portals\?query=Special\+Target\+Institution$/);
      await page.getByRole("link", { name: targetTitle }).waitFor({ state: "visible" });
      assert.equal(await page.getByTestId("source-portal-row").count(), 1);
      await page.getByRole("link", { name: targetTitle }).click();
      await page.waitForURL(/\/source-portals\/source-21\?query=Special\+Target\+Institution$/);
      await page.getByTestId("source-portal-back").click();
      await page.waitForURL(/\/source-portals\?query=Special\+Target\+Institution$/);
      await page.getByRole("link", { name: targetTitle }).waitFor({ state: "visible" });

      await page.goto(`${base}/source-portals/source-20`);
      await page.getByTestId("source-portal-detail-title").waitFor();
      await page.getByTestId("source-portal-no-updates").waitFor();
      await page.goto(`${base}/source-portals/unknown-entry`);
      await page.getByTestId("source-portal-not-found").waitFor();
      await page.getByTestId("source-portal-back").click();
      await page.waitForURL(`${base}/source-portals`);
      await page.close();
    }
  }
  console.log("Source portal list/detail smoke passed in English and Chinese at desktop and mobile widths.");
} finally {
  await browser.close();
}

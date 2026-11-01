import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const base = process.env.SMOKE_URL || "http://127.0.0.1:5185";
const portal = {
  portal_key: "soa-research-topics",
  url: "https://www.soa.org/research/research-topic-list/",
  title_zh: "研究主题目录",
  title_en: "Research Topics",
  institution_zh: "美国精算师协会（SOA）",
  institution_en: "Society of Actuaries (SOA)",
  overview_zh: "汇集 SOA 按研究主题整理的资料入口。",
  overview_en: "SOA's directory of materials organized by research topic.",
  updates: [
    {
      acquired_on: "2026-11-01",
      description_zh: "本次与上次日期相比，目录新增了内容。",
      description_en: "Compared with the previous date, this directory adds material.",
    },
    {
      acquired_on: "2026-10-31",
      description_zh: "首次记录了研究主题目录当前列出的内容。",
      description_en: "This first record covers the research directory.",
    },
  ],
};

try {
  for (const language of ["en", "zh"]) {
    for (const viewport of [{ width: 1280, height: 800 }, { width: 375, height: 812 }]) {
      const page = await browser.newPage({ viewport });
      await page.addInitScript((value) => localStorage.setItem("lang", value), language);
      await page.route("**/api/**", (route) => {
        const { pathname } = new URL(route.request().url());
        const body = pathname === "/api/auth/me"
          ? { data: { require_auth: false, authenticated: true, user: { id: 1, role: "admin", is_active: true }, permissions: ["files.read"] } }
          : pathname === "/api/source-portals" ? { portals: [portal] } : {};
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
      });
      await page.goto(`${base}/source-portals`);
      await page.getByTestId("source-portals-title").waitFor();
      await page.getByText(language === "zh" ? portal.title_zh : portal.title_en, { exact: true }).waitFor();
      await page.getByText(language === "zh" ? portal.updates[0].description_zh : portal.updates[0].description_en, { exact: true }).waitFor();
      assert.equal(await page.locator("[data-testid=source-portals-grid] time").first().getAttribute("datetime"), "2026-11-01");
      assert.equal(await page.locator("[data-testid=source-portals-grid] li").count(), 2);
      assert.equal(await page.getByText(/capture_id|version_id|\bcount\b/i).count(), 0);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.close();
    }
  }
  console.log("Source portal reader smoke passed for English and Chinese at desktop and mobile widths.");
} finally {
  await browser.close();
}

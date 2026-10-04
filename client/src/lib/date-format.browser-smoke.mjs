import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
try {
  for (const zone of ["America/New_York", "Asia/Shanghai"]) {
    const context = await browser.newContext({ timezoneId: zone, locale: "en-US" });
    const page = await context.newPage();
    await page.goto(process.env.SMOKE_URL || "http://127.0.0.1:5173", { waitUntil: "domcontentloaded" });
    const result = await page.evaluate(async (timeZone) => {
      const { formatDateTime, formatUtcIso } = await import("/src/lib/date-format.ts");
      const { formatWeeklyDateTime, formatWeeklyPeriodLabel, formatWeeklyPeriodUtcTitle } = await import("/src/lib/weekly-dashboard.ts");
      const mainSource = await (await fetch("/src/main.tsx")).text();
      const reactUrl = mainSource.match(/from "([^"]*react\.js\?v=[^"]+)"/)?.[1];
      const reactDomUrl = mainSource.match(/from "([^"]*react-dom_client\.js\?v=[^"]+)"/)?.[1];
      if (!reactUrl || !reactDomUrl) throw new Error("Unable to resolve Vite React modules");
      const React = (await import(reactUrl)).default;
      const { createRoot } = (await import(reactDomUrl)).default;
      const { WeeklyHighlightCard } = await import("/src/components/WeeklyHighlightCard.tsx");
      const opts = { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone };
      const preDst = formatDateTime("2026-03-08T06:30:00Z", "en", opts);
      const postDst = formatDateTime("2026-03-08T07:30:00Z", "en", opts);
      const crossDay = formatDateTime("2026-03-08T00:30:00Z", "en", opts);
      const zh = formatDateTime("2026-03-08T07:30:00Z", "zh", opts);
      const cardDate = async (lang, firstSeen) => {
        const rootElement = document.createElement("div");
        document.body.append(rootElement);
        const root = createRoot(rootElement);
        root.render(React.createElement(WeeklyHighlightCard, {
          view: {
            snapshot: null,
            files: [{ url: "https://example.test/article", title: "Article", first_seen: firstSeen }],
            fileCount: 1,
            filesUnavailable: false,
            explanationState: "missing",
            explanationText: "Not generated",
          },
          lang,
          t: (key) => ({
            "dashboard.new_materials_count": "{count} new materials",
            "dashboard.untitled_material": "Untitled material",
            "dashboard.explanation_missing": "Not generated",
          })[key] || key,
          onOpenFile: () => undefined,
        }));
        await new Promise((resolve) => setTimeout(resolve, 20));
        const time = rootElement.querySelector("time");
        const value = time && { text: time.textContent, title: time.getAttribute("title"), dateTime: time.getAttribute("datetime") };
        root.unmount();
        rootElement.remove();
        return value;
      };
      const weeklyEn = await cardDate("en", "2026-09-03T00:30:00Z");
      const weeklyZh = await cardDate("zh", "2026-09-03T00:30:00Z");
      const weeklyInvalid = await cardDate("en", "not-a-date");
      return {
        preDst, postDst, crossDay, zh,
        utc: formatUtcIso("2026-03-08T07:30:00Z"),
        invalid: formatDateTime("bad", "en"),
        weeklyEn, weeklyZh, weeklyInvalid,
        weeklyPeriodDateTime: formatWeeklyDateTime("2026-03-09T00:00:00Z", "en"),
        weeklyPeriodDateEn: formatWeeklyPeriodLabel("2026-03-09T00:00:00Z", "2026-03-16T00:00:00Z", "en"),
        weeklyPeriodDateZh: formatWeeklyPeriodLabel("2026-03-09T00:00:00Z", "2026-03-16T00:00:00Z", "zh"),
        weeklyPeriodUtcTitle: formatWeeklyPeriodUtcTitle("2026-03-09T00:00:00Z", "2026-03-16T00:00:00Z"),
        invalidWeeklyPeriodUtcTitle: formatWeeklyPeriodUtcTitle("not-a-date", "2026-03-16T00:00:00Z"),
      };
    }, zone);
    assert.equal(result.utc, "2026-03-08T07:30:00.000Z");
    assert.equal(result.invalid, "—");
    if (zone === "America/New_York") {
      assert.match(result.preDst, /01:30|1:30/);
      assert.match(result.postDst, /03:30|3:30/);
      assert.match(result.crossDay, /Mar 7/);
    } else {
      assert.match(result.postDst, /15:30|3:30/);
      assert.match(result.crossDay, /Mar 8/);
    }
    assert.match(result.zh, /3月8日/);
    assert.equal(result.weeklyEn?.text, zone === "America/New_York" ? "Sep 2" : "Sep 3");
    assert.equal(result.weeklyZh?.text, zone === "America/New_York" ? "9月2日" : "9月3日");
    for (const weekly of [result.weeklyEn, result.weeklyZh]) {
      assert.equal(weekly?.title, "2026-09-03T00:30:00.000Z (UTC)");
      assert.equal(weekly?.dateTime, "2026-09-03T00:30:00.000Z");
    }
    assert.equal(result.weeklyInvalid?.text, "—");
    assert.equal(result.weeklyInvalid?.title, null);
    assert.equal(result.weeklyInvalid?.dateTime, null);
    if (zone === "America/New_York") {
      assert.match(result.weeklyPeriodDateTime, /Mar 8, 2026, 08:00 PM EDT/);
    } else {
      assert.match(result.weeklyPeriodDateTime, /Mar 9, 2026, 08:00 AM GMT\+8/);
    }
    assert.equal(result.weeklyPeriodDateEn, "Mar 9, 2026 – Mar 16, 2026");
    assert.equal(result.weeklyPeriodDateZh, "2026年3月9日 – 2026年3月16日");
    assert.equal(result.weeklyPeriodUtcTitle, "2026-03-09T00:00:00.000Z – 2026-03-16T00:00:00.000Z (UTC)");
    assert.equal(result.invalidWeeklyPeriodUtcTitle, undefined);
    console.log(`${zone}:`, JSON.stringify(result));
    await context.close();
  }
} finally {
  await browser.close();
}

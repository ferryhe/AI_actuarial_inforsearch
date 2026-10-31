import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { WeeklyDashboardSection } from "../components/WeeklyDashboardSection";
import { WeeklyHighlightCard } from "../components/WeeklyHighlightCard";
import { buildWeeklyDashboardView, loadWeeklyUpdateDetail, type WeeklyDashboardData } from "./weekly-dashboard";

const snapshot = { id: "weekly-current", period_start: "2026-10-19", period_end: "2026-10-26", generated_at: "2026-10-26", status: "published" as const, file_count: 5, metadata: {} };
const files = Array.from({ length: 5 }, (_, i) => ({ url: `https://example.org/${i}`, title: `Study ${i}`, summary: `Source summary ${i}.`, first_seen: "2026-10-20" }));
const base: WeeklyDashboardData = { status: "ready", snapshot, files, filesUnavailable: false, explanation: { snapshot_id: snapshot.id, status: "failed", explanation_zh: "", explanation_en: "", generated_at: null }, explanationUnavailable: false };
const t = (key: string) => ({ "dashboard.explanation_missing": "Not generated", "dashboard.explanation_unavailable": "Unavailable", "dashboard.files_unavailable": "Files unavailable", "dashboard.explanation_failed": "AI guide unavailable" }[key] || key);

test("zero snapshot shows fixed copy in both locales on home and detail", () => {
  for (const lang of ["zh", "en"]) {
    const data = { ...base, snapshot: { ...snapshot, file_count: 0 }, files: [], explanationUnavailable: true };
    const text = lang === "zh" ? "本周暂无新资料。" : "No new material this week.";
    const view = buildWeeklyDashboardView(data, lang, t);
    assert.equal(view.explanationText, text);
    assert.ok(renderToStaticMarkup(<WeeklyDashboardSection data={data} lang={lang} t={t} onOpenFile={() => {}} />).includes(text));
    assert.ok(renderToStaticMarkup(<WeeklyHighlightCard view={view} lang={lang} t={t} onOpenFile={() => {}} grouped />).includes(text));
  }
  assert.equal(buildWeeklyDashboardView({ ...base, status: "no_snapshot", snapshot: null, explanation: null }, "en", t).explanationText, "Not generated");
  assert.equal(buildWeeklyDashboardView({ ...base, explanationUnavailable: true }, "en", t).explanationText, "Unavailable");
});

test("legacy failed rows render current files as clickable fallback and preserve failure state", () => {
  for (const lang of ["zh", "en"]) {
    const view = buildWeeklyDashboardView(base, lang, t);
    assert.equal(view.explanationState, "failed");
    const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang={lang} t={t} onOpenFile={() => {}} />);
    assert.ok(markup.includes("AI guide unavailable"));
    assert.equal((markup.match(/href="https:\/\/example.org\//g) || []).length, 5);
    assert.ok(markup.includes("Source summary 0."));
  }
  assert.equal(buildWeeklyDashboardView({ ...base, filesUnavailable: true }, "en", t).explanationText, "Files unavailable");
  const mismatched = { ...base, explanation: { ...base.explanation!, snapshot_id: "weekly-previous", generation_mode: "fallback" as const, explanation_en: "Previous week" } };
  assert.equal(buildWeeklyDashboardView(mismatched, "en", t).explanationText, "Not generated");
});

test("detail keeps all 1116 members available in three pages and GET never generates", async () => {
  const calls: string[] = [];
  const all = Array.from({ length: 1116 }, (_, i) => ({ ...files[0], url: `https://example.org/${i}` }));
  const data = await loadWeeklyUpdateDetail(snapshot.id, async <T,>(url: string): Promise<T> => {
    calls.push(url);
    if (url.endsWith("/explanation")) return { explanation: base.explanation } as T;
    if (url.includes("/files?")) {
      const offset = Number(new URL(url, "http://fixture").searchParams.get("offset"));
      return { files: all.slice(offset, offset + 500), total: all.length } as T;
    }
    return { summary: { ...snapshot, file_count: all.length } } as T;
  });
  assert.equal(data.files.length, 1116);
  assert.equal(calls.filter(url => url.includes("/files?")).length, 3);
  assert.ok(calls.every(url => !/generate|retry/.test(url)));
});


test("quoted source Markdown cannot add a non-member fallback link", () => {
  const data = { ...base, files: [{ ...files[0], summary: "Source summary [outside](https://outside.example/previous)." }] };
  const view = buildWeeklyDashboardView(data, "en", t);
  const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang="en" t={t} onOpenFile={() => {}} />);
  assert.ok(!markup.includes('href="https://outside.example/previous"'));
  assert.ok(markup.includes('href="https://example.org/0"'));
});

test("legacy fallback does not cut a long summary before its limiting qualification", () => {
  const summary = "This model is safe under the reported conditions. " + "Evidence requires careful interpretation. ".repeat(20) + "It is not approved for general use.";
  const data = { ...base, files: [{ ...files[0], summary }] };
  const view = buildWeeklyDashboardView(data, "en", t);
  assert.ok(view.explanationText.includes("Study 0"));
  assert.ok(view.explanationText.includes(summary));
  assert.ok(view.explanationText.includes("It is not approved for general use."));
});


test("legacy failed guide displays the complete existing 943 character summary", () => {
  const summary = "A real first sentence. " + "Further source detail. ".repeat(40);
  assert.equal(summary.length, 943);
  const view = buildWeeklyDashboardView({ ...base, files: [{ ...files[0], summary }] }, "en", t);
  assert.ok(view.explanationText.includes(summary.trim()));
  assert.ok(view.explanationText.includes("https://example.org/0"));
});

test("legacy failed guide uses title only when the source summary is missing", () => {
  const view = buildWeeklyDashboardView({ ...base, files: [{ ...files[0], summary: null }] }, "en", t);
  assert.ok(view.explanationText.includes("Study 0"));
  assert.ok(!view.explanationText.includes("Source summary"));
});

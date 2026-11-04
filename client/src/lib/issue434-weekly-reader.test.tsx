import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { WeeklyDashboardSection } from "../components/WeeklyDashboardSection";
import { WeeklyHighlightCard } from "../components/WeeklyHighlightCard";
import { buildWeeklyDashboardView, loadLatestWeeklyDashboard, loadWeeklyUpdateDetail, type WeeklyDashboardData } from "./weekly-dashboard";

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

test("failed guides recommend three existing article cards and preserve failure state", () => {
  for (const lang of ["zh", "en"]) {
    const view = buildWeeklyDashboardView(base, lang, t);
    assert.equal(view.explanationState, "failed");
    const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang={lang} t={t} onOpenFile={() => {}} />);
    assert.ok(markup.includes("AI guide unavailable"));
    assert.equal((markup.match(/data-testid="weekly-file-row-/g) || []).length, 5);
    assert.equal((markup.match(/<li>/g) || []).length, 3);
    assert.equal((markup.match(/href="https:\/\/example.org\//g) || []).length, 0);
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
  assert.ok(markup.includes('data-testid="weekly-file-row-0"'));
});

test("existing article card keeps the complete summary and its limiting qualification", () => {
  const summary = "This model is safe under the reported conditions. " + "Evidence requires careful interpretation. ".repeat(20) + "It is not approved for general use.";
  const data = { ...base, files: [{ ...files[0], summary }] };
  const view = buildWeeklyDashboardView(data, "en", t);
  assert.ok(view.explanationText.includes("Study 0"));
  const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang="en" t={t} onOpenFile={() => {}} />);
  assert.ok(!view.explanationText.includes(summary));
  assert.ok(markup.includes(summary));
  assert.ok(markup.includes("It is not approved for general use."));
});


test("legacy failed guide displays the complete existing 943 character summary", () => {
  const summary = "A real first sentence. " + "Further source detail. ".repeat(40);
  assert.equal(summary.length, 943);
  const view = buildWeeklyDashboardView({ ...base, files: [{ ...files[0], summary }] }, "en", t);
  const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang="en" t={t} onOpenFile={() => {}} />);
  assert.ok(markup.includes(summary.trim()));
  assert.ok(!view.explanationText.includes(summary.trim()));
});

test("legacy failed guide uses title only when the source summary is missing", () => {
  const view = buildWeeklyDashboardView({ ...base, files: [{ ...files[0], summary: null }] }, "en", t);
  assert.ok(view.explanationText.includes("Study 0"));
  assert.ok(!view.explanationText.includes("Source summary"));
  assert.ok(view.explanationText.includes("Topic details are unavailable"));
  assert.ok(!view.explanationText.includes("highlights cover Study"));
  assert.ok(!view.explanationText.includes("explore Study 0 in detail"));
  assert.match(buildWeeklyDashboardView({ ...base, files: [{ ...files[0], category: "AI" }] }, "zh", t).explanationText, /适合希望了解该文具体内容的读者/);
});

test("saved recommendations share one order across languages and lead the existing cards", () => {
  const ranked = [files[4], files[1], files[3]];
  const guide = (items: typeof files) => "This week focuses on insurance AI.\n\n" + items.map(file => `- [${file.title}](${file.url})\n  Source excerpt.`).join("\n\n");
  const data: WeeklyDashboardData = {
    ...base,
    files: files.map(file => ({ ...file, category: "Insurance", keywords: ["reserving"], bilingual_metadata: {
      en: { title: file.title, summary: file.summary, category: "Insurance", keywords: ["AI", "data science", "reserving", "governance", "pricing"] },
      zh: { title: `中文${file.title}`, summary: "中文摘要。", category: "Insurance", keywords: ["人工智能", "数据科学", "准备金", "治理", "定价"] },
    } })),
    explanation: { ...base.explanation!, status: "complete", explanation_en: guide(ranked), explanation_zh: guide([...ranked].reverse()) },
  };
  for (const lang of ["en", "zh"]) {
    const view = buildWeeklyDashboardView(data, lang, t);
    assert.deepEqual(view.files.slice(0, 3).map(file => file.url), ranked.map(file => file.url));
    assert.equal(view.recommendedCount, 3);
    assert.match(view.explanationText, lang === "zh" ? /本周发现 5 篇文章/ : /discovered 5 articles/);
    assert.match(view.explanationText, lang === "zh" ? /适合希望了解准备金、治理、定价主题具体内容/ : /explore reserving, governance, pricing in detail/);
    assert.ok(!view.explanationText.includes(lang === "zh" ? "本周重点包括：准备金、治理、定价、准备金" : "highlights cover reserving, governance, pricing, reserving"));
    for (const grouped of [false, true]) {
      const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang={lang} t={t} onOpenFile={() => {}} grouped={grouped} />);
      assert.equal((markup.match(/data-testid="weekly-file-row-/g) || []).length, 5);
      assert.equal((markup.match(/<li>/g) || []).length, 3);
      const cardTitles = [...markup.matchAll(/data-testid="weekly-file-row-\d+"[^]*?title="([^"]+)"/g)].map(match => match[1]);
      assert.deepEqual(cardTitles.slice(0, 3), ranked.map(file => lang === "zh" ? `中文${file.title}` : file.title));
      assert.ok(!markup.includes("Source excerpt."));
    }
  }
  assert.deepEqual(data.files.map(file => file.url), files.map(file => file.url), "view must not mutate the API result");
});

test("home fetches later snapshot members before trimming the six-card preview", async () => {
  const members = Array.from({ length: 1116 }, (_, i) => ({ ...files[0], url: `https://example.org/${i}`, title: `Study ${i}` }));
  const recommended = [members[502], members[8], members[1]];
  const data = { ...base, snapshot: { ...snapshot, file_count: members.length }, explanation: {
    ...base.explanation!, status: "complete" as const,
    explanation_en: recommended.map(file => `- [${file.title}](${file.url})`).join("\n\n"),
  } };
  const calls: string[] = [];
  const load = (failPages: boolean) => loadLatestWeeklyDashboard(async <T,>(url: string): Promise<T> => {
    calls.push(url);
    if (url.endsWith("/latest")) return { summary: data.snapshot } as T;
    if (url.endsWith("/explanation")) return { explanation: data.explanation } as T;
    const params = new URL(url, "https://fixture").searchParams;
    const limit = Number(params.get("limit"));
    const offset = Number(params.get("offset"));
    if (failPages && limit === 500) throw new Error("Additional page unavailable");
    return { files: members.slice(offset, offset + limit), total: members.length } as T;
  });
  const loaded = await load(false);
  assert.equal(loaded.files.length, 6);
  assert.deepEqual(loaded.files.slice(0, 3), recommended);
  assert.ok(calls.some(url => url.endsWith("limit=500&offset=6")));
  assert.equal(calls.filter(url => url.includes("/files?")).length, 2, "stop once the recommendations are found");
  assert.ok(calls.every(url => !/generate|retry/.test(url)));
  const partial = await load(true);
  assert.equal(partial.files.length, 6);
  assert.equal(partial.filesUnavailable, false);
  assert.ok(!buildWeeklyDashboardView(partial, "en", t).explanationText.includes("Study 502"));
});

test("home retains recommendations from a successful page when a subsequent page fails", async () => {
  const members = Array.from({ length: 1116 }, (_, i) => ({ ...files[0], url: `https://example.org/${i}`, title: `Study ${i}` }));
  const loaded = await loadLatestWeeklyDashboard(async <T,>(url: string): Promise<T> => {
    if (url.endsWith("/latest")) return { summary: { ...snapshot, file_count: members.length } } as T;
    if (url.endsWith("/explanation")) return { explanation: { ...base.explanation!, status: "complete",
      explanation_en: [1100, 502, 1].map(i => `- [Study ${i}](${members[i].url})`).join("\n\n"),
    } } as T;
    const params = new URL(url, "https://fixture").searchParams;
    const offset = Number(params.get("offset"));
    const limit = Number(params.get("limit"));
    if (offset >= 506) throw new Error("Later page unavailable");
    return { files: members.slice(offset, offset + limit), total: members.length } as T;
  });
  assert.equal(loaded.files.length, 6);
  assert.equal(loaded.filesUnavailable, false);
  assert.deepEqual(loaded.files.slice(0, 2), [members[502], members[1]]);
  const view = buildWeeklyDashboardView(loaded, "en", t);
  assert.ok(view.explanationText.includes("Study 502"));
  assert.ok(!view.explanationText.includes("Study 1100"));
});

test("recommendations handle fewer than three members and escaped titles and URLs", () => {
  const file = { ...files[0], url: "https://example.org/report (final).pdf", title: "Report [v2] *final*", keywords: ["pricing"] };
  const data = { ...base, snapshot: { ...snapshot, file_count: 2 }, files: [files[1], file], explanation: {
    ...base.explanation!, status: "complete" as const,
    explanation_en: "Weekly focus.\n\n- [Report \\[v2\\] \\*final\\*](https://example.org/report%20%28final%29.pdf)\n\n- [Outside](https://outside.example/report)",
  } };
  const view = buildWeeklyDashboardView(data, "en", t);
  assert.equal(view.files[0], file);
  assert.equal(view.recommendedCount, 2);
  const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang="en" t={t} onOpenFile={() => {}} />);
  assert.equal((markup.match(/<li>/g) || []).length, 2);
  assert.ok(markup.includes("Report [v2] *final*"));
  assert.ok(!markup.includes("<em>final</em>"));
  assert.ok(!markup.includes("outside.example"));
});

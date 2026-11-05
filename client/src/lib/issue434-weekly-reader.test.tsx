import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { WeeklyDashboardSection } from "../components/WeeklyDashboardSection";
import { WeeklyHighlightCard } from "../components/WeeklyHighlightCard";
import { buildWeeklyDashboardView, loadLatestWeeklyDashboard, loadWeeklyUpdateDetail, localizedWeeklyFileMetadata, type WeeklyDashboardData } from "./weekly-dashboard";

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
    assert.equal(view.recommendedCount, 3, "a legacy failed guide without saved links uses the deterministic first three cards");
    assert.deepEqual(view.files.slice(0, 3).map(file => file.url), files.slice(0, 3).map(file => file.url));
    assert.equal((markup.match(/<li>/g) || []).length, 3);
    assert.ok(markup.includes(lang === "zh" ? "本周推荐阅读以下文章：" : "Recommended reading this week:"));
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
  const data = { ...base, files: [{ ...files[0], summary }], explanation: {
    ...base.explanation!, status: "complete" as const,
    explanation_en: `- [Study 0](${files[0].url})`,
  } };
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
  const view = buildWeeklyDashboardView({ ...base, files: [{ ...files[0], summary: null }], explanation: {
    ...base.explanation!, status: "complete" as const, explanation_en: `- [Study 0](${files[0].url})`,
  } }, "en", t);
  assert.ok(view.explanationText.includes("Study 0"));
  assert.ok(!view.explanationText.includes("Source summary"));
  assert.ok(view.explanationText.includes("Topic details are unavailable"));
  assert.ok(!view.explanationText.includes("highlights cover Study"));
  assert.ok(!view.explanationText.includes("explore Study 0 in detail"));
  assert.match(buildWeeklyDashboardView({ ...base, files: [{ ...files[0], category: "AI" }], explanation: {
    ...base.explanation!, status: "complete" as const, explanation_zh: `- [Study 0](${files[0].url})`,
  } }, "zh", t).explanationText, /适合希望了解该文具体内容的读者/);
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
  const partialView = buildWeeklyDashboardView(partial, "en", t);
  assert.equal(partialView.recommendedCount, 0);
  assert.equal(partialView.explanationText, data.explanation.explanation_en);
  assert.ok(!partialView.explanationText.includes("Recommended reading this week"));
});

test("frozen weekly recommendation cards keep both sites' bilingual guide projections equal", () => {
  const guide = (urls: string[]) => urls.map((url, index) => `- [Study ${index}](${url})`).join("\n\n");
  const urls = files.slice(0, 3).map(file => file.url);
  const localFiles = (site: string) => files.map((file, index) => ({
    ...file,
    original_filename: null,
    title: `${site} base ${index}`,
    summary: `${site} base summary ${index}`,
    category: `${site} base category`,
    keywords: [`${site} base keyword ${index}`],
    bilingual_metadata: {
      en: { title: `${site} English ${index}`, summary: `${site} English summary ${index}`, category: "Pricing", keywords: [`${site} English topic ${index}`] },
      zh: { title: `${site} 中文标题 ${index}`, summary: `${site} 中文摘要 ${index}`, category: "Pricing", keywords: [`${site} 中文主题 ${index}`] },
    },
  }));
  const canonicalFiles = localFiles("China");
  const guideGeneratedAt = "2026-10-26T00:30:00+00:00";
  const projections = canonicalFiles.slice(0, 3).map(file => ({
    url: file.url,
    first_seen: file.first_seen,
    original_filename: file.original_filename ?? null,
    title: file.title,
    category: file.category,
    keywords: file.keywords,
    summary: file.summary,
    bilingual_metadata: file.bilingual_metadata,
  }));
  const guideState = {
    ...base,
    snapshot: { ...snapshot, file_count: files.length, metadata: {
      weekly_recommendation_cards_v1: projections,
      weekly_recommendation_cards_v1_owner: {
        snapshot_id: snapshot.id,
        guide_generated_at: guideGeneratedAt,
      },
    } },
    explanation: {
      ...base.explanation!,
      status: "complete" as const,
      explanation_en: guide(urls),
      explanation_zh: guide(urls),
      generated_at: guideGeneratedAt,
    },
  };
  const chinaData = { ...guideState, files: canonicalFiles };
  const overseasData = { ...guideState, files: localFiles("Overseas") };
  for (const lang of ["zh", "en"]) {
    const sourceView = buildWeeklyDashboardView(chinaData, lang, t);
    const overseasView = buildWeeklyDashboardView(overseasData, lang, t);
    assert.equal(overseasView.explanationText, sourceView.explanationText);
    assert.deepEqual(overseasView.files.slice(0, 3).map(file => file.url), urls);
    assert.deepEqual(
      overseasView.files.slice(0, 3).map(file => localizedWeeklyFileMetadata(file, lang).title),
      sourceView.files.slice(0, 3).map(file => localizedWeeklyFileMetadata(file, lang).title),
    );
    assert.equal(overseasData.files[0].title, "Overseas base 0", "the view overlays a copy, not API rows");
    const home = renderToStaticMarkup(<WeeklyDashboardSection data={overseasData} lang={lang} t={t} onOpenFile={() => {}} />);
    const detail = renderToStaticMarkup(<WeeklyHighlightCard view={overseasView} lang={lang} t={t} onOpenFile={() => {}} />);
    for (const markup of [home, detail]) {
      assert.equal((markup.match(/data-testid="weekly-file-row-/g) || []).length, 5);
      assert.ok(markup.includes(localizedWeeklyFileMetadata(sourceView.files[0], lang).title));
    }
  }

  const legacyProjection = projections.map((projection, index) => index === 0
    ? { ...projection, bilingual_metadata: null }
    : projection);
  const legacyState = {
    ...guideState,
    snapshot: { ...guideState.snapshot!, metadata: {
      weekly_recommendation_cards_v1: legacyProjection,
      weekly_recommendation_cards_v1_owner: {
        snapshot_id: snapshot.id,
        guide_generated_at: guideGeneratedAt,
      },
    } },
  };
  const legacyChina = buildWeeklyDashboardView({ ...legacyState, files: canonicalFiles }, "en", t);
  const legacyOverseas = buildWeeklyDashboardView({ ...legacyState, files: localFiles("Overseas") }, "en", t);
  assert.equal(
    localizedWeeklyFileMetadata(legacyOverseas.files[0], "en").title,
    localizedWeeklyFileMetadata(legacyChina.files[0], "en").title,
    "a projection with legacy-only metadata still overlays shared fallback fields",
  );

  const newGuideTime = "2026-10-27T00:30:00+00:00";
  const newGuideState = {
    ...guideState,
    explanation: { ...guideState.explanation!, generated_at: newGuideTime },
  };
  const freshChina = buildWeeklyDashboardView({ ...newGuideState, files: canonicalFiles }, "en", t);
  const freshOverseas = buildWeeklyDashboardView({ ...newGuideState, files: localFiles("Overseas") }, "en", t);
  assert.notEqual(freshOverseas.explanationText, freshChina.explanationText, "an old projection cannot own a new guide revision");

  const refreshedProjection = localFiles("China").slice(0, 3).map(file => ({
    url: file.url,
    first_seen: file.first_seen,
    original_filename: file.original_filename ?? null,
    title: file.title,
    category: file.category,
    keywords: file.keywords,
    summary: file.summary,
    bilingual_metadata: file.bilingual_metadata,
  }));
  const refreshedState = {
    ...newGuideState,
    snapshot: { ...snapshot, file_count: files.length, metadata: {
      weekly_recommendation_cards_v1: refreshedProjection,
      weekly_recommendation_cards_v1_owner: {
        snapshot_id: snapshot.id,
        guide_generated_at: newGuideTime,
      },
    } },
  };
  for (const lang of ["zh", "en"]) {
    const sourceView = buildWeeklyDashboardView({ ...refreshedState, files: localFiles("China") }, lang, t);
    const overseasView = buildWeeklyDashboardView({ ...refreshedState, files: localFiles("Overseas") }, lang, t);
    assert.equal(overseasView.explanationText, sourceView.explanationText);
    assert.deepEqual(
      overseasView.files.slice(0, 3).map(file => localizedWeeklyFileMetadata(file, lang).title),
      sourceView.files.slice(0, 3).map(file => localizedWeeklyFileMetadata(file, lang).title),
    );
  }
});

test("a frozen guide keeps the same recommendations through a partial home-page read", async () => {
  const recommendationIndexes = [1100, 502, 1];
  const generatedAt = "2026-10-26T00:30:00+00:00";
  const guideText = (site: string) => recommendationIndexes
    .map(index => `- [Study ${index}](${membersFor(site)[index].url})`).join("\n\n");
  const membersFor = (site: string) => Array.from({ length: 1116 }, (_, i) => ({
    ...files[0],
    url: `https://example.org/${i}`,
    original_filename: `study-${i}.pdf`,
    title: `${site} local Study ${i}`,
    summary: `${site} local summary ${i}`,
    category: `${site} local category`,
    keywords: [`${site} local topic ${i}`],
    bilingual_metadata: {
      en: { title: `${site} local English ${i}`, summary: `${site} local English summary ${i}`, category: `${site} local category`, keywords: [`${site} local English topic ${i}`] },
      zh: { title: `${site} local 中文 ${i}`, summary: `${site} local 中文摘要 ${i}`, category: `${site} local category`, keywords: [`${site} local 中文主题 ${i}`] },
    },
  }));
  const chinaMembers = membersFor("China");
  const overseasMembers = membersFor("Overseas");
  const sourceGuide = {
    ...base.explanation!,
    status: "complete" as const,
    explanation_en: guideText("China"),
    explanation_zh: guideText("China"),
    generated_at: generatedAt,
  };
  const projection = (index: number) => ({
    url: chinaMembers[index].url,
    first_seen: chinaMembers[index].first_seen,
    original_filename: chinaMembers[index].original_filename ?? null,
    title: `Canonical Study ${index}`,
    summary: `Canonical summary ${index}`,
    category: "Canonical category",
    keywords: [`Canonical topic ${index}`],
    bilingual_metadata: {
      en: { title: `Canonical English ${index}`, summary: `Canonical English summary ${index}`, category: "Canonical category", keywords: [`Canonical English topic ${index}`] },
      zh: { title: `规范中文标题 ${index}`, summary: `规范中文摘要 ${index}`, category: "Canonical category", keywords: [`规范中文主题 ${index}`] },
    },
  });
  const snapshotWithProjection = {
    ...snapshot,
    file_count: chinaMembers.length,
    metadata: {
      weekly_recommendation_cards_v1: recommendationIndexes.map(projection),
      weekly_recommendation_cards_v1_owner: {
        snapshot_id: snapshot.id,
        guide_generated_at: generatedAt,
      },
    },
  };
  const loadSite = async (site: string, siteMembers: typeof chinaMembers, failLaterPage: boolean) =>
    loadLatestWeeklyDashboard(async <T,>(url: string): Promise<T> => {
      if (url.endsWith("/latest")) return { summary: snapshotWithProjection } as T;
      if (url.endsWith("/explanation")) return { explanation: sourceGuide } as T;
      const params = new URL(url, "https://fixture").searchParams;
      const offset = Number(params.get("offset"));
      const limit = Number(params.get("limit"));
      if (failLaterPage && offset >= 506) throw new Error("Later page unavailable");
      return { files: siteMembers.slice(offset, offset + limit), total: siteMembers.length } as T;
    });
  const completeChina = await loadSite("China", chinaMembers, false);
  const partialOverseas = await loadSite("Overseas", overseasMembers, true);
  assert.equal(partialOverseas.files.length, 6);
  assert.equal(partialOverseas.files.some(file => file.url === overseasMembers[1100].url), false);

  for (const lang of ["en", "zh"]) {
    const chinaView = buildWeeklyDashboardView(completeChina, lang, t);
    const overseasView = buildWeeklyDashboardView(partialOverseas, lang, t);
    assert.equal(overseasView.files.length, 6, "home retains its six-card preview limit");
    assert.equal(overseasView.recommendedCount, 3);
    assert.equal(overseasView.explanationText, chinaView.explanationText);
    assert.deepEqual(
      overseasView.files.slice(0, 3).map(file => file.url),
      recommendationIndexes.map(index => chinaMembers[index].url),
    );
    assert.deepEqual(
      overseasView.files.slice(0, 3).map(file => localizedWeeklyFileMetadata(file, lang).title),
      chinaView.files.slice(0, 3).map(file => localizedWeeklyFileMetadata(file, lang).title),
    );
    assert.equal(overseasView.files[0].title, "Canonical Study 1100");
    const homeMarkup = renderToStaticMarkup(<WeeklyDashboardSection data={partialOverseas} lang={lang} t={t} onOpenFile={() => {}} />);
    const weeklyMarkup = renderToStaticMarkup(<WeeklyHighlightCard view={overseasView} lang={lang} t={t} onOpenFile={() => {}} grouped />);
    for (const markup of [homeMarkup, weeklyMarkup]) {
      assert.ok(markup.includes(localizedWeeklyFileMetadata(chinaView.files[0], lang).title));
      assert.ok(markup.includes(localizedWeeklyFileMetadata(chinaView.files[0], lang).summary));
    }
  }

  const detail = await loadWeeklyUpdateDetail(snapshot.id, async <T,>(url: string): Promise<T> => {
    if (url.endsWith("/explanation")) return { explanation: sourceGuide } as T;
    if (url.includes("/files?")) {
      const params = new URL(url, "https://fixture").searchParams;
      const offset = Number(params.get("offset"));
      const limit = Number(params.get("limit"));
      return { files: overseasMembers.slice(offset, offset + limit), total: overseasMembers.length } as T;
    }
    return { summary: snapshotWithProjection } as T;
  });
  const detailView = buildWeeklyDashboardView(detail, "en", t);
  assert.equal(detailView.files.length, overseasMembers.length, "weekly detail keeps every loaded member");
  assert.equal(detailView.recommendedCount, 3);
  assert.deepEqual(detailView.files.slice(0, 3).map(file => file.url), recommendationIndexes.map(index => chinaMembers[index].url));

  const legacyData = {
    ...partialOverseas,
    snapshot: { ...snapshotWithProjection, metadata: {} },
  };
  const legacyView = buildWeeklyDashboardView(legacyData, "en", t);
  assert.equal(legacyView.recommendedCount, 0);
  assert.equal(legacyView.explanationText, sourceGuide.explanation_en);
  assert.ok(!legacyView.explanationText.includes("Recommended reading this week"));
  assert.ok(!legacyView.explanationText.includes("Study 0"));
});

test("recommendations handle fewer than three members and escaped titles and URLs", () => {
  const file = { ...files[0], url: "https://example.org/report (final).pdf", title: "Report [v2] *final*", keywords: ["pricing"] };
  const data = { ...base, snapshot: { ...snapshot, file_count: 2 }, files: [files[1], file], explanation: {
    ...base.explanation!, status: "complete" as const,
    explanation_en: "Weekly focus.\n\n- [Report \\[v2\\] \\*final\\*](https://example.org/report%20%28final%29.pdf)",
  } };
  const view = buildWeeklyDashboardView(data, "en", t);
  assert.equal(view.files[0], file);
  assert.equal(view.recommendedCount, 1);
  const markup = renderToStaticMarkup(<WeeklyHighlightCard view={view} lang="en" t={t} onOpenFile={() => {}} />);
  assert.equal((markup.match(/<li>/g) || []).length, 1);
  assert.ok(markup.includes("Report [v2] *final*"));
  assert.ok(!markup.includes("<em>final</em>"));
  assert.ok(!markup.includes("outside.example"));
});

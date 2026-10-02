import assert from "node:assert/strict";
import { chromium } from "playwright-core";
import axe from "axe-core";

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true });
const assertVisibleFocusables = async (page, forbiddenHrefs = []) => {
  await page.evaluate(() => (document.activeElement instanceof HTMLElement ? document.activeElement.blur() : undefined));
  const seen = [];
  const seenKeys = new Set();
  for (let index = 0; index < 48; index += 1) {
    await page.keyboard.press("Tab");
    const target = await page.evaluate(() => {
      const node = document.activeElement;
      if (!(node instanceof HTMLElement) || !node.matches('a[href],button,input,select,textarea,[tabindex]')) return null;
      const rect = node.getBoundingClientRect();
      let hidden = false;
      for (let current = node; current; current = current.parentElement) {
        const style = getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden" || current.getAttribute("aria-hidden") === "true") {
          hidden = true;
          break;
        }
      }
      return { id: node.id, testId: node.getAttribute("data-testid"), href: node instanceof HTMLAnchorElement ? node.getAttribute("href") : null, hidden, width: rect.width, height: rect.height };
    });
    if (!target) continue;
    const key = `${target.href || ""}|${target.id}|${target.testId || ""}`;
    if (seenKeys.has(key)) break;
    seenKeys.add(key);
    seen.push(target);
    assert.equal(target.hidden, false, `Tab reached hidden focusable ${JSON.stringify(target)}`);
    assert.ok(target.width > 0 && target.height > 0, `Tab reached zero-size focusable ${JSON.stringify(target)}`);
  }
  for (const href of forbiddenHrefs) assert.equal(seen.some((target) => target.href === href), false, `Tab reached mobile-hidden link ${href}: ${JSON.stringify(seen)}`);
  return seen;
};
const assertTextZoom = async (page, control, action = control) => {
  await page.evaluate(() => { document.documentElement.style.fontSize = ""; });
  const before = await page.evaluate(() => ({
    root: Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
    text: Array.from(document.querySelectorAll("h1,h2,h3,p,label,button"))
      .filter((node) => node instanceof HTMLElement && node.getBoundingClientRect().width > 0 && node.getBoundingClientRect().height > 0)
      .map((node, index) => { node.setAttribute("data-smoke-zoom-text", String(index)); return { index, fontSize: Number.parseFloat(getComputedStyle(node).fontSize) }; }),
  }));
  await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
  await control.scrollIntoViewIfNeeded();
  assert.equal(await control.isVisible(), true);
  assert.equal(await action.isVisible(), true, "200% hid the form action");
  if (await control.evaluate((node) => node.matches("input,select,textarea"))) {
    assert.equal(await control.evaluate((node) => Boolean(node.labels?.[0]?.textContent?.trim() || node.getAttribute("aria-labelledby"))), true, "200% control lost its visible label association");
  }
  const after = await page.evaluate((beforeText) => ({
    root: Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
    grownText: beforeText.some(({ index, fontSize }) => {
      const node = document.querySelector(`[data-smoke-zoom-text="${index}"]`);
      return node && Number.parseFloat(getComputedStyle(node).fontSize) >= fontSize * 1.9;
    }),
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  }), before.text);
  assert.ok(after.root >= before.root * 1.9, "200% did not increase root text");
  assert.equal(after.grownText, true, "200% did not increase a visible text sample");
  assert.equal(after.overflow, false, "200% introduced horizontal viewport overflow");
  if (await action.evaluate((node) => node.matches("button,input,select,textarea,[tabindex]"))) {
    await action.focus();
    assert.equal(await action.evaluate((node) => document.activeElement === node), true);
  }
  assert.equal(await control.evaluate((node) => { const style = getComputedStyle(node); return style.clipPath === "none" && style.visibility !== "hidden" && style.display !== "none"; }), true, "200% text clipped the key form control");
};
const assertTarget = async (page, id) => { const rect = await page.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); };
const assertVisibleFocus = async (page) => assert.equal(await page.evaluate(() => { const node = document.activeElement; return !!node && (getComputedStyle(node).outlineStyle !== "none" || getComputedStyle(node).boxShadow !== "none"); }), true, "focused control has no visible focus indicator");
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const fixture = (url) => url.includes("/api/auth/me") ? { data: { require_auth: true, authenticated: true, user: { id: 1, email: "smoke@example.test", display_name: "Smoke", role: "admin", is_active: true }, permissions: ["tasks.run", "tasks.view", "tasks.stop", "schedule.write", "sites.write", "config.read", "config.write", "catalog.read", "catalog.write", "files.write", "files.delete", "files.download", "markdown.write", "export.read", "export.full", "users.manage"] } }
    : url.includes("/api/config/search-engines") ? { engines: [{ id: "brave", name: "Brave Search", configured: false }] }
    : url.includes("/api/config/backend-settings") ? { defaults: {}, features: { enable_file_deletion: false, enable_rate_limiting: false }, feature_sources: {} }
    : url.includes("/api/config/categories") ? { categories: { General: [] } }
    : url.includes("/api/auth/tokens") ? { tokens: [] }
    : url.includes("/api/config/providers") ? { providers: [{ provider_id: "openai", display_name: "OpenAI", supports: { chat: true } }] }
    : url.includes("/api/config/ai-models") || url.includes("/api/config/model-catalog") ? { available: { openai: [{ name: "smoke", display_name: "Smoke", types: ["chat"] }] } }
    : url.includes("/api/config/ai-routing") ? { bindings: [{ function_name: "chat", provider: "openai", model: "smoke", credential_id: "openai-smoke", configured: true }] }
    : url.includes("/api/config/provider-credentials") ? { credentials: [{ provider_id: "openai", category: "llm", api_key: "smoke", credential_id: "openai-smoke", is_default: true, source: "db" }] }
    : url.includes("/api/config/markdown-conversion") ? { config: { default_tool: "local", tools: { local: { display_name: "Local", provider: "local", model: "model" } }, formats: { pdf: { extensions: [".pdf"], candidate_chain: ["local"] } }, limits: { max_bytes: 10 } } }
    : { tasks: [], sites: [], settings: {}, defaults: {} };
  await page.route("**/api/**", (route) => route.request().method() === "POST" && route.request().url().includes("/api/collections/run")
    ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "crawl failed" }) })
    : route.fulfill({ contentType: "application/json", body: JSON.stringify(fixture(route.request().url())) }));
  await page.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await assertTarget(page, "button-toggle-history");
  for (const id of ["tab-run-tasks", "tab-pipeline-baton", "tab-scheduled-tasks"]) { const rect = await page.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  await page.getByTestId("button-start-web_crawl").click();
  const crawl = page.getByTestId("input-crawl-url");
  await crawl.waitFor();
  assert.ok(await crawl.evaluate((node) => node.labels?.length));
  for (const id of ["input-crawl-name", "input-crawl-max-pages", "input-crawl-max-depth"]) {
    assert.equal(await page.getByTestId(id).evaluate((node) => !!node.getAttribute("aria-describedby") && !!document.getElementById(node.getAttribute("aria-describedby"))), true);
  }
  const box = await crawl.boundingBox();
  assert.ok(box && box.width >= 43.9 && box.height >= 43.9, JSON.stringify(box));
  await crawl.focus(); await page.keyboard.press("Tab");
  assert.equal(await page.getByTestId("input-crawl-name").evaluate((node) => document.activeElement === node), true);
  assert.equal(await page.getByTestId("input-crawl-name").evaluate((node) => getComputedStyle(node).outlineStyle !== "none" || getComputedStyle(node).boxShadow !== "none"), true);
  for (const node of await page.locator('[data-testid="input-crawl-url"], [data-testid="input-crawl-name"], [data-testid="input-crawl-max-pages"], [data-testid="input-crawl-max-depth"], [data-testid="button-run-task"]').all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify(rect)); }
  const ids = await page.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id));
  const testIds = await page.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(new Set(testIds).size, testIds.length);
  await assertVisibleFocusables(page, ["/profile", "/users"]);
  assert.equal(await page.locator('[tabindex]:not([tabindex="-1"])').evaluateAll((nodes) => nodes.every((node) => getComputedStyle(node).display !== "none" && getComputedStyle(node).visibility !== "hidden")), true);
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="input-crawl-url"]')?.parentElement?.parentElement?.parentElement, { rules: { "color-contrast": { enabled: false } } })).violations);
  assert.deepEqual(violations, []);
  await crawl.fill("https://example.test");
  await assertTextZoom(page, crawl, page.getByTestId("button-run-task"));
  await page.getByTestId("button-run-task").click();
  const submitError = page.locator("#error-task-submit");
  await submitError.waitFor();
  assert.equal(await submitError.getAttribute("role"), "alert");
  assert.equal(await page.getByTestId("button-run-task").getAttribute("aria-describedby"), "error-task-submit");
  console.log(JSON.stringify({ chromium: "pass", surface: "tasks", labeled: true, target44: true, tab: true, uniqueIds: true, uniqueTestIds: true }));

  const fileImport = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await fileImport.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(fixture(route.request().url())) }));
  await fileImport.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await fileImport.getByTestId("button-start-file_import").click();
  for (const id of ["input-local-files", "input-local-directory"]) {
    const input = fileImport.getByTestId(id); await input.focus();
    assert.equal(await input.evaluate((node) => document.activeElement === node && node.closest("label")?.matches(":focus-within")), true, `${id} did not expose keyboard focus`);
    assert.equal(await input.getAttribute("aria-describedby"), "hint-local-files");
    const labelBox = await input.locator("xpath=ancestor::label").boundingBox(); assert.ok(labelBox && labelBox.width >= 43.9 && labelBox.height >= 43.9, JSON.stringify({ id, labelBox }));
  }
  await assertTextZoom(fileImport, fileImport.getByTestId("input-local-files").locator("xpath=ancestor::label"), fileImport.getByTestId("button-run-task"));
  console.log(JSON.stringify({ chromium: "pass", surface: "file-import", described: true, tab: true, text200: true }));

  const database = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await database.route("**/api/**", (route) => { const url = route.request().url(); const smokeFile = { url: "file-smoke", title: "Smoke", original_filename: "smoke.pdf", markdown_status: "ready", source_site: "Smoke", first_seen: "2026-01-01T00:00:00Z" }; return route.fulfill({ contentType: "application/json", body: JSON.stringify(url.includes("/api/sources") ? { sources: ["Smoke"] } : url.includes("/api/categories") ? { categories: ["General"] } : url.includes("/api/files") ? { files: [smokeFile], total: 40 } : fixture(url)) }); });
  await database.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/database`, { waitUntil: "domcontentloaded" });
  const dbSearch = database.getByTestId("input-search"); await dbSearch.waitFor();
  await database.getByTestId("button-toggle-filters").click();
  for (const id of ["input-search", "button-toggle-filters", "select-source", "select-category", "select-sort"]) { await assertTarget(database, id); assert.equal(await database.getByTestId(id).evaluate((node) => Boolean(node.labels?.[0]?.textContent?.trim() || node.getAttribute("aria-label") || node.textContent?.trim())), true, `${id} lacks a visible label`); }
  await dbSearch.focus(); await database.keyboard.press("Tab"); assert.equal(await database.getByTestId("button-toggle-filters").evaluate((node) => document.activeElement === node), true);
  await assertVisibleFocus(database);
  for (const id of ["button-export-csv", "button-export-full-csv", "checkbox-include-deleted"]) await assertTarget(database, id);
  const exportInternal = await database.getByTestId("checkbox-export-internal-fields").locator("xpath=parent::label").boundingBox(); assert.ok(exportInternal && exportInternal.width >= 43.9 && exportInternal.height >= 43.9, JSON.stringify(exportInternal));
  await database.getByTestId("select-source").selectOption("Smoke");
  await assertTarget(database, "button-clear-filters");
  await dbSearch.fill("smoke");
  for (const id of ["button-clear-search", "input-page-jump", "button-page-jump", "button-select-all-visible", "button-bulk-delete", "checkbox-select-mobile-0", "button-ai-explain-mobile-0", "button-preview-mobile-0", "button-download-mobile-0", "button-prev-page", "button-next-page"]) await assertTarget(database, id);
  await database.addScriptTag({ content: axe.source }); assert.deepEqual(await database.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="input-search"]')?.parentElement?.parentElement, { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await assertTextZoom(database, dbSearch, database.getByTestId("button-toggle-filters"));
  console.log(JSON.stringify({ chromium: "pass", surface: "database", labeled: true, target44: true, tab: true, text200: true }));

  const settings = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await settings.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(fixture(route.request().url())) }));
  await settings.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/settings`, { waitUntil: "domcontentloaded" });
  await settings.getByTestId("tab-ai").click();
  await assertTarget(settings, "button-refresh-settings");
  for (const id of ["button-import-provider-env", "button-refresh-model-catalog", "button-reencrypt-credentials", "button-add-provider", "button-add-model-route"]) { const rect = await settings.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  await settings.getByTestId("button-edit-provider-openai").click();
  for (const id of ["input-api-key-openai", "input-base-url-openai", "button-save-provider-openai", "button-cancel-provider-openai"]) await assertTarget(settings, id);
  await settings.getByTestId("button-add-model-route").click();
  for (const id of ["select-add-model-function", "select-add-model-provider", "select-add-model-name", "select-add-model-credential", "button-stage-model-route", "button-cancel-model-route-add"]) await assertTarget(settings, id);
  await settings.getByTestId("button-cancel-model-route-add").click();
  await settings.getByTestId("button-edit-model-chat").click();
  for (const id of ["select-provider-chat", "select-credential-chat", "select-model-chat", "button-cancel-model-chat"]) await assertTarget(settings, id);
  await settings.getByTestId("tab-search").click();
  for (const id of ["button-edit-search-brave", "input-max-pages", "input-max-depth", "input-delay", "input-extensions", "input-keywords"]) { const rect = await settings.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  await settings.getByTestId("input-max-pages").fill("201"); const defaultsSave = settings.getByTestId("button-save-defaults"); await defaultsSave.waitFor(); const defaultsSaveBox = await defaultsSave.boundingBox(); assert.ok(defaultsSaveBox && defaultsSaveBox.width >= 43.9 && defaultsSaveBox.height >= 43.9, JSON.stringify(defaultsSaveBox));
  await settings.getByTestId("button-edit-search-brave").click();
  const credential = settings.getByTestId("input-search-key-brave");
  await credential.waitFor();
  assert.equal(await credential.getAttribute("aria-labelledby"), "label-search-engine-brave");
  assert.ok(await settings.locator("#label-search-engine-brave").textContent());
  const credentialBox = await credential.boundingBox();
  assert.ok(credentialBox && credentialBox.width >= 43.9 && credentialBox.height >= 43.9, JSON.stringify(credentialBox));
  await assertTarget(settings, "button-cancel-search-brave");
  await credential.focus(); await settings.keyboard.press("Tab");
  assert.equal(await settings.evaluate(() => document.activeElement?.matches("button")), true);
  assert.equal(await settings.evaluate(() => { const node = document.activeElement; return !!node && (getComputedStyle(node).outlineStyle !== "none" || getComputedStyle(node).boxShadow !== "none"); }), true);
  const settingIds = await settings.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id));
  const settingTestIds = await settings.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(settingIds).size, settingIds.length); assert.equal(new Set(settingTestIds).size, settingTestIds.length);
  await settings.addScriptTag({ content: axe.source });
  const settingsViolations = await settings.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="input-search-key-brave"]')?.parentElement, { rules: { "color-contrast": { enabled: false } } })).violations);
  assert.deepEqual(settingsViolations, []);
  await settings.getByTestId("tab-prompts").click(); const promptsBox = await settings.getByTestId("tab-prompts").boundingBox(); assert.ok(promptsBox && promptsBox.height >= 43.9, JSON.stringify(promptsBox)); await assertTarget(settings, "weekly-explanation-prompt-edit"); await settings.getByTestId("weekly-explanation-prompt-edit").click(); const weeklyPrompt = settings.getByTestId("weekly-explanation-prompt-input"); await weeklyPrompt.waitFor(); assert.equal(await weeklyPrompt.getAttribute("aria-labelledby"), "weekly-explanation-prompt-title"); await assertTarget(settings, "weekly-explanation-prompt-cancel");
  await settings.getByTestId("tab-categories").click(); const aiFilter = settings.getByTestId("input-ai-filter-keywords"); await aiFilter.waitFor(); assert.equal(await aiFilter.getAttribute("aria-describedby"), "hint-ai-filter-keywords hint-ai-filter-crawler"); assert.equal(await aiFilter.getAttribute("aria-labelledby"), "heading-ai-filter-keywords"); assert.ok((await settings.locator("#hint-ai-filter-crawler").textContent())?.trim()); for (const id of ["input-new-category", "button-add-category", "button-toggle-category-General"]) { await assertTarget(settings, id); }
  for (const label of [settings.locator('label[for="input-new-category"]'), settings.locator("#heading-ai-filter-keywords")]) { const rect = await label.boundingBox(); assert.ok(rect && rect.width > 1 && rect.height > 1, JSON.stringify(rect)); }
  await settings.getByTestId("button-toggle-category-General").click(); const categoryLabel = settings.locator('label[for="input-cat-keywords-General"]'); const categoryLabelBox = await categoryLabel.boundingBox(); assert.ok(categoryLabelBox && categoryLabelBox.width > 1 && categoryLabelBox.height > 1, JSON.stringify(categoryLabelBox));
  await settings.getByTestId("input-new-category").fill("Smoke category");
  await assertTextZoom(settings, aiFilter, settings.getByTestId("button-add-category"));
  await settings.getByTestId("tab-system").click();
  await settings.getByTestId("toggle-system-flag-enable_file_deletion").waitFor();
  for (const id of ["toggle-system-flag-enable_file_deletion", "input-rate-limit-defaults"]) await assertTarget(settings, id);
  await settings.getByTestId("tab-tokens").click();
  await assertTarget(settings, "button-create-token");
  await settings.getByTestId("button-create-token").click();
  const tokenSubject = settings.getByTestId("input-token-subject"); await tokenSubject.waitFor();
  for (const id of ["input-token-subject", "select-token-group", "button-submit-token"]) await assertTarget(settings, id);
  await tokenSubject.fill("Smoke token");
  await assertTextZoom(settings, tokenSubject, settings.getByTestId("button-submit-token"));
  console.log(JSON.stringify({ chromium: "pass", surface: "settings", labeled: true, target44: true, tab: true, uniqueIds: true, uniqueTestIds: true }));

  const preview = await browser.newPage({ viewport: { width: 1280, height: 844 } });
  await preview.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/rag/files/preview") ? { data: { file_info: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", local_path: "", content_type: "application/pdf", bytes: 10 }, markdown: { content: "text", source: "smoke", updated_at: "" }, chunk_sets: [{ chunk_set_id: "set-a", profile_name: "A", chunk_count: 1 }, { chunk_set_id: "set-b", profile_name: "B", chunk_count: 1 }], active_chunk_set_id: "set-a", chunks: [{ chunk_id: "c1", chunk_index: 0, content: "text", token_count: 1, chunk_set_id: "set-a" }] } } : fixture(route.request().url())) }));
  await preview.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/file-preview?file_url=file-smoke`, { waitUntil: "domcontentloaded" });
  const chunkSet = preview.getByTestId("select-chunk-set"); await chunkSet.waitFor();
  assert.equal(await chunkSet.getAttribute("aria-labelledby"), "label-chunk-set");
  assert.ok(await preview.locator("#label-chunk-set").textContent());
  await chunkSet.focus(); assert.equal(await preview.evaluate(() => document.activeElement?.id), "select-chunk-set");
  const previewIds = await preview.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id)); const previewTestIds = await preview.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(previewIds).size, previewIds.length); assert.equal(new Set(previewTestIds).size, previewTestIds.length);
  await preview.addScriptTag({ content: axe.source });
  assert.deepEqual(await preview.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="pane-chunks"]'), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await assertTextZoom(preview, chunkSet, preview.getByTestId("button-back-preview"));
  console.log(JSON.stringify({ chromium: "pass", surface: "file-preview", labeled: true, tab: true, uniqueIds: true, uniqueTestIds: true }));

  const previewMobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await previewMobile.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/rag/files/preview") ? { data: { file_info: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", local_path: "", content_type: "application/pdf", bytes: 10 }, markdown: { content: "text", source: "smoke", updated_at: "" }, chunk_sets: [{ chunk_set_id: "set-a", profile_name: "A", chunk_count: 1 }], active_chunk_set_id: "set-a", chunks: [] } } : fixture(route.request().url())) }));
  await previewMobile.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/file-preview?file_url=file-smoke`, { waitUntil: "domcontentloaded" });
  assert.equal(await previewMobile.getByTestId("select-chunk-set").count(), 0);
  assert.equal(await previewMobile.locator('[tabindex]:not([tabindex="-1"])').evaluateAll((nodes) => nodes.every((node) => getComputedStyle(node).display !== "none" && getComputedStyle(node).visibility !== "hidden")), true);
  await assertVisibleFocusables(previewMobile);
  console.log(JSON.stringify({ chromium: "pass", surface: "file-preview-mobile", hiddenControlsExcluded: true }));

  const loggedOut = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await loggedOut.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/auth/me") ? { data: { require_auth: true, authenticated: false, user: null, permissions: [] } } : fixture(route.request().url())) }));
  await loggedOut.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await assertVisibleFocusables(loggedOut, ["/register"]);
  console.log(JSON.stringify({ chromium: "pass", surface: "layout-mobile-logged-out", hiddenControlsExcluded: true }));

  const knowledge = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await knowledge.addInitScript(() => localStorage.setItem("lang", "zh"));
  await knowledge.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/rag/knowledge-bases") ? { knowledge_bases: [{ kb_id: "kb-smoke", name: "Smoke KB", description: "Needs re-embed", file_count: 1, chunk_count: 1, status: "ready", embedding_model: "smoke", reason: "embedding_incompatible" }] } : route.request().url().includes("/api/rag/files/selectable") ? { files: [{ url: "file-smoke", title: "Smoke file" }] } : route.request().url().includes("/api/chunk/profiles") ? { profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }] } : route.request().url().includes("/api/rag/categories/mapping") || route.request().url().includes("/api/categories?mode=used") ? { categories: ["General"] } : fixture(route.request().url())) }));
  await knowledge.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/knowledge`, { waitUntil: "domcontentloaded" });
  for (const id of ["button-build-agentic-manifest-kb-smoke", "button-view-kb-kb-smoke", "button-ask-ai-kb-kb-smoke", "button-delete-kb-kb-smoke"]) { const rect = await knowledge.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  for (const id of ["button-reembed-kb-kb-smoke", "button-toggle-cleanup"]) { const rect = await knowledge.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  await knowledge.getByTestId("button-create-kb").click();
  await knowledge.getByTestId("select-kb-mode").selectOption("category");
  await assertTarget(knowledge, "button-toggle-kb-category-General");
  await knowledge.getByTestId("button-close-create-kb").click();
  await knowledge.getByTestId("button-toggle-cleanup").click();
  for (const id of ["input-cleanup-days", "label-cleanup-dryrun", "button-run-cleanup"]) { const rect = await knowledge.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  await assertTarget(knowledge, "button-create-kb");
  await knowledge.getByTestId("button-create-kb").click();
  const kbName = knowledge.getByTestId("input-kb-name"); await kbName.waitFor();
  await knowledge.getByTestId("select-kb-mode").selectOption("manual");
  await knowledge.getByTestId("button-select-all-kb-files").waitFor();
  await assertTarget(knowledge, "button-select-all-kb-files");
  const kbCloseBox = await knowledge.getByTestId("button-close-create-kb").boundingBox(); assert.ok(kbCloseBox && kbCloseBox.width >= 43.9 && kbCloseBox.height >= 43.9, JSON.stringify(kbCloseBox));
  assert.ok(await kbName.evaluate((node) => node.labels?.[0]?.textContent?.trim()));
  for (const [id, hint] of [["input-kb-id", "hint-kb-id"], ["select-kb-mode", "hint-kb-mode"]]) assert.equal(await knowledge.getByTestId(id).evaluate((node, hintId) => node.getAttribute("aria-describedby") === hintId && !!document.getElementById(hintId), hint), true);
  for (const node of await knowledge.locator('[data-testid="input-kb-name"], [data-testid="input-kb-id"], [data-testid="select-kb-mode"], [data-testid="select-kb-chunk-profile"], [data-testid="input-kb-description"], [data-testid="button-submit-kb"], [data-testid="button-submit-kb-index"]').all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify(rect)); }
  await kbName.focus(); await knowledge.keyboard.press("Tab"); assert.equal(await knowledge.evaluate(() => document.activeElement?.id), "input-kb-id");
  await assertVisibleFocus(knowledge);
  const knowledgeIds = await knowledge.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id)); const knowledgeTestIds = await knowledge.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(knowledgeIds).size, knowledgeIds.length); assert.equal(new Set(knowledgeTestIds).size, knowledgeTestIds.length, `duplicate test IDs: ${JSON.stringify(knowledgeTestIds.filter((id, index) => knowledgeTestIds.indexOf(id) !== index))}`);
  await knowledge.addScriptTag({ content: axe.source }); assert.deepEqual(await knowledge.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="input-kb-name"]')?.closest("div[class*=rounded]"), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await kbName.fill("Smoke KB");
  await knowledge.getByTestId("select-kb-mode").selectOption("all");
  await assertTextZoom(knowledge, kbName, knowledge.getByTestId("button-submit-kb"));
  console.log(JSON.stringify({ chromium: "pass", surface: "knowledge", labeled: true, target44: true, tab: true, uniqueIds: true, uniqueTestIds: true }));

  const pipeline = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await pipeline.route("**/api/**", (route) => { const url = route.request().url(); return route.fulfill({ contentType: "application/json", body: JSON.stringify(url.includes("/api/pipeline/status") ? { config: { overrides: {} }, state: { round_status: "idle" }, summary: { status: "failed", successful_stages: 0, failed_stages: 2, stopped_stages: 0, latest_failure: { task_id: "catalog-failed", stage: "catalog", error_count: 1, first_error_code: "SMOKE", summary: "Catalog failed" } }, stages: [{ step: "catalog", status: "failed", tasks: [{ task_id: "catalog-failed", status: "failed", error_count: 1, first_error_code: "SMOKE", first_error_summary: "Catalog failed", failed_items: 1 }], failures: [{ task_id: "catalog-failed", first_error_code: "SMOKE", first_error_summary: "Catalog failed" }] }, { step: "chunk_generation", status: "failed", tasks: [{ task_id: "chunk-failed", status: "failed", error_count: 1, first_error_code: "SMOKE", first_error_summary: "Chunk failed", failed_items: 1 }], failures: [{ task_id: "chunk-failed", first_error_code: "SMOKE", first_error_summary: "Chunk failed" }] }] } : url.includes("/api/scheduled-tasks") ? { tasks: [{ name: "Scheduled Collection", type: "scheduled", interval: "daily at 02:00", enabled: true, params: {} }] } : fixture(url)) }); });
  await pipeline.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await pipeline.getByTestId("tab-pipeline-baton").click();
  for (const id of ["button-refresh-pipeline-baton", "button-start-pipeline-baton", "button-pipeline-latest-failure", "button-pipeline-task-log-catalog-failed", "button-pipeline-failure-log-catalog-failed"]) await assertTarget(pipeline, id);
  const failedOnlyBox = await pipeline.getByTestId("pipeline-failed-only").locator("xpath=parent::label").boundingBox(); assert.ok(failedOnlyBox && failedOnlyBox.width >= 43.9 && failedOnlyBox.height >= 43.9, JSON.stringify(failedOnlyBox));
  await pipeline.getByTestId("button-pipeline-stage-catalog").focus(); await pipeline.keyboard.press("Tab"); await assertVisibleFocus(pipeline);
  const pipelineIds = await pipeline.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id)); const pipelineTestIds = await pipeline.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(pipelineIds).size, pipelineIds.length); assert.equal(new Set(pipelineTestIds).size, pipelineTestIds.length, `duplicate pipeline test IDs: ${JSON.stringify(pipelineTestIds.filter((id, index) => pipelineTestIds.indexOf(id) !== index))}`);
  await assertTextZoom(pipeline, pipeline.getByTestId("button-pipeline-stage-catalog"), pipeline.getByTestId("button-refresh-pipeline-baton"));
  console.log(JSON.stringify({ chromium: "pass", surface: "pipeline-baton", target44: true, tab: true, uniqueIds: true, uniqueTestIds: true, text200: true }));

  const schedule = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await schedule.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/schedule/status") ? { count: 1, jobs: [] } : route.request().url().includes("/api/scheduled-tasks") ? { tasks: [{ name: "Smoke schedule", type: "scheduled", interval: "daily", enabled: true, params: {} }] } : fixture(route.request().url())) }));
  await schedule.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await schedule.getByTestId("tab-scheduled-tasks").click();
  await schedule.getByTestId("button-delete-sched-Smoke schedule").click(); await assertTarget(schedule, "button-cancel-delete-sched-Smoke schedule"); await schedule.getByTestId("button-cancel-delete-sched-Smoke schedule").click();
  await schedule.getByTestId("button-add-scheduled-task").click();
  const form = schedule.getByTestId("form-scheduled-task"); await form.waitFor();
  await schedule.getByTestId("input-sched-name").fill("Smoke schedule");
  for (const id of ["input-sched-name", "select-sched-type", "select-sched-frequency", "input-sched-time", "select-sched-timezone"]) assert.ok(await schedule.getByTestId(id).evaluate((node) => node.labels?.[0]?.textContent?.trim()));
  for (const node of await form.locator("input, select, textarea, button").all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ testId: await node.getAttribute("data-testid"), rect })); }
  await schedule.getByTestId("input-sched-name").focus(); await schedule.keyboard.press("Tab"); assert.equal(await schedule.evaluate(() => document.activeElement?.matches("select")), true);
  await assertVisibleFocus(schedule);
  const scheduleIds = await schedule.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id)); const scheduleTestIds = await schedule.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(scheduleIds).size, scheduleIds.length); assert.equal(new Set(scheduleTestIds).size, scheduleTestIds.length);
  await schedule.addScriptTag({ content: axe.source }); assert.deepEqual(await schedule.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="form-scheduled-task"]'), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await assertTextZoom(schedule, schedule.getByTestId("input-sched-name"), schedule.getByTestId("button-save-sched"));
  console.log(JSON.stringify({ chromium: "pass", surface: "schedule", labeled: true, target44: true, tab: true, uniqueIds: true, uniqueTestIds: true }));

  const fileDetail = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await fileDetail.route("**/api/**", (route) => {
    const url = route.request().url();
    if (route.request().method() === "POST" && url.includes("/api/files/delete")) {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "delete failed" }) });
    }
    const data = url.includes("/api/files/detail") ? { file: { url: "file-smoke", title: "Smoke file", original_filename: "smoke.pdf", source_site: "smoke", content_type: "text/plain", bytes: 12, local_path: "/tmp/smoke.txt", category: "General", summary: "Summary", keywords: ["actuarial"] } }
      : url.includes("/api/files/file-smoke/markdown") ? { markdown: { markdown_content: "text", markdown_source: "manual" } }
      : url.includes("/api/files/file-smoke/chunk-sets") ? { chunk_sets: [] }
      : url.includes("/api/config/llm-providers") ? { providers: ["openai"] }
      : url.includes("/api/config/ai-models") ? { available: { openai: [{ name: "smoke-catalog", types: ["catalog"] }] }, current: { catalog: { provider: "openai", model: "smoke-catalog" } } }
      : url.includes("/api/config/categories") ? { categories: { AI: [] } }
      : url.includes("/api/chunk/profiles") ? { profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }] }
      : fixture(url);
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(data) });
  });
  await fileDetail.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/file-detail?url=file-smoke`, { waitUntil: "domcontentloaded" });
  await fileDetail.getByTestId("button-edit").click();
  for (const id of ["button-ai-explain", "button-download", "button-preview", "button-delete", "button-md-view", "button-md-edit"]) { const rect = await fileDetail.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  const title = fileDetail.getByTestId("input-title"); await title.waitFor();
  for (const id of ["input-title", "input-summary", "input-keywords"]) assert.ok(await fileDetail.getByTestId(id).evaluate((node) => node.labels?.[0]?.textContent?.trim()));
  for (const node of await fileDetail.locator('[data-testid="input-title"], [data-testid="input-summary"], [data-testid="input-keywords"], [data-testid="button-save"], [data-testid="button-cancel"]').all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ testId: await node.getAttribute("data-testid"), rect })); }
  await title.focus(); await fileDetail.keyboard.press("Tab");
  assert.equal(await fileDetail.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.matches("button, input, select, textarea")), true);
  assert.equal(await fileDetail.evaluate(() => { const node = document.activeElement; return !!node && (getComputedStyle(node).outlineStyle !== "none" || getComputedStyle(node).boxShadow !== "none"); }), true);
  await fileDetail.getByTestId("button-toggle-categories").click();
  await assertTarget(fileDetail, "button-cat-AI");
  await fileDetail.getByTestId("button-cancel").click();
  await fileDetail.getByTestId("button-md-edit").click();
  const markdownInput = fileDetail.getByTestId("input-markdown"); await markdownInput.waitFor();
  const markdownLabel = fileDetail.locator('label[for="input-markdown"]'); const markdownLabelBox = await markdownLabel.boundingBox(); assert.ok(markdownLabelBox && markdownLabelBox.width > 1 && markdownLabelBox.height > 1, JSON.stringify(markdownLabelBox));
  await fileDetail.getByTestId("button-md-view").click(); await fileDetail.getByTestId("button-catalog").click();
  const catalogSource = fileDetail.getByTestId("select-catalog-source"); await catalogSource.waitFor();
  assert.ok(await catalogSource.evaluate((node) => node.labels?.[0]?.textContent?.trim()));
  assert.equal(await catalogSource.getAttribute("aria-describedby"), "hint-catalog-source"); assert.ok(await fileDetail.locator("#hint-catalog-source").textContent());
  for (const node of await fileDetail.locator('[data-testid="select-catalog-source"], [data-testid="button-submit-catalog"], [data-testid="select-catalog-source"] ~ * button, [data-testid="select-catalog-source"] ~ label').all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ testId: await node.getAttribute("data-testid"), rect })); }
  const detailIds = await fileDetail.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id)); const detailTestIds = await fileDetail.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(detailIds).size, detailIds.length); assert.equal(new Set(detailTestIds).size, detailTestIds.length);
  await fileDetail.addScriptTag({ content: axe.source }); assert.deepEqual(await fileDetail.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="select-catalog-source"]')?.closest(".space-y-4"), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await assertTextZoom(fileDetail, catalogSource, fileDetail.getByTestId("button-submit-catalog"));
  await fileDetail.evaluate(() => { document.documentElement.style.fontSize = ""; });
  await fileDetail.getByRole("button", { name: "Cancel" }).click();
  await fileDetail.getByTestId("button-delete").click();
  const confirmInput = fileDetail.getByTestId("input-confirm-delete"); await confirmInput.waitFor();
  assert.equal(await confirmInput.evaluate((node) => node.labels?.[0]?.textContent?.trim().length > 0), true);
  for (const id of ["input-confirm-delete", "button-close-delete-modal", "button-cancel-delete", "button-execute-delete"]) await assertTarget(fileDetail, id);
  await confirmInput.fill("confirm delete"); await fileDetail.getByTestId("button-execute-delete").click();
  await fileDetail.locator("#error-confirm-delete").waitFor();
  assert.equal(await fileDetail.getByTestId("button-execute-delete").getAttribute("aria-describedby"), "error-confirm-delete");
  assert.deepEqual(await fileDetail.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="input-confirm-delete"]')?.closest(".space-y-2"), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  console.log(JSON.stringify({ chromium: "pass", surface: "file-detail", labeled: true, described: true, target44: true, tab: true, uniqueIds: true, uniqueTestIds: true }));

  const fileDetailMissing = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await fileDetailMissing.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/files/detail") ? { file: null } : fixture(route.request().url())) }));
  await fileDetailMissing.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/file-detail?url=missing-smoke`, { waitUntil: "domcontentloaded" });
  await fileDetailMissing.getByTestId("link-back-database").waitFor(); await assertTarget(fileDetailMissing, "link-back-database");
  await fileDetailMissing.getByTestId("link-back-database").focus(); await assertVisibleFocus(fileDetailMissing);
  console.log(JSON.stringify({ chromium: "pass", surface: "file-detail-not-found", target44: true, tab: true }));

  const listening = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await listening.route("**/api/**", (route) => { const url = route.request().url(); const exploreFailure = url.includes("/api/web-listening/rules/explore"); const draftValidation = url.includes("/api/web-listening/rules/draft"); return route.fulfill({ status: exploreFailure ? 500 : 200, contentType: "application/json", body: JSON.stringify(exploreFailure ? { detail: "operation failed" } : draftValidation ? { success: false, valid: false, errors: ["draft invalid"] } : fixture(url)) }); });
  await listening.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await listening.getByTestId("button-start-web_listening").click();
  const listeningForm = listening.getByTestId("form-web-listening"); await listeningForm.waitFor();
  assert.equal(await listeningForm.locator("input:not([type=checkbox]), textarea").evaluateAll((nodes) => nodes.every((node) => !!node.labels?.length)), true);
  for (const node of await listeningForm.locator("input:not([type=checkbox]), textarea, button, label:has(input[type=checkbox])").all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ testId: await node.getAttribute("data-testid"), rect })); }
  const listeningUrl = listening.getByTestId("input-web-listening-url"); await listeningUrl.focus(); await listening.keyboard.press("Tab"); assert.equal(await listening.evaluate(() => document.activeElement?.matches("input, textarea, button")), true);
  await assertVisibleFocus(listening);
  await listeningUrl.fill("https://smoke.example"); await listening.getByTestId("textarea-web-listening-goal").fill("Monitor"); await listening.getByTestId("button-web-listening-explore").click(); await listening.locator("#error-web-listening-explore").waitFor(); assert.equal(await listening.getByTestId("button-web-listening-explore").getAttribute("aria-describedby"), "error-web-listening-explore");
  await listening.getByTestId("button-web-listening-draft").click();
  await listening.locator("#error-web-listening-result").waitFor();
  assert.equal(await listening.locator("#error-web-listening-result").getAttribute("role"), "alert");
  assert.equal(await listening.getByTestId("button-web-listening-draft").getAttribute("aria-describedby"), "error-web-listening-result");
  assert.equal(await listening.getByTestId("button-web-listening-explore").getAttribute("aria-describedby"), null);
  for (const id of ["checkbox-web-listening-tool-crawler", "checkbox-web-listening-tool-search", "checkbox-web-listening-content-file", "checkbox-web-listening-content-webpage"]) await listening.getByTestId(id).click();
  assert.equal(await listeningForm.locator("fieldset").evaluateAll((nodes) => nodes.every((node) => node.getAttribute("aria-describedby") === "hint-web-listening-strategy-required")), true);
  assert.ok(await listening.locator("#hint-web-listening-strategy-required").textContent());
  await listening.addScriptTag({ content: axe.source }); assert.deepEqual(await listening.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="form-web-listening"]'), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await assertTextZoom(listening, listeningUrl, listening.getByTestId("button-web-listening-explore"));
  console.log(JSON.stringify({ chromium: "pass", surface: "web-listening", labeled: true, target44: true, tab: true, axe: true, text200: true }));

  const markdown = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await markdown.route("**/api/**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(fixture(route.request().url())) }));
  await markdown.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/settings`, { waitUntil: "domcontentloaded" });
  await markdown.getByTestId("tab-markdown-conversion").click();
  const markdownTab = markdown.getByTestId("markdown-conversion-tab"); await markdownTab.waitFor();
  assert.equal(await markdownTab.locator("input, select").evaluateAll((nodes) => nodes.every((node) => !!node.labels?.length)), true);
  for (const node of await markdownTab.locator("input:not([type=checkbox]), select, button, label:has(input[type=checkbox])").all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ testId: await node.getAttribute("data-testid"), rect })); }
  const markdownSelect = markdown.getByTestId("select-markdown-default-tool"); await markdownSelect.focus(); await markdown.keyboard.press("Tab"); assert.equal(await markdown.evaluate(() => document.activeElement?.matches("input, button")), true);
  await assertVisibleFocus(markdown);
  await markdown.addScriptTag({ content: axe.source }); assert.deepEqual(await markdown.evaluate(async () => (await window.axe.run(document.querySelector('[data-testid="markdown-conversion-tab"]'), { rules: { "color-contrast": { enabled: false } } })).violations), []);
  await assertTextZoom(markdown, markdownSelect, markdown.getByTestId("button-save-markdown-config"));
  console.log(JSON.stringify({ chromium: "pass", surface: "settings-markdown", labeled: true, target44: true, tab: true, axe: true, text200: true }));

  const siteConfig = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await siteConfig.route("**/api/**", (route) => { const url = route.request().url(); const failure = url.includes("/api/web-listening/rules/explore") || url.includes("/api/config/sites/add") || url.includes("/api/collections/run"); const site = { name: "Smoke", url: "https://smoke.example", max_pages: 1, max_depth: 1 }; const data = failure ? { detail: "save failed" } : route.request().method() === "POST" && url.includes("/api/config/sites/import") ? { count: 1, names: ["Smoke"] } : route.request().method() === "GET" && url.includes("/api/config/sites") ? { sites: [site] } : url.includes("/api/config/backups") ? { backups: [] } : fixture(url); return route.fulfill({ status: failure ? 500 : 200, contentType: "application/json", body: JSON.stringify(data) }); });
  await siteConfig.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" });
  await siteConfig.getByTestId("button-start-site_config").click();
  await siteConfig.getByTestId("button-run-task").click(); await siteConfig.locator("#error-task-submit").waitFor();
  assert.equal(await siteConfig.getByTestId("button-run-task").getAttribute("aria-describedby"), "error-task-submit");
  await siteConfig.getByTestId("button-run-site-Smoke").click(); await siteConfig.locator("#error-task-submit").waitFor();
  assert.equal(await siteConfig.getByTestId("button-run-site-Smoke").getAttribute("aria-describedby"), "error-task-submit");
  assert.equal(await siteConfig.getByTestId("button-run-task").getAttribute("aria-describedby"), null);
  await siteConfig.getByTestId("input-import-file").setInputFiles({ name: "sites.yaml", mimeType: "application/x-yaml", buffer: Buffer.from("sites: []") });
  await siteConfig.getByTestId("panel-import-preview").waitFor();
  for (const id of ["radio-mode-merge", "radio-mode-overwrite"]) { const rect = await siteConfig.getByTestId(id).locator("xpath=..").boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  for (const id of ["button-confirm-import", "button-cancel-import"]) await assertTarget(siteConfig, id);
  await siteConfig.getByTestId("button-cancel-import").click();
  for (const id of ["button-toggle-site-Smoke", "button-toggle-backups"]) await assertTarget(siteConfig, id);
  await siteConfig.getByTestId("button-delete-site-Smoke").click();
  for (const id of ["button-confirm-delete-site-Smoke", "button-cancel-delete-site-Smoke"]) await assertTarget(siteConfig, id);
  await siteConfig.getByTestId("button-cancel-delete-site-Smoke").click();
  for (const id of ["button-import-yaml", "button-export-current", "button-download-sample"]) { const rect = await siteConfig.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  await siteConfig.getByTestId("button-add-site").click(); const siteForm = siteConfig.getByTestId("form-site"); await siteForm.waitFor();
  for (const node of await siteForm.locator("input:not([type=checkbox]), textarea, button, label:has(input[type=checkbox])").all()) { const rect = await node.boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ testId: await node.getAttribute("data-testid"), rect })); }
  await siteConfig.getByTestId("input-site-url").focus(); await siteConfig.keyboard.press("Tab"); assert.equal(await siteConfig.evaluate(() => document.activeElement?.matches("input, textarea, button")), true);
  await assertVisibleFocus(siteConfig);
  await siteConfig.getByTestId("input-site-name").fill("Smoke site"); await siteConfig.getByTestId("input-site-url").fill("https://smoke.example"); await siteConfig.getByTestId("input-site-goal").fill("Monitor updates");
  await siteConfig.getByTestId("button-site-explore").click(); await siteConfig.getByTestId("text-site-explore-error").waitFor(); assert.equal(await siteConfig.getByTestId("button-site-explore").getAttribute("aria-describedby"), "error-site-explore");
  await siteConfig.getByTestId("checkbox-site-tool-crawler").click(); assert.equal(await siteForm.locator("fieldset").evaluateAll((nodes) => nodes.every((node) => node.getAttribute("aria-describedby") === "error-site-strategy")), true);
  await siteConfig.getByTestId("checkbox-site-tool-crawler").click(); await siteConfig.getByTestId("checkbox-site-tool-search").click(); await siteConfig.locator("#error-site-search-query").waitFor(); assert.equal(await siteConfig.getByTestId("input-site-queries").getAttribute("aria-describedby"), "error-site-search-query");
  await siteConfig.getByTestId("input-site-queries").fill("site:smoke.example"); await siteConfig.getByTestId("button-save-site").click(); await siteConfig.getByTestId("text-site-save-error").waitFor(); assert.equal(await siteConfig.getByTestId("button-save-site").getAttribute("aria-describedby"), "error-site-save");
  const siteIds = await siteConfig.locator("[id]").evaluateAll((nodes) => nodes.map((node) => node.id)); const siteTestIds = await siteConfig.locator("[data-testid]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-testid")));
  assert.equal(new Set(siteIds).size, siteIds.length); assert.equal(new Set(siteTestIds).size, siteTestIds.length); assert.equal(await siteConfig.locator('[tabindex]:not([tabindex="-1"])').evaluateAll((nodes) => nodes.every((node) => getComputedStyle(node).display !== "none" && getComputedStyle(node).visibility !== "hidden")), true);
  await assertTextZoom(siteConfig, siteConfig.getByTestId("input-site-url"), siteConfig.getByTestId("button-save-site"));
  console.log(JSON.stringify({ chromium: "pass", surface: "site-config", target44: true, tab: true, uniqueIds: true, uniqueTestIds: true, text200: true }));

  const scheduleError = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await scheduleError.route("**/api/**", (route) => route.fulfill({ status: route.request().url().includes("/api/scheduled-tasks/add") ? 500 : 200, contentType: "application/json", body: JSON.stringify(route.request().url().includes("/api/scheduled-tasks/add") ? { detail: "save failed" } : route.request().url().includes("/api/scheduled-tasks") ? { tasks: [] } : fixture(route.request().url())) }));
  await scheduleError.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/tasks`, { waitUntil: "domcontentloaded" }); await scheduleError.getByTestId("tab-scheduled-tasks").click(); await scheduleError.getByTestId("button-add-scheduled-task").click();
  await scheduleError.getByTestId("input-sched-name").fill("Smoke schedule"); await scheduleError.getByTestId("button-save-sched").click();
  await scheduleError.getByTestId("text-scheduled-error").waitFor(); assert.equal(await scheduleError.getByTestId("button-save-sched").getAttribute("aria-describedby"), "error-scheduled-task");
  console.log(JSON.stringify({ chromium: "pass", surface: "schedule-error", described: true }));

  const knowledgeProfiles = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await knowledgeProfiles.route("**/api/**", (route) => { const url = route.request().url(); return route.fulfill({ status: url.includes("/api/rag/knowledge-bases") && route.request().method() === "POST" ? 500 : 200, contentType: "application/json", body: JSON.stringify(url.includes("/api/chunk/profiles") ? { profiles: [{ profile_id: "p", name: "Default", chunk_size: 512, chunk_overlap: 50 }] } : url.includes("/api/rag/knowledge-bases") && route.request().method() === "POST" ? { detail: "create failed" } : fixture(url)) }); });
  await knowledgeProfiles.goto(`${process.env.SMOKE_URL || "http://127.0.0.1:5173"}/knowledge`, { waitUntil: "domcontentloaded" });
  const createProfile = knowledgeProfiles.getByTestId("button-create-profile"); await createProfile.waitFor({ timeout: 5_000 }); await createProfile.scrollIntoViewIfNeeded(); await createProfile.click(); const profileClose = knowledgeProfiles.getByTestId("button-close-create-profile"); await profileClose.waitFor({ timeout: 5_000 }); const profileCloseBox = await profileClose.boundingBox(); assert.ok(profileCloseBox && profileCloseBox.width >= 43.9 && profileCloseBox.height >= 43.9, JSON.stringify(profileCloseBox)); for (const id of ["button-cancel-profile", "button-submit-profile"]) { const rect = await knowledgeProfiles.getByTestId(id).boundingBox(); assert.ok(rect && rect.width >= 43.9 && rect.height >= 43.9, JSON.stringify({ id, rect })); }
  const profileDelete = knowledgeProfiles.getByTestId("button-delete-profile-0"); await profileDelete.scrollIntoViewIfNeeded(); const profileDeleteBox = await profileDelete.boundingBox(); assert.ok(profileDeleteBox && profileDeleteBox.width >= 43.9 && profileDeleteBox.height >= 43.9, JSON.stringify(profileDeleteBox));
  await profileClose.click();
  await knowledgeProfiles.getByTestId("button-create-kb").click();
  await knowledgeProfiles.getByTestId("input-kb-name").fill("Smoke KB");
  await knowledgeProfiles.getByTestId("select-kb-mode").selectOption("all");
  const createKb = knowledgeProfiles.getByTestId("button-submit-kb");
  await createKb.waitFor({ state: "visible" });
  assert.equal(await createKb.isDisabled(), false, "all-mode create KB action should enable after a name is supplied");
  await createKb.click();
  await knowledgeProfiles.getByTestId("alert-kb-action-error").waitFor();
  assert.equal(await createKb.getAttribute("aria-describedby"), "error-kb-action");
  console.log(JSON.stringify({ chromium: "pass", surface: "knowledge-profile-and-error", target44: true, described: true }));
} finally { await browser.close(); }

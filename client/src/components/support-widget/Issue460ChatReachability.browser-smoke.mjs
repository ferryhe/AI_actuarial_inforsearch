import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const evidenceDir = process.env.SMOKE_EVIDENCE_DIR || "reports/issue-460/browser/review-fix";
const executablePath = process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const outcomes = [];
const overlayFlows = [];
const modalFlows = [];
const fileDetailModalFlows = [];
const kb = { kb_id: "kb-menu-smoke", name: "Synthetic menu knowledge base", usable: true, availability: "ready" };
const permissions = ["stats.read", "files.read", "files.delete", "files.download", "chat.view", "chat.conversations", "catalog.read", "catalog.write", "tasks.view", "tasks.run", "config.read"];
const syntheticFile = {
  url: "synthetic://issue460/file-1",
  title: "Synthetic overlay smoke file",
  original_filename: "overlay-smoke.pdf",
  source_site: "Synthetic source",
  source_key: "synthetic",
  source_name_en: "Synthetic source",
  source_name_zh: "合成来源",
  content_type: "application/pdf",
  first_seen: "2026-01-01T00:00:00Z",
  last_seen: "2026-01-02T00:00:00Z",
  category: "Smoke test",
  keywords: [],
  summary: "Synthetic test record",
  has_markdown: true,
  markdown_source: "synthetic",
  bytes: 1024,
  local_path: "C:/synthetic/overlay-smoke.pdf",
  deleted_at: null,
};

async function assertHitTarget(page, locator, testId, width, height = 844) {
  await locator.waitFor({ state: "visible" });
  await locator.click({ trial: true, timeout: 1200 });
  const box = await locator.boundingBox();
  assert.ok(box && box.x + box.width / 2 >= 0 && box.y + box.height / 2 >= 0 &&
    box.x + box.width / 2 <= width && box.y + box.height / 2 <= height,
  `${testId} center outside viewport at ${width}px: ${JSON.stringify(box)}`);
  const hit = await page.evaluate(({ x, y, id }) => {
    const element = document.elementFromPoint(x, y);
    return {
      element: element?.tagName.toLowerCase() || null,
      control: element?.closest(`[data-testid="${id}"]`)?.getAttribute("data-testid") || null,
    };
  }, { x: box.x + box.width / 2, y: box.y + box.height / 2, id: testId });
  assert.equal(hit.control, testId, `${testId} was covered at ${width}px: ${JSON.stringify({ hit, box })}`);
  return { box, hit };
}

async function captureHitTarget(page, locator, testId, width) {
  try {
    return { status: "PASS", ...(await assertHitTarget(page, locator, testId, width)) };
  } catch (error) {
    const box = await locator.boundingBox().catch(() => null);
    const hit = box && await page.evaluate(({ x, y, id }) => {
      const element = document.elementFromPoint(x, y);
      return {
        element: element?.tagName.toLowerCase() || null,
        control: element?.closest(`[data-testid="${id}"]`)?.getAttribute("data-testid") || null,
      };
    }, { x: box.x + box.width / 2, y: box.y + box.height / 2, id: testId }).catch(() => null);
    return { status: "FAIL", error: String(error), box, hit };
  }
}

async function probeVerticalEdges(page, locator, testId) {
  const box = await locator.boundingBox();
  assert.ok(box, `${testId} must have a measurable rectangle`);
  const samples = [];
  for (const [edge, y] of [["top-inner", 2], ["bottom-inner", box.height - 2]]) {
    await locator.click({ trial: true, position: { x: box.width / 2, y } });
    const hit = await page.evaluate(({ x, y: pointY, id }) => {
      const element = document.elementFromPoint(x, pointY);
      return {
        element: element?.tagName.toLowerCase() || null,
        control: element?.closest(`[data-testid="${id}"]`)?.getAttribute("data-testid") || null,
      };
    }, { x: box.x + box.width / 2, y: box.y + y, id: testId });
    assert.equal(hit.control, testId, `${testId} ${edge} was intercepted: ${JSON.stringify({ box, hit })}`);
    samples.push({ edge, point: { x: box.x + box.width / 2, y: box.y + y }, hit });
  }
  return { box, samples };
}

async function installDialogApiMocks(page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/support/capabilities") return route.fulfill({ json: { feedback_enabled: true, assistant_enabled: false } });
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { data: { require_auth: true, authenticated: true, user: { id: 1, email: "smoke@example.test", role: "admin" }, permissions } } });
    if (url.pathname === "/api/files/detail") return route.fulfill({ json: { file: syntheticFile } });
    if (url.pathname === "/api/files" || url.pathname.startsWith("/api/files?")) return route.fulfill({ json: { files: [syntheticFile], total: 1, limit: 50, offset: 0 } });
    if (url.pathname === "/api/config/search-engines") return route.fulfill({ json: { engines: [] } });
    if (url.pathname === "/api/config/llm-providers") return route.fulfill({ json: { providers: [{ name: "synthetic", status: "active" }], known: { synthetic: { display_name: "Synthetic" } } } });
    if (url.pathname === "/api/config/ai-models") return route.fulfill({ json: { available: { synthetic: [{ name: "synthetic-catalog", display_name: "Synthetic Catalog", types: ["catalog"] }] }, current: { catalog: { provider: "synthetic", model: "synthetic-catalog" } } } });
    if (url.pathname === "/api/config/markdown-conversion") return route.fulfill({ json: { tools: [{ name: "local", provider: "local", displayName: "Local" }] } });
    if (url.pathname === "/api/config/categories") return route.fulfill({ json: { categories: {} } });
    if (url.pathname === "/api/chunk/profiles") return route.fulfill({ json: { profiles: [] } });
    if (url.pathname === "/api/sources") return route.fulfill({ json: { source_options: [] } });
    if (url.pathname.startsWith("/api/categories")) return route.fulfill({ json: { categories: [] } });
    if (url.pathname.endsWith("/markdown")) return route.fulfill({ json: { markdown: { markdown_content: "Synthetic markdown" } } });
    if (url.pathname.endsWith("/chunk-sets")) return route.fulfill({ json: { chunk_sets: [] } });
    return route.fulfill({ json: {} });
  });
}

await mkdir(evidenceDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
try {
  const lazyFailurePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await installDialogApiMocks(lazyFailurePage);
  let lazyChatQueryPosts = 0;
  await lazyFailurePage.route("**/api/chat/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/chat/conversations" && request.method() === "POST") return route.fulfill({ json: { success: true, data: { conversation_id: "lazy-failure-chat-smoke" } } });
    if (url.pathname === "/api/chat/conversations") return route.fulfill({ json: { success: true, data: { conversations: [] } } });
    if (url.pathname === "/api/chat/query" && request.method() === "POST") {
      lazyChatQueryPosts += 1;
      return route.fulfill({ json: { success: true, data: { conversation_id: "lazy-failure-chat-smoke", response: "Synthetic Chat survived feedback module failure", citations: [] } } });
    }
    return route.fulfill({ json: {} });
  });
  let failedFeedbackChunk = false;
  await lazyFailurePage.route("**/src/features/feedback/FeedbackForm.tsx*", async (route) => {
    if (!failedFeedbackChunk) { failedFeedbackChunk = true; await route.abort("failed"); }
    else await route.continue();
  });
  await lazyFailurePage.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  const lazyChatInput = lazyFailurePage.getByTestId("input-chat-message");
  await lazyChatInput.waitFor({ state: "visible" });
  const lazyChatSend = lazyFailurePage.getByTestId("button-send-message");
  await lazyFailurePage.getByTestId("support-widget-trigger").click();
  await lazyFailurePage.getByRole("alert").waitFor({ state: "visible" });
  assert.equal(await lazyChatInput.isVisible(), true, "a failed feedback chunk must not remove Chat input");
  assert.equal(await lazyChatSend.isVisible(), true, "a failed feedback chunk must not remove Chat send");
  await lazyChatInput.fill("Chat remains usable after feedback chunk failure");
  const lazyChatResponse = lazyFailurePage.waitForResponse((response) => response.url().includes("/api/chat/query") && response.request().method() === "POST");
  await lazyChatSend.click();
  assert.equal((await lazyChatResponse).status(), 200);
  assert.equal(lazyChatQueryPosts, 1);
  await lazyFailurePage.screenshot({ path: path.join(evidenceDir, "feedback-lazy-chunk-failure-localized-390x844.png"), fullPage: false });
  await lazyFailurePage.getByRole("button", { name: "Try again" }).click();
  await lazyFailurePage.locator("#feedback-panel").waitFor({ state: "visible" });
  assert.equal(await lazyChatInput.isVisible(), true, "Chat remains available after feedback module retry");
  const lazyFailureRecovery = { failedChunkLocalized: true, chatInputRemainsVisible: true, chatSendRemainsVisible: true, mockedChatSendAfterFailure: true, mockedChatQueryPosts: lazyChatQueryPosts, retryReloadsModule: await lazyFailurePage.locator("#feedback-panel").isVisible(), providerCalls: 0, screenshot: "feedback-lazy-chunk-failure-localized-390x844.png" };
  await lazyFailurePage.close();

  for (const width of [390, 1024]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    const requests = [];
    const feedbackPosts = [];
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      requests.push({ method: request.method(), path: `${url.pathname}${url.search}` });
      if (url.pathname === "/api/support/capabilities") {
        return route.fulfill({ json: { feedback_enabled: true, assistant_enabled: false } });
      }
      if (url.pathname === "/api/feedback" && request.method() === "POST") {
        feedbackPosts.push(request.postDataJSON());
        return route.fulfill({ status: 201, json: { feedback_id: `feedback-smoke-${width}`, status: "recorded", created_at: "2026-11-05T00:00:00Z" } });
      }
      if (url.pathname === "/api/auth/me") {
        return route.fulfill({ json: { data: { require_auth: true, authenticated: true, user: { id: 1, email: "smoke@example.test", role: "admin" }, permissions } } });
      }
      if (url.pathname === "/api/chat/knowledge-bases") {
        return route.fulfill({ json: { success: true, data: { knowledge_bases: [kb] } } });
      }
      if (url.pathname === "/api/categories") return route.fulfill({ json: { categories: [] } });
      if (url.pathname === "/api/chat/available-documents") {
        return route.fulfill({ json: { success: true, data: { items: [], total: 0, limit: 50, offset: 0 } } });
      }
      if (url.pathname === "/api/chat/conversations" && request.method() === "POST") {
        return route.fulfill({ json: { success: true, data: { conversation_id: "conv-menu-smoke" } } });
      }
      if (url.pathname === "/api/chat/conversations") {
        return route.fulfill({ json: { success: true, data: { conversations: [{ id: "conv-menu-smoke", title: "Synthetic drawer conversation", created_at: "2026-01-01T00:00:00Z" }] } } });
      }
      if (url.pathname === "/api/chat/conversations/conv-menu-smoke") {
        return route.fulfill({ json: { success: true, data: { conversation: { id: "conv-menu-smoke", title: "Synthetic drawer conversation" }, messages: [] } } });
      }
      if (url.pathname === "/api/chat/query" && request.method() === "POST") {
        return route.fulfill({ json: { success: true, data: { conversation_id: "smoke", response: "Synthetic Chat acceptance reply", citations: [] } } });
      }
      return route.fulfill({ json: {} });
    });

    await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
    const chatInput = page.getByTestId("input-chat-message");
    const chatSend = page.getByTestId("button-send-message");
    await chatInput.waitFor({ state: "visible" });
    await chatInput.fill(`R1 synthetic reachability ${width}`);
    await chatSend.waitFor({ state: "visible" });
    const supportTrigger = page.getByTestId("support-widget-trigger");
    await supportTrigger.click();
    const feedbackSubmit = page.getByRole("button", { name: "Send feedback" });
    await feedbackSubmit.waitFor({ state: "visible" });
    const feedbackInput = page.getByLabel("Your feedback");
    const feedbackText = `Synthetic feedback survives Chat menu selection ${width}`;
    await feedbackInput.fill(feedbackText);

    assert.equal(await chatInput.isVisible(), true);
    assert.equal(await chatSend.isVisible(), true);
    const chatControls = {};
    chatControls.input = await assertHitTarget(page, chatInput, "input-chat-message", width);
    chatControls.send = await assertHitTarget(page, chatSend, "button-send-message", width);
    const modeSelector = page.getByTestId("button-mode-selector");
    chatControls.modeSelector = await assertHitTarget(page, modeSelector, "button-mode-selector", width);
    await modeSelector.click();
    const summaryOption = page.getByTestId("mode-option-summary");
    chatControls.modeSummary = await assertHitTarget(page, summaryOption, "mode-option-summary", width);
    await summaryOption.click();
    assert.match(await modeSelector.innerText(), /Summary/i, `mode selection did not apply at ${width}px`);

    const ragAgentic = page.getByTestId("rag-mode-option-agentic");
    chatControls.ragAgentic = await assertHitTarget(page, ragAgentic, "rag-mode-option-agentic", width);
    await ragAgentic.click();
    assert.match(await ragAgentic.getAttribute("class"), /bg-card text-foreground/, `Agentic RAG was not selected at ${width}px`);
    const ragStandard = page.getByTestId("rag-mode-option-standard");
    chatControls.ragStandard = await assertHitTarget(page, ragStandard, "rag-mode-option-standard", width);
    await ragStandard.click();
    assert.match(await ragStandard.getAttribute("class"), /bg-card text-foreground/, `Standard RAG was not selected at ${width}px`);

    const kbSelector = page.getByTestId("button-kb-selector");
    chatControls.kbSelector = await assertHitTarget(page, kbSelector, "button-kb-selector", width);
    await kbSelector.click();
    const kbOption = page.getByTestId(`kb-option-${kb.kb_id}`);
    chatControls.kbOption = await assertHitTarget(page, kbOption, `kb-option-${kb.kb_id}`, width);
    await kbOption.click();
    assert.match(await kbSelector.innerText(), /^1 selected$/i, `knowledge base selection did not apply at ${width}px`);
    assert.equal(await feedbackInput.inputValue(), feedbackText, `feedback text was lost at ${width}px`);
    assert.equal(await feedbackSubmit.isVisible(), true, `feedback panel closed at ${width}px`);

    const feedbackSubmitControl = page.getByTestId("feedback-submit");
    const feedbackSubmitHit = await assertHitTarget(page, feedbackSubmitControl, "feedback-submit", width);
    const feedbackResponse = page.waitForResponse((response) => response.url().includes("/api/feedback") && response.request().method() === "POST");
    await feedbackSubmitControl.click();
    assert.equal((await feedbackResponse).status(), 201);
    await page.getByRole("status").waitFor({ state: "visible" });
    assert.equal(feedbackPosts.length, 1, `feedback submit should send once at ${width}px`);

    const finalBoxes = await Promise.all([chatInput.boundingBox(), chatSend.boundingBox(), page.locator("#feedback-panel").boundingBox()]);
    const [inputBox, sendBox, feedbackBox] = finalBoxes;
    assert.ok(inputBox && sendBox && feedbackBox, `missing controls at ${width}px`);
    const inputHit = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.tagName.toLowerCase() || null,
      { x: inputBox.x + inputBox.width / 2, y: inputBox.y + inputBox.height / 2 });
    assert.equal(inputHit, "textarea", `unexpected input hit target at ${width}px`);
    const chatQueryResponse = page.waitForResponse((response) => response.url().includes("/api/chat/query") && response.request().method() === "POST");
    await chatSend.click();
    assert.equal((await chatQueryResponse).status(), 200);
    assert.equal(requests.filter((request) => request.method === "POST" && request.path.startsWith("/api/chat/query")).length, 1);
    await page.screenshot({ path: path.join(evidenceDir, `chat-${width}x844.png`), fullPage: false });
    outcomes.push({
      viewport: `${width}x844`, route: "/chat", feedback_open: true,
      chat_input_visible: true, chat_send_visible: true, chat_input_hit_target: inputHit,
      chat_controls_visible_and_hit: chatControls,
      selected_mode: "summary", selected_rag_mode: "standard", selected_knowledge_base: kb.kb_id,
      feedback_text_preserved: await feedbackInput.inputValue() === feedbackText,
      feedback_panel_remains_open: await feedbackSubmit.isVisible(),
      actual_feedback_submit_clicked: true,
      feedback_submit_hit: feedbackSubmitHit,
      feedback_request_id: feedbackPosts[0].client_request_id,
      feedback_receipt: await page.getByRole("status").innerText(),
      feedback_submit_did_not_intercept_chat: true, actual_chat_send_clicked: true,
      mocked_chat_query_posts: 1, real_provider_calls: 0,
      chat_input: inputBox, chat_send: sendBox, feedback_panel: feedbackBox,
    });

    if (width === 390) {
      const chatOpen = page.getByTestId("button-open-chat-sidebar");
      await assertHitTarget(page, chatOpen, "button-open-chat-sidebar", width);
      await chatOpen.click();
      const chatClose = page.getByTestId("button-close-chat-sidebar");
      const closeHit = await assertHitTarget(page, chatClose, "button-close-chat-sidebar", width);
      await page.screenshot({ path: path.join(evidenceDir, "chat-drawer-feedback-open-390x844.png"), fullPage: false });
      const toggleDocs = page.getByTestId("button-toggle-documents-panel");
      const docsHit = await assertHitTarget(page, toggleDocs, "button-toggle-documents-panel", width);
      await toggleDocs.click();
      await page.getByTestId("input-doc-search").waitFor({ state: "visible" });
      await toggleDocs.click();
      const conversation = page.getByTestId("conversation-conv-menu-smoke");
      await conversation.waitFor({ state: "visible" });
      const conversationHit = await assertHitTarget(page, conversation, "conversation-conv-menu-smoke", width);
      await conversation.click();
      await page.waitForFunction(() => document.querySelector('[data-testid="conversation-conv-menu-smoke"]')?.className.includes("bg-primary/10"));
      await chatClose.click();
      await chatClose.waitFor({ state: "hidden" });
      assert.equal(await feedbackSubmit.isVisible(), true, "feedback panel was unmounted by Chat drawer");
      await feedbackInput.fill(`${feedbackText} edited`);
      await feedbackInput.fill(feedbackText);
      assert.equal(await feedbackInput.inputValue(), feedbackText);
      overlayFlows.push({
        case: "feedback-open-then-chat-drawer",
        viewport: "390x844",
        drawer_controls_hit: { close: closeHit.hit, toggle_documents: docsHit.hit, conversation: conversationHit.hit },
        conversation_selected: true,
        drawer_closed_by_real_click: true,
        feedback_panel_remains_open: await feedbackSubmit.isVisible(),
        sentinel_preserved_and_editable: await feedbackInput.inputValue() === feedbackText,
      });

      await chatOpen.click();
      const escapeClose = page.getByTestId("button-close-chat-sidebar");
      await escapeClose.waitFor({ state: "visible" });
      await escapeClose.focus();
      await page.keyboard.press("Escape");
      await escapeClose.waitFor({ state: "hidden" });
      assert.equal(await feedbackSubmit.isVisible(), true, "Escape inside the Chat drawer must leave feedback open");
      assert.equal(await feedbackInput.inputValue(), feedbackText, "Chat drawer Escape must preserve feedback text");
      overlayFlows.push({
        case: "chat-drawer-escape-does-not-close-feedback",
        viewport: "390x844",
        focus_before_escape: "button-close-chat-sidebar",
        chat_drawer_closed: true,
        feedback_panel_remains_open: await feedbackSubmit.isVisible(),
        feedback_text_preserved: await feedbackInput.inputValue() === feedbackText,
        focus_after_escape: await page.evaluate(() => document.activeElement?.getAttribute("data-testid")),
      });

      await supportTrigger.click();
      await feedbackSubmit.waitFor({ state: "hidden" });
      await chatOpen.click();
      await chatClose.waitFor({ state: "visible" });
      const triggerBox = await supportTrigger.boundingBox();
      assert.ok(triggerBox, "support trigger should remain measurable behind Chat drawer");
      const triggerHit = await page.evaluate(({ x, y }) => {
        const element = document.elementFromPoint(x, y);
        return { element: element?.tagName.toLowerCase() || null, control: element?.getAttribute("data-testid") || element?.closest("[data-testid]")?.getAttribute("data-testid") || null };
      }, { x: triggerBox.x + triggerBox.width / 2, y: triggerBox.y + triggerBox.height / 2 });
      assert.equal(triggerHit.control, "chat-sidebar-backdrop", `Chat drawer did not intercept support trigger: ${JSON.stringify(triggerHit)}`);
      await page.mouse.click(triggerBox.x + triggerBox.width / 2, triggerBox.y + triggerBox.height / 2);
      await chatClose.waitFor({ state: "hidden" });
      assert.equal(await supportTrigger.getAttribute("aria-expanded"), "false", "covered support trigger must not open from the backdrop click");
      await supportTrigger.click();
      await feedbackInput.waitFor({ state: "visible" });
      const drawerFirstSentinel = "drawer-first synthetic feedback";
      await feedbackInput.fill(drawerFirstSentinel);
      assert.equal(await feedbackInput.inputValue(), drawerFirstSentinel);
      overlayFlows.push({
        case: "chat-drawer-first",
        viewport: "390x844",
        support_trigger_bounds: triggerBox,
        element_from_point: triggerHit,
        backdrop_closed_chat_drawer: true,
        covered_trigger_did_not_open_feedback: true,
        feedback_opened_and_edited_after_drawer: await feedbackSubmit.isVisible() && await feedbackInput.inputValue() === drawerFirstSentinel,
      });

      const openLayoutSidebar = page.getByTestId("open-sidebar");
      const layoutOpenHit = await assertHitTarget(page, openLayoutSidebar, "open-sidebar", width);
      await openLayoutSidebar.click();
      const knowledgeNav = page.getByTestId("mobile-nav-knowledge");
      await knowledgeNav.waitFor({ state: "visible" });
      await page.screenshot({ path: path.join(evidenceDir, "layout-sidebar-feedback-open-390x844.png"), fullPage: false });
      const knowledgeHit = await assertHitTarget(page, knowledgeNav, "mobile-nav-knowledge", width);
      await knowledgeNav.click();
      await page.waitForFunction(() => window.location.pathname === "/knowledge");
      assert.equal(await feedbackInput.inputValue(), drawerFirstSentinel, "Layout navigation must preserve feedback draft");
      await page.getByTestId("close-sidebar").click();
      await page.getByTestId("close-sidebar").waitFor({ state: "hidden" });
      assert.equal(await feedbackSubmit.isVisible(), true, "feedback panel must remain mounted after Layout navigation");
      await feedbackInput.fill(`${drawerFirstSentinel} edited`);
      await feedbackInput.fill(drawerFirstSentinel);
      assert.equal(await feedbackInput.inputValue(), drawerFirstSentinel);
      overlayFlows.push({
        case: "feedback-open-then-layout-mobile-navigation",
        viewport: "390x844",
        open_sidebar_hit: layoutOpenHit.hit,
        knowledge_nav_hit: knowledgeHit.hit,
        actual_route: new URL(page.url()).pathname,
        sidebar_closed_by_real_click: true,
        feedback_panel_remains_open: await feedbackSubmit.isVisible(),
        sentinel_preserved_and_editable: await feedbackInput.inputValue() === drawerFirstSentinel,
      });
    }
    await page.close();
  }

  const keyboardPage = await browser.newPage({ viewport: { width: 390, height: 500 } });
  await installDialogApiMocks(keyboardPage);
  const keyboardFeedbackPosts = [];
  await keyboardPage.route("**/api/feedback", async (route) => {
    keyboardFeedbackPosts.push(route.request().postDataJSON());
    return route.fulfill({ status: 201, json: { feedback_id: "feedback-keyboard-sim", status: "recorded", created_at: "2026-11-05T00:00:00Z" } });
  });
  await keyboardPage.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  const keyboardChatInput = keyboardPage.getByTestId("input-chat-message");
  await keyboardChatInput.waitFor({ state: "visible" });
  await keyboardChatInput.fill(Array.from({ length: 18 }, (_, index) => `Synthetic keyboard height line ${index + 1}`).join("\n"));
  assert.equal(await keyboardChatInput.evaluate((element) => getComputedStyle(element).height), "120px");
  await keyboardPage.getByTestId("support-widget-trigger").click();
  await keyboardPage.locator("#feedback-panel").waitFor({ state: "visible" });
  const keyboardFeedbackInput = keyboardPage.getByLabel("Your feedback");
  await keyboardFeedbackInput.fill("Keyboard available-height submission simulation");
  const keyboardForm = keyboardPage.locator("#feedback-panel form");
  const keyboardFeedbackSubmit = keyboardPage.getByTestId("feedback-submit");
  const keyboardScrollTopBefore = await keyboardForm.evaluate((element) => element.scrollTop);
  await keyboardFeedbackSubmit.scrollIntoViewIfNeeded();
  const keyboardFormScrollTop = await keyboardForm.evaluate((element) => element.scrollTop);
  assert.ok(keyboardFormScrollTop > 0, "390x500 simulation should require scrolling the feedback form to reach submit");
  const keyboardPanelBox = await keyboardPage.locator("#feedback-panel").boundingBox();
  assert.ok(keyboardPanelBox && keyboardPanelBox.y >= 16 && keyboardPanelBox.y + keyboardPanelBox.height <= 500,
    `feedback panel must stay in the simulated keyboard viewport: ${JSON.stringify(keyboardPanelBox)}`);
  const keyboardSubmitHit = await assertHitTarget(keyboardPage, keyboardFeedbackSubmit, "feedback-submit", 390, 500);
  const keyboardSubmitEdgeHits = await probeVerticalEdges(keyboardPage, keyboardFeedbackSubmit, "feedback-submit");
  const keyboardModeSelector = keyboardPage.getByTestId("button-mode-selector");
  const keyboardModeEdgeHits = await probeVerticalEdges(keyboardPage, keyboardModeSelector, "button-mode-selector");
  const keyboardModePanelGap = keyboardModeEdgeHits.box.y - (keyboardPanelBox.y + keyboardPanelBox.height);
  await keyboardPage.screenshot({ path: path.join(evidenceDir, "keyboard-available-height-submit-ready-390x500.png"), fullPage: false });
  const keyboardFeedbackResponse = keyboardPage.waitForResponse((response) => response.url().includes("/api/feedback") && response.request().method() === "POST");
  await keyboardFeedbackSubmit.click();
  assert.equal((await keyboardFeedbackResponse).status(), 201);
  const keyboardReceiptStatus = keyboardPage.getByRole("status");
  await keyboardReceiptStatus.waitFor({ state: "visible" });
  await keyboardReceiptStatus.scrollIntoViewIfNeeded();
  const keyboardReceiptBox = await keyboardReceiptStatus.boundingBox();
  const keyboardFormBoxAfterReceipt = await keyboardForm.boundingBox();
  assert.ok(keyboardReceiptBox && keyboardFormBoxAfterReceipt && keyboardReceiptBox.y >= keyboardFormBoxAfterReceipt.y &&
    keyboardReceiptBox.y + keyboardReceiptBox.height <= keyboardFormBoxAfterReceipt.y + keyboardFormBoxAfterReceipt.height,
  `receipt must be visible inside the scrollable form: ${JSON.stringify({ keyboardReceiptBox, keyboardFormBoxAfterReceipt })}`);
  assert.equal(keyboardFeedbackPosts.length, 1);
  await keyboardPage.screenshot({ path: path.join(evidenceDir, "keyboard-available-height-simulation-390x500.png"), fullPage: false });
  const keyboardCase = {
    scenario: "keyboard_available_height_simulation",
    viewport: "390x500",
    route: "/chat",
    actualChatComposerHeight: "120px",
    chatComposerBox: await keyboardChatInput.boundingBox(),
    feedbackPanel: keyboardPanelBox,
    feedbackFormScrollTopBefore: keyboardScrollTopBefore,
    feedbackFormScrollTopAfter: keyboardFormScrollTop,
    feedbackFormScrollTopAfterReceipt: await keyboardForm.evaluate((element) => element.scrollTop),
    feedbackFormScrolled: keyboardFormScrollTop > keyboardScrollTopBefore,
    feedbackSubmitHit: keyboardSubmitHit,
    feedbackSubmitEdgeHits: keyboardSubmitEdgeHits,
    chatModeEdgeHits: keyboardModeEdgeHits,
    feedbackPanelToModeSelectorGap: keyboardModePanelGap,
    actualFeedbackSubmitClicked: true,
    receiptBox: keyboardReceiptBox,
    receiptVisibleInsideForm: true,
    feedbackRequestId: keyboardFeedbackPosts[0].client_request_id,
    feedbackReceipt: await keyboardPage.getByRole("status").innerText(),
    providerCalls: 0,
    submitReadyScreenshot: "keyboard-available-height-submit-ready-390x500.png",
    screenshot: "keyboard-available-height-simulation-390x500.png",
  };
  await keyboardPage.close();

  for (const width of [390, 1024]) {
    for (const scenario of ["database", "file-detail"]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    await installDialogApiMocks(page);
    const route = scenario === "database" ? "/database" : "/file-detail?file_id=1";
    await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });
    const trigger = page.getByTestId("support-widget-trigger");
    await trigger.waitFor({ state: "visible" });
    if (scenario === "database") {
      const rowSelect = page.getByTestId(width < 768 ? "checkbox-select-mobile-0" : "checkbox-select-0");
      await rowSelect.waitFor({ state: "visible" });
      await rowSelect.click();
      const bulkDelete = page.getByTestId("button-bulk-delete");
      await bulkDelete.waitFor({ state: "visible" });
      assert.equal(await bulkDelete.isDisabled(), false, "synthetic selected file should enable bulk delete");
      await trigger.click();
      const form = page.locator("#feedback-panel");
      await form.waitFor({ state: "visible" });
      const feedbackInput = page.getByLabel("Your feedback");
      const sentinel = "Database modal overlay sentinel";
      await feedbackInput.fill(sentinel);
      await bulkDelete.click();
    } else {
      await page.getByTestId("button-delete").waitFor({ state: "visible" });
      await trigger.click();
      const form = page.locator("#feedback-panel");
      await form.waitFor({ state: "visible" });
      const feedbackInput = page.getByLabel("Your feedback");
      const sentinel = "File detail modal overlay sentinel";
      await feedbackInput.fill(sentinel);
      await page.getByTestId("button-delete").click();
    }

    const modal = page.getByTestId("modal-confirm-delete");
    await modal.waitFor({ state: "visible" });
    await page.waitForFunction((element) => Number(getComputedStyle(element).opacity) >= 0.99, await modal.elementHandle());
    await page.screenshot({ path: path.join(evidenceDir, `${scenario}-${width}x844-dialog-open.png`), fullPage: false });
    const modalBox = await modal.boundingBox();
    const feedbackBox = await page.locator("#feedback-panel").boundingBox();
    const headerClose = modal.getByTestId("button-close-delete-modal");
    const headerCloseTarget = await captureHitTarget(page, headerClose, "button-close-delete-modal", width);
    await modal.getByTestId("input-confirm-delete").fill("confirm delete");
    const confirmButton = modal.getByTestId("button-execute-delete");
    assert.equal(await confirmButton.isEnabled(), true, `${scenario} synthetic confirmation should enable the confirm control`);
    const confirmTarget = await captureHitTarget(page, confirmButton, "button-execute-delete", width);
    const cancel = page.getByTestId("button-cancel-delete");
    const cancelBox = await cancel.boundingBox();
    assert.ok(cancelBox, `${scenario} cancel button should be measurable`);
    const cancelTarget = await captureHitTarget(page, cancel, "button-cancel-delete", width);
    await cancel.click();
    await modal.waitFor({ state: "hidden" });
    const feedbackInput = page.getByLabel("Your feedback");
    const expectedSentinel = scenario === "database" ? "Database modal overlay sentinel" : "File detail modal overlay sentinel";
    const feedbackDraftPreserved = await feedbackInput.count() > 0 && await feedbackInput.inputValue() === expectedSentinel;
    modalFlows.push({
      route,
      viewport: `${width}x844`,
      modal_box: modalBox,
      feedback_panel_box: feedbackBox,
      header_close_hit_and_trial: headerCloseTarget,
      confirm_hit_and_trial_only: confirmTarget,
      confirm_action_submitted: false,
      cancel_hit_and_trial: cancelTarget,
      actual_cancel_click: true,
      cancel_hit_ok: cancelTarget.status === "PASS",
      modal_closed_by_cancel_while_feedback_open: await modal.count() === 0,
      feedback_draft_preserved: feedbackDraftPreserved,
    });
    await page.close();
    }
  }

  for (const width of [390, 1024]) {
    for (const scenario of ["catalog", "chunk"]) {
      const page = await browser.newPage({ viewport: { width, height: 844 } });
      await installDialogApiMocks(page);
      await page.goto(`${baseUrl}/file-detail?file_id=1`, { waitUntil: "domcontentloaded" });
      const trigger = page.getByTestId("support-widget-trigger");
      await trigger.waitFor({ state: "visible" });
      await trigger.click();
      const feedbackInput = page.getByLabel("Your feedback");
      await feedbackInput.waitFor({ state: "visible" });
      const sentinel = `FileDetail ${scenario} modal sentinel ${width}`;
      await feedbackInput.fill(sentinel);

      if (scenario === "catalog") {
        const openCatalog = page.getByTestId("button-catalog");
        await openCatalog.waitFor({ state: "visible" });
        await openCatalog.click();
      } else {
        const openChunk = page.getByTestId("button-modify-chunk");
        await openChunk.waitFor({ state: "visible" });
        assert.equal(await openChunk.isDisabled(), false, "synthetic markdown/task permission should enable the chunk modal");
        await openChunk.click();
      }

      const modal = page.getByTestId("file-detail-modal-surface");
      await modal.waitFor({ state: "visible" });
      await page.waitForFunction((element) => Number(getComputedStyle(element).opacity) >= 0.99, await modal.elementHandle());
      await page.screenshot({ path: path.join(evidenceDir, `file-detail-${scenario}-${width}x844-dialog-open.png`), fullPage: false });
      const title = scenario === "catalog" ? "Catalog This File" : "Chunk & Embedding (This File)";
      await page.getByRole("heading", { name: title }).waitFor({ state: "visible" });
      const submit = page.getByTestId(scenario === "catalog" ? "button-submit-catalog" : "button-submit-chunk");
      assert.equal(await submit.isEnabled(), true, `${scenario} synthetic submit control should be enabled for hit testing`);
      const submitHit = await captureHitTarget(page, submit, scenario === "catalog" ? "button-submit-catalog" : "button-submit-chunk", width);
      const cancel = page.getByTestId(scenario === "catalog" ? "button-cancel-catalog" : "button-cancel-chunk");
      const cancelHit = await captureHitTarget(page, cancel, scenario === "catalog" ? "button-cancel-catalog" : "button-cancel-chunk", width);
      await cancel.click();
      await modal.waitFor({ state: "hidden" });
      const feedbackPreserved = await feedbackInput.inputValue() === sentinel;
      const flow = {
        route: "/file-detail?file_id=1",
        scenario,
        viewport: `${width}x844`,
        submit_hit_and_trial_only: submitHit,
        submit_action_executed: false,
        cancel_hit_and_trial: cancelHit,
        actual_cancel_click: true,
        modal_closed: await modal.count() === 0,
        feedback_panel_still_open: await page.getByRole("button", { name: "Send feedback" }).isVisible(),
        feedback_sentinel_preserved: feedbackPreserved,
      };
      fileDetailModalFlows.push(flow);
      await page.close();
    }
  }

  const resultPath = process.env.SMOKE_RESULT_PATH || path.join(evidenceDir, "issue460-r1-chat-reachability.json");
  const result = {
    result: modalFlows.every((item) => item.modal_closed_by_cancel_while_feedback_open && item.header_close_hit_and_trial.status === "PASS" && item.confirm_hit_and_trial_only.status === "PASS" && item.cancel_hit_ok) && fileDetailModalFlows.every((item) => item.modal_closed && item.feedback_panel_still_open && item.feedback_sentinel_preserved && item.submit_hit_and_trial_only.status === "PASS" && item.cancel_hit_and_trial.status === "PASS") ? "PASS" : "CONFIRMED_MODAL_COLLISION",
    chatViewports: outcomes.map((item) => item.viewport),
    chatMenuCases: outcomes,
    overlayFlows,
    modalFlows,
    fileDetailModalFlows,
    keyboardAvailableHeightCase: keyboardCase,
    lazyFailureRecovery,
    actualChatSends: outcomes.length,
    realProviderCalls: 0,
  };
  await writeFile(resultPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ ...result, evidence: resultPath }));
  assert.equal(result.result, "PASS", `dialog collision evidence: ${JSON.stringify(modalFlows)}`);
} finally {
  await browser.close();
}

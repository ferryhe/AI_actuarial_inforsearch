import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium, webkit } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const chromePath = process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const sizes = [
  { width: 390, height: 500 },
  { width: 390, height: 400 },
  { width: 844, height: 390 },
  { width: 390, height: 844 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];
const longAnswer = Array.from({ length: 40 }, (_, index) => `Synthetic answer paragraph ${index + 1}.`).join("\n\n");
const citation = { doc_id: "user-guide-en", section_id: "file-details", language: "en", title: "Guide", source_version: "1.0.0", content_hash: "a".repeat(64) };
const browser = process.env.SMOKE_BROWSER === "webkit"
  ? await webkit.launch({ headless: true })
  : await chromium.launch({ executablePath: chromePath, headless: true });

function assistantReply(overrides = {}) {
  return { schema_version: "1.0", stop_reason: overrides.intent === "clarify" ? "clarify" : "finish", intent: "knowledge", answer: longAnswer, citations: [citation], evidence_ids: [], selected_target: null, feedback_draft: null, availability: "available", error_code: null, generation_attempts: 1, embedding_attempts: 0, ...overrides };
}

async function installMocks(page, flags = { assistant_enabled: true, feedback_enabled: false }, plans = [], lang = "en") {
  const assistantRequests = [];
  const chatRequests = [];
  const feedbackRequests = [];
  await page.addInitScript((language) => localStorage.setItem("lang", language), lang);
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { success: true, data: { require_auth: false, authenticated: false, user: null, permissions: ["stats.read", "files.read", "catalog.read", "chat.view", "chat.query", "chat.conversations"] } } });
    if (url.pathname === "/api/support/capabilities") return route.fulfill({ json: flags });
    if (url.pathname === "/api/chat/knowledge-bases") return route.fulfill({ json: { success: true, data: { knowledge_bases: [{ kb_id: "smoke-kb", name: "Smoke KB", availability: "ready", usable: true, serving: true }] } } });
    if (url.pathname === "/api/categories") return route.fulfill({ json: { categories: Array.from({ length: 8 }, (_, index) => `Sample category ${index + 1}`) } });
    if (url.pathname === "/api/chat/available-documents") return route.fulfill({ json: { data: { items: [], total: 0, offset: 0, limit: 50 } } });
    if (url.pathname === "/api/chat/query" && request.method() === "POST") {
      chatRequests.push(request.postDataJSON());
      return route.fulfill({ json: { success: true, data: { conversation_id: "smoke-chat", response: "Synthetic Chat response", citations: [] } } });
    }
    if (url.pathname === "/api/assistant/v1/query" && request.method() === "POST") {
      assistantRequests.push(request.postDataJSON());
      const plan = plans.shift() || {};
      if (plan.delay) await new Promise((resolve) => setTimeout(resolve, plan.delay));
      return route.fulfill({ json: assistantReply(plan.reply) });
    }
    if (url.pathname === "/api/assistant/help/section") return route.fulfill({ json: { ...citation, content: "Current guide section content." } });
    if (url.pathname === "/api/assistant/help") return route.fulfill({ json: { results: [citation] } });
    if (url.pathname === "/api/feedback" && request.method() === "POST") {
      feedbackRequests.push(request.postDataJSON());
      return route.fulfill({ status: 201, json: { feedback_id: `smoke-feedback-${feedbackRequests.length}`, status: "recorded", created_at: "2026-11-07T00:00:00Z" } });
    }
    return route.fulfill({ json: {} });
  });
  return { assistantRequests, chatRequests, feedbackRequests };
}

async function nativeClick(page, locator, label, { click = true } = {}) {
  await locator.waitFor({ state: "visible" });
  const box = await locator.boundingBox();
  assert.ok(box && box.width > 0 && box.height > 0, `${label} has no visible box`);
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const hit = await locator.evaluate((target, coordinates) => {
    const element = document.elementFromPoint(coordinates.x, coordinates.y);
    const describe = (node) => node && { tag: node.tagName, id: node.id, testId: node.getAttribute("data-testid"), className: typeof node.className === "string" ? node.className : "", rect: (() => { const rect = node.getBoundingClientRect(); return { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right }; })() };
    const supportPanel = document.querySelector("#support-panel");
    const panel = document.querySelector("#assistant-panel");
    return { belongs: Boolean(element && (element === target || target.contains(element))), tag: element?.tagName ?? null, element: describe(element), panel: describe(panel), panelChildren: panel ? [...panel.children].map(describe) : [], chatComposer: describe(document.querySelector("[data-chat-composer]")), hostStyle: supportPanel ? getComputedStyle(supportPanel).maxHeight : null };
  }, point);
  assert.ok(hit.belongs, `${label} center is intercepted or outside the viewport: ${JSON.stringify({ box, point, hit })}`);
  if (click) await page.mouse.click(point.x, point.y);
  return { box, point, hitTag: hit.tag };
}

async function setTextarea(locator, value) {
  await locator.evaluate((element, text) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(element, text);
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  }, value);
}

async function openSupport(page) {
  const trigger = page.getByTestId("support-widget-trigger");
  await nativeClick(page, trigger, "support trigger");
}

async function revealFeedbackSubmit(page, button) {
  const form = page.locator("#feedback-panel form");
  await form.waitFor({ state: "visible" });
  const bounds = await form.boundingBox();
  assert.ok(bounds, "feedback form must be measurable");
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const box = await button.boundingBox();
    if (box && box.y >= bounds.y && box.y + box.height <= bounds.y + bounds.height) break;
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(30);
  }
  return nativeClick(page, button, "feedback submit");
}

async function revealWithinPane(page, pane, target, label, maxAttempts = 30) {
  const paneBox = await pane.boundingBox();
  assert.ok(paneBox, `${label} pane must be measurable`);
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const box = await target.boundingBox();
    if (box && box.y >= paneBox.y && box.y + box.height <= paneBox.y + paneBox.height) break;
    await page.mouse.move(paneBox.x + paneBox.width / 2, paneBox.y + paneBox.height / 2);
    await page.mouse.wheel(0, 550);
    await page.waitForTimeout(20);
  }
  return nativeClick(page, target, label);
}

async function latestAnswerGeometry(page) {
  return page.evaluate(() => {
    const panel = document.querySelector("#assistant-panel");
    const history = panel?.querySelector(":scope > div.overflow-y-auto");
    const answers = panel?.querySelectorAll(".assistant-answer");
    const answer = answers?.[answers.length - 1];
    const body = answer?.firstElementChild || answer;
    if (!panel || !history || !body) return null;
    const clip = history.getBoundingClientRect();
    const bodyRect = body.getBoundingClientRect();
    const clipTop = clip.top + history.clientTop;
    const clipBottom = clipTop + history.clientHeight;
    const main = document.querySelector("main");
    return {
      clip: { top: clipTop, bottom: clipBottom },
      body: { top: bodyRect.top, bottom: bodyRect.bottom },
      bodyStartVisible: bodyRect.top >= clipTop - 1 && bodyRect.top < clipBottom,
      history: { scrollTop: history.scrollTop, scrollHeight: history.scrollHeight, clientHeight: history.clientHeight, overflowY: getComputedStyle(history).overflowY },
      panel: (() => { const rect = panel.getBoundingClientRect(); return { top: rect.top, bottom: rect.bottom }; })(),
      windowScrollY: window.scrollY,
      mainScrollTop: main?.scrollTop ?? null,
    };
  });
}

async function waitForAnswer(page) {
  await page.waitForFunction(() => Boolean(document.querySelector("#assistant-panel .assistant-answer")), null, { timeout: 5000 });
  await page.waitForTimeout(50);
}

async function checkLayout(page, viewport) {
  const layout = await page.locator("#support-panel").evaluate((panel) => {
    const { left, right, top, bottom, width } = panel.getBoundingClientRect();
    const main = document.querySelector("main").getBoundingClientRect();
    const visibleTop = window.visualViewport?.offsetTop ?? 0;
    return {
      left, right, top, bottom, width, mainRight: main.right, mainWidth: main.width,
      modal: panel.matches(":modal"), visibleTop, visibleBottom: visibleTop + (window.visualViewport?.height ?? window.innerHeight),
      backdrop: getComputedStyle(panel, "::backdrop").backgroundColor,
    };
  });
  const desktop = viewport.width >= 1024;
  assert.equal(layout.modal, !desktop);
  assert.ok(Math.abs(layout.right - viewport.width) <= 1 && Math.abs(layout.top - layout.visibleTop) <= 1 && Math.abs(layout.bottom - layout.visibleBottom) <= 1, JSON.stringify(layout));
  if (desktop) assert.ok(Math.abs(layout.mainRight - layout.left) <= 1, `page must reserve the rail's width: ${JSON.stringify(layout)}`);
  else {
    assert.equal(layout.mainRight, viewport.width);
    assert.equal(layout.backdrop, "rgba(0, 0, 0, 0.3)");
  }
  return layout;
}

async function checkLongAnswer(page, viewport, useMouseWheel = true) {
  const panel = page.locator("#assistant-panel");
  await panel.waitFor({ state: "visible" });
  const main = page.locator("main");
  const mainBefore = await main.evaluate((node) => node.scrollTop);
  const submit = panel.locator('form button[type="submit"]');
  const question = page.locator("#assistant-message");
  const questionFontSize = await question.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
  assert.ok(questionFontSize >= 16, `Assistant input must stay at least 16px to avoid mobile browser zoom: ${questionFontSize}px`);
  await setTextarea(question, `Long viewport smoke ${viewport.width}x${viewport.height}`);
  const before = await page.evaluate(() => {
    const panel = document.querySelector("#assistant-panel");
    const submit = panel?.querySelector('form button[type="submit"]');
    const panelRect = panel?.getBoundingClientRect();
    const submitRect = submit?.getBoundingClientRect();
    const point = submitRect && { x: submitRect.left + submitRect.width / 2, y: submitRect.top + submitRect.height / 2 };
    const hit = point && document.elementFromPoint(point.x, point.y);
    return { panel: panelRect && { top: panelRect.top, bottom: panelRect.bottom }, submit: submitRect && { top: submitRect.top, bottom: submitRect.bottom, x: point.x, y: point.y }, hitSubmit: Boolean(submit && hit && (hit === submit || submit.contains(hit))) };
  });
  assert.ok(before?.hitSubmit && before.submit, `assistant submit is not natively hittable at ${viewport.width}x${viewport.height}: ${JSON.stringify(before)}`);
  assert.ok(before.submit.y >= 0 && before.submit.y <= viewport.height, `assistant submit lies outside viewport: ${JSON.stringify(before)}`);
  await page.mouse.click(before.submit.x, before.submit.y);
  await waitForAnswer(page);
  const answer = await latestAnswerGeometry(page);
  assert.ok(answer?.bodyStartVisible, `latest answer body start must be visible in history at ${viewport.width}x${viewport.height}: ${JSON.stringify(answer)}`);
  assert.ok(answer.history.overflowY === "auto" && answer.history.scrollHeight > answer.history.clientHeight, `history must scroll independently: ${JSON.stringify(answer.history)}`);
  assert.ok(answer.panel.top >= 0 && answer.panel.bottom <= viewport.height, `assistant panel must fit viewport: ${JSON.stringify(answer.panel)}`);
  assert.equal(answer.windowScrollY, 0, "assistant reveal must not scroll window");
  assert.equal(answer.mainScrollTop, mainBefore, "assistant reveal must not scroll the page's main region");
  const oldHistoryTop = answer.history.scrollTop;
  const history = panel.locator(":scope > div.overflow-y-auto");
  if (useMouseWheel) {
    const historyBox = await history.boundingBox();
    assert.ok(historyBox, "assistant history must have a box");
    await page.mouse.move(historyBox.x + historyBox.width / 2, historyBox.y + historyBox.height / 2);
    await page.mouse.wheel(0, 160);
    await page.waitForTimeout(50);
  } else {
    await history.evaluate((node) => { node.scrollTop += 160; });
  }
  const afterScroll = await latestAnswerGeometry(page);
  assert.ok(afterScroll.history.scrollTop > oldHistoryTop, "history must move its own scroll pane");
  assert.equal(afterScroll.windowScrollY, 0, "history must not scroll window");
  assert.equal(afterScroll.mainScrollTop, mainBefore, "history must not scroll main page region");
  return { before, afterAnswer: answer, afterHistoryScroll: afterScroll };
}

async function checkChatFooter(page, requests) {
  const mode = page.getByTestId("button-mode-selector");
  const modeHit = await nativeClick(page, mode, "Chat mode selector");
  await nativeClick(page, mode, "close Chat mode selector");
  await nativeClick(page, page.getByTestId("rag-mode-option-agentic"), "Chat agentic RAG option");
  await nativeClick(page, page.getByTestId("rag-mode-option-standard"), "Chat standard RAG option");
  const kb = page.getByTestId("button-kb-selector");
  const kbHit = await nativeClick(page, kb, "Chat knowledge base selector");
  const option = page.getByTestId("kb-option-smoke-kb");
  const optionHit = await nativeClick(page, option, "Chat knowledge base option", { click: false });
  await nativeClick(page, kb, "close Chat knowledge base selector");
  const input = page.getByTestId("input-chat-message");
  const inputFontSize = await input.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
  assert.ok(inputFontSize >= 16, `Chat input must stay at least 16px to avoid mobile browser zoom: ${inputFontSize}px`);
  const inputHit = await nativeClick(page, input, "Chat input");
  await setTextarea(input, "Chat footer remains usable");
  const send = page.getByTestId("button-send-message");
  const sendHit = await nativeClick(page, send, "Chat send");
  await page.waitForFunction(() => document.querySelectorAll('[data-testid^="message-"]').length >= 2, null, { timeout: 5000 });
  assert.equal(requests.length, 1, "native Chat send must issue exactly one mocked request");
  return { modeHit, kbHit, optionHit, inputHit, sendHit };
}

async function runCoreCase(routePath, viewport) {
  const page = await browser.newPage({ viewport });
  const requests = await installMocks(page);
  await page.goto(`${baseUrl}${routePath}`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await openSupport(page);
  const layout = await checkLayout(page, viewport);
  const answerGeometry = await checkLongAnswer(page, viewport);
  let footer = null;
  if (layout.modal) {
    await page.mouse.click(4, viewport.height / 2);
    await page.locator("#support-panel").waitFor({ state: "hidden" });
  }
  if (routePath === "/chat") footer = await checkChatFooter(page, requests.chatRequests);
  const result = { route: routePath, viewport: `${viewport.width}x${viewport.height}`, layout, assistantPosts: requests.assistantRequests.length, answerGeometry, chatFooter: footer };
  await page.close();
  return result;
}

async function runFlagCase(assistantEnabled, feedbackEnabled) {
  const flags = { assistant_enabled: assistantEnabled, feedback_enabled: feedbackEnabled };
  const page = await browser.newPage({ viewport: { width: 390, height: 400 } });
  const requests = await installMocks(page, flags, [
    { delay: 700, reply: assistantReply({ citations: [citation] }) },
    { reply: assistantReply({ intent: "feedback", answer: "Feedback classification", feedback_draft: "editable draft" }) },
  ]);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  if (!assistantEnabled && !feedbackEnabled) {
    await page.waitForTimeout(300);
    assert.equal(await page.getByTestId("support-widget-trigger").count(), 0, "no feature flag means no support entry");
    const result = { flags, noEntry: true, assistantPosts: 0, feedbackPosts: 0 };
    await page.close();
    return result;
  }

  await page.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await openSupport(page);
  if (!assistantEnabled) {
    const feedbackSubmit = page.getByTestId("feedback-submit");
    await page.locator("#feedback-content").waitFor({ state: "visible" });
    await setTextarea(page.locator("#feedback-content"), "Feedback-only native reachability check");
    await revealFeedbackSubmit(page, feedbackSubmit);
    await page.waitForFunction(() => Boolean(document.querySelector('#feedback-panel [role="status"]')), null, { timeout: 5000 });
    assert.equal(requests.feedbackRequests.length, 1, "feedback-only submit posts once");
    assert.equal(requests.assistantRequests.length, 0, "feedback-only has no assistant endpoint");
    const result = { flags, feedbackSubmitHit: true, assistantPosts: 0, feedbackPosts: requests.feedbackRequests.length };
    await page.close();
    return result;
  }

  if (feedbackEnabled) {
    const panel = page.locator("#assistant-panel");
    await panel.waitFor({ state: "visible" });
    await setTextarea(page.locator("#assistant-message"), "A long question that remains visible while manual feedback is open.");
    const ask = panel.locator('form button[type="submit"]');
    await nativeClick(page, ask, "assistant ask while feedback is enabled");
    const manualFeedback = page.locator("#assistant-panel > div:nth-child(2) > div button").first();
    const history = panel.locator(":scope > div.overflow-y-auto");
    const historyBox = await history.boundingBox();
    assert.ok(historyBox, "assistant history should have a scrollport while the first request is pending");
    await manualFeedback.scrollIntoViewIfNeeded();
    await nativeClick(page, manualFeedback, "manual feedback action while reply is pending");
    await page.locator("#feedback-panel").waitFor({ state: "visible" });
    const cancel = page.locator("#feedback-panel button").filter({ hasText: "Cancel" });
    await cancel.waitFor({ state: "visible" });
    await page.waitForTimeout(800);
    await page.locator("#assistant-panel .assistant-answer").waitFor({ state: "attached" });
    const feedbackForm = page.locator("#feedback-panel form");
    const feedbackBox = await feedbackForm.boundingBox();
    assert.ok(feedbackBox, "manual feedback form should be scrollable");
    await page.mouse.move(feedbackBox.x + feedbackBox.width / 2, feedbackBox.y + feedbackBox.height / 2);
    await page.mouse.wheel(0, 700);
    await page.waitForTimeout(40);
    await nativeClick(page, cancel, "cancel manual feedback after reply");
    await page.locator("#assistant-panel").waitFor({ state: "visible" });
    await page.waitForFunction(() => {
      const answer = document.querySelector("#assistant-panel .assistant-answer > :first-child");
      const history = document.querySelector("#assistant-panel > div.overflow-y-auto");
      if (!answer || !history) return false;
      const clip = history.getBoundingClientRect();
      const top = answer.getBoundingClientRect().top;
      return top >= clip.top + history.clientTop - 1 && top < clip.top + history.clientTop + history.clientHeight;
    }, null, { timeout: 5000 });
    const citationButton = page.locator("#assistant-panel .assistant-answer + button");
    await revealWithinPane(page, page.locator("#assistant-panel > div.overflow-y-auto"), citationButton, "help citation");
    await page.getByTestId("assistant-help-section").waitFor({ state: "visible" });

    await setTextarea(page.locator("#assistant-message"), "Automatically classified feedback draft");
    const secondAsk = page.locator('#assistant-panel form button[type="submit"]');
    await nativeClick(page, secondAsk, "assistant automatic feedback ask");
    await page.locator("#feedback-content").waitFor({ state: "visible" });
    assert.equal(await page.locator("#feedback-content").inputValue(), "Automatically classified feedback draft", "automatic feedback preserves the original question as an editable draft");
    const feedbackSubmit = page.getByTestId("feedback-submit");
    await revealFeedbackSubmit(page, feedbackSubmit);
    await page.waitForFunction(() => Boolean(document.querySelector('#feedback-panel [role="status"]')), null, { timeout: 5000 });
    assert.equal(requests.assistantRequests.length, 2);
    assert.equal(requests.feedbackRequests.length, 1);
    assert.ok(requests.assistantRequests.every((body) => !("mode" in body) && body.selected_target === null), "assistant frontend uses the versioned freeform transport");
    const result = { flags, pendingManualFeedbackCancel: true, answerVisibleAfterCancel: true, helpCitationOpened: true, automaticDraft: await page.locator("#feedback-content").count() === 1, assistantPosts: requests.assistantRequests.length, feedbackPosts: requests.feedbackRequests.length };
    await page.close();
    return result;
  }

  const result = { flags, coreCaseCovered: true, assistantPosts: requests.assistantRequests.length, feedbackPosts: 0 };
  await page.close();
  return result;
}

async function runChatGrowthCase(viewport) {
  const page = await browser.newPage({ viewport });
  const requests = await installMocks(page);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  const chatInput = page.getByTestId("input-chat-message");
  await chatInput.waitFor({ state: "visible" });
  const initialHeight = await chatInput.evaluate((input) => input.getBoundingClientRect().height);
  await setTextarea(chatInput, Array.from({ length: 12 }, (_, index) => `Chat composer growth line ${index + 1}`).join("\n"));
  const inputHeight = await chatInput.evaluate((input) => input.getBoundingClientRect().height);
  assert.equal(await chatInput.evaluate((input) => input.style.height), "120px");
  assert.ok(inputHeight > initialHeight && inputHeight <= 120, `Chat input must grow within its viewport cap: ${inputHeight}`);
  const chatDraft = await chatInput.inputValue();
  await openSupport(page);
  const answer = await checkLongAnswer(page, viewport);
  await page.keyboard.press("Escape");
  await page.locator("#support-panel").waitFor({ state: "hidden" });
  assert.equal(await chatInput.inputValue(), chatDraft);
  const chatSend = await nativeClick(page, page.getByTestId("button-send-message"), "Chat send after closing Assistant", { click: false });
  const result = { viewport: `${viewport.width}x${viewport.height}`, chatInputHeight: inputHeight, answerGeometry: answer, chatSend, assistantPosts: requests.assistantRequests.length };
  await page.close();
  return result;
}

async function runResizeCase() {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const requests = await installMocks(page);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await openSupport(page);
  const panel = page.locator("#assistant-panel");
  await setTextarea(page.locator("#assistant-message"), "Resize keeps the current answer and footer usable");
  await nativeClick(page, panel.locator('form button[type="submit"]'), "assistant submit before resize");
  await waitForAnswer(page);
  const dimensions = [sizes[3], sizes[1], sizes[5], sizes[2]];
  const measurements = [];
  for (const viewport of dimensions) {
    await page.setViewportSize(viewport);
    await page.waitForFunction(({ width, height }) => {
      const panel = document.querySelector("#support-panel");
      return panel?.matches(":modal") === (width < 1024) && Math.abs(panel.getBoundingClientRect().bottom - height) <= 1;
    }, viewport, { timeout: 5000 });
    const layout = await checkLayout(page, viewport);
    const answerGeometry = await latestAnswerGeometry(page);
    assert.ok(answerGeometry?.bodyStartVisible, `latest answer start must remain visible after resize to ${viewport.width}x${viewport.height}: ${JSON.stringify(answerGeometry)}`);
    assert.equal(answerGeometry.windowScrollY, 0);
    const submitHit = await nativeClick(page, panel.locator('form button[type="submit"]'), `assistant submit after resize to ${viewport.width}x${viewport.height}`, { click: false });
    measurements.push({ viewport: `${viewport.width}x${viewport.height}`, layout, answerGeometry, pointerHits: { assistantSubmit: submitHit } });
  }
  assert.equal(requests.assistantRequests.length, 1);
  const result = { route: "/chat", openPanelResizeSequence: dimensions.map(({ width, height }) => `${width}x${height}`), measurements };
  await page.close();
  return result;
}

async function runScrollAndKeyboardCase(viewport, lang) {
  const mobile = viewport.width < 1024;
  const page = await browser.newPage({ viewport, isMobile: mobile, hasTouch: mobile });
  const requests = await installMocks(page, undefined, [], lang);
  await page.addInitScript(() => {
    const viewport = Object.assign(new EventTarget(), { offsetTop: 0, keyboardHeight: null });
    Object.defineProperty(viewport, "height", { get: () => viewport.keyboardHeight ?? window.innerHeight });
    Object.defineProperty(window, "visualViewport", { value: viewport });
  });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.getByTestId("category-row-7").waitFor();
  const main = page.locator("main");
  const trigger = page.getByTestId("support-widget-trigger");
  const closedWidth = await main.evaluate((node) => node.getBoundingClientRect().width);
  const measurements = [];
  for (const position of [0, 0.5, 1]) {
    const scrollTop = await main.evaluate((node, fraction) => {
      node.scrollTop = (node.scrollHeight - node.clientHeight) * fraction;
      return node.scrollTop;
    }, position);
    assert.equal(scrollTop > 0, position > 0);
    await openSupport(page);
    const layout = await checkLayout(page, viewport);
    assert.ok(Math.abs(closedWidth - layout.mainWidth - (mobile ? 0 : layout.width)) <= 1);
    const measurement = { position, scrollTop, layout };
    if (mobile && position === 1) {
      const input = page.locator("#assistant-message");
      await input.tap();
      await page.evaluate(() => {
        Object.assign(window.visualViewport, { offsetTop: 430, keyboardHeight: 152 });
        window.visualViewport.dispatchEvent(new Event("resize"));
        window.visualViewport.dispatchEvent(new Event("scroll"));
      });
      measurement.keyboard = await checkLayout(page, viewport);
      await nativeClick(page, input, "assistant input above the keyboard", { click: false });
      // Playwright's mobile WebKit has touch input and no mouse wheel.
      measurement.answer = await checkLongAnswer(page, viewport, browser.browserType().name() !== "webkit");
      assert.equal(requests.assistantRequests[0].locale, lang);
      await page.evaluate(() => {
        Object.assign(window.visualViewport, { offsetTop: 0, keyboardHeight: null });
        window.visualViewport.dispatchEvent(new Event("resize"));
      });
      measurement.restored = await checkLayout(page, viewport);
    }
    if (!mobile) {
      await main.evaluate((node) => { node.scrollTop = node.scrollTop > 0 ? 0 : node.scrollHeight; });
      assert.deepEqual(await checkLayout(page, viewport), layout);
    }
    if (mobile && position === 0.5) await page.mouse.click(4, viewport.height / 2);
    else if (position === 0) await page.locator("#assistant-panel header button").click();
    else await page.keyboard.press("Escape");
    await page.locator("#support-panel").waitFor({ state: "hidden" });
    assert.equal(await trigger.getAttribute("aria-expanded"), "false");
    await page.waitForFunction(() => document.activeElement?.getAttribute("data-testid") === "support-widget-trigger");
    assert.equal(await main.evaluate((node) => node.getBoundingClientRect().width), closedWidth);
    measurements.push(measurement);
  }
  await page.close();
  return { lang, viewport, measurements };
}

async function runLongHistoryManualFeedbackCase() {
  const page = await browser.newPage({ viewport: { width: 390, height: 500 } });
  const requests = await installMocks(page, { assistant_enabled: true, feedback_enabled: true }, [
    { reply: assistantReply({ answer: longAnswer }) },
    { delay: 700, reply: assistantReply({ answer: `Latest pending reply starts here.\n\n${longAnswer}` }) },
  ]);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await openSupport(page);
  const input = page.locator("#assistant-message");
  const ask = page.locator('#assistant-panel form button[type="submit"]');
  await setTextarea(input, "First long-history question");
  await nativeClick(page, ask, "first long-history question");
  await waitForAnswer(page);
  const firstAnswer = await latestAnswerGeometry(page);
  assert.ok(firstAnswer.bodyStartVisible, "first answer should be revealed before testing the second request");

  await setTextarea(input, "Second question while reading older history");
  await nativeClick(page, ask, "second question with delayed reply");
  const history = page.locator("#assistant-panel > div.overflow-y-auto");
  const historyBox = await history.boundingBox();
  assert.ok(historyBox, "assistant history pane must be measurable");
  await page.mouse.move(historyBox.x + historyBox.width / 2, historyBox.y + historyBox.height / 2);
  await page.mouse.wheel(0, -1000);
  await page.waitForTimeout(60);
  const olderReadingTop = await history.evaluate((element) => element.scrollTop);
  assert.ok(olderReadingTop < firstAnswer.history.scrollTop, "native wheel should move from the latest answer to older history");
  const manualFeedback = page.locator("#assistant-panel > div.overflow-y-auto > div button").first();
  await nativeClick(page, manualFeedback, "manual feedback while the second reply is pending");
  await page.locator("#feedback-panel").waitFor({ state: "visible" });
  await page.locator("#assistant-panel .assistant-answer").nth(1).waitFor({ state: "attached", timeout: 5000 });
  const cancel = page.locator("#feedback-panel button").filter({ hasText: /cancel/i });
  await revealWithinPane(page, page.locator("#feedback-panel form"), cancel, "cancel manual feedback after delayed reply");
  await page.waitForFunction(() => {
    const answers = document.querySelectorAll("#assistant-panel .assistant-answer > :first-child");
    const answer = answers[answers.length - 1];
    const history = document.querySelector("#assistant-panel > div.overflow-y-auto");
    if (!answer || !history) return false;
    const clip = history.getBoundingClientRect();
    const top = answer.getBoundingClientRect().top;
    return top >= clip.top + history.clientTop - 1 && top < clip.top + history.clientTop + history.clientHeight;
  }, null, { timeout: 5000 });
  const afterCancel = await latestAnswerGeometry(page);
  assert.ok(afterCancel.bodyStartVisible, "cancel must reveal the new answer once after the pending manual-feedback flow");
  assert.equal(afterCancel.windowScrollY, 0);
  assert.equal(afterCancel.mainScrollTop, 0);
  const result = { firstAnswerStartVisible: firstAnswer.bodyStartVisible, olderReadingTop, afterCancel, assistantPosts: requests.assistantRequests.length };
  await page.close();
  return result;
}

async function runOlderReadingPreservationCase() {
  const page = await browser.newPage({ viewport: { width: 390, height: 500 } });
  const requests = await installMocks(page, { assistant_enabled: true, feedback_enabled: true }, [
    { reply: assistantReply({ answer: longAnswer }) },
    { delay: 700, reply: assistantReply({ answer: `Unread latest reply.\n\n${longAnswer}` }) },
  ]);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await openSupport(page);
  const input = page.locator("#assistant-message");
  const ask = page.locator('#assistant-panel form button[type="submit"]');
  await setTextarea(input, "First answer before reading older content");
  await nativeClick(page, ask, "first question before older-reading check");
  await waitForAnswer(page);
  const history = page.locator("#assistant-panel > div.overflow-y-auto");
  const historyBox = await history.boundingBox();
  assert.ok(historyBox, "assistant history pane must be measurable");
  await setTextarea(input, "Second delayed answer while reading older content");
  await nativeClick(page, ask, "second question during older-history reading");
  await page.mouse.move(historyBox.x + historyBox.width / 2, historyBox.y + historyBox.height / 2);
  await page.mouse.wheel(0, -1000);
  await page.waitForTimeout(60);
  const readingTop = await history.evaluate((element) => element.scrollTop);
  await page.locator("#assistant-panel .assistant-answer").nth(1).waitFor({ state: "attached", timeout: 5000 });
  await page.waitForTimeout(50);
  const afterReply = await latestAnswerGeometry(page);
  assert.equal(afterReply.history.scrollTop, readingTop, "a reply without opening feedback must preserve the older reading position");
  assert.equal(afterReply.bodyStartVisible, false, "the newest answer should remain below the clip while the user reads older content");
  assert.equal(afterReply.windowScrollY, 0);
  assert.equal(afterReply.mainScrollTop, 0);
  const result = { readingTop, afterReply, assistantPosts: requests.assistantRequests.length, manualFeedbackOpened: false };
  await page.close();
  return result;
}

async function runClarificationLanguageCase(lang) {
  const english = lang === "en";
  const backendText = english
    ? "I could not determine the request. Please add more detail or rephrase your question."
    : "无法确定请求，请补充更多细节或换一种方式提问。";
  const recoveryText = english
    ? "Please add more detail or rephrase your question."
    : "请补充更多细节或换一种方式提问。";
  const page = await browser.newPage({ viewport: { width: 390, height: 500 } });
  const requests = await installMocks(page, { assistant_enabled: true, feedback_enabled: false }, [
    { reply: assistantReply({ intent: "clarify", answer: backendText }) },
  ], lang);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("support-widget-trigger").waitFor({ state: "visible" });
  await openSupport(page);
  await setTextarea(page.locator("#assistant-message"), english ? "Help" : "帮助");
  await nativeClick(page, page.locator('#assistant-panel form button[type="submit"]'), `${lang} clarifying question`);
  await page.locator("#assistant-panel .assistant-answer").waitFor({ state: "visible" });
  const articleText = await page.locator("#assistant-panel article").innerText();
  assert.ok(articleText.includes(backendText) && articleText.includes(recoveryText), `${lang} clarification should request a clearer question: ${articleText}`);
  assert.doesNotMatch(articleText, /choose feedback|feedback, usage|choose a type|请选择|选择类型|下方选择|点击提建议/i);
  assert.equal(await page.locator("#assistant-panel select, #assistant-panel [role=combobox], #assistant-panel [role=radiogroup]").count(), 0);
  const result = { lang, articleText, assistantPosts: requests.assistantRequests.length, removedTypeControls: 0 };
  await page.close();
  return result;
}

try {
  const results = [];
  for (const routePath of ["/", "/chat"]) {
    for (const viewport of sizes) results.push(await runCoreCase(routePath, viewport));
  }
  const featureMatrix = [];
  for (const [assistant, feedback] of [[false, false], [false, true], [true, false], [true, true]]) {
    featureMatrix.push(await runFlagCase(assistant, feedback));
  }
  const composerGrowth = [];
  for (const viewport of [sizes[0], sizes[2]]) composerGrowth.push(await runChatGrowthCase(viewport));
  const resizeSequence = await runResizeCase();
  const longHistoryManualCancel = await runLongHistoryManualFeedbackCase();
  const olderReadingPreservation = await runOlderReadingPreservationCase();
  const clarificationLanguages = [];
  for (const lang of ["en", "zh"]) clarificationLanguages.push(await runClarificationLanguageCase(lang));
  const scrollAndKeyboard = [];
  for (const lang of ["en", "zh"]) {
    for (const viewport of [{ width: 1280, height: 620 }, { width: 390, height: 844 }]) {
      scrollAndKeyboard.push(await runScrollAndKeyboardCase(viewport, lang));
    }
  }
  const evidence = { browser: browser.browserType().name(), api: "all routes mocked", realProviderCalls: 0, coreCases: results, featureMatrix, composerGrowth, resizeSequence, longHistoryManualCancel, olderReadingPreservation, clarificationLanguages, scrollAndKeyboard };
  const evidencePath = process.env.SMOKE_EVIDENCE_PATH || path.resolve(process.cwd(), "../../../reports/issue-473-480-20261107/issue-474/review-5-browser-smoke.json");
  await mkdir(path.dirname(evidencePath), { recursive: true });
  await writeFile(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`);
  console.log(JSON.stringify({ ...evidence, evidencePath }, null, 2));
  assert.equal(results.length, 2 * sizes.length);
  assert.equal(featureMatrix.length, 4);
  assert.ok(featureMatrix.find((result) => !result.flags.assistant_enabled && !result.flags.feedback_enabled)?.noEntry);
} finally {
  await browser.close();
}

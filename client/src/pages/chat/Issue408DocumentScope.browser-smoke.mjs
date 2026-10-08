import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const baseUrl = process.env.SMOKE_URL || "http://127.0.0.1:5173";
const docs = [
  { file_url: "https://scope.example.test/cas-primer.pdf", filename: "cas-primer.pdf", title: "The CAS AI Primer", category: "Guidance", keywords: [] },
  { file_url: "https://scope.example.test/soa-guide.pdf", filename: "soa-guide.pdf", title: "SOA Guide", category: "Guidance", keywords: [] },
];
const conversations = new Map();
const queryRequests = [];
const markdownRequests = [];
const scopeClearRequests = [];
const restoreRequests = [];
const libraryRetrievals = [];
const selectorA = { file_url: docs[0].file_url, filename: docs[0].filename, title: docs[0].title };
const selectorB = { file_url: docs[1].file_url, filename: docs[1].filename, title: docs[1].title };
let queryNumber = 0;
let createdConversationNumber = 0;
let rejectFirstDocumentBSwitchForQuota = true;
let failFirstAcceptedDocumentBSwitch = true;

async function fixtureApi(route) {
  const request = route.request();
  const { pathname, search } = new URL(request.url());
  const method = request.method();
  if (pathname === "/api/auth/me") {
    return route.fulfill({ json: { data: {
      require_auth: true,
      authenticated: true,
      user: { id: 408, email: "scope-smoke@example.test", role: "registered" },
      permissions: ["chat.conversations", "chat.query", "chat.view"],
    } } });
  }
  if (pathname === "/api/chat/conversations" && method === "GET") {
    return route.fulfill({ json: { success: true, data: { conversations: [...conversations.values()].map((item) => ({
      conversation_id: item.id,
      title: item.title,
      created_at: item.created_at,
      updated_at: item.updated_at,
      metadata: { document_scope: item.documentScope },
    })) } } });
  }
  if (pathname === "/api/chat/conversations" && method === "POST") {
    createdConversationNumber += 1;
    const id = `conv-new-${createdConversationNumber}`;
    conversations.set(id, { id, title: "New conversation", documentScope: [], created_at: new Date().toISOString() });
    return route.fulfill({ status: 201, json: { success: true, data: { conversation_id: id } } });
  }
  const conversationMatch = pathname.match(/^\/api\/chat\/conversations\/([^/]+)$/);
  if (conversationMatch && method === "GET") {
    const conversation = conversations.get(conversationMatch[1]);
    assert.ok(conversation, `unknown conversation ${conversationMatch[1]}`);
    restoreRequests.push(conversation.id);
    if (conversation.id === "conv-explain-1" && restoreRequests.filter((id) => id === conversation.id).length === 1) {
      return route.fulfill({ status: 500, json: { detail: "Temporary restore failure" } });
    }
    return route.fulfill({ json: { success: true, data: {
      conversation: { conversation_id: conversation.id, title: conversation.title, metadata: { document_scope: conversation.documentScope } },
      messages: [],
    } } });
  }
  if (pathname.endsWith("/document-scope") && method === "DELETE") {
    const id = pathname.split("/")[4];
    const conversation = conversations.get(id);
    assert.ok(conversation, `unknown conversation ${id}`);
    conversation.documentScope = [];
    scopeClearRequests.push(id);
    return route.fulfill({ json: { success: true } });
  }
  if (conversationMatch && method === "DELETE") {
    conversations.delete(conversationMatch[1]);
    return route.fulfill({ json: { success: true } });
  }
  if (pathname === "/api/chat/knowledge-bases") {
    return route.fulfill({ json: { success: true, data: { knowledge_bases: [] } } });
  }
  if (pathname === "/api/categories") return route.fulfill({ json: { categories: ["Guidance"] } });
  if (pathname === "/api/chat/available-documents") {
    return route.fulfill({ json: { success: true, data: { items: docs, total: docs.length, offset: 0, limit: 50 } } });
  }
  if (pathname.startsWith("/api/files/") && pathname.endsWith("/markdown")) {
    const encodedUrl = pathname.slice("/api/files/".length, -"/markdown".length);
    const fileUrl = decodeURIComponent(encodedUrl);
    const doc = docs.find((item) => item.file_url === fileUrl);
    assert.ok(doc, `unknown Markdown source ${fileUrl}`);
    markdownRequests.push(fileUrl);
    return route.fulfill({ json: { success: true, markdown: { markdown_content: `Markdown body for ${doc.title}.` } } });
  }
  if (pathname === "/api/chat/query" && method === "POST") {
    const body = request.postDataJSON();
    queryRequests.push(body);
    queryNumber += 1;
    const id = body.conversation_id || "conv-explain-1";
    const conversation = conversations.get(id) || {
      id,
      title: body.message,
      documentScope: [],
      scopeInitialized: false,
      created_at: new Date().toISOString(),
    };
    const requestedScope = body.document_scope || [];
    if (
      id === "conv-explain-1"
      && body.document_scope_switch
      && JSON.stringify(requestedScope) === JSON.stringify([selectorB])
      && rejectFirstDocumentBSwitchForQuota
    ) {
      rejectFirstDocumentBSwitchForQuota = false;
      return route.fulfill({ status: 429, json: {
        success: false,
        error: "Daily AI chat limit reached. Please retry later.",
      } });
    }
    if (requestedScope.length) {
      if (conversation.scopeInitialized && !body.document_scope_switch && JSON.stringify(requestedScope) !== JSON.stringify(conversation.documentScope)) {
        return route.fulfill({ status: 409, json: {
          success: false,
          code: "CHAT_DOCUMENT_SCOPE_MISMATCH",
          error: "The supplied document content does not match this conversation's document scope.",
          retryable: false,
          data: { conversation_id: id, message_id: `msg-${queryNumber}` },
        } });
      }
      conversation.documentScope = requestedScope;
      conversation.scopeInitialized = true;
    } else if (body.document_scope_clear) {
      conversation.documentScope = [];
      conversation.scopeInitialized = true;
    } else if (conversation.documentScope.length) {
      conversations.set(id, conversation);
      return route.fulfill({ status: 422, json: {
        success: false,
        code: "CHAT_DOCUMENT_EMPTY",
        error: "The selected document has no usable Markdown content.",
        retryable: true,
        data: { conversation_id: id, message_id: `msg-${queryNumber}` },
      } });
    } else {
      libraryRetrievals.push({ conversationId: id, message: body.message });
      conversation.scopeInitialized = true;
    }
    conversations.set(id, conversation);
    if (
      id === "conv-explain-1"
      && body.document_scope_switch
      && JSON.stringify(requestedScope) === JSON.stringify([selectorB])
      && failFirstAcceptedDocumentBSwitch
    ) {
      failFirstAcceptedDocumentBSwitch = false;
      return route.fulfill({ status: 502, json: {
        success: false,
        code: "CHAT_PROVIDER_UPSTREAM",
        error: "The AI provider is temporarily unavailable. Please retry.",
        retryable: true,
        data: { conversation_id: id, message_id: `msg-${queryNumber}` },
      } });
    }
    return route.fulfill({ json: { success: true, data: {
      conversation_id: id,
      message_id: `msg-${queryNumber}`,
      response: `Fixture answer ${queryNumber}`,
      citations: [],
    } } });
  }
  throw new Error(`Unexpected API request: ${method} ${pathname}${search}`);
}

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.route("**/api/**", fixtureApi);
  await page.goto(`${baseUrl}/chat`, { waitUntil: "networkidle" });
  await page.getByTestId("button-toggle-documents-panel").click();
  await page.getByTestId("document-0").click();
  await page.getByText("Fixture answer 1", { exact: true }).waitFor();
  await page.getByTestId("chat-document-scope").getByText("The CAS AI Primer").waitFor();

  async function sendFollowup(text, answer) {
    await page.getByTestId("input-chat-message").fill(text);
    const [response] = await Promise.all([
      page.waitForResponse((item) => item.url().includes("/api/chat/query") && item.request().method() === "POST"),
      page.getByTestId("button-send-message").click(),
    ]);
    assert.equal(response.ok(), true, `${text} failed with ${response.status()}`);
    await page.getByText(answer, { exact: true }).waitFor();
  }

  await sendFollowup("Follow-up one", "Fixture answer 2");
  await sendFollowup("Follow-up two", "Fixture answer 3");
  for (const request of queryRequests.slice(0, 3)) {
    assert.deepEqual(request.document_scope, [selectorA]);
    assert.equal(request.document_file_url, docs[0].file_url);
    assert.equal(request.document_content, `Markdown body for ${docs[0].title}.`);
  }
  assert.equal(queryRequests[0].document_scope_switch, true);
  assert.equal(queryRequests[1].document_scope_switch, false);
  assert.equal(queryRequests[2].document_scope_switch, false);

  await page.reload({ waitUntil: "networkidle" });
  await page.getByTestId("conversation-conv-explain-1").click();
  await page.getByTestId("conversation-load-error").waitFor();
  assert.equal(await page.getByTestId("input-chat-message").isDisabled(), true);
  assert.equal(queryRequests.length, 3);
  await page.getByTestId("button-retry-load-conversation").click();
  await page.getByTestId("chat-document-scope").getByText("The CAS AI Primer").waitFor();
  await sendFollowup("After restore", "Fixture answer 4");
  assert.deepEqual(queryRequests[3].document_scope, [selectorA]);
  assert.equal(queryRequests[3].document_file_url, docs[0].file_url);

  await page.getByTestId("button-toggle-documents-panel").click();
  const [quotaResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().includes("/api/chat/query") && item.request().method() === "POST"),
    page.getByTestId("document-1").click(),
  ]);
  assert.equal(quotaResponse.status(), 429);
  await page.getByTestId("chat-document-scope").getByText("SOA Guide").waitFor();
  assert.deepEqual(queryRequests[4].document_scope, [selectorB]);
  assert.equal(queryRequests[4].document_scope_switch, true);
  await page.getByText("Daily AI chat limit reached. Please retry later.").waitFor();

  await page.getByTestId("input-chat-message").fill("Retry switch after quota");
  const [providerFailureResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().includes("/api/chat/query") && item.request().method() === "POST"),
    page.getByTestId("button-send-message").click(),
  ]);
  assert.equal(providerFailureResponse.status(), 502);
  assert.deepEqual(queryRequests[5].document_scope, [selectorB]);
  assert.equal(queryRequests[5].document_scope_switch, true);
  assert.deepEqual(conversations.get("conv-explain-1").documentScope, [selectorB]);
  const scopeAfterProviderFailure = conversations.get("conv-explain-1").documentScope.map((source) => ({ ...source }));
  await page.getByText("The AI provider is temporarily unavailable. Please retry.").waitFor();

  const switchTab = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await switchTab.route("**/api/**", fixtureApi);
  await switchTab.goto(`${baseUrl}/chat`, { waitUntil: "networkidle" });
  await switchTab.getByTestId("conversation-conv-explain-1").click();
  await switchTab.getByTestId("chat-document-scope").getByText("SOA Guide").waitFor();
  await switchTab.getByTestId("button-toggle-documents-panel").click();
  await switchTab.getByTestId("document-0").click();
  await switchTab.getByText("Fixture answer 7", { exact: true }).waitFor();
  assert.deepEqual(queryRequests[6].document_scope, [selectorA]);
  assert.equal(queryRequests[6].document_scope_switch, true);
  assert.deepEqual(conversations.get("conv-explain-1").documentScope, [selectorA]);
  const scopeAfterOtherTabSwitch = conversations.get("conv-explain-1").documentScope.map((source) => ({ ...source }));
  await switchTab.close();

  await page.getByTestId("input-chat-message").fill("Old tab follow-up after provider failure");
  const [scopeMismatchResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().includes("/api/chat/query") && item.request().method() === "POST"),
    page.getByTestId("button-send-message").click(),
  ]);
  assert.equal(scopeMismatchResponse.status(), 409);
  assert.deepEqual(queryRequests[7].document_scope, [selectorB]);
  assert.equal(queryRequests[7].document_scope_switch, false);
  assert.deepEqual(conversations.get("conv-explain-1").documentScope, [selectorA]);

  await page.getByTestId("button-clear-document-scope").click();
  await page.getByTestId("chat-document-scope").waitFor({ state: "detached" });
  assert.deepEqual(scopeClearRequests, ["conv-explain-1"]);
  await sendFollowup("Search the library", "Fixture answer 9");
  assert.deepEqual(queryRequests[8].document_scope, []);
  assert.equal(Object.hasOwn(queryRequests[8], "document_file_url"), false);

  await page.getByTestId("button-new-conversation").click();
  await page.getByTestId("conversation-conv-new-1").waitFor();
  assert.equal(await page.getByTestId("chat-document-scope").count(), 0);
  await sendFollowup("New conversation question", "Fixture answer 10");
  assert.deepEqual(queryRequests[9].document_scope, []);
  assert.equal(queryRequests[9].conversation_id, "conv-new-1");

  const otherTab = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await otherTab.route("**/api/**", fixtureApi);
  await otherTab.goto(`${baseUrl}/chat`, { waitUntil: "networkidle" });
  await otherTab.getByTestId("conversation-conv-new-1").click();
  await otherTab.getByTestId("input-chat-message").waitFor();
  await otherTab.getByTestId("button-toggle-documents-panel").click();
  await otherTab.getByTestId("document-1").click();
  await otherTab.getByText("Fixture answer 11", { exact: true }).waitFor();
  assert.deepEqual(queryRequests[10].document_scope, [selectorB]);
  assert.equal(queryRequests[10].document_scope_switch, true);

  const priorLibraryRetrievals = libraryRetrievals.length;
  await page.getByTestId("input-chat-message").fill("Old tab follow-up");
  const [staleTabResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().includes("/api/chat/query") && item.request().method() === "POST"),
    page.getByTestId("button-send-message").click(),
  ]);
  assert.equal(staleTabResponse.status(), 422);
  await page.getByText("Document markdown content is unavailable.").waitFor();
  assert.deepEqual(queryRequests[11].document_scope, []);
  assert.equal(queryRequests[11].document_scope_clear, false);
  assert.equal(queryRequests[11].conversation_id, "conv-new-1");
  assert.deepEqual(conversations.get("conv-new-1").documentScope, [selectorB]);
  assert.equal(libraryRetrievals.length, priorLibraryRetrievals);
  assert.equal(libraryRetrievals.some((item) => item.message === "Old tab follow-up"), false);
  assert.equal(markdownRequests.length, 9);

  console.log(JSON.stringify({
    chromium: "pass",
    browser: "real Chromium with local API fixtures",
    evidence: "first Explain, two follow-ups, restore retry, quota rejection and recovered switch, scope-accepted provider failure, other-tab switch, persisted clear, new conversation, and stale-tab inheritance",
    queryCount: queryRequests.length,
    markdownFetches: markdownRequests.length,
    libraryRetrievals,
    staleTab: {
      sentScope: queryRequests[11].document_scope,
      savedScopeAfterFailure: conversations.get("conv-new-1").documentScope,
      retrievalCountUnchanged: libraryRetrievals.length === priorLibraryRetrievals,
    },
    quotaSwitch: {
      rejectedRequest: queryRequests[4].document_scope_switch,
      retriedRequest: queryRequests[5].document_scope_switch,
      afterOtherTabSwitch: queryRequests[7].document_scope_switch,
      scopeAcceptedBeforeProviderFailure: scopeAfterProviderFailure,
      scopeAfterOtherTabSwitch,
    },
    restoreRequests,
    clearRequests: scopeClearRequests,
    model: "fixture replies; backend model chunks verified by pytest lifecycle tests",
  }));
  await otherTab.close();
  await page.close();
} finally {
  await browser.close();
}

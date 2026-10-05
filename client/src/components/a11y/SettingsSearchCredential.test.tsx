import "@testing-library/jest-dom/vitest";
import axe from "axe-core";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Layout from "@/components/Layout";
import Settings from "@/pages/Settings";

const { apiDelete, apiGet, apiPost } = vi.hoisted(() => ({
  apiDelete: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ apiDelete, apiGet, apiPost, ApiError: class ApiError extends Error {}, formatApiErrorDetail: () => "" }));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    isLoggedIn: false,
    logout: vi.fn(),
    permissions: [],
  }),
}));

vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }),
}));

beforeEach(() => {
  localStorage.setItem("lang", "en");
  window.scrollTo = vi.fn();
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/backend-settings") return Promise.resolve({ defaults: {} });
    if (url === "/api/config/search-engines") {
      return Promise.resolve({ engines: [{ id: "brave", name: "Brave Search", configured: false }] });
    }
    if (url === "/api/config/providers") return Promise.resolve({ providers: [] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [] });
    return Promise.resolve({});
  });
  apiDelete.mockResolvedValue({});
  apiPost.mockResolvedValue({});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openSearchCredentialEditor() {
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-search"));
  await user.click(await screen.findByTestId("button-edit-search-brave"));
  return user;
}

describe("search credential save button", () => {
  it("includes the engine target in its English accessible name", async () => {
    await openSearchCredentialEditor();
    expect(screen.getByRole("button", { name: "Save search credential Brave Search" })).toBeInTheDocument();
  });

  it("includes the engine target in its Chinese accessible name", async () => {
    localStorage.setItem("lang", "zh");
    await openSearchCredentialEditor();
    expect(screen.getByRole("button", { name: "保存搜索凭据 Brave Search" })).toBeInTheDocument();
  });

  it("labels the credential input and has no axe violations", async () => {
    await openSearchCredentialEditor();
    const input = screen.getByLabelText("Brave Search");
    expect(input).toHaveAttribute("id", "input-search-key-brave");
    expect((await axe.run(input.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  });

  it("describes a rejected credential save through the real save action", async () => {
    const user = await openSearchCredentialEditor();
    apiPost.mockRejectedValueOnce({ detail: "save failed" });
    await user.type(screen.getByTestId("input-search-key-brave"), "smoke-key");
    await user.click(screen.getByTestId("button-save-search-brave"));
    const alert = await screen.findByTestId("text-search-credential-error");
    expect(alert).toHaveAttribute("id", "error-search-credential");
    expect(alert).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("button-save-search-brave")).toHaveAttribute("aria-describedby", "error-search-credential");
    expect((await axe.run(alert.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  });
});

it("associates a failed AI provider save with its real Save action", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/providers") return Promise.resolve({ providers: [{ provider_id: "openai", display_name: "OpenAI", supports: { chat: true } }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [{ provider_id: "openai", category: "llm", is_default: true, status: "active", source: "db" }] });
    if (url === "/api/config/model-catalog") return Promise.resolve({ available: {} });
    if (url === "/api/config/ai-routing") return Promise.resolve({ bindings: [] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  apiPost.mockRejectedValueOnce({ detail: "credential save failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-edit-provider-openai"));
  await user.type(screen.getByTestId("input-api-key-openai"), "smoke-key");
  await user.click(screen.getByTestId("button-save-provider-openai"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-provider-openai");
  expect(screen.getByTestId("button-save-provider-openai")).toHaveAttribute("aria-describedby", "error-settings-provider-openai");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("connects Mathpix API-key help only to the Mathpix key field", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/providers") return Promise.resolve({ providers: [{ provider_id: "mathpix", display_name: "Mathpix", supports: { ocr: true } }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [{ provider_id: "mathpix", category: "llm", is_default: true, status: "active", source: "db" }] });
    if (url === "/api/config/model-catalog") return Promise.resolve({ available: {} });
    if (url === "/api/config/ai-routing") return Promise.resolve({ bindings: [] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  const user = userEvent.setup(); render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-edit-provider-mathpix"));
  const key = screen.getByTestId("input-api-key-mathpix");
  expect(key).toHaveAttribute("aria-describedby", "hint-mathpix-api-key");
  expect(document.getElementById("hint-mathpix-api-key")?.textContent?.trim()).not.toBe("");
  expect((await axe.run(key.parentElement!.parentElement!, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates a failed AI provider delete with only its real Delete action", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/providers") return Promise.resolve({ providers: [{ provider_id: "openai", display_name: "OpenAI", supports: { chat: true } }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [{ provider_id: "openai", category: "llm", is_default: true, status: "active", source: "db" }] });
    if (url === "/api/config/model-catalog") return Promise.resolve({ available: {} });
    if (url === "/api/config/ai-routing") return Promise.resolve({ bindings: [] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  apiDelete.mockRejectedValueOnce({ detail: "delete failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-delete-provider-openai"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-delete-provider-openai");
  expect(screen.getByTestId("button-delete-provider-openai")).toHaveAttribute("aria-describedby", "error-settings-delete-provider-openai");
  expect(screen.getByTestId("button-edit-provider-openai")).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates failed AI maintenance with only the initiating action", async () => {
  apiPost.mockRejectedValueOnce({ detail: "import failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-import-provider-env"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-import-provider-env");
  expect(screen.getByTestId("button-import-provider-env")).toHaveAttribute("aria-describedby", "error-settings-import-provider-env");
  expect(screen.getByTestId("button-refresh-model-catalog")).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates failed model-catalog refresh with only Refresh models", async () => {
  apiGet.mockImplementation((url: string) => url.includes("?refresh=true") ? Promise.reject({ detail: "refresh failed" }) : Promise.resolve({ defaults: {}, engines: [], available: {} }));
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-refresh-model-catalog"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-refresh-model-catalog");
  expect(screen.getByTestId("button-refresh-model-catalog")).toHaveAttribute("aria-describedby", "error-settings-refresh-model-catalog");
  expect(screen.getByTestId("button-import-provider-env")).not.toHaveAttribute("aria-describedby");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates failed routing save with only the routing Save action", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/providers") return Promise.resolve({ providers: [{ provider_id: "openai", display_name: "OpenAI", supports: { chat: true } }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [{ provider_id: "openai", credential_id: "cred-smoke", category: "llm", source: "db", status: "active" }] });
    if (url === "/api/config/model-catalog") return Promise.resolve({ available: { openai: [{ name: "gpt-smoke", types: ["chatbot"] }] } });
    if (url === "/api/config/ai-routing") return Promise.resolve({ bindings: [] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  apiPost.mockRejectedValueOnce({ detail: "routing failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-add-model-route"));
  expect(screen.getByTestId("button-stage-model-route")).toHaveClass("min-h-[48px]");
  await user.selectOptions(screen.getByTestId("select-add-model-function"), "chat");
  await user.selectOptions(screen.getByTestId("select-add-model-provider"), "openai");
  await user.selectOptions(screen.getByTestId("select-add-model-name"), "gpt-smoke");
  await user.click(screen.getByTestId("button-stage-model-route"));
  await user.click(screen.getByTestId("button-save-models"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-save-models");
  expect(screen.getByTestId("button-save-models")).toHaveAttribute("aria-describedby", "error-settings-save-models");
  expect(screen.getByTestId("button-add-model-route")).not.toHaveAttribute("aria-describedby");
});

it("omits an unresolved saved credential from an unchanged routing save", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/providers") return Promise.resolve({ providers: [{ provider_id: "openai", display_name: "OpenAI", supports: { chat: true } }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [] });
    if (url === "/api/config/model-catalog") return Promise.resolve({ available: { openai: [{ name: "gpt-smoke", types: ["chatbot"] }] } });
    if (url === "/api/config/ai-routing") return Promise.resolve({ bindings: [{ function_name: "chat", provider: "openai", model: "gpt-smoke", credential_id: null, stable_credential_id: null, credential_error: "credential_not_found", configured: false }] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  expect(await screen.findByTestId("model-row-chat")).toBeInTheDocument();
  await user.click(await screen.findByTestId("button-edit-model-chat"));
  await user.click(screen.getByTestId("button-save-models"));
  const routingCall = apiPost.mock.calls.find(([url]) => url === "/api/config/ai-routing");
  expect(routingCall).toBeDefined();
  expect(routingCall![1].bindings).toEqual([
    { function_name: "chat", provider: "openai", model: "gpt-smoke" },
  ]);
});

function mockConfiguredChatRoute(rawConfig: Record<string, unknown>) {
  const credentialId = "openai:llm:instance:primary";
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/providers") return Promise.resolve({ providers: [{ provider_id: "openai", display_name: "OpenAI", supports: { chat: true } }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [{ provider_id: "openai", credential_id: credentialId, stable_credential_id: credentialId, category: "llm", source: "db", status: "active", is_default: true }] });
    if (url === "/api/config/model-catalog") return Promise.resolve({ available: { openai: [{ name: "gpt-smoke", types: ["chatbot"] }] } });
    if (url === "/api/config/ai-routing") return Promise.resolve({ bindings: [{ function_name: "chat", provider: "openai", model: "gpt-smoke", credential_id: credentialId, stable_credential_id: credentialId, credential_error: null, configured: true, raw_config: rawConfig }] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
}

async function editConfiguredChatRoute(rawConfig: Record<string, unknown>) {
  mockConfiguredChatRoute(rawConfig);
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-edit-model-chat"));
  return user;
}

it("does not pin an inherited default credential on a no-op route save", async () => {
  const user = await editConfiguredChatRoute({ provider: "openai", model: "gpt-smoke" });
  expect(screen.getByTestId("select-credential-chat")).toHaveValue("");
  await user.click(screen.getByTestId("button-save-models"));
  const call = apiPost.mock.calls.find(([url]) => url === "/api/config/ai-routing");
  expect(call![1].bindings).toEqual([
    { function_name: "chat", provider: "openai", model: "gpt-smoke" },
  ]);
});

it("sends a credential when the user explicitly selects it", async () => {
  const user = await editConfiguredChatRoute({ provider: "openai", model: "gpt-smoke" });
  await user.selectOptions(screen.getByTestId("select-credential-chat"), "openai:llm:instance:primary");
  await user.click(screen.getByTestId("button-save-models"));
  const call = apiPost.mock.calls.find(([url]) => url === "/api/config/ai-routing");
  expect(call![1].bindings).toEqual([
    { function_name: "chat", provider: "openai", model: "gpt-smoke", credential_id: "openai:llm:instance:primary" },
  ]);
});

it("sends an empty credential when the user explicitly clears it", async () => {
  const user = await editConfiguredChatRoute({
    provider: "openai",
    model: "gpt-smoke",
    credential_id: "openai:llm:instance:primary",
  });
  await user.selectOptions(screen.getByTestId("select-credential-chat"), "");
  await user.click(screen.getByTestId("button-save-models"));
  const call = apiPost.mock.calls.find(([url]) => url === "/api/config/ai-routing");
  expect(call![1].bindings).toEqual([
    { function_name: "chat", provider: "openai", model: "gpt-smoke", credential_id: "" },
  ]);
});

it("associates failed credential re-encryption with its submit action", async () => {
  apiPost.mockRejectedValueOnce({ detail: "re-encryption failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(await screen.findByTestId("button-reencrypt-credentials"));
  await user.type(screen.getByTestId("input-old-encryption-key"), "old-key");
  await user.click(screen.getByTestId("button-submit-reencrypt-credentials"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-reencrypt-credentials");
  expect(screen.getByTestId("button-submit-reencrypt-credentials")).toHaveAttribute("aria-describedby", "error-settings-reencrypt-credentials");
  expect(screen.getByTestId("button-import-provider-env")).not.toHaveAttribute("aria-describedby");
});

it("associates a failed Search defaults save with the defaults action", async () => {
  apiPost.mockRejectedValueOnce({ detail: "defaults failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-search"));
  await user.type(await screen.findByTestId("input-max-pages"), "2");
  await user.click(screen.getByTestId("button-save-defaults"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-save-defaults");
  expect(screen.getByTestId("button-save-defaults")).toHaveAttribute("aria-describedby", "error-settings-save-defaults");
});

it("associates failed categories and token mutations with their respective actions", async () => {
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);

  await user.click(screen.getByTestId("tab-categories"));
  const newCategory = await screen.findByTestId("input-new-category");
  expect((newCategory as HTMLInputElement).labels?.[0]).not.toHaveClass("sr-only");
  expect(screen.getByTestId("input-ai-filter-keywords")).toHaveAttribute("aria-labelledby", "heading-ai-filter-keywords");
  expect(document.getElementById("heading-ai-filter-keywords")).not.toHaveClass("sr-only");
  await user.type(newCategory, "Smoke");
  await user.click(screen.getByTestId("button-add-category"));
  apiPost.mockRejectedValueOnce({ detail: "categories failed" });
  await user.click(screen.getByTestId("button-save-categories"));
  let alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-categories-save");
  expect(screen.getByTestId("button-save-categories")).toHaveAttribute("aria-describedby", "error-settings-categories-save");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);

  await user.click(screen.getByTestId("tab-tokens"));
  await user.click(await screen.findByTestId("button-create-token"));
  await user.type(screen.getByTestId("input-token-subject"), "smoke");
  apiPost.mockRejectedValueOnce({ detail: "token failed" });
  await user.click(screen.getByTestId("button-submit-token"));
  alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-create-token");
  expect(screen.getByTestId("button-submit-token")).toHaveAttribute("aria-describedby", "error-settings-create-token");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates failed Search credential Delete with only that Delete action", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/search-engines") return Promise.resolve({ engines: [{ id: "brave", name: "Brave Search", configured: true }] });
    if (url === "/api/config/provider-credentials") return Promise.resolve({ credentials: [{ provider_id: "brave_search", category: "search", source: "db" }] });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  apiDelete.mockRejectedValueOnce({ detail: "delete failed" });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-search"));
  await user.click(await screen.findByTestId("button-delete-search-brave"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-delete-search-brave");
  expect(screen.getByTestId("button-delete-search-brave")).toHaveAttribute("aria-describedby", "error-settings-delete-search-brave");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates failed API Token revoke with only that revoke action", async () => {
  apiGet.mockImplementation((url: string) => url === "/api/auth/tokens" ? Promise.resolve({ tokens: [{ id: 10, subject: "Smoke", group_name: "registered", token_type: "standard", is_active: true, status: "active", created_at: null, expires_at: "2030-01-01T00:00:00Z", last_used_at: null, revoked_at: null }] }) : Promise.resolve({ defaults: {}, engines: [] }));
  apiPost.mockRejectedValueOnce({ detail: "revoke failed" });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-tokens"));
  await user.click(await screen.findByTestId("button-revoke-token-10"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-revoke-token-10");
  expect(screen.getByTestId("button-revoke-token-10")).toHaveAttribute("aria-describedby", "error-settings-revoke-token-10");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates failed System save with only the System save action", async () => {
  apiGet.mockImplementation((url: string) => url === "/api/config/backend-settings"
    ? Promise.resolve({ features: { enable_file_deletion: false, require_auth: false, enable_global_logs_api: false, enable_rate_limiting: false, enable_csrf: false, enable_security_headers: false, expose_error_details: false } })
    : Promise.resolve({ defaults: {}, engines: [] }));
  apiPost.mockRejectedValueOnce({ detail: "system failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-system"));
  await user.type(await screen.findByTestId("input-rate-limit-defaults"), "x");
  await user.click(screen.getByTestId("button-save-system"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-system-save");
  expect(screen.getByTestId("button-save-system")).toHaveAttribute("aria-describedby", "error-settings-system-save");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("associates a failed catalog prompt save with that prompt action", async () => {
  apiGet.mockImplementation((url: string) => {
    if (url === "/api/config/ai-models") return Promise.resolve({ current: { catalog: { system_prompt: "existing" } } });
    return Promise.resolve({ defaults: {}, engines: [] });
  });
  apiPost.mockRejectedValueOnce({ detail: "prompt failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-prompts"));
  await user.click(await screen.findByTestId("catalog-prompt-edit"));
  await user.click(screen.getByTestId("catalog-prompt-save"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-catalog-prompt");
  expect(screen.getByTestId("catalog-prompt-save")).toHaveAttribute("aria-describedby", "error-settings-catalog-prompt");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

it("labels and describes a failed weekly prompt save through its own action", async () => {
  apiGet.mockImplementation((url: string) => url === "/api/config/ai-models"
    ? Promise.resolve({ current: { weekly_explanation: { prompt: "existing" } } })
    : Promise.resolve({ defaults: {}, engines: [] }));
  apiPost.mockRejectedValueOnce({ detail: "prompt failed" });
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-prompts"));
  await user.click(await screen.findByTestId("weekly-explanation-prompt-edit"));
  const input = screen.getByTestId("weekly-explanation-prompt-input");
  expect(input).toHaveAttribute("aria-labelledby", "weekly-explanation-prompt-title");
  expect(document.getElementById("weekly-explanation-prompt-title")?.textContent?.trim()).not.toBe("");
  expect(screen.getByTestId("weekly-explanation-prompt-cancel")).toHaveClass("min-h-[48px]");
  await user.click(screen.getByTestId("weekly-explanation-prompt-save"));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveAttribute("id", "error-settings-weekly-explanation-prompt");
  expect(screen.getByTestId("weekly-explanation-prompt-save")).toHaveAttribute("aria-describedby", "error-settings-weekly-explanation-prompt");
  expect((await axe.run(alert, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});

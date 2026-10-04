import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Layout from "@/components/Layout";
import Settings from "@/pages/Settings";

const { apiGet, apiPost, actor } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), actor: { user: { id: 1 as number | null, email: "admin@example.test" as string | null, role: "admin" } } }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, apiDelete: vi.fn(), ApiError: class extends Error {}, formatApiErrorDetail: () => "" }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ ...actor, permissions: ["tokens.manage"], isLoggedIn: true, logout: vi.fn() }) }));
vi.mock("@/hooks/use-theme", () => ({ useTheme: () => ({ theme: "light", toggleTheme: vi.fn() }) }));
const metadata = { id: 10, subject: "Automation", group_name: "admin", token_type: "service", created_at: "2026-01-01T12:00:00+00:00", expires_at: null, last_used_at: "2026-01-02T12:00:00+00:00", status: "active", is_active: true, revoked_at: null };
beforeEach(() => {
  localStorage.setItem("lang", "en");
  window.scrollTo = vi.fn();
  actor.user = { id: 1, email: "admin@example.test", role: "admin" };
  apiGet.mockImplementation(async (url: string) => url === "/api/auth/tokens" ? { tokens: [metadata, { ...metadata, id: 11, subject: "Expired", token_type: "standard", expires_at: "2026-01-03T12:00:00+00:00", status: "expired" }, { ...metadata, id: 12, subject: "Revoked", status: "revoked", is_active: false }] } : {});
  apiPost.mockResolvedValue({ success: true, token: "one-time-plaintext", metadata });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
async function openTokens() {
  const user = userEvent.setup();
  render(<Layout><Settings /></Layout>);
  await user.click(screen.getByTestId("tab-tokens"));
  await screen.findByTestId("token-row-10");
  await user.click(screen.getByTestId("button-create-token"));
  await user.type(screen.getByTestId("input-token-subject"), "New token");
  return user;
}
it("uses canonical groups, seven-day admin default and 1/7/30/custom expiry", async () => {
  const user = await openTokens();
  const groups = screen.getByTestId("select-token-group");
  expect(Array.from(groups.querySelectorAll("option")).map(o => o.value)).toEqual(["registered", "premium", "operator", "admin"]);
  await user.selectOptions(groups, "admin");
  expect(screen.getByTestId("select-token-expiry")).toHaveValue("7");
  for (const days of ["1", "7", "30"]) {
    await user.selectOptions(screen.getByTestId("select-token-expiry"), days);
    await user.click(screen.getByTestId("button-submit-token"));
    await screen.findByTestId("text-created-token");
    const payload = apiPost.mock.calls.at(-1)![1];
    expect(payload.group_name).toBe("admin");
    expect(payload.group).toBeUndefined();
    expect(Math.round((Date.parse(payload.expires_at) - Date.now()) / 86400000)).toBe(Number(days));
  }
  await user.selectOptions(screen.getByTestId("select-token-expiry"), "custom");
  expect(screen.getByTestId("button-submit-token")).toBeDisabled();
  await user.type(screen.getByTestId("input-token-expiry"), "2030-01-01T12:00");
  await user.click(screen.getByTestId("button-submit-token"));
  expect(apiPost.mock.calls.at(-1)![1].expires_at).toBe(new Date("2030-01-01T12:00").toISOString());
});
it("translates canonical role choices while retaining submitted values", async () => {
  const user = await openTokens();
  const groups = screen.getByTestId("select-token-group");
  const values = () => Array.from(groups.querySelectorAll("option")).map((o) => o.value);
  const labels = () => Array.from(groups.querySelectorAll("option")).map((o) => o.textContent);
  expect(values()).toEqual(["registered", "premium", "operator", "admin"]);
  expect(labels()).toEqual(["Registered", "Premium", "Operator", "Administrator"]);
  await user.click(screen.getByTestId("toggle-lang"));
  expect(labels()).toEqual(["注册用户", "Premium 用户", "操作员", "管理员"]);
  await user.selectOptions(groups, "operator");
  await user.click(screen.getByTestId("button-submit-token"));
  await screen.findByTestId("text-created-token");
  expect(apiPost.mock.calls.at(-1)![1].group_name).toBe("operator");
});
it("shows complete metadata, local dates with UTC titles, and confirmed service creation", async () => {
  const user = await openTokens();
  const row = screen.getByTestId("token-row-10");
  expect(screen.getByTestId("token-role-10")).toHaveTextContent("Administrator");
  expect(row).toHaveTextContent("Service");
  expect(row).toHaveTextContent("Active");
  expect(row).toHaveTextContent("No expiry");
  const time = row.querySelector("time")!;
  expect(time.title).toBe("2026-01-01T12:00:00.000Z (UTC)");
  expect(time.textContent).toBe(new Date(metadata.created_at).toLocaleString());
  expect(screen.getByTestId("token-row-11")).toHaveTextContent("Expired");
  expect(screen.getByTestId("token-row-12")).toHaveTextContent("Revoked");
  await user.selectOptions(screen.getByTestId("select-token-type"), "service");
  expect(screen.getByTestId("token-service-warning")).toHaveTextContent("administrator");
  expect(screen.getByTestId("button-submit-token")).toBeDisabled();
  await user.click(screen.getByTestId("confirm-service-token"));
  await user.click(screen.getByTestId("button-submit-token"));
  await screen.findByTestId("text-created-token");
  expect(apiPost.mock.calls.at(-1)![1]).toEqual({ subject: "New token", group_name: "admin", token_type: "service", expires_at: null, confirm_service: true });
});
it("does not offer service creation for API-token identity", async () => {
  actor.user = { id: null, email: null, role: "admin" };
  await openTokens();
  expect(screen.queryByTestId("select-token-type")).not.toBeInTheDocument();
});
it("translates stored canonical roles in both locales while preserving create values", async () => {
  const roles = ["registered", "premium", "operator", "admin"];
  apiGet.mockImplementation(async (url: string) => url === "/api/auth/tokens" ? { tokens: [metadata, ...roles.map((group_name, i) => ({ ...metadata, id: 20 + i, group_name }))] } : {});
  const user = await openTokens();
  ["Registered", "Premium", "Operator", "Administrator"].forEach((label, i) => expect(screen.getByTestId(`token-role-${20 + i}`)).toHaveTextContent(label));
  await user.click(screen.getByTestId("toggle-lang"));
  ["注册用户", "Premium 用户", "操作员", "管理员"].forEach((label, i) => expect(screen.getByTestId(`token-role-${20 + i}`)).toHaveTextContent(label));
  const groups = screen.getByTestId("select-token-group");
  expect(Array.from(groups.querySelectorAll("option")).map(o => o.value)).toEqual(roles);
  await user.selectOptions(groups, "premium");
  await user.click(screen.getByTestId("button-submit-token"));
  await screen.findByTestId("text-created-token");
  expect(apiPost.mock.calls.at(-1)![1].group_name).toBe("premium");
});
it("hides historical token role codes from customers", async () => {
  apiGet.mockImplementation(async (url: string) => url === "/api/auth/tokens" ? { tokens: [metadata, { ...metadata, id: 30, group_name: "catalog_only" }] } : {});
  actor.user = { id: 2, email: "customer@example.test", role: "registered" };
  await openTokens();
  expect(screen.getByTestId("token-role-30")).toHaveTextContent("Unknown status");
  expect(screen.getByTestId("token-row-30")).not.toHaveTextContent("catalog_only");
  expect(screen.queryByTestId("token-row-30")?.querySelector("details")).toBeNull();
});
it("shows historical token role codes only in collapsed privileged diagnostics", async () => {
  apiGet.mockImplementation(async (url: string) => url === "/api/auth/tokens" ? { tokens: [metadata, { ...metadata, id: 31, group_name: "catalog_only" }] } : {});
  actor.user = { id: 3, email: "operator@example.test", role: "operator" };
  await openTokens();
  const row = screen.getByTestId("token-row-31");
  expect(row.querySelector("details")).not.toHaveAttribute("open");
  expect(row.querySelector("details")).toHaveTextContent("catalog_only");
});

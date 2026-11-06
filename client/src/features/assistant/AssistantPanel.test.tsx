import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import axe from "axe-core";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, ApiError: class extends Error {} }));
vi.mock("@/components/Layout", () => ({ useTranslation: () => ({ lang: "en", t: (key: string) => key }) }));
vi.mock("wouter", () => ({ useLocation: () => ["/database", vi.fn()] }));
import AssistantPanel from "./AssistantPanel";
import SupportWidget from "@/components/support-widget/SupportWidget";

const t = (key: string, values?: Record<string, string | number>) => values ? `${key}:${values.id}` : key;
const reply = (intent = "feedback") => ({ intent, answer: "Review first", citations: [], feedback_draft: intent === "feedback" ? "Do not substitute summary" : null, availability: "available", error_code: null, generation_attempts: 1, embedding_attempts: 0 });
const ref = { doc_id: "user-guide-en", section_id: "file-details", language: "en", title: "Guide", source_version: "1.0.0", content_hash: "a".repeat(64) };

beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "one-request") }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show(feedbackEnabled = true, lang = "en") { return render(<AssistantPanel t={t} lang={lang} open feedbackEnabled={feedbackEnabled} onClose={vi.fn()} />); }
function question(value = "Original user text") { fireEvent.change(screen.getByLabelText("assistant.message"), { target: { value } }); fireEvent.click(screen.getByRole("button", { name: "assistant.ask" })); }

it("manual feedback uses the ordinary form without any assistant request", async () => {
  show();
  fireEvent.change(screen.getByLabelText("assistant.message"), { target: { value: "Original" } });
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  expect(await screen.findByLabelText("feedback.content")).toHaveValue("Original");
  expect(apiPost).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  expect(screen.getByLabelText("assistant.message")).toBeVisible();
  expect(apiPost).not.toHaveBeenCalled();
});

it("forced feedback classification remains an editable original draft until confirmation and reuses id on retry", async () => {
  apiPost.mockResolvedValueOnce(reply()).mockRejectedValueOnce(new Error("lost receipt")).mockResolvedValueOnce({ feedback_id: "db-receipt", status: "recorded", created_at: "now" });
  show(); question();
  const draft = await screen.findByLabelText("feedback.content");
  expect(draft).toHaveValue("Original user text");
  expect(apiPost).toHaveBeenCalledTimes(1);
  fireEvent.change(draft, { target: { value: "Confirmed edited text" } });
  fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
  await screen.findByRole("alert");
  const submitted = apiPost.mock.calls[1][1];
  expect(submitted.content).toBe("Confirmed edited text");
  fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
  expect(await screen.findByRole("status")).toHaveTextContent("db-receipt");
  expect(apiPost.mock.calls[2][1]).toEqual(submitted);
  expect(apiPost.mock.calls.map((call) => call[0])).toEqual(["/api/assistant/query", "/api/feedback", "/api/feedback"]);
});

it("cancel and Q&A never call feedback", async () => {
  apiPost.mockResolvedValueOnce(reply()).mockResolvedValueOnce(reply("knowledge"));
  show(); question();
  await screen.findByLabelText("feedback.content");
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  question("Subject question");
  await screen.findByText("Subject question", { selector: "article p" });
  expect(apiPost.mock.calls.every((call) => call[0] === "/api/assistant/query")).toBe(true);
});

it("independent assistant-only flag exposes questions without a submit action", async () => {
  apiGet.mockResolvedValue({ feedback_enabled: false, assistant_enabled: true });
  apiPost.mockResolvedValue(reply());
  render(<SupportWidget />);
  fireEvent.click(await screen.findByTestId("support-widget-trigger"));
  await screen.findByLabelText("assistant.message"); question();
  await screen.findByText("Review first");
  expect(screen.queryByRole("button", { name: "assistant.feedback" })).not.toBeInTheDocument();
  expect(screen.queryByTestId("feedback-submit")).not.toBeInTheDocument();
});

it("explicit choice and Chinese locale are sent with only the current question", async () => {
  apiPost.mockResolvedValue(reply("usage")); show(true, "zh");
  fireEvent.change(screen.getByLabelText("assistant.mode"), { target: { value: "usage" } });
  question("怎样提交建议");
  await screen.findByText("Review first");
  expect(apiPost).toHaveBeenCalledWith("/api/assistant/query", { message: "怎样提交建议", mode: "usage", locale: "zh" });
});

it("errors and malformed responses can be retried without feedback", async () => {
  apiPost.mockResolvedValueOnce({ intent: "unexpected" }).mockResolvedValueOnce(reply("clarify"));
  show(); question(); await screen.findByRole("alert");
  question(); await screen.findByText("assistant.choose");
  expect(apiPost.mock.calls.every((call) => call[0] === "/api/assistant/query")).toBe(true);
});

it("renders safe Markdown and opens the exact help reference", async () => {
  apiPost.mockResolvedValue({ ...reply("usage"), answer: "<script>alert(1)</script> [unsafe](javascript:alert(1))", citations: [ref] });
  apiGet.mockResolvedValue({ ...ref, content: "**Current guide**" });
  const { container } = show(); question();
  fireEvent.click(await screen.findByRole("button", { name: /Guide \/ file-details/ }));
  expect(await screen.findByTestId("assistant-help-section")).toHaveTextContent("Current guide");
  expect(apiGet).toHaveBeenCalledWith(`/api/assistant/help/section?${new URLSearchParams(ref)}`);
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
});

it("reads the static guide without AI and reports stale references", async () => {
  apiGet.mockResolvedValueOnce({ results: [ref] }).mockRejectedValueOnce(new Error("410"));
  show(); fireEvent.click(screen.getByRole("button", { name: "assistant.guide" }));
  fireEvent.click(await screen.findByRole("button", { name: "file-details (1.0.0)" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("assistant.help_error");
  expect(apiPost).not.toHaveBeenCalled();
});

it("unmount clears history and ignores a late response", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockImplementation(() => new Promise((done) => { resolve = done; }));
  const first = show(); question(); first.unmount(); show();
  resolve(reply());
  await waitFor(() => expect(screen.queryByText("Review first")).not.toBeInTheDocument());
  expect(screen.queryByLabelText("feedback.content")).not.toBeInTheDocument();
});

it("a late automatic draft cannot replace a manually opened feedback form", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockImplementation(() => new Promise((done) => { resolve = done; }));
  show(); question("Question still pending");
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  const draft = await screen.findByLabelText("feedback.content");
  fireEvent.change(draft, { target: { value: "Manual edited draft" } });
  resolve(reply());
  await waitFor(() => expect(draft).toHaveValue("Manual edited draft"));
  expect(apiPost).toHaveBeenCalledTimes(1);
});

it("has no axe violations in its accessible controls", async () => {
  const { container } = show();
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations).toEqual([]);
});

it("retries a rejected feedback import after the outer widget remounts the assistant", async () => {
  vi.resetModules();
  let loadAttempts = 0;
  vi.doMock("@/features/feedback/FeedbackForm", async () => {
    loadAttempts += 1;
    if (loadAttempts === 1) throw new Error("synthetic feedback chunk failure");
    return vi.importActual("@/features/feedback/FeedbackForm");
  });
  try {
    apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: true });
    const { default: RetryWidget } = await import("@/components/support-widget/SupportWidget");
    render(<RetryWidget />);
    fireEvent.click(await screen.findByTestId("support-widget-trigger"));
    fireEvent.click(await screen.findByRole("button", { name: "assistant.feedback" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("feedback.load_error");

    fireEvent.click(screen.getByRole("button", { name: "feedback.retry" }));
    fireEvent.click(await screen.findByRole("button", { name: "assistant.feedback" }));
    expect(await screen.findByLabelText("feedback.content")).toBeVisible();
    expect(loadAttempts).toBe(2);
    expect(apiPost).not.toHaveBeenCalled();
  } finally {
    vi.doUnmock("@/features/feedback/FeedbackForm");
  }
});

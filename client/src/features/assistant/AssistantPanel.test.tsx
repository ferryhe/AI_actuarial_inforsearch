import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import { useI18n } from "@/hooks/use-i18n";

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, ApiError: class extends Error {} }));
vi.mock("@/components/Layout", () => ({ useTranslation: () => ({ lang: "en", t: (key: string) => key }) }));
vi.mock("wouter", () => ({ useLocation: () => ["/database", vi.fn()] }));
import AssistantPanel from "./AssistantPanel";
import SupportWidget from "@/components/support-widget/SupportWidget";

const t = (key: string, values?: Record<string, string | number>) => values ? `${key}:${values.id}` : key;
const reply = (intent = "feedback") => ({ intent, answer: "Review first", citations: [], feedback_draft: intent === "feedback" ? "Do not substitute summary" : null, availability: "available", error_code: null, generation_attempts: 1, embedding_attempts: 0 });
const ref = { doc_id: "user-guide-en", section_id: "file-details", language: "en", title: "Guide", source_version: "1.0.0", content_hash: "a".repeat(64) };

function LocalizedAssistant({ lang }: { lang: string }) {
  const { t } = useI18n();
  return <AssistantPanel t={t} lang={lang} open feedbackEnabled onClose={vi.fn()} />;
}

beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "one-request") }); });
afterEach(() => { cleanup(); localStorage.removeItem("lang"); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

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

it("uses automatic routing with one freeform question input", async () => {
  apiPost.mockResolvedValue(reply("usage")); show(true, "zh");
  expect(screen.queryByLabelText("assistant.mode")).not.toBeInTheDocument();
  expect(screen.getByLabelText("assistant.message")).toBeVisible();
  question("怎样提交建议");
  await screen.findByText("Review first");
  expect(apiPost).toHaveBeenCalledWith("/api/assistant/query", { message: "怎样提交建议", mode: "auto", locale: "zh" });
});

it.each([
  ["en", "Help", "Please add more detail or rephrase your question."],
  ["zh", "帮助", "请补充更多细节或换一种方式提问。"],
])("clarification recovery text asks for a clearer question in %s without removed type choices", async (lang, questionText, recoveryText) => {
  localStorage.setItem("lang", lang);
  apiPost.mockResolvedValue({ ...reply("clarify"), answer: "A clarification response." });
  render(<LocalizedAssistant lang={lang} />);
  const input = document.querySelector("#assistant-message") as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: questionText } });
  fireEvent.submit(input.closest("form")!);
  expect(await screen.findByText(recoveryText, { selector: "#assistant-panel article p" })).toBeInTheDocument();
  const article = document.querySelector("#assistant-panel article")!;
  expect(article.textContent).not.toMatch(/choose|type below|feedback, usage|选择类型|下方选择|点击提建议/i);
  expect(document.querySelectorAll("#assistant-panel select, #assistant-panel [role=combobox], #assistant-panel [role=radiogroup]")).toHaveLength(0);
  expect(apiPost).toHaveBeenCalledWith("/api/assistant/query", { message: questionText, mode: "auto", locale: lang });
});

it("blurs a submitted question and reveals its answer inside the assistant scroll pane", async () => {
  apiPost.mockResolvedValue({ ...reply("knowledge"), answer: Array.from({ length: 80 }, (_, i) => `Answer paragraph ${i}`).join("\n\n") });
  const windowScroll = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show();
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  const form = input.closest("form")!;
  await waitFor(() => expect(input).toHaveFocus());
  container.scrollTop = 15;
  fireEvent.change(input, { target: { value: "A long question".repeat(100) } });
  fireEvent.submit(input.closest("form")!);
  expect(input).not.toHaveFocus();
  await screen.findByText("Answer paragraph 0");
  await waitFor(() => expect(container.scrollTop).toBe(175));
  expect(container).not.toContainElement(form);
  expect(form.parentElement).toBe(document.querySelector("#assistant-panel"));
  expect(input).toBeVisible();
  expect(form.querySelector('button[type="submit"]')).toBeVisible();
  expect(windowScroll).not.toHaveBeenCalled();
});

it("reveals a delayed answer after manual feedback cancellation without refocusing the composer", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockImplementation(() => new Promise((done) => { resolve = done; }));
  const longQuestion = Array.from({ length: 45 }, (_, i) => `Question paragraph ${i}`).join("\n\n");
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show();
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  await waitFor(() => expect(input).toHaveFocus());
  const focus = vi.spyOn(input, "focus");
  container.scrollTop = 25;
  fireEvent.change(input, { target: { value: longQuestion } });
  fireEvent.submit(input.closest("form")!);
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  await screen.findByLabelText("feedback.content");
  container.scrollTop = 0;
  resolve({ ...reply("knowledge"), answer: Array.from({ length: 80 }, (_, i) => `Delayed answer paragraph ${i}`).join("\n\n") });
  await waitFor(() => expect(document.querySelector(".assistant-answer")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  await waitFor(() => expect(container.scrollTop).toBe(160));
  expect(focus).not.toHaveBeenCalled();
  expect(input).not.toHaveFocus();
});

it("reveals a pending reply after cancel when scrolling up to manual feedback", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockResolvedValueOnce({ ...reply("knowledge"), answer: Array.from({ length: 80 }, (_, i) => `Older paragraph ${i}`).join("\n\n") })
    .mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.classList.contains("assistant-answer")) {
      const answers = [...document.querySelectorAll(".assistant-answer")];
      return { top: answers.indexOf(this) === 0 ? 260 : 1340 } as DOMRect;
    }
    return { top: this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show();
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  question("First question");
  await screen.findByText("Older paragraph 0");
  await waitFor(() => expect(container.scrollTop).toBe(160));
  fireEvent.change(input, { target: { value: "Second question" } });
  fireEvent.submit(input.closest("form")!);
  container.scrollTop = 0;
  fireEvent.wheel(container, { deltaY: -200 });
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  await screen.findByLabelText("feedback.content");
  resolve({ ...reply("knowledge"), answer: "Latest delayed answer" });
  await screen.findByText("Latest delayed answer");
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  await waitFor(() => expect(container.scrollTop).toBe(1240));
});

it("does not move the assistant pane when the user reads older answers during a request", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockResolvedValueOnce(reply("knowledge")).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show();
  question("First answer");
  await screen.findByText("Review first");
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  container.scrollTop = 200;
  fireEvent.change(input, { target: { value: "Second question" } });
  fireEvent.submit(input.closest("form")!);
  fireEvent.touchMove(container);
  container.scrollTop = 100;
  resolve({ ...reply("knowledge"), answer: "Second answer" });
  await screen.findByText("Second answer");
  await waitFor(() => expect(container.scrollTop).toBe(100));
});

it("preserves the history position when the user scrolls with its native scrollbar", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockResolvedValueOnce(reply("knowledge")).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0, right: this.classList.contains("overflow-y-auto") ? 300 : 0 } as DOMRect;
  });
  show();
  question("First answer");
  await screen.findByText("Review first");
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  Object.defineProperties(container, { offsetWidth: { configurable: true, value: 300 }, clientWidth: { configurable: true, value: 285 } });
  container.scrollTop = 200;
  fireEvent.change(input, { target: { value: "Second question" } });
  fireEvent.submit(input.closest("form")!);
  fireEvent.mouseDown(container, { clientX: 299 });
  container.scrollTop = 0;
  resolve({ ...reply("knowledge"), answer: "Second answer" });
  await screen.findByText("Second answer");
  await waitFor(() => expect(container.scrollTop).toBe(0));
});

it("preserves older history when Shift+Space scrolls from a citation during a pending reply", async () => {
  let resolve!: (value: unknown) => void;
  const citation = { source_type: "kb", file_id: "source", section_id: "section-1", kb_id: "public", title: "Older citation", link: "/file-detail?url=source", source_version: "publication-1", source_date: "2026-11-06", stale: false };
  apiPost.mockResolvedValueOnce({ ...reply("knowledge"), citations: [citation] }).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show();
  question("First answer");
  const link = await screen.findByRole("link", { name: /Older citation/ });
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  container.scrollTop = 4096;
  fireEvent.change(input, { target: { value: "Second question" } });
  fireEvent.submit(input.closest("form")!);
  link.focus();
  fireEvent.keyDown(link, { key: " ", code: "Space", shiftKey: true });
  container.scrollTop = 3979;
  resolve({ ...reply("knowledge"), answer: "Second answer" });
  await screen.findByText("Second answer");
  await waitFor(() => expect(container.scrollTop).toBe(3979));
});

it("does not treat Space activation on the feedback button as history scrolling", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockResolvedValueOnce(reply("knowledge")).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show();
  question("First answer");
  await screen.findByText("Review first");
  const input = screen.getByLabelText("assistant.message");
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;
  container.scrollTop = 200;
  fireEvent.change(input, { target: { value: "Second question" } });
  fireEvent.submit(input.closest("form")!);
  const feedback = screen.getByRole("button", { name: "assistant.feedback" });
  feedback.focus();
  fireEvent.keyDown(feedback, { key: " ", code: "Space" });
  fireEvent.click(feedback);
  await screen.findByLabelText("feedback.content");
  resolve({ ...reply("knowledge"), answer: "Second answer" });
  await screen.findByText("Second answer");
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  await waitFor(() => expect(container.scrollTop).toBe(360));
});

it("restores composer focus after cancel when no new answer arrived", async () => {
  show();
  const input = screen.getByLabelText("assistant.message");
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  await screen.findByLabelText("feedback.content");
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  await waitFor(() => expect(input).toHaveFocus());
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

it("renders catalog and body citations as internal links with versions and nonzero embedding counts", async () => {
  const source = { file_id: "source", section_id: "section-1", kb_id: "public", title: "Body document", link: "/file-detail?url=source", source_version: "publication-1", source_date: "2026-11-06", stale: true };
  apiPost.mockResolvedValue({ ...reply("knowledge"), embedding_attempts: 2, citations: [{ ...source, source_type: "kb" }, { ...source, source_type: "catalog", title: "Directory document", section_id: "", kb_id: null }] });
  show(); question("Body question");
  expect(await screen.findByRole("link", { name: /Body document.*assistant.source_kb/ })).toHaveAttribute("href", "/file-detail?url=source");
  expect(screen.getByRole("link", { name: /Directory document.*assistant.source_catalog/ })).toHaveTextContent("publication-1");
  expect(screen.getByRole("link", { name: /Body document/ })).toHaveTextContent("assistant.stale");
  expect(apiGet).not.toHaveBeenCalled();
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

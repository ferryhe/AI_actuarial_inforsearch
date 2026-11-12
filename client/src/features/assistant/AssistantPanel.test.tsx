import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import { useI18n } from "@/hooks/use-i18n";
import { ApiError } from "@/lib/api";

const { apiGet, apiPost, navigate, route } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), navigate: vi.fn(), route: { current: "/database" } }));
vi.mock("@/lib/api", () => ({ apiGet, apiPost, ApiError: class extends Error { constructor(message: string, public status: number) { super(message); } } }));
vi.mock("@/components/Layout", () => ({ useTranslation: () => ({ lang: "en", t: (key: string) => key }) }));
vi.mock("wouter", () => ({ useLocation: () => [route.current, navigate] }));
import AssistantPanel from "./AssistantPanel";
import { queryAssistant } from "./transport";
import SupportWidget from "@/components/support-widget/SupportWidget";

const t = (key: string, values?: Record<string, string | number>) => values ? `${key}:${values.id}` : key;
const reply = (intent = "feedback") => ({ schema_version: "1.0", stop_reason: intent === "clarify" ? "clarify" : "finish", intent, answer: "Review first", citations: [], evidence_ids: [], selected_target: null, feedback_draft: intent === "feedback" ? "Do not substitute summary" : null, availability: "available", error_code: null, generation_attempts: 1, embedding_attempts: 0 });
const ref = { doc_id: "user-guide-en", section_id: "file-details", language: "en", title: "Guide", source_version: "1.0.0", content_hash: "a".repeat(64) };

function LocalizedAssistant({ lang }: { lang: string }) {
  const { t } = useI18n();
  return <AssistantPanel t={t} lang={lang} open feedbackEnabled onClose={vi.fn()} />;
}

beforeAll(() => {
  const show = function (this: HTMLDialogElement) { this.open = true; };
  Object.assign(HTMLDialogElement.prototype, {
    show,
    showModal: show,
    close(this: HTMLDialogElement) { this.open = false; },
  });
});
beforeEach(() => { route.current = "/database"; navigate.mockReset(); apiGet.mockReset(); apiPost.mockReset(); vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "one-request") }); });
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

it("reopens canceled manual feedback with the original composer text", async () => {
  show();
  fireEvent.change(screen.getByLabelText("assistant.message"), { target: { value: "Original user text" } });
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  const draft = await screen.findByLabelText("feedback.content");
  expect(draft).toHaveValue("Original user text");
  fireEvent.change(draft, { target: { value: "Canceled edit" } });
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  expect(apiPost).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  expect(await screen.findByLabelText("feedback.content")).toHaveValue("Original user text");
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
  expect(apiPost.mock.calls.map((call) => call[0])).toEqual(["/api/assistant/v1/query", "/api/feedback", "/api/feedback"]);
});

it("cancel and Q&A never call feedback", async () => {
  apiPost.mockResolvedValueOnce(reply()).mockResolvedValueOnce(reply("knowledge"));
  show(); question();
  await screen.findByLabelText("feedback.content");
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel" }));
  question("Subject question");
  await screen.findByText("Subject question", { selector: "article p" });
  expect(apiPost.mock.calls.every((call) => call[0] === "/api/assistant/v1/query")).toBe(true);
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

it("does not show the assistant scope note", () => {
  show();
  expect(screen.queryByText("assistant.scope")).not.toBeInTheDocument();
});

it("fits the same assistant drawer when the visual viewport shrinks, pans, and restores", async () => {
  apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: true });
  const viewport = Object.assign(new EventTarget(), { height: 844, offsetTop: 0 });
  vi.stubGlobal("visualViewport", viewport);
  render(<SupportWidget />);
  const trigger = await screen.findByTestId("support-widget-trigger");
  fireEvent.click(trigger);
  const dialog = screen.getByRole<HTMLDialogElement>("dialog", { name: "assistant.title" });
  const input = screen.getByLabelText("assistant.message");
  expect(dialog.style.getPropertyValue("--assistant-viewport-height")).toBe("844px");
  viewport.height = 152;
  viewport.dispatchEvent(new Event("resize"));
  viewport.offsetTop = 680;
  viewport.dispatchEvent(new Event("scroll"));
  expect(dialog.style.getPropertyValue("--assistant-viewport-top")).toBe("680px");
  expect(dialog.style.getPropertyValue("--assistant-viewport-height")).toBe("152px");
  expect(dialog).toHaveAttribute("data-compact-assistant");
  Object.assign(viewport, { height: 844, offsetTop: 0 });
  viewport.dispatchEvent(new Event("resize"));
  expect(dialog.style.getPropertyValue("--assistant-viewport-top")).toBe("0px");
  expect(dialog).not.toHaveAttribute("data-compact-assistant");
  expect(screen.getByLabelText("assistant.message")).toBe(input);
  fireEvent.keyDown(input, { key: "Escape" });
  expect(dialog).not.toHaveAttribute("open");
  await waitFor(() => expect(trigger).toHaveFocus());
});

it("keeps the Chat composer slot available when the assistant launcher is below the visual viewport", async () => {
  route.current = "/chat";
  apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: true });
  vi.stubGlobal("visualViewport", Object.assign(new EventTarget(), { offsetTop: 500, height: 200 }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.hasAttribute("data-support-fixed-anchor")) return { top: 786, bottom: 830, right: 376, height: 44 } as DOMRect;
    return { top: 0, bottom: 0, height: 0 } as DOMRect;
  });
  render(<><div data-chat-composer><div data-chat-support-slot /></div><SupportWidget /></>);
  const trigger = await screen.findByTestId("support-widget-trigger");
  expect(document.querySelector("[data-chat-support-slot]")).toContainElement(trigger);
  fireEvent.click(trigger);
  expect(screen.getByRole("dialog")).toHaveAttribute("data-compact-assistant");
});

it("lifts the launcher into the visual viewport on a page without the Chat composer", async () => {
  route.current = "/weekly";
  apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: true });
  vi.stubGlobal("visualViewport", Object.assign(new EventTarget(), { offsetTop: 500, height: 200 }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return this.hasAttribute("data-support-fixed-anchor")
      ? { top: 786, bottom: 830, right: 376, height: 44 } as DOMRect
      : { top: 0, bottom: 0, height: 0 } as DOMRect;
  });
  render(<SupportWidget />);
  const trigger = await screen.findByTestId("support-widget-trigger");
  const anchor = document.querySelector("[data-support-fixed-anchor]");
  expect(anchor).toContainElement(trigger);
  expect(anchor?.parentElement?.style.getPropertyValue("--assistant-trigger-offset")).toBe("-134px");
});

it("uses automatic routing with one freeform question input", async () => {
  apiPost.mockResolvedValue(reply("usage")); show(true, "zh");
  expect(screen.queryByLabelText("assistant.mode")).not.toBeInTheDocument();
  expect(screen.getByLabelText("assistant.message")).toBeVisible();
  question("怎样提交建议");
  await screen.findByText("Review first");
  expect(apiPost).toHaveBeenCalledWith("/api/assistant/v1/query", { message: "怎样提交建议", locale: "zh", selected_target: null, recent_questions: [] }, { signal: expect.any(AbortSignal) });
});

it("shows a finished answer and its evidence without a clarification prompt", async () => {
  apiPost.mockResolvedValueOnce({ ...reply("answer"), answer: "Sample found", schema_version: "1.0", stop_reason: "finish", evidence_ids: ["test_lookup:sample"] })
    .mockResolvedValueOnce({ ...reply("clarify"), answer: "Which item?", schema_version: "1.0", stop_reason: "clarify", evidence_ids: [] });
  show(false); question("sample");
  await screen.findByText("Sample found");
  expect(screen.getByText("[1] test_lookup:sample")).toBeInTheDocument();
  expect(screen.queryByText("assistant.choose")).not.toBeInTheDocument();
  question("unknown");
  await screen.findByText("Which item?");
  expect(screen.getByText("assistant.choose")).toBeInTheDocument();
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
  expect(apiPost).toHaveBeenCalledWith("/api/assistant/v1/query", { message: questionText, locale: lang, selected_target: null, recent_questions: [] }, { signal: expect.any(AbortSignal) });
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

it("reveals long replies after the twelve-entry cap without taking over manual scrolling", async () => {
  let finishFifteenth!: (value: unknown) => void;
  const answer = (number: number) => ({ ...reply("knowledge"), answer: `Answer ${number}\n\n${"Long paragraph. ".repeat(40)}` });
  apiPost.mockImplementation(() => {
    const number = apiPost.mock.calls.length;
    return number === 15 ? new Promise((done) => { finishFifteenth = done; }) : Promise.resolve(answer(number));
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.classList.contains("assistant-answer") ? 260 : this.classList.contains("overflow-y-auto") ? 100 : 0 } as DOMRect;
  });
  show(false);
  const container = document.querySelector("#assistant-panel .overflow-y-auto") as HTMLDivElement;

  for (let number = 1; number <= 14; number += 1) {
    question(`Question ${number}`);
    await screen.findByText(`Answer ${number}`);
    await waitFor(() => expect(container.scrollTop).toBe(number * 160));
    expect(container.querySelectorAll("article")).toHaveLength(Math.min(number, 12));
  }
  expect(screen.queryByText("Question 1")).not.toBeInTheDocument();

  question("Question 15");
  fireEvent.wheel(container);
  container.scrollTop = 500;
  finishFifteenth(answer(15));
  await screen.findByText("Answer 15");
  await waitFor(() => expect(container.scrollTop).toBe(500));
  expect(container.querySelectorAll("article")).toHaveLength(12);

  fireEvent.click(screen.getByRole("button", { name: "assistant.clear" }));
  container.scrollTop = 0;
  question("Question 16");
  await screen.findByText("Answer 16");
  await waitFor(() => expect(container.scrollTop).toBe(160));
  expect(container.querySelectorAll("article")).toHaveLength(1);
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
  expect(apiPost.mock.calls.every((call) => call[0] === "/api/assistant/v1/query")).toBe(true);
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

it("keeps the guide cleared when its earlier request finishes late", async () => {
  let resolve!: (value: unknown) => void;
  apiGet.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  show(false);
  fireEvent.click(screen.getByRole("button", { name: "assistant.guide" }));
  fireEvent.click(screen.getByRole("button", { name: "assistant.clear" }));
  await act(async () => resolve({ results: [ref] }));
  expect(screen.queryByRole("button", { name: "file-details (1.0.0)" })).not.toBeInTheDocument();
});

it("keeps a help citation cleared when its earlier request finishes late", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockResolvedValue({ ...reply("usage"), citations: [ref] });
  apiGet.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  show(false);
  question("Show the guide section");
  fireEvent.click(await screen.findByRole("button", { name: /Guide \/ file-details/ }));
  fireEvent.click(screen.getByRole("button", { name: "assistant.clear" }));
  await act(async () => resolve({ ...ref, content: "Cleared section" }));
  expect(screen.queryByTestId("assistant-help-section")).not.toBeInTheDocument();
});

it("keeps the newer help citation when an older citation succeeds late", async () => {
  const newer = { ...ref, section_id: "weekly" };
  let resolveOlder!: (value: unknown) => void;
  let resolveNewer!: (value: unknown) => void;
  apiPost.mockResolvedValue({ ...reply("usage"), citations: [ref, newer] });
  apiGet.mockImplementationOnce(() => new Promise((done) => { resolveOlder = done; }))
    .mockImplementationOnce(() => new Promise((done) => { resolveNewer = done; }));
  show(false);
  question("Show both guide sections");
  fireEvent.click(await screen.findByRole("button", { name: /Guide \/ file-details/ }));
  fireEvent.click(screen.getByRole("button", { name: /Guide \/ weekly/ }));
  await act(async () => resolveNewer({ ...newer, content: "Current weekly section" }));
  expect(screen.getByTestId("assistant-help-section")).toHaveTextContent("Current weekly section");
  await act(async () => resolveOlder({ ...ref, content: "Older file section" }));
  expect(screen.getByTestId("assistant-help-section")).toHaveTextContent("Current weekly section");
  expect(screen.getByTestId("assistant-help-section")).not.toHaveTextContent("Older file section");
});

it("ignores an older guide error after a newer help citation succeeds", async () => {
  let rejectOlder!: (reason: Error) => void;
  let resolveNewer!: (value: unknown) => void;
  apiPost.mockResolvedValue({ ...reply("usage"), citations: [ref] });
  apiGet.mockImplementationOnce(() => new Promise((_, reject) => { rejectOlder = reject; }))
    .mockImplementationOnce(() => new Promise((done) => { resolveNewer = done; }));
  show(false);
  question("Show the guide section");
  fireEvent.click(screen.getByRole("button", { name: "assistant.guide" }));
  fireEvent.click(await screen.findByRole("button", { name: /Guide \/ file-details/ }));
  await act(async () => resolveNewer({ ...ref, content: "Current file section" }));
  expect(screen.getByTestId("assistant-help-section")).toHaveTextContent("Current file section");
  await act(async () => rejectOlder(new Error("Old guide failed")));
  expect(screen.getByTestId("assistant-help-section")).toHaveTextContent("Current file section");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("renders catalog and body citations as internal links with versions and nonzero embedding counts", async () => {
  const source = { file_id: "source", section_id: "section-1", kb_id: "public", title: "Body document", link: "/file-detail?url=source", source_version: "publication-1", source_date: "2026-11-06", stale: true };
  apiPost.mockResolvedValue({ ...reply("knowledge"), embedding_attempts: 2, citations: [{ ...source, source_type: "kb" }, { ...source, source_type: "catalog", title: "Directory document", section_id: "", kb_id: null }] });
  show(); question("Body question");
  expect(await screen.findByRole("link", { name: /Body document.*assistant.source_kb/ })).toHaveAttribute("href", "/file-detail?url=source");
  expect(screen.getByRole("link", { name: /Directory document.*assistant.source_catalog/ })).toHaveTextContent("publication-1");
  expect(screen.getByRole("link", { name: /Body document/ })).toHaveTextContent("assistant.stale");
  fireEvent.click(screen.getByRole("link", { name: /Body document/ }));
  expect(navigate).toHaveBeenCalledWith("/file-detail?url=source");
  expect(apiGet).not.toHaveBeenCalled();
});

it("opens an allowed Weekly action without reloading the assistant", async () => {
  apiPost.mockResolvedValue({ ...reply("answer"), answer: "Open [Weekly](/weekly)." });
  show(false); question("How do weekly updates work?");
  fireEvent.click(await screen.findByRole("link", { name: "Weekly" }));
  expect(navigate).toHaveBeenCalledWith("/weekly");
  expect(screen.getByText("How do weekly updates work?", { selector: "article p" })).toBeInTheDocument();
});

it("keeps source-portal navigation and its follow-up in the same mounted conversation", async () => {
  apiGet.mockResolvedValue({ assistant_enabled: true, feedback_enabled: false });
  apiPost.mockResolvedValueOnce({ ...reply("answer"), answer: "Showing 12 of 13 sources; open [Source Portals](/source-portals)." }).mockResolvedValue(reply("answer"));
  const { rerender } = render(<SupportWidget />);
  fireEvent.click(await screen.findByTestId("support-widget-trigger"));
  await screen.findByLabelText("assistant.message");
  question("Which sources are available?");
  fireEvent.click(await screen.findByRole("link", { name: "Source Portals" }));
  expect(navigate).toHaveBeenCalledWith("/source-portals");
  route.current = "/source-portals";
  rerender(<SupportWidget />);
  expect(screen.getByText("Which sources are available?", { selector: "article p" })).toBeInTheDocument();
  question("Which source has SOA material?");
  expect(apiPost.mock.calls[1][1].recent_questions).toEqual(["Which sources are available?"]);
});

it("uses the second verified file card as the target after navigation and a follow-up", async () => {
  const cards = ["first", "second"].map((name, index) => ({
    source_type: "catalog", file_id: `https://example.org/${name}.pdf`, section_id: "", kb_id: index ? "other" : "public", title: `${name} report`,
    link: `/file-detail?url=${encodeURIComponent(`https://example.org/${name}.pdf`)}`, source_version: null, source_date: null, stale: false,
  }));
  apiGet.mockResolvedValue({ assistant_enabled: true, feedback_enabled: false });
  apiPost.mockResolvedValueOnce({ ...reply("answer"), citations: cards, selected_target: null }).mockResolvedValue(reply("answer"));
  const { rerender } = render(<SupportWidget />);
  fireEvent.click(await screen.findByTestId("support-widget-trigger"));
  await screen.findByLabelText("assistant.message");
  question("Show recent reports");
  fireEvent.click(await screen.findByRole("link", { name: /second report/ }));
  expect(navigate).toHaveBeenCalledWith(cards[1].link);
  route.current = cards[1].link;
  rerender(<SupportWidget />);
  expect(screen.getByText("Show recent reports", { selector: "article p" })).toBeInTheDocument();
  question("What does this report say?");
  expect(apiPost.mock.calls[1][1]).toMatchObject({
    selected_target: { kb_id: "other", file_id: cards[1].file_id }, recent_questions: ["Show recent reports"],
  });
});

it("does not carry an older target through an unassigned catalog card", async () => {
  const old = { kb_id: "public", file_id: "https://example.org/old.pdf" };
  const unassigned = { source_type: "catalog", file_id: "https://example.org/new.pdf", section_id: "", kb_id: null, title: "unassigned report", link: "/file-detail?url=https%3A%2F%2Fexample.org%2Fnew.pdf", source_version: null, source_date: null, stale: false };
  apiGet.mockResolvedValue({ assistant_enabled: true, feedback_enabled: false });
  apiPost.mockResolvedValueOnce({ ...reply("answer"), citations: [unassigned], selected_target: old }).mockResolvedValue(reply("answer"));
  const { rerender } = render(<SupportWidget />);
  fireEvent.click(await screen.findByTestId("support-widget-trigger"));
  await screen.findByLabelText("assistant.message");
  question("Find the report");
  fireEvent.click(await screen.findByRole("link", { name: /unassigned report/ }));
  expect(navigate).toHaveBeenCalledWith(unassigned.link);
  route.current = unassigned.link;
  rerender(<SupportWidget />);
  question("What about this one?");
  expect(apiPost.mock.calls[1][1]).toMatchObject({ selected_target: null, opened_file_url: unassigned.file_id, recent_questions: ["Find the report"] });
  fireEvent.click(screen.getByRole("button", { name: "assistant.clear" }));
  question("What else?");
  expect(apiPost.mock.calls[2][1].opened_file_url).toBeUndefined();
});

it("does not replace this session's file context on a modified card click", async () => {
  const old = { kb_id: "public", file_id: "https://example.org/old.pdf" };
  const card = { source_type: "catalog", file_id: "https://example.org/new.pdf", section_id: "", kb_id: null, title: "new report", link: "/file-detail?url=https%3A%2F%2Fexample.org%2Fnew.pdf", source_version: null, source_date: null, stale: false };
  apiPost.mockResolvedValueOnce({ ...reply("answer"), citations: [card], selected_target: old }).mockResolvedValue(reply("answer"));
  show(false);
  question("Find the report");
  const link = await screen.findByRole("link", { name: /new report/ });
  link.addEventListener("click", (event) => event.preventDefault());
  fireEvent.click(link, { ctrlKey: true });
  question("Continue here");
  expect(apiPost.mock.calls[1][1]).toMatchObject({ selected_target: old, recent_questions: ["Find the report"] });
  expect(apiPost.mock.calls[1][1].opened_file_url).toBeUndefined();
  expect(navigate).not.toHaveBeenCalled();
});

it("unmount clears history and ignores a late response", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockImplementation(() => new Promise((done) => { resolve = done; }));
  const first = show(); question(); first.unmount(); show();
  resolve(reply());
  await waitFor(() => expect(screen.queryByText("Review first")).not.toBeInTheDocument());
  expect(screen.queryByLabelText("feedback.content")).not.toBeInTheDocument();
});

it("keeps bounded question context and the selected target across site navigation, then clears both", async () => {
  const target = { kb_id: "public", file_id: "soa-report" };
  apiPost.mockResolvedValueOnce({ ...reply("answer"), selected_target: target }).mockResolvedValueOnce({ ...reply("answer"), selected_target: target }).mockResolvedValue(reply("answer"));
  const { rerender } = show(false);
  question("Latest SOA report");
  await screen.findByText("Latest SOA report", { selector: "article p" });
  rerender(<AssistantPanel t={t} lang="en" open feedbackEnabled={false} onClose={vi.fn()} />);
  question("What does it say?");
  await screen.findByText("What does it say?", { selector: "article p" });
  expect(apiPost.mock.calls[1][1]).toMatchObject({ selected_target: target, recent_questions: ["Latest SOA report"] });
  fireEvent.click(screen.getByRole("button", { name: "assistant.clear" }));
  expect(screen.queryByText("Latest SOA report")).not.toBeInTheDocument();
  question("This week?");
  expect(apiPost.mock.calls[2][1]).toMatchObject({ selected_target: null, recent_questions: [] });
});

it("keeps the mounted assistant history when the host navigates to Weekly", async () => {
  apiGet.mockResolvedValue({ assistant_enabled: true, feedback_enabled: false });
  apiPost.mockResolvedValue(reply("answer"));
  const { rerender } = render(<SupportWidget />);
  fireEvent.click(await screen.findByTestId("support-widget-trigger"));
  await screen.findByLabelText("assistant.message");
  question("Weekly guide");
  await screen.findByText("Weekly guide", { selector: "article p" });
  route.current = "/weekly";
  rerender(<SupportWidget />);
  expect(screen.getByText("Weekly guide", { selector: "article p" })).toBeInTheDocument();
  question("What's new?");
  expect(apiPost.mock.calls[1][1].recent_questions).toEqual(["Weekly guide"]);
});

it("cancels the real request and ignores a response that arrives late", async () => {
  let resolve!: (value: unknown) => void;
  apiPost.mockImplementationOnce(() => new Promise((done) => { resolve = done; })).mockResolvedValueOnce(reply("answer"));
  show(false); question("Slow question");
  const signal = apiPost.mock.calls[0][2].signal as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "assistant.cancel_request" }));
  expect(signal.aborted).toBe(true);
  resolve({ ...reply("answer"), answer: "Outdated answer" });
  question("New question");
  await screen.findByText("New question", { selector: "article p" });
  expect(screen.queryByText("Outdated answer")).not.toBeInTheDocument();
});

it("clears prior answers on identity change", async () => {
  apiPost.mockResolvedValue(reply("answer"));
  const { rerender } = render(<AssistantPanel t={t} lang="en" open feedbackEnabled={false} onClose={vi.fn()} identity="reader-1" />);
  question("Private question");
  await screen.findByText("Private question", { selector: "article p" });
  rerender(<AssistantPanel t={t} lang="en" open feedbackEnabled={false} onClose={vi.fn()} identity="reader-2" />);
  await waitFor(() => expect(screen.queryByText("Private question")).not.toBeInTheDocument());
});

it.each([401, 403])("drops prior evidence and refocuses after a %i permission error", async (status) => {
  const target = { kb_id: "private", file_id: "report" };
  apiPost.mockResolvedValueOnce({ ...reply("answer"), selected_target: target }).mockRejectedValueOnce(new ApiError("Forbidden", status)).mockResolvedValueOnce(reply("answer"));
  show(false); question("Private report");
  await screen.findByText("Private report", { selector: "article p" });
  const input = screen.getByLabelText("assistant.message");
  question("Read it again");
  expect(input).not.toHaveFocus();
  await screen.findByRole("alert");
  expect(screen.queryByText("Private report")).not.toBeInTheDocument();
  await waitFor(() => expect(input).toHaveFocus());
  question("Try after sign-in");
  expect(apiPost.mock.calls[2][1]).toMatchObject({ selected_target: null, recent_questions: [] });
});

it.each([401, 403])("keeps manually edited feedback after a pending query returns %i", async (status) => {
  let rejectQuery!: (reason: unknown) => void;
  apiPost.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectQuery = reject; }));
  const { rerender } = render(<AssistantPanel t={t} lang="en" open feedbackEnabled onClose={vi.fn()} identity="reader-1" />);
  question("Pending question");
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  const draft = await screen.findByLabelText("feedback.content");
  fireEvent.change(draft, { target: { value: "Edited ordinary feedback draft" } });

  await act(async () => { rejectQuery(new ApiError("Permission changed", status)); });
  expect(screen.getByText("assistant.error", { selector: "[role=alert]" })).toBeInTheDocument();
  expect(screen.getByLabelText("feedback.content")).toBeVisible();
  expect(screen.getByLabelText("feedback.content")).toHaveValue("Edited ordinary feedback draft");
  expect(apiPost.mock.calls.map(([path]) => path)).toEqual(["/api/assistant/v1/query"]);

  rerender(<AssistantPanel t={t} lang="en" open feedbackEnabled onClose={vi.fn()} identity="reader-2" />);
  await waitFor(() => expect(screen.queryByLabelText("feedback.content")).not.toBeInTheDocument());
});

it("allows a separate consumer to use the versioned transport contract", async () => {
  apiPost.mockResolvedValue(reply("answer"));
  const controller = new AbortController();
  const result = await queryAssistant({ message: "Overview", locale: "en", selected_target: null, recent_questions: [] }, controller.signal);
  expect(result.schema_version).toBe("1.0");
  expect(apiPost).toHaveBeenCalledWith("/api/assistant/v1/query", { message: "Overview", locale: "en", selected_target: null, recent_questions: [] }, { signal: controller.signal });
  apiPost.mockResolvedValue({ ...reply("answer"), schema_version: "2.0" });
  await expect(queryAssistant({ message: "Overview", locale: "en", selected_target: null, recent_questions: [] }, controller.signal)).rejects.toThrow();
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

it("opens a suggestion from the assistant in the bundled feedback form", async () => {
  apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: true });
  render(<SupportWidget />);
  fireEvent.click(await screen.findByTestId("support-widget-trigger"));
  const input = await screen.findByLabelText("assistant.message");
  fireEvent.change(input, { target: { value: "Keep this suggestion" } });
  fireEvent.click(screen.getByRole("button", { name: "assistant.feedback" }));
  expect(await screen.findByLabelText("feedback.content")).toHaveValue("Keep this suggestion");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(apiPost).not.toHaveBeenCalled();
});

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiGet, apiPost, route } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), route: { value: "/database" } }));
vi.mock("@/lib/api", () => ({ ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }, apiGet, apiPost }));
vi.mock("@/components/Layout", () => ({ useTranslation: () => ({ lang: "en", t: (key: string, values?: Record<string, string>) => values ? `${key}:${values.id}` : key }) }));
vi.mock("wouter", () => ({ useLocation: () => [route.value, vi.fn()] }));

import FeedbackForm from "./FeedbackForm";
import SupportWidget from "@/components/support-widget/SupportWidget";
import { ApiError } from "@/lib/api";

const t = (key: string, values?: Record<string, string | number>) => values ? `${key}:${values.id}` : key;

describe("feedback support widget", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    route.value = "/database";
    window.history.replaceState({}, "", "/");
    vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValueOnce("request-1").mockReturnValueOnce("request-2") });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("only reveals the entry after capabilities enables feedback", async () => {
    apiGet.mockResolvedValue({ feedback_enabled: false, assistant_enabled: false });
    const { rerender } = render(<SupportWidget />);
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith("/api/support/capabilities"));
    expect(screen.queryByTestId("support-widget-trigger")).not.toBeInTheDocument();
    rerender(<SupportWidget />);
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("hides the entry when capabilities fails", async () => {
    apiGet.mockRejectedValue(new Error("offline"));
    render(<SupportWidget />);
    await waitFor(() => expect(apiGet).toHaveBeenCalledOnce());
    expect(screen.queryByTestId("support-widget-trigger")).not.toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("opens the feedback form from the support widget", async () => {
    apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: false });
    render(<SupportWidget />);
    const trigger = await screen.findByTestId("support-widget-trigger");
    fireEvent.click(trigger);
    expect(await screen.findByLabelText("feedback.content")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the draft and request id when the mounted panel closes during an uncertain submission", async () => {
    apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: false });
    let rejectPending!: (error: Error) => void;
    apiPost.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectPending = reject; }))
      .mockResolvedValueOnce({ feedback_id: "receipt-after-reopen", status: "recorded", created_at: "now" });
    render(<SupportWidget />);
    const trigger = await screen.findByTestId("support-widget-trigger");
    fireEvent.click(trigger);
    const textarea = await screen.findByLabelText("feedback.content");
    fireEvent.change(textarea, { target: { value: "Keep this draft while hidden" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());
    const originalId = apiPost.mock.calls[0][1].client_request_id;

    fireEvent.click(trigger);
    expect(textarea).not.toBeVisible();
    fireEvent.click(trigger);
    expect(await screen.findByLabelText("feedback.content")).toHaveValue("Keep this draft while hidden");
    rejectPending(new TypeError("response lost"));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    expect(await screen.findByRole("status")).toHaveTextContent("receipt-after-reopen");
    expect(apiPost).toHaveBeenCalledTimes(2);
    expect(apiPost.mock.calls[1][1].client_request_id).toBe(originalId);
  });

  it("keeps the request id on retry and only shows a server receipt on success", async () => {
    window.history.replaceState({}, "", "/database");
    apiPost.mockRejectedValueOnce(new ApiError("server error", 500)).mockResolvedValueOnce({ feedback_id: "receipt-1", status: "recorded", created_at: "now" });
    render(<FeedbackForm t={t} lang="en" onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("feedback.content"), { target: { value: "A useful suggestion" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    const firstRequest = apiPost.mock.calls[0][1];
    expect(firstRequest).toMatchObject({ content: "A useful suggestion", kind: "suggestion", origin: "widget", page_path: "/database", locale: "en" });

    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    expect(await screen.findByRole("status")).toHaveTextContent("receipt-1");
    expect(apiPost.mock.calls[1][1].client_request_id).toBe(firstRequest.client_request_id);
  });

  it("replays the committed payload and receipt after a language change", async () => {
    window.history.replaceState({}, "", "/chat");
    route.value = "/chat";
    const committed = new Map<string, { payload: Record<string, unknown>; receipt: { feedback_id: string; status: string; created_at: string } }>();
    apiPost.mockImplementation(async (_path, payload) => {
      const saved = committed.get(payload.client_request_id);
      if (!saved) {
        const receipt = { feedback_id: "receipt-after-lost-response", status: "recorded", created_at: "now" };
        committed.set(payload.client_request_id, { payload: { ...payload }, receipt });
        throw new TypeError("response lost after commit");
      }
      expect(payload).toEqual(saved.payload);
      return saved.receipt;
    });

    let lang = "en";
    const props = { t, onClose: vi.fn() };
    const { rerender } = render(<FeedbackForm {...props} lang={lang} />);
    fireEvent.change(screen.getByLabelText("feedback.content"), { target: { value: "Synthetic language retry" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    const original = apiPost.mock.calls[0][1];
    expect(original).toMatchObject({ content: "Synthetic language retry", kind: "suggestion", origin: "widget", page_path: "/chat", locale: "en" });

    lang = "zh";
    rerender(<FeedbackForm {...props} lang={lang} />);
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    expect(await screen.findByRole("status")).toHaveTextContent("receipt-after-lost-response");
    expect(apiPost.mock.calls[1][1]).toEqual(original);
  });

  it.each([429, 0])("retains text and the request id after %s failure", async (status) => {
    apiPost.mockRejectedValueOnce(status ? new ApiError("rate limited", status) : new TypeError("offline"));
    render(<FeedbackForm t={t} lang="zh" onClose={vi.fn()} />);
    const textarea = screen.getByLabelText("feedback.content");
    fireEvent.change(textarea, { target: { value: "仍要保留的内容" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await screen.findByRole("alert");
    expect(textarea).toHaveValue("仍要保留的内容");
    expect(apiPost.mock.calls[0][1].locale).toBe("zh-CN");
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2));
    expect(apiPost.mock.calls[1][1].client_request_id).toBe(apiPost.mock.calls[0][1].client_request_id);
  });

  it("uses a new request id after editing and rejects blank or oversized text", async () => {
    apiPost.mockResolvedValue({ feedback_id: "receipt-2", status: "recorded", created_at: "now" });
    render(<FeedbackForm t={t} lang="en" onClose={vi.fn()} />);
    const textarea = screen.getByLabelText("feedback.content");
    fireEvent.change(textarea, { target: { value: "First" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await screen.findByRole("status");
    fireEvent.change(textarea, { target: { value: "Changed" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2));
    expect(apiPost.mock.calls[0][1].client_request_id).not.toBe(apiPost.mock.calls[1][1].client_request_id);

    fireEvent.change(textarea, { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledTimes(2);
    fireEvent.change(textarea, { target: { value: "😀".repeat(4001) } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledTimes(2);
  });

  it("uses a new id when the current page changes", async () => {
    apiPost.mockResolvedValue({ feedback_id: "receipt-route", status: "recorded", created_at: "now" });
    const props = { t, lang: "en", onClose: vi.fn() };
    const { rerender } = render(<FeedbackForm {...props} />);
    const textarea = screen.getByLabelText("feedback.content");
    fireEvent.change(textarea, { target: { value: "Same text" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await screen.findByRole("status");
    const firstId = apiPost.mock.calls[0][1].client_request_id;

    route.value = "/chat";
    window.history.replaceState({}, "", "/chat");
    rerender(<FeedbackForm {...props} />);
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2));
    expect(apiPost.mock.calls[1][1]).toMatchObject({ content: "Same text", page_path: "/chat" });
    expect(apiPost.mock.calls[1][1].client_request_id).not.toBe(firstId);
  });

  it("closes on Escape and restores focus to the entry", async () => {
    apiGet.mockResolvedValue({ feedback_enabled: true, assistant_enabled: false });
    render(<><button data-testid="outside-widget">Chat drawer control</button><SupportWidget /></>);
    const trigger = await screen.findByTestId("support-widget-trigger");
    fireEvent.click(trigger);
    await screen.findByLabelText("feedback.content");
    fireEvent.keyDown(screen.getByTestId("outside-widget"), { key: "Escape" });
    expect(screen.getByLabelText("feedback.content")).toBeVisible();
    fireEvent.keyDown(screen.getByLabelText("feedback.content"), { key: "Escape" });
    await waitFor(() => expect(screen.getByLabelText("feedback.content")).not.toBeVisible());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it.each(["receipt", "error"] as const)("ignores a stale %s after the route changes", async (outcome) => {
    let resolveRequest!: (value: unknown) => void;
    let rejectRequest!: (error: unknown) => void;
    apiPost.mockImplementationOnce(() => new Promise((resolve, reject) => {
      resolveRequest = resolve;
      rejectRequest = reject;
    }));
    route.value = "/database";
    const props = { t, lang: "en", open: true, onClose: vi.fn() };
    const { rerender } = render(<FeedbackForm {...props} />);
    fireEvent.change(screen.getByLabelText("feedback.content"), { target: { value: "Submission from old route" } });
    fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledOnce());

    route.value = "/chat";
    window.history.replaceState({}, "", "/chat");
    rerender(<FeedbackForm {...props} />);
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    if (outcome === "receipt") resolveRequest({ feedback_id: "stale-receipt", status: "recorded", created_at: "now" });
    else rejectRequest(new ApiError("stale server error", 500));
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("feedback.content")).toHaveValue("Submission from old route");
  });
});

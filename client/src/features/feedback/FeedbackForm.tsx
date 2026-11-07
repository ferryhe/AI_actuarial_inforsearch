import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation } from "wouter";
import { X } from "lucide-react";
import { IconButton } from "@/components/a11y/IconButton";
import { ApiError, apiPost } from "@/lib/api";

type Kind = "suggestion" | "problem" | "other";
type Receipt = { feedback_id: string; status: "recorded"; created_at: string };
type Submission = { client_request_id: string; content: string; kind: Kind; origin: "widget"; page_path: string; locale: string };
type Translate = (key: string, values?: Record<string, string | number>) => string;

export default function FeedbackForm({ t, lang, open = true, onClose, initialContent = "", onCancel }: { t: Translate; lang: string; open?: boolean; onClose: () => void; initialContent?: string; onCancel?: () => void }) {
  const [location] = useLocation();
  const locationRef = useRef(location);
  const routeGeneration = useRef(0);
  if (locationRef.current !== location) {
    locationRef.current = location;
    routeGeneration.current += 1;
  }
  const [kind, setKind] = useState<Kind>("suggestion");
  const [content, setContent] = useState(initialContent);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");
  const [statusLocation, setStatusLocation] = useState(location);
  const submissionRef = useRef<{ route: string; payload: Submission } | null>(null);
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const previousLocation = useRef(location);

  useEffect(() => {
    if (previousLocation.current !== location) {
      previousLocation.current = location;
      submissionRef.current = null;
      setSubmitting(false);
      setReceipt("");
      setError("");
      setStatusLocation(location);
    }
  }, [location]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => contentRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const edit = () => {
    submissionRef.current = null;
    setReceipt("");
    setError("");
    setStatusLocation(location);
  };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = content.trim();
    const length = [...trimmed].length;
    if (!length || length > 4000 || trimmed.includes("\0")) {
      setError(t("feedback.invalid_content"));
      setReceipt("");
      setStatusLocation(location);
      contentRef.current?.focus();
      return;
    }

    const route = location;
    const generation = routeGeneration.current;
    const submission = submissionRef.current?.route === route ? submissionRef.current.payload : {
      client_request_id: crypto.randomUUID(),
      content: trimmed,
      kind,
      origin: "widget" as const,
      page_path: window.location.pathname || "/",
      locale: lang === "zh" ? "zh-CN" : "en",
    };
    submissionRef.current = { route, payload: submission };
    setSubmitting(true);
    setError("");
    setReceipt("");
    setStatusLocation(route);
    try {
      const result = await apiPost<Receipt>("/api/feedback", submission);
      if (!result?.feedback_id || result.status !== "recorded") throw new Error("Invalid feedback receipt");
      if (routeGeneration.current === generation && locationRef.current === route) setReceipt(result.feedback_id);
    } catch (err) {
      if (routeGeneration.current === generation && locationRef.current === route) {
        setError(err instanceof ApiError && err.status === 429
          ? t("feedback.rate_limited")
          : err instanceof ApiError && err.status >= 500
            ? t("feedback.server_error")
            : t("feedback.network_error"));
      }
    } finally {
      if (routeGeneration.current === generation && locationRef.current === route) setSubmitting(false);
    }
  }

  return (
    <section id="feedback-panel" aria-labelledby="feedback-title" className="flex w-[min(22.5rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-2xl">
      <header className="flex items-center justify-between border-b border-border px-4 py-2">
        <h2 id="feedback-title" className="text-base font-semibold">{t("feedback.title")}</h2>
        <IconButton label={t("a11y.close_feedback")} onClick={onClose}>
          <X className="h-4 w-4" />
        </IconButton>
      </header>
      <form onSubmit={submit} className="min-h-0 space-y-3 overflow-y-auto p-4">
        <div>
          <label htmlFor="feedback-kind" className="mb-1 block text-sm font-medium">{t("feedback.kind")}</label>
          <select
            id="feedback-kind"
            value={kind}
            disabled={submitting}
            onChange={(event) => { edit(); setKind(event.target.value as Kind); }}
            className="min-h-[44px] w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="suggestion">{t("feedback.kind.suggestion")}</option>
            <option value="problem">{t("feedback.kind.problem")}</option>
            <option value="other">{t("feedback.kind.other")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="feedback-content" className="mb-1 block text-sm font-medium">{t("feedback.content")}</label>
          <textarea
            ref={contentRef}
            id="feedback-content"
            required
            rows={5}
            value={content}
            disabled={submitting}
            aria-describedby="feedback-content-hint"
            onChange={(event) => { edit(); setContent(event.target.value); }}
            className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
          <p id="feedback-content-hint" className="mt-1 text-xs text-muted-foreground">{t("feedback.content_hint")}</p>
        </div>
        <p className="break-all text-xs text-muted-foreground">{t("feedback.page")}: {location || "/"}</p>
        {onCancel && <button type="button" disabled={submitting} className="min-h-[44px] rounded-md border border-border px-3" onClick={onCancel}>{t("assistant.cancel")}</button>}
        {error && statusLocation === location && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {receipt && statusLocation === location && <p role="status" aria-live="polite" className="break-all text-sm text-green-700 dark:text-green-400">{t("feedback.receipt", { id: receipt })}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="min-h-[44px] w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-wait disabled:opacity-60"
          data-testid="feedback-submit"
        >
          {submitting ? t("feedback.sending") : t("feedback.submit")}
        </button>
      </form>
    </section>
  );
}

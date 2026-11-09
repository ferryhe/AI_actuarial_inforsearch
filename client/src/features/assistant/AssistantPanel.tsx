import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type MouseEvent as ReactMouseEvent } from "react";
import { X } from "lucide-react";
import { z } from "zod";
import { useLocation } from "wouter";
import { IconButton } from "@/components/a11y/IconButton";
import { MarkdownContent } from "@/components/MarkdownContent";
import { ApiError, apiGet } from "@/lib/api";
import { helpSchema, type HelpCitation, type QueryTransport, type Reply } from "./contract";
import { queryAssistant } from "./transport";

type Translate = (key: string, values?: Record<string, string | number>) => string;

export default function AssistantPanel({ t, lang, open, feedbackEnabled, onClose, identity = "guest", query = queryAssistant }: { t: Translate; lang: string; open: boolean; feedbackEnabled: boolean; onClose: () => void; identity?: string; query?: QueryTransport }) {
  const [, navigate] = useLocation();
  const FeedbackForm = useMemo(() => lazy(() => import("@/features/feedback/FeedbackForm")), []);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ question: string; reply: Reply }[]>([]);
  const latestEntry = history[history.length - 1];
  const [selectedTarget, setSelectedTarget] = useState<Reply["selected_target"]>(null);
  const [openedFileUrl, setOpenedFileUrl] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<{ text: string; id: number } | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [help, setHelp] = useState<HelpCitation[]>([]);
  const [section, setSection] = useState("");
  const mounted = useRef(true);
  const input = useRef<HTMLTextAreaElement>(null);
  const scrollContainer = useRef<HTMLDivElement>(null);
  const latestAnswer = useRef<HTMLDivElement>(null);
  const revealedReply = useRef<(typeof history)[number] | undefined>(undefined);
  const userScrolledDuringRequest = useRef(false);
  const inFlight = useRef(false);
  const feedbackGeneration = useRef(0);
  const helpGeneration = useRef(0);
  const request = useRef<AbortController | null>(null);
  const requestGeneration = useRef(0);
  const currentIdentity = useRef(identity);
  const cancelRequest = useCallback(() => {
    requestGeneration.current += 1;
    request.current?.abort();
    request.current = null;
    inFlight.current = false;
    setPending(false);
  }, []);
  const clear = useCallback(() => {
    cancelRequest();
    feedbackGeneration.current += 1;
    helpGeneration.current += 1;
    setHistory([]);
    setSelectedTarget(null);
    setOpenedFileUrl(null);
    setDraft(null);
    setFeedbackOpen(false);
    setHelp([]);
    setSection("");
    setMessage("");
    setError("");
    revealedReply.current = undefined;
  }, [cancelRequest]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; request.current?.abort(); requestGeneration.current += 1; }; }, []);
  useEffect(() => {
    if (currentIdentity.current === identity) return;
    currentIdentity.current = identity;
    clear();
  }, [identity, clear]);
  useEffect(() => {
    if (!open || feedbackOpen || latestEntry !== revealedReply.current) return;
    const frame = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [latestEntry, open, feedbackOpen]);
  useEffect(() => {
    if (!open || feedbackOpen || !latestEntry || latestEntry === revealedReply.current) return;
    const container = scrollContainer.current;
    const answer = latestAnswer.current;
    if (container && answer && !userScrolledDuringRequest.current) {
      container.scrollTop += answer.getBoundingClientRect().top - container.getBoundingClientRect().top;
    }
    revealedReply.current = latestEntry;
  }, [feedbackOpen, latestEntry, open]);

  function openFeedback(text: string) {
    if (!feedbackEnabled) return;
    feedbackGeneration.current += 1;
    if (!draft || draft.text !== text) setDraft((previous) => ({ text, id: (previous?.id ?? 0) + 1 }));
    setFeedbackOpen(true);
  }

  function preserveScrollPosition() {
    if (inFlight.current && history.length) userScrolledDuringRequest.current = true;
  }

  function preserveScrollbarScroll(event: ReactMouseEvent<HTMLDivElement>) {
    const container = scrollContainer.current;
    if (!container || !inFlight.current || !history.length) return;
    const rect = container.getBoundingClientRect();
    const scrollbarLeft = container.clientLeft;
    const scrollbarRight = container.offsetWidth - container.clientWidth - scrollbarLeft;
    if ((scrollbarLeft && event.clientX < rect.left + scrollbarLeft) || (scrollbarRight && event.clientX >= rect.right - scrollbarRight)) {
      userScrolledDuringRequest.current = true;
    }
  }

  function preserveKeyboardScroll(event: KeyboardEvent<HTMLDivElement>) {
    const scrollKeys = ["ArrowDown", "ArrowUp", "End", "Home", "PageDown", "PageUp"];
    const spaceOnCitation = (event.key === " " || event.code === "Space") && event.target instanceof HTMLAnchorElement;
    if (scrollKeys.includes(event.key) || spaceOnCitation) preserveScrollPosition();
  }

  function navigateWithin(event: ReactMouseEvent<HTMLElement>) {
    if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = (event.target as Element).closest("a[href]");
    const path = link?.getAttribute("href");
    if (path === "/weekly" || path === "/source-portals" || path?.startsWith("/file-detail?url=")) {
      event.preventDefault();
      navigate(path);
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !message.trim() || message.length > 4000 || message.includes("\0")) return;
    userScrolledDuringRequest.current = false;
    input.current?.blur();
    inFlight.current = true;
    setPending(true);
    setError("");
    const question = message;
    const generation = feedbackGeneration.current;
    const requestId = ++requestGeneration.current;
    const controller = new AbortController();
    request.current = controller;
    try {
      const reply = await query({ message: question, locale: lang === "zh" ? "zh" : "en", selected_target: selectedTarget, recent_questions: history.slice(-3).map((item) => item.question.slice(0, 500)), ...(openedFileUrl && { opened_file_url: openedFileUrl }) }, controller.signal);
      if (!mounted.current || requestId !== requestGeneration.current) return;
      if (reply.error_code === "SCOPE_REVOKED") setHistory([]);
      setHistory((items) => [...items.slice(-11), { question, reply }]);
      setSelectedTarget(reply.selected_target);
      if (reply.selected_target || reply.error_code === "SCOPE_REVOKED") setOpenedFileUrl(null);
      if (reply.intent === "feedback" && reply.availability === "available" && reply.feedback_draft !== null && generation === feedbackGeneration.current) openFeedback(question);
    } catch (reason) {
      if (!mounted.current || requestId !== requestGeneration.current) return;
      if (reason instanceof ApiError && [401, 403].includes(reason.status)) {
        setHistory([]);
        setSelectedTarget(null);
        setOpenedFileUrl(null);
        revealedReply.current = undefined;
      }
      setError(t("assistant.error"));
    } finally {
      if (mounted.current && requestId === requestGeneration.current) { request.current = null; inFlight.current = false; setPending(false); }
    }
  }

  async function readCitation(reference: HelpCitation) {
    const generation = ++helpGeneration.current;
    setError("");
    try {
      const exact = helpSchema.parse(reference);
      const value = z.object({ ...helpSchema.shape, content: z.string() }).parse(await apiGet(`/api/assistant/help/section?${new URLSearchParams(exact)}`));
      if (mounted.current && generation === helpGeneration.current) setSection(value.content);
    } catch { if (mounted.current && generation === helpGeneration.current) setError(t("assistant.help_error")); }
  }

  async function browseHelp() {
    const generation = ++helpGeneration.current;
    setError("");
    try {
      const value = z.object({ results: z.array(helpSchema) }).parse(await apiGet(`/api/assistant/help?${new URLSearchParams({ q: lang === "zh" ? "指南" : "guide", language: lang === "zh" ? "zh" : "en", limit: "10" })}`));
      if (mounted.current && generation === helpGeneration.current) setHelp(value.results);
    } catch { if (mounted.current && generation === helpGeneration.current) setError(t("assistant.help_error")); }
  }

  return <>
    {draft && feedbackEnabled && <div hidden={!feedbackOpen}><Suspense fallback={<p role="status">{t("feedback.title")}</p>}><FeedbackForm key={draft.id} t={t} lang={lang} open={open && feedbackOpen} initialContent={draft.text} onClose={onClose} onCancel={() => { setFeedbackOpen(false); setDraft(null); }} /></Suspense></div>}
    <section hidden={feedbackOpen} onClick={navigateWithin} id="assistant-panel" aria-labelledby="assistant-title" className="flex w-[min(22.5rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-2xl">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2"><h2 id="assistant-title" className="text-base font-semibold">{t("assistant.title")}</h2><IconButton label={t("a11y.close_feedback")} onClick={onClose}><X className="h-4 w-4" /></IconButton></header>
      <div ref={scrollContainer} onWheel={preserveScrollPosition} onTouchMove={preserveScrollPosition} onMouseDown={preserveScrollbarScroll} onKeyDown={preserveKeyboardScroll} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
        <p className="text-xs text-muted-foreground">{t("assistant.scope")}</p>
        <div className="flex flex-wrap gap-2">{feedbackEnabled && <button type="button" className="min-h-[44px] rounded-md border border-border px-3" onClick={() => { userScrolledDuringRequest.current = false; openFeedback(message); }}>{t("assistant.feedback")}</button>}<button type="button" className="min-h-[44px] rounded-md border border-border px-3" onClick={browseHelp}>{t("assistant.guide")}</button><button type="button" className="min-h-[44px] rounded-md border border-border px-3" onClick={clear}>{t("assistant.clear")}</button></div>
        {history.map(({ question, reply }, index) => <article key={index} className="space-y-2 border-t border-border pt-3"><p className="whitespace-pre-wrap break-words font-medium">{question}</p><div ref={index === history.length - 1 ? latestAnswer : undefined} className="assistant-answer"><MarkdownContent content={reply.answer} /></div>{reply.citations.map((ref, i) => ref.source_type === "help" ? <button type="button" key={`${ref.doc_id}-${ref.section_id}`} className="min-h-[44px] text-left text-primary underline" onClick={() => readCitation(ref)}>[{i + 1}] {ref.title} / {ref.section_id} ({ref.source_version}) — {t("assistant.source_help")}</button> : <a key={`${ref.kb_id}-${ref.file_id}-${ref.section_id}`} className="block min-h-[44px] break-words text-primary underline" href={ref.link} onClick={(event) => { if (!event.button && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { setSelectedTarget(ref.kb_id ? { kb_id: ref.kb_id, file_id: ref.file_id } : null); setOpenedFileUrl(ref.kb_id ? null : ref.file_id); } }}>[{i + 1}] {ref.title} — {t(`assistant.source_${ref.source_type}`)} {ref.section_id} {ref.source_version && `(${ref.source_version})`} {ref.source_date} {ref.stale && t("assistant.stale")}</a>)}{reply.evidence_ids.map((id, i) => <p key={id} className="break-all text-xs text-muted-foreground">[{i + 1}] {id}</p>)}{reply.intent === "clarify" && <p>{t("assistant.choose")}</p>}</article>)}
        {help.map((ref) => <button type="button" key={ref.section_id} className="block min-h-[44px] text-left text-primary underline" onClick={() => readCitation(ref)}>{ref.section_id} ({ref.source_version})</button>)}
        {section && <div className="border-t border-border pt-3" data-testid="assistant-help-section"><MarkdownContent content={section} /></div>}
        {pending && <p role="status">{t("assistant.wait")}</p>}
        {error && <p role="alert" className="text-destructive">{error}</p>}
      </div>
      <form onSubmit={ask} className="flex shrink-0 items-end gap-2 border-t border-border p-2">
        <label className="sr-only" htmlFor="assistant-message">{t("assistant.message")}</label>
        <textarea id="assistant-message" ref={input} required rows={1} maxLength={4000} value={message} disabled={pending} onChange={(e) => setMessage(e.target.value)} className="min-h-[44px] max-h-32 min-w-0 flex-1 resize-y overflow-y-auto rounded-md border border-border bg-background px-3 py-2" aria-describedby="assistant-hint" />
        <p id="assistant-hint" className="sr-only">{t("feedback.content_hint")}</p>
        <button type="submit" disabled={pending} className="min-h-[44px] shrink-0 rounded-md bg-primary px-4 text-primary-foreground disabled:opacity-60">{pending ? t("assistant.wait") : t("assistant.ask")}</button>
        {pending && <button type="button" className="min-h-[44px] shrink-0 rounded-md border border-border px-2" onClick={cancelRequest}>{t("assistant.cancel_request")}</button>}
      </form>
    </section>
  </>;
}

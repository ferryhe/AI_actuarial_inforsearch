import { Component, Suspense, lazy, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { MessageSquare, X } from "lucide-react";
import { IconButton } from "@/components/a11y/IconButton";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";
import { useLocation } from "wouter";

class FeedbackLoadErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  render() {
    if (this.state.failed) return this.props.fallback;
    return this.props.children;
  }
}

type Capabilities = { feedback_enabled: boolean; assistant_enabled: boolean };

export default function SupportWidget({ onOpenChange }: { onOpenChange?: (open: boolean) => void }) {
  const { t, lang } = useTranslation();
  const [location] = useLocation();
  const isChat = location.split("?")[0] === "/chat";
  const [enabled, setEnabled] = useState(false);
  const [assistantEnabled, setAssistantEnabled] = useState(false);
  const [feedbackEnabled, setFeedbackEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [panelSpace, setPanelSpace] = useState({ maxHeight: 0, lift: 0 });
  const FeedbackForm = useMemo(() => lazy(() => import("@/features/feedback/FeedbackForm")), [loadAttempt]);
  const AssistantPanel = useMemo(() => lazy(() => import("@/features/assistant/AssistantPanel")), [loadAttempt]);

  useEffect(() => {
    let mounted = true;
    apiGet<Capabilities>("/api/support/capabilities")
      .then((capabilities) => {
        if (mounted) {
          setEnabled(capabilities?.feedback_enabled === true || capabilities?.assistant_enabled === true);
          setAssistantEnabled(capabilities?.assistant_enabled === true);
          setFeedbackEnabled(capabilities?.feedback_enabled === true);
        }
      })
      .catch(() => { if (mounted) setEnabled(false); });
    return () => { mounted = false; };
  }, []);

  useLayoutEffect(() => {
    if (!enabled) return;
    const hostElement = host.current;
    const triggerElement = trigger.current;
    if (!hostElement || !triggerElement) return;
    const chatComposer = isChat ? document.querySelector<HTMLElement>("[data-chat-composer]") : null;

    const updatePanelSpace = () => {
      const visualViewport = window.visualViewport;
      const viewportTop = visualViewport?.offsetTop ?? 0;
      const viewportBottom = viewportTop + (visualViewport?.height ?? window.innerHeight);
      const triggerBounds = triggerElement.getBoundingClientRect();
      const hostStyle = getComputedStyle(hostElement);
      const gap = Number.parseFloat(hostStyle.rowGap) || 0;
      const safeTop = Number.parseFloat(hostStyle.paddingTop) || 0;
      const normalBottom = Math.min(triggerBounds.top - gap, viewportBottom - triggerBounds.height - gap);
      const chatTop = chatComposer?.getBoundingClientRect().top;
      const bottom = chatTop === undefined ? normalBottom : Math.min(normalBottom, chatTop - gap);
      const next = {
        maxHeight: Math.max(0, Math.floor(bottom - viewportTop - safeTop) - 1),
        lift: Math.max(0, Math.round(normalBottom - bottom)),
      };
      setPanelSpace((previous) => previous.maxHeight === next.maxHeight && previous.lift === next.lift ? previous : next);
    };

    updatePanelSpace();
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updatePanelSpace);
    resizeObserver?.observe(triggerElement);
    if (chatComposer) resizeObserver?.observe(chatComposer);
    window.addEventListener("resize", updatePanelSpace);
    window.addEventListener("scroll", updatePanelSpace, true);
    window.visualViewport?.addEventListener("resize", updatePanelSpace);
    window.visualViewport?.addEventListener("scroll", updatePanelSpace);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updatePanelSpace);
      window.removeEventListener("scroll", updatePanelSpace, true);
      window.visualViewport?.removeEventListener("resize", updatePanelSpace);
      window.visualViewport?.removeEventListener("scroll", updatePanelSpace);
    };
  }, [enabled, isChat, location]);

  const panelStyle = {
    "--support-panel-max-height": `min(38rem, ${panelSpace.maxHeight}px)`,
    marginBottom: panelSpace.lift,
  } as CSSProperties;

  const close = useCallback(() => {
    setOpen(false);
    onOpenChange?.(false);
    requestAnimationFrame(() => trigger.current?.focus());
  }, [onOpenChange]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (open && event.key === "Escape") {
      event.preventDefault();
      close();
    }
  };

  if (!enabled) return null;

  return (
    <div ref={host} className="pointer-events-none fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 z-50 flex flex-col items-end gap-3" style={{ paddingTop: "env(safe-area-inset-top, 0px)" }} onKeyDown={handleKeyDown}>
      {hasOpened && (
        <div id="support-panel" hidden={!open} className="pointer-events-auto" style={panelStyle}>
          <FeedbackLoadErrorBoundary
            key={loadAttempt}
            fallback={(
              <div role="alert" className="w-[min(22.5rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-border bg-card p-4 text-sm shadow-xl">
                <p>{t("feedback.load_error")}</p>
                <button type="button" className="mt-3 min-h-[44px] rounded-md border border-border px-3" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>{t("feedback.retry")}</button>
              </div>
            )}
          >
            <Suspense fallback={<div role="status" className="w-[min(22.5rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-border bg-card p-4 text-sm shadow-xl">{t("feedback.title")}</div>}>
              {assistantEnabled ? <AssistantPanel key={location} t={t} lang={lang} open={open} onClose={close} feedbackEnabled={feedbackEnabled} /> : <FeedbackForm t={t} lang={lang} open={open} onClose={close} />}
            </Suspense>
          </FeedbackLoadErrorBoundary>
        </div>
      )}
      <IconButton
        ref={trigger}
        label={open ? t("a11y.close_feedback") : t("a11y.open_feedback")}
        aria-expanded={open}
        aria-controls="support-panel"
        onClick={() => {
          if (open) close();
          else { setHasOpened(true); setOpen(true); onOpenChange?.(true); }
        }}
        className="pointer-events-auto rounded-full bg-primary text-primary-foreground shadow-lg hover:bg-primary/90"
        data-testid="support-widget-trigger"
      >
        {open ? <X className="h-5 w-5" /> : <MessageSquare className="h-5 w-5" />}
      </IconButton>
    </div>
  );
}

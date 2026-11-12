import { Component, useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { MessageSquare, X } from "lucide-react";
import { IconButton } from "@/components/a11y/IconButton";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";
import { watchVisualViewport } from "@/lib/visual-viewport";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import AssistantPanel from "@/features/assistant/AssistantPanel";
import FeedbackForm from "@/features/feedback/FeedbackForm";
import { queryAssistant } from "@/features/assistant/transport";
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
  const { user, permissions } = useAuth();
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
  const fixedAnchor = useRef<HTMLDivElement>(null);
  const currentSlot = useRef<HTMLElement | null>(null);
  const restoreTriggerFocus = useRef(false);
  const [portalSlot, setPortalSlot] = useState<HTMLElement | null>(null);
  const [panelSpace, setPanelSpace] = useState({
    maxHeight: 0, lift: 0, compact: false, compactWidth: null as number | null, rightInset: 0,
  });
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
    const anchor = fixedAnchor.current;
    if (!hostElement || !anchor) return;
    const chatComposer = isChat ? document.querySelector<HTMLElement>("[data-chat-composer]") : null;
    const chatSend = chatComposer?.querySelector<HTMLElement>("[data-chat-send]");

    const updatePanelSpace = (viewportTop: number, viewportBottom: number) => {
      const triggerBounds = anchor.getBoundingClientRect();
      const covered = triggerBounds.top < viewportTop || triggerBounds.bottom > viewportBottom;
      const slot = covered ? chatComposer?.querySelector<HTMLElement>("[data-chat-support-slot]") ?? null : null;
      if (slot !== currentSlot.current) {
        restoreTriggerFocus.current = document.activeElement === trigger.current;
        currentSlot.current = slot;
        setPortalSlot(slot);
      }
      const hostStyle = getComputedStyle(hostElement);
      const gap = Number.parseFloat(hostStyle.rowGap) || 0;
      const safeTop = Number.parseFloat(hostStyle.paddingTop) || 0;
      const normalBottom = Math.min(triggerBounds.top - gap, viewportBottom - triggerBounds.height - gap);
      const chatTop = chatComposer?.getBoundingClientRect().top;
      const aboveComposer = chatTop === undefined ? normalBottom : Math.min(normalBottom, chatTop - gap);
      const compact = open && (assistantEnabled || isChat) && aboveComposer - viewportTop - safeTop < 132;
      const bottom = compact ? viewportBottom - 4 : aboveComposer;
      // Leave Send and the leading part of the Chat textarea available beside the panel.
      const compactChat = compact && chatSend;
      const right = compactChat ? chatSend.getBoundingClientRect().left - 4 : triggerBounds.right;
      const next = {
        maxHeight: Math.max(0, Math.floor(bottom - viewportTop - safeTop) - 2),
        lift: Math.round(triggerBounds.top - gap - bottom),
        compact,
        compactWidth: compactChat ? Math.max(0, Math.floor(right - 44)) : null,
        rightInset: Math.max(0, Math.ceil(triggerBounds.right - right)),
      };
      setPanelSpace((previous) => previous.maxHeight === next.maxHeight && previous.lift === next.lift
        && previous.compact === next.compact && previous.compactWidth === next.compactWidth
        && previous.rightInset === next.rightInset ? previous : next);
    };

    let bounds: [number, number];
    const stopWatching = watchVisualViewport((top, bottom) => {
      bounds = [top, bottom];
      updatePanelSpace(...bounds);
    });
    const updateLayout = () => updatePanelSpace(...bounds);
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateLayout);
    resizeObserver?.observe(anchor);
    if (chatComposer) resizeObserver?.observe(chatComposer);
    window.addEventListener("scroll", updateLayout, true);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("scroll", updateLayout, true);
      stopWatching();
    };
  }, [enabled, isChat, location, assistantEnabled, open, portalSlot]);

  useLayoutEffect(() => {
    if (restoreTriggerFocus.current) {
      restoreTriggerFocus.current = false;
      trigger.current?.focus({ preventScroll: true });
    }
  }, [portalSlot]);

  const { compact, compactWidth } = panelSpace;
  const panelStyle = {
    "--support-panel-max-height": `min(38rem, ${panelSpace.maxHeight}px)`,
    "--support-panel-max-width": compactWidth === null ? undefined : `${compactWidth}px`,
    marginBottom: panelSpace.lift,
    marginRight: panelSpace.rightInset,
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
  const supportTrigger = (
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
  );

  return (
    <div ref={host} className={cn("pointer-events-none fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 flex flex-col items-end gap-3", compact ? "z-[65]" : "z-50")} style={{ paddingTop: "max(1rem, env(safe-area-inset-top, 0px))" }} onKeyDown={handleKeyDown}>
      {hasOpened && (
        <div id="support-panel" hidden={!open} data-compact-assistant={compact && assistantEnabled || undefined} data-compact-feedback={compact && !assistantEnabled || undefined} className="group/support-panel pointer-events-auto" style={panelStyle}>
          <FeedbackLoadErrorBoundary
            key={loadAttempt}
            fallback={(
              <div role="alert" className="w-[min(22.5rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-border bg-card p-4 text-sm shadow-xl">
                <p>{t("feedback.load_error")}</p>
                <button type="button" className="mt-3 min-h-[44px] rounded-md border border-border px-3" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>{t("feedback.retry")}</button>
              </div>
            )}
          >
            {assistantEnabled ? <AssistantPanel t={t} lang={lang} open={open} onClose={close} feedbackEnabled={feedbackEnabled} identity={JSON.stringify([user?.id, user?.email, permissions])} query={queryAssistant} /> : <FeedbackForm t={t} lang={lang} open={open} onClose={close} />}
          </FeedbackLoadErrorBoundary>
        </div>
      )}
      <div ref={fixedAnchor} data-support-fixed-anchor className="size-11 shrink-0">
        {portalSlot ? createPortal(supportTrigger, portalSlot) : supportTrigger}
      </div>
    </div>
  );
}

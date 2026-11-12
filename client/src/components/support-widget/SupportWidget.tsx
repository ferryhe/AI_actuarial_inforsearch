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
export type OpenSupportPanel = "assistant" | "feedback" | null;

function AssistantDialog({ open, onClose, label, children }: { open: boolean; onClose: () => void; label: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);

  useLayoutEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const desktop = window.matchMedia("(min-width: 64rem)");
    const show = () => {
      const focused = document.activeElement;
      if (dialog.open) dialog.close();
      if (desktop.matches) dialog.show();
      else dialog.showModal();
      if (focused instanceof HTMLElement && dialog.contains(focused)) focused.focus({ preventScroll: true });
    };
    const stopWatching = watchVisualViewport((top, bottom) => {
      const height = bottom - top;
      dialog.style.setProperty("--assistant-viewport-top", `${top}px`);
      dialog.style.setProperty("--assistant-viewport-height", `${height}px`);
      dialog.toggleAttribute("data-compact-assistant", height < 240);
      dialog.toggleAttribute("data-compact-feedback", height < 240);
    });
    show();
    desktop.addEventListener("change", show);
    return () => {
      desktop.removeEventListener("change", show);
      stopWatching();
      if (dialog.open) dialog.close();
    };
  }, [open]);

  return (
    <dialog
      ref={ref}
      id="support-panel"
      data-assistant
      aria-label={label}
      className="group/support-panel fixed z-50 m-0 w-[min(24rem,calc(100%-3rem))] max-h-none max-w-none overflow-hidden border-l border-border bg-card text-card-foreground shadow-xl lg:w-[var(--assistant-panel-width)]"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const { left, right, top, bottom } = event.currentTarget.getBoundingClientRect();
        if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) onClose();
      }}
    >
      {children}
    </dialog>
  );
}

export default function SupportWidget({ onOpenChange }: { onOpenChange?: (panel: OpenSupportPanel) => void }) {
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
      if (assistantEnabled) {
        const offset = Math.max(viewportTop + 4 - triggerBounds.top, Math.min(0, viewportBottom - 4 - triggerBounds.bottom));
        hostElement.style.setProperty("--assistant-trigger-offset", `${offset}px`);
        return;
      }
      const hostStyle = getComputedStyle(hostElement);
      const gap = Number.parseFloat(hostStyle.rowGap) || 0;
      const safeTop = Number.parseFloat(hostStyle.paddingTop) || 0;
      const normalBottom = Math.min(triggerBounds.top - gap, viewportBottom - triggerBounds.height - gap);
      const chatTop = chatComposer?.getBoundingClientRect().top;
      const aboveComposer = chatTop === undefined ? normalBottom : Math.min(normalBottom, chatTop - gap);
      const compact = open && isChat && aboveComposer - viewportTop - safeTop < 132;
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
    onOpenChange?.(null);
    requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true }));
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
      aria-haspopup={assistantEnabled ? "dialog" : undefined}
      onClick={() => {
        if (open) close();
        else { setHasOpened(true); setOpen(true); onOpenChange?.(assistantEnabled ? "assistant" : "feedback"); }
      }}
      className={cn(
        "pointer-events-auto rounded-full bg-primary text-primary-foreground shadow-lg hover:bg-primary/90",
        assistantEnabled && "translate-y-[var(--assistant-trigger-offset,0px)]",
        assistantEnabled && open && "invisible",
      )}
      data-testid="support-widget-trigger"
    >
      {open ? <X className="h-5 w-5" /> : <MessageSquare className="h-5 w-5" />}
    </IconButton>
  );
  const panel = hasOpened && (
    <FeedbackLoadErrorBoundary
      key={loadAttempt}
      fallback={(
        <div role="alert" className={cn("overflow-y-auto bg-card p-4 text-sm", !assistantEnabled && "w-[min(22.5rem,calc(100vw-2rem))] rounded-xl border border-border shadow-xl")}>
          {assistantEnabled && <IconButton label={t("a11y.close_feedback")} onClick={close} className="float-right"><X className="h-4 w-4" /></IconButton>}
          <p>{t("feedback.load_error")}</p>
          <button type="button" className="mt-3 min-h-[44px] rounded-md border border-border px-3" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>{t("feedback.retry")}</button>
        </div>
      )}
    >
      {assistantEnabled ? <AssistantPanel t={t} lang={lang} open={open} onClose={close} feedbackEnabled={feedbackEnabled} identity={JSON.stringify([user?.id, user?.email, permissions])} query={queryAssistant} /> : <FeedbackForm t={t} lang={lang} open={open} onClose={close} />}
    </FeedbackLoadErrorBoundary>
  );

  return (<>
    <div ref={host} className={cn("pointer-events-none fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 flex flex-col items-end gap-3", compact ? "z-[65]" : "z-50")} style={{ paddingTop: "max(1rem, env(safe-area-inset-top, 0px))" }} onKeyDown={handleKeyDown}>
      {hasOpened && !assistantEnabled && (
        <div id="support-panel" hidden={!open} data-compact-feedback={compact || undefined} className="group/support-panel pointer-events-auto" style={panelStyle}>
          {panel}
        </div>
      )}
      <div ref={fixedAnchor} data-support-fixed-anchor className="size-11 shrink-0">
        {portalSlot ? createPortal(supportTrigger, portalSlot) : supportTrigger}
      </div>
    </div>
    {assistantEnabled && hasOpened && (
      <AssistantDialog open={open} onClose={close} label={t("assistant.title")}>{panel}</AssistantDialog>
    )}
  </>);
}

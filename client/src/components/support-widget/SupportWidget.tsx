import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { MessageSquare, X } from "lucide-react";
import { IconButton } from "@/components/a11y/IconButton";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";
import { useLocation } from "wouter";
import { cn } from "@/lib/utils";

const FeedbackForm = lazy(() => import("@/features/feedback/FeedbackForm"));
type Capabilities = { feedback_enabled: boolean; assistant_enabled: boolean };

export default function SupportWidget({ onOpenChange }: { onOpenChange?: (open: boolean) => void }) {
  const { t, lang } = useTranslation();
  const [location] = useLocation();
  const isChat = location.split("?")[0] === "/chat";
  const [enabled, setEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let mounted = true;
    apiGet<Capabilities>("/api/support/capabilities")
      .then((capabilities) => {
        if (mounted) setEnabled(capabilities?.feedback_enabled === true);
      })
      .catch(() => { if (mounted) setEnabled(false); });
    return () => { mounted = false; };
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    onOpenChange?.(false);
    requestAnimationFrame(() => trigger.current?.focus());
  }, [onOpenChange]);

  if (!enabled) return null;

  return (
    <div className="pointer-events-none fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 z-50 flex flex-col items-end gap-3">
      {open && (
        <div className={cn("pointer-events-auto", isChat && "max-xl:mb-32")}>
          <Suspense fallback={<div role="status" className="w-[min(22.5rem,calc(100vw-2rem))] rounded-xl border border-border bg-card p-4 text-sm shadow-xl">{t("feedback.title")}</div>}>
            <FeedbackForm t={t} lang={lang} onClose={close} />
          </Suspense>
        </div>
      )}
      <IconButton
        ref={trigger}
        label={open ? t("a11y.close_feedback") : t("a11y.open_feedback")}
        aria-expanded={open}
        aria-controls="feedback-panel"
        onClick={() => {
          if (open) close();
          else { setOpen(true); onOpenChange?.(true); }
        }}
        className="pointer-events-auto rounded-full bg-primary text-primary-foreground shadow-lg hover:bg-primary/90"
        data-testid="support-widget-trigger"
      >
        {open ? <X className="h-5 w-5" /> : <MessageSquare className="h-5 w-5" />}
      </IconButton>
    </div>
  );
}

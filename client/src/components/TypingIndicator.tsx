import { motion, useReducedMotion } from "framer-motion";
import { Bot } from "lucide-react";

export function TypingIndicator({ label }: { label?: string }) {
  const reducedMotion = useReducedMotion();

  return (
    <div role={label ? "status" : undefined} aria-label={label} className="flex items-center gap-3 max-w-3xl">
      {label && <span className="sr-only">{label}</span>}
      <div aria-hidden="true" className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0">
        <Bot className="w-4 h-4 text-muted-foreground" />
      </div>
      <div aria-hidden="true" className="flex gap-1 px-4 py-3 rounded-2xl bg-card border border-border rounded-bl-md">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-2 h-2 rounded-full bg-muted-foreground/40"
            animate={reducedMotion ? undefined : { y: [0, -6, 0] }}
            transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
          />
        ))}
      </div>
    </div>
  );
}

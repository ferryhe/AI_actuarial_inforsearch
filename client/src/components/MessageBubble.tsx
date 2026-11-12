import type { ReactNode } from "react";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";

export function MessageBubble({ role, content, children }: { role: "user" | "assistant"; content: ReactNode; children?: ReactNode }) {
  const isUser = role === "user";
  const Avatar = isUser ? User : Bot;
  return (
    <div
      data-message-role={role}
      className={cn("flex min-w-0 max-w-3xl gap-3", isUser && "ml-auto flex-row-reverse")}
    >
      <div
        aria-hidden="true"
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        <Avatar className="h-4 w-4" />
      </div>
      <div className={cn("flex min-w-0 max-w-full flex-col gap-2", isUser ? "items-end" : "items-start")}>
        <div className={cn(
          "min-w-0 max-w-full rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "whitespace-pre-wrap break-words bg-primary text-primary-foreground rounded-br-md [overflow-wrap:anywhere]"
            : "bg-card border border-border rounded-bl-md",
        )}>
          {content}
        </div>
        {children}
      </div>
    </div>
  );
}

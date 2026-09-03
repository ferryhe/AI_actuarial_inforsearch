import { type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface WeeklyGroupDisclosureProps {
  groupIndex: number;
  groupId: string;
  label: string;
  count: ReactNode;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}

export function WeeklyGroupDisclosure({
  groupIndex,
  groupId,
  label,
  count,
  collapsed,
  onToggle,
  children,
}: WeeklyGroupDisclosureProps) {
  return (
    <section className="min-w-0 border-t border-border" data-testid={`weekly-group-${groupIndex}`}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        aria-controls={groupId}
        className="flex w-full min-w-0 items-center gap-2 bg-muted/40 px-4 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
        data-testid={`weekly-group-toggle-${groupIndex}`}
      >
        {collapsed ? (
          <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
        )}
        <span className="min-w-0 flex-1 break-words text-sm font-semibold [overflow-wrap:anywhere]">
          {label}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {count}
        </span>
      </button>
      <div id={groupId} hidden={collapsed} className="min-w-0">
        {children}
      </div>
    </section>
  );
}

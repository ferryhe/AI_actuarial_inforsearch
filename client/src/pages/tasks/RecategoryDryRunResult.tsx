import type { HistoryTask } from "./Tasks.types";

interface RecategoryDryRunResultProps {
  task: HistoryTask;
  t: (key: string) => string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function categoryNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function impactCount(value: unknown, category: string): number | null {
  const impact = asRecord(value);
  const count = impact?.[category];
  return typeof count === "number" && Number.isInteger(count) && count >= 0 ? count : null;
}

function CategoryList({
  categories,
  impact,
  title,
  t,
}: {
  categories: string[];
  impact: unknown;
  title: string;
  t: (key: string) => string;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <h5 className="text-xs font-medium text-muted-foreground">{title}</h5>
      <ul className="max-h-48 space-y-1 overflow-y-auto overflow-x-hidden pr-1">
        {categories.map((category, index) => {
          const count = impactCount(impact, category);
          return (
            <li
              key={`${category}-${index}`}
              className="flex min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-1 rounded-md bg-background/70 px-2.5 py-2 text-xs"
            >
              <span className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">{category}</span>
              {count !== null && (
                <span className="shrink-0 whitespace-nowrap text-muted-foreground">
                  {t("tasks.recategory_result.article_count").replace("{count}", String(count))}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function RecategoryDryRunResult({ task, t }: RecategoryDryRunResultProps) {
  if (task.type !== "recategory" || task.status !== "completed") return null;

  const metadata = asRecord(task.metadata);
  if (!metadata || metadata.dry_run !== true) return null;

  const removed = categoryNames(metadata.removed_categories);
  const added = categoryNames(metadata.added_categories);
  const needsRecategory = typeof metadata.needs_recategory === "boolean"
    ? metadata.needs_recategory
    : null;
  const hasCategoryChanges = removed.length > 0 || added.length > 0;
  const hasSafeDetails = needsRecategory !== null || hasCategoryChanges;

  return (
    <section
      className="min-w-0 overflow-hidden rounded-lg border border-border bg-muted/30 p-3"
      data-testid="recategory-dry-run-result"
    >
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t("tasks.recategory_result.title")}
      </h4>
      <div className="min-w-0 space-y-3">
        {needsRecategory !== null && (
          <p className="break-words text-xs font-medium [overflow-wrap:anywhere]">
            {t(needsRecategory
              ? "tasks.recategory_result.needed"
              : "tasks.recategory_result.not_needed")}
          </p>
        )}
        {!hasSafeDetails && (
          <p className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">
            {t("tasks.recategory_result.unavailable")}
          </p>
        )}
        {needsRecategory === false && !hasCategoryChanges && (
          <p className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">
            {t("tasks.recategory_result.no_changes")}
          </p>
        )}
        {removed.length > 0 && (
          <CategoryList
            categories={removed}
            impact={metadata.removed_impact}
            title={t("tasks.recategory_result.removed")}
            t={t}
          />
        )}
        {added.length > 0 && (
          <CategoryList
            categories={added}
            impact={metadata.added_impact}
            title={t("tasks.recategory_result.added")}
            t={t}
          />
        )}
      </div>
    </section>
  );
}

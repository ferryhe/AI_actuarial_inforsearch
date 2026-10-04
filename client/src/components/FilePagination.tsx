import { useTranslation } from "@/components/Layout";

export default function FilePagination({ total, limit, offset, loading, onOffset, testId }: {
  total: number; limit: number; offset: number; loading: boolean;
  onOffset: (offset: number) => void; testId: string;
}) {
  const { t } = useTranslation();
  if (total <= limit && offset === 0) return null;
  return (
    <div className="flex items-center justify-between gap-2 border-t border-border p-2 text-xs" data-testid={testId}>
      <button type="button" disabled={loading || offset === 0} onClick={() => onOffset(Math.max(0, offset - limit))}
        className="min-h-12 px-3 rounded border border-border disabled:opacity-40" data-testid={`${testId}-prev`}>{t("db.prev")}</button>
      <span aria-live="polite">{total ? offset + 1 : 0}–{Math.min(offset + limit, total)} / {total}</span>
      <button type="button" disabled={loading || offset + limit >= total} onClick={() => onOffset(offset + limit)}
        className="min-h-12 px-3 rounded border border-border disabled:opacity-40" data-testid={`${testId}-next`}>{t("db.next")}</button>
    </div>
  );
}

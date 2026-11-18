import { useState, type SyntheticEvent } from "react";
import { getCanonicalDisplayName } from "@/pages/chat/displayName";
import {
  buildWeeklyDatabasePath,
  loadWeeklyIntake,
  localizedWeeklyFileMetadata,
  type WeeklySnapshot,
  type WeeklySnapshotFile,
} from "@/lib/weekly-dashboard";

interface WeeklyIntakeListProps {
  snapshot: WeeklySnapshot;
  lang: string;
  t: (key: string) => string;
  onOpenFile: (url: string) => void;
}

export function WeeklyIntakeList({ snapshot, lang, t, onOpenFile }: WeeklyIntakeListProps) {
  const [intake, setIntake] = useState<WeeklySnapshotFile[] | "loading" | "failed">();
  const files = Array.isArray(intake) ? intake : [];
  const partial = Array.isArray(intake) && files.length < snapshot.file_count;

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    if (!event.currentTarget.open || intake === "loading" || Array.isArray(intake)) return;
    setIntake("loading");
    loadWeeklyIntake(snapshot.id).then(setIntake).catch(() => setIntake("failed"));
  }

  return (
    <details className="min-w-0 rounded-xl border border-border bg-card" onToggle={handleToggle}>
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" data-testid="weekly-intake-toggle">
        {t("weekly.open_intake").replace("{count}", String(snapshot.file_count))}
      </summary>
      {intake === "loading" ? (
        <p className="px-4 pb-3 text-sm text-muted-foreground" role="status">{t("weekly.loading_intake")}</p>
      ) : null}
      {intake === "failed" || (partial && files.length === 0) ? (
        <p className="px-4 pb-3 text-sm text-muted-foreground" role="status">{t("weekly.intake_load_error")}</p>
      ) : null}
      {files.length > 0 ? (
        <ul className="divide-y divide-border border-t border-border">
          {files.map((file) => (
            <li key={file.url}>
              <button
                type="button"
                className="block w-full px-4 py-2 text-left text-sm [overflow-wrap:anywhere] hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                onClick={() => onOpenFile(file.url)}
                data-testid="weekly-intake-row"
              >
                {getCanonicalDisplayName(
                  { ...file, title: localizedWeeklyFileMetadata(file, lang).title },
                  t("dashboard.untitled_material"),
                )}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {intake === "failed" || partial ? (
        <div className="border-t border-border p-3">
          <a className="text-xs text-primary hover:underline" href={buildWeeklyDatabasePath(snapshot)}>
            {t("weekly.view_collected")}
          </a>
        </div>
      ) : null}
    </details>
  );
}

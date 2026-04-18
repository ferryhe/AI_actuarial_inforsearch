import { useEffect, useState, useCallback } from "react";
import { ArrowLeft, Folder, FileText, Loader2, AlertCircle, FolderOpen, X } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface BrowseEntry { name: string; type: "dir" | "file"; size?: number }

export function FolderBrowser({ onSelect, onClose }: { onSelect: (path: string) => void; onClose: () => void }) {
  const { t } = useTranslation();
  const [currentPath, setCurrentPath] = useState("");
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const browse = useCallback(async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const q = path ? `?path=${encodeURIComponent(path)}` : "";
      const res = await apiGet<{ path: string; parent: string | null; entries: BrowseEntry[] }>(`/api/utils/browse-folder${q}`);
      setCurrentPath(res.path || "");
      setParentPath(res.parent || null);
      setEntries(res.entries || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("tasks.form.browse_error"));
    } finally { setLoading(false); }
  }, [t]);

  useEffect(() => { browse(); }, [browse]);

  const dirs = entries.filter((e) => e.type === "dir");
  const files = entries.filter((e) => e.type === "file");

  return (
    <div className="rounded-lg border border-primary/30 bg-card overflow-hidden" data-testid="panel-folder-browser">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <FolderOpen className="w-4 h-4 text-primary shrink-0" />
          <span className="text-xs font-mono truncate" data-testid="text-current-path">{currentPath || "/"}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => { onSelect(currentPath); onClose(); }}
            className="text-xs px-2.5 py-1 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            data-testid="button-select-folder">{t("tasks.form.select_folder")}</button>
          <button onClick={onClose}
            className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground"
            data-testid="button-close-browser"><X className="w-3.5 h-3.5" /></button>
        </div>
      </div>
      <div className="max-h-[280px] overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
        ) : error ? (
          <div className="px-3.5 py-4 text-xs text-destructive flex items-center gap-2"><AlertCircle className="w-4 h-4 shrink-0" />{error}</div>
        ) : (
          <div className="divide-y divide-border">
            {parentPath !== null && (
              <button onClick={() => browse(parentPath)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs hover:bg-muted/50 transition-colors text-left"
                data-testid="button-parent-dir">
                <ArrowLeft className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-muted-foreground font-medium">..</span>
              </button>
            )}
            {dirs.map((d) => (
              <button key={d.name} onClick={() => browse(currentPath.replace(/\/+$/, "") + "/" + d.name)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs hover:bg-muted/50 transition-colors text-left"
                data-testid={`button-dir-${d.name}`}>
                <Folder className="w-3.5 h-3.5 text-amber-500" />
                <span className="font-medium truncate">{d.name}</span>
              </button>
            ))}
            {files.map((f) => (
              <div key={f.name} className="flex items-center gap-2.5 px-3.5 py-2 text-xs text-muted-foreground">
                <FileText className="w-3.5 h-3.5" />
                <span className="truncate flex-1">{f.name}</span>
                {f.size != null && <span className="shrink-0 text-[10px]">{(f.size / 1024).toFixed(1)} KB</span>}
              </div>
            ))}
            {dirs.length === 0 && files.length === 0 && (
              <div className="px-3.5 py-4 text-xs text-muted-foreground text-center">{t("tasks.form.empty_folder")}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

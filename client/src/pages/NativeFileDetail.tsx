import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useSearch } from "wouter";
import { ArrowLeft, ExternalLink, FileText, Loader2 } from "lucide-react";
import { apiGet } from "@/lib/api";
import { getReturnPathFromSearch } from "@/lib/navigation";

type FileData = {
  url: string;
  title?: string | null;
  original_filename?: string | null;
  source_site?: string | null;
  source_page_url?: string | null;
  local_path?: string | null;
  bytes?: number | null;
  content_type?: string | null;
  last_seen?: string | null;
  crawl_time?: string | null;
  category?: string | null;
  summary?: string | null;
  keywords?: string | null;
};

type MarkdownData = {
  markdown_content?: string | null;
  markdown_source?: string | null;
  markdown_updated_at?: string | null;
};

function formatBytes(bytes?: number | null): string {
  if (bytes == null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid gap-1 border-t border-border px-4 py-3 sm:grid-cols-[140px_1fr] sm:gap-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="min-w-0 text-sm">{value}</div>
    </div>
  );
}

export default function NativeFileDetail() {
  const search = useSearch();
  const [, navigate] = useLocation();
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const fileUrl = params.get("url") || "";
  const returnPath = getReturnPathFromSearch(search) || "/database";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<FileData | null>(null);
  const [markdown, setMarkdown] = useState<MarkdownData | null>(null);

  useEffect(() => {
    if (!fileUrl) {
      setError("Missing file URL");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      apiGet<{ file: FileData }>(`/api/files/detail?url=${encodeURIComponent(fileUrl)}`),
      apiGet<{ markdown: MarkdownData | null }>(`/api/files/${encodeURIComponent(fileUrl)}/markdown`),
    ])
      .then(([fileRes, markdownRes]) => {
        if (cancelled) return;
        setFile(fileRes.file || null);
        setMarkdown(markdownRes.markdown || null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to load file details";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fileUrl]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading file details…
      </div>
    );
  }

  if (error || !file) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 py-16">
        <button onClick={() => navigate(returnPath)} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted" data-testid="button-back-native-detail">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <div className="rounded-xl border border-border bg-card p-6">
          <h1 className="text-xl font-serif font-bold tracking-tight">File detail unavailable</h1>
          <p className="mt-2 text-sm text-muted-foreground">{error || "The requested file could not be found."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(returnPath)} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted" data-testid="button-back-native-detail">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <span className="rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
          FastAPI-native detail
        </span>
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-4">
          <h1 className="text-2xl font-serif font-bold tracking-tight">{file.title || file.original_filename || "Untitled file"}</h1>
          <p className="mt-1 text-sm text-muted-foreground">Read-only detail view backed entirely by native FastAPI endpoints.</p>
        </div>
        <DetailRow label="Source" value={file.source_site || "-"} />
        <DetailRow label="Original URL" value={file.url ? <a href={file.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-primary hover:underline">{file.url}<ExternalLink className="h-3.5 w-3.5 shrink-0" /></a> : "-"} />
        <DetailRow label="Source page" value={file.source_page_url ? <a href={file.source_page_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-primary hover:underline">{file.source_page_url}<ExternalLink className="h-3.5 w-3.5 shrink-0" /></a> : "-"} />
        <DetailRow label="Content type" value={file.content_type || "-"} />
        <DetailRow label="Size" value={formatBytes(file.bytes)} />
        <DetailRow label="Collected" value={formatDate(file.crawl_time || file.last_seen)} />
        <DetailRow label="Category" value={file.category || "-"} />
        <DetailRow label="Keywords" value={file.keywords || "-"} />
        <DetailRow label="Summary" value={<div className="whitespace-pre-wrap">{file.summary || "-"}</div>} />
        <DetailRow label="Local path" value={<span className="break-all font-mono text-xs">{file.local_path || "-"}</span>} />
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <FileText className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Markdown</h2>
        </div>
        <div className="space-y-3 px-4 py-4">
          <div className="text-xs text-muted-foreground">
            Source: {markdown?.markdown_source || "-"} · Updated: {formatDate(markdown?.markdown_updated_at)}
          </div>
          <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-lg bg-muted/40 p-4 text-sm leading-6 text-foreground">{markdown?.markdown_content || "No markdown content available."}</pre>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState, useCallback, useRef } from "react";
import { useLocation, useSearch } from "wouter";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  FileText,
  Layers,
  Download,
  Monitor,
  ChevronLeft,
  ChevronRight,
  ImageIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface FileInfo {
  url: string;
  title: string;
  original_filename: string;
  local_path: string;
  content_type: string;
  bytes: number;
}

interface ChunkItem {
  chunk_id: string;
  chunk_index: number;
  content: string;
  token_count: number;
  section_hierarchy?: string;
  chunk_set_id: string;
}

interface ChunkSetItem {
  chunk_set_id: string;
  profile_name?: string;
  chunk_count?: number;
  updated_at?: string;
}

interface PreviewData {
  file_info: FileInfo;
  markdown: { content: string; source: string; updated_at: string };
  chunk_sets: ChunkSetItem[];
  active_chunk_set_id: string;
  chunks: ChunkItem[];
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : true
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [query]);
  return matches;
}

function PdfViewer({ fileUrl }: { fileUrl: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [pdfLoading, setPdfLoading] = useState(true);
  const [pdfError, setPdfError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadPdf() {
      setPdfLoading(true);
      setPdfError(null);
      try {
        const pdfjsLib = await loadPdfjsLib();
        const downloadUrl = `/api/download?url=${encodeURIComponent(fileUrl)}`;
        const doc = await pdfjsLib.getDocument(downloadUrl).promise;
        if (cancelled) return;
        setPdfDoc(doc);
        setTotalPages(doc.numPages);
        setCurrentPage(1);
      } catch (e) {
        if (!cancelled) setPdfError(e instanceof Error ? e.message : "Failed to load PDF");
      } finally {
        if (!cancelled) setPdfLoading(false);
      }
    }
    loadPdf();
    return () => { cancelled = true; };
  }, [fileUrl]);

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    let cancelled = false;
    async function renderPage() {
      const page = await pdfDoc.getPage(currentPage);
      if (cancelled) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const container = canvas.parentElement;
      const containerWidth = container ? container.clientWidth - 16 : 800;
      const viewport = page.getViewport({ scale: 1 });
      const scale = containerWidth / viewport.width;
      const scaledViewport = page.getViewport({ scale });
      canvas.height = scaledViewport.height;
      canvas.width = scaledViewport.width;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        await page.render({ canvasContext: ctx, viewport: scaledViewport }).promise;
      }
    }
    renderPage();
    return () => { cancelled = true; };
  }, [pdfDoc, currentPage]);

  if (pdfLoading) return <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  if (pdfError) return <div className="text-xs text-destructive py-4 text-center flex items-center justify-center gap-2"><AlertCircle className="w-4 h-4" />{pdfError}</div>;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-center gap-3 py-2">
        <button onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}
          className="p-1 rounded hover:bg-muted disabled:opacity-30 transition-colors" data-testid="button-pdf-prev">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-xs text-muted-foreground" data-testid="text-pdf-page">{currentPage} / {totalPages}</span>
        <button onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages}
          className="p-1 rounded hover:bg-muted disabled:opacity-30 transition-colors" data-testid="button-pdf-next">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
      <div className="overflow-auto rounded-lg border border-border bg-white dark:bg-gray-900 p-2">
        <canvas ref={canvasRef} className="mx-auto" data-testid="canvas-pdf" />
      </div>
    </div>
  );
}

let _pdfjsLibPromise: Promise<any> | null = null;
function loadPdfjsLib(): Promise<any> {
  if (_pdfjsLibPromise) return _pdfjsLibPromise;
  _pdfjsLibPromise = new Promise((resolve, reject) => {
    const existing = (window as any).pdfjsLib;
    if (existing) { resolve(existing); return; }
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
    script.onload = () => {
      const lib = (window as any).pdfjsLib;
      if (lib) {
        lib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        resolve(lib);
      } else reject(new Error("pdfjsLib not found after script load"));
    };
    script.onerror = () => {
      const fallback = document.createElement("script");
      fallback.src = "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js";
      fallback.onload = () => {
        const lib2 = (window as any).pdfjsLib;
        if (lib2) {
          lib2.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";
          resolve(lib2);
        } else reject(new Error("pdfjsLib not found after fallback load"));
      };
      fallback.onerror = () => reject(new Error("Failed to load PDF.js"));
      document.head.appendChild(fallback);
    };
    document.head.appendChild(script);
  });
  return _pdfjsLibPromise;
}

function ImageViewer({ fileUrl }: { fileUrl: string }) {
  return (
    <div className="overflow-auto rounded-lg border border-border bg-white dark:bg-gray-900 p-2">
      <img src={`/api/download?url=${encodeURIComponent(fileUrl)}`} alt="File preview"
        className="max-w-full mx-auto" data-testid="img-preview" />
    </div>
  );
}

function OriginalPane({ fileInfo }: { fileInfo: FileInfo }) {
  const { t } = useTranslation();
  const ct = fileInfo.content_type || "";
  const isPdf = ct.includes("pdf");
  const isImage = ct.includes("image");

  return (
    <div className="flex flex-col h-full">
      <div className="px-3.5 py-2.5 border-b border-border bg-muted/30 flex items-center gap-2">
        {isPdf ? <FileText className="w-4 h-4 text-red-500" /> : isImage ? <ImageIcon className="w-4 h-4 text-blue-500" /> : <FileText className="w-4 h-4 text-muted-foreground" />}
        <span className="text-xs font-medium truncate">{fileInfo.title || fileInfo.original_filename}</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{formatBytes(fileInfo.bytes)}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {isPdf ? (
          <PdfViewer fileUrl={fileInfo.url} />
        ) : isImage ? (
          <ImageViewer fileUrl={fileInfo.url} />
        ) : (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground mb-3">{t("fp.no_preview")}</p>
            <a href={`/api/download?url=${encodeURIComponent(fileInfo.url)}`} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline" data-testid="link-download-original">
              <Download className="w-4 h-4" />{t("fv.download")}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

function ChunksPane({ chunks, chunkSets, activeChunkSetId, onChunkSetChange }: {
  chunks: ChunkItem[];
  chunkSets: ChunkSetItem[];
  activeChunkSetId: string;
  onChunkSetChange: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col h-full">
      <div className="px-3.5 py-2.5 border-b border-border bg-muted/30 flex items-center gap-2">
        <Layers className="w-4 h-4 text-primary" />
        <span className="text-xs font-medium">{t("fp.chunks")} ({chunks.length})</span>
        {chunkSets.length > 1 && (
          <select value={activeChunkSetId} onChange={(e) => onChunkSetChange(e.target.value)}
            className="ml-auto text-[11px] px-2 py-1 rounded border border-border bg-background" data-testid="select-chunk-set">
            {chunkSets.map((cs) => (
              <option key={cs.chunk_set_id} value={cs.chunk_set_id}>
                {cs.profile_name || "default"} ({cs.chunk_count ?? "?"})
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {chunks.length === 0 ? (
          <p className="text-xs text-muted-foreground italic text-center py-8">{t("fp.no_chunks")}</p>
        ) : (
          chunks.map((chunk) => (
            <div key={chunk.chunk_id} className="rounded-lg border border-border bg-card p-3 space-y-1.5" data-testid={`chunk-${chunk.chunk_index}`}>
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-primary">#{chunk.chunk_index + 1}</span>
                <span className="text-[10px] text-muted-foreground">{chunk.token_count} tokens</span>
              </div>
              {chunk.section_hierarchy && (
                <p className="text-[10px] text-muted-foreground/70 truncate">{chunk.section_hierarchy}</p>
              )}
              <pre className="text-xs whitespace-pre-wrap font-sans leading-relaxed text-foreground/90 max-h-[200px] overflow-y-auto">
                {chunk.content}
              </pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function FilePreview() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const searchStr = useSearch();
  const searchParams = new URLSearchParams(searchStr);
  const fileUrl = searchParams.get("file_url") || "";
  const initialChunkSetId = searchParams.get("chunk_set_id") || "";

  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const [data, setData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeChunkSetId, setActiveChunkSetId] = useState(initialChunkSetId);

  const fetchPreview = useCallback(async (chunkSetId?: string) => {
    if (!fileUrl) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ file_url: fileUrl });
      if (chunkSetId) params.set("chunk_set_id", chunkSetId);
      const res = await apiGet<{ data?: PreviewData } & PreviewData>(`/api/rag/files/preview?${params}`);
      const d = res.data || res;
      setData(d);
      setActiveChunkSetId(d.active_chunk_set_id || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load preview");
    } finally { setLoading(false); }
  }, [fileUrl]);

  useEffect(() => { fetchPreview(initialChunkSetId); }, [fetchPreview, initialChunkSetId]);

  function handleChunkSetChange(id: string) {
    setActiveChunkSetId(id);
    fetchPreview(id);
  }

  if (!fileUrl) {
    return (
      <div className="text-center py-16">
        <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
        <p className="text-muted-foreground">{t("fp.no_file_url")}</p>
      </div>
    );
  }

  if (!isDesktop) {
    return (
      <div className="text-center py-16 space-y-4">
        <Monitor className="w-16 h-16 mx-auto text-muted-foreground/40" />
        <h2 className="text-lg font-semibold">{t("fp.desktop_only_title")}</h2>
        <p className="text-sm text-muted-foreground max-w-md mx-auto">{t("fp.desktop_only_desc")}</p>
        <button onClick={() => navigate(`/file/${encodeURIComponent(fileUrl)}`)}
          className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline mt-4" data-testid="link-back-detail">
          <ArrowLeft className="w-4 h-4" />{t("fp.back_to_detail")}
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4 py-16 text-center">
        <AlertCircle className="w-12 h-12 mx-auto text-destructive/60" />
        <p className="text-muted-foreground">{error || "Preview unavailable"}</p>
        <button onClick={() => navigate(`/file/${encodeURIComponent(fileUrl)}`)}
          className="text-sm text-primary hover:underline" data-testid="link-back-error">
          <ArrowLeft className="w-4 h-4 inline mr-1" />{t("fp.back_to_detail")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3 h-[calc(100vh-80px)]">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3">
        <button onClick={() => navigate(`/file/${encodeURIComponent(fileUrl)}`)} className="p-2 rounded-lg hover:bg-muted transition-colors" data-testid="button-back-preview">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-serif font-bold truncate" data-testid="text-preview-title">
          {data.file_info.title || data.file_info.original_filename || "File Preview"}
        </h1>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="grid grid-cols-2 gap-3 h-[calc(100%-52px)]">
        <div className="rounded-xl border border-border bg-card overflow-hidden" data-testid="pane-original">
          <OriginalPane fileInfo={data.file_info} />
        </div>
        <div className="rounded-xl border border-border bg-card overflow-hidden" data-testid="pane-chunks">
          <ChunksPane
            chunks={data.chunks}
            chunkSets={data.chunk_sets}
            activeChunkSetId={activeChunkSetId}
            onChunkSetChange={handleChunkSetChange}
          />
        </div>
      </motion.div>
    </div>
  );
}

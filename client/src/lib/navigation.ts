import { useSearch as useBrowserSearch } from "wouter/use-browser-location";

export interface AskAiChatTarget {
  kbId: string;
  ragMode: "agentic";
}

const ASK_AI_CHAT_PARAMS = new Set(["kb_id", "rag_mode"]);

function isSafeRelativePath(value: string): boolean {
  return value.startsWith("/") && !value.startsWith("//");
}

export function sanitizeReturnPath(value: string | null | undefined): string | null {
  const raw = String(value || "").trim();
  if (!raw || !isSafeRelativePath(raw)) {
    return null;
  }
  return raw;
}

function getRawSearchParams(rawSearch?: string): URLSearchParams {
  const search = rawSearch ?? (typeof window === "undefined" ? "" : window.location.search);
  return new URLSearchParams(search);
}

export function useRawSearchParams(): URLSearchParams {
  return getRawSearchParams(useBrowserSearch());
}

export function useRawSearch(): string {
  return useBrowserSearch();
}

export function buildAskAiChatPath(kbId: string): string {
  if (!kbId.trim()) {
    throw new Error("Ask AI requires a knowledge base ID");
  }
  const params = new URLSearchParams();
  params.set("kb_id", kbId);
  params.set("rag_mode", "agentic");
  return `/chat?${params.toString()}`;
}

export function getAskAiChatTargetKey(target: AskAiChatTarget): string {
  return `${target.ragMode}\n${target.kbId}`;
}

export function parseAskAiChatTarget(rawSearch?: string): AskAiChatTarget | null {
  const search = rawSearch ?? (typeof window === "undefined" ? "" : window.location.search);
  try {
    decodeURIComponent(search.replace(/\+/g, " "));
  } catch {
    return null;
  }

  const params = new URLSearchParams(search);
  if (Array.from(params.keys()).some((key) => !ASK_AI_CHAT_PARAMS.has(key))) {
    return null;
  }

  const kbIds = params.getAll("kb_id");
  const ragModes = params.getAll("rag_mode");
  if (kbIds.length !== 1 || ragModes.length !== 1) {
    return null;
  }
  const kbId = kbIds[0];
  if (!kbId.trim() || ragModes[0] !== "agentic") {
    return null;
  }
  return { kbId, ragMode: "agentic" };
}

export function buildFileDetailPath(fileUrl: string, from?: string | null): string {
  const params = new URLSearchParams();
  params.set("url", fileUrl);

  const safeFrom = sanitizeReturnPath(from);
  if (safeFrom) {
    params.set("from", safeFrom);
  }

  return `/file-detail?${params.toString()}`;
}

export function buildFilePreviewPath(fileUrl: string, from?: string | null): string {
  const params = new URLSearchParams();
  params.set("file_url", fileUrl);

  const safeFrom = sanitizeReturnPath(from);
  if (safeFrom) {
    params.set("from", safeFrom);
  }

  return `/file-preview?${params.toString()}`;
}

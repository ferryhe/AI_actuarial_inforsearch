export interface ChatDisplayNameSource {
  title?: unknown;
  original_filename?: unknown;
  filename?: unknown;
  url?: unknown;
  file_url?: unknown;
  source_url?: unknown;
}

export function getChatValidName(value: unknown): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized && normalized.toLowerCase() !== "unknown" ? normalized : "";
}

function unwrapFileUrl(value: unknown): string {
  const rawUrl = typeof value === "string" ? value.trim() : "";
  if (!rawUrl) return "";
  try {
    const parsed = new URL(rawUrl, "https://chat.local");
    if (["/file-detail", "/file-preview", "/file_preview"].includes(parsed.pathname)) {
      return (parsed.searchParams.get("url") || parsed.searchParams.get("file_url") || "").trim();
    }
    if (rawUrl.startsWith("/file/")) {
      return decodeURIComponent(rawUrl.slice("/file/".length).split("?", 1)[0]);
    }
  } catch {
    return rawUrl;
  }
  return rawUrl;
}

function fileUrlBasename(source: ChatDisplayNameSource): string {
  const fileUrl = unwrapFileUrl(source.file_url) || unwrapFileUrl(source.source_url) || unwrapFileUrl(source.url);
  if (!fileUrl) return "";
  try {
    const pathname = new URL(fileUrl, "https://chat.local").pathname;
    const basename = pathname.replace(/\\/g, "/").replace(/\/$/, "").split("/").pop() || "";
    try {
      return getChatValidName(decodeURIComponent(basename));
    } catch {
      return getChatValidName(basename);
    }
  } catch {
    return "";
  }
}

export function getCanonicalDisplayName(source: ChatDisplayNameSource, fallback: string): string {
  return getChatValidName(source.title)
    || getChatValidName(source.original_filename)
    || getChatValidName(source.filename)
    || fileUrlBasename(source)
    || fallback;
}

export function getChatDisplayName(source: ChatDisplayNameSource, fallback: string): string {
  return getCanonicalDisplayName(source, fallback);
}

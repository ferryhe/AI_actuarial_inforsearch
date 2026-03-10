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

export function getCurrentRelativeLocation(): string {
  if (typeof window === "undefined") {
    return "/";
  }

  const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return sanitizeReturnPath(next) || "/";
}

export function getReturnPathFromSearch(search: string): string | null {
  return sanitizeReturnPath(new URLSearchParams(search).get("from"));
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

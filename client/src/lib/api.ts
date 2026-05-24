export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getStoredAuthToken(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem("api_write_auth_token") || window.localStorage.getItem("api_write_auth_token") || "";
}

export function setStoredAuthToken(token: string, persist = false): void {
  if (typeof window === "undefined") return;
  const normalized = token.trim();
  if (!normalized) {
    window.sessionStorage.removeItem("api_write_auth_token");
    if (persist) window.localStorage.removeItem("api_write_auth_token");
    return;
  }
  window.sessionStorage.setItem("api_write_auth_token", normalized);
  if (persist) {
    window.localStorage.setItem("api_write_auth_token", normalized);
  }
}

function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const prefix = `${name}=`;
  const parts = document.cookie.split("; ");
  for (const part of parts) {
    if (part.startsWith(prefix)) {
      return decodeURIComponent(part.slice(prefix.length));
    }
  }
  return "";
}

async function apiFetch<T = unknown>(url: string, options?: RequestInit): Promise<T> {
  const authToken = getStoredAuthToken();
  const method = (options?.method || "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string> | undefined),
  };
  if (authToken && !headers["X-Auth-Token"]) {
    headers["X-Auth-Token"] = authToken;
  }
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method) && !headers["X-CSRF-Token"]) {
    const csrfToken = readCookie("csrf_token");
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const res = await fetch(url, {
    ...options,
    credentials: options?.credentials ?? "include",
    headers,
  });

  if (!res.ok) {
    let detail: unknown;
    try {
      const body = await res.json();
      detail = body.error || body.message || body.detail;
    } catch {}
    const message = typeof detail === "string" && detail ? detail : `Request failed (${res.status})`;
    throw new ApiError(message, res.status, detail);
  }

  if (res.status === 204) return null as T;

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return null as T;

  return res.json() as Promise<T>;
}

export function apiGet<T = unknown>(url: string): Promise<T> {
  return apiFetch<T>(url);
}

export function apiPost<T = unknown>(url: string, body?: unknown): Promise<T> {
  return apiFetch<T>(url, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPut<T = unknown>(url: string, body?: unknown): Promise<T> {
  return apiFetch<T>(url, {
    method: "PUT",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPatch<T = unknown>(url: string, body?: unknown): Promise<T> {
  return apiFetch<T>(url, {
    method: "PATCH",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete<T = unknown>(url: string): Promise<T> {
  return apiFetch<T>(url, { method: "DELETE" });
}

export function formatApiErrorDetail(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = err.detail;
    if (typeof detail === "string") return detail || err.message;
    if (detail === null || detail === undefined) return err.message;
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return err instanceof Error ? err.message : "";
}

import { ApiError } from "@/lib/api";

export function formatAuthSubmitError(err: unknown, t: (key: string) => string, fallbackKey: string): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return t("auth.error.rate_limited");
    if (err.status >= 500) return t("auth.error.system_unavailable");
    return typeof err.detail === "string" && err.detail ? err.detail : err.message;
  }
  return t(fallbackKey);
}

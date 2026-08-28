import { ApiError, formatApiErrorDetail } from "@/lib/api";

type Translate = (key: string) => string;

export function formatSettingsMutationError(
  error: unknown,
  t: Translate,
  fallbackKey: string
): string {
  if (!(error instanceof ApiError)) return t(fallbackKey);

  const detail = formatApiErrorDetail(error) || error.message;
  let classificationKey = fallbackKey;
  if (error.status === 401) {
    classificationKey = "settings.error_session";
  } else if (error.status === 403) {
    classificationKey = detail.toLowerCase().includes("csrf")
      ? "settings.error_csrf"
      : "settings.error_permission";
  } else if (error.status === 400 || error.status === 422) {
    classificationKey = "settings.error_validation";
  } else if (error.status >= 500 && error.status < 600) {
    classificationKey = "settings.error_config_write";
  }

  return `${t(classificationKey)}: ${detail}`;
}

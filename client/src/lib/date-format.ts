function parseDateTime(value: string | null | undefined, assumeUtcForNaive = false): Date | null {
  if (!value) return null;
  const normalized = assumeUtcForNaive && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? `${value}Z` : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatUtcIso(value: string | null | undefined, assumeUtcForNaive = false): string | null {
  return parseDateTime(value, assumeUtcForNaive)?.toISOString() ?? null;
}

export function formatDateTime(
  value: string | null | undefined,
  lang: string,
  options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" },
  assumeUtcForNaive = false,
): string {
  const date = parseDateTime(value, assumeUtcForNaive);
  if (!date) return "—";
  try {
    return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", options).format(date);
  } catch {
    return "—";
  }
}

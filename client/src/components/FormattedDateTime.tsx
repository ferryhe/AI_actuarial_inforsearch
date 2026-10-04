import { formatDateTime, formatUtcIso } from "@/lib/date-format";

export function FormattedDateTime({
  value,
  lang,
  fallback = "—",
  assumeUtcForNaive = false,
}: {
  value: string | null | undefined;
  lang: string;
  fallback?: string;
  assumeUtcForNaive?: boolean;
}) {
  const iso = formatUtcIso(value, assumeUtcForNaive);
  if (!iso) return <>{fallback}</>;
  return <time dateTime={iso} title={`${iso} (UTC)`}>{formatDateTime(value, lang, undefined, assumeUtcForNaive)}</time>;
}

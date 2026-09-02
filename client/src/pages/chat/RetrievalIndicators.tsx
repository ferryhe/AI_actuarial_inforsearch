type Translate = (key: string) => string;

const RETRIEVAL_METHODS = new Set([
  "vector",
  "summaries",
  "titles",
  "sections",
  "relations",
  "formulas",
  "tables",
  "calculation_terms",
]);

interface RetrievalIndicatorsProps {
  semanticRelevance100?: number | null;
  keywordRelevance100?: number | null;
  retrievalMethod?: string | null;
  t: Translate;
}

function isValidRelevance(value: number | null | undefined): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 100;
}

function formatRelevance(value: number | null | undefined): string {
  return isValidRelevance(value) ? `${value}/100` : "—";
}

function methodKey(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  return RETRIEVAL_METHODS.has(normalized) ? normalized : "other";
}

export function RetrievalIndicators({
  semanticRelevance100,
  keywordRelevance100,
  retrievalMethod,
  t,
}: RetrievalIndicatorsProps) {
  const semanticLabel = t("chat.relevance.semantic");
  const keywordLabel = t("chat.relevance.keyword");
  const methodLabel = t("chat.relevance.method");
  const method = methodKey(retrievalMethod);
  const semanticValue = formatRelevance(semanticRelevance100);
  const keywordValue = formatRelevance(keywordRelevance100);
  const methodValue = t(`chat.retrieval_method.${method}`);
  const badges: [string, string][] = [];

  if (method === "vector" || isValidRelevance(semanticRelevance100)) {
    badges.push([semanticLabel, semanticValue]);
  }
  if ((method !== "vector" && method !== "other") || isValidRelevance(keywordRelevance100)) {
    badges.push([keywordLabel, keywordValue]);
  }
  badges.push([methodLabel, methodValue]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {badges.map(([label, value]) => (
        <span
          key={label}
          aria-label={`${label}: ${value}`}
          className="whitespace-nowrap rounded-full border border-border bg-muted px-2 py-0.5 text-muted-foreground"
        >
          {label}: {value}
        </span>
      ))}
    </div>
  );
}

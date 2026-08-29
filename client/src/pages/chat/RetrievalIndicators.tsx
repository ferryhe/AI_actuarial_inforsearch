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

function formatRelevance(value: number | null | undefined): string {
  return Number.isInteger(value) && Number(value) >= 0 && Number(value) <= 100
    ? `${value}/100`
    : "—";
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
  const semanticValue = formatRelevance(semanticRelevance100);
  const keywordValue = formatRelevance(keywordRelevance100);
  const methodValue = t(`chat.retrieval_method.${methodKey(retrievalMethod)}`);
  const badges = [
    [semanticLabel, semanticValue],
    [keywordLabel, keywordValue],
    [methodLabel, methodValue],
  ];

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

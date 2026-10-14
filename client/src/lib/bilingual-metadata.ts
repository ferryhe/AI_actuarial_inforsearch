export interface CatalogMetadataEntry {
  title: string;
  summary: string;
  category: string;
  keywords: string[];
}

export interface LegacyCatalogMetadata {
  title?: unknown;
  summary?: unknown;
  category?: unknown;
  keywords?: unknown;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function hasCompleteLocalizedCatalogMetadata(bilingual: unknown, lang: string): boolean {
  if ((lang !== "zh" && lang !== "en") || !bilingual || typeof bilingual !== "object") return false;
  const packages = bilingual as Record<string, unknown>;
  const entry = packages[lang];
  if (!entry || typeof entry !== "object") return false;
  const candidate = entry as Record<string, unknown>;
  const keywords = Array.isArray(candidate.keywords)
    ? candidate.keywords.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : [];
  const selectedCategory = text(candidate.category);
  const other = packages[lang === "zh" ? "en" : "zh"];
  const otherCategory = other && typeof other === "object"
    ? text((other as Record<string, unknown>).category)
    : "";
  return Boolean(text(candidate.title) && text(candidate.summary) && selectedCategory && keywords.length > 0)
    && (!otherCategory || selectedCategory === otherCategory);
}

export function localizedCatalogMetadata(
  bilingual: unknown,
  lang: string,
  legacy: LegacyCatalogMetadata,
): CatalogMetadataEntry {
  const fallback: CatalogMetadataEntry = {
    title: text(legacy.title),
    summary: text(legacy.summary),
    category: text(legacy.category),
    keywords: Array.isArray(legacy.keywords)
      ? legacy.keywords.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      : [],
  };
  if (!hasCompleteLocalizedCatalogMetadata(bilingual, lang)) return fallback;
  const candidate = (bilingual as Record<string, Record<string, unknown>>)[lang];
  const keywords = Array.isArray(candidate.keywords)
    ? candidate.keywords.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : [];
  const title = text(candidate.title);
  const summary = text(candidate.summary);
  const category = text(candidate.category);
  return { title, summary, category, keywords };
}

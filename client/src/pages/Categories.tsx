import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "wouter";
import { ArrowRight, Search, Sparkles, Tags } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet, formatApiErrorDetail } from "@/lib/api";
import { categoryDisplayName } from "@/lib/category-labels";
import { useAuth } from "@/context/AuthContext";
import { findDedicatedCategoryKnowledgeBaseId } from "@/lib/chat-knowledge-bases";
import { buildAskAiChatPath } from "@/lib/navigation";
import { fetchKnowledgeBases as fetchChatKnowledgeBases } from "./chat/api";
import type { KnowledgeBase as ChatKnowledgeBase } from "./chat/types";

interface CategoryOption {
  name: string;
  label?: string;
  labels?: { en?: string; zh?: string };
  count?: number | null;
}

interface CategoriesResponse {
  categories?: Array<string | CategoryOption>;
}

interface CategorizedKnowledgeBase {
  id?: string;
  kb_id?: string;
  categories?: string[];
}

interface KnowledgeBasesResponse {
  knowledge_bases?: CategorizedKnowledgeBase[];
  data?: { knowledge_bases?: CategorizedKnowledgeBase[] };
}

function normalizeCategories(items: CategoriesResponse["categories"]): CategoryOption[] {
  return (items || [])
    .map<CategoryOption | null>((item) => {
      if (typeof item === "string") {
        const name = item.trim();
        return name ? { name } : null;
      }
      if (item && typeof item.name === "string" && item.name.trim()) {
        return {
          name: item.name.trim(),
          label: typeof item.label === "string" ? item.label : undefined,
          labels: item.labels,
          count: typeof item.count === "number" ? item.count : null,
        };
      }
      return null;
    })
    .filter((item): item is CategoryOption => item !== null);
}

function databaseCategoryPath(category: string): string {
  const params = new URLSearchParams({ category });
  return `/database?${params.toString()}`;
}

export default function Categories() {
  const { t, lang } = useTranslation();
  const { permissions } = useAuth();
  const canAskAi = permissions.includes("chat.view") && permissions.includes("chat.query");
  const [, navigate] = useLocation();
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [categorizedKnowledgeBases, setCategorizedKnowledgeBases] = useState<CategorizedKnowledgeBase[]>([]);
  const [chatKnowledgeBases, setChatKnowledgeBases] = useState<ChatKnowledgeBase[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    Promise.all([
      apiGet<CategoriesResponse>("/api/categories?mode=used"),
      apiGet<KnowledgeBasesResponse>("/api/rag/knowledge-bases")
        .catch((): KnowledgeBasesResponse => ({})),
      canAskAi
        ? fetchChatKnowledgeBases().catch(() => [] as ChatKnowledgeBase[])
        : Promise.resolve([] as ChatKnowledgeBase[]),
    ])
      .then(([result, knowledgeBaseResult, chatKbList]) => {
        if (!cancelled) {
          setCategories(normalizeCategories(result.categories));
          setCategorizedKnowledgeBases(
            knowledgeBaseResult.knowledge_bases
              || knowledgeBaseResult.data?.knowledge_bases
              || [],
          );
          setChatKnowledgeBases(chatKbList);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(formatApiErrorDetail(err) || t("categories.load_error"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [canAskAi, t]);

  const visibleCategories = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return categories;
    return categories.filter((category) => {
      const name = category.name.toLowerCase();
      const label = categoryDisplayName(category, lang).toLowerCase();
      return name.includes(normalizedQuery) || label.includes(normalizedQuery);
    });
  }, [categories, lang, query]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="categories-title">
          {t("categories.title")}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
          {t("categories.subtitle")}
        </p>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <label className="relative block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("categories.search_placeholder")}
            aria-label={t("categories.search_placeholder")}
            className="w-full rounded-lg border border-input bg-background py-2 pl-9 pr-3 text-sm outline-none transition-colors focus:border-primary"
            data-testid="input-category-search"
          />
        </label>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" data-testid="categories-error">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="categories-loading">
          {[...Array(6)].map((_, index) => (
            <div key={index} className="h-28 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : visibleCategories.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center" data-testid="categories-empty">
          <Tags className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
          <p className="font-medium text-muted-foreground">{t("categories.no_categories")}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="categories-grid">
          {visibleCategories.map((category) => {
            const dedicatedKbId = canAskAi
              ? findDedicatedCategoryKnowledgeBaseId(
                category.name,
                categorizedKnowledgeBases,
                chatKnowledgeBases,
              )
              : null;
            const askAiPath = dedicatedKbId ? buildAskAiChatPath(dedicatedKbId) : "";
            return (
              <div key={category.name} className="group h-full rounded-xl border border-border bg-card p-5 transition-all hover:border-primary/30 hover:shadow-md">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Tags className="h-5 w-5" strokeWidth={1.8} />
                    </div>
                    <div className="min-w-0">
                      <h2 className="truncate text-sm font-semibold" data-testid="category-card-title">
                        {categoryDisplayName(category, lang)}
                      </h2>
                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{category.name}</p>
                    </div>
                  </div>
                  {typeof category.count === "number" && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                      {category.count}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 text-xs font-medium">
                  <Link
                    href={databaseCategoryPath(category.name)}
                    className="inline-flex items-center gap-1.5 text-primary hover:underline"
                    aria-label={t("categories.open")}
                  >
                    <span>{t("categories.open")}</span>
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </Link>
                  <button
                    type="button"
                    onClick={() => dedicatedKbId && navigate(askAiPath)}
                    disabled={!dedicatedKbId}
                    aria-label={dedicatedKbId ? t("common.ask_ai") : t("categories.ask_ai_unavailable")}
                    title={dedicatedKbId ? t("common.ask_ai") : t("categories.ask_ai_unavailable")}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-primary transition-colors hover:bg-primary/5 disabled:cursor-not-allowed disabled:text-muted-foreground disabled:opacity-60"
                    data-testid={`button-ask-ai-category-${category.name}`}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {t("common.ask_ai")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

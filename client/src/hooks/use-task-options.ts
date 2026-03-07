import { useState, useEffect, useCallback, useRef } from "react";
import { apiGet } from "@/lib/api";

interface SearchEngine {
  name: string;
  value: string;
  available: boolean;
}

interface TaskOptions {
  engines: SearchEngine[];
  providers: string[];
  categories: string[];
  conversionTools: string[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

interface EngineResponse {
  engines?: Array<{ name: string; key?: string; available?: boolean }>;
  [key: string]: unknown;
}

interface ProviderResponse {
  providers?: Array<{ name?: string; provider?: string; [key: string]: unknown }> | string[];
  [key: string]: unknown;
}

interface CategoryResponse {
  categories?: string[];
  data?: string[];
  [key: string]: unknown;
}

interface ModelResponse {
  models?: Array<{ name?: string; key?: string; [key: string]: unknown }> | string[];
  tools?: string[];
  [key: string]: unknown;
}

const FALLBACK_ENGINES: SearchEngine[] = [
  { name: "Brave Search", value: "brave", available: true },
  { name: "Google (SerpAPI)", value: "google", available: true },
  { name: "Google (Serper)", value: "serper", available: true },
  { name: "Tavily", value: "tavily", available: true },
];

const FALLBACK_CONVERSION_TOOLS = ["docling", "marker", "local", "mistral", "deepseekocr"];

const cache: {
  engines?: SearchEngine[];
  providers?: string[];
  categories?: string[];
  conversionTools?: string[];
  timestamp?: number;
} = {};

const CACHE_TTL = 60000;

function isCacheValid(): boolean {
  return !!cache.timestamp && Date.now() - cache.timestamp < CACHE_TTL;
}

export function useTaskOptions(): TaskOptions {
  const [engines, setEngines] = useState<SearchEngine[]>(cache.engines || FALLBACK_ENGINES);
  const [providers, setProviders] = useState<string[]>(cache.providers || []);
  const [categories, setCategories] = useState<string[]>(cache.categories || []);
  const [conversionTools, setConversionTools] = useState<string[]>(cache.conversionTools || FALLBACK_CONVERSION_TOOLS);
  const [loading, setLoading] = useState(!isCacheValid());
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(false);

  const fetchOptions = useCallback(async (force = false) => {
    if (!force && isCacheValid()) {
      setEngines(cache.engines || FALLBACK_ENGINES);
      setProviders(cache.providers || []);
      setCategories(cache.categories || []);
      setConversionTools(cache.conversionTools || FALLBACK_CONVERSION_TOOLS);
      return;
    }

    setLoading(true);
    setError(null);

    const results = await Promise.allSettled([
      apiGet<EngineResponse>("/api/config/search-engines"),
      apiGet<ProviderResponse>("/api/config/llm-providers"),
      apiGet<CategoryResponse>("/api/categories?mode=used"),
      apiGet<ModelResponse>("/api/config/ai-models"),
    ]);

    const [enginesResult, providersResult, categoriesResult, modelsResult] = results;

    let fetchedEngines = FALLBACK_ENGINES;
    if (enginesResult.status === "fulfilled" && enginesResult.value?.engines) {
      fetchedEngines = enginesResult.value.engines.map((e) => ({
        name: e.name,
        value: e.key || e.name.toLowerCase().replace(/[^a-z0-9]/g, "_"),
        available: e.available !== false,
      }));
      if (fetchedEngines.length === 0) fetchedEngines = FALLBACK_ENGINES;
    }

    let fetchedProviders: string[] = [];
    if (providersResult.status === "fulfilled" && providersResult.value?.providers) {
      const prov = providersResult.value.providers;
      fetchedProviders = Array.isArray(prov)
        ? prov.map((p) => (typeof p === "string" ? p : p.name || p.provider || "")).filter(Boolean)
        : [];
    }

    let fetchedCategories: string[] = [];
    if (categoriesResult.status === "fulfilled") {
      const catRes = categoriesResult.value;
      fetchedCategories = catRes?.categories || catRes?.data || [];
      if (!Array.isArray(fetchedCategories)) fetchedCategories = [];
    }

    let fetchedTools = FALLBACK_CONVERSION_TOOLS;
    if (modelsResult.status === "fulfilled") {
      const modelRes = modelsResult.value;
      if (modelRes?.tools && Array.isArray(modelRes.tools) && modelRes.tools.length > 0) {
        fetchedTools = modelRes.tools;
      } else if (modelRes?.models && Array.isArray(modelRes.models) && modelRes.models.length > 0) {
        const toolNames = modelRes.models.map((m) =>
          typeof m === "string" ? m : m.name || m.key || ""
        ).filter(Boolean);
        if (toolNames.length > 0) fetchedTools = toolNames;
      }
    }

    cache.engines = fetchedEngines;
    cache.providers = fetchedProviders;
    cache.categories = fetchedCategories;
    cache.conversionTools = fetchedTools;
    cache.timestamp = Date.now();

    setEngines(fetchedEngines);
    setProviders(fetchedProviders);
    setCategories(fetchedCategories);
    setConversionTools(fetchedTools);
    setLoading(false);

    const failedCount = results.filter((r) => r.status === "rejected").length;
    if (failedCount === results.length) {
      setError("Failed to load all options from backend");
    } else if (failedCount > 0) {
      setError(`Some options failed to load (${failedCount}/${results.length})`);
    }
  }, []);

  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true;
      fetchOptions();
    }
  }, [fetchOptions]);

  const refresh = useCallback(() => {
    fetchOptions(true);
  }, [fetchOptions]);

  return { engines, providers, categories, conversionTools, loading, error, refresh };
}

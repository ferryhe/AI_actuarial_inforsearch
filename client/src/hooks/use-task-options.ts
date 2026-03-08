import { useState, useEffect, useCallback, useRef } from "react";
import { apiGet } from "@/lib/api";

interface SearchEngine {
  name: string;
  value: string;
  available: boolean;
}

export interface ConversionTool {
  name: string;
  provider: string;
  displayName: string;
}

interface TaskOptions {
  engines: SearchEngine[];
  providers: string[];
  categories: string[];
  conversionTools: string[];
  conversionToolsInfo: ConversionTool[];
  catalogProviders: string[];
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

interface AvailableModel {
  name?: string;
  display_name?: string;
  types?: string[];
  [key: string]: unknown;
}

interface AiModelsResponse {
  current?: {
    catalog?: { provider?: string; model?: string };
    ocr?: { provider?: string; model?: string };
    [key: string]: unknown;
  };
  available?: Record<string, AvailableModel[]>;
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

const FALLBACK_CONVERSION_TOOLS = ["docling", "marker", "mistral", "deepseekocr"];
const FALLBACK_CONVERSION_TOOLS_INFO: ConversionTool[] = [
  { name: "docling", provider: "local", displayName: "Docling" },
  { name: "marker", provider: "local", displayName: "Marker" },
  { name: "mistral", provider: "mistral", displayName: "Mistral OCR" },
  { name: "deepseekocr", provider: "siliconflow", displayName: "DeepSeek OCR" },
];

const cache: {
  engines?: SearchEngine[];
  providers?: string[];
  categories?: string[];
  conversionTools?: string[];
  conversionToolsInfo?: ConversionTool[];
  catalogProviders?: string[];
  timestamp?: number;
} = {};

const CACHE_TTL = 60000;

function isCacheValid(): boolean {
  return !!cache.timestamp && Date.now() - cache.timestamp < CACHE_TTL;
}

const ENGINE_DEFS: ConversionTool[] = [
  { name: "docling", provider: "local", displayName: "Docling" },
  { name: "marker", provider: "local", displayName: "Marker" },
  { name: "local", provider: "local", displayName: "Local (Basic)" },
  { name: "mistral", provider: "mistral", displayName: "Mistral OCR" },
  { name: "deepseekocr", provider: "siliconflow", displayName: "DeepSeek OCR" },
];

function extractOcrTools(available: Record<string, AvailableModel[]>): ConversionTool[] {
  const providersWithOcr = new Set<string>();
  for (const [provider, models] of Object.entries(available)) {
    if (!Array.isArray(models)) continue;
    for (const m of models) {
      if ((m.types || []).includes("ocr")) {
        providersWithOcr.add(provider);
        break;
      }
    }
  }
  // Always include local tools (docling, marker, local — no API key required).
  // Add API-based tools only when their provider has OCR-capable models configured.
  const localTools = ENGINE_DEFS.filter((e) => e.provider === "local");
  const apiTools = ENGINE_DEFS.filter((e) => e.provider !== "local" && providersWithOcr.has(e.provider));
  return [...localTools, ...apiTools];
}

function extractCatalogProviders(available: Record<string, AvailableModel[]>): string[] {
  const providers = new Set<string>();
  for (const [provider, models] of Object.entries(available)) {
    if (!Array.isArray(models)) continue;
    for (const m of models) {
      const types = m.types || [];
      if (types.includes("chat") || types.includes("catalog")) {
        providers.add(provider);
        break;
      }
    }
  }
  return Array.from(providers);
}

export function useTaskOptions(): TaskOptions {
  const [engines, setEngines] = useState<SearchEngine[]>(cache.engines || FALLBACK_ENGINES);
  const [providers, setProviders] = useState<string[]>(cache.providers || []);
  const [categories, setCategories] = useState<string[]>(cache.categories || []);
  const [conversionTools, setConversionTools] = useState<string[]>(cache.conversionTools || FALLBACK_CONVERSION_TOOLS);
  const [conversionToolsInfo, setConversionToolsInfo] = useState<ConversionTool[]>(cache.conversionToolsInfo || FALLBACK_CONVERSION_TOOLS_INFO);
  const [catalogProviders, setCatalogProviders] = useState<string[]>(cache.catalogProviders || []);
  const [loading, setLoading] = useState(!isCacheValid());
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef(false);

  const fetchOptions = useCallback(async (force = false) => {
    if (!force && isCacheValid()) {
      setEngines(cache.engines || FALLBACK_ENGINES);
      setProviders(cache.providers || []);
      setCategories(cache.categories || []);
      setConversionTools(cache.conversionTools || FALLBACK_CONVERSION_TOOLS);
      setConversionToolsInfo(cache.conversionToolsInfo || FALLBACK_CONVERSION_TOOLS_INFO);
      setCatalogProviders(cache.catalogProviders || []);
      return;
    }

    setLoading(true);
    setError(null);

    const results = await Promise.allSettled([
      apiGet<EngineResponse>("/api/config/search-engines"),
      apiGet<ProviderResponse>("/api/config/llm-providers"),
      apiGet<CategoryResponse>("/api/categories?mode=used"),
      apiGet<AiModelsResponse>("/api/config/ai-models"),
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
    let fetchedToolsInfo = FALLBACK_CONVERSION_TOOLS_INFO;
    let fetchedCatalogProviders: string[] = [];

    if (modelsResult.status === "fulfilled") {
      const modelRes = modelsResult.value;
      if (modelRes?.available && typeof modelRes.available === "object") {
        const ocrTools = extractOcrTools(modelRes.available);
        if (ocrTools.length > 0) {
          fetchedToolsInfo = ocrTools;
          fetchedTools = ocrTools.map((t) => t.name);
        }
        fetchedCatalogProviders = extractCatalogProviders(modelRes.available);
      } else if (modelRes?.tools && Array.isArray(modelRes.tools) && modelRes.tools.length > 0) {
        fetchedTools = modelRes.tools;
        fetchedToolsInfo = modelRes.tools.map((t) => ({ name: t, provider: "unknown", displayName: t }));
      }
    }

    cache.engines = fetchedEngines;
    cache.providers = fetchedProviders;
    cache.categories = fetchedCategories;
    cache.conversionTools = fetchedTools;
    cache.conversionToolsInfo = fetchedToolsInfo;
    cache.catalogProviders = fetchedCatalogProviders;
    cache.timestamp = Date.now();

    setEngines(fetchedEngines);
    setProviders(fetchedProviders);
    setCategories(fetchedCategories);
    setConversionTools(fetchedTools);
    setConversionToolsInfo(fetchedToolsInfo);
    setCatalogProviders(fetchedCatalogProviders);
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

  return { engines, providers, categories, conversionTools, conversionToolsInfo, catalogProviders, loading, error, refresh };
}

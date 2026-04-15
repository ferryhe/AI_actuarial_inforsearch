import { useCallback, useEffect, useState } from "react";
import { Bot, Cpu, Globe, Loader2, RefreshCw, Settings as SettingsIcon, Tag, AlertCircle } from "lucide-react";
import { apiGet } from "@/lib/api";

interface BackendSettings {
  defaults?: Record<string, unknown>;
  search?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
}

interface ProviderInfo {
  provider: string;
  display_name: string;
  source: string;
  status: string;
  api_base_url?: string | null;
}

interface AiModels {
  current: Record<string, unknown>;
  available: Record<string, Array<{ name: string; display_name?: string }>>;
}

interface SearchEngine {
  id: string;
  name: string;
  configured: boolean;
}

interface CategoriesConfig {
  categories: Record<string, string[]>;
  ai_filter_keywords?: string[];
  ai_keywords?: string[];
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="overflow-auto rounded-lg bg-muted/40 p-4 text-xs leading-6">{JSON.stringify(value, null, 2)}</pre>;
}

export default function NativeSettings() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [backendSettings, setBackendSettings] = useState<BackendSettings | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [aiModels, setAiModels] = useState<AiModels | null>(null);
  const [searchEngines, setSearchEngines] = useState<SearchEngine[]>([]);
  const [categories, setCategories] = useState<CategoriesConfig | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [backendRes, providerRes, modelRes, engineRes, categoryRes] = await Promise.all([
        apiGet<BackendSettings>("/api/config/backend-settings"),
        apiGet<{ providers: ProviderInfo[] }>("/api/config/llm-providers"),
        apiGet<AiModels>("/api/config/ai-models"),
        apiGet<{ engines: SearchEngine[] }>("/api/config/search-engines"),
        apiGet<CategoriesConfig>("/api/config/categories"),
      ]);
      setBackendSettings(backendRes);
      setProviders(providerRes.providers || []);
      setAiModels(modelRes);
      setSearchEngines(engineRes.engines || []);
      setCategories(categoryRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-serif font-bold tracking-tight">系统设置</h1>
          <p className="mt-1 text-sm text-muted-foreground">FastAPI-native 只读设置页，展示 PR1 暴露的配置读取接口。</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">PR1 read-only</span>
          <button onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> 刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> 正在加载设置…</div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2"><SettingsIcon className="h-4 w-4 text-primary" /><h2 className="font-semibold">后端设置</h2></div>
            <JsonBlock value={backendSettings} />
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2"><Bot className="h-4 w-4 text-primary" /><h2 className="font-semibold">LLM Providers</h2></div>
            <div className="space-y-3">
              {providers.map((provider) => (
                <div key={`${provider.provider}-${provider.source}`} className="rounded-lg border border-border p-3 text-sm">
                  <div className="font-medium">{provider.display_name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">provider={provider.provider} · source={provider.source} · status={provider.status}</div>
                  <div className="mt-1 break-all text-xs text-muted-foreground">{provider.api_base_url || "default base URL"}</div>
                </div>
              ))}
              {providers.length === 0 && <p className="text-sm text-muted-foreground">暂无 provider 配置。</p>}
            </div>
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2"><Cpu className="h-4 w-4 text-primary" /><h2 className="font-semibold">AI Models</h2></div>
            <JsonBlock value={aiModels} />
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2"><Globe className="h-4 w-4 text-primary" /><h2 className="font-semibold">搜索引擎</h2></div>
            <div className="space-y-3">
              {searchEngines.map((engine) => (
                <div key={engine.id} className="flex items-center justify-between rounded-lg border border-border p-3 text-sm">
                  <span>{engine.name}</span>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${engine.configured ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground"}`}>{engine.configured ? "configured" : "missing key"}</span>
                </div>
              ))}
              {searchEngines.length === 0 && <p className="text-sm text-muted-foreground">暂无搜索引擎配置。</p>}
            </div>
          </section>

          <section className="rounded-xl border border-border bg-card p-5 lg:col-span-2">
            <div className="mb-4 flex items-center gap-2"><Tag className="h-4 w-4 text-primary" /><h2 className="font-semibold">分类配置</h2></div>
            <JsonBlock value={categories} />
          </section>
        </div>
      )}
    </div>
  );
}

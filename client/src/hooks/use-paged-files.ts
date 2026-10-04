import { useCallback, useEffect, useState } from "react";

export interface FilePage<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface FilePageFilters {
  search: string;
  categories: string[];
  limit: number;
  offset: number;
}

export function usePagedFiles<T>(
  load: (filters: FilePageFilters, signal: AbortSignal) => Promise<FilePage<T>>,
  enabled = true,
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const limit = 50;
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  const changeSearch = useCallback((value: string) => { setSearch(value); setOffset(0); }, []);
  const changeCategories = useCallback((value: string[]) => { setCategories(value); setOffset(0); }, []);

  useEffect(() => { setSearch(""); setCategories([]); setOffset(0); }, [load]);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setItems([]);
    // The timer also cancels a pending debounce when filters change.
    const timer = window.setTimeout(async () => {
      try {
        const page = await load({ search, categories, limit, offset }, controller.signal);
        if (controller.signal.aborted) return;
        if (offset > 0 && offset >= page.total) {
          setOffset(Math.max(0, Math.ceil(page.total / limit) - 1) * limit);
          return;
        }
        setItems(page.items);
        setTotal(page.total);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setItems([]);
        setTotal(0);
        setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [load, enabled, search, categories, offset, revision]);

  return { items, total, limit, offset, loading, error, search, categories,
    setSearch: changeSearch, setCategories: changeCategories, setOffset, reload };
}

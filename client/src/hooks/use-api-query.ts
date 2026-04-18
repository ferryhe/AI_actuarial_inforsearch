/**
 * use-api-query.ts
 *
 * Standardized API state management hook for React components.
 * Handles loading, error, and success states consistently.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useApiQuery(
 *     () => apiGet<MyDataType>('/api/ops-read/stats'),
 *     { watch: false }
 *   );
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseApiQueryOptions {
  /** If true, re-fetches when deps change (requires deps). Default: false */
  watch?: boolean;
  /** Dependencies that trigger re-fetch when watch=true. Default: [] */
  deps?: unknown[];
  /** Initial data to use while first fetch is pending */
  initialData?: unknown;
  /** Callback invoked on each successful fetch */
  onSuccess?: (data: unknown) => void;
  /** Callback invoked on each error */
  onError?: (error: Error) => void;
}

export interface UseApiQueryResult<T> {
  /** The fetched data (undefined until first successful fetch) */
  data: T | undefined;
  /** True while initial fetch is in progress */
  loading: boolean;
  /** True while a re-fetch (after initial) is in progress */
  refreshing: boolean;
  /** The most recent error, if any */
  error: Error | null;
  /** Manually trigger a re-fetch */
  refetch: () => void;
  /** Reset to initial state */
  reset: () => void;
}

/**
 * Standardized API query hook.
 *
 * @param queryFn - Async function that returns the data (e.g. `() => apiGet<T>('/api/...')`)
 * @param options - Configuration options
 */
export function useApiQuery<T>(
  queryFn: () => Promise<T>,
  options: UseApiQueryOptions = {}
): UseApiQueryResult<T> {
  const { watch = false, deps = [], initialData, onSuccess, onError } = options;

  const [data, setData] = useState<T | undefined>(initialData as T | undefined);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const queryFnRef = useRef(queryFn);
  queryFnRef.current = queryFn;

  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  onSuccessRef.current = onSuccess;
  onErrorRef.current = onError;

  const fetch = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const result = await queryFnRef.current();
      setData(result);
      onSuccessRef.current?.(result);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      onErrorRef.current?.(error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const refetch = useCallback(() => {
    fetch(true);
  }, [fetch]);

  const reset = useCallback(() => {
    setData(initialData as T | undefined);
    setLoading(false);
    setRefreshing(false);
    setError(null);
  }, [initialData]);

  // Initial fetch
  useEffect(() => {
    fetch(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Watch mode: re-fetch when deps change
  useEffect(() => {
    if (watch && deps.length > 0) {
      fetch(true);
    }
  }, [watch, fetch, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    data,
    loading,
    refreshing,
    error,
    refetch,
    reset,
  };
}

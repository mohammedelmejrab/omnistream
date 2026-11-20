import { useCallback, useEffect, useRef, useState } from 'react';
import { NetworkError } from '@/api/client';

export interface Resource<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  /** Re-runs the loader. Previous data stays visible while it runs. */
  reload: () => void;
  /** Replace the data locally (after a mutation) without refetching. */
  setData: (next: T | undefined | ((prev: T | undefined) => T | undefined)) => void;
}

/**
 * Loads data on mount and whenever `deps` change. Aborts stale requests so a
 * slow earlier response can never overwrite a newer one.
 */
export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): Resource<T> {
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    loadRef.current(controller.signal).then(
      (result) => {
        if (controller.signal.aborted) return;
        setDataState(result);
        setError(undefined);
        setLoading(false);
      },
      (err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err : new NetworkError());
        setLoading(false);
      },
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps supplied by caller
  }, [tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((next: T | undefined | ((prev: T | undefined) => T | undefined)) => {
    setDataState((prev) => (typeof next === 'function' ? (next as (p: T | undefined) => T | undefined)(prev) : next));
  }, []);

  return { data, error, loading, reload, setData };
}

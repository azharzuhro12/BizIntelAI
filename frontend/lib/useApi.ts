"use client";

/**
 * Hook fetch per-widget: tiap kartu dashboard memuat endpoint-nya sendiri
 * sehingga kegagalan satu endpoint tidak menjatuhkan sisanya.
 *
 * Refetch menahan render sebelumnya (opacity dikurangi WidgetCard),
 * bukan skeleton - tidak ada layout jump. Loading diputar bersama tick
 * (bukan di dalam efek) sesuai aturan react-hooks/set-state-in-effect.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface UseApiResult<T> {
  data: T | null;
  error: ApiError | null;
  /** True saat fetch berjalan (pertama maupun refetch). */
  loading: boolean;
  /** True hanya sebelum data pertama berhasil tiba. */
  initialLoading: boolean;
  reload: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  // Fetcher terbaru di-update lewat efek (bukan saat render) agar tidak
  // melanggar aturan refs; efek ini dideklarasikan sebelum efek fetch.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    let cancelled = false;
    fetcherRef
      .current()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof ApiError
              ? cause
              : new ApiError("network", "Terjadi kesalahan tak terduga saat memuat data."),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const reload = useCallback(() => {
    setLoading(true);
    setTick((t) => t + 1);
  }, []);

  return { data, error, loading, initialLoading: loading && data === null, reload };
}

/** State render widget turunan dari hasil useApi. */
export type WidgetStatus = "loading" | "error" | "empty" | "ready";

export function toWidgetStatus<T>(
  data: T | null,
  error: ApiError | null,
  isEmpty: (value: T) => boolean,
): WidgetStatus {
  if (error !== null && data === null) return "error";
  if (data === null) return "loading";
  return isEmpty(data) ? "empty" : "ready";
}

"use client";

/**
 * Bingkai kartu widget: judul + subjudul + tubuh dengan state
 * loading/error/empty/ready seragam. Saat refetch (data lama masih ada),
 * tubuh ditahan dengan opacity dikurangi - bukan skeleton.
 */

import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import type { WidgetStatus } from "@/lib/useApi";
import { EmptyState, ErrorState, LoadingState } from "./States";

interface WidgetCardProps {
  title: string;
  subtitle?: string;
  /** Aksi kanan-atas (badge, dsb.) */
  headerExtra?: ReactNode;
  children: ReactNode;
  status: WidgetStatus;
  error?: ApiError | null;
  /** Refetch berjalan sementara data lama masih tampil. */
  refreshing?: boolean;
  onRetry: () => void;
  emptyMessage?: string;
  loadingLabel?: string;
}

export function WidgetCard({
  title,
  subtitle,
  headerExtra,
  children,
  status,
  error = null,
  refreshing = false,
  onRetry,
  emptyMessage,
  loadingLabel,
}: WidgetCardProps) {
  return (
    <section className="rounded-xl border border-hairline bg-card p-4 shadow-sm sm:p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p> : null}
        </div>
        {headerExtra}
      </div>
      {status === "error" ? (
        <ErrorState message={error?.message ?? "Gagal memuat data."} code={error?.code} onRetry={onRetry} />
      ) : status === "loading" ? (
        <LoadingState label={loadingLabel} />
      ) : status === "empty" ? (
        <EmptyState message={emptyMessage} />
      ) : (
        <div className={refreshing ? "opacity-60 transition-opacity" : "transition-opacity"}>
          {children}
        </div>
      )}
    </section>
  );
}

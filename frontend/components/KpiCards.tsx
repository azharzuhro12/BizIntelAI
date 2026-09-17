"use client";

/**
 * Empat kartu KPI independen (menggantikan KpiTiles satu kartu) - tiap
 * metrik punya kartu + ikon kecilnya sendiri sehingga angka tidak lagi
 * bertumpuk. Revenue tetap figur utama (font terbesar). Kartu anomali
 * menghitung hari ber-flag dari /api/analytics/anomalies (label
 * "terdeteksi", bukan tafsiran fraud) - kegagalan endpoint anomali
 * menjatuhkan kartu itu saja, bukan seluruh KPI.
 */

import type { ReactNode } from "react";

import { getAnomalies, getKpi } from "@/lib/api";
import { formatCurrency, formatDateRange, formatNumberRound } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { EmptyState, ErrorState, LoadingState } from "./States";

export function KpiCards() {
  const { data, error, loading, reload } = useApi(getKpi);
  const status = toWidgetStatus(data, error, () => false);

  return (
    <div aria-busy={loading} className="grid gap-4 sm:grid-cols-2">
      {status === "loading" ? (
        <div className="rounded-xl border border-hairline bg-card p-5 shadow-sm sm:col-span-2">
          <LoadingState label="Memuat KPI…" />
        </div>
      ) : status === "error" ? (
        <div className="rounded-xl border border-hairline bg-card p-5 shadow-sm sm:col-span-2">
          <ErrorState message={error?.message ?? "Gagal memuat KPI."} code={error?.code} onRetry={reload} />
        </div>
      ) : !data ? (
        <div className="rounded-xl border border-hairline bg-card p-5 shadow-sm sm:col-span-2">
          <EmptyState />
        </div>
      ) : (
        <div
          className={`grid gap-4 sm:col-span-2 sm:grid-cols-2 ${
            loading ? "opacity-60 transition-opacity" : "transition-opacity"
          }`}
        >
          <KpiCard
            label="Total Revenue"
            value={formatCurrency(data.total_revenue)}
            sub={`Periode data: ${formatDateRange(data.date_range_start, data.date_range_end)}`}
            icon={<IconEuro />}
            iconClass="text-series-1"
            hero
          />
          <KpiCard
            label="Jumlah Transaksi"
            value={formatNumberRound(data.total_transactions)}
            icon={<IconCart />}
          />
          <KpiCard
            label="Rata-rata Nilai Transaksi"
            value={formatCurrency(data.average_transaction_value)}
            icon={<IconTag />}
          />
          <AnomalyCard />
        </div>
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  sub,
  icon,
  iconClass = "text-ink-muted",
  hero = false,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: ReactNode;
  iconClass?: string;
  hero?: boolean;
}) {
  return (
    <section className="flex flex-col rounded-xl border border-hairline bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium tracking-wide text-ink-secondary uppercase">{label}</p>
        <span className={`shrink-0 ${iconClass}`}>{icon}</span>
      </div>
      <p
        className={`mt-3 font-semibold tracking-tight text-ink tabular ${
          hero ? "text-4xl" : "text-2xl"
        }`}
      >
        {value}
      </p>
      {sub ? <p className="mt-1.5 text-xs text-ink-muted">{sub}</p> : null}
    </section>
  );
}

function AnomalyCard() {
  const { data, error, loading, reload } = useApi(getAnomalies);
  const status = toWidgetStatus(data, error, (value) => value.length === 0);

  return (
    <section className="flex flex-col rounded-xl border border-hairline bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium tracking-wide text-ink-secondary uppercase">Anomali</p>
        <span className="shrink-0 text-series-2">
          <IconAlertTriangle />
        </span>
      </div>
      {status === "loading" ? (
        <LoadingState label="Memuat anomali…" />
      ) : status === "error" ? (
        <div className="mt-3">
          <ErrorState message={error?.message ?? "Gagal memuat anomali."} code={error?.code} onRetry={reload} />
        </div>
      ) : !data ? null : (
        <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <p className="mt-3 text-2xl font-semibold tracking-tight text-ink tabular">
            {formatNumberRound(data.length)}
          </p>
          <p className="mt-1.5 text-xs text-ink-muted">
            hari terdeteksi · IsolationForest
          </p>
        </div>
      )}
    </section>
  );
}

/* ---------- Ikon garis (stroke currentColor, dekoratif aria-hidden) ---------- */

function IconEuro() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 10h12" />
      <path d="M4 14h9" />
      <path d="M19 6a7.7 7.7 0 0 0-5.2-2A7.9 7.9 0 0 0 6 12c0 6 4 8 7.8 8a7.7 7.7 0 0 0 5.2-2" />
    </svg>
  );
}

function IconCart() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="8" cy="21" r="1" />
      <circle cx="19" cy="21" r="1" />
      <path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12" />
    </svg>
  );
}

function IconTag() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
      <circle cx="7.5" cy="7.5" r=".5" fill="currentColor" />
    </svg>
  );
}

function IconAlertTriangle() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

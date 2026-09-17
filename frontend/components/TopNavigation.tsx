"use client";

/**
 * Navigasi atas (SaaS BI shell): brand, navigasi kontekstual, dan status
 * sistem. Aplikasi hanya punya SATU route ("/") - item navigasi adalah
 * anchor ke section yang benar-benar ada di halaman, bukan route palsu.
 * "Agent Runs" belum punya UI (kandidat lanjutan) sehingga tampil
 * non-interaktif, bukan sebagai link mati.
 *
 * Status sistem dari GET /api/health (frontend fetch baru; backend tidak
 * berubah) dan periode data dari GET /api/analytics/kpi - tidak ada nilai
 * dinamis yang di-hardcode.
 */

import { getHealth, getKpi } from "@/lib/api";
import { formatDateRange } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const NAV_ITEMS = [
  { label: "Dashboard", href: "#dashboard" },
  { label: "Analytics", href: "#analytics" },
  { label: "Forecast", href: "#forecast" },
] as const;

export function TopNavigation() {
  const health = useApi(getHealth);
  const kpi = useApi(getKpi);

  const healthy =
    health.data !== null && health.data.status === "ok" && health.data.database === "connected";
  const statusLabel = health.initialLoading
    ? "Memeriksa sistem…"
    : healthy
      ? "System Healthy"
      : health.error
        ? "API tidak terjangkau"
        : "Sistem bermasalah";
  const dotClass = health.initialLoading
    ? "bg-ink-muted"
    : healthy
      ? "bg-success"
      : "bg-series-2";

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-card">
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-4 px-4 sm:gap-6 sm:px-6">
        <a href="#dashboard" className="flex shrink-0 items-center gap-2">
          <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
            <rect x="1" y="8" width="3" height="7" rx="1" fill="var(--series-1)" />
            <rect x="6" y="4" width="3" height="11" rx="1" fill="var(--series-1)" />
            <rect x="11" y="1" width="3" height="14" rx="1" fill="var(--series-1)" />
          </svg>
          <span className="text-sm font-semibold tracking-tight text-ink">BizIntel AI</span>
        </a>

        <nav aria-label="Navigasi utama" className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item, index) => (
            <a
              key={item.href}
              href={item.href}
              aria-current={index === 0 ? "page" : undefined}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                index === 0
                  ? "bg-series-1/10 font-medium text-ink"
                  : "text-ink-secondary hover:bg-surface hover:text-ink"
              }`}
            >
              {item.label}
            </a>
          ))}
          {/* Sumber RAG (citation) tampil di panel AI Assistant, yang
              hanya inline di >= lg — di bawah itu targetnya drawer
              off-canvas, jadi item ini tidak ditampilkan. */}
          <a
            href="#assistant-panel"
            title="Sumber RAG tampil di panel AI Assistant"
            className="hidden rounded-md px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-surface hover:text-ink lg:inline-block"
          >
            RAG
          </a>
          <span
            aria-disabled="true"
            title="Riwayat run agent belum ditampilkan di UI"
            className="cursor-not-allowed rounded-md px-3 py-1.5 text-sm text-ink-muted/70"
          >
            Agent Runs
          </span>
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-4">
          {kpi.data ? (
            <p className="hidden whitespace-nowrap text-xs text-ink-muted lg:block">
              Data: {formatDateRange(kpi.data.date_range_start, kpi.data.date_range_end)}
            </p>
          ) : null}
          <p aria-live="polite" className="flex items-center gap-1.5 whitespace-nowrap text-xs text-ink-secondary">
            <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${dotClass}`} />
            {statusLabel}
          </p>
        </div>
      </div>
    </header>
  );
}

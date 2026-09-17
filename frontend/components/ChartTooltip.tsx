"use client";

/**
 * Tooltip Recharts ber-token: nilai memimpin (strong, tabular), nama deret
 * sekunder, kunci deret = stroke pendek warna series (bukan kotak).
 * Semua teks dirender sebagai React children (escapes) - data API tidak
 * pernah lewat innerHTML.
 */

export interface TooltipEntry {
  name?: string | number;
  value?: unknown;
  color?: string;
  stroke?: string;
  payload?: Record<string, unknown>;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
  formatValue: (value: number, entry: TooltipEntry) => string;
}

export function ChartTooltip({ active, payload, label, formatValue }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-hairline bg-surface px-3 py-2 text-xs shadow-sm">
      <p className="mb-1 text-ink-muted">{label}</p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2 py-0.5">
          <span
            aria-hidden
            className="inline-block h-0.5 w-3 shrink-0 rounded"
            style={{ background: entry.stroke ?? entry.color ?? "var(--ink-muted)" }}
          />
          <span className="font-semibold text-ink tabular">
            {formatValue(Number(entry.value), entry)}
          </span>
          <span className="text-ink-secondary">{entry.name}</span>
        </div>
      ))}
    </div>
  );
}

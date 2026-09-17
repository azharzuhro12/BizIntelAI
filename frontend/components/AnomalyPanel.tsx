"use client";

/**
 * Deteksi anomaly harian (IsolationForest): garis revenue semua hari +
 * marker oranye khusus hari anomaly (identitas berbeda = hue berbeda,
 * ring surface 2px). Dua deret -> legend hadir.
 */

import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getAnomalies, getDailyRevenue } from "@/lib/api";
import { buildAnomalyRows, filterAnomalyDays } from "@/lib/chartData";
import { formatAxisCurrency, formatCurrency, formatDate, formatNumberRound } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { ChartTooltip } from "./ChartTooltip";
import { DataTable } from "./DataTable";
import { WidgetCard } from "./WidgetCard";

export function AnomalyPanel() {
  // Garis lengkap semua hari dari /revenue; hari ber-flag dari /anomalies
  // (endpoint tersebut hanya mengembalikan hari anomaly - WHERE is_anomaly).
  const history = useApi(getDailyRevenue);
  const anomalies = useApi(getAnomalies);

  const status = toWidgetStatus(history.data, history.error, (rows) => rows.length === 0);
  const rows =
    history.data && anomalies.data ? buildAnomalyRows(history.data, anomalies.data) : null;
  const anomalyDays = anomalies.data ? filterAnomalyDays(anomalies.data) : [];
  const anomalyRows = rows ? rows.filter((row) => row.isAnomaly) : [];

  return (
    <WidgetCard
      title="Deteksi anomaly harian"
      subtitle={
        anomalies.data
          ? `${anomalyDays.length} hari anomaly terdeteksi (IsolationForest)`
          : "IsolationForest pada daily_metrics"
      }
      status={status}
      error={history.error}
      refreshing={history.loading || anomalies.loading}
      onRetry={history.reload}
      emptyMessage="Tidak ada data revenue harian."
    >
      {rows ? (
        <>
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "var(--ink-secondary)", fontSize: 12 }}
                  axisLine={{ stroke: "var(--grid)" }}
                  tickLine={false}
                  minTickGap={24}
                />
                <YAxis
                  tickFormatter={(value: number) => formatAxisCurrency(value)}
                  tick={{ fill: "var(--ink-secondary)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={64}
                />
                <Tooltip
                  cursor={{ stroke: "var(--grid)" }}
                  content={({ active, payload, label }) => (
                    <ChartTooltip
                      active={active}
                      payload={payload}
                      label={label}
                      formatValue={(value) => formatCurrency(value)}
                    />
                  )}
                />
                <Legend formatter={(value) => <span className="text-xs text-ink-secondary">{value}</span>} />
                <Line
                  name="Revenue harian"
                  dataKey="revenue"
                  type="linear"
                  stroke="var(--series-1)"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5 }}
                />
                <Scatter
                  name="Hari anomaly"
                  data={anomalyRows}
                  dataKey="revenue"
                  fill="var(--series-2)"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {anomalies.error ? (
            <p className="mt-2 text-xs text-ink-muted">
              Data hari anomaly belum termuat
              {anomalies.error.code ? ` (kode: ${anomalies.error.code})` : ""}.{" "}
              <button
                type="button"
                onClick={anomalies.reload}
                className="underline hover:text-ink-secondary"
              >
                Muat ulang
              </button>
            </p>
          ) : null}
          {anomalyRows.length === 0 && !anomalies.error ? (
            <p className="mt-2 text-xs text-ink-muted">Tidak ada hari yang ditandai anomaly.</p>
          ) : (
            <DataTable
              caption="Hari anomaly terdeteksi model"
              rows={anomalyDays}
              columns={[
                { header: "Tanggal", cell: (row) => formatDate(row.date) },
                { header: "Revenue", numeric: true, cell: (row) => formatCurrency(row.revenue) },
                {
                  header: "Item terjual",
                  numeric: true,
                  cell: (row) => formatNumberRound(row.quantity),
                },
                {
                  header: "Transaksi",
                  numeric: true,
                  cell: (row) => formatNumberRound(row.transactions),
                },
              ]}
            />
          )}
        </>
      ) : null}
    </WidgetCard>
  );
}

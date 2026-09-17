"use client";

/**
 * Tren revenue harian (30 hari terakhir) + prediksi model N hari ke depan.
 * Satu entitas (revenue) = satu hue: aktual solid series-1, prediksi dashed
 * shade senada + badge "Model predictions". Prediksi TIDAK di-clamp -
 * nilai negatif (limitasi ekstrapolasi antar-bulan) tampil apa adanya.
 */

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getDailyRevenue, getRevenueForecast } from "@/lib/api";
import { buildRevenueForecastRows } from "@/lib/chartData";
import { formatCurrency, formatDate, formatAxisCurrency } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { ChartTooltip } from "./ChartTooltip";
import { DataTable } from "./DataTable";
import { WidgetCard } from "./WidgetCard";

export function RevenueForecastChart() {
  const history = useApi(getDailyRevenue);
  const forecast = useApi(() => getRevenueForecast(7));

  const status = toWidgetStatus(history.data, history.error, (rows) => rows.length === 0);
  const rows =
    history.data && forecast.data ? buildRevenueForecastRows(history.data, forecast.data, 30) : null;
  const hasNegativePrediction = (forecast.data?.predictions ?? []).some((p) => p.predicted_revenue < 0);

  return (
    <WidgetCard
      title="Tren revenue harian & prediksi"
      subtitle="30 hari terakhir + 7 hari prediksi model"
      headerExtra={
        forecast.data ? (
          <span className="rounded-full border border-hairline px-2.5 py-0.5 text-[11px] text-ink-secondary">
            Model predictions · {forecast.data.model}
          </span>
        ) : null
      }
      status={status}
      error={history.error}
      refreshing={history.loading || forecast.loading}
      onRetry={history.reload}
      emptyMessage="Tidak ada data revenue harian."
    >
      {rows ? (
        <>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                  width={80}
                  domain={([dataMin, dataMax]: readonly [number, number]) => [Math.min(0, dataMin), dataMax]}
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
                <Legend
                  iconType="plainline"
                  formatter={(value) => <span className="text-xs text-ink-secondary">{value}</span>}
                />
                <Line
                  name="Revenue aktual"
                  dataKey="actual"
                  type="linear"
                  stroke="var(--series-1)"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
                <Line
                  name="Prediksi model"
                  dataKey="predicted"
                  type="linear"
                  stroke="var(--forecast)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                  activeDot={{ r: 5 }}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {hasNegativePrediction ? (
            <p className="mt-2 text-xs text-ink-muted">
              Catatan model: prediksi bernilai negatif adalah limitasi ekstrapolasi di luar rentang
              data latih dan sengaja tidak diubah.
            </p>
          ) : null}
          {forecast.error ? (
            <p className="mt-2 text-xs text-ink-muted">
              Prediksi belum tersedia
              {forecast.error.code ? ` (kode: ${forecast.error.code})` : ""} — grafik menampilkan
              revenue aktual saja.{" "}
              <button type="button" onClick={forecast.reload} className="underline hover:text-ink-secondary">
                Muat ulang prediksi
              </button>
            </p>
          ) : null}
          <DataTable
            caption="Revenue harian aktual dan prediksi model"
            rows={rows}
            columns={[
              { header: "Tanggal", cell: (row) => formatDate(row.date) },
              {
                header: "Revenue aktual",
                numeric: true,
                cell: (row) => (row.actual === null ? "—" : formatCurrency(row.actual)),
              },
              {
                header: "Prediksi model",
                numeric: true,
                cell: (row) => (row.predicted === null ? "—" : formatCurrency(row.predicted)),
              },
            ]}
          />
        </>
      ) : null}
    </WidgetCard>
  );
}

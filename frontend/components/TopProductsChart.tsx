"use client";

/**
 * Produk dengan revenue teratas: bar horizontal satu hue (satu deret =
 * satu warna slot 1; panjang bar sudah membawa magnitude). Ujung data
 * membulat 4px, pangkal kotak, ketebalan dikap 16px.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getTopProducts } from "@/lib/api";
import { takeTop } from "@/lib/chartData";
import { formatAxisCurrency, formatCurrency, formatNumberRound } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { ChartTooltip } from "./ChartTooltip";
import { DataTable } from "./DataTable";
import { WidgetCard } from "./WidgetCard";

export function TopProductsChart() {
  const { data, error, loading, reload } = useApi(getTopProducts);
  const status = toWidgetStatus(data, error, (rows) => rows.length === 0);
  const rows = data ? takeTop(data, 10) : null;

  return (
    <WidgetCard
      title="Produk dengan revenue teratas"
      subtitle="10 teratas periode berjalan"
      status={status}
      error={error}
      refreshing={loading}
      onRetry={reload}
      emptyMessage="Tidak ada data produk."
    >
      {rows ? (
        <>
          <div className="h-[320px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid horizontal={false} stroke="var(--grid)" />
                <XAxis
                  type="number"
                  tickFormatter={(value: number) => formatAxisCurrency(value)}
                  tick={{ fill: "var(--ink-secondary)", fontSize: 12 }}
                  axisLine={{ stroke: "var(--grid)" }}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="product"
                  width={120}
                  tick={{ fill: "var(--ink-secondary)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "var(--wash)" }}
                  content={({ active, payload, label }) => (
                    <ChartTooltip
                      active={active}
                      payload={payload}
                      label={label}
                      formatValue={(value) => formatCurrency(value)}
                    />
                  )}
                />
                <Bar
                  name="Revenue"
                  dataKey="revenue"
                  fill="var(--series-1)"
                  barSize={16}
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <DataTable
            caption="Revenue per produk, terurut menurun"
            rows={rows}
            columns={[
              { header: "Produk", cell: (row) => row.product },
              { header: "Revenue", numeric: true, cell: (row) => formatCurrency(row.revenue) },
              { header: "Item terjual", numeric: true, cell: (row) => formatNumberRound(row.quantity) },
            ]}
          />
        </>
      ) : null}
    </WidgetCard>
  );
}

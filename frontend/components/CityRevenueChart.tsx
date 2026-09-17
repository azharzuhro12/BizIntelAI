"use client";

/** Revenue per kota: kolom vertikal satu hue, kategori nominal (bukan ramp). */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getCityRevenue } from "@/lib/api";
import { formatAxisCurrency, formatCurrency, formatNumberRound } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { ChartTooltip } from "./ChartTooltip";
import { DataTable } from "./DataTable";
import { WidgetCard } from "./WidgetCard";

export function CityRevenueChart() {
  const { data, error, loading, reload } = useApi(getCityRevenue);
  const status = toWidgetStatus(data, error, (rows) => rows.length === 0);

  return (
    <WidgetCard
      title="Revenue per kota"
      status={status}
      error={error}
      refreshing={loading}
      onRetry={reload}
      emptyMessage="Tidak ada data kota."
    >
      {data ? (
        <>
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis
                  dataKey="city"
                  tick={{ fill: "var(--ink-secondary)", fontSize: 12 }}
                  axisLine={{ stroke: "var(--grid)" }}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(value: number) => formatAxisCurrency(value)}
                  tick={{ fill: "var(--ink-secondary)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={64}
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
                  barSize={24}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <DataTable
            caption="Revenue per kota"
            rows={data}
            columns={[
              { header: "Kota", cell: (row) => row.city },
              { header: "Revenue", numeric: true, cell: (row) => formatCurrency(row.revenue) },
              { header: "Item terjual", numeric: true, cell: (row) => formatNumberRound(row.quantity) },
            ]}
          />
        </>
      ) : null}
    </WidgetCard>
  );
}

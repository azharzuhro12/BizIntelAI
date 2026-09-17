"use client";

/** Agregat bulanan (v_monthly_metrics): kolom per bulan, satu hue. */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getMonthlyRevenue } from "@/lib/api";
import { formatAxisCurrency, formatCurrency, formatMonth, formatNumberRound } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { ChartTooltip } from "./ChartTooltip";
import { DataTable } from "./DataTable";
import { WidgetCard } from "./WidgetCard";

export function MonthlyRevenueChart() {
  const { data, error, loading, reload } = useApi(getMonthlyRevenue);
  const status = toWidgetStatus(data, error, (rows) => rows.length === 0);
  const rows = data
    ? data.map((row) => ({ ...row, label: formatMonth(row.month) }))
    : null;

  return (
    <WidgetCard
      title="Revenue bulanan"
      status={status}
      error={error}
      refreshing={loading}
      onRetry={reload}
      emptyMessage="Tidak ada data bulanan."
    >
      {rows ? (
        <>
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis
                  dataKey="label"
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
            caption="Revenue per bulan"
            rows={rows}
            columns={[
              { header: "Bulan", cell: (row) => formatMonth(row.month) },
              { header: "Revenue", numeric: true, cell: (row) => formatCurrency(row.revenue) },
              { header: "Item terjual", numeric: true, cell: (row) => formatNumberRound(row.quantity) },
              {
                header: "Transaksi",
                numeric: true,
                cell: (row) => formatNumberRound(row.transactions),
              },
            ]}
          />
        </>
      ) : null}
    </WidgetCard>
  );
}

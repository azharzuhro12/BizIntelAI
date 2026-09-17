/** Test pemetaan data -> chart (pure; chart internals tidak diuji di jsdom). */

import { describe, expect, it } from "vitest";

import {
  buildAnomalyRows,
  buildRevenueForecastRows,
  filterAnomalyDays,
  takeTop,
} from "@/lib/chartData";
import type { AnomalyDay, DailyRevenuePoint, ForecastResponse } from "@/lib/types";

function day(date: string, revenue: number): DailyRevenuePoint {
  return { date, revenue, quantity: 10, transactions: 2 };
}

const history: DailyRevenuePoint[] = [
  day("2022-12-21", 4000),
  day("2022-12-22", 4100),
  day("2022-12-23", 4200),
  day("2022-12-24", 4300),
];

const forecast: ForecastResponse = {
  model: "LinearRegression",
  features: ["day", "revenue_lag1"],
  last_history_date: "2022-12-24",
  days: 3,
  predictions: [
    { date: "2022-12-25", predicted_revenue: 4400 },
    { date: "2022-12-26", predicted_revenue: 4500 },
    { date: "2022-12-27", predicted_revenue: -9007.63 },
  ],
};

describe("buildRevenueForecastRows", () => {
  it("gabung history + prediksi; prediksi mulai dari titik jangkar history", () => {
    const rows = buildRevenueForecastRows(history, forecast);
    expect(rows).toHaveLength(7);
    const anchor = rows.find((row) => row.date === "2022-12-24");
    expect(anchor?.actual).toBe(4300);
    expect(anchor?.predicted).toBe(4300); // jangkar: dashed menyambung dari aktual
    const last = rows[rows.length - 1];
    expect(last.date).toBe("2022-12-27");
    expect(last.actual).toBeNull();
    expect(last.predicted).toBe(-9007.63);
  });

  it("prediksi negatif TIDAK di-clamp (limitasi model tampil apa adanya)", () => {
    const rows = buildRevenueForecastRows(history, forecast);
    expect(rows.some((row) => (row.predicted ?? 0) < 0)).toBe(true);
  });

  it("hanya N hari history terakhir yang dipakai", () => {
    const long = Array.from({ length: 40 }, (_, i) => day(`2022-11-${(i % 28) + 1}`, 1000 + i));
    const rows = buildRevenueForecastRows(long, { ...forecast, last_history_date: "2022-11-28" }, 30);
    const historyOnly = rows.filter((row) => row.actual !== null);
    expect(historyOnly.length).toBeLessThanOrEqual(30);
  });

  it("label pendek Indonesia untuk tiap baris", () => {
    const rows = buildRevenueForecastRows(history, forecast);
    expect(rows[0].label).toMatch(/Nov|Des/);
  });
});

describe("filterAnomalyDays & buildAnomalyRows", () => {
  // Kontrak endpoint: /anomalies hanya mengembalikan hari ber-flag.
  const anomalyDays: AnomalyDay[] = [
    { date: "2022-12-02", revenue: 100, quantity: 1, transactions: 1, anomaly_score_label: -1, is_anomaly: true },
    { date: "2022-12-03", revenue: 300, quantity: 3, transactions: 2, anomaly_score_label: -1, is_anomaly: true },
  ];
  const history: DailyRevenuePoint[] = [
    day("2022-12-03", 300),
    day("2022-12-01", 200),
    day("2022-12-02", 100),
    day("2022-12-04", 400),
  ];

  it("filterAnomalyDays menjaga hanya is_anomaly=true terurut tanggal", () => {
    const mixed: AnomalyDay[] = [
      { date: "2022-12-02", revenue: 100, quantity: 1, transactions: 1, anomaly_score_label: -1, is_anomaly: true },
      { date: "2022-12-01", revenue: 200, quantity: 2, transactions: 1, anomaly_score_label: 1, is_anomaly: false },
      { date: "2022-12-03", revenue: 300, quantity: 3, transactions: 2, anomaly_score_label: -1, is_anomaly: true },
    ];
    expect(filterAnomalyDays(mixed).map((d) => d.date)).toEqual(["2022-12-02", "2022-12-03"]);
  });

  it("gabung semua hari (dari /revenue) + penanda hari anomaly, urut tanggal", () => {
    const rows = buildAnomalyRows(history, anomalyDays);
    expect(rows.map((r) => r.date)).toEqual([
      "2022-12-01",
      "2022-12-02",
      "2022-12-03",
      "2022-12-04",
    ]);
    expect(rows.map((r) => r.isAnomaly)).toEqual([false, true, true, false]);
    expect(rows[1].revenue).toBe(100);
  });

  it("tanggal anomaly di luar history tidak menambah baris", () => {
    const extra: AnomalyDay[] = [
      ...anomalyDays,
      { date: "2022-12-09", revenue: 999, quantity: 1, transactions: 1, anomaly_score_label: -1, is_anomaly: true },
    ];
    expect(buildAnomalyRows(history, extra)).toHaveLength(4);
  });
});

describe("takeTop", () => {
  it("potong daftar ke N pertama tanpa mengubah urutan", () => {
    expect(takeTop([9, 8, 7, 6, 5], 3)).toEqual([9, 8, 7]);
    expect(takeTop([1, 2], 5)).toEqual([1, 2]);
  });
});

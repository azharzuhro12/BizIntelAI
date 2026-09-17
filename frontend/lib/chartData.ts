/**
 * Pemetaan data API -> bentuk siap-render chart (pure, unit-testable).
 * Dipisah dari komponen karena ResponsiveContainer berukuran 0x0 di jsdom -
 * chart diuji lewat fungsi ini, komponen diuji lewat state-nya.
 */

import type { AnomalyDay, DailyRevenuePoint, ForecastResponse } from "./types";

/** Satu baris chart revenue harian + forecast. */
export interface RevenueForecastRow {
  /** ISO YYYY-MM-DD (kunci sumbu X) */
  date: string;
  /** Label pendek untuk tick: "7 Nov" */
  label: string;
  /** Revenue aktual (null pada hari prediksi). */
  actual: number | null;
  /** Prediksi model (null pada hari aktual murni). Pada titik jangkar
   *  (hari terakhir history) nilainya = actual agar segmen dashed menyambung. */
  predicted: number | null;
}

function shortDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
  });
}

/**
 * Gabungkan history harian (N hari terakhir) + prediksi forecast menjadi
 * satu deret untuk line chart: aktual solid, prediksi dashed shade senada.
 * Prediksi TIDAK di-clamp - nilai negatif (limitasi ekstrapolasi bulan)
 * dibiarkan tampil apa adanya.
 */
export function buildRevenueForecastRows(
  history: DailyRevenuePoint[],
  forecast: ForecastResponse,
  historyDays = 30,
): RevenueForecastRow[] {
  const trimmed = history.slice(-historyDays);
  const rows: RevenueForecastRow[] = trimmed.map((point) => ({
    date: point.date,
    label: shortDate(point.date),
    actual: point.revenue,
    predicted: null,
  }));

  // Titik jangkar: hari history terakhir mendapat nilai predicted = aktual
  // di tanggal tersebut agar garis dashed mulai tepat dari ujung history.
  const anchorIndex = forecast.last_history_date
    ? rows.findIndex((row) => row.date.slice(0, 10) === forecast.last_history_date.slice(0, 10))
    : rows.length - 1;
  const anchor = anchorIndex >= 0 ? anchorIndex : rows.length - 1;
  if (rows[anchor]) {
    rows[anchor] = { ...rows[anchor], predicted: rows[anchor].actual };
  }

  for (const point of forecast.predictions) {
    const date = point.date.slice(0, 10);
    const existing = rows.findIndex((row) => row.date.slice(0, 10) === date);
    const cell = { date, label: shortDate(date), actual: null, predicted: point.predicted_revenue };
    if (existing >= 0) {
      rows[existing] = { ...rows[existing], predicted: point.predicted_revenue };
    } else {
      rows.push(cell);
    }
  }
  return rows;
}

/** Hari anomaly saja (is_anomaly=true), urut tanggal (endpoint sudah
 *  terfilter WHERE is_anomaly; filter ini menjaga kontrak bila berubah). */
export function filterAnomalyDays(days: AnomalyDay[]): AnomalyDay[] {
  return days.filter((day) => day.is_anomaly).sort((a, b) => a.date.localeCompare(b.date));
}

/** Deret revenue untuk chart anomaly: garis semua hari + penanda hari anomaly.
 *  Endpoint /anomalies hanya mengembalikan hari ber-flag, jadi garis lengkap
 *  datang dari /revenue dan tanggal anomaly dicocokkan per tanggal. */
export interface AnomalyChartRow {
  date: string;
  label: string;
  revenue: number;
  isAnomaly: boolean;
}

export function buildAnomalyRows(history: DailyRevenuePoint[], anomalies: AnomalyDay[]): AnomalyChartRow[] {
  const anomalyDates = new Set(anomalies.map((day) => day.date.slice(0, 10)));
  return [...history]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((point) => ({
      date: point.date,
      label: shortDate(point.date),
      revenue: point.revenue,
      isAnomaly: anomalyDates.has(point.date.slice(0, 10)),
    }));
}

/** Top-N produk untuk bar chart horizontal (input sudah sorted desc). */
export function takeTop<T>(rows: T[], n: number): T[] {
  return rows.slice(0, n);
}

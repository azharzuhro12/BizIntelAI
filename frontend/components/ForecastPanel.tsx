"use client";

/**
 * Section prediksi komplementer: BUKAN chart kedua (gabungan aktual +
 * prediksi sudah ada di kartu utama RevenueForecastChart) — daftar nilai
 * per hari + total horison dari /api/forecast/revenue?days=7. Prediksi
 * negatif ditampilkan apa adanya (limitasi ekstrapolasi bulan, tidak
 * di-clamp) dan ditandai warna anomaly agar mudah dibaca.
 */

import { getRevenueForecast } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { toWidgetStatus, useApi } from "@/lib/useApi";
import { WidgetCard } from "./WidgetCard";

export function ForecastPanel() {
  const { data, error, loading, reload } = useApi(() => getRevenueForecast(7));
  const status = toWidgetStatus(data, error, (value) => value.predictions.length === 0);

  return (
    <WidgetCard
      title="Prediksi Revenue 7 Hari ke Depan"
      subtitle={data ? `Model ${data.model} · horison 7 hari` : "Prediksi model machine learning"}
      status={status}
      error={error}
      refreshing={loading}
      onRetry={reload}
      loadingLabel="Memuat prediksi…"
      emptyMessage="Tidak ada prediksi untuk ditampilkan."
    >
      {data ? (
        <div>
          <ul className="divide-y divide-hairline/70">
            {data.predictions.map((point) => (
              <li key={point.date} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="text-ink-secondary">{formatDate(point.date)}</span>
                <span
                  className={`font-medium tabular ${
                    point.predicted_revenue < 0 ? "text-series-2" : "text-ink"
                  }`}
                >
                  {formatCurrency(point.predicted_revenue)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 flex items-center justify-between gap-3 border-t border-hairline pt-3 text-sm">
            <span className="text-ink-secondary">Total 7 hari</span>
            <span className="font-semibold tabular text-ink">
              {formatCurrency(data.predictions.reduce((sum, p) => sum + p.predicted_revenue, 0))}
            </span>
          </p>
          <p className="mt-3 text-xs text-ink-muted">
            Catatan model: prediksi bernilai negatif adalah limitasi ekstrapolasi di luar
            rentang data pelatihan — ditampilkan apa adanya, tidak di-clamp.
          </p>
        </div>
      ) : null}
    </WidgetCard>
  );
}

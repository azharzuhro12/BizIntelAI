"""Service forecasting revenue - memuat artefak model yang SUDAH ADA.

Prinsip:
  - TIDAK ada retraining di dalam API.
  - Artefak dimuat sekali (cache) lalu divalidasi kompatibilitasnya
    terhadap konfigurasi fitur (forecast_features.joblib).
  - Jika artefak tidak kompatibel, error yang PERSIS dilempar -
    tanpa workaround yang tidak valid.

Feature engineering mengikuti notebook cell 30 (jangan menebak):
  day_of_week     = pandas .dt.dayofweek (Senin=0 .. Minggu=6)
  day_of_month    = .dt.day
  month           = .dt.month
  is_weekend      = 1 jika day_of_week >= 5
  lag_1           = revenue hari sebelumnya (shift 1)
  lag_7           = revenue 7 hari sebelumnya (shift 7)
  rolling_mean_7  = rata-rata revenue 7 hari SEBELUM hari-H
                    ( Revenue.shift(1).rolling(7).mean() )
"""

import warnings
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from ..db import get_connection  # noqa: F401  (dipakai caller router)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "backend" / "models"
MODEL_PATH = MODELS_DIR / "revenue_forecasting_linear_regression.joblib"
FEATURES_PATH = MODELS_DIR / "forecast_features.joblib"

MODEL_NAME = "revenue_forecasting_linear_regression"


class ForecastModelUnavailableError(RuntimeError):
    """Artefak tidak dapat dipakai untuk forecasting revenue dengan aman."""


@lru_cache(maxsize=1)
def load_forecast_model():
    """Muat artefak + daftar fitur, lalu validasi kompatibilitas.

    Return (model, features). Raise ForecastModelUnavailableError jika
    fitur artefak != forecast_features.joblib.
    """
    if not MODEL_PATH.exists():
        raise ForecastModelUnavailableError(
            "File artefak model tidak ditemukan: "
            "backend/models/revenue_forecasting_linear_regression.joblib"
        )
    if not FEATURES_PATH.exists():
        raise ForecastModelUnavailableError(
            "File konfigurasi fitur tidak ditemukan: "
            "backend/models/forecast_features.joblib"
        )

    # Artefak dibuat dengan sklearn 1.6.1; warning versi bila host berbeda
    # sudah diverifikasi tidak memengaruhi predict().
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = joblib.load(MODEL_PATH)
        features = list(joblib.load(FEATURES_PATH))

    expected = [str(f) for f in getattr(model, "feature_names_in_", [])]
    if expected != features:
        raise ForecastModelUnavailableError(
            "Artefak 'revenue_forecasting_linear_regression.joblib' TIDAK "
            "kompatibel dengan forecast_features.joblib. "
            f"Model mengharapkan {len(expected)} fitur: {expected}. "
            f"Konfigurasi fitur forecasting berisi {len(features)} fitur: "
            f"{features}. Artefak ini adalah model prediksi Quantity dari "
            "section 'Predictive Models' notebook (fitur one-hot transaksi: "
            "Price, Revenue, Product_*, City_*, dll.), BUKAN model time-series "
            "revenue forecasting (7 fitur lag/kalender) yang dilatih di cell 32. "
            "Model time-series yang benar tidak pernah di-export oleh notebook "
            "(cell 66 menyimpan variabel 'linear_model' yang salah)."
        )

    return model, features


def forecast_revenue(days: int) -> dict:
    """Prediksi revenue N hari ke depan setelah data terakhir di daily_metrics.

    Recursive forecasting: prediksi hari ke-t dipakai sebagai lag untuk
    hari ke-t+1. Riwayat dibaca dari PostgreSQL (daily_metrics).
    """
    model, features = load_forecast_model()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT metric_date, revenue FROM daily_metrics "
                "ORDER BY metric_date"
            )
            history = cur.fetchall()

    if len(history) < 8:
        raise ForecastModelUnavailableError(
            f"Riwayat daily_metrics tidak cukup untuk fitur lag/rolling "
            f"(butuh >= 8 hari, tersedia {len(history)} hari)."
        )

    # Series riwayat: index = date, value = revenue (float)
    series = {d: float(r) for d, r in history}
    last_date = max(series)

    predictions: list[dict] = []
    for step in range(1, days + 1):
        target = last_date + timedelta(days=step)

        # 7 hari SEBELUM target (d-7 .. d-1), sesuai shift(1).rolling(7)
        window = [series.get(target - timedelta(days=k)) for k in range(1, 8)]
        if any(v is None for v in window):
            raise ForecastModelUnavailableError(
                "Celah tanggal pada riwayat daily_metrics - fitur rolling "
                "tidak dapat dibangun."
            )

        feature_row = {
            "day_of_week": target.weekday(),  # Senin=0, sama dengan pandas
            "day_of_month": target.day,
            "month": target.month,
            "is_weekend": int(target.weekday() >= 5),
            "lag_1": window[0],
            "lag_7": window[6],
            "rolling_mean_7": sum(window) / 7.0,
        }
        X = pd.DataFrame([[feature_row[f] for f in features]], columns=features)
        predicted = float(model.predict(X)[0])

        predictions.append(
            {"date": target, "predicted_revenue": round(predicted, 2)}
        )
        # gunakan prediksi sebagai riwayat utk langkah berikutnya
        series[target] = predicted

    return {
        "model": MODEL_NAME,
        "features": features,
        "last_history_date": last_date,
        "days": days,
        "predictions": predictions,
    }

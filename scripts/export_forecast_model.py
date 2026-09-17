#!/usr/bin/env python3
"""
BizIntel AI - Export ULANG model revenue forecasting time-series yang benar.

Latar belakang:
  Notebook cell 66 keliru menyimpan variabel 'linear_model' (prediktor Quantity
  18 fitur one-hot dari section Predictive Models) padahal comment cell
  tersebut berupa 'Simpan model forecasting terbaik'. Model yang benar-benar
  menghasilkan revenue_model_metrics.csv dan revenue_test_predictions.csv
  adalah best_revenue_model = revenue_models["Linear Regression"] (cell 32-34).

Script ini mereplikasi training pipeline notebook SECARA EXACT (tanpa mengubah
logic sedikit pun), lalu memverifikasi hasil terhadap CSV output notebook
yang sudah tervalidasi SEBELUM artefak lama disentuh:

  Replikasi (notebook cell 26, 30, 31, 32):
    daily_sales (dari data/processed/daily_sales.csv, nilai float64 identik
    karena CSV round-trip) -> fitur time-series -> dropna -> split 80/20
    kronologis -> LinearRegression fit pada target Revenue.

  Verifikasi wajib (semua harus PASS sebelum swap artefak):
    V1 fitur X_test identik dengan revenue_test_predictions.csv
    V2 predict(X_test) == kolom Predicted_Revenue CSV (toleransi 1e-6)
    V3 metrik MAE/RMSE/MAPE == baris 'Linear Regression' revenue_model_metrics.csv
    V4 7 fitur == forecast_features.joblib
    V5 bukan model Quantity (bukan 18 fitur one-hot)

Pemakaian:  python3 scripts/export_forecast_model.py
"""

import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[1]
DAILY_CSV = ROOT / "data" / "processed" / "daily_sales.csv"
TEST_PRED_CSV = ROOT / "data" / "ml_outputs" / "revenue_test_predictions.csv"
METRICS_CSV = ROOT / "data" / "ml_outputs" / "revenue_model_metrics.csv"
FEATURES_JOBLIB = ROOT / "backend" / "models" / "forecast_features.joblib"
OLD_ARTIFACT = ROOT / "backend" / "models" / "revenue_forecasting_linear_regression.joblib"
NEW_TMP = ROOT / "backend" / "models" / ".revenue_forecasting_linear_regression.new"
OLD_RENAMED = ROOT / "backend" / "models" / "quantity_prediction_linear_regression.joblib"
NOTEBOOK = ROOT / "notebooks" / "exploratory-data-analysis-and-predictive-models.ipynb"

TOL = 1e-6


def fail(msg: str) -> None:
    print(f"\n[VERIFIKASI GAGAL] {msg}")
    print("STOP - artefak lama TIDAK diganti.")
    sys.exit(1)


def build_model():
    """Replikasi exact notebook cell 26 -> 30 -> 31 -> 32."""
    # cell 26: daily_sales (CSV = export float64 round-trip dari notebook)
    daily_sales = pd.read_csv(DAILY_CSV, parse_dates=["Date"])
    daily_sales = daily_sales.sort_values("Date").reset_index(drop=True)

    # cell 30: time-series features
    forecast_df = daily_sales.copy()
    forecast_df["day_of_week"] = forecast_df["Date"].dt.dayofweek
    forecast_df["day_of_month"] = forecast_df["Date"].dt.day
    forecast_df["month"] = forecast_df["Date"].dt.month
    forecast_df["is_weekend"] = (forecast_df["day_of_week"] >= 5).astype(int)
    forecast_df["lag_1"] = forecast_df["Revenue"].shift(1)
    forecast_df["lag_7"] = forecast_df["Revenue"].shift(7)
    forecast_df["rolling_mean_7"] = (
        forecast_df["Revenue"].shift(1).rolling(7).mean()
    )
    feature_cols = [
        "day_of_week", "day_of_month", "month", "is_weekend",
        "lag_1", "lag_7", "rolling_mean_7",
    ]
    model_data = (
        forecast_df[feature_cols + ["Revenue"]].dropna().reset_index(drop=True)
    )

    # cell 31: split kronologis 80/20
    split_idx = int(len(model_data) * 0.80)
    split_idx = max(1, min(split_idx, len(model_data) - 1))
    X = model_data[feature_cols]
    y = model_data["Revenue"]
    X_train, X_test = X.iloc[:split_idx].copy(), X.iloc[split_idx:].copy()
    y_train, y_test = y.iloc[:split_idx].copy(), y.iloc[split_idx:].copy()

    # cell 32: LinearRegression (inilah revenue_models["Linear Regression"])
    lr = LinearRegression()
    lr.fit(X_train, y_train)
    return lr, feature_cols, X_test, y_test, model_data


def verify(lr, feature_cols, X_test, y_test) -> None:
    tp = pd.read_csv(TEST_PRED_CSV)
    metrics = pd.read_csv(METRICS_CSV)
    lr_metrics = metrics[metrics["Model"] == "Linear Regression"].iloc[0]
    features_joblib = list(joblib.load(FEATURES_JOBLIB))

    print(f"Jumlah observasi test notebook : {len(tp)}")
    print(f"Jumlah observasi test replika  : {len(X_test)}")

    # V1: fitur test identik
    if len(tp) != len(X_test):
        fail(f"jumlah baris test beda: {len(tp)} vs {len(X_test)}")
    max_feat_diff = max(
        float(np.abs(tp[c].to_numpy() - X_test[c].to_numpy()).max())
        for c in feature_cols
    )
    print(f"V1 max selisih fitur X_test vs CSV : {max_feat_diff:.3e}")
    if max_feat_diff > TOL:
        fail("fitur X_test tidak identik dengan revenue_test_predictions.csv")

    # V2: prediksi identik dengan output notebook
    pred = lr.predict(X_test)
    diff = np.abs(pred - tp["Predicted_Revenue"].to_numpy())
    print(f"V2 max |pred - Predicted_Revenue|  : {diff.max():.3e}")
    if diff.max() > TOL:
        fail("prediksi tidak cocok dengan revenue_test_predictions.csv")

    # V3: metrik identik
    actual = y_test.to_numpy()
    mae = np.mean(np.abs(actual - pred))
    rmse = np.sqrt(np.mean((actual - pred) ** 2))
    mape = np.mean(np.abs((actual - pred) / actual)) * 100
    print(
        f"V3 MAE  {mae:.10f} vs {lr_metrics['MAE']:.10f} "
        f"(selisih {abs(mae - lr_metrics['MAE']):.3e})"
    )
    print(
        f"V3 RMSE {rmse:.10f} vs {lr_metrics['RMSE']:.10f} "
        f"(selisih {abs(rmse - lr_metrics['RMSE']):.3e})"
    )
    print(
        f"V3 MAPE {mape:.10f} vs {lr_metrics['MAPE (%)']:.10f} "
        f"(selisih {abs(mape - lr_metrics['MAPE (%)']):.3e})"
    )
    if max(
        abs(mae - lr_metrics["MAE"]),
        abs(rmse - lr_metrics["RMSE"]),
        abs(mape - lr_metrics["MAPE (%)"]),
    ) > 1e-6:
        fail("metrik tidak cocok dengan revenue_model_metrics.csv")

    # V4: fitur == forecast_features.joblib
    print(f"V4 fitur model  : {feature_cols}")
    print(f"V4 joblib fitur : {features_joblib}")
    if feature_cols != features_joblib:
        fail("urutan/nama fitur tidak sama dengan forecast_features.joblib")

    # V5: bukan model Quantity (18 fitur one-hot)
    n = lr.n_features_in_
    print(f"V5 n_features_in_ = {n} (model Quantity punya 18)")
    if n != 7:
        fail("model bukan model 7-fitur revenue forecasting")

    print("\n>>> SEMUA VERIFIKASI IN-MEMORY PASS")


def verify_artifact_file(path: Path) -> None:
    """Muat ulang artefak dari file dan verifikasi ulang (V2/V4/V5)."""
    m = joblib.load(path)
    tp = pd.read_csv(TEST_PRED_CSV)
    feature_cols = [str(f) for f in m.feature_names_in_]
    assert isinstance(m, LinearRegression), type(m)
    assert feature_cols == list(joblib.load(FEATURES_JOBLIB))
    X = tp[feature_cols]
    diff = np.abs(m.predict(X) - tp["Predicted_Revenue"].to_numpy()).max()
    print(f"Reload artefak {path.name}: {type(m).__name__}, "
          f"{m.n_features_in_} fitur, max selisih prediksi {diff:.3e}")
    if diff > TOL:
        fail("artefak hasil reload tidak mereproduksi prediksi notebook")


def main() -> None:
    lr, feature_cols, X_test, y_test, _ = build_model()
    print("=== VERIFIKASI MODEL HASIL REPLIKASI ===")
    verify(lr, feature_cols, X_test, y_test)

    # Simpan sementara (belum menimpa artefak lama)
    joblib.dump(lr, NEW_TMP)
    print("\n=== VERIFIKASI ARTEFAK DARI FILE (reload) ===")
    verify_artifact_file(NEW_TMP)

    # Semua verifikasi lolos -> swap artefak
    print("\n=== SWAP ARTEFAK ===")
    if OLD_ARTIFACT.exists():
        shutil.move(str(OLD_ARTIFACT), str(OLD_RENAMED))
        print(f"Artefak lama (model Quantity) dipindah ke: {OLD_RENAMED.name}")
    shutil.move(str(NEW_TMP), str(OLD_ARTIFACT))
    print(f"Artefak baru terpasang              : {OLD_ARTIFACT.name}")

    verify_artifact_file(OLD_ARTIFACT)
    print("\nSELESAI - artefak revenue forecasting yang benar kini aktif.")


if __name__ == "__main__":
    main()

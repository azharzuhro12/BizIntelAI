"""Endpoint forecasting revenue - inference dari artefak model yang ada."""

from fastapi import APIRouter, HTTPException, Query

from ..schemas import ForecastResponse
from ..services.forecast_service import (
    ForecastModelUnavailableError,
    forecast_revenue,
)

router = APIRouter()


@router.get("/revenue", response_model=ForecastResponse)
def read_revenue_forecast(
    days: int = Query(7, ge=1, le=30, description="Jumlah hari ke depan"),
):
    """Prediksi revenue N hari setelah data terakhir di daily_metrics.

    Memuat artefak backend/models/revenue_forecasting_linear_regression.joblib
    (tanpa retraining). Jika artefak tidak kompatibel, endpoint mengembalikan
    503 dengan diagnosis persis - bukan workaround.
    """
    try:
        return forecast_revenue(days)
    except ForecastModelUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "forecast_model_unavailable",
                "reason": str(exc),
                "model_file": "backend/models/revenue_forecasting_linear_regression.joblib",
                "features_file": "backend/models/forecast_features.joblib",
                "hint": (
                    "Artefak dibuat ulang dengan menjalankan "
                    "python3 scripts/export_forecast_model.py dari root "
                    "project (replikasi exact training notebook), lalu "
                    "restart backend."
                ),
            },
        )

"""Endpoint analitik BizIntel AI - semua data dari PostgreSQL."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..db import get_connection
from ..schemas import (
    AnomalyDay,
    CityRevenue,
    DailyRevenuePoint,
    KPIResponse,
    MonthlyRevenue,
    ProductRevenue,
)
from ..services import analytics_service

router = APIRouter()


@router.get("/kpi", response_model=KPIResponse)
def read_kpi():
    """KPI utama: total revenue, quantity, transaksi, AOV, rentang tanggal."""
    with get_connection() as conn:
        return analytics_service.get_kpi(conn)


@router.get("/revenue", response_model=list[DailyRevenuePoint])
def read_daily_revenue(
    start_date: date | None = Query(None, description="Filter mulai (inklusif), format YYYY-MM-DD"),
    end_date: date | None = Query(None, description="Filter akhir (inklusif), format YYYY-MM-DD"),
):
    """Revenue harian dari daily_metrics. Tanpa filter = seluruh histori."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail=f"start_date ({start_date}) tidak boleh lebih besar dari end_date ({end_date})",
        )
    with get_connection() as conn:
        return analytics_service.get_daily_revenue(conn, start_date, end_date)


@router.get("/products", response_model=list[ProductRevenue])
def read_product_revenue():
    """Revenue & quantity per produk (diurutkan dari revenue terbesar)."""
    with get_connection() as conn:
        return analytics_service.get_product_revenue(conn)


@router.get("/cities", response_model=list[CityRevenue])
def read_city_revenue():
    """Revenue & quantity per kota (diurutkan dari revenue terbesar)."""
    with get_connection() as conn:
        return analytics_service.get_city_revenue(conn)


@router.get("/monthly", response_model=list[MonthlyRevenue])
def read_monthly_revenue():
    """Agregat bulanan dari view v_monthly_metrics."""
    with get_connection() as conn:
        return analytics_service.get_monthly_revenue(conn)


@router.get("/anomalies", response_model=list[AnomalyDay])
def read_anomalies():
    """Hari-hari ber-flag anomaly (IsolationForest) dari daily_metrics."""
    with get_connection() as conn:
        return analytics_service.get_anomalies(conn)

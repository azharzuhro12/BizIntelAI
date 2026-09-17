"""Test API BizIntel AI.

Nilai ekspektasi = angka yang SUDAH tervalidasi konsisten antara
PostgreSQL dan notebook (lihat scripts/validate_db.py):
  - 254 transaksi unik, 53 hari observasi, 8 hari anomaly
  - total revenue 769515.86, total quantity 116995.31
  - top product Burgers 376999.81, top city Lisbon 241714.12
  - monthly: 2022-11 = 332114.66, 2022-12 = 437401.20

Test forecast mengharapkan 503 karena artefak yang tersimpan terbukti
BUKAN model revenue forecasting (lihat laporan tahap backend).
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["tables"]["sales"] == 254
    assert body["tables"]["daily_metrics"] == 53


def test_health_db_down_does_not_leak_connection_details(monkeypatch):
    """Regression (Phase 7): detail 503 hanya klasifikasi aman, TIDAK berisi
    str(exc) psycopg2 (yang memuat host/user/password-midtransaksi)."""

    class _FakeOperationalError(Exception):
        pass

    def _raise(*args, **kwargs):
        raise _FakeOperationalError(
            "connection to server at 10.0.0.5:5432 failed: FATAL: password "
            "authentication failed for user \"bizintel\""
        )

    monkeypatch.setattr("app.main.get_connection", _raise)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()["detail"]
    assert body["status"] == "error"
    # hanya kode klasifikasi - tidak ada detail exception mentah
    assert body["database"] in {
        "unreachable_or_auth_failed",
        "schema_missing",
        "database_error",
    }
    dumped = repr(body)
    assert "10.0.0.5" not in dumped
    assert "bizintel" not in dumped
    assert "password" not in dumped.lower()


def test_kpi_matches_validated_db():
    r = client.get("/api/analytics/kpi")
    assert r.status_code == 200
    kpi = r.json()
    assert kpi["total_revenue"] == 769515.86
    assert kpi["total_quantity"] == 116995.31
    assert kpi["total_transactions"] == 254
    # 769515.8592 / 254
    assert kpi["average_transaction_value"] == 3029.59
    assert kpi["date_range_start"] == "2022-11-07"
    assert kpi["date_range_end"] == "2022-12-29"


def test_revenue_daily_full_history():
    r = client.get("/api/analytics/revenue")
    assert r.status_code == 200
    points = r.json()
    assert len(points) == 53
    assert points[0]["date"] == "2022-11-07"
    assert points[-1]["date"] == "2022-12-29"
    total = round(sum(p["revenue"] for p in points), 2)
    assert abs(total - 769515.86) < 0.05  # toleransi pembulatan 2 desimal


def test_revenue_date_filter():
    r = client.get(
        "/api/analytics/revenue",
        params={"start_date": "2022-12-01", "end_date": "2022-12-31"},
    )
    assert r.status_code == 200
    points = r.json()
    assert len(points) == 29
    assert all(p["date"] >= "2022-12-01" for p in points)


def test_revenue_invalid_range_rejected():
    r = client.get(
        "/api/analytics/revenue",
        params={"start_date": "2022-12-31", "end_date": "2022-12-01"},
    )
    assert r.status_code == 400


def test_revenue_invalid_date_format_rejected():
    r = client.get("/api/analytics/revenue", params={"start_date": "31-12-2022"})
    assert r.status_code == 422


def test_products_aggregation():
    r = client.get("/api/analytics/products")
    assert r.status_code == 200
    products = r.json()
    assert len(products) == 5
    assert products[0]["product"] == "Burgers"
    assert products[0]["revenue"] == 376999.81
    by_name = {p["product"]: p["revenue"] for p in products}
    assert by_name["Beverages"] == 103200.26
    assert by_name["Sides & Other"] == 48999.80


def test_cities_aggregation():
    r = client.get("/api/analytics/cities")
    assert r.status_code == 200
    cities = r.json()
    assert len(cities) == 5
    assert cities[0]["city"] == "Lisbon"
    assert cities[0]["revenue"] == 241714.12


def test_monthly_from_view():
    r = client.get("/api/analytics/monthly")
    assert r.status_code == 200
    monthly = r.json()
    assert len(monthly) == 2
    by_month = {m["month"]: m["revenue"] for m in monthly}
    assert by_month["2022-11-01"] == 332114.66
    assert by_month["2022-12-01"] == 437401.20


def test_anomalies_count_is_eight():
    r = client.get("/api/analytics/anomalies")
    assert r.status_code == 200
    anomalies = r.json()
    assert len(anomalies) == 8
    assert all(a["is_anomaly"] is True for a in anomalies)
    assert all(a["anomaly_score_label"] == -1 for a in anomalies)


def test_forecast_revenue_returns_valid_forecast():
    """Artefak revenue forecasting sudah benar (LinearRegression 7 fitur
    time-series, terverifikasi mereproduksi prediksi notebook) - endpoint
    harus mengembalikan HTTP 200 dengan forecast sesuai kontrak."""
    r = client.get("/api/forecast/revenue")
    assert r.status_code == 200
    body = r.json()

    # metadata sesuai schema ForecastResponse
    assert body["model"] == "revenue_forecasting_linear_regression"
    assert body["features"] == [
        "day_of_week", "day_of_month", "month", "is_weekend",
        "lag_1", "lag_7", "rolling_mean_7",
    ]
    assert body["last_history_date"] == "2022-12-29"  # hari terakhir daily_metrics
    assert body["days"] == 7  # nilai default kontrak endpoint

    # jumlah prediction sesuai kontrak (default 7 hari)
    predictions = body["predictions"]
    assert len(predictions) == 7

    # setiap prediction sesuai schema aktual: {date, predicted_revenue}
    for p in predictions:
        assert set(p.keys()) == {"date", "predicted_revenue"}
        assert isinstance(p["predicted_revenue"], (int, float))

    # tanggal berurutan harian, dimulai hari setelah riwayat terakhir
    # (catatan: nilai Januari bisa negatif - limitasi ekstrapolasi model
    # linear saat bulan bergeser di luar range training, bukan error)
    expected_dates = [
        (date(2022, 12, 30) + timedelta(days=i)).isoformat() for i in range(7)
    ]
    assert [p["date"] for p in predictions] == expected_dates


def test_forecast_invalid_days_rejected():
    r = client.get("/api/forecast/revenue", params={"days": 0})
    assert r.status_code == 422
    r = client.get("/api/forecast/revenue", params={"days": 99})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# CORS (Phase 6): preflight + header origin frontend dev diizinkan eksplisit
# ---------------------------------------------------------------------------
def test_cors_preflight_from_frontend_origin():
    r = client.options(
        "/api/analytics/kpi",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "GET" in r.headers["access-control-allow-methods"]


def test_cors_get_response_has_allow_origin():
    r = client.get("/api/health", headers={"Origin": "http://127.0.0.1:3000"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_cors_unknown_origin_not_allowed():
    r = client.get(
        "/api/health", headers={"Origin": "http://evil.example.com"}
    )
    assert r.status_code == 200  # request tetap diproses (tanpa cookie auth)
    assert "access-control-allow-origin" not in r.headers

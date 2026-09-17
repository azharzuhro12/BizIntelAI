"""Analytics tools untuk AI Agent BizIntel AI (Phase 1: SQL, Phase 2: ML).

PRINSIP KEAMANAN (read-only, tanpa SQL mentah):
- TIDAK ADA tool yang menerima SQL dari user maupun dari LLM; tidak ada tool
  execute_sql. LLM hanya dapat memilih nama tool + parameter bisnis.
- Setiap tool membungkus fungsi service yang sudah ada: teks query tetap
  (didefinisikan di service, bukan input), dan parameterized (psycopg2 named
  params) sehingga tidak ada jalur SQL injection via agent.
- Semua query hanya SELECT terhadap sales / daily_metrics / v_monthly_metrics.
- Satu-satunya parameter bebas dari luar adalah nilai bisnis (rentang
  tanggal / jumlah hari forecast), dan divalidasi sebelum masuk service.
- Tidak ada eksekusi Python arbitrer; path artefak model TIDAK berasal dari
  input user/LLM (tetap di forecast_service).

PRINSIP ML (Phase 2):
- Tool ML hanya membungkus forecast_service yang sudah ada - TIDAK ada
  duplikasi logic forecasting, TIDAK ada retraining/model baru.
- Nilai prediksi dikembalikan apa adanya (tidak di-clamp/diubah); jika
  artefak gagal dimuat, dikembalikan error terstruktur - bukan angka fallback.

Hasil tool dikembalikan sebagai string JSON agar bisa dimasukkan ke
ToolMessage dan dibaca LLM.
"""

import json
from datetime import date

from langchain_core.tools import tool

from ..db import get_connection
from ..rag.retriever import search_knowledge
from ..services import analytics_service
from ..services.forecast_service import (
    ForecastModelUnavailableError,
    forecast_revenue,
)


def _json(data) -> str:
    """Serialisasi hasil query untuk dikirim kembali ke LLM."""
    return json.dumps(data, default=str, ensure_ascii=False)


def _parse_date(value: str | None) -> date | None:
    """Konversi parameter tanggal; ValueError jika format tidak valid."""
    if value in (None, ""):
        return None
    return date.fromisoformat(value)


@tool
def get_kpi() -> str:
    """KPI utama penjualan: total revenue, total quantity, jumlah transaksi,
    rata-rata nilai transaksi (AOV), dan rentang tanggal data yang tersedia.
    Gunakan untuk pertanyaan menyeluruh seperti 'berapa total revenue?'."""
    with get_connection() as conn:
        return _json(analytics_service.get_kpi(conn))


@tool
def get_revenue_by_period(start_date: str = "", end_date: str = "") -> str:
    """Revenue harian (dari daily_metrics) untuk rentang tanggal opsional,
    format YYYY-MM-DD. Tanpa parameter = seluruh histori. Kolom per hari:
    date, revenue, quantity, transactions."""
    try:
        start, end = _parse_date(start_date), _parse_date(end_date)
    except ValueError:
        return _json(
            {"error": "Format tanggal tidak valid; gunakan YYYY-MM-DD."}
        )
    if start and end and start > end:
        return _json(
            {"error": "start_date tidak boleh lebih besar dari end_date."}
        )
    with get_connection() as conn:
        return _json(analytics_service.get_daily_revenue(conn, start, end))


@tool
def get_revenue_by_product() -> str:
    """Revenue & quantity total per produk, diurutkan dari revenue terbesar.
    Gunakan untuk pertanyaan seperti 'produk mana yang revenue-nya terbesar?'."""
    with get_connection() as conn:
        return _json(analytics_service.get_product_revenue(conn))


@tool
def get_revenue_by_city() -> str:
    """Revenue & quantity total per kota, diurutkan dari revenue terbesar.
    Gunakan untuk pertanyaan seperti 'berapa revenue di Lisbon?'."""
    with get_connection() as conn:
        return _json(analytics_service.get_city_revenue(conn))


@tool
def get_monthly_revenue() -> str:
    """Agregat revenue/quantity/transaksi per bulan (view v_monthly_metrics).
    Gunakan untuk perbandingan antar bulan, misalnya November vs Desember."""
    with get_connection() as conn:
        return _json(analytics_service.get_monthly_revenue(conn))


@tool
def get_anomalies() -> str:
    """Daftar hari ber-flag anomaly (hasil IsolationForest di notebook):
    tanggal, revenue, quantity, transactions, label. Gunakan untuk
    'apakah ada hari anomali?' atau 'kapan terjadi anomaly & berapa
    revenue hari itu?'."""
    with get_connection() as conn:
        return _json(analytics_service.get_anomalies(conn))


@tool
def get_revenue_forecast(days: int = 3) -> str:
    """Prediksi (forecast) revenue N hari ke depan setelah data terakhir
    (2022-12-29), dihasilkan model ML LinearRegression time-series - ini
    PREDIKSI, bukan data aktual. Parameter days: 1-30, default 3 (horizon
    pendek lebih andal). Gunakan untuk pertanyaan tentang prediksi/forecast/
    perkiraan revenue masa depan. Jangan memakai tool ini untuk data
    historis."""
    if not 1 <= days <= 30:
        return _json(
            {"error": "days harus bilangan bulat antara 1 dan 30."}
        )
    try:
        # Membungkus forecast_service yang sudah ada (tanpa duplikasi logic):
        # memuat artefak revenue_forecasting_linear_regression.joblib dan
        # melakukan recursive forecasting dari riwayat daily_metrics.
        result = forecast_revenue(days)
    except ForecastModelUnavailableError as exc:
        # Model gagal -> error terstruktur yang aman, TANPA angka fallback.
        return _json(
            {"error": "forecast_model_unavailable", "detail": str(exc)[:300]}
        )
    return _json(result)


@tool
def search_business_knowledge(query: str, top_k: int = 4) -> str:
    """Cari kebijakan/pengetahuan bisnis (business policy) restoran dari
    dokumen internal: sales policy, promotion policy, inventory/restock,
    product guidelines, business guidelines. Gunakan untuk pertanyaan tentang
    ATURAN/KEBIJAKAN/PROSEDUR bisnis (mis. 'apa aturan promotion?', 'kapan
    perlu restock?', 'bagaimana cara membaca KPI?') - BUKAN untuk angka
    transaksi (pakai tool SQL) dan BUKAN untuk prediksi (pakai tool forecast).
    Hasil berisi kutipan dokumen + source untuk citation."""
    q = (query or "").strip()
    if not q:
        return _json(
            {"query": "", "results": [], "message": "Query kosong."}
        )
    if not 1 <= top_k <= 10:
        top_k = 4
    # Query hanya menjadi teks pencarian embedding - tidak pernah dipakai
    # sebagai path file/SQL; knowledge base fixed di data/knowledge/.
    return _json(search_knowledge(q, top_k))


# Registry eksplisit: satu-satunya cara LLM menyentuh database & model ML.
AGENT_TOOLS = [
    get_kpi,
    get_revenue_by_period,
    get_revenue_by_product,
    get_revenue_by_city,
    get_monthly_revenue,
    get_anomalies,
    get_revenue_forecast,
    search_business_knowledge,
]

# Parameter tool yang diizinkan (untuk audit keamanan / test):
# hanya nilai bisnis/search, tidak ada parameter 'sql'/'path'/'file'.
ALLOWED_TOOL_PARAMS = {
    "get_kpi": set(),
    "get_revenue_by_period": {"start_date", "end_date"},
    "get_revenue_by_product": set(),
    "get_revenue_by_city": set(),
    "get_monthly_revenue": set(),
    "get_anomalies": set(),
    "get_revenue_forecast": {"days"},
    "search_business_knowledge": {"query", "top_k"},
}


def get_tools():
    """Salinan daftar tool agent (dipakai graph & test)."""
    return list(AGENT_TOOLS)

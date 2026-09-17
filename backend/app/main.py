"""BizIntel AI - FastAPI backend.

Menyajikan data & analitik dari PostgreSQL (source of truth):
tabel sales, daily_metrics, dan view v_monthly_metrics.
Termasuk AI agent (LangGraph) via POST /api/chat dengan conversation
memory per session_id dan audit agent_runs (Phase 4).

Menjalankan (dari folder backend/):
    uvicorn app.main:app --host 127.0.0.1 --port 8020
Dokumentasi Swagger: http://127.0.0.1:8020/docs
"""

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import get_connection
from .routers import agent, analytics, chat, forecast, rag

app = FastAPI(
    title="BizIntel AI API",
    description=(
        "Backend analitik business intelligence untuk data penjualan "
        "restoran. Sumber data: PostgreSQL (sales, daily_metrics, "
        "v_monthly_metrics). AI agent: POST /api/chat (memory per sesi + "
        "audit agent_runs)."
    ),
    version="0.3.0",
)

# CORS: origin frontend dev (Next.js). Eksplisit - BUKAN "*" - dan bisa
# dioverride via env untuk port lain (dipisah koma). Tidak ada credentials/
# cookie auth di API ini, jadi allow_credentials tidak diperlukan.
_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("BIZINTEL_CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(forecast.router, prefix="/api/forecast", tags=["Forecast"])
app.include_router(chat.router, prefix="/api/chat", tags=["Agent"])
app.include_router(rag.router, prefix="/api/rag", tags=["Agent"])
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])

logger = logging.getLogger(__name__)


def _classify_db_error(exc: Exception) -> str:
    """Klasifikasi kegagalan DB untuk respons health TANPA membocorkan
    detail exception (host/user/path bisa terkandung di str(exc)).
    Detail lengkap tetap tercatat di log server."""
    name = type(exc).__name__
    if "OperationalError" in name:
        return "unreachable_or_auth_failed"
    if "ProgrammingError" in name:
        return "schema_missing"
    return "database_error"


@app.get("/api/health", tags=["System"])
def health_check():
    """Cek kesehatan service + koneksi PostgreSQL."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT (SELECT COUNT(*) FROM sales), "
                    "(SELECT COUNT(*) FROM daily_metrics)"
                )
                sales_rows, daily_rows = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - dilaporkan sebagai 503
        logger.error("Health check gagal: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": _classify_db_error(exc),
            },
        )

    return {
        "status": "ok",
        "database": "connected",
        "tables": {"sales": sales_rows, "daily_metrics": daily_rows},
    }

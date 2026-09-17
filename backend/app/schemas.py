"""Skema respons Pydantic untuk API BizIntel AI.

Nama field mengikuti kolom aktual di PostgreSQL
(sales, daily_metrics, v_monthly_metrics) - lihat db/init/01_schema.sql.
"""

import re
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

# session_id hanya string biasa (parameter query), tetapi dibatasi charset
# aman agar tidak pernah menyerupai path/identifier: huruf, angka, - _ .
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SESSION_ID_MAX_LEN = 128



class KPIResponse(BaseModel):
    total_revenue: float
    total_quantity: float
    total_transactions: int
    average_transaction_value: float
    date_range_start: date
    date_range_end: date


class DailyRevenuePoint(BaseModel):
    date: date
    revenue: float
    quantity: float
    transactions: int


class ProductRevenue(BaseModel):
    product: str
    revenue: float
    quantity: float


class CityRevenue(BaseModel):
    city: str
    revenue: float
    quantity: float


class MonthlyRevenue(BaseModel):
    month: date
    revenue: float
    quantity: float
    transactions: int


class AnomalyDay(BaseModel):
    date: date
    revenue: float
    quantity: float
    transactions: int
    anomaly_score_label: int
    is_anomaly: bool


class ForecastPoint(BaseModel):
    date: date
    predicted_revenue: float


class ForecastResponse(BaseModel):
    model: str
    features: list[str]
    last_history_date: date
    days: int
    predictions: list[ForecastPoint]


class ChatRequest(BaseModel):
    """Request POST /api/chat - satu pertanyaan untuk AI agent."""

    message: str = Field(
        min_length=1,
        max_length=2000,
        examples=["Berapa total revenue?"],
        description="Pertanyaan bisnis dalam bahasa bebas",
    )
    session_id: str | None = Field(
        default=None,
        examples=["demo-session-001"],
        description=(
            "ID sesi percakapan (opsional). Sesi yang sama mempertahankan "
            "konteks percakapan; jika kosong, dibuat otomatis per request."
        ),
    )

    @field_validator("session_id")
    @classmethod
    def _clean_session_id(cls, value: str | None) -> str | None:
        """Trim, tolak kosong, batasi panjang + charset aman.

        session_id hanya dipakai sebagai nilai parameter query (tidak pernah
        path/identifier/shell argumen), charset ketat adalah lapisan pertahanan
        ekstra - '../.env' ditolak 422, bukan dibuka sebagai file.
        """
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("session_id tidak boleh kosong")
        if len(value) > SESSION_ID_MAX_LEN:
            raise ValueError("session_id maksimal 128 karakter")
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "session_id hanya boleh berisi huruf, angka, '-', '_', '.'"
            )
        return value


class ChatResponse(BaseModel):
    """Response POST /api/chat - jawaban agent + jejak tool yang dipakai."""

    answer: str
    tools_used: list[str] = Field(
        default_factory=list,
        description="Nama tool yang dipanggil agent, urut pemanggilan",
    )
    session_id: str = Field(
        description="ID sesi yang dipakai untuk percakapan ini",
    )


class AgentRunRecord(BaseModel):
    """Satu baris audit agent_runs (lihat app/agent/audit.py)."""

    run_id: int
    session_id: str
    user_message: str
    assistant_message: str | None
    tools_used: list[str]
    status: str
    error_type: str | None
    latency_ms: int | None
    model_name: str | None
    created_at: datetime


class AgentRunListResponse(BaseModel):
    """Response GET /api/agent/runs/{session_id} (debug, read-only)."""

    session_id: str
    count: int
    runs: list[AgentRunRecord]


class RagSearchRequest(BaseModel):
    """Request POST /api/rag/search - debugging Retrieval RAG (internal)."""

    query: str = Field(
        min_length=1,
        max_length=1000,
        examples=["Apa aturan promotion?"],
        description="Query pencarian natural language",
    )
    top_k: int = Field(default=4, ge=1, le=10, description="Jumlah chunk teratas")

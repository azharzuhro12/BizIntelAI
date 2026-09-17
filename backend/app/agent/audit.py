"""Observability/audit agent Phase 4 - tabel agent_runs (PostgreSQL).

Satu record per eksekusi /api/chat (bukan per token/tool). Ini AUDIT log,
berbeda dari conversation memory (agent_messages) - lihat docs/agent-phase4.md.

Yang dicatat: session_id, user_message, assistant_message, tools_used
(dari eksekusi aktual, bukan karangan), status (SUCCESS/ERROR), error_type
generik (LLM_ERROR/MEMORY_ERROR/AGENT_ERROR), latency_ms (monotonic clock),
model_name, created_at. TIDAK ADA credential/secret yang dicatat.
"""

import logging
from typing import Optional

from psycopg2.extras import Json

from ..db import get_connection
from .ensure import ensure_agent_tables
from .memory import MemoryStoreError  # dipakai bersama memory store & audit reader

logger = logging.getLogger("bizintel.agent")

DEFAULT_RUN_LIMIT = 20
MAX_RUN_LIMIT = 50

_RUN_COLUMNS = (
    "run_id, session_id, user_message, assistant_message, tools_used, "
    "status, error_type, latency_ms, model_name, created_at"
)


def record_run(
    *,
    session_id: str,
    user_message: str,
    assistant_message: Optional[str],
    tools_used: list[str],
    status: str,
    error_type: Optional[str] = None,
    latency_ms: Optional[int] = None,
    model_name: Optional[str] = None,
) -> Optional[int]:
    """Insert satu baris audit. Best-effort: kegagalan insert tidak boleh
    merusak response user (detail hanya ke log server)."""
    try:
        ensure_agent_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_runs "
                    "(session_id, user_message, assistant_message, tools_used, "
                    "status, error_type, latency_ms, model_name) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING run_id",
                    (
                        session_id,
                        user_message,
                        assistant_message,
                        Json(list(tools_used)),
                        status,
                        error_type,
                        latency_ms,
                        model_name,
                    ),
                )
                run_id = cur.fetchone()[0]
            conn.commit()
        return int(run_id)
    except Exception:  # noqa: BLE001 - audit bersifat best-effort
        logger.exception("Gagal mencatat agent_run")
        return None


def get_runs(session_id: str, limit: int = DEFAULT_RUN_LIMIT) -> list[dict]:
    """Ambil run terbaru sebuah sesi (read-only, parameterized, dibatasi)."""
    limit = max(1, min(int(limit), MAX_RUN_LIMIT))
    try:
        ensure_agent_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_RUN_COLUMNS} FROM agent_runs "
                    "WHERE session_id = %s ORDER BY run_id DESC LIMIT %s",
                    (session_id, limit),
                )
                rows = cur.fetchall()
    except Exception as exc:
        raise MemoryStoreError(f"gagal membaca agent_runs (detail di log server)") from exc

    keys = _RUN_COLUMNS.split(", ")
    return [dict(zip(keys, row)) for row in rows]

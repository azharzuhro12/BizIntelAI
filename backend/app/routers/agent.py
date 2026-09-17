"""Endpoint observability agent - GET /api/agent/runs/{session_id} (debug).

Read-only: SELECT parameterized terhadap agent_runs, dibatasi jumlah record,
tanpa stack trace internal / credential pada response. Hanya untuk audit &
debugging observability Phase 4 (bukan sumber data analytics).
"""

import logging

from fastapi import APIRouter, HTTPException, Path, Query

from ..agent.audit import MAX_RUN_LIMIT, get_runs
from ..agent.memory import MemoryStoreError
from ..schemas import SESSION_ID_MAX_LEN, SESSION_ID_PATTERN, AgentRunListResponse

logger = logging.getLogger("bizintel.agent")

router = APIRouter()


@router.get("/runs/{session_id}", response_model=AgentRunListResponse)
def list_agent_runs(
    session_id: str = Path(
        description="ID sesi yang mau dilihat riwayat eksekusinya",
        pattern=SESSION_ID_PATTERN.pattern,
        max_length=SESSION_ID_MAX_LEN,
    ),
    limit: int = Query(default=20, ge=1, le=MAX_RUN_LIMIT),
) -> AgentRunListResponse:
    """Riwayat eksekusi agent (audit agent_runs) untuk satu session_id."""
    try:
        runs = get_runs(session_id, limit)
    except MemoryStoreError:
        logger.exception("Gagal membaca agent_runs (session %s)", session_id)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "audit_unavailable",
                "reason": "Audit log tidak dapat dibaca saat ini.",
            },
        )
    return AgentRunListResponse(session_id=session_id, count=len(runs), runs=runs)

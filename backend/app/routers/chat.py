"""Endpoint AI Agent - POST /api/chat (LangGraph + tools + memory + audit).

Phase 4:
- session_id opsional pada request (auto-generated jika kosong) -> memory
  percakapan per sesi (lihat app/agent/memory.py).
- SETIAP eksekusi dicatat ke agent_runs (observability): status, error_type
  generik, latency_ms (monotonic), tools_used dari eksekusi aktual.
- Fail closed pada kegagalan memory (MemoryStoreError -> 503); tidak pernah
  fallback ke history sesi lain.
"""

import logging
import time

from fastapi import APIRouter, HTTPException

from ..agent.audit import record_run
from ..agent.graph import run_agent_chat
from ..agent.llm import LLMNotConfiguredError, get_llm_config
from ..agent.memory import MemoryStoreError, new_session_id
from ..schemas import ChatRequest, ChatResponse

logger = logging.getLogger("bizintel.agent")

router = APIRouter()


def _safe_model_name() -> str | None:
    """Nama model untuk audit; None bila LLM belum dikonfigurasi/gagal dibaca."""
    try:
        return get_llm_config().get("model")
    except Exception:  # noqa: BLE001 - metadata audit saja
        return None


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Ajukan pertanyaan bisnis ke AI agent.

    Agent memilih tool analitik read-only (SQL/ML/RAG) yang relevan dan wajib
    menjawab berdasarkan hasil tool (grounding) - lihat docs/agent-phase1..4.md.
    Kirim ``session_id`` yang sama untuk percakapan multi-turn. Response berisi
    jawaban + daftar tool yang benar-benar dipanggil + session_id yang dipakai.
    """
    session_id = request.session_id or new_session_id()
    start = time.monotonic()

    answer: str | None = None
    tools_used: list[str] = []
    status = "SUCCESS"
    error_type: str | None = None
    http_error: HTTPException | None = None

    try:
        result = run_agent_chat(request.message, session_id)
        answer = result["answer"]
        tools_used = result["tools_used"]
    except LLMNotConfiguredError as exc:
        error_type = "LLM_ERROR"
        logger.error("Chat gagal: LLM tidak dikonfigurasi (session %s)", session_id)
        http_error = HTTPException(
            status_code=503,
            detail={
                "error": "llm_not_configured",
                "reason": str(exc),
                "hint": (
                    "Set ANTHROPIC_API_KEY atau ANTHROPIC_AUTH_TOKEN (opsional: "
                    "ANTHROPIC_BASE_URL, ANTHROPIC_MODEL) di environment atau "
                    "file .env root project, lalu restart backend."
                ),
            },
        )
    except MemoryStoreError:
        # Fail closed: tanpa memory yang benar, sesi tidak diproses agar
        # konteks tidak tertukar antar session (tidak ada fallback global).
        error_type = "MEMORY_ERROR"
        logger.exception("Chat gagal: conversation memory (session %s)", session_id)
        http_error = HTTPException(
            status_code=503,
            detail={
                "error": "memory_unavailable",
                "reason": (
                    "Conversation memory tidak tersedia saat ini; permintaan "
                    "tidak diproses agar konteks sesi tidak tertukar."
                ),
            },
        )
    except Exception:  # noqa: BLE001 - kegagalan LLM/network; detail hanya ke log
        error_type = "AGENT_ERROR"
        logger.exception("Agent chat gagal memproses pesan (session %s)", session_id)
        http_error = HTTPException(
            status_code=502,
            detail={
                "error": "agent_failure",
                "reason": (
                    "LLM/agent gagal diproses; lihat log server untuk detail."
                ),
            },
        )

    # Satu baris audit per eksekusi (best-effort, tidak pernah mengandung
    # credential; insert gagal -> hanya log server, response tetap dikirim).
    latency_ms = round((time.monotonic() - start) * 1000)
    record_run(
        session_id=session_id,
        user_message=request.message,
        assistant_message=answer,
        tools_used=tools_used,
        status="ERROR" if http_error is not None else status,
        error_type=error_type,
        latency_ms=latency_ms,
        model_name=_safe_model_name(),
    )

    if http_error is not None:
        raise http_error
    return ChatResponse(answer=answer, tools_used=tools_used, session_id=session_id)

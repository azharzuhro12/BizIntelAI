"""Conversation memory Phase 4 - PostgreSQL-backed, keyed by session_id.

DESAIN (lihat docs/agent-phase4.md untuk analisis lengkap):
- Persistence layer sederhana & terstruktur sendiri (opsi prioritas #3 pada
  spesifikasi Phase 4), BUKAN LangGraph checkpointer:
  * MemorySaver official = process-local saja (hilang saat restart);
  * langgraph-checkpoint-postgres = dependensi baru (psycopg3 + pool) +
    tabel migrasi sendiri, dan checkpoint menyimpan SELURUH state graph
    sehingga truncation MAX_HISTORY_MESSAGES serta tools_used per-run
    jadi rumit dikendalikan.
- Graph agent TETAP stateless: history di-load per request, di-inject
  sebagai messages (setelah SystemMessage), lalu pasangan Human+AI terbaru
  di-append ke DB. tools_used tetap persis per eksekusi, tidak terakumulasi
  antar turn.
- Persisten di PostgreSQL -> bertahan lintas restart server.
- MEMORY HANYA konteks percakapan - BUKAN source of truth analytics
  (PostgreSQL), knowledge (ChromaDB), atau model (joblib). Tidak pernah
  menyimpan credential/env/path.
- FAIL CLOSED: kegagalan memory -> MemoryStoreError. Tidak pernah diam-diam
  memakai history session lain / global memory.
"""

import uuid

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ..db import get_connection
from .ensure import ensure_agent_tables

# Batas history yang di-inject ke konteks LLM (pesan TERBARU dipertahankan;
# request saat ini TIDAK ikut ter-truncate karena selalu di-append setelahnya).
MAX_HISTORY_MESSAGES = 20

SESSION_ID_MAX_LEN = 128


class MemoryStoreError(RuntimeError):
    """Kegagalan akses conversation memory (fail closed, bukan silent)."""


def new_session_id() -> str:
    """Session id baru untuk client yang tidak mengirim session_id."""
    return uuid.uuid4().hex


def load_history(session_id: str) -> list[BaseMessage]:
    """Ambil MAX_HISTORY_MESSAGES pesan terakhir sesi, urut kronologis.

    Hanya role 'human'/'ai' yang pernah tersimpan (dijaga CHECK constraint
    tabel) - history tidak mungkin berubah menjadi system prompt.
    """
    try:
        ensure_agent_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, content FROM agent_messages "
                    "WHERE session_id = %s "
                    "ORDER BY message_id DESC LIMIT %s",
                    (session_id, MAX_HISTORY_MESSAGES),
                )
                rows = cur.fetchall()
    except Exception as exc:
        raise MemoryStoreError(
            f"gagal memuat history sesi (detail di log server)"
        ) from exc

    messages: list[BaseMessage] = []
    for role, content in reversed(rows):  # DESC -> balik ke kronologis
        if role == "human":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages


def append_history(session_id: str, human_text: str, ai_text: str) -> None:
    """Simpan satu pasangan turn (human + ai) - satu INSERT atomik."""
    try:
        ensure_agent_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_messages (session_id, role, content) "
                    "VALUES (%s, 'human', %s), (%s, 'ai', %s)",
                    (session_id, human_text, session_id, ai_text),
                )
            conn.commit()
    except Exception as exc:
        raise MemoryStoreError(
            f"gagal menyimpan history sesi (detail di log server)"
        ) from exc


def history_size(session_id: str) -> int:
    """Jumlah total pesan tersimpan untuk sesi (untuk test/debug)."""
    try:
        ensure_agent_tables()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM agent_messages WHERE session_id = %s",
                    (session_id,),
                )
                return int(cur.fetchone()[0])
    except Exception as exc:
        raise MemoryStoreError(f"gagal menghitung history sesi") from exc


"""Pastikan tabel agent (agent_messages, agent_runs) ada - DDL idempotent.

Satu sumber DDL: db/init/02_agent.sql (dibaca langsung agar tidak ada
duplikasi definisi schema). File itu juga dijalankan otomatis oleh
docker-entrypoint-initdb.d untuk container baru; modul ini menutup kasus
container LAMA yang sudah jalan sebelum Phase 4 (initdb hanya jalan sekali).

Parser sengaja sederhana: schema 02_agent.sql hanya berisi komentar satu
baris penuh dan statement tanpa ';' di dalam string/comment.
"""

import logging
import re
from functools import lru_cache
from pathlib import Path

from ..db import get_connection

logger = logging.getLogger("bizintel.agent")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = PROJECT_ROOT / "db" / "init" / "02_agent.sql"


def _statements(sql_text: str) -> list[str]:
    """Pecah file SQL menjadi statement (abaikan baris komentar penuh)."""
    body = "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", body) if s.strip()]


@lru_cache(maxsize=1)
def ensure_agent_tables() -> None:
    """Jalankan DDL idempotent sekali per proses (CREATE ... IF NOT EXISTS)."""
    statements = _statements(MIGRATION_FILE.read_text())
    with get_connection() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        conn.commit()
    logger.info("Tabel agent siap (agent_messages, agent_runs)")

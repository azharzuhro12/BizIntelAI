"""Startup checks container backend BizIntel AI.

Dijalankan entrypoint.sh SEBELUM uvicorn:
  1. Tunggu PostgreSQL tersedia (retry sampai 60 detik).
  2. Terapkan schema idempotent dari /db/init/*.sql (IF NOT EXISTS).
  3. Import dataset (scripts/import_data.py) hanya bila tabel sales kosong.
  4. Ingest RAG ChromaDB (idempotent; deterministik dari /data/knowledge).

Gagal di langka mana pun -> proses exit non-zero -> container gagal start
(fail-closed), tidak ada server "setengah jalan".
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

# Skrip dijalankan entrypoint lewat path absolut (python3 /backend/docker/…)
# sehingga sys.path[0] = direktori skrip, bukan CWD /backend. Paket `app`
# harus di-import dari /backend -> daftarkan eksplisit.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_KWARGS = {
    "host": os.environ.get("PGHOST", "postgres"),
    "port": int(os.environ.get("PGPORT", "5432")),
    "user": os.environ.get("PGUSER") or os.environ["POSTGRES_USER"],
    "password": os.environ.get("PGPASSWORD") or os.environ["POSTGRES_PASSWORD"],
    "dbname": os.environ.get("PGDATABASE") or os.environ["POSTGRES_DB"],
}


def connect(**extra: int) -> "psycopg2.extensions.connection":
    return psycopg2.connect(connect_timeout=3, **{**DB_KWARGS, **extra})  # type: ignore[arg-type]


def wait_for_postgres() -> None:
    """Retry koneksi sampai DB siap (compose healthcheck sudah gating,
    retry ini tambahan untuk cold-start jaringan container)."""
    for _ in range(60):
        try:
            connect().close()
            print("[startup] PostgreSQL tersedia", flush=True)
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    raise SystemExit("[startup] PostgreSQL tidak tersedia setelah 60 detik")


def ensure_schema() -> None:
    """Jalankan ulang DDL idempotent (IF NOT EXISTS) dari /db/init."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            for sql_file in sorted(Path("/db/init").glob("*.sql")):
                cur.execute(sql_file.read_text())
        conn.commit()
    finally:
        conn.close()
    print("[startup] schema OK (DDL idempotent diterapkan)", flush=True)


def import_dataset_if_empty() -> None:
    """Import CSV hanya bila tabel sales masih kosong (volume baru)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM sales")
            (n_sales,) = cur.fetchone()
    finally:
        conn.close()
    if n_sales and n_sales > 0:
        print(f"[startup] dataset sudah ada (sales={n_sales}), import dilewati", flush=True)
        return
    print("[startup] tabel sales kosong -> import dataset", flush=True)
    subprocess.run(
        [sys.executable, "/scripts/import_data.py"],
        check=True,
        cwd="/",
    )


def ingest_rag() -> None:
    """Ingest knowledge -> ChromaDB (idempotent, chunk id deterministik)."""
    from app.rag.ingest import ingest_knowledge

    result = ingest_knowledge()
    if result.get("status") != "ok":
        raise SystemExit(f"[startup] RAG ingest gagal: {result.get('reason')}")
    print(f"[startup] RAG ingest OK ({result.get('chunks')} chunk)", flush=True)


if __name__ == "__main__":
    wait_for_postgres()
    ensure_schema()
    import_dataset_if_empty()
    ingest_rag()
    print("[startup] semua check lolos", flush=True)

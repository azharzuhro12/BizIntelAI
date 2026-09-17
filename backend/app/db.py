"""Koneksi PostgreSQL untuk BizIntel AI.

Sumber konfigurasi: file .env di root project, dengan override oleh
environment variable standar (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)
agar siap dipakai juga saat backend di-containerize nanti.
Tidak ada kredensial yang di-hardcode.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> dict:
    """Baca .env root project (tanpa dependensi python-dotenv)."""
    env_file = PROJECT_ROOT / ".env"
    values = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def get_db_config() -> dict:
    """Prioritas: environment variable > file .env."""
    file_env = _load_env_file()

    def pick(env_key: str, file_key: str, default: str) -> str:
        return os.environ.get(env_key, file_env.get(file_key, default))

    return {
        "host": pick("PGHOST", "POSTGRES_HOST", "localhost"),
        "port": int(pick("PGPORT", "POSTGRES_PORT", "5432")),
        "user": pick("PGUSER", "POSTGRES_USER", "bizintel"),
        "password": pick("PGPASSWORD", "POSTGRES_PASSWORD", ""),
        "dbname": pick("PGDATABASE", "POSTGRES_DB", "bizintel"),
    }


@contextmanager
def get_connection():
    """Context manager koneksi PostgreSQL (ditutup otomatis)."""
    conn = psycopg2.connect(**get_db_config())
    try:
        yield conn
    finally:
        conn.close()

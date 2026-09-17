#!/usr/bin/env python3
"""
BizIntel AI - Import dataset hasil notebook ke PostgreSQL.

Sumber data (hasil notebook, BUKAN dummy):
  - data/processed/cleaned_transactions.csv -> tabel sales
  - data/processed/daily_sales.csv          -> tabel daily_metrics

Catatan normalisasi (tidak mengubah angka/hasil ML apa pun):
  - purchase_type / payment_method di-TRIM dari spasi bawaan CSV asli
    (mis. "Online " -> "Online", " Gift Card" -> "Gift Card")
  - Is_Anomaly "True"/"False" dikonversi ke BOOLEAN asli

Script idempotent: menjalankan ulang akan TRUNCATE lalu insert ulang.

Pemakaian:  python3 scripts/import_data.py
"""

import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"


def load_env() -> dict:
    """Baca .env sederhana tanpa dependensi tambahan (opsional: absen di
    container, kredensial datang dari env proses PG*)."""
    env = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        return env
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def import_sales(conn) -> int:
    df = pd.read_csv(DATA_DIR / "cleaned_transactions.csv")
    df["Purchase Type"] = df["Purchase Type"].str.strip()
    df["Payment Method"] = df["Payment Method"].str.strip()

    rows = [
        (
            int(r["Order ID"]),
            pd.to_datetime(r["Date"]).date(),
            r["Product"],
            round(float(r["Price"]), 2),
            round(float(r["Quantity"]), 2),
            r["Purchase Type"],
            r["Payment Method"],
            r["Manager"],
            r["City"],
            round(float(r["Revenue"]), 4),
        )
        for _, r in df.iterrows()
    ]

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE sales RESTART IDENTITY")
        execute_values(
            cur,
            """
            INSERT INTO sales (order_id, sale_date, product, price, quantity,
                               purchase_type, payment_method, manager, city, revenue)
            VALUES %s
            """,
            rows,
        )
    return len(rows)


def import_daily_metrics(conn) -> int:
    df = pd.read_csv(DATA_DIR / "daily_sales.csv")
    df["Is_Anomaly"] = df["Is_Anomaly"].astype(str).str.lower() == "true"

    rows = [
        (
            pd.to_datetime(r["Date"]).date(),
            round(float(r["Revenue"]), 4),
            round(float(r["Quantity"]), 2),
            int(r["Transactions"]),
            int(r["anomaly_score_label"]),
            bool(r["Is_Anomaly"]),
        )
        for _, r in df.iterrows()
    ]

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE daily_metrics")
        execute_values(
            cur,
            """
            INSERT INTO daily_metrics (metric_date, revenue, quantity,
                                      transactions, anomaly_score_label, is_anomaly)
            VALUES %s
            """,
            rows,
        )
    return len(rows)


def main() -> None:
    # Prioritas sama dengan app/db.py: env proses PG* > file .env POSTGRES_*
    # (di container kredensial datang dari env proses; di host dari .env).
    env = load_env()
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST") or env.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("PGPORT") or env.get("POSTGRES_PORT", 5432)),
        user=os.environ.get("PGUSER") or env["POSTGRES_USER"],
        password=os.environ.get("PGPASSWORD") or env["POSTGRES_PASSWORD"],
        dbname=os.environ.get("PGDATABASE") or env["POSTGRES_DB"],
    )
    try:
        n_sales = import_sales(conn)
        n_daily = import_daily_metrics(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Import selesai: sales={n_sales} baris, daily_metrics={n_daily} baris")


if __name__ == "__main__":
    main()

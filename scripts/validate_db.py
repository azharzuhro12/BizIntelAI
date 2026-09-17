#!/usr/bin/env python3
"""
BizIntel AI - Validasi hasil PostgreSQL vs hasil notebook (CSV).

Membandingkan nilai yang dihitung dari CSV (pandas, sebagai "expected" =
hasil notebook) dengan nilai yang di-query dari PostgreSQL ("actual").

Cek yang dijalankan:
  1.  row count (sales)
  2.  unique orders
  3.  date range
  4.  total revenue
  5.  total quantity
  6.  revenue by product
  7.  revenue by city
  8.  monthly revenue (dibandingkan juga dengan monthly_revenue.csv)
  9.  daily_metrics: jumlah hari, total transaksi per hari vs sales
  10. jumlah hari anomaly vs sales_anomalies.csv

Exit code 1 jika ada mismatch.

Pemakaian:  python3 scripts/validate_db.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
ML_DIR = ROOT / "data" / "ml_outputs"

PASS, FAIL = "PASS", "FAIL"
failures = 0


def load_env() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def check(name: str, expected, actual) -> None:
    global failures
    ok = expected == actual
    if not ok:
        failures += 1
    mark = PASS if ok else FAIL
    print(f"  [{mark}] {name}: notebook={expected}  |  postgres={actual}")


def money(x: float) -> float:
    """Bulatkan ke 2 desimal untuk menghilangkan artefak float (mis. ...00003)."""
    return round(float(x), 2)


def main() -> None:
    env = load_env()
    # Precedensi sama dengan app/db.py & import_data.py: env PG* > .env
    # POSTGRES_* — memungkinkan validasi ke DB remote (mis. Supabase)
    # murni lewat environment variable, tanpa mengubah .env lokal.
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST") or env.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("PGPORT") or env.get("POSTGRES_PORT", 5432)),
        user=os.environ.get("PGUSER") or env["POSTGRES_USER"],
        password=os.environ.get("PGPASSWORD") or env["POSTGRES_PASSWORD"],
        dbname=os.environ.get("PGDATABASE") or env["POSTGRES_DB"],
    )
    cur = conn.cursor()

    # ---- Expected: dihitung ulang dari CSV hasil notebook ----
    tx = pd.read_csv(DATA_DIR / "cleaned_transactions.csv")
    daily = pd.read_csv(DATA_DIR / "daily_sales.csv")
    monthly_csv = pd.read_csv(DATA_DIR / "monthly_revenue.csv")
    anomalies_csv = pd.read_csv(ML_DIR / "sales_anomalies.csv")

    print("== 1. Row count ==")
    cur.execute("SELECT COUNT(*) FROM sales")
    check("jumlah baris sales", len(tx), cur.fetchone()[0])

    print("== 2. Unique orders ==")
    cur.execute("SELECT COUNT(DISTINCT order_id) FROM sales")
    check("unique order_id", int(tx["Order ID"].nunique()), cur.fetchone()[0])

    print("== 3. Date range ==")
    cur.execute("SELECT MIN(sale_date), MAX(sale_date) FROM sales")
    db_min, db_max = cur.fetchone()
    check(
        "rentang tanggal",
        (str(pd.to_datetime(tx["Date"]).min().date()), str(pd.to_datetime(tx["Date"]).max().date())),
        (str(db_min), str(db_max)),
    )

    print("== 4. Total revenue ==")
    cur.execute("SELECT SUM(revenue) FROM sales")
    check("total revenue", money(tx["Revenue"].sum()), money(cur.fetchone()[0]))

    print("== 5. Total quantity ==")
    cur.execute("SELECT SUM(quantity) FROM sales")
    check("total quantity", money(tx["Quantity"].sum()), money(cur.fetchone()[0]))

    print("== 6. Revenue by product ==")
    exp = {p: money(v) for p, v in tx.groupby("Product")["Revenue"].sum().items()}
    cur.execute(
        "SELECT product, SUM(revenue) FROM sales GROUP BY product ORDER BY product"
    )
    act = {p: money(v) for p, v in cur.fetchall()}
    for p in sorted(exp):
        check(f"revenue produk {p!r}", exp[p], act.get(p))

    print("== 7. Revenue by city ==")
    exp = {c: money(v) for c, v in tx.groupby("City")["Revenue"].sum().items()}
    cur.execute("SELECT city, SUM(revenue) FROM sales GROUP BY city ORDER BY city")
    act = {c: money(v) for c, v in cur.fetchall()}
    for c in sorted(exp):
        check(f"revenue kota {c!r}", exp[c], act.get(c))

    print("== 8. Monthly revenue (vs monthly_revenue.csv & vs view) ==")
    exp_monthly = {
        str(pd.to_datetime(d).date()): money(v)
        for d, v in zip(monthly_csv["Date"], monthly_csv["Revenue"])
    }
    # dari sales langsung
    cur.execute(
        """
        SELECT date_trunc('month', sale_date)::date AS bulan, SUM(revenue)
        FROM sales GROUP BY 1 ORDER BY 1
        """
    )
    act_sales = {str(b): money(v) for b, v in cur.fetchall()}
    # dari view v_monthly_metrics
    cur.execute("SELECT month, revenue FROM v_monthly_metrics")
    act_view = {str(b): money(v) for b, v in cur.fetchall()}
    for b in sorted(exp_monthly):
        check(f"bulan {b} (sales vs CSV)", exp_monthly[b], act_sales.get(b))
        check(f"bulan {b} (view vs CSV)", exp_monthly[b], act_view.get(b))

    print("== 9. daily_metrics konsisten dengan sales ==")
    cur.execute("SELECT COUNT(*) FROM daily_metrics")
    check("jumlah hari teramati", len(daily), cur.fetchone()[0])
    # transaksi per hari harus sama dengan COUNT(DISTINCT order_id) dari sales
    exp_tx_per_day = {
        str(d): n
        for d, n in tx.assign(Date=pd.to_datetime(tx["Date"]).dt.date)
        .groupby("Date")["Order ID"]
        .nunique()
        .items()
    }
    cur.execute(
        "SELECT metric_date, transactions FROM daily_metrics ORDER BY metric_date"
    )
    act_tx_per_day = {str(d): n for d, n in cur.fetchall()}
    mismatch_days = [
        d for d in exp_tx_per_day if exp_tx_per_day[d] != act_tx_per_day.get(d)
    ]
    check("transaksi/hari sales vs daily_metrics", [], mismatch_days)
    # revenue harian total harus = revenue total sales
    cur.execute("SELECT SUM(revenue) FROM daily_metrics")
    check(
        "total revenue daily_metrics vs sales",
        money(tx["Revenue"].sum()),
        money(cur.fetchone()[0]),
    )

    print("== 10. Anomaly ==")
    cur.execute("SELECT COUNT(*) FROM daily_metrics WHERE is_anomaly")
    check(
        "jumlah hari anomaly (vs sales_anomalies.csv)",
        len(anomalies_csv),
        cur.fetchone()[0],
    )

    conn.close()

    print()
    if failures:
        print(f"VALIDASI GAGAL: {failures} mismatch")
        sys.exit(1)
    print("SEMUA VALIDASI PASS - PostgreSQL konsisten dengan hasil notebook")


if __name__ == "__main__":
    main()

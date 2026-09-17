"""Query analitik untuk BizIntel AI.

Semua query parameterized dan hanya membaca dari PostgreSQL
(sales, daily_metrics, v_monthly_metrics) - PostgreSQL adalah source of truth.
"""

from datetime import date

import psycopg2.extras


def _rows_to_dicts(cur) -> list[dict]:
    """Ubah hasil query (RealDictCursor) menjadi list of dict."""
    return [dict(row) for row in cur.fetchall()]


def get_kpi(conn) -> dict:
    query = """
        SELECT
            COALESCE(SUM(revenue), 0)                                   AS total_revenue,
            COALESCE(SUM(quantity), 0)                                  AS total_quantity,
            COUNT(DISTINCT order_id)                                     AS total_transactions,
            CASE WHEN COUNT(DISTINCT order_id) > 0
                 THEN SUM(revenue) / COUNT(DISTINCT order_id)
                 ELSE 0 END                                              AS average_transaction_value,
            MIN(sale_date)                                               AS date_range_start,
            MAX(sale_date)                                               AS date_range_end
        FROM sales
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        row = dict(cur.fetchone())
    # NUMERIC -> float untuk respons JSON
    for key in ("total_revenue", "total_quantity", "average_transaction_value"):
        row[key] = round(float(row[key]), 2)
    return row


def get_daily_revenue(
    conn, start_date: date | None = None, end_date: date | None = None
) -> list[dict]:
    query = """
        SELECT metric_date AS date,
               revenue,
               quantity,
               transactions
        FROM daily_metrics
        WHERE (%(start_date)s IS NULL OR metric_date >= %(start_date)s)
          AND (%(end_date)s IS NULL OR metric_date <= %(end_date)s)
        ORDER BY metric_date
    """
    params = {"start_date": start_date, "end_date": end_date}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        rows = _rows_to_dicts(cur)
    for row in rows:
        row["revenue"] = round(float(row["revenue"]), 2)
        row["quantity"] = round(float(row["quantity"]), 2)
    return rows


def get_product_revenue(conn) -> list[dict]:
    query = """
        SELECT product,
               SUM(revenue)  AS revenue,
               SUM(quantity) AS quantity
        FROM sales
        GROUP BY product
        ORDER BY revenue DESC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        rows = _rows_to_dicts(cur)
    for row in rows:
        row["revenue"] = round(float(row["revenue"]), 2)
        row["quantity"] = round(float(row["quantity"]), 2)
    return rows


def get_city_revenue(conn) -> list[dict]:
    query = """
        SELECT city,
               SUM(revenue)  AS revenue,
               SUM(quantity) AS quantity
        FROM sales
        GROUP BY city
        ORDER BY revenue DESC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        rows = _rows_to_dicts(cur)
    for row in rows:
        row["revenue"] = round(float(row["revenue"]), 2)
        row["quantity"] = round(float(row["quantity"]), 2)
    return rows


def get_monthly_revenue(conn) -> list[dict]:
    query = """
        SELECT month, revenue, quantity, transactions
        FROM v_monthly_metrics
        ORDER BY month
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        rows = _rows_to_dicts(cur)
    for row in rows:
        row["revenue"] = round(float(row["revenue"]), 2)
        row["quantity"] = round(float(row["quantity"]), 2)
    return rows


def get_anomalies(conn) -> list[dict]:
    query = """
        SELECT metric_date          AS date,
               revenue,
               quantity,
               transactions,
               anomaly_score_label,
               is_anomaly
        FROM daily_metrics
        WHERE is_anomaly
        ORDER BY metric_date
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        rows = _rows_to_dicts(cur)
    for row in rows:
        row["revenue"] = round(float(row["revenue"]), 2)
        row["quantity"] = round(float(row["quantity"]), 2)
    return rows

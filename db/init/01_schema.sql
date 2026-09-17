-- ============================================================
-- BizIntel AI - PostgreSQL Schema
-- Dibuat berdasarkan INSPEKSI kolom aktual dari:
--   - data/processed/cleaned_transactions.csv  (254 baris, 10 kolom)
--   - data/processed/daily_sales.csv           (53 baris, 6 kolom)
-- Hasil notebook: EDA + forecasting (Linear Regression) + anomaly (IsolationForest)
--
-- Tahap ini hanya membuat tabel yang benar-benar dipakai sekarang:
--   sales         <- cleaned_transactions.csv (fakta transaksi, sumber kebenaran)
--   daily_metrics <- daily_sales.csv (agregat harian + label anomaly ML)
--   v_monthly_metrics <- view agregat bulanan (menggantikan monthly_revenue.csv)
--
-- Tabel berikut DITUNDA ke tahap berikutnya (jangan dibuat kosong-koosong):
--   products, forecasts, documents, reports, agent_runs
--   - products  : data asli hanya punya nama produk (5 nilai), belum ada atribut
--   - forecasts : menunggu service forecasting yang memakai model .joblib
--   - documents/reports/agent_runs : tahap RAG/agent (dilarang di tahap ini)
-- ============================================================

-- ------------------------------------------------------------
-- 1) FAKTA TRANSAKSI
-- Sumber: cleaned_transactions.csv
-- Kolom asli: Order ID, Date, Product, Price, Quantity,
--             Purchase Type, Payment Method, Manager, City, Revenue
-- Catatan tipe:
--   - Quantity bisa pecahan (mis. 573.07) sesuai data asli -> NUMERIC
--   - Revenue = Price * Quantity -> 4 desimal (NUMERIC(14,4))
--   - order_id UNIQUE: hasil inspect 254 baris = 254 order id unik
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sales (
    sale_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       BIGINT  NOT NULL UNIQUE,
    sale_date      DATE    NOT NULL,
    product        VARCHAR(100) NOT NULL,
    price          NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    quantity       NUMERIC(12,2) NOT NULL CHECK (quantity >= 0),
    purchase_type  VARCHAR(50)  NOT NULL,
    payment_method VARCHAR(50)  NOT NULL,
    manager        VARCHAR(100) NOT NULL,
    city           VARCHAR(100) NOT NULL,
    revenue        NUMERIC(14,4) NOT NULL CHECK (revenue >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sales_sale_date ON sales (sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_product   ON sales (product);
CREATE INDEX IF NOT EXISTS idx_sales_city      ON sales (city);
CREATE INDEX IF NOT EXISTS idx_sales_manager   ON sales (manager);

-- ------------------------------------------------------------
-- 2) METRIK HARIAN + LABEL ANOMALY ML
-- Sumber: daily_sales.csv (output notebook: groupby Date + IsolationForest)
-- Kolom asli: Date, Revenue, Quantity, Transactions,
--             anomaly_score_label, Is_Anomaly
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_metrics (
    metric_date         DATE PRIMARY KEY,
    revenue             NUMERIC(14,4) NOT NULL,
    quantity            NUMERIC(14,2) NOT NULL,
    transactions        INTEGER NOT NULL CHECK (transactions >= 0),
    anomaly_score_label INTEGER,              -- IsolationForest: -1 = anomaly, 1 = normal
    is_anomaly          BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_anomaly ON daily_metrics (is_anomaly);

-- ------------------------------------------------------------
-- 3) VIEW AGREGAT BULANAN
-- Pengganti monthly_revenue.csv -> dihitung on-the-fly dari daily_metrics,
-- sehingga selalu konsisten dengan data transaksi di DB.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_monthly_metrics AS
SELECT
    date_trunc('month', metric_date)::date AS month,
    SUM(revenue)::NUMERIC(14,4)            AS revenue,
    SUM(quantity)::NUMERIC(14,2)           AS quantity,
    SUM(transactions)                      AS transactions
FROM daily_metrics
GROUP BY 1
ORDER BY 1;

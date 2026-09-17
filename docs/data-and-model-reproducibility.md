# Data & Model Reproducibility — BizIntel AI

Dokumen ini menjelaskan dari mana setiap angka di dashboard berasal dan
bagaimana seluruh pipeline dapat direproduksi ulang dari nol. Semua nilai di
bawah adalah **hasil pengukuran aktual** dari artefak di repo (bukan target /
klaim aspiratif). Batasan dan hal yang TIDAK bisa diklaim dari data ini
dibahas eksplisit di bagian akhir.

## 1. Dataset

| Fakta | Nilai terukur |
|---|---|
| Sumber | Dataset publik Kaggle `rohitgrewal/restaurant-sales-data` (notebook EDA + forecasting + anomaly di `notebooks/`) |
| Transaksi (`sales`) | 254 baris |
| Hari observasi (`daily_metrics`) | 53 hari: 2022-11-07 → 2022-12-29 |
| Total revenue | €769.515,86 |
| Total quantity | 116.995,31 |
| Rata-rata nilai transaksi | €3.029,59 |
| Produk unik | 5 (Beverages, Burgers, Chicken Sandwiches, Fries, Sides & Other) |
| Kota unik | 5 (Berlin, Lisbon, London, Madrid, Paris) |
| Top product | Burgers — €376.999,81 |
| Top city | Lisbon — €241.714,12 |
| Revenue bulanan | 2022-11: €332.114,66 · 2022-12: €437.401,20 |
| Hari anomaly ter-flag | 8 dari 53 |

Mata uang data adalah EUR; dashboard memformatnya dengan locale id-ID
(€769.515,86) — format tampilan saja, angka tidak diubah.

### Alur data (reproduksi dari nol)

```
Kaggle CSV
  └─ notebooks/ (EDA + cleaning)            → data/processed/*.csv
       ├─ cleaned_transactions.csv  (254)   → tabel sales
       ├─ daily_sales.csv           (53, + label anomaly) → daily_metrics
       └─ monthly_revenue.csv       (usang; view v_monthly_metrics dipakai)
```

1. `data/processed/` adalah output notebook — source of truth analitik.
2. `docker compose up` pada volume baru otomatis: buat schema
   (`db/init/01_schema.sql`, idempotent) → import CSV
   (`scripts/import_data.py`, TRUNCATE+insert, idempotent) → ingest RAG.
3. Manual: `python3 scripts/import_data.py` lalu
   `python3 scripts/validate_db.py` (memverifikasi 254/53/769515.86/…).

## 2. Eksperimen ML — forecasting revenue

Perbandingan model pada test split notebook
(`data/ml_outputs/revenue_model_metrics.csv`, nilai aktual):

| Model | MAE | RMSE | MAPE |
|---|---|---|---|
| **Linear Regression (dipilih)** | **610,15** | **743,92** | **3,64%** |
| Random Forest | 1.373,23 | 1.550,74 | 8,15% |
| XGBoost | 1.529,68 | 1.787,81 | 9,05% |

- Fitur (7): `day_of_week, day_of_month, month, is_weekend, lag_1, lag_7,
  rolling_mean_7` (feature engineering notebook cell 30).
- Artefak produksi `backend/models/revenue_forecasting_linear_regression.joblib`
  direplikasi **exact** oleh `scripts/export_forecast_model.py` — prediksi
  identik dengan `revenue_test_predictions.csv` hingga ~1e-10. API tidak
  pernah retraining; artefak dimuat + divalidasi terhadap
  `forecast_features.joblib` (mismatch fitur → 503 `forecast_model_unavailable`,
  tanpa angka fallback).
- Forecast deterministik (recursive multi-step dari hari data terakhir):
  days=3 → 16533,84 / 15924,91 / **-9007,63**; days=7 melanjutkan negatif.
  **Nilai negatif TIDAK di-clamp** — itu perilaku asli model saat
  meng-ekstrapolasi transisi bulan di luar rentang latih (lihat §5).

## 3. Deteksi anomaly

- IsolationForest pada `daily_metrics` (notebook) → 8 hari ber-flag
  (`is_anomaly`, score -1), disajikan apa adanya di dashboard
  (`data/ml_outputs/sales_anomalies.csv`).
- **Label exploratory — tidak ada ground truth.** "Anomaly" berarti hari
  yang secara statistik menyimpang dari pola revenue/quantity/transactions,
  bukan bukti fraud, kebocoran kas, atau kesalahan pencatatan.

## 4. RAG knowledge base

- 5 dokumen kebijakan sintetis (`data/knowledge/*.md`) — **konten demo**,
  bukan kebijakan restoran nyata.
- Chunking deterministik (700 karakter, overlap 80) → **21 chunk**;
  embedding lokal ONNX all-MiniLM-L6-v2 (unduh sekali saat build image);
  ChromaDB cosine, `MIN_SIMILARITY=0,30` (di bawah itu hasil dibuang).
- Ingest idempoten (`python3 -m app.rag.ingest` dari `backend/`); ID chunk
  deterministik (`nama-file::chunkNNN`) sehingga koleksi dapat dibangun ulang
  identik kapan pun.

## 5. Batasan eksplisit (jangan melebihi klaim ini)

1. **Dataset kecil**: 254 transaksi / 53 hari. Semua angka agregat stabil
   untuk demo, tetapi bukan basis generalisasi bisnis.
2. **Rentang sempit & satu musim**: hanya Nov–Des 2022. Efek musiman lain
   (Q1, liburan lain) tidak terwakili.
3. **Batas ekstrapolasi model**: recursive forecast di luar rentang latih
   menyimpang — terbukti prediksi negatif saat bulan bergeser 12→1.
   Horizon pendek (±3 hari) aman; UI menampilkan nilai apa adanya + catatan
   limitasi, tanpa clamping.
4. **Anomaly bukan bukti fraud** — label statistik tanpa ground truth (§3).
5. **Dokumen RAG sintetis** — dipakai untuk mendemonstrasikan grounding &
   citation, bukan kebijakan nyata.
6. **AI Assistant butuh langganan GLM-5.3** (API Anthropic-compatible
   BigModel/Z.ai). Tanpa kredensial, dashboard analytics + forecast + anomaly
   tetap berfungsi penuh; hanya `/api/chat` yang 503 `llm_not_configured`.
7. **Evaluasi agent** (`docs/agent-phase5.md`): deterministik + live run;
   hasil live bervariasi antar run (18–22/23 teramati) — angka di README
   adalah snapshot run terakhir yang tercatat di
   `data/evaluation/latest_evaluation.json`.

## 6. Ringkasan perintah reproduksi

```bash
# Full stack (volume baru otomatis schema+data+RAG)
docker compose up --build

# Hanya data/schema ke PostgreSQL yang sudah jalan
python3 scripts/import_data.py && python3 scripts/validate_db.py

# Artefak model forecast (replikasi exact notebook)
python3 scripts/export_forecast_model.py

# Vector store RAG (deterministik)
cd backend && python3 -m app.rag.ingest

# Evaluasi agent (tanpa LLM / dengan LLM)
python3 scripts/evaluate_agent.py --mode deterministic
python3 scripts/evaluate_agent.py --mode live
```

# AI Agent — Phase 2: ML Analytics Tools

Ditambahkan 2026-09-16, di atas Phase 1 (`docs/agent-phase1.md`). Menambahkan
kemampuan ML ke agent yang sama dengan membungkus **service yang sudah ada** —
tanpa retraining, tanpa model baru, tanpa mengubah notebook/dataset/schema.

## Yang ditambahkan

1 tool ML baru: **`get_revenue_forecast(days: int = 3)`** (`backend/app/agent/tools.py`).
Tool `get_anomalies()` Phase 1 **tetap** — sudah bersumber `daily_metrics`
(label IsolationForest hasil notebook), tidak ada deteksi anomaly kedua dan
tidak di-rewrite.

## Artefak forecast yang dipakai

- `backend/models/revenue_forecasting_linear_regression.joblib`
  (LinearRegression 7 fitur time-series; terverifikasi mereproduksi
  `revenue_test_predictions.csv`).
- `backend/models/forecast_features.joblib` (urutan fitur).
- Path artefak = konstanta `forecast_service.MODEL_PATH` — **bukan** input
  user/LLM. Tidak ada parameter `path`/`file` di tool manapun.

Tool hanya memanggil `forecast_service.forecast_revenue(days)` — logic
recursive forecasting, validasi artefak, dan pembacaan riwayat
`daily_metrics` **tidak diduplikasi**. Kontrak parameter mengikuti endpoint
`GET /api/forecast/revenue`: `days` 1–30, default tool 3 (horizon pendek).

## Tools lengkap (Phase 1 + 2)

| Tool | Parameter | Sumber | Jenis |
|---|---|---|---|
| `get_kpi()` | — | agregat `sales` | SQL |
| `get_revenue_by_period(start_date, end_date)` | opsional `YYYY-MM-DD` | `daily_metrics` | SQL |
| `get_revenue_by_product()` | — | `sales` | SQL |
| `get_revenue_by_city()` | — | `sales` | SQL |
| `get_monthly_revenue()` | — | `v_monthly_metrics` | SQL |
| `get_anomalies()` | — | `daily_metrics` (label notebook) | SQL |
| `get_revenue_forecast(days=3)` | `days` 1–30 | artefak ML + `daily_metrics` | **ML** |

## Alur agent (tetap satu graph sederhana)

```
POST /api/chat → agent (LLM) → tools → agent → … → END → {answer, tools_used}
```

Pemilihan tool (terverifikasi live):

| Pertanyaan | Tool |
|---|---|
| Prediksi revenue 3 hari ke depan | `get_revenue_forecast(days=3)` |
| Forecast revenue minggu depan | `get_revenue_forecast(days=7)` |
| Ada anomaly? / kapan & berapa revenue hari anomaly? | `get_anomalies` |
| Berapa total revenue? | `get_kpi` |
| Produk revenue terbesar? | `get_revenue_by_product` |
| Bandingkan November dan Desember | `get_monthly_revenue` |
| Kondisi revenue + forecast ke depan | `get_kpi` + `get_revenue_forecast` |

## Grounding rules ML (system prompt)

- Hasil forecast = **prediksi model**, bukan fakta aktual — wajib frasa
  "Model memprediksi…" / "Forecast model memperkirakan…".
- Angka prediksi dikutip persis dari tool; dilarang mengubah/membulatkan
  sendiri/mengarang.
- Jika artefak gagal (`forecast_model_unavailable`): sampaikan bahwa
  forecast tidak tersedia — **tanpa angka fallback**.

## Known limitation (DIBIARKAN, tidak di-"perbaiki")

Forecast recursive bisa **negatif** setelah 2022-12-31 karena training hanya
mencakup Nov–Des (fitur `month` diekstrapolasi ke bulan 1). Kebijakan:
nilai dikembalikan & dikutip **apa adanya** — tidak di-clamp `max(x, 0)`,
tidak mengubah koefisien, tidak retrain, tidak workaround. Default 3 hari
meminimalkan paparan; jika user meminta horizon panjang, agent menjelaskan
nilai negatif itu output model di luar pola data training.

Contoh nilai aktual (deterministik, days=7):
`16533.84, 15924.91, -9007.63, -10474.2, -11961.51, -13709.57, -15150.81`.

## Security model (tidak berubah dari Phase 1)

- Tanpa `execute_sql`/SQL mentah; tanpa eksekusi Python arbitrer.
- Tanpa path model/file dari input user/LLM.
- Parameter tool tervalidasi (`days` 1–30; tanggal `YYYY-MM-DD`); parameter
  di luar schema diabaikan.
- Error aman: kegagalan DB/artefak → pesan generik ke LLM+user, detail hanya
  di log server; tanpa bocor kredensial.

## Testing

`backend/tests/test_agent_ml.py` (16 test deterministik): kontrak days 3/7,
invalid 0/31/-1/100, default 3, artefak benar (nama+7 fitur+nilai), struktur
prediksi, nilai negatif tidak di-clamp, error model tanpa fallback, anomaly
tetap bekerja, tool selection forecast/anomaly, kombinasi KPI+forecast,
schema parameter hanya `days`. Total suite: **47/47 PASS**.

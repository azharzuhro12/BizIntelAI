# BizIntel AI — Ringkasan Portfolio

Aplikasi business intelligence **end-to-end yang bisa dijalankan satu perintah**
(`docker compose up --build`): ETL → PostgreSQL → FastAPI → dashboard Next.js,
plus AI agent yang menjawab pertanyaan bisnis dari data nyata — bukan karangan.

> Semua angka di halaman ini hasil pengukuran aktual (lihat
> `docs/data-and-model-reproducibility.md` dan `README.md` §9).

## Elevator pitch (30 detik)

Dashboard BI penjualan restoran dengan AI Assistant ter-grounding: agent
LangGraph memilih sendiri antara 8 tool terukur — query SQL parameterized,
forecast ML dari artefak model, dan retrieval RAG kebijakan — lalu menjawab
**hanya** dari hasil tool, dengan citation sumber dan audit trail per run.
Setiap angka di UI bisa dilacak sampai ke query/model/dokumen asalnya.

## Apa yang didemonstrasikan

| Kompetensi | Buktinya di repo ini |
|---|---|
| Data engineering | ETL notebook Kaggle → dataset bersih → PostgreSQL (schema idempotent, import deterministik) |
| ML yang bertanggung jawab | Artefak LinearRegression (MAPE 3,64%) di-*serve* tanpa retraining; prediksi negatif ekstrapolasi **ditampilkan apa adanya** + catatan limitasi, bukan di-clamp |
| API design | Error kontrak eksplisit (`llm_not_configured`, `forecast_model_unavailable`) — tidak pernah fake success; health endpoint fail-safe |
| AI engineering | LangGraph single-agent, 8 tool (SQL/ML/RAG), grounding ketat, prompt injection ditolak (teruji) |
| RAG | ChromaDB + embedding ONNX lokal (tanpa API embedding berbayar), citation `[file.md]` diverifikasi dari metadata retrieval aktual |
| Evaluasi sistem AI | Evaluator **deterministik tanpa LLM-as-a-judge**: tool selection, parsing angka multi-format, groundedness, Hit@k — hasil live dilaporkan apa adanya (18–22/23 antar run) |
| Frontend | Next.js 16 + React 19, state loading/error/empty per widget, kembar tabel aksesibilitas tiap chart, dark mode |
| Testing | 226 pytest + 70 vitest + tsc/eslint bersih + evaluasi agent deterministik 21/21 ground-truth |
| Productionization | Docker Compose 3 service, startup checks fail-closed (DB→schema→data→RAG), rahasia tidak dibake ke image, frontend non-root |

## Angka kunci

- **Data**: 254 transaksi, 53 hari (Nov–Des 2022), total revenue €769.515,86
- **Model**: LinearRegression MAPE 3,64% (vs RF 8,15%, XGBoost 9,05%)
- **Agent live (23 kasus)**: tool selection 100%, groundedness 19/19,
  out-of-domain 4/4, retrieval Hit@3 9/9
- **Testing**: 226/226 pytest · 70/70 vitest · tsc & eslint bersih

## Jalankan

```bash
cp .env.example .env    # isi POSTGRES_PASSWORD
docker compose up --build
# Dashboard http://localhost:3000 · API docs http://localhost:8020/docs
```

Tanpa kredensial LLM pun dashboard penuh berfungsi; `/api/chat` gagal dengan
jelas (503 `llm_not_configured`) — desain fail-safe, bukan crash.

## Peta dokumentasi

| Dokumen | Isi |
|---|---|
| `README.md` | gambaran lengkap + quick start (EN) |
| `docs/portfolio-case-study.md` | case study engineering (EN) — keputusan + bukti |
| `docs/interview-summary.md` | ringkasan wawancara 30s/1menit + Q&A (EN) |
| `docs/phase7-productionization.md` | Docker, startup checks, security |
| `docs/phase6-frontend.md` | desain & kontrak frontend |
| `docs/agent-phase1..5.md` | evolusi agent: tool → ML → RAG → memory → evaluasi |
| `docs/data-and-model-reproducibility.md` | reproduksi data/model + batasan jujur |

## Batasan yang diakui

Dataset demo satu musim (53 hari); dokumen RAG sintetis; tanpa auth multi-user;
forecast recursive menyimpang di luar rentang latih (diungkap, bukan
disembunyikan). Daftar lengkap di `README.md` §11 — kejujuran limitasi adalah
bagian dari engineering.

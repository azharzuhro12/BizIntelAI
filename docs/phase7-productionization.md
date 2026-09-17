# Phase 7 — Productionization (Docker & pengemasan)

Dikerjakan 2026-09-16–17, di atas Phase 1–6. Target: seluruh stack
(PostgreSQL + FastAPI + Next.js) berjalan dengan **satu perintah**
`docker compose up --build`, di mesin mana pun yang punya Docker — tanpa
mengubah perilaku production code yang sudah teruji (226 pytest + 54 vitest).

## 1. Keputusan desain

1. **Image meniru layout root repo.** Context build backend = root repo;
   di dalam image dibuat `/backend`, `/data/processed`, `/data/knowledge`,
   `/scripts`, `/db/init` — persis struktur di host. Modul-modul yang menghitung
   `PROJECT_ROOT = Path(__file__).resolve().parents[N]` (path model joblib,
   dokumen RAG, dsb.) bekerja tanpa perubahan kode.
2. **Rahasia tidak pernah dibake ke image.** `.env` dikecualikan lewat
   `.dockerignore` (root dan frontend); kredensial DB & LLM masuk lewat env
   runtime docker-compose. `NEXT_PUBLIC_API_URL` adalah satu-satunya build-arg
   (memang nilai publik untuk browser).
3. **Fail-closed, bukan setengah jalan.** Entrypoint backend menjalankan
   `startup_checks.py` sebelum uvicorn: tunggu PostgreSQL (≤60 dtk) → DDL
   idempotent `/db/init/*.sql` → import dataset hanya bila `sales` kosong →
   ingest RAG ChromaDB (idempotent). Gagal di satu langkah → container exit
   non-zero, tidak ada server "hidup tapi kosong".
4. **Volume baru = reproducible otomatis.** Schema (IF NOT EXISTS) dijalankan
   ulang tiap start; dataset 254 transaksi diimpor dari CSV yang sama dengan
   notebook; ChromaDB dibangun ulang dari `data/knowledge/*.md` (chunk id
   deterministik → ingest idempotent). Tidak ada state ajaib yang harus
   disalin manual.
5. **Frontend standalone + non-root.** `next.config.ts` → `output: "standalone"`
   (tidak mengubah `npm run dev` di host); image runner multi-stage
   `node:22-alpine` dengan user khusus `nextjs`.
6. **Embedding ONNX di-pre-download saat BUILD** (all-MiniLM-L6-v2, ±79 MB ke
   cache image) supaya ingest RAG di startup deterministik dan tidak butuh
   internet saat runtime.

## 2. Struktur file yang ditambahkan

```
docker-compose.yml          # postgres + backend + frontend (healthcheck berantai)
backend/Dockerfile          # python:3.12-slim + libgomp1 (sklearn/onnxruntime)
backend/docker/entrypoint.sh        # startup_checks → uvicorn 0.0.0.0:8020
backend/docker/startup_checks.py    # DB → schema → data → RAG (fail-closed)
frontend/Dockerfile         # multi-stage deps → build → runner non-root
frontend/.dockerignore      # node_modules, .next, .env.local
.dockerignore               # .env*, chroma, __pycache__, frontend, docs, tests
.env.example                # contoh konfigurasi (tanpa nilai rahasia)
frontend/next.config.ts     # output: "standalone"
```

## 3. docker-compose.yml

| Service | Image/build | Port | Catatan |
|---|---|---|---|
| `postgres` | `postgres:17-alpine` | `${POSTGRES_PORT:-5432}` | volume `bizintel_pgdata`; `/db/init` di-mount ke initdb DDL; healthcheck `pg_isready` |
| `backend` | build root repo | `8020:8020` | env `PG*` diarahkan ke service `postgres`; healthcheck `GET /api/health`; `depends_on: postgres (healthy)` |
| `frontend` | build `./frontend` | `${FRONTEND_PORT:-3000}:3000` | build-arg `NEXT_PUBLIC_API_URL` (default `http://localhost:8020` — dilihat browser host); `depends_on: backend (healthy)` |

Kredensial LLM (`ANTHROPIC_AUTH_TOKEN`/`BASE_URL`/`MODEL`) diteruskan opsional —
tanpa nilainya dashboard & seluruh endpoint analytics tetap berfungsi penuh dan
`/api/chat` mengembalikan 503 `llm_not_configured` (kontrak yang sama dengan
jalur dev, diuji di `tests/test_agent.py`).

Port 3000 di host terpakai proyek lain? Satu baris override:
`FRONTEND_PORT=3002 BIZINTEL_CORS_ORIGINS=http://localhost:3002,http://127.0.0.1:3002 docker compose up`.

## 4. Catatan perbaikan saat build

- **Protokol embedding ChromaDB 1.5+**: langkah pre-download ONNX semula
  memanggil `DefaultEmbeddingFunction()(documents=[...])` — kwarg legacy yang
  ditolak protokol baru (`TypeError: unexpected keyword argument 'documents'`).
  Diperbaiki menjadi pemanggilan posisional `(['warmup'])` — konvensi yang sama
  dengan jalur internal ChromaDB (kode produksi `app/rag/embeddings.py` tidak
  tersentuh karena hanya menyerahkan embedding function ke ChromaDB).

## 5. Hasil verifikasi (2026-09-17, `docker compose up` di host lokal)

Lingkungan: image `bizintelai-backend` 1,58 GB · `bizintelai-frontend`
328 MB · frontend di port host 3001 (3000 dipakai proyek lain), CORS diset
`http://localhost:3001,http://127.0.0.1:3001`.

| Check | Hasil |
|---|---|
| Startup checks (log container) | PostgreSQL tersedia → schema OK → dataset sudah ada (sales=254, import dilewati) → **RAG ingest OK (21 chunk)** → uvicorn 0.0.0.0:8020 |
| Healthcheck compose | postgres healthy → backend healthy (GET /api/health 200) → frontend start |
| `GET /api/health` | `status ok`, `database connected`, sales 254 / daily_metrics 53 |
| `GET /api/analytics/kpi` | total_revenue **769515.86** · 254 transaksi · AOV 3029.59 · rentang 2022-11-07→2022-12-29 (identik baseline host) |
| `/revenue` · `/anomalies` · `/products` · `/cities` · `/monthly` | 53 hari · 8 anomaly · top Burgers 376999.81 · top Lisbon 241714.12 · Nov 332114.66 / Des 437401.20 — semua identik baseline |
| `GET /api/forecast/revenue?days=3` | 16533.84 · 15924.91 · **-9007.63** — persis nilai deterministik baseline host (prediksi negatif month-extrapolation tetap apa adanya) |
| `POST /api/rag/search` ("kebijakan promo diskon") | top-1 `promotion_policy.md` score 0.6042, metadata citation utuh (ingest in-container dari `/data/knowledge`) |
| `POST /api/chat` (LLM live glm-5.3 via relay) | pertanyaan gabungan SQL+RAG → `tools_used [get_kpi, search_business_knowledge]`, angka grounded 769.515,86, citation `[promotion_policy.md]` format kontrak, isi kebijakan (diskon maks 30%) akurat |
| `GET /api/agent/runs/{session_id}` | run tercatat: SUCCESS · latency 15.274 ms · model glm-5.3 |
| CORS | preflight origin :3001 → 200 + `access-control-allow-origin` benar; origin asing → tanpa header |
| Frontend | HTTP 200 di :3001; screenshot headless: 7 widget render penuh (hero, forecast dashed + badge, anomaly, produk, kota, bulanan, chat) dengan angka live |
| Rahasia | `.env` tidak ada di kedua image; metadata image backend hanya env base Python (0 var token/password); kredensial DB & LLM hanya env runtime container; frontend jalan sebagai user non-root `nextjs`, 0 var sensitif |
| Suite pasca-perubahan | pytest backend **226/226** · vitest **54/54** · tsc/eslint bersih (di host, sebelum build) |

Dua bug build yang ditemukan & diperbaiki saat verifikasi (di luar warmup
ChromaDB §4):

1. `startup_checks.py` gagal `ModuleNotFoundError: No module named 'app'` —
   skrip dipanggil lewat path absolut sehingga `sys.path[0]` = direktori
   skrip, bukan CWD `/backend`. Fix: `sys.path.insert` eksplisit ke
   `/backend` (kode aplikasi tidak tersentuh).
2. Log `RAG ingest OK (None chunk)` — startup check membaca key `ingested`,
   padahal kontrak `ingest_knowledge()` sukses memakai `chunks`. Fix satu
   baris; kini tercetak `21 chunk`.

Catatan jujur: jalur "volume benar-benar kosong → import otomatis 254 baris"
belum diuji ulang sesi ini (volume dev sudah berisi data; wrapper startup
memanggil `scripts/import_data.py` yang sama yang sudah tervalidasi di host).
Path tersebut identik kode, tapi statusnya untested-in-this-run, bukan
terverifikasi.

## 6. Yang TIDAK dikerjakan (sesuai batasan)

Tidak ada perubahan: logika agent, tool, RAG, model ML, schema, dan kontrak
API. Deployment cloud/publik, TLS, auth multi-user, dan CI/CD di luar scope
fase ini (aplikasi demo lokal/portfolio).

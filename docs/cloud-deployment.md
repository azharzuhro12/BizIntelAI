# BizIntel AI — Cloud Deployment Guide (Free Tier)

Target topology for the portfolio/demo deployment — **no code changes required beyond two deployment-compatibility fixes** (Render `PORT` binding, and `validate_db.py` honoring `PG*` env vars):

```
GitHub (repo) → Supabase PostgreSQL (infrastruktur PG murni, TANPA Supabase SDK)
             → Vercel FastAPI backend (Python 3.13 serverless, project "bizintelai")
             → Vercel Next.js frontend (project "bizintelai-frontend")
```

> **STATUS LIVE (2026-09-17):** kedua komponen berjalan di Vercel (Hobby) —
> API `https://bizintelai.vercel.app` · dashboard `https://bizintelai-frontend.vercel.app`.
> Backend di Vercel mem-bundle tanpa chromadb (batas 500 MB/function) sehingga
> `/api/rag` fail-soft — lihat §3. Jalur Render (§3-alt, Docker + RAG penuh)
> tetap tersedia sebagai alternatif.

Semua komponen aplikasi tidak berubah: psycopg2 tetap dipakai (Supabase hanya menggantikan "mesin" PostgreSQL), LangGraph/RAG/ML/schema/API kontrak utuh. Panduan langkah-manual (akun dibuat oleh Anda, bukan otomatis).

---

## 1. Supabase — manual setup checklist

Supabase dipakai **hanya sebagai PostgreSQL terkelola**. Tidak ada perubahan schema yang diperlukan: `db/init/*.sql` adalah SQL standar (idempotent `IF NOT EXISTS`, identity, JSONB, `CREATE OR REPLACE VIEW`) dan kompatibel penuh dengan PostgreSQL Supabase. Tabel yang terbentuk: `sales`, `daily_metrics`, `agent_messages`, `agent_runs`, view `v_monthly_metrics`.

1. **Buat project** — https://supabase.com/dashboard → *New project*. Pilih region terdekat (mis. Singapore). Simpan database password yang Anda buat (jangan commit).
2. **Ambil connection string** — Dashboard → *Connect* (atau Project Settings → Database). Ada tiga mode; **pakai Session Pooler** untuk Render dan validasi lokal:
   - **Session pooler** (dipakai): `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres` — IPv4, semantik session penuh (aman untuk psycopg2 per-request).
   - Transaction pooler (port 6543): cadangan bila batas koneksi tersentuh; hindari dulu (mode transaksi membatasi fitur session).
   - Direct (`db.<ref>.supabase.com:5432`): **IPv6-only** di plan free — tidak reliable dari Render free; jangan dipakai.
3. **Terapkan schema** — Dashboard → *SQL Editor* → *New query*: paste isi `db/init/01_schema.sql`, jalankan; ulangi untuk `db/init/02_agent.sql`. (Idempotent — aman diulang.)
4. **Import dataset** — dari repo lokal (lihat §2 untuk pola env):
   ```bash
   export PGHOST="aws-0-<region>.pooler.supabase.com" PGPORT=5432 \
          PGUSER="postgres.<ref>" PGPASSWORD="<password>" \
          PGDATABASE=postgres PGSSLMODE=require
   python3 scripts/import_data.py
   ```
5. **Validasi** — angka yang HARUS tercapai (data asli, bukan buatan):
   ```bash
   python3 scripts/validate_db.py
   # SEMUA VALIDASI PASS: 254 sales, 53 daily, revenue 769.515,86,
   # quantity 116.995,31, 8 hari anomaly
   ```

Catatan: entrypoint container juga menjalankan DDL idempotent + import-hanya-jika-kosong saat start, jadi langkah 3–4 boleh dilewati bila Anda biarkan Render yang menyediakan DB saat boot pertama. Menjalankan manual tetap disarankan agar database pasti siap sebelum backend live.

Free tier: project Supabase free berhenti sementara (pause) setelah ~1 minggu tanpa aktivitas — cukup di-unpause dari dashboard.

## 2. Local backend → Supabase validation

Backend lokal diarahkan ke Supabase **hanya via environment variable** (tidak ada kredensial di kode/`.env`). `app/db.py` prioritas: `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE` (env) > `POSTGRES_*` (file `.env` lokal). `PGSSLMODE` dibaca native oleh libpq/psycopg2.

```bash
export PGHOST=... PGPORT=5432 PGUSER=... PGPASSWORD=... PGDATABASE=postgres PGSSLMODE=require
python3 scripts/validate_db.py
cd backend && python3 -m uvicorn app.main:app --reload --port 8020
```

(Dari root repo module path-nya `app.main:app` karena paket `app` ada di `backend/` — bukan `backend.app.main:app`.)

Lalu uji:

| Endpoint | Expected |
|---|---|
| `GET /api/health` | `{"status":"ok","database":"connected","tables":{"sales":254,"daily_metrics":53}}` |
| `GET /api/analytics/kpi` | total_revenue 769515.86 · total_quantity 116995.31 · 254 transaksi |
| `GET /api/analytics/products` | item pertama Burgers 376999.81 |
| `GET /api/analytics/cities` | item pertama Lisbon 241714.12 |
| `GET /api/analytics/monthly` | 2022-11: 332114.66 · 2022-12: 437401.20 |
| `GET /api/forecast/revenue?days=1` | model Linear Regression, prediksi 16533.84 |
| `POST /api/chat` | hanya bila `ANTHROPIC_*` tersedia di env; jawab grounded + `tools_used` |

Mekanisme ini sudah diverifikasi lokal (backend dijalankan murni dengan `PG*` env — semua endpoint PASS; `/api/chat` diverifikasi grounded end-to-end).

## 3. Vercel — backend (LIVE)

Dipakai sekarang. Satu repo, project terpisah untuk backend (root) & frontend (`frontend/`).

| Komponen | Isi |
|---|---|
| Entrypoint | `api/index.py` — re-export `app` dari `backend.app.main` (Vercel hanya memindai functions di `api/`; uvicorn lokal/Docker tidak berubah) |
| `vercel.json` | `framework: "fastapi"` eksplisit (routing catch-all — TANPA ini hanya `/api` & `/api/index` yang ter-route), `fluid`, `regions: ["sin1"]`, `functions["api/index.py"]` maxDuration 60 |
| Deps | `requirements.txt` root = **generated** oleh `scripts/sync-requirements.sh` dari `backend/requirements.txt` (satu sumber kebenaran). Self-contained (parser Vercel tanpa `-r`) + filter `chromadb`/`pytest`/`uvicorn[standard]` demi batas bundle 500 MB |
| RAG | **fail-soft** di serverless: `backend/app/rag/vectorstore.py` & `embeddings.py` guard `ImportError`; `/api/rag` dan grounding agent mengembalikan pesan terkontrol, bukan 500. RAG penuh → jalur Render (§3-alt) |
| Python | `.python-version` = 3.13 |
| Env vars (project settings) | `PG*` (Supabase session pooler), `PGSSLMODE=require`, `BIZINTEL_CORS_ORIGINS`, `ANTHROPIC_AUTH_TOKEN`/`BASE_URL`/`MODEL` |
| Deploy | `cd <repo-root> && npx vercel deploy --prod --yes` (CLI; ubah env var → wajib redeploy agar terpakai) |

Catatan pitfall yang sudah dijawab (jangan diulang): `functions` pattern harus menunjuk file di `api/`; pyproject root tanpa tabel `[project]` membuat `uv lock` gagal; deteksi framework perlu literal `fastapi` di requirements (flag `-r` tidak dipindai); deployment protection project baru default ON (matikan di Settings → Deployment Protection).

## 3-alt. Render — backend alternatif (Docker, RAG penuh)

Konfigurasi tersedia dua cara — **Blueprint** (repo sudah punya `render.yaml`) atau manual:

**Via Blueprint (disarankan):** Render Dashboard → *New* → *Blueprint* → pilih repo. Render membaca `render.yaml`; semua env var kredensial ditandai `sync: false` → Anda mengisi nilainya di dashboard saat deploy (tidak pernah tersimpan di repo).

**Manual (dashboard):**

| Setting | Nilai |
|---|---|
| Runtime | **Docker** |
| Dockerfile Path | `./backend/Dockerfile` |
| Docker Build Context Directory | repo root (`./`) — Dockerfile me-COPY `backend/`, `data/`, `scripts/`, `db/` dari root |
| Instance type | Free |
| Health Check Path | `/api/health` |
| Port | tidak perlu diset — entrypoint binding `0.0.0.0:${PORT:-8020}` (Render menyuntik `PORT`) |

**Environment variables (dashboard, jangan pernah di-commit):**

| Var | Nilai |
|---|---|
| `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` / `PGDATABASE` | kredensial Supabase session pooler (§1.2) |
| `PGSSLMODE` | `require` |
| `BIZINTEL_CORS_ORIGINS` | `https://<nama-vercel>.vercel.app` (diisi setelah langkah Vercel; awal deploy boleh dummy lalu update + redeploy) |
| `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` | kredensial LLM GLM (opsional; tanpa ini hanya `/api/chat` yang 503) |

Saat boot pertama, entrypoint container otomatis: tunggu PG → DDL idempotent → import dataset bila `sales` kosong → ingest RAG → uvicorn. Fail-closed: jika DB tidak terjangkau, container gagal start (tidak ada server setengah jalan).

Free tier: service **tidur setelah ±15 menit tanpa traffic** → request pertama berikutnya menunggu cold start (±50–60 s). RAM 512 MB — cukup untuk stack ini, tapi ini batas paling ketat dari seluruh topologi.

## 4. Vercel — frontend

Tidak ada perubahan kode: `frontend/lib/api.ts` memakai `process.env.NEXT_PUBLIC_API_URL` dengan fallback dev `http://127.0.0.1:8020` (fallback itu tidak pernah aktif di production bila env diset). Tidak ada localhost yang di-hardcode di tempat lain.

| Setting | Nilai |
|---|---|
| Project | `bizintelai-frontend` (LIVE: `https://bizintelai-frontend.vercel.app`) |
| Root Directory | `frontend` |
| Framework | Next.js — eksplisit via `frontend/vercel.json` (`"framework": "nextjs"`) |
| Environment Variable | `NEXT_PUBLIC_API_URL = https://bizintelai.vercel.app` |
| Deployment Protection | **Disabled** (default project baru = Vercel Authentication; tanpa ini publik dapat 404/redirect login) |
| Build / Output | default (`npm run build`; standalone tidak dipakai di Vercel, next.config aman diabaikan) |

`NEXT_PUBLIC_API_URL` di-inline ke bundle client saat **build** → set env var **sebelum** deploy pertama (atau setelah menambahkannya, trigger *Redeploy*).

Pitfall yang sudah dijawab: project yang dibuat via `vercel project add`/CLI (bukan import Git) memiliki `framework: null` di setting, dan deploy CLI **tidak** melakukan auto-detect dari `package.json` — build sukses tapi deployment tanpa route (semua path 404 meski `Deployment Protection` sudah dimatikan). Solusi: `frontend/vercel.json` dengan `"framework": "nextjs"` eksplisit, lalu redeploy (terverifikasi: route `/` static + URL API ter-bake di chunk client).

## 5. ChromaDB / RAG di disk ephemeral

Realita Render free: filesystem container ephemeral — `data/chroma/` hilang tiap instance baru. Arsitektur saat ini **sudah dirancang untuk itu**, tanpa perubahan:

- entrypoint selalu menjalankan `ingest_rag()` saat boot — rebuild index dari 5 dokumen sintetis yang di-bake ke image (`/data/knowledge`)
- chunking deterministik (700/80) → index identik setiap kali; 21 chunk
- model embedding ONNX (all-MiniLM-L6-v2) sudah di-pre-download **saat build image** → ingest startup tidak butuh internet
- biayanya hanya beberapa detik tambahan per cold start; perilaku retrieval tidak berubah (MIN_SIMILARITY 0.30, cosine)

Jadi: **tidak ada paid vector DB, tidak ada perubahan RAG** — ephemeral disk diakui secara eksplisit dan ditangani oleh regenerasi deterministik saat startup.

## 6. Final deployment checklist (urutan wajib)

| # | Langkah | Manual (Anda) | Otomatis (Claude Code) | Expected | Jangan di-commit |
|---|---|---|---|---|---|
| 1 | **GitHub** | buat repo, `git remote add`, push | sudah: hygiene tervalidasi (140 file bersih) | repo live, `.env` tak terkirim | `.env`, `data/chroma/`, `latest_*.json` |
| 2 | **Supabase** | §1 langkah 1–2 (akun + project + conn string) | — | conn string session pooler di tangan | password DB di mana pun |
| 3 | **Validasi lokal → Supabase** | §1 langkah 3–5 + §2 | perintah sudah disiapkan | `SEMUA VALIDASI PASS` + endpoint PASS | export `PG*` hanya di shell |
| 4 | **Render backend** | §3 (Blueprint/manual) | `render.yaml` sudah disiapkan | service build + live, log startup "semua check lolos" | semua env var bernilai |
| 5 | **Validasi API Render** | `curl https://<svc>.onrender.com/api/health` | bantu baca log bila gagal | `status ok`, tables 254/53 | — |
| 6 | **Vercel frontend** | §4 (import repo, root `frontend`, set env) | — | deploy sukses, dashboard tampil | `NEXT_PUBLIC_API_URL` berisi token? tidak — ini URL publik, boleh di dashboard saja |
| 7 | **CORS finalization** | update `BIZINTEL_CORS_ORIGINS` di Render = URL Vercel, redeploy | — | browser console tanpa error CORS | — |
| 8 | **Full browser validation** | buka dashboard, cek 9 chart + KPI | — | KPI €769.515,86; forecast dashed tampil | — |
| 9 | **AI Assistant** | tanya "Berapa total revenue?" | — | jawab grounded + chip `get_kpi` | — |
| 10 | **RAG** | tanya "Apa aturan promo?" | — | jawab policy + chip `promotion_policy.md` | — |
| 11 | **ML forecast** | tanya "Prediksi revenue 3 hari" / cek chart | — | tabel prediksi; nilai negatif TIDAK di-clamp | — |
| 12 | **Security** | cek: tab baru → tidak bisa POST cross-origin tanpa header CORS; log Render bebas kredensial | scan sudah bersih | tidak ada secret di log/repo/bundle | — |

## 7. Ringkasan environment variables

| Var | Di mana | Sumber nilai |
|---|---|---|
| `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDATABASE` | lokal (validasi) + Render | Supabase session pooler |
| `PGSSLMODE=require` | lokal + Render | tetap |
| `BIZINTEL_CORS_ORIGINS` | Render | URL produksi Vercel |
| `ANTHROPIC_AUTH_TOKEN` `ANTHROPIC_BASE_URL` `ANTHROPIC_MODEL` | lokal (chat) + Render | langganan GLM Anda |
| `NEXT_PUBLIC_API_URL` | Vercel | `https://<svc>.onrender.com` |

## 8. Caveat free tier (jujur, bukan blocker)

- Render free tidur ±15 menit idle → cold start ±1 menit (startup checks + RAG ingest).
- Render free 512 MB RAM — batas paling ketat; pantau log OOM.
- Supabase free pause ~1 minggu idle → unpause manual.
- Render free build minutes 750/bulan — image backend ±1,6 GB per build; cukup untuk demo.
- Vercel free hobby: cukup untuk dashboard statis + client fetch.

Tidak ada layanan berbayar, tidak perlu kartu kredit.

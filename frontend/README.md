# BizIntel AI — Frontend Dashboard

Dashboard BI penjualan restoran (Next.js 16 + React 19 + Tailwind 4 + Recharts)
untuk backend FastAPI di `../backend`. Menampilkan KPI periode, tren revenue
harian + prediksi model, produk/kota teratas, agregat bulanan, deteksi anomaly
(IsolationForest), dan panel AI Assistant dengan memory per sesi.

## Menjalankan (dev)

1. Pastikan PostgreSQL (`bizintel-postgres`) dan backend berjalan:

   ```bash
   cd ../backend
   python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8020
   ```

2. Frontend:

   ```bash
   npm install
   npm run dev            # default port 3000
   ```

   Port selain 3000? Backend mengizinkan origin secara eksplisit — jalankan
   backend dengan `BIZINTEL_CORS_ORIGINS="http://localhost:<port>,http://127.0.0.1:<port>"`.
   Base URL API bisa dioverride `NEXT_PUBLIC_API_URL` (default
   `http://127.0.0.1:8020`) lewat `.env.local`.

## Perintah

| Perintah | Fungsi |
|---|---|
| `npm run dev` | server dev (Turbopack) |
| `npm test` / `npm run test:watch` | Vitest (70 test) |
| `npm run typecheck` | typecheck strict (`tsc --noEmit`) |
| `npx eslint` | lint |
| `npm run build` | build produksi |

## Struktur singkat

- `app/` — layout, halaman, token palet di `globals.css` (light/dark).
- `components/` — widget dashboard, panel chat, bingkai state per kartu.
- `lib/` — API client (`ApiError`), kontrak tipe, hook fetch, pemetaan data
  chart, format id-ID, sesi chat.
- `tests/` — Vitest + jsdom; chart diuji lewat pemetaan data murni, bukan
  internals Recharts.

Dokumentasi lengkap fase: `../docs/phase6-frontend.md`.

# Phase 6 — Frontend Dashboard + AI Assistant (Next.js)

Ditambahkan 2026-09-16, di atas Phase 1–5.2 (`docs/agent-phase1..5.md`). Dashboard
web BI untuk seluruh kemampuan backend: KPI, tren revenue harian + forecast,
produk/kota teratas, agregat bulanan, deteksi anomaly, dan panel AI Assistant
(memory per sesi, jejak `tools_used`, kutipan RAG). **Tidak ada perubahan
production code backend** — satu-satunya sentuhan backend fase ini adalah CORS
(yang dikerjakan di awal Phase 6 sebelum sesi ini) dan env override-nya.

## 1. Stack & struktur

Next.js 16.3.5 (App Router, Turbopack) + React 19.2 + TypeScript strict +
Tailwind CSS 4 + Recharts 3.10 + Vitest 5 (jsdom, @testing-library).

```
frontend/
├── app/
│   ├── layout.tsx          # metadata, lang="id", font Geist
│   ├── page.tsx            # → <Dashboard/> (server component)
│   └── globals.css         # token palet (CSS vars light/dark) + Tailwind 4
├── components/
│   ├── Dashboard.tsx       # komposisi widget (server component)
│   ├── KpiTiles.tsx        # hero figure + 3 metrik (GET /api/analytics/kpi)
│   ├── RevenueForecastChart.tsx  # 30 hari aktual + 7 hari prediksi (2 endpoint)
│   ├── TopProductsChart.tsx      # bar horizontal top-10 produk
│   ├── CityRevenueChart.tsx      # bar per kota
│   ├── MonthlyRevenueChart.tsx   # bar agregat bulanan (v_monthly_metrics)
│   ├── AnomalyPanel.tsx   # garis revenue semua hari + marker hari anomaly
│   ├── ChatPanel.tsx      # AI Assistant (POST /api/chat)
│   ├── WidgetCard.tsx     # bingkai + state loading/error/empty/ready
│   ├── ChartTooltip.tsx   # tooltip Recharts ber-token
│   ├── DataTable.tsx      # kembar tabel tiap chart (<details>, WCAG)
│   └── States.tsx         # LoadingState / ErrorState / EmptyState
├── lib/
│   ├── api.ts             # satu-satunya jalur ke backend + ApiError
│   ├── types.ts           # kontrak respons 1:1 dengan schemas.py
│   ├── useApi.ts          # hook fetch per-widget + toWidgetStatus
│   ├── chartData.ts       # pemetaan data→chart (pure, teruji)
│   ├── format.ts          # format id-ID (EUR, tanggal, sumbu)
│   └── session.ts         # session_id chat via useSyncExternalStore
└── tests/                 # 54 test vitest (lihat §6)
```

## 2. API client & kontrak

`lib/api.ts` membungkus semua endpoint dan **menormalisasi setiap kegagalan ke
`ApiError`** dengan `kind` yang dirender UI:

| kind        | pemicu                                                            |
|-------------|-------------------------------------------------------------------|
| `network`   | fetch gagal / timeout (GET 20 dtk, forecast 30 dtk, chat 120 dtk) |
| `client`    | HTTP 4xx                                                          |
| `server`    | HTTP 5xx — `code` = kode kontrak (`forecast_model_unavailable`, `llm_not_configured`, `memory_unavailable`, `agent_failure`) |
| `malformed` | bukan JSON / bentuk tidak sesuai kontrak (validator per endpoint) |

Base URL: `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8020`).
Validator bentuk (`parseKpi`, `parseDaily`, …) memetakan respons mentah ke tipe
`lib/types.ts` — array/object/number/string/tanggal ISO dicek eksplisit, jadi
respons rusak diklasifikasi `malformed`, bukan meledak di dalam komponen.

Dua perilaku kontrak yang penting untuk UI:

- **Kutipan RAG ada DI DALAM `answer`** sebagai `[file.md]` (kontrak agent
  Phase 3), bukan field terpisah → `parseCitations()` mengekstraknya dengan
  regex `\[([A-Za-z0-9_-]+\.md)\]` (unik, urut kemunculan) dan panel chat
  menampilkannya sebagai baris "Sumber: …".
- **`GET /api/analytics/anomalies` hanya mengembalikan hari ber-flag**
  (`WHERE is_anomaly`) → `AnomalyPanel` mengambil garis lengkap dari
  `GET /api/analytics/revenue` lalu menandai hari anomaly; tidak mengarang
  data hari non-anomaly.

## 3. State per widget

Tiap kartu memuat endpoint-nya sendiri lewat `useApi` — kegagalan satu endpoint
tidak menjatuhkan kartu lain. `toWidgetStatus()` menurunkan
`loading → error → empty → ready`; `WidgetCard` merender state seragam
(spinner / alert + kode + "Coba lagi" / pesan kosong / konten). Refetch
menahan render lama dengan opacity 60% (bukan skeleton — tanpa layout jump).

Dua kartu gabungan punya jalur degrade eksplisit:

- **Forecast**: bila `/api/forecast/revenue` 503, chart tetap menampilkan
  revenue aktual + catatan kode error + tautan muat ulang prediksi.
- **Anomaly**: bila `/api/anomalies` gagal, garis revenue tetap tampil + catatan.

## 4. Desain visual (skill dataviz)

Palet CSS vars light/dark, **divalidasi `scripts/validate_palette.js` pada kedua
mode** (CVD ΔE ≥ 24, kontras ≥ 3:1):

| Token | Light | Dark | Peran |
|---|---|---|---|
| series-1 | `#2a78d6` | `#3987e5` | deret utama (revenue, bar) |
| series-2 | `#eb6834` | `#d95926` | identitas "hari anomaly" |
| forecast | `#1e5fae` | `#7fb1ef` | shade ke-2 hue series-1 (2 shade 1 hue) |
| surface | `#fcfcfb` | `#1a1a19` | latar |
| ink / secondary / muted | `#0b0b0b` / `#52514e` / `#898781` | `#fff` / `#c3c2b7` / `#898781` | teks |
| grid | `#e1e0d9` | `#2c2c2a` | hairline solid |

Aturan yang dipegang: satu axis; bar ≤ 24px dengan ujung data membulat 4px dan
pangkal kotak; line 2px; grid hairline **solid**; legend hanya untuk ≥2 deret
(1 deret = judul kartu); tooltip nilai-memimpin dengan kunci stroke pendek;
teks selalu token tinta (tidak pernah warna deret); **hero figure tepat satu**
(total revenue); `tabular-nums` hanya di tabel/tick; tiap chart punya kembar
tabel (`<details>`); forecast dashed senada + badge "Model predictions".

**Prediksi TIDAK di-clamp.** Nilai negatif (limitasi ekstrapolasi model saat
bulan bergeser di luar rentang latih) tampil apa adanya, sumbu Y meluas di
bawah nol, dan kartu menampilkan catatan limitasi — konsisten dengan larangan
mengubah perilaku ML.

## 5. AI Assistant panel

- `session_id` per tab browser: `lib/session.ts` dibaca lewat
  `useSyncExternalStore` (snapshot SSR = null → tidak ada hydration mismatch;
  snapshot klien membaca/membuat id di `sessionStorage` dengan charset aman
  `^[A-Za-z0-9_.-]{1,128}$`). Tombol "Sesi baru" reset id + thread;
  `adoptSessionId()` mengikuti id aktual yang di-echo backend.
- Setiap jawaban menampilkan chip `tools_used` (urut pemanggilan aktual) dan
  baris "Sumber: …" hasil `parseCitations`.
- Error `ApiError` tampil inline (pesan + kode, mis. `llm_not_configured`);
  thread tetap utuh, input siap dipakai lagi. Input maks 2000 karakter
  (kontrak `ChatRequest`).
- Sementara menunggu jawaban: indikator "Agent sedang berpikir…" + input
  nonaktif (latency LLM p95 ± 24 dtk).

## 6. Test frontend (Vitest + jsdom) — 54 test, 7 file

| File | Cakupan |
|---|---|
| `tests/api.test.ts` | klasifikasi ApiError (network/4xx/5xx+kode/malformed×2), URL & body POST chat, `parseCitations` |
| `tests/chartData.test.ts` | titik jangkar forecast, prediksi negatif tak di-clamp, pemotongan history, gabungan revenue+anomaly |
| `tests/format.test.ts` | EUR id-ID, minus di depan simbol, sumbu rb/jt, tanggal |
| `tests/session.test.ts` | pembuatan/validasi charset id, snapshot stabil, reset + notifikasi, adopt |
| `tests/WidgetCard.test.tsx` | 4 state kartu + retry |
| `tests/KpiTiles.test.tsx` | loading/error+retry/ready + format hero |
| `tests/ChatPanel.test.tsx` | kirim pesan, chip tool, sumber kutipan, error 503 inline, sesi baru |

Pola test: **chart internals TIDAK diuji di jsdom** (ResponsiveContainer 0×0);
yang diuji adalah fungsi pemetaan murni (`lib/chartData.ts`) + komponen state
(non-chart) + API client dengan `fetch` yang di-mock.

## 7. Menjalankan

```bash
# Backend (PostgreSQL docker `bizintel-postgres` harus up)
cd backend && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8020

# Frontend dev (port bebas; CORS backend default mengizinkan :3000,
# untuk port lain override env — contoh :3001)
cd frontend && npm install && npm run dev -- --port 3001
# lalu jalankan backend dengan:
BIZINTEL_CORS_ORIGINS="http://localhost:3001,http://127.0.0.1:3001" \
  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8020

# Test / lint / build
cd frontend && npm test && npx tsc --noEmit && npx eslint && npm run build
```

## 8. Hasil verifikasi (2026-09-16)

- Vitest **54/54 PASS**; `tsc --noEmit` bersih; `eslint` bersih;
  `next build` sukses (route `/` static prerender).
- pytest backend **225/225 PASS** (termasuk 3 test CORS Phase 6) — tanpa
  perubahan code backend pada sesi ini.
- Integrasi live (backend 8020 + next dev 3001, port 3000 dipakai container
  lain): preflight OPTIONS dari origin frontend **200 +
  `access-control-allow-origin`**; semua endpoint analytics 200 (kpi obj,
  revenue 53 baris, products 5, cities 5, monthly 2, anomalies 8, forecast
  7 hari); `POST /api/chat` multi-tool (`get_kpi`+`get_anomalies`) grounded;
  `POST /api/rag/search` mengembalikan `promotion_policy.md`;
  `GET /api/agent/runs/{id}` tercatat SUCCESS; origin tak dikenal tidak
  menerima header CORS.
- Render diverifikasi screenshot headless Chrome: 7 widget tampil utuh di
  light mode (dark mode: palet sama-sama tervalidasi validator; mode gelap
  mengikuti `prefers-color-scheme`).

## 9. Batasan & catatan lanjutan

- Sumbu forecast memuat angka negatif sesuai data model — disengaja (lihat §4).
- Endpoint debug `POST /api/rag/search` dan `GET /api/agent/runs` belum
  dipakai UI (kandidat fitur: panel evidence RAG & riwayat run per sesi).
- Tidak ada auth/SSR fetch/proxy rewrite: dashboard murni client-side ke API
  eksplisit-CORS, sesuai larangan SaaS/deployment fase ini.
- `AGENTS.md`/`CLAUDE.md` di `frontend/` dibuat otomatis oleh Next 16 saat
  `next dev` (dikelola `generate-agent-files.js`) — dibiarkan apa adanya.

## 10. Refinement layout: AI Assistant pindah ke sidebar kanan (2026-09-17)

Perubahan murni layout — ChatPanel, kontrak API, dan seluruh perilaku assistant
TIDAK diubah. Komponen baru `components/AssistantSidebar.tsx` (client) membungkus
SATU instance `<ChatPanel/>` untuk semua breakpoint (state percakapan &
session_id tidak terduplikasi):

- **Desktop (≥ lg)**: `Dashboard.tsx` memakai grid
  `lg:grid-cols-[minmax(0,1fr)_21rem] xl:…22rem` → kolom utama ~70% +
  sidebar ~30% (terukur 864/352px @1440). Wrapper sidebar `lg:sticky
  lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:overflow-y-auto` → tetap terlihat
  saat dashboard digulir; thread chat tetap scroll internal (`max-h-96`
  milik ChatPanel). Grid widget dalam dinaikkan `lg:grid-cols-2` →
  `xl:grid-cols-2` karena sidebar mengambil ruang di lebar lg. Kontainer
  `max-w-6xl` → `max-w-7xl`.
- **Mobile/tablet (< lg)**: dashboard satu kolom penuh; assistant jadi drawer
  kanan (fixed, translate-x) yang dibuka tombol mengambang bulat
  (`lg:hidden`). Backdrop klik-untuk-tutup + tombol "Tutup" + Escape;
  fokus pindah ke input saat dibuka dan kembali ke FAB saat ditutup.
- **A11y**: aside `aria-label="AI Assistant"`, FAB `aria-expanded` +
  `aria-controls`, tombol backdrop/tutup ber-`aria-label` semantik, judul
  drawer `aria-hidden` (h2 semantik tetap dari ChatPanel). Tanpa
  set-state-in-effect (aturan React Compiler/eslint proyek) — semua interaksi
  via event handler.
- **Pembelajaran implementasi**: komponen yang mengembalikan fragment
  (FAB+backdrop+aside) di dalam grid akan terurai jadi BANYAK grid item —
  sidebar harus satu root element (wrapper div yang sekaligus jadi kolom
  sticky); `DOMRect` tidak terserialisasi JSON saat di-return dari
  `page.evaluate` (baca sebagai angka primitif).

Verifikasi (19/19 PASS, puppeteer headless + Chrome sistem): rasio kolom
0.70, sticky saat scroll (aside.top=24), FAB hidden di desktop, 5 judul
widget + KPI + assistant ter-render, chat live glm-5.3 multi-tool
(`get_kpi`+`search_business_knowledge`) dengan chip tool + citation
`[promotion_policy.md]` + angka grounded, session_id identik setelah reload,
drawer mobile buka/tutup (backdrop, fokus, Escape), dark mode surface benar.
Test baru `tests/AssistantSidebar.test.tsx` (6 test) → total vitest 60/60;
tsc & eslint bersih; `next build` sukses; image Docker frontend di-rebuild.

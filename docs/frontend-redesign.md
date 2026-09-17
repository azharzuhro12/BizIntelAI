# Frontend Redesign — Professional AI Business Intelligence Dashboard

Dokumen ini merangkum redesign visual menyeluruh frontend BizIntel AI (2026-09-17):
dari dashboard gelap multi-section menjadi SaaS BI profesional — tema terang, kartu
putih dengan border/shadow halus, satu aksen biru, navigasi atas penuh lebar, dan AI
Assistant sebagai copilot tetap di kolom kanan.

**Ruang lingkup: hanya frontend.** Tidak ada perubahan backend, skema/data PostgreSQL,
arsitektur LangGraph, tools agent, RAG/ChromaDB, model ML, atau kontrak API. Satu-satunya
integrasi baru di sisi frontend adalah fetch `GET /api/health` (endpoint sudah ada) untuk
indikator status sistem.

## 1. Design tokens (`app/globals.css`)

| Token | Light | Dark | Penggunaan |
| --- | --- | --- | --- |
| `--surface` | `#f7f7f5` | `#141413` | background halaman |
| `--card` | `#ffffff` | `#1e1e1d` | kartu widget |
| `--grid` | `#e4e3dc` | `#2e2e2c` | border hairline & garis chart |
| `--success` | `#1e8e5a` | `#4cc38a` | dot status sehat |
| `--series-1` / `--series-2` / `--forecast` | tidak berubah | tidak berubah | warna seri chart tervalidasi CVD |

Neon/gradien/glassmorphism dihilangkan seluruhnya; kartu memakai `rounded-xl border
border-hairline bg-card shadow-sm`.

## 2. Struktur halaman (`components/Dashboard.tsx`)

```
<TopNavigation />                      sticky, h-14, max-w-[1440px]
<main>
  header #dashboard                    h1 + subtitle (scroll-mt-20)
  grid lg: [minmax(0,1fr) | 20rem]     xl: 22.5rem, items-start
  ├── kolom utama (space-y-5)
  │   ├── section #analytics  → KpiCards (2×2)
  │   ├── RevenueForecastChart         chart dominan
  │   ├── grid xl:2 → TopProductsChart + AnomalyPanel
  │   ├── grid xl:2 → CityRevenueChart + MonthlyRevenueChart
  │   └── section #forecast   → ForecastPanel (scroll-mt-20)
  └── AssistantSidebar                 sticky copilot kanan
```

## 3. Komponen

| Komponen | Status | Ringkasan |
| --- | --- | --- |
| `TopNavigation.tsx` | baru | Brand + anchor kontekstual + status `System Healthy` + periode data dari `/api/analytics/kpi`; item aktif pill `bg-series-1/10` |
| `KpiCards.tsx` | baru (mengganti `KpiTiles.tsx`) | 4 kartu independen: Total Revenue (hero), Transaksi, AOV, Anomali (dengan `useApi(getAnomalies)` sendiri) — nilai tidak pernah tumpang tindih |
| `ForecastPanel.tsx` | baru | Prediksi 7 hari: daftar tanggal + nilai, total, catatan limitasi; negatif ditampilkan apa adanya |
| `ChatPanel.tsx` | diubah | Copilot penuh tinggi: header ✨ + status Online dari `/api/health`, thread menggulir sendiri, input tertaut di dasar; logika chat tidak berubah |
| `AssistantSidebar.tsx` | diubah | Sticky `top-[4.5rem]` `h-[calc(100dvh-6rem)]` di ≥lg; drawer off-canvas + FAB di <lg (logika fokus/Escape dipertahankan) |
| `Dashboard.tsx` | ditulis ulang | Shell dua kolom + anchor section |
| `WidgetCard.tsx` | diubah | Frame kartu profesional |
| `RevenueForecastChart.tsx` | diubah | `YAxis width={80}` agar label negatif ("-€15,2 rb") tidak terpotong |
| `TopProductsChart` / `CityRevenueChart` / `MonthlyRevenueChart` | diubah | Tinggi disesuaikan grid baru |
| `lib/api.ts` + `lib/types.ts` | diubah | Tambahan frontend-only: `getHealth()` + tipe `Health` |

Dihapus: `KpiTiles.tsx` dan `tests/KpiTiles.test.tsx` (benar-benar tak terpakai setelah
swap; penggantinya `KpiCards.test.tsx` lebih lengkap).

## 4. Perilaku responsif

- **Desktop ≥1280 (1440/1366/1280/1024):** dua kolom; sidebar 360px (320px di 1024).
  Sidebar sticky di bawah nav (`top=72`, tinggi `viewport−96`); di dasar halaman sticky
  wajar release karena konten utama habis.
- **Tablet 768:** satu kolom penuh; AI Assistant jadi FAB + drawer.
- **Mobile 390:** satu kolom; drawer `min(22rem, 88vw)`, backdrop, fokus otomatis ke
  input, Escape menutup.
- Tanpa scroll horizontal di semua viewport teruji.

## 5. Keputusan desain penting

1. **KPI 2×2, bukan 4 sebaris** — kolom utama ~1010px di 1440 (890px di 1280); empat
   kartu sebaris membuat kartu ≤240px dan nilai hero €769.515,86 sesak. STEP 19 spec
   mengizinkan penyesuaian grid di kolom sempit.
2. **Prediksi negatif TIDAK di-clamp** — mandate spec; catatan limitasi ekstrapolasi
   selalu tampil saat ada nilai negatif (jujur soal limitasi model, nilai live dari API).
3. **Item nav tanpa halaman** — Dashboard/Analytics/Forecast = anchor ke section nyata;
   RAG → `#assistant-panel` (hanya ≥lg, karena targetnya drawer off-canvas di bawah itu);
   Agent Runs = `<span aria-disabled>` non-interaktif (belum ada UI-nya) — tidak ada
   link mati maupun halaman karangan.
4. **Status "System Healthy" / "Online"** — dari `GET /api/health` (status `ok` +
   database `connected`), bukan hardcode; fallback "API tidak terjangkau"/"Sistem
   bermasalah".
5. **Tidak ada metrik bisnis karangan** — tidak ada growth %, margin, ROI, dsb.;
   semua angka dari endpoint analitik yang sudah ada.

## 6. Aksesibilitas

- `aria-current="page"` + gaya visual pada item nav aktif; `aria-disabled` pada Agent Runs.
- Status sistem `aria-live="polite"` (nav) dan thread chat `aria-live="polite"`.
- Drawer: `aria-expanded`/`aria-controls` pada FAB, backdrop ber-pername, fokus
  dikembalikan ke FAB saat tertutup, Escape menutup.
- Label input (`aria-label="Pertanyaan untuk AI assistant"`), tombol ikon ber-`aria-label`,
  chart memiliki tabel data pendamping (`DataTable`) sebagai alternatif non-visual.

## 7. Pengujian & validasi

| Pemeriksaan | Hasil |
| --- | --- |
| Vitest | **69/69** (10 file; baseline 60 → +9 bersih) |
| `tsc --noEmit` | lolos |
| ESLint | lolos |
| `next build` | sukses |
| Puppeteer multi-viewport (1440/1366/1280/1024/768/390) | **77/77** — tanpa overflow horizontal, sticky nav/sidebar presisi, proporsi kolom 0.65–0.73, 9 chart ter-render, nilai KPI/forecast live, 4 skenario chat GLM-5.3 nyata dengan chip tool benar (`get_kpi`, `get_revenue_forecast`, `search_business_knowledge`, kombinasi), session persist, drawer mobile, dark mode |

Perbaikan pasca-inspeksi visual screenshot: label y-axis negatif lengkap
(`YAxis width 80`) dan pill item nav aktif. Saran inspeksi yang **sengaja ditolak**
karena berlawanan dengan mandate spec: clamping prediksi negatif dan re-layout kolom.

## 8. Limitasi yang diketahui

- **Agent Runs** belum punya UI — item nav non-interaktif sampai UI riwayat run dibuat.
- **Prediksi negatif** (total 7 hari −€27.844,97) adalah limitasi ekstrapolasi model
  linear di luar rentang data pelatihan; ditampilkan apa adanya + catatan.
- **Item RAG** hanya tampil ≥lg (target anchor adalah panel inline; di bawah lg panel
   berupa drawer yang dibuka via FAB).
- Di puncak halaman (scroll 0) dasar sidebar copilot masih di bawah lipatan — perilaku
  wajar sticky (bukan fixed); setelah scroll ±110px panel terpasang penuh.

## 9. Menjalankan

```bash
# Dev
cd frontend && npx next dev --port 3001   # API http://localhost:8020

# Docker (port host 3001; 3000 dipakai aplikasi lain)
FRONTEND_PORT=3001 NEXT_PUBLIC_API_URL=http://localhost:8020 \
  docker compose up -d --build frontend
```

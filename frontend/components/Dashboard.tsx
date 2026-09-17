/**
 * Susunan dashboard BizIntel AI (SaaS BI shell): navigasi atas sticky,
 * page header, lalu dua kolom di >= lg — dashboard utama + AI Assistant
 * copilot sticky di kanan. Tiap widget memuat endpoint-nya sendiri
 * (state loading/error/empty independen) - server component yang hanya
 * mengomposisikan client components.
 */

import { AnomalyPanel } from "./AnomalyPanel";
import { AssistantSidebar } from "./AssistantSidebar";
import { CityRevenueChart } from "./CityRevenueChart";
import { ForecastPanel } from "./ForecastPanel";
import { KpiCards } from "./KpiCards";
import { MonthlyRevenueChart } from "./MonthlyRevenueChart";
import { RevenueForecastChart } from "./RevenueForecastChart";
import { TopNavigation } from "./TopNavigation";
import { TopProductsChart } from "./TopProductsChart";

export function Dashboard() {
  return (
    <>
      <TopNavigation />
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 sm:px-6 lg:py-8">
        <header id="dashboard" className="scroll-mt-20">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Business Intelligence Dashboard
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-secondary">
            Analysis data penjualan restoran — insight berbasis SQL, machine learning, RAG,
            dan AI agent.
          </p>
        </header>

        {/* Dua kolom di >= lg: dashboard utama (~70%) + AI Assistant sticky
            (~30%, lihat AssistantSidebar). items-start agar sticky sidebar
            tidak terkunci stretch setinggi baris grid. */}
        <div className="mt-6 gap-5 lg:grid lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start xl:grid-cols-[minmax(0,1fr)_22.5rem]">
          <div className="min-w-0 space-y-5">
            <section id="analytics" className="scroll-mt-20" aria-label="Ringkasan KPI">
              <KpiCards />
            </section>
            <RevenueForecastChart />
            {/* Grid widget dalam naik ke xl: di lebar lg sidebar sudah
                mengambil ruang, dua kolom chart akan terlalu sempit. */}
            <div className="grid gap-5 xl:grid-cols-2">
              <TopProductsChart />
              <AnomalyPanel />
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              <CityRevenueChart />
              <MonthlyRevenueChart />
            </div>
            <section id="forecast" className="scroll-mt-20" aria-label="Prediksi revenue">
              <ForecastPanel />
            </section>
          </div>
          <AssistantSidebar />
        </div>

        <footer className="mt-8 text-xs text-ink-muted">
          Sumber data: dataset penjualan restoran (Kaggle) · PostgreSQL + FastAPI ·
          dashboard Next.js
        </footer>
      </main>
    </>
  );
}

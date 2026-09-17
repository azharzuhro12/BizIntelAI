/** Test 4 kartu KPI independen: nilai getKpi + jumlah hari anomali (getAnomalies). */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KpiCards } from "@/components/KpiCards";
import { ApiError, getAnomalies, getKpi } from "@/lib/api";
import type { AnomalyDay, Kpi } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, getKpi: vi.fn(), getAnomalies: vi.fn() };
});

const mockedGetKpi = vi.mocked(getKpi);
const mockedGetAnomalies = vi.mocked(getAnomalies);

const kpiMock: Kpi = {
  total_revenue: 769515.86,
  total_quantity: 224834,
  total_transactions: 254,
  average_transaction_value: 3029.59,
  date_range_start: "2022-11-07",
  date_range_end: "2022-12-29",
};

function anomalyRows(count: number): AnomalyDay[] {
  return Array.from({ length: count }, (_, i) => ({
    date: `2022-11-${String(10 + i).padStart(2, "0")}`,
    revenue: 1000 + i,
    quantity: 10 + i,
    transactions: 2 + i,
    anomaly_score_label: -0.7 - i * 0.01,
    is_anomaly: true,
  }));
}

beforeEach(() => {
  mockedGetKpi.mockReset();
  mockedGetAnomalies.mockReset();
});

describe("KpiCards", () => {
  it("menampilkan state memuat sebelum data tiba", async () => {
    mockedGetKpi.mockImplementation(() => new Promise(() => {}));
    mockedGetAnomalies.mockImplementation(() => new Promise(() => {}));
    render(<KpiCards />);
    expect(await screen.findByText("Memuat KPI…")).toBeInTheDocument();
  });

  it("error getKpi -> state error dengan tombol coba lagi, lalu pulih", async () => {
    mockedGetKpi
      .mockRejectedValueOnce(new ApiError("network", "Tidak dapat terhubung ke server API."))
      .mockResolvedValue(kpiMock);
    mockedGetAnomalies.mockResolvedValue(anomalyRows(8));
    render(<KpiCards />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Tidak dapat terhubung ke server API.");
    await userEvent.click(screen.getByRole("button", { name: "Coba lagi" }));
    expect(await screen.findByText("€769.515,86")).toBeInTheDocument();
  });

  it("merender 4 kartu: revenue, transaksi, AOV, jumlah hari anomali + periode", async () => {
    mockedGetKpi.mockResolvedValue(kpiMock);
    mockedGetAnomalies.mockResolvedValue(anomalyRows(8));
    render(<KpiCards />);

    expect(await screen.findByText("€769.515,86")).toBeInTheDocument();
    expect(screen.getByText("Total Revenue")).toBeInTheDocument();
    expect(screen.getByText("254")).toBeInTheDocument();
    expect(screen.getByText("Jumlah Transaksi")).toBeInTheDocument();
    expect(screen.getByText("€3.029,59")).toBeInTheDocument();
    expect(screen.getByText("Rata-rata Nilai Transaksi")).toBeInTheDocument();
    // Dua useApi independen - tunggu kartu anomali selesai (bukan sinkron).
    expect(await screen.findByText("8")).toBeInTheDocument();
    expect(screen.getByText(/hari terdeteksi/)).toBeInTheDocument();
    expect(screen.getByText(/7 Nov – 29 Des 2022/)).toBeInTheDocument();
  });

  it("kegagalan getAnomalies hanya menjatuhkan kartu anomali, KPI lain tetap", async () => {
    mockedGetKpi.mockResolvedValue(kpiMock);
    mockedGetAnomalies.mockRejectedValue(
      new ApiError("server", "Server API mengalami kendala (HTTP 500).", { status: 500 }),
    );
    render(<KpiCards />);

    expect(await screen.findByText("€769.515,86")).toBeInTheDocument();
    expect(screen.getByText("254")).toBeInTheDocument();
    expect(screen.getByText("€3.029,59")).toBeInTheDocument();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("HTTP 500");
  });
});

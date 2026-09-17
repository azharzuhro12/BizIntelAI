/** Test panel prediksi komplementer: daftar 7 hari, total, catatan limitasi, error. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForecastPanel } from "@/components/ForecastPanel";
import { ApiError, getRevenueForecast } from "@/lib/api";
import type { ForecastResponse } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, getRevenueForecast: vi.fn() };
});

const mockedGetRevenueForecast = vi.mocked(getRevenueForecast);

const forecastMock: ForecastResponse = {
  model: "Linear Regression",
  features: ["day", "month", "lag_1", "lag_7", "roll_7", "dow", "doy"],
  last_history_date: "2022-12-29",
  days: 7,
  predictions: [
    { date: "2022-12-30", predicted_revenue: 16533.84 },
    { date: "2022-12-31", predicted_revenue: 15924.91 },
    { date: "2023-01-01", predicted_revenue: -9007.63 },
    { date: "2023-01-02", predicted_revenue: -10474.2 },
    { date: "2023-01-03", predicted_revenue: -11961.51 },
    { date: "2023-01-04", predicted_revenue: -13709.57 },
    { date: "2023-01-05", predicted_revenue: -15150.81 },
  ],
};

beforeEach(() => {
  mockedGetRevenueForecast.mockReset();
});

describe("ForecastPanel", () => {
  it("merender daftar 7 prediksi (negatif apa adanya), total, dan catatan limitasi", async () => {
    mockedGetRevenueForecast.mockResolvedValue(forecastMock);
    render(<ForecastPanel />);

    expect(await screen.findByText("Prediksi Revenue 7 Hari ke Depan")).toBeInTheDocument();
    expect(screen.getByText("Model Linear Regression · horison 7 hari")).toBeInTheDocument();
    expect(screen.getByText("30 Des 2022")).toBeInTheDocument();
    expect(screen.getByText("€16.533,84")).toBeInTheDocument();
    expect(screen.getByText("€15.924,91")).toBeInTheDocument();
    // Negatif tidak di-clamp/disembunyikan (minus di depan simbol).
    expect(screen.getByText("-€9.007,63")).toBeInTheDocument();
    expect(screen.getByText("-€15.150,81")).toBeInTheDocument();
    // Total = 16533.84 + 15924.91 - 9007.63 - 10474.2 - 11961.51 - 13709.57 - 15150.81
    expect(screen.getByText("-€27.844,97")).toBeInTheDocument();
    expect(screen.getByText("Total 7 hari")).toBeInTheDocument();
    expect(screen.getByText(/Catatan model/)).toBeInTheDocument();
  });

  it("error forecast_model_unavailable -> state error dengan coba lagi, lalu pulih", async () => {
    mockedGetRevenueForecast
      .mockRejectedValueOnce(
        new ApiError("server", "Server API mengalami kendala (HTTP 503): model tidak tersedia", {
          status: 503,
          code: "forecast_model_unavailable",
        }),
      )
      .mockResolvedValue(forecastMock);
    render(<ForecastPanel />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("forecast_model_unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Coba lagi" }));
    expect(await screen.findByText("€16.533,84")).toBeInTheDocument();
  });

  it("prediksi kosong -> state kosong", async () => {
    mockedGetRevenueForecast.mockResolvedValue({ ...forecastMock, predictions: [] });
    render(<ForecastPanel />);

    expect(await screen.findByText("Tidak ada prediksi untuk ditampilkan.")).toBeInTheDocument();
  });
});

/** Test navigasi atas: anchor ke section nyata, status sistem + periode data dari API. */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TopNavigation } from "@/components/TopNavigation";
import { getHealth, getKpi } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, getHealth: vi.fn(), getKpi: vi.fn() };
});

const mockedGetHealth = vi.mocked(getHealth);
const mockedGetKpi = vi.mocked(getKpi);

beforeEach(() => {
  mockedGetHealth.mockReset();
  mockedGetKpi.mockReset();
});

describe("TopNavigation", () => {
  it("brand + item navigasi berupa anchor ke section yang ada; Agent Runs non-interaktif", async () => {
    mockedGetHealth.mockResolvedValue({ status: "ok", database: "connected", tables: {} });
    mockedGetKpi.mockResolvedValue({
      total_revenue: 769515.86,
      total_quantity: 224834,
      total_transactions: 254,
      average_transaction_value: 3029.59,
      date_range_start: "2022-11-07",
      date_range_end: "2022-12-29",
    });
    render(<TopNavigation />);

    expect(screen.getByRole("link", { name: "BizIntel AI" })).toHaveAttribute(
      "href",
      "#dashboard",
    );
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "#dashboard");
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveAttribute("href", "#analytics");
    expect(screen.getByRole("link", { name: "Forecast" })).toHaveAttribute("href", "#forecast");
    expect(screen.getByRole("link", { name: "RAG" })).toHaveAttribute("href", "#assistant-panel");

    // Agent Runs belum punya UI - tampil sebagai teks non-interaktif, bukan link.
    const agentRuns = screen.getByText("Agent Runs");
    expect(agentRuns.tagName).toBe("SPAN");
    expect(agentRuns).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByRole("link", { name: "Agent Runs" })).not.toBeInTheDocument();
  });

  it("status System Healthy + periode data dari API saat sehat", async () => {
    mockedGetHealth.mockResolvedValue({ status: "ok", database: "connected", tables: {} });
    mockedGetKpi.mockResolvedValue({
      total_revenue: 769515.86,
      total_quantity: 224834,
      total_transactions: 254,
      average_transaction_value: 3029.59,
      date_range_start: "2022-11-07",
      date_range_end: "2022-12-29",
    });
    render(<TopNavigation />);

    expect(await screen.findByText("System Healthy")).toBeInTheDocument();
    expect(await screen.findByText(/Data: 7 Nov – 29 Des 2022/)).toBeInTheDocument();
  });

  it("backend tidak terjangkau -> status error, periode disembunyikan", async () => {
    mockedGetHealth.mockRejectedValue(new Error("network"));
    mockedGetKpi.mockRejectedValue(new Error("network"));
    render(<TopNavigation />);

    expect(await screen.findByText("API tidak terjangkau")).toBeInTheDocument();
    expect(screen.queryByText(/Data: /)).not.toBeInTheDocument();
  });

  it("database terputus (health 200 tapi tidak sehat) -> status bermasalah", async () => {
    mockedGetHealth.mockResolvedValue({ status: "ok", database: "disconnected", tables: {} });
    mockedGetKpi.mockResolvedValue({
      total_revenue: 769515.86,
      total_quantity: 224834,
      total_transactions: 254,
      average_transaction_value: 3029.59,
      date_range_start: "2022-11-07",
      date_range_end: "2022-12-29",
    });
    render(<TopNavigation />);

    expect(await screen.findByText("Sistem bermasalah")).toBeInTheDocument();
  });
});

/** Test state WidgetCard (loading/error/empty/ready) - tanpa chart. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WidgetCard } from "@/components/WidgetCard";
import { ApiError } from "@/lib/api";

describe("WidgetCard", () => {
  it("status loading menampilkan indikator", () => {
    render(
      <WidgetCard title="Judul" status="loading" onRetry={() => {}}>
        <p>konten</p>
      </WidgetCard>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Memuat data…");
    expect(screen.queryByText("konten")).not.toBeInTheDocument();
  });

  it("status error menampilkan pesan + kode + tombol coba lagi", async () => {
    const retry = vi.fn();
    const error = new ApiError("server", "Server API mengalami kendala (HTTP 503)", {
      status: 503,
      code: "forecast_model_unavailable",
    });
    render(
      <WidgetCard title="Judul" status="error" error={error} onRetry={retry}>
        <p>konten</p>
      </WidgetCard>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Server API mengalami kendala");
    expect(screen.getByText("Kode: forecast_model_unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Coba lagi" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("status empty menampilkan pesan kustom", () => {
    render(
      <WidgetCard title="Judul" status="empty" onRetry={() => {}} emptyMessage="Belum ada data">
        <p>konten</p>
      </WidgetCard>,
    );
    expect(screen.getByText("Belum ada data")).toBeInTheDocument();
  });

  it("status ready merender children", () => {
    render(
      <WidgetCard title="Judul" status="ready" onRetry={() => {}}>
        <p>konten</p>
      </WidgetCard>,
    );
    expect(screen.getByText("konten")).toBeInTheDocument();
  });
});

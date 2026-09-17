/** Test panel chat: alur kirim, tools_used, kutipan RAG, error, sesi baru. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/ChatPanel";
import { ApiError, getHealth, sendChat } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    sendChat: vi.fn(),
    // Heartbeat header copilot - di-stub agar tidak ada fetch nyata di jsdom.
    getHealth: vi.fn(),
  };
});

const mockedSendChat = vi.mocked(sendChat);
const mockedGetHealth = vi.mocked(getHealth);

const okResponse: ChatResponse = {
  answer:
    "Aturan promo mengikuti kebijakan di [promotion_policy.md]. Total revenue €769.515,86.",
  tools_used: ["search_business_knowledge", "get_kpi"],
  session_id: "test-session-1",
};

beforeEach(() => {
  mockedSendChat.mockReset();
  mockedGetHealth.mockReset();
  mockedGetHealth.mockResolvedValue({ status: "ok", database: "connected", tables: {} });
  sessionStorage.clear();
});

describe("ChatPanel", () => {
  it("keadaan awal: empty state copilot + saran pertanyaan + input aktif setelah sesi siap", async () => {
    render(<ChatPanel />);
    expect(
      screen.getByText("Tanya apa saja tentang penjualan dan analisis data."),
    ).toBeInTheDocument();
    expect(screen.getByText("Contoh pertanyaan:")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("Pertanyaan untuk AI assistant")).toBeEnabled(),
    );
    expect(screen.getByText(/^Sesi: /)).toBeInTheDocument();
  });

  it("status header Online saat heartbeat sehat, Offline saat gagal", async () => {
    mockedGetHealth.mockResolvedValue({ status: "ok", database: "connected", tables: {} });
    const { unmount } = render(<ChatPanel />);
    expect(await screen.findByText("Online")).toBeInTheDocument();
    unmount();

    mockedGetHealth.mockResolvedValue({ status: "error", database: "disconnected", tables: {} });
    render(<ChatPanel />);
    expect(await screen.findByText("Offline")).toBeInTheDocument();
  });

  it("kirim pesan -> bubble user + jawaban + chip tool + sumber kutipan", async () => {
    mockedSendChat.mockResolvedValue(okResponse);
    render(<ChatPanel />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.type(input, "Apa aturan promo?");
    await userEvent.click(screen.getByRole("button", { name: "Kirim" }));

    expect(await screen.findByText(/Aturan promo mengikuti kebijakan/)).toBeInTheDocument();
    expect(screen.getByText("Apa aturan promo?")).toBeInTheDocument();
    expect(screen.getByText("search_business_knowledge")).toBeInTheDocument();
    expect(screen.getByText("get_kpi")).toBeInTheDocument();
    // Citation RAG: label "Sumber:" + chip per dokumen (chip memecah text
    // node, jadi assertion label dan chip dipisah).
    expect(screen.getByText(/Sumber:/)).toBeInTheDocument();
    expect(screen.getByText("promotion_policy.md")).toBeInTheDocument();
    expect(mockedSendChat).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Apa aturan promo?" }),
    );
  });

  it("jawaban assistant dirender Markdown (bold/tabel/list/kode); pesan user tetap teks polos", async () => {
    mockedSendChat.mockResolvedValue({
      answer:
        "Prediksi revenue 3 hari ke depan:\n\n| Tanggal | Prediksi Revenue |\n|---|---:|\n| 2022-12-30 | **16.533,84** |\n| 2023-01-01 | **-9.007,63** |\n\nCatatan penting:\n\n- Nilai negatif merupakan output model\n- Model dilatih pada data `daily_metrics`",
      tools_used: ["get_revenue_forecast"],
      session_id: "md-test-1",
    });
    render(<ChatPanel />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.type(input, "saya **user** biasa");
    await userEvent.click(screen.getByRole("button", { name: "Kirim" }));

    // Tabel GFM jadi elemen <table> sungguhan (bukan sintaks mentah).
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Tanggal" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2022-12-30" })).toBeInTheDocument();
    // Bold: nilai berada di <strong>, bukan sisa "**".
    expect(screen.getByText("16.533,84").tagName).toBe("STRONG");
    expect(screen.getByText("-9.007,63").tagName).toBe("STRONG");
    // Bullet list + inline code.
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText(/Nilai negatif merupakan output model/).closest("li")).not.toBeNull();
    expect(screen.getByText("daily_metrics").tagName).toBe("CODE");
    // Tidak ada sintaks Markdown mentah yang tersisa di jawaban.
    expect(screen.queryByText(/\|---/)).not.toBeInTheDocument();
    // Pesan user TIDAK dirender Markdown: asterisk tampil literal.
    expect(screen.getByText("saya **user** biasa")).toBeInTheDocument();
    // Chip tool tetap tampil bersama jawaban Markdown.
    expect(screen.getByText("get_revenue_forecast")).toBeInTheDocument();
  });

  it("saran pertanyaan bisa diklik langsung", async () => {
    mockedSendChat.mockResolvedValue(okResponse);
    render(<ChatPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /Prediksi revenue/ }));
    expect(await screen.findByText(/Aturan promo mengikuti/)).toBeInTheDocument();
  });

  it("error 503 llm_not_configured tampil sebagai alert, thread tetap", async () => {
    mockedSendChat.mockRejectedValue(
      new ApiError("server", "Server API mengalami kendala (HTTP 503): LLM belum dikonfigurasi", {
        status: 503,
        code: "llm_not_configured",
      }),
    );
    render(<ChatPanel />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.type(input, "total revenue?");
    await userEvent.click(screen.getByRole("button", { name: "Kirim" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("LLM belum dikonfigurasi");
    expect(alert).toHaveTextContent("llm_not_configured");
    expect(screen.getByText("total revenue?")).toBeInTheDocument();
  });

  it("tombol Sesi baru mengosongkan thread dan mengganti id", async () => {
    mockedSendChat.mockResolvedValue(okResponse);
    render(<ChatPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /Prediksi revenue/ }));
    await screen.findByText(/Aturan promo mengikuti/);
    const sessionIdLama = screen.getByText(/^Sesi: /).textContent;

    await userEvent.click(screen.getByRole("button", { name: "Sesi baru" }));
    expect(
      screen.getByText("Tanya apa saja tentang penjualan dan analisis data."),
    ).toBeInTheDocument();
    expect(screen.getByText(/^Sesi: /).textContent).not.toBe(sessionIdLama);
  });
});

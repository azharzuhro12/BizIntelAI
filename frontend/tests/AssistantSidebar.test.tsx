/** Test wadah AI Assistant: drawer mobile (FAB/backdrop/Esc) + ChatPanel tetap utuh. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AssistantSidebar } from "@/components/AssistantSidebar";
import { ApiError, getHealth, sendChat } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    sendChat: vi.fn(),
    // Heartbeat ChatPanel - di-stub agar tidak ada fetch nyata di jsdom.
    getHealth: vi.fn().mockResolvedValue({ status: "ok", database: "connected", tables: {} }),
  };
});

const mockedSendChat = vi.mocked(sendChat);
const mockedGetHealth = vi.mocked(getHealth);

const okResponse: ChatResponse = {
  answer: "Total revenue €769.515,86 sesuai [sales_policy.md].",
  tools_used: ["get_kpi", "search_business_knowledge"],
  session_id: "sidebar-test-1",
};

beforeEach(() => {
  mockedSendChat.mockReset();
  mockedGetHealth.mockReset();
  mockedGetHealth.mockResolvedValue({ status: "ok", database: "connected", tables: {} });
  sessionStorage.clear();
});

describe("AssistantSidebar", () => {
  it("merender ChatPanel (input siap) dan tombol mengambang tertutup", async () => {
    render(<AssistantSidebar />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    expect(input).toBeEnabled();

    const fab = screen.getByRole("button", { name: "Buka AI Assistant" });
    expect(fab).toHaveAttribute("aria-expanded", "false");
    expect(fab).toHaveAttribute("aria-controls", "assistant-panel");
    expect(screen.getByLabelText("AI Assistant", { selector: "aside" })).toBeInTheDocument();
  });

  it("klik tombol mengambang membuka drawer: backdrop + tombol tutup muncul", async () => {
    render(<AssistantSidebar />);
    await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.click(screen.getByRole("button", { name: "Buka AI Assistant" }));

    expect(screen.getByRole("button", { name: "Tutup panel AI Assistant" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tutup AI Assistant" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buka AI Assistant" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("menutup via backdrop mengembalikan fokus ke tombol mengambang", async () => {
    render(<AssistantSidebar />);
    await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.click(screen.getByRole("button", { name: "Buka AI Assistant" }));

    await userEvent.click(screen.getByRole("button", { name: "Tutup panel AI Assistant" }));

    expect(screen.queryByRole("button", { name: "Tutup panel AI Assistant" })).not.toBeInTheDocument();
    const fab = screen.getByRole("button", { name: "Buka AI Assistant" });
    expect(fab).toHaveAttribute("aria-expanded", "false");
    expect(fab).toHaveFocus();
  });

  it("Escape dari dalam panel menutup drawer", async () => {
    render(<AssistantSidebar />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.click(screen.getByRole("button", { name: "Buka AI Assistant" }));
    await userEvent.type(input, "uji"); // pastikan fokus di dalam drawer

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "Tutup panel AI Assistant" })).not.toBeInTheDocument();
  });

  it("alur chat tetap berfungsi di dalam sidebar: jawaban + chip tool + sumber", async () => {
    mockedSendChat.mockResolvedValue(okResponse);
    render(<AssistantSidebar />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.type(input, "Berapa total revenue?");
    await userEvent.click(screen.getByRole("button", { name: "Kirim" }));

    expect(await screen.findByText(/Total revenue €769\.515,86/)).toBeInTheDocument();
    expect(screen.getByText("get_kpi")).toBeInTheDocument();
    // Citation RAG: label "Sumber:" + chip dokumen (text node terpisah).
    expect(screen.getByText(/Sumber:/)).toBeInTheDocument();
    expect(screen.getByText("sales_policy.md")).toBeInTheDocument();
    expect(mockedSendChat).toHaveBeenCalledTimes(1);
  });

  it("error jaringan ditampilkan inline tanpa mengosongkan thread", async () => {
    mockedSendChat.mockRejectedValue(
      new ApiError("server", "Model LLM belum terkonfigurasi.", {
        code: "llm_not_configured",
      }),
    );
    render(<AssistantSidebar />);
    const input = await screen.findByLabelText("Pertanyaan untuk AI assistant");
    await userEvent.type(input, "Halo");
    await userEvent.click(screen.getByRole("button", { name: "Kirim" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Model LLM belum terkonfigurasi."),
    );
    expect(screen.getByText("Halo")).toBeInTheDocument(); // bubble user tetap ada
  });
});

/** Test API client: klasifikasi error, bentuk kontrak, parse kutipan. */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiBaseUrl, getKpi, parseCitations, sendChat } from "@/lib/api";

function mockFetchOnce(body: unknown, init: { status?: number; raw?: string } = {}) {
  return vi.fn().mockResolvedValue(
    new Response(init.raw ?? JSON.stringify(body), {
      status: init.status ?? 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const kpiPayload = {
  total_revenue: 769515.86,
  total_quantity: 224834,
  total_transactions: 1000,
  average_transaction_value: 769.52,
  date_range_start: "2022-11-07",
  date_range_end: "2022-12-29",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("apiBaseUrl", () => {
  it("default ke backend lokal 8020 tanpa trailing slash", () => {
    expect(apiBaseUrl()).toBe("http://127.0.0.1:8020");
  });

  it("mengikuti NEXT_PUBLIC_API_URL dan memangkas slash", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com/");
    expect(apiBaseUrl()).toBe("https://api.example.com");
  });
});

describe("getKpi", () => {
  it("memetakan respons kontrak ke Kpi", async () => {
    vi.stubGlobal("fetch", mockFetchOnce(kpiPayload));
    const kpi = await getKpi();
    expect(kpi.total_revenue).toBe(769515.86);
    expect(kpi.date_range_end).toBe("2022-12-29");
  });

  it("network error saat fetch gagal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const error = await getKpi().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe("network");
    expect((error as ApiError).status).toBeNull();
  });

  it("4xx diklasifikasi client dengan pesan detail", async () => {
    vi.stubGlobal("fetch", mockFetchOnce({ detail: "Not found" }, { status: 404 }));
    const error = await getKpi().catch((e) => e);
    expect((error as ApiError).kind).toBe("client");
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).reason).toBe("Not found");
  });

  it("503 server mengekstrak kode error kontrak", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchOnce(
        { detail: { error: "forecast_model_unavailable", reason: "artefak hilang" } },
        { status: 503 },
      ),
    );
    const { getRevenueForecast } = await import("@/lib/api");
    const error = await getRevenueForecast().catch((e) => e);
    expect((error as ApiError).kind).toBe("server");
    expect((error as ApiError).code).toBe("forecast_model_unavailable");
    expect((error as ApiError).reason).toBe("artefak hilang");
  });

  it("JSON tidak valid diklasifikasi malformed", async () => {
    vi.stubGlobal("fetch", mockFetchOnce(null, { raw: "<html>ups</html>" }));
    const error = await getKpi().catch((e) => e);
    expect((error as ApiError).kind).toBe("malformed");
  });

  it("bentuk tidak sesuai kontrak diklasifikasi malformed", async () => {
    vi.stubGlobal("fetch", mockFetchOnce({ total_revenue: "bukan angka" }));
    const error = await getKpi().catch((e) => e);
    expect((error as ApiError).kind).toBe("malformed");
  });

  it("kirim POST /api/chat dengan body kontrak", async () => {
    const fetchMock = mockFetchOnce({
      answer: "Total revenue €769.515,86 [promotion_policy.md]",
      tools_used: ["get_kpi"],
      session_id: "s-1",
    });
    vi.stubGlobal("fetch", fetchMock);
    const response = await sendChat({ message: "total revenue?", session_id: "s-1" });
    expect(response.tools_used).toEqual(["get_kpi"]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8020/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ message: "total revenue?", session_id: "s-1" });
  });
});

describe("parseCitations", () => {
  it("ekstrak [file.md] unik dengan urutan kemunculan", () => {
    const answer =
      "Aturan promo ada di [promotion_policy.md]; jadwal operasional [operations_schedule.md], ringkas di [promotion_policy.md].";
    expect(parseCitations(answer)).toEqual(["promotion_policy.md", "operations_schedule.md"]);
  });

  it("menolak bentuk non-kutipan (path, ekstensi lain)", () => {
    expect(parseCitations("lihat ../etc/passwd dan [notes.txt] dan [a b.md]")).toEqual([]);
  });

  it("string kosong -> array kosong", () => {
    expect(parseCitations("")).toEqual([]);
  });
});

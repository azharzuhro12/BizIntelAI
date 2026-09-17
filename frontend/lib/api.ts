/**
 * API client BizIntel AI - satu-satunya jalur frontend ke backend FastAPI.
 *
 * Semua kegagalan dinormalisasi ke ApiError dengan `kind` yang bisa
 * dirender UI (loading/error/empty per widget):
 * - "network"  : backend tidak terjangkau / timeout / koneksi diputus
 * - "client"   : HTTP 4xx (request salah dari sisi klien)
 * - "server"   : HTTP 5xx, termasuk error kode kontrak backend
 *                (forecast_model_unavailable, llm_not_configured, dll)
 * - "malformed": respons bukan JSON / bentuk tidak sesuai kontrak
 */

import type {
  AgentRunListResponse,
  AnomalyDay,
  ChatRequest,
  ChatResponse,
  CityRevenue,
  DailyRevenuePoint,
  ForecastResponse,
  Health,
  Kpi,
  MonthlyRevenue,
  ProductRevenue,
  RagSearchResponse,
} from "./types";

export type ApiErrorKind = "network" | "client" | "server" | "malformed";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  /** HTTP status; null untuk network/malformed. */
  readonly status: number | null;
  /** Kode error kontrak backend (detail.error), mis. "llm_not_configured". */
  readonly code: string | null;
  /** Alasan manusiawi dari backend (detail.reason/detail string), bila ada. */
  readonly reason: string | null;

  constructor(
    kind: ApiErrorKind,
    message: string,
    options?: { status?: number; code?: string; reason?: string; cause?: unknown },
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options?.status ?? null;
    this.code = options?.code ?? null;
    this.reason = options?.reason ?? null;
    if (options?.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

const DEFAULT_API_URL = "http://127.0.0.1:8020";

/** Base URL backend; override production via NEXT_PUBLIC_API_URL. */
export function apiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
  return raw.replace(/\/+$/, "");
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  /** Timeout ms; default 20_000. Chat LLM butuh jauh lebih lama. */
  timeoutMs?: number;
  signal?: AbortSignal;
}

/** Body error FastAPI: {"detail": "teks"} atau {"detail": {error, reason, hint}}. */
function extractDetail(payload: unknown): { code: string | null; reason: string | null } {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return { code: null, reason: detail };
    }
    if (detail && typeof detail === "object") {
      const obj = detail as Record<string, unknown>;
      return {
        code: typeof obj.error === "string" ? obj.error : null,
        reason: typeof obj.reason === "string" ? obj.reason : null,
      };
    }
  }
  return { code: null, reason: null };
}

async function request<T>(
  path: string,
  expect: (value: unknown) => T,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, timeoutMs = 20_000, signal } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), timeoutMs);
  const onExternalAbort = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", onExternalAbort);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError("network", "Tidak dapat terhubung ke server API. Pastikan backend berjalan.", {
      cause,
    });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }

  let payload: unknown = null;
  let parseFailed = false;
  try {
    const text = await response.text();
    payload = text ? JSON.parse(text) : null;
  } catch {
    parseFailed = true;
  }

  if (!response.ok) {
    const { code, reason } = extractDetail(payload);
    const kind: ApiErrorKind = response.status >= 500 ? "server" : "client";
    const label = response.status >= 500 ? "Server API mengalami kendala" : "Permintaan ditolak server";
    throw new ApiError(kind, `${label} (HTTP ${response.status})${reason ? `: ${reason}` : ""}`, {
      status: response.status,
      code: code ?? undefined,
      reason: reason ?? undefined,
    });
  }

  if (parseFailed) {
    throw new ApiError("malformed", "Respons server bukan JSON yang valid.");
  }

  try {
    return expect(payload);
  } catch (cause) {
    throw new ApiError("malformed", "Respons server tidak sesuai bentuk yang diharapkan.", {
      cause,
    });
  }
}

/* ---------- Validator bentuk kontrak (melampirkan ApiError malformed) ---------- */

const asRecord = (value: unknown, message: string): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(message);
  }
  return value as Record<string, unknown>;
};

const asArray = (value: unknown, message: string): unknown[] => {
  if (!Array.isArray(value)) {
    throw new TypeError(message);
  }
  return value;
};

const num = (row: Record<string, unknown>, key: string): number => {
  const v = row[key];
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new TypeError(`Field ${key} harus number`);
  }
  return v;
};

const str = (row: Record<string, unknown>, key: string): string => {
  const v = row[key];
  if (typeof v !== "string") {
    throw new TypeError(`Field ${key} harus string`);
  }
  return v;
};

const isoDate = (row: Record<string, unknown>, key: string): string => {
  const v = str(row, key);
  if (!/^\d{4}-\d{2}-\d{2}/.test(v)) {
    throw new TypeError(`Field ${key} harus tanggal ISO`);
  }
  return v;
};

function parseKpi(value: unknown): Kpi {
  const r = asRecord(value, "KPI harus object");
  return {
    total_revenue: num(r, "total_revenue"),
    total_quantity: num(r, "total_quantity"),
    total_transactions: num(r, "total_transactions"),
    average_transaction_value: num(r, "average_transaction_value"),
    date_range_start: isoDate(r, "date_range_start"),
    date_range_end: isoDate(r, "date_range_end"),
  };
}

function parseDaily(value: unknown): DailyRevenuePoint[] {
  return asArray(value, "Revenue harus array").map((item) => {
    const r = asRecord(item, "Titik revenue harus object");
    return {
      date: isoDate(r, "date"),
      revenue: num(r, "revenue"),
      quantity: num(r, "quantity"),
      transactions: num(r, "transactions"),
    };
  });
}

function parseProducts(value: unknown): ProductRevenue[] {
  return asArray(value, "Products harus array").map((item) => {
    const r = asRecord(item, "Baris product harus object");
    return { product: str(r, "product"), revenue: num(r, "revenue"), quantity: num(r, "quantity") };
  });
}

function parseCities(value: unknown): CityRevenue[] {
  return asArray(value, "Cities harus array").map((item) => {
    const r = asRecord(item, "Baris city harus object");
    return { city: str(r, "city"), revenue: num(r, "revenue"), quantity: num(r, "quantity") };
  });
}

function parseMonthly(value: unknown): MonthlyRevenue[] {
  return asArray(value, "Monthly harus array").map((item) => {
    const r = asRecord(item, "Baris monthly harus object");
    return {
      month: isoDate(r, "month"),
      revenue: num(r, "revenue"),
      quantity: num(r, "quantity"),
      transactions: num(r, "transactions"),
    };
  });
}

function parseAnomalies(value: unknown): AnomalyDay[] {
  return asArray(value, "Anomalies harus array").map((item) => {
    const r = asRecord(item, "Baris anomaly harus object");
    const isAnomaly = r.is_anomaly;
    if (typeof isAnomaly !== "boolean") {
      throw new TypeError("Field is_anomaly harus boolean");
    }
    return {
      date: isoDate(r, "date"),
      revenue: num(r, "revenue"),
      quantity: num(r, "quantity"),
      transactions: num(r, "transactions"),
      anomaly_score_label: num(r, "anomaly_score_label"),
      is_anomaly: isAnomaly,
    };
  });
}

function parseForecast(value: unknown): ForecastResponse {
  const r = asRecord(value, "Forecast harus object");
  return {
    model: str(r, "model"),
    features: asArray(r.features, "features harus array").map((f) => String(f)),
    last_history_date: isoDate(r, "last_history_date"),
    days: num(r, "days"),
    predictions: asArray(r.predictions, "predictions harus array").map((item) => {
      const p = asRecord(item, "Titik forecast harus object");
      return { date: isoDate(p, "date"), predicted_revenue: num(p, "predicted_revenue") };
    }),
  };
}

function parseChat(value: unknown): ChatResponse {
  const r = asRecord(value, "Chat response harus object");
  return {
    answer: str(r, "answer"),
    tools_used: asArray(r.tools_used, "tools_used harus array").map((t) => String(t)),
    session_id: str(r, "session_id"),
  };
}

function parseRagSearch(value: unknown): RagSearchResponse {
  const r = asRecord(value, "RAG response harus object");
  const out: RagSearchResponse = {
    query: str(r, "query"),
    results: asArray(r.results, "results harus array").map((item) => {
      const row = asRecord(item, "Hasil RAG harus object");
      return {
        source: typeof row.source === "string" ? row.source : null,
        chunk_id: typeof row.chunk_id === "string" ? row.chunk_id : null,
        document_type: typeof row.document_type === "string" ? row.document_type : null,
        content: str(row, "content"),
        score: num(row, "score"),
      };
    }),
  };
  if (typeof r.message === "string") out.message = r.message;
  return out;
}

function parseRuns(value: unknown): AgentRunListResponse {
  const r = asRecord(value, "Runs response harus object");
  return {
    session_id: str(r, "session_id"),
    count: num(r, "count"),
    runs: asArray(r.runs, "runs harus array").map((item) => {
      const row = asRecord(item, "Baris run harus object");
      return {
        run_id: num(row, "run_id"),
        session_id: str(row, "session_id"),
        user_message: str(row, "user_message"),
        assistant_message: typeof row.assistant_message === "string" ? row.assistant_message : null,
        tools_used: asArray(row.tools_used, "tools_used harus array").map((t) => String(t)),
        status: str(row, "status"),
        error_type: typeof row.error_type === "string" ? row.error_type : null,
        latency_ms: typeof row.latency_ms === "number" ? row.latency_ms : null,
        model_name: typeof row.model_name === "string" ? row.model_name : null,
        created_at: str(row, "created_at"),
      };
    }),
  };
}

function parseHealth(value: unknown): Health {
  const r = asRecord(value, "Health harus object");
  return {
    status: str(r, "status"),
    database: str(r, "database"),
    tables: Object.fromEntries(
      Object.entries(
        asRecord(r.tables ?? {}, "tables harus object"),
      ).map(([table, rows]) => [table, Number(rows)]),
    ),
  };
}

/* ---------- Endpoint publik ---------- */

/** GET /api/health - heartbeat untuk indikator status sistem di UI. */
export function getHealth(signal?: AbortSignal): Promise<Health> {
  return request("/api/health", parseHealth, { timeoutMs: 10_000, signal });
}

export function getKpi(signal?: AbortSignal): Promise<Kpi> {
  return request("/api/analytics/kpi", parseKpi, { signal });
}

export function getDailyRevenue(signal?: AbortSignal): Promise<DailyRevenuePoint[]> {
  return request("/api/analytics/revenue", parseDaily, { signal });
}

export function getTopProducts(signal?: AbortSignal): Promise<ProductRevenue[]> {
  return request("/api/analytics/products", parseProducts, { signal });
}

export function getCityRevenue(signal?: AbortSignal): Promise<CityRevenue[]> {
  return request("/api/analytics/cities", parseCities, { signal });
}

export function getMonthlyRevenue(signal?: AbortSignal): Promise<MonthlyRevenue[]> {
  return request("/api/analytics/monthly", parseMonthly, { signal });
}

export function getAnomalies(signal?: AbortSignal): Promise<AnomalyDay[]> {
  return request("/api/analytics/anomalies", parseAnomalies, { signal });
}

/** Prediksi N hari ke depan (days 1-30). 503 -> ApiError server
 *  code="forecast_model_unavailable" (state UI khusus, bukan crash). */
export function getRevenueForecast(days = 7, signal?: AbortSignal): Promise<ForecastResponse> {
  return request(`/api/forecast/revenue?days=${days}`, parseForecast, { timeoutMs: 30_000, signal });
}

/** Tanya AI agent. Latency LLM tinggi (p95 ~24s) -> timeout panjang. */
export function sendChat(req: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
  return request("/api/chat", parseChat, { method: "POST", body: req, timeoutMs: 120_000, signal });
}

/** Debug retrieval RAG tanpa LLM. */
export function searchKnowledge(query: string, topK = 4, signal?: AbortSignal): Promise<RagSearchResponse> {
  return request("/api/rag/search", parseRagSearch, {
    method: "POST",
    body: { query, top_k: topK },
    signal,
  });
}

export function getAgentRuns(sessionId: string, limit = 10, signal?: AbortSignal): Promise<AgentRunListResponse> {
  return request(`/api/agent/runs/${encodeURIComponent(sessionId)}?limit=${limit}`, parseRuns, { signal });
}

/* ---------- Util kontrak chat ---------- */

/**
 * Kutipan RAG ada DI DALAM answer sebagai [file.md] (kontrak agent Phase 3),
 * bukan field terpisah. Ekstrak unik, jaga urutan kemunculan pertama.
 */
const CITATION_PATTERN = /\[([A-Za-z0-9_-]+\.md)\]/g;

export function parseCitations(answer: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const match of answer.matchAll(CITATION_PATTERN)) {
    const doc = match[1];
    if (!seen.has(doc)) {
      seen.add(doc);
      out.push(doc);
    }
  }
  return out;
}

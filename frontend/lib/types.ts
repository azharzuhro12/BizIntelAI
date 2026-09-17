/**
 * Tipe respons API BizIntel AI - mengikuti skema Pydantic di
 * backend/app/schemas.py secara 1:1 (audit kontrak Phase 6).
 * Field tanggal dikirim backend sebagai "YYYY-MM-DD" (date ISO pendek).
 */

export type IsoDate = string;

/** GET /api/analytics/kpi */
export interface Kpi {
  total_revenue: number;
  total_quantity: number;
  total_transactions: number;
  average_transaction_value: number;
  date_range_start: IsoDate;
  date_range_end: IsoDate;
}

/** GET /api/analytics/revenue - satu baris per hari */
export interface DailyRevenuePoint {
  date: IsoDate;
  revenue: number;
  quantity: number;
  transactions: number;
}

/** GET /api/analytics/products - terurut revenue desc */
export interface ProductRevenue {
  product: string;
  revenue: number;
  quantity: number;
}

/** GET /api/analytics/cities */
export interface CityRevenue {
  city: string;
  revenue: number;
  quantity: number;
}

/** GET /api/analytics/monthly - month = tanggal awal bulan */
export interface MonthlyRevenue {
  month: IsoDate;
  revenue: number;
  quantity: number;
  transactions: number;
}

/** GET /api/analytics/anomalies - label IsolationForest per hari */
export interface AnomalyDay {
  date: IsoDate;
  revenue: number;
  quantity: number;
  transactions: number;
  anomaly_score_label: number;
  is_anomaly: boolean;
}

export interface ForecastPoint {
  date: IsoDate;
  predicted_revenue: number;
}

/** GET /api/forecast/revenue?days=N (503 forecast_model_unavailable) */
export interface ForecastResponse {
  model: string;
  features: string[];
  last_history_date: IsoDate;
  days: number;
  predictions: ForecastPoint[];
}

/** POST /api/chat */
export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  tools_used: string[];
  session_id: string;
}

export interface AgentRunRecord {
  run_id: number;
  session_id: string;
  user_message: string;
  assistant_message: string | null;
  tools_used: string[];
  status: string;
  error_type: string | null;
  latency_ms: number | null;
  model_name: string | null;
  created_at: string;
}

/** GET /api/agent/runs/{session_id} */
export interface AgentRunListResponse {
  session_id: string;
  count: number;
  runs: AgentRunRecord[];
}

/** GET /api/health - heartbeat backend + koneksi database */
export interface Health {
  status: string;
  database: string;
  tables: Record<string, number>;
}

/** POST /api/rag/search (debug retrieval) */
export interface RagSearchResult {
  source: string | null;
  chunk_id: string | null;
  document_type: string | null;
  content: string;
  score: number;
}

export interface RagSearchResponse {
  query: string;
  results: RagSearchResult[];
  message?: string;
}

/** Satu pesan percakapan di panel chat (state UI lokal). */
export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  /** Hanya untuk role=assistant: nama tool yang dipanggil agent. */
  toolsUsed?: string[];
  /** Hanya untuk role=assistant: dokumen .md yang dikutip jawaban. */
  citations?: string[];
}

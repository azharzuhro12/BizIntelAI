# AI Agent — Phase 1: SQL Analytics Tool

Ditambahkan 2026-09-16. Satu agent LangGraph + 6 tool analitik read-only
di atas PostgreSQL. **Bukan** RAG/MCP/multi-agent (ditunda ke fase berikutnya).

## Arsitektur

```
User → POST /api/chat (FastAPI)
     → LangGraph agent (LLM memilih tool)
     → SQL analytics tools (read-only, whitelisted)
     → PostgreSQL (sales / daily_metrics / v_monthly_metrics)
     → hasil tool kembali ke LLM
     → jawaban bisnis {answer, tools_used}
```

Struktur file:

```
backend/app/agent/
├── __init__.py
├── llm.py     # resolusi kredensial LLM dari environment (tanpa hardcode)
├── state.py   # AgentState: messages + tools_used (TypedDict)
├── tools.py   # 6 tool read-only (registry AGENT_TOOLS)
└── graph.py   # StateGraph: agent → tools → agent → … → END
backend/app/routers/chat.py   # POST /api/chat
backend/tests/test_agent.py   # 19 test deterministik (LLM dipalsukan)
docs/agent-phase1.md          # dokumen ini
```

## Workflow LangGraph

Loop ReAct sederhana (dua node):

- **agent** — LLM dengan tools ter-bind; memutuskan memanggil tool atau
  menjawab langsung (pertanyaan umum → tanpa tool).
- **tools** — mengeksekusi tiap tool call lewat registry, mencatat
  `state.tools_used`, mengubah exception menjadi `ToolMessage` `TOOL_ERROR`
  yang aman (detail asli hanya ke log server).

```
START → agent → (ada tool_calls?) --ya→ tools → agent → …
                └─(tidak ada)→ END
```

State: `AgentState(TypedDict)` — `messages` (reducer `add_messages`) dan
`tools_used` (append-only). Batas loop: `recursion_limit=24`.

## Tools tersedia

| Tool | Parameter | Sumber |
|---|---|---|
| `get_kpi()` | — | agregat `sales` |
| `get_revenue_by_period(start_date, end_date)` | `YYYY-MM-DD`, opsional | `daily_metrics` |
| `get_revenue_by_product()` | — | `sales` GROUP BY product |
| `get_revenue_by_city()` | — | `sales` GROUP BY city |
| `get_monthly_revenue()` | — | view `v_monthly_metrics` |
| `get_anomalies()` | — | `daily_metrics` WHERE is_anomaly |

Semua tool membungkus `backend/app/services/analytics_service.py` (query yang
sama dengan endpoint `/api/analytics/*`).

## Keamanan / read-only SQL

1. **Tidak ada tool SQL mentah.** Tidak ada `execute_sql`; LLM hanya bisa
   memilih nama tool + parameter bisnis. Parameter di luar schema tool
   diabaikan (tidak pernah diteruskan ke query).
2. **Query tetap + parameterized.** Teks SQL didefinisikan di
   `analytics_service.py`, nilai dikirim via named params psycopg2 — tidak
   ada jalur SQL injection dari pesan/parameter user.
3. **Hanya SELECT** terhadap `sales`/`daily_metrics`/`v_monthly_metrics`;
   INSERT/UPDATE/DELETE/DROP/ALTER/CREATE tidak mungkin dilakukan agent.
4. **Grounding.** System prompt melarang mengarang angka; jika data tidak
   tersedia agent harus menjawab: *"Data yang diperlukan tidak tersedia pada
   database saat ini."*
5. **Error aman.** Kegagalan DB/tool → `TOOL_ERROR` generik ke LLM (tanpa
   host/user/password), detail lengkap hanya di log server
   (`logging` `bizintel.agent`). Kredensial tidak pernah dikembalikan ke
   response API.

## Environment variables

Tidak ada kredensial di kode. Sumber nilai: env var proses → file `.env`
root project.

| Variabel | Fungsi |
|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | kredensial provider anthropic (salah satu) |
| `ANTHROPIC_API_URL` / `ANTHROPIC_BASE_URL` | opsional, endpoint Anthropic-compatible |
| `ANTHROPIC_MODEL` | opsional, nama model |
| `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`, `OPENAI_MODEL`) | alternatif provider openai — butuh `langchain-openai` (belum di requirements) |

Machine ini memakai provider **anthropic-compatible** (endpoint relay,
model `glm-5.3`) yang dibaca dari env shell profile pengguna. Tanpa
kredensial apa pun, `POST /api/chat` mengembalikan **503**
`llm_not_configured` + petunjuk — bukan crash.

## Contoh

```bash
curl -X POST http://127.0.0.1:8020/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Berapa total revenue?"}'
# → {"answer": "Total revenue adalah 769.515,86 …", "tools_used": ["get_kpi"]}
```

Pemetaan pertanyaan → tool (terverifikasi live):

| Pertanyaan | Tool |
|---|---|
| Berapa total revenue? | `get_kpi` |
| Produk mana revenue terbesar? | `get_revenue_by_product` |
| Berapa revenue Lisbon? | `get_revenue_by_city` |
| Bandingkan November dan Desember | `get_monthly_revenue` |
| Apakah ada anomaly? | `get_anomalies` |
| Hello | — (tanpa tool) |

## Testing

`backend/tests/test_agent.py` — deterministik (LLM diganti `ScriptedLLM`
ber-script; PostgreSQL nyata untuk angka). Mencakup: pemilihan tool per
pertanyaan, grounding angka tervalidasi, greeting tanpa tool, error DB →
`TOOL_ERROR` aman, parameter liar diabaikan + DB utuh, injeksi SQL via
pesan tidak menyentuh DB, kontrak endpoint `/api/chat` (200/503/502/422).

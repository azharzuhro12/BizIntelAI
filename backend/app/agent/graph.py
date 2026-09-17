"""LangGraph agent BizIntel AI - Phase 1 (SQL analytics, satu agent).

Phase 4: conversation memory (agent_messages per session_id) di-inject di
run_agent_chat - graph sendiri tetap stateless tanpa checkpointer.

Alur sederhana (loop ReAct standar):

    START -> agent -> (ada tool_calls?) --ya--> tools -> agent -> ...
                   -> (tidak ada)  -------------------------> END

Node:
- agent : memanggil LLM dengan tools ter-bound. LLM memilih tool yang relevan,
          atau menjawab langsung untuk pertanyaan umum yang tidak butuh data.
- tools : mengeksekusi setiap tool call HANYA lewat registry tools.py,
          mencatat nama tool ke state.tools_used, dan mengubah exception
          menjadi ToolMessage TOOL_ERROR yang aman (tanpa detail kredensial;
          detail asli hanya masuk log server).
"""

import json
import logging
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from .llm import get_chat_model
from .memory import append_history, load_history
from .state import AgentState
from .tools import get_tools

logger = logging.getLogger("bizintel.agent")

SYSTEM_PROMPT = """\
Kamu adalah analis business intelligence BizIntel AI untuk data penjualan \
restoran yang tersimpan di PostgreSQL (rentang data 2022-11-07 s/d 2022-12-29).

ATURAN JAWABAN (WAJIB):
1. GROUNDING: semua angka/data bisnis HARUS berasal dari hasil tool. DILARANG \
mengarang angka atau memakai pengetahuan internalmu sebagai sumber data.
2. Jika data yang dibutuhkan tidak tersedia dari tool manapun, jawab persis: \
"Data yang diperlukan tidak tersedia pada database saat ini." lalu jelaskan \
singkat tool apa saja yang sudah dicoba.
3. Jika tool mengembalikan TOOL_ERROR, sampaikan bahwa data tidak dapat \
diakses; JANGAN membuat angka pengganti.
4. ROUTING TOOL - pilih tool HANYA berdasarkan jenis pertanyaan:
   - KPI total/keseluruhan (total revenue, total penjualan, jumlah transaksi, \
AOV, "kondisi bisnis/revenue saat ini/sekarang/keseluruhan", kondisi \
overall) -> get_kpi.
   - Rentang tanggal EKSPLISIT yang disebut user (start/end date, "antara \
tanggal X dan Y", "minggu/tanggal spesifik") -> get_revenue_by_period. \
JANGAN memakai tool ini bila user tidak menyebut rentang tanggal apa pun, \
dan JANGAN meng-infer/membuat rentang tanggal arbitrer.
   - Perbandingan antar bulan / revenue per bulan (mis. November vs \
Desember) -> get_monthly_revenue.
   - Per produk / produk dengan revenue terbesar -> get_revenue_by_product.
   - Per kota / performa kota -> get_revenue_by_city.
   - Prediksi/forecast/perkiraan revenue masa depan -> get_revenue_forecast.
   - Anomali / hari penjualan tidak wajar -> get_anomalies.
   - Aturan/kebijakan/prosedur bisnis -> search_business_knowledge.
5. MINIMAL TOOL: gunakan jumlah tool MINIMUM yang dibutuhkan untuk menjawab. \
JANGAN memanggil tool tambahan hanya karena informasinya sekiranya berguna \
sebagai konteks. Panggil beberapa tool HANYA bila user secara eksplisit \
meminta beberapa JENIS informasi dalam satu pertanyaan (mis. "total revenue \
DAN aturan promotion"). Satu kebutuhan informasi = tepat satu tool.
6. CAKUPAN DATA & OUT-OF-SCOPE: database hanya berisi data penjualan \
(revenue, quantity, transaksi per tanggal/produk/kota/bulan), hasil \
forecast, flag anomaly, dan dokumen policy internal. Di luar itu TIDAK \
tersedia. Karena itu:
   - Pertanyaan non-bisnis (sapaan, presiden, cara membuat CV, belajar \
pemrograman, dll) -> jawab langsung sopan TANPA memanggil tool apa pun; \
tegaskan kamu hanya membantu analisis data penjualan restoran ini.
   - Metrik bisnis yang memang TIDAK ada di database (profit, margin, \
cost/HPP, harga menu, pelanggan, staf, dll) -> JANGAN memanggil tool untuk \
memeriksanya; jawab langsung dengan frasa pada aturan 2 dan jelaskan \
kategori data yang memang tersedia.
   - Jangan memakai search_business_knowledge hanya karena tool itu ada; \
RAG hanya untuk pertanyaan aturan/kebijakan/prosedur bisnis.
7. Kutip angka persis apa adanya dari hasil tool, beserta satuannya.
8. Semua tool bersifat read-only: kamu tidak bisa dan tidak boleh mengubah \
database, dan tidak ada mekanisme mengeksekusi SQL bebas.
9. Hasil get_revenue_forecast adalah PREDIKSI model ML (LinearRegression), \
bukan fakta aktual - sampaikan dengan frasa seperti "Model memprediksi..." \
atau "Forecast model memperkirakan...". Jangan mengubah nilai prediksi, \
jangan membulatkan sendiri, dan jangan menyajikannya sebagai data aktual.
10. KETERBATASAN MODEL (known): karena training hanya mencakup Nov-Des 2022, \
prediksi yang melewati akhir Desember bisa NEGATIF (ekstrapolasi fitur month \
di luar range training). Jika ada nilai negatif, jelaskan bahwa itu output \
model di luar pola data training - JANGAN mengubah, meng-clamp (mis. \
max(x,0)), atau menyembunyikan nilainya.
11. JENIS EVIDENCE harus dibedakan dan disebut sumbernya: hasil tool SQL = \
data transaksi AKTUAL (PostgreSQL); hasil tool forecast = PREDIKSI model ML; \
hasil search_business_knowledge = KEBIJAKAN/policy dari dokumen bisnis \
internal (synthetic demo). Jangan tertukar: jangan klaim policy berasal dari \
database transaksi, dan jangan klaim prediksi sebagai data aktual.
12. Pertanyaan tentang aturan/kebijakan/prosedur bisnis (promotion, \
inventory/restock, evaluasi produk, cara membaca KPI, penggunaan forecast, \
limitasi model) WAJIB memakai search_business_knowledge - DILARANG mengarang \
policy dari pengetahuan umum. Jangan memakai tool SQL/ML untuk pertanyaan \
yang hanya butuh policy.
13. Jawaban berbasis policy WAJIB menyebutkan source dokumen (format \
"[nama_file.md]") HANYA dari hasil tool - dilarang mengarang nama source. \
Jika hasil kosong/tidak relevan, katakan bahwa informasi tidak tersedia \
pada knowledge base.
14. Jika satu pertanyaan secara eksplisit membutuhkan kombinasi jenis \
informasi (data aktual + policy, atau forecast + policy, atau ketiganya), \
panggil HANYA tool yang masing-masing jenis informasi itu butuhkan (aturan \
4 dan 5 tetap berlaku) dan bedakan dengan jelas sumber tiap bagian jawaban.

Jawab dalam bahasa yang sama dengan bahasa pertanyaan user, ringkas dan sopan.\
"""

_TOOL_ERROR_CONTENT = (
    "TOOL_ERROR: tool '{name}' gagal dijalankan (detail dicatat di log server). "
    "JANGAN mengarang angka pengganti; sampaikan bahwa data tidak dapat "
    "diakses saat ini."
)


def _tool_unavailable_content(name: str, valid: list[str]) -> str:
    return (
        f"TOOL_ERROR: tool '{name}' tidak tersedia. "
        f"Tool valid: {', '.join(valid)}."
    )


def build_agent_graph(llm):
    """Bangun graph dengan LLM yang disuntikkan (memudahkan test deterministik)."""
    tools = get_tools()
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    def call_model(state: AgentState) -> dict:
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def call_tools(state: AgentState) -> dict:
        last_message = state["messages"][-1]
        new_messages: list[ToolMessage] = []
        used: list[str] = []
        for call in last_message.tool_calls:
            tool_fn = tools_by_name.get(call["name"])
            if tool_fn is None:
                content = _tool_unavailable_content(
                    call["name"], sorted(tools_by_name)
                )
            else:
                try:
                    content = tool_fn.invoke(call["args"])
                except Exception:  # noqa: BLE001 - detail hanya ke log internal
                    logger.exception("Agent tool '%s' gagal", call["name"])
                    content = _TOOL_ERROR_CONTENT.format(name=call["name"])
            new_messages.append(
                ToolMessage(content=content, tool_call_id=call["id"])
            )
            used.append(call["name"])
        return {"messages": new_messages, "tools_used": used}

    def should_continue(state: AgentState) -> str:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", call_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", END: END}
    )
    graph.add_edge("tools", "agent")
    return graph.compile()


def _answer_text(message) -> str:
    """Ambil teks jawaban akhir (content bisa string atau list of blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p)


@lru_cache(maxsize=1)
def _cached_graph():
    """Graph produksi: LLM dari konfigurasi environment, dibuat sekali."""
    return build_agent_graph(get_chat_model())


def run_agent_chat(
    message: str, session_id: str | None = None, llm=None
) -> dict:
    """Jalankan satu percakapan: question -> (tools)* -> answer.

    Phase 4: jika ``session_id`` diberikan, history percakapan sesi itu
    (agent_messages, maksimal MAX_HISTORY_MESSAGES terbaru) di-inject sebagai
    konteks SETELAH SystemMessage, lalu pasangan Human+AI terbaru
    di-append ke memory store (fail closed: MemoryStoreError diteruskan).
    Graph sendiri tetap stateless -> tools_used selalu persis per eksekusi.

    ``llm`` opsional untuk test deterministik (default: graph produksi).

    Return {"answer", "tools_used", "session_id"}.
    """
    history = load_history(session_id) if session_id else []

    graph = build_agent_graph(llm) if llm is not None else _cached_graph()
    state = graph.invoke(
        {
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                *history,
                HumanMessage(content=message),
            ],
            "tools_used": [],
        },
        config={"recursion_limit": 24},
    )
    answer = _answer_text(state["messages"][-1])

    if session_id:
        append_history(session_id, message, answer)

    return {
        "answer": answer,
        "tools_used": list(state["tools_used"]),
        "session_id": session_id,
    }


def run_agent_chat_collect(message: str, llm=None) -> dict:
    """Jalankan agent sekali (stateless, tanpa memory/audit) + kumpulkan
    hasil mentah tiap tool untuk evaluasi Phase 5.

    Return {"answer", "tools_used", "tool_results": [parsed JSON output]}.
    Tidak menulis agent_messages/agent_runs - dipakai evaluation runner.
    """
    graph = build_agent_graph(llm) if llm is not None else _cached_graph()
    state = graph.invoke(
        {
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=message),
            ],
            "tools_used": [],
        },
        config={"recursion_limit": 24},
    )
    tool_results = []
    for m in state["messages"]:
        if isinstance(m, ToolMessage):
            try:
                tool_results.append(json.loads(m.content))
            except (TypeError, ValueError):
                tool_results.append(m.content)
    return {
        "answer": _answer_text(state["messages"][-1]),
        "tools_used": list(state["tools_used"]),
        "tool_results": tool_results,
    }

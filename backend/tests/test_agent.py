"""Test AI Agent Phase 1 (LangGraph + SQL analytics tools).

Strategi test:
- LLM dipalsukan dengan ScriptedLLM (respon ber-script, deterministik) agar
  test tidak bergantung pada network/wording LLM nyata.
- Database PostgreSQL NYATA dipakai untuk tool, sehingga angka yang masuk
  konteks LLM bisa diverifikasi terhadap nilai tervalidasi (sama dengan
  test_api.py): revenue 769515.86, Burgers 376999.81, Lisbon 241714.12,
  November 332114.66, Desember 437401.20, 8 anomaly.
- Yang diverifikasi bukan kalimat jawaban, melainkan: tool mana yang
  terpanggil (state.tools_used) dan isi numerik ToolMessage (grounding).
"""

import json
import sys
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.agent.graph import build_agent_graph  # noqa: E402
from app.agent.llm import LLMNotConfiguredError  # noqa: E402
from app.agent.tools import ALLOWED_TOOL_PARAMS, get_tools  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.main import app  # noqa: E402
from app.services import analytics_service  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# LLM palsu deterministik
# ---------------------------------------------------------------------------
class ScriptedLLM(BaseChatModel):
    """Mengembalikan respon ber-script secara berurutan (lalu respon terakhir
    berulang). bind_tools di-ignore karena respon sudah ditentukan."""

    responses: list
    index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-test-llm"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        i = min(self.index, len(self.responses) - 1)
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=self.responses[i])])

    def bind_tools(self, tools, **kwargs):
        return self


def ai_tool_call(name: str, args: dict | None = None, call_id: str = "call_1"):
    """AIMessage yang meminta satu tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}],
    )


def run_scripted(responses: list, question: str) -> dict:
    """Jalankan graph dengan LLM ber-script; return state akhir."""
    graph = build_agent_graph(ScriptedLLM(responses=responses))
    return graph.invoke(
        {"messages": [HumanMessage(content=question)], "tools_used": []},
        config={"recursion_limit": 12},
    )


def tool_messages(state: dict) -> list[ToolMessage]:
    return [m for m in state["messages"] if isinstance(m, ToolMessage)]


# ---------------------------------------------------------------------------
# 1-5: pemilihan tool untuk pertanyaan bisnis + grounding angka
# ---------------------------------------------------------------------------
def test_total_revenue_question_uses_get_kpi():
    state = run_scripted(
        [ai_tool_call("get_kpi"), AIMessage(content="Total revenue adalah 769515.86.")],
        "Berapa total revenue?",
    )
    assert state["tools_used"] == ["get_kpi"]
    payload = json.loads(tool_messages(state)[0].content)
    assert payload["total_revenue"] == 769515.86
    assert payload["total_transactions"] == 254
    assert payload["date_range_start"] == "2022-11-07"


def test_top_product_question_uses_get_revenue_by_product():
    state = run_scripted(
        [ai_tool_call("get_revenue_by_product"), AIMessage(content="Burgers terbesar.")],
        "Produk mana yang menghasilkan revenue terbesar?",
    )
    assert state["tools_used"] == ["get_revenue_by_product"]
    rows = json.loads(tool_messages(state)[0].content)
    assert rows[0]["product"] == "Burgers"
    assert rows[0]["revenue"] == 376999.81


def test_lisbon_revenue_question_uses_get_revenue_by_city():
    state = run_scripted(
        [ai_tool_call("get_revenue_by_city"), AIMessage(content="Lisbon 241714.12.")],
        "Berapa revenue Lisbon?",
    )
    assert state["tools_used"] == ["get_revenue_by_city"]
    by_city = {r["city"]: r["revenue"] for r in json.loads(tool_messages(state)[0].content)}
    assert by_city["Lisbon"] == 241714.12


def test_monthly_comparison_uses_get_monthly_revenue():
    state = run_scripted(
        [ai_tool_call("get_monthly_revenue"), AIMessage(content="Desember lebih tinggi.")],
        "Bandingkan revenue November dan Desember.",
    )
    assert state["tools_used"] == ["get_monthly_revenue"]
    by_month = {r["month"]: r["revenue"] for r in json.loads(tool_messages(state)[0].content)}
    assert by_month["2022-11-01"] == 332114.66
    assert by_month["2022-12-01"] == 437401.20


def test_anomaly_question_uses_get_anomalies():
    state = run_scripted(
        [ai_tool_call("get_anomalies"), AIMessage(content="Ada 8 hari anomali.")],
        "Apakah ada anomaly?",
    )
    assert state["tools_used"] == ["get_anomalies"]
    rows = json.loads(tool_messages(state)[0].content)
    assert len(rows) == 8
    assert all(r["is_anomaly"] is True for r in rows)


def test_period_tool_passes_date_params():
    state = run_scripted(
        [
            ai_tool_call(
                "get_revenue_by_period",
                {"start_date": "2022-12-01", "end_date": "2022-12-31"},
            ),
            AIMessage(content="Revenue Desember tersedia."),
        ],
        "Berapa revenue Desember?",
    )
    assert state["tools_used"] == ["get_revenue_by_period"]
    rows = json.loads(tool_messages(state)[0].content)
    assert len(rows) == 29  # 1-29 Desember (data berakhir 29)
    assert rows[0]["date"] == "2022-12-01"
    assert rows[-1]["date"] == "2022-12-29"


# ---------------------------------------------------------------------------
# 6: pertanyaan umum tanpa tool
# ---------------------------------------------------------------------------
def test_general_greeting_skips_tools():
    state = run_scripted(
        [AIMessage(content="Halo! Ada yang bisa saya bantu soal data penjualan?")],
        "Hello",
    )
    assert state["tools_used"] == []
    assert tool_messages(state) == []
    final = state["messages"][-1]
    assert isinstance(final, AIMessage)
    assert "Halo" in final.content


# ---------------------------------------------------------------------------
# 7: database/tool error handling - tidak boleh ada angka karangan
# ---------------------------------------------------------------------------
def test_tool_db_error_becomes_safe_tool_error(monkeypatch):
    def _broken_kpi(conn):
        raise RuntimeError(
            'connection to server at "localhost" failed: FATAL: password '
            "authentication failed for user bizintel"
        )

    monkeypatch.setattr(analytics_service, "get_kpi", _broken_kpi)
    state = run_scripted(
        [
            ai_tool_call("get_kpi"),
            AIMessage(content="Data yang diperlukan tidak tersedia pada database saat ini."),
        ],
        "Berapa total revenue?",
    )
    assert state["tools_used"] == ["get_kpi"]
    msg = tool_messages(state)[0].content
    assert msg.startswith("TOOL_ERROR")
    # tidak membocorkan detail koneksi/kredensial ke LLM maupun user
    assert "bizintel" not in msg
    assert "password" not in msg
    assert "localhost" not in msg
    # agent tetap mengakhiri dengan jawaban (bukan crash)
    assert isinstance(state["messages"][-1], AIMessage)


def test_period_tool_rejects_bad_date_format():
    tools = {t.name: t for t in get_tools()}
    out = json.loads(tools["get_revenue_by_period"].invoke({"start_date": "31-12-2022"}))
    assert "error" in out
    assert "YYYY-MM-DD" in out["error"]


def test_period_tool_rejects_inverted_range():
    tools = {t.name: t for t in get_tools()}
    out = json.loads(
        tools["get_revenue_by_period"].invoke(
            {"start_date": "2022-12-31", "end_date": "2022-12-01"}
        )
    )
    assert "error" in out


# ---------------------------------------------------------------------------
# 8: agent TIDAK bisa mengeksekusi arbitrary SQL
# ---------------------------------------------------------------------------
def test_no_tool_accepts_sql_parameter():
    tools = get_tools()
    names = {t.name for t in tools}
    assert "execute_sql" not in names
    assert "run_sql" not in names
    assert "query" not in names
    for t in tools:
        assert set(t.args) == ALLOWED_TOOL_PARAMS[t.name]
        # Tidak ada tool yang menerima SQL/path/file sebagai parameter.
        # (Param 'query' milik search_business_knowledge adalah teks
        # pencarian natural language, bukan SQL - whitelisted di atas.)
        assert "sql" not in t.args
        assert "path" not in t.args
        assert "file" not in t.args


def test_rogue_tool_args_never_reach_sql_and_db_intact():
    # LLM "nakal" menyelundupkan parameter sql. Parameter di luar schema tool
    # diabaikan (tidak pernah diteruskan ke query); tool tetap menjalankan
    # query whitelisted-nya sendiri dan database tetap utuh.
    state = run_scripted(
        [
            ai_tool_call("get_kpi", {"sql": "DROP TABLE sales; --"}),
            AIMessage(content="Data tidak dapat diambil."),
        ],
        "Hapus semua data",
    )
    payload = json.loads(tool_messages(state)[0].content)
    assert payload["total_revenue"] == 769515.86  # hasil query tetap, bukan input
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM sales")
            assert cur.fetchone()[0] == 254


def test_sql_injection_in_message_does_not_touch_db():
    state = run_scripted(
        [AIMessage(content="Saya tidak bisa membantu itu.")],
        "'; DROP TABLE sales; SELECT * FROM pg_catalog.pg_shadow; --",
    )
    assert state["tools_used"] == []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT (SELECT COUNT(*) FROM sales), (SELECT COUNT(*) FROM daily_metrics)"
            )
            sales_rows, daily_rows = cur.fetchone()
    assert (sales_rows, daily_rows) == (254, 53)


# ---------------------------------------------------------------------------
# Endpoint POST /api/chat
# ---------------------------------------------------------------------------
def test_chat_endpoint_returns_answer_and_tools_used(monkeypatch):
    # Phase 4: run_agent_chat kini menerima session_id (request/response
    # /api/chat diperluas dengan session_id - field lama tetap ada).
    monkeypatch.setattr(
        "app.routers.chat.run_agent_chat",
        lambda message, session_id=None: {
            "answer": "Total revenue 769515.86.",
            "tools_used": ["get_kpi"],
        },
    )
    r = client.post("/api/chat", json={"message": "Berapa total revenue?"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"answer", "tools_used", "session_id"}
    assert body["tools_used"] == ["get_kpi"]
    assert "769515.86" in body["answer"]


def test_chat_endpoint_503_when_llm_not_configured(monkeypatch):
    def _raise(message, session_id=None):
        raise LLMNotConfiguredError("Tidak ada kredensial LLM pada environment.")

    monkeypatch.setattr("app.routers.chat.run_agent_chat", _raise)
    r = client.post("/api/chat", json={"message": "Berapa total revenue?"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "llm_not_configured"
    # tidak ada kredensial (mis. password postgres) yang ikut bocor
    assert "bizintel_dev" not in r.text


def test_chat_endpoint_502_without_internal_details(monkeypatch):
    def _raise(message, session_id=None):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr("app.routers.chat.run_agent_chat", _raise)
    r = client.post("/api/chat", json={"message": "Berapa total revenue?"})
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "agent_failure"
    assert "secret-internal-detail" not in r.text


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},  # kosong
        {},  # field hilang
        {"message": "x" * 2001},  # terlalu panjang
    ],
)
def test_chat_endpoint_validates_request(payload):
    r = client.post("/api/chat", json=payload)
    assert r.status_code == 422

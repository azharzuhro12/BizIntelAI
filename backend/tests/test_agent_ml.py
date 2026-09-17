"""Test AI Agent Phase 2 (ML analytics tools: forecast + anomaly).

Strategi sama dengan test_agent.py:
- LLM dipalsukan dengan ScriptedLLM (deterministik, tanpa network/wording).
- Service & DB nyata: nilai forecast deterministik karena artefak dan
  riwayat daily_metrics tetap (nilai acuan = output live endpoint Phase 1):
    days=3 -> 16533.84, 15924.91, -9007.63
    days=7 -> ... lanjut -10474.2, -11961.51, -13709.57, -15150.81
  (nilai negatif = known limitation ekstrapolasi; TIDAK boleh di-clamp)
"""

import json
import sys
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.graph import build_agent_graph  # noqa: E402
from app.agent.tools import get_tools  # noqa: E402
from app.services.forecast_service import (  # noqa: E402
    ForecastModelUnavailableError,
    MODEL_PATH,
)

TOOLS_BY_NAME = {t.name: t for t in get_tools()}

FORECAST_3 = [("2022-12-30", 16533.84), ("2022-12-31", 15924.91), ("2023-01-01", -9007.63)]
FORECAST_7_TAIL = [("2023-01-02", -10474.2), ("2023-01-03", -11961.51),
                   ("2023-01-04", -13709.57), ("2023-01-05", -15150.81)]


# ---------------------------------------------------------------------------
# LLM palsu deterministik (sama pola dengan test_agent.py)
# ---------------------------------------------------------------------------
class ScriptedLLM(BaseChatModel):
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


def ai_tool_call(name, args=None, call_id="call_1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}],
    )


def run_scripted(responses: list, question: str) -> dict:
    graph = build_agent_graph(ScriptedLLM(responses=responses))
    return graph.invoke(
        {"messages": [HumanMessage(content=question)], "tools_used": []},
        config={"recursion_limit": 12},
    )


def tool_messages(state: dict) -> list[ToolMessage]:
    return [m for m in state["messages"] if isinstance(m, ToolMessage)]


# ---------------------------------------------------------------------------
# Tool forecast - kontrak & nilai
# ---------------------------------------------------------------------------
def test_forecast_tool_days_3():
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": 3}))
    assert out["model"] == "revenue_forecasting_linear_regression"
    assert out["last_history_date"] == "2022-12-29"
    assert out["days"] == 3
    assert out["features"] == [
        "day_of_week", "day_of_month", "month", "is_weekend",
        "lag_1", "lag_7", "rolling_mean_7",
    ]
    assert [(p["date"], p["predicted_revenue"]) for p in out["predictions"]] == FORECAST_3


def test_forecast_tool_days_7():
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": 7}))
    assert len(out["predictions"]) == 7
    got = [(p["date"], p["predicted_revenue"]) for p in out["predictions"]]
    assert got[:3] == FORECAST_3
    assert got[3:] == FORECAST_7_TAIL


def test_forecast_tool_default_days_is_3():
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({}))
    assert out["days"] == 3
    assert len(out["predictions"]) == 3


@pytest.mark.parametrize("days", [0, 31, -1, 100])
def test_forecast_tool_rejects_invalid_days(days):
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": days}))
    assert "error" in out
    assert "1" in out["error"] and "30" in out["error"]
    assert "predictions" not in out  # tidak ada angka fallback


def test_forecast_tool_uses_correct_artifact():
    # Path artefak TIDAK berasal dari input user/LLM - konstanta service.
    assert MODEL_PATH.name == "revenue_forecasting_linear_regression.joblib"
    assert MODEL_PATH.exists()
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": 1}))
    # service memvalidasi feature_names_in_ artefak == forecast_features.joblib;
    # nilai yang cocok dengan output notebook membuktikan artefak yang benar.
    assert out["model"] == "revenue_forecasting_linear_regression"
    assert len(out["features"]) == 7  # model Quantity yang salah punya 18


def test_forecast_prediction_structure():
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": 5}))
    assert len(out["predictions"]) == 5
    for p in out["predictions"]:
        assert set(p) == {"date", "predicted_revenue"}
        assert isinstance(p["predicted_revenue"], float)
        # format tanggal ISO valid
        from datetime import date

        date.fromisoformat(p["date"])


def test_forecast_negative_values_are_not_clamped():
    """Known limitation: prediksi Januari negatif - harus apa adanya."""
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": 7}))
    values = [p["predicted_revenue"] for p in out["predictions"]]
    assert values[2:] == [-9007.63, -10474.2, -11961.51, -13709.57, -15150.81]
    assert any(v < 0 for v in values)  # tidak ada max(prediction, 0)


def test_forecast_tool_model_unavailable_returns_safe_error(monkeypatch):
    def _broken(days):
        raise ForecastModelUnavailableError("artefak tidak kompatibel: detail panjang")

    monkeypatch.setattr("app.agent.tools.forecast_revenue", _broken)
    out = json.loads(TOOLS_BY_NAME["get_revenue_forecast"].invoke({"days": 3}))
    assert out["error"] == "forecast_model_unavailable"
    assert "predictions" not in out  # tidak ada angka karangan/fallback


# ---------------------------------------------------------------------------
# Tool anomaly (regression Phase 1)
# ---------------------------------------------------------------------------
def test_anomaly_tool_still_works():
    rows = json.loads(TOOLS_BY_NAME["get_anomalies"].invoke({}))
    assert len(rows) == 8
    assert all(r["is_anomaly"] is True for r in rows)
    assert all(r["anomaly_score_label"] == -1 for r in rows)
    # jawaban "kapan anomaly & berapa revenue" terlayani dari kolom yang sama
    assert all({"date", "revenue"} <= set(r) for r in rows)


# ---------------------------------------------------------------------------
# Agent tool selection (deterministik via scripted tool calls)
# ---------------------------------------------------------------------------
def test_agent_selects_forecast_tool():
    state = run_scripted(
        [
            ai_tool_call("get_revenue_forecast", {"days": 3}),
            AIMessage(content="Model memprediksi revenue 3 hari ke depan."),
        ],
        "Berapa prediksi revenue 3 hari ke depan?",
    )
    assert state["tools_used"] == ["get_revenue_forecast"]
    payload = json.loads(tool_messages(state)[0].content)
    assert payload["days"] == 3
    assert payload["predictions"][0] == {"date": "2022-12-30", "predicted_revenue": 16533.84}


def test_agent_selects_anomaly_tool_for_anomaly_question():
    state = run_scripted(
        [
            ai_tool_call("get_anomalies"),
            AIMessage(content="Anomaly terjadi pada tanggal-tanggal berikut..."),
        ],
        "Pada tanggal berapa terjadi anomaly dan berapa revenue hari itu?",
    )
    assert state["tools_used"] == ["get_anomalies"]
    rows = json.loads(tool_messages(state)[0].content)
    assert len(rows) == 8


def test_agent_combines_kpi_and_forecast():
    """Pertanyaan gabungan -> dua tool dipanggil, keduanya grounded."""
    state = run_scripted(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_kpi", "args": {}, "id": "call_1", "type": "tool_call"},
                    {"name": "get_revenue_forecast", "args": {"days": 3},
                     "id": "call_2", "type": "tool_call"},
                ],
            ),
            AIMessage(content="Kondisi revenue saat ini dan prediksi model..."),
        ],
        "Bagaimana kondisi revenue dan forecast beberapa hari ke depan?",
    )
    assert state["tools_used"] == ["get_kpi", "get_revenue_forecast"]
    msgs = tool_messages(state)
    assert len(msgs) == 2
    kpi = json.loads(msgs[0].content)
    fc = json.loads(msgs[1].content)
    assert kpi["total_revenue"] == 769515.86
    assert fc["predictions"][0]["predicted_revenue"] == 16533.84


def test_forecast_tool_args_schema_only_days():
    """Security: parameter tool ML hanya 'days' - tidak ada sql/path/file."""
    t = TOOLS_BY_NAME["get_revenue_forecast"]
    assert set(t.args) == {"days"}
    assert t.args["days"]["type"] == "integer"

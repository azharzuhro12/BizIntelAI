"""Test AI Agent Phase 3 (RAG business knowledge tool).

Strategi:
- Retrieval diuji langsung terhadap ChromaDB lokal (embedding deterministik);
  query acuan dipilih yang terverifikasi stabil top-1 benar.
- Routing agent diuji dengan ScriptedLLM (deterministik, tanpa network).
- Knowledge base = dokumen SYNTHETIC/DEMO di data/knowledge/*.md
  (5 dokumen -> 21 chunk pada saat test ini ditulis).
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
from app.agent.tools import get_tools  # noqa: E402
from app.main import app  # noqa: E402
from app.rag.config import CHROMA_DIR, CHUNK_SIZE, COLLECTION_NAME  # noqa: E402
from app.rag.ingest import ingest_knowledge  # noqa: E402
from app.rag.loader import chunk_text, load_chunks  # noqa: E402
from app.rag.retriever import search_knowledge  # noqa: E402
from app.rag.vectorstore import get_collection  # noqa: E402

client = TestClient(app)

EXPECTED_SOURCES = {
    "sales_policy.md",
    "promotion_policy.md",
    "inventory_policy.md",
    "product_guidelines.md",
    "business_guidelines.md",
}

# Query terverifikasi stabil (top-1 benar + skor > threshold):
STABLE_QUERIES = {
    "promotion_policy.md": "Apa aturan promotion?",
    "inventory_policy.md": "Bagaimana aturan inventory dan kapan perlu restock?",
    "product_guidelines.md": "Bagaimana evaluasi product performance?",
    "business_guidelines.md": "Bagaimana manajemen membaca KPI?",
    "sales_policy.md": "Apa definisi revenue dan periode pelaporan?",
}


# ---------------------------------------------------------------------------
# LLM palsu deterministik (pola sama dengan test_agent.py / test_agent_ml.py)
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


def ai_multi_tool_calls(calls):
    return AIMessage(
        content="",
        tool_calls=[
            {"name": n, "args": a, "id": f"call_{i}", "type": "tool_call"}
            for i, (n, a) in enumerate(calls, start=1)
        ],
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
# Ingestion & vector store
# ---------------------------------------------------------------------------
def test_ingestion_idempotent():
    first = ingest_knowledge()
    assert first["status"] == "ok"
    assert first["documents"] == 5
    second = ingest_knowledge()  # ulang tidak menduplikasi
    collection = get_collection()
    assert collection is not None
    assert collection.name == COLLECTION_NAME
    assert collection.count() == first["chunks"] == second["chunks"]


def test_chroma_persisted_in_data_dir():
    assert (CHROMA_DIR).exists()
    assert get_collection() is not None
    assert get_collection().count() > 0


def test_chunk_metadata():
    chunks = load_chunks()
    assert len(chunks) == 21
    assert {c["metadata"]["source"] for c in chunks} == EXPECTED_SOURCES
    for c in chunks:
        meta = c["metadata"]
        assert meta["document_type"] == "business_policy"
        assert meta["chunk_id"] == c["id"]
        assert meta["chunk_id"].startswith(meta["source"] + "::")
        assert c["text"].strip()
        # tidak ada secret di metadata
        assert not any(k in meta for k in ("password", "api_key", "token"))


def test_chunking_bounds_deterministic_and_overlap():
    text = " ".join(f"token{i:03d}" for i in range(400))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= CHUNK_SIZE for c in chunks)
    assert chunk_text(text) == chunks  # deterministik
    # overlap: token akhir chunk[i] muncul lagi di chunk[i+1]
    for i in range(len(chunks) - 1):
        tail = chunks[i].split()[-3:]
        assert tail and all(t in chunks[i + 1].split() for t in tail)


# ---------------------------------------------------------------------------
# Retrieval quality (source benar, bukan sekadar HTTP 200)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("expected_source", sorted(STABLE_QUERIES))
def test_retrieval_returns_correct_source(expected_source):
    result = search_knowledge(STABLE_QUERIES[expected_source], top_k=3)
    assert result["query"] == STABLE_QUERIES[expected_source]
    assert result["results"], "harus ada hasil relevan"
    assert result["results"][0]["source"] == expected_source
    for r in result["results"]:
        assert set(r) == {"source", "chunk_id", "document_type", "content", "score"}
        assert r["source"] in EXPECTED_SOURCES  # tidak ada source karangan
        assert 0.0 <= r["score"] <= 1.0


def test_empty_retrieval_out_of_domain():
    result = search_knowledge("quantum entanglement submarine navigation", top_k=3)
    assert result["results"] == []
    assert result["message"] == "No relevant business knowledge found."


def test_empty_query_retrieval():
    result = search_knowledge("   ")
    assert result["results"] == []
    assert "message" in result


# ---------------------------------------------------------------------------
# Tool interface & security
# ---------------------------------------------------------------------------
def test_rag_tool_schema():
    tools = {t.name: t for t in get_tools()}
    assert "search_business_knowledge" in tools
    t = tools["search_business_knowledge"]
    assert set(t.args) == {"query", "top_k"}
    assert t.args["query"]["type"] == "string"
    assert t.args["top_k"]["type"] == "integer"
    # tidak ada parameter path/file/sql - tidak ada file access dari user
    assert not ({"path", "file", "sql"} & set(t.args))


def test_rag_tool_path_traversal_is_just_search_text():
    tools = {t.name: t for t in get_tools()}
    # query traversal diperlakukan sebagai teks pencarian biasa, bukan path
    out = json.loads(
        tools["search_business_knowledge"].invoke({"query": "../../.env"})
    )
    # tidak pernah mengembalikan isi file .env / kredensial apa pun
    assert "POSTGRES_PASSWORD" not in json.dumps(out)
    assert "bizintel_dev" not in json.dumps(out)
    for r in out["results"]:
        assert r["source"] in EXPECTED_SOURCES  # hanya dari knowledge dir


def test_rag_tool_returns_source_metadata():
    tools = {t.name: t for t in get_tools()}
    out = json.loads(
        tools["search_business_knowledge"].invoke({"query": "Apa aturan promotion?"})
    )
    assert out["results"]
    top = out["results"][0]
    assert top["source"] == "promotion_policy.md"
    assert top["chunk_id"].startswith("promotion_policy.md::")
    assert "content" in top and "score" in top


def test_rag_tool_empty_query():
    tools = {t.name: t for t in get_tools()}
    out = json.loads(tools["search_business_knowledge"].invoke({"query": ""}))
    assert out["results"] == []
    assert "message" in out


# ---------------------------------------------------------------------------
# Agent routing (deterministik via scripted tool calls)
# ---------------------------------------------------------------------------
def test_agent_routes_policy_question_to_rag():
    state = run_scripted(
        [
            ai_tool_call("search_business_knowledge", {"query": "aturan promotion"}),
            AIMessage(content="Berdasarkan promotion_policy.md, aturannya ..."),
        ],
        "Apa aturan promotion?",
    )
    assert state["tools_used"] == ["search_business_knowledge"]
    payload = json.loads(tool_messages(state)[0].content)
    assert payload["results"][0]["source"] == "promotion_policy.md"


def test_agent_combines_sql_and_rag():
    state = run_scripted(
        [
            ai_multi_tool_calls(
                [("get_kpi", {}), ("search_business_knowledge", {"query": "policy promotion"})]
            ),
            AIMessage(content="Revenue aktual 769515,86; menurut promotion_policy.md ..."),
        ],
        "Berapa revenue bulan ini dan berdasarkan policy promotion, apa yang perlu diperhatikan?",
    )
    assert state["tools_used"] == ["get_kpi", "search_business_knowledge"]
    msgs = tool_messages(state)
    assert "769515.86" in msgs[0].content  # data aktual dari SQL
    rag = json.loads(msgs[1].content)
    assert rag["results"][0]["source"] == "promotion_policy.md"  # policy dari RAG


def test_agent_combines_ml_and_rag():
    state = run_scripted(
        [
            ai_multi_tool_calls(
                [
                    ("get_revenue_forecast", {"days": 3}),
                    ("search_business_knowledge", {"query": "penggunaan forecast"}),
                ]
            ),
            AIMessage(content="Model memprediksi ...; business_guidelines.md menyarankan ..."),
        ],
        "Bagaimana forecast revenue dan bagaimana policy menjelaskan penggunaan forecast?",
    )
    assert state["tools_used"] == ["get_revenue_forecast", "search_business_knowledge"]
    msgs = tool_messages(state)
    fc = json.loads(msgs[0].content)
    assert fc["predictions"][0]["predicted_revenue"] == 16533.84  # prediksi ML
    rag = json.loads(msgs[1].content)
    assert rag["results"][0]["source"] == "business_guidelines.md"


# ---------------------------------------------------------------------------
# Endpoint debug /api/rag/search
# ---------------------------------------------------------------------------
def test_rag_search_endpoint():
    r = client.post("/api/rag/search", json={"query": "Apa aturan promotion?"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]
    assert body["results"][0]["source"] == "promotion_policy.md"


@pytest.mark.parametrize(
    "payload",
    [{"query": ""}, {"query": "x" * 1001}, {"query": "promosi", "top_k": 99}, {}],
)
def test_rag_search_endpoint_validates_request(payload):
    r = client.post("/api/rag/search", json=payload)
    assert r.status_code == 422

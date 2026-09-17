"""Dataset evaluasi agent (data/evaluation/agent_eval_cases.json).

Expected values WAJIB punya field 'source' yang mendokumentasikan asal
angkanya (PostgreSQL tervalidasi / output model tervalidasi / dokumen
knowledge). Dataset bukan input produksi dan tidak mengandung secret.
"""

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "evaluation" / "agent_eval_cases.json"

CATEGORIES = (
    "SQL",
    "ML",
    "RAG",
    "SQL+RAG",
    "ML+RAG",
    "SQL+ML",
    "SQL+ML+RAG",
    "OUT_OF_DOMAIN",
)

Category = Literal[
    "SQL", "ML", "RAG", "SQL+RAG", "ML+RAG", "SQL+ML", "SQL+ML+RAG",
    "OUT_OF_DOMAIN",
]


class ExpectedValue(BaseModel):
    tool: str
    path: Optional[str] = None  # "predictions.0.predicted_revenue" | "#len" | None
    value: float
    tolerance: float = 0.01
    in_answer: bool = True
    source: str  # dokumentasi asal angka (WAJIB)
    tool_args: dict = Field(default_factory=dict)


class EvalCase(BaseModel):
    id: str
    category: Category
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    expected_values: list[ExpectedValue] = Field(default_factory=list)
    expected_answer_terms: list[str] = Field(default_factory=list)
    expect_unavailable: bool = False
    notes: str = ""


def load_cases(path: Path = DEFAULT_CASES_FILE) -> list[EvalCase]:
    data = json.loads(Path(path).read_text())
    return [EvalCase(**c) for c in data["cases"]]


# ---------------------------------------------------------------------------
# Session case (Phase 5.2): regression multi-turn DENGAN konteks percakapan.
# Memodelkan interaksi nyata (memory di-inject setelah SystemMessage) tanpa
# menulis agent_messages/agent_runs - dipakai runner.run_session_live.
# ---------------------------------------------------------------------------
DEFAULT_SESSION_CASES_FILE = (
    PROJECT_ROOT / "data" / "evaluation" / "agent_session_cases.json"
)


class SessionTurn(BaseModel):
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    expect_unavailable: bool = False


class SessionCase(BaseModel):
    id: str
    description: str = ""
    turns: list[SessionTurn]


def load_session_cases(
    path: Path = DEFAULT_SESSION_CASES_FILE,
) -> list[SessionCase]:
    data = json.loads(Path(path).read_text())
    return [SessionCase(**c) for c in data["sessions"]]


def get_value_at_path(obj, path: Optional[str]):
    """Ambil nilai dari output tool. Path titik dengan indeks numerik,
    '#len' = panjang list (row count), None = None (pencocokan ke nilai mana pun)."""
    if path is None:
        return None
    if path == "#len":
        return len(obj)
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur

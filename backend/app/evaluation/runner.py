"""Orchestrator evaluasi Phase 5: dua mode, satu format laporan.

Mode DETERMINISTIK (tanpa kredensial LLM):
- Verifikasi ground-truth: setiap expected_value di dataset dieksekusi ulang
  lewat tool registry (PostgreSQL / forecast_service / ChromaDB aktual) dan
  dicocokkan. Memastikan dataset tidak berisi angka basi/karangan.
- Retrieval Hit@1/3/4 via ChromaDB aktual (query = question case).

Mode LIVE (butuh kredensial LLM):
- Setiap case dijalankan lewat run_agent_chat_collect (stateless, tanpa
  menulis memory/audit), lalu dinilai semua evaluator deterministik.
- LLMNotConfiguredError -> status case "environment_unavailable" (BUKAN
  failure; dibedakan sesuai spec: TEST FAILURE != ENVIRONMENT UNAVAILABLE).

Latency dicatat tetapi TIDAK mempengaruhi correctness score.
"""

import json
import time
from datetime import datetime, timezone

from langchain_core.messages import ToolMessage

from ..agent.llm import LLMNotConfiguredError
from ..agent.tools import AGENT_TOOLS
from .cases import EvalCase, SessionCase, get_value_at_path, load_cases
from .metrics import (
    answer_terms_check,
    citation_check,
    evaluate_retrieval,
    groundedness_check,
    latency_stats,
    multi_tool_success,
    numeric_answer_check,
    out_of_domain_check,
    retrieved_sources_from_tool_results,
    tool_selection_pass,
)
from .numerics import (
    collect_tool_numbers,
    contains_value,
    matches,
)

TOOL_REGISTRY = {t.name: t for t in AGENT_TOOLS}

REPORT_NOTES = [
    "Semua evaluator deterministik - tidak ada LLM-as-a-judge.",
    "Latency dilaporkan sebagai statistik saja dan tidak masuk correctness score.",
    "Evaluation scores describe this project's test set and should not be "
    "interpreted as general model performance.",
    "Case environment_unavailable tidak dihitung sebagai failure dan tidak "
    "masuk denominator metric.",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Mode deterministik: verifikasi ground-truth dataset + retrieval hit@k
# ---------------------------------------------------------------------------
def verify_expected_values(cases: list[EvalCase]) -> list[dict]:
    """Jalankan tool sesuai tool_args tiap expected_value dan cocokkan angka."""
    cache: dict[str, object] = {}
    checks = []
    for case in cases:
        for ev in case.expected_values:
            tool = TOOL_REGISTRY.get(ev.tool)
            if tool is None:
                checks.append({
                    "case": case.id, "tool": ev.tool, "path": ev.path,
                    "expected": ev.value, "status": "fail",
                    "reason": f"unknown_tool:{ev.tool}",
                })
                continue
            key = f"{ev.tool}:{json.dumps(ev.tool_args, sort_keys=True)}"
            if key not in cache:
                try:
                    cache[key] = json.loads(tool.invoke(ev.tool_args))
                except Exception as exc:  # env down (DB/model) != test failure
                    cache[key] = {
                        "__error__": f"{type(exc).__name__}: {exc}",
                    }
            output = cache[key]
            if isinstance(output, dict) and "__error__" in output:
                checks.append({
                    "case": case.id, "tool": ev.tool, "path": ev.path,
                    "expected": ev.value, "status": "environment_unavailable",
                    "reason": output["__error__"][:200],
                })
                continue
            if ev.path is not None:
                try:
                    actual = get_value_at_path(output, ev.path)
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    checks.append({
                        "case": case.id, "tool": ev.tool, "path": ev.path,
                        "expected": ev.value, "status": "fail",
                        "reason": f"path_error:{exc}",
                    })
                    continue
                ok = matches(float(actual), ev.value, ev.tolerance)
                actual_repr = actual
            else:
                # path None: nilai harus muncul di mana pun pada output tool
                ok = contains_value(
                    collect_tool_numbers([output]), ev.value, ev.tolerance,
                    allow_rounded=False,
                )
                actual_repr = None
            checks.append({
                "case": case.id, "tool": ev.tool, "path": ev.path,
                "expected": ev.value, "actual": actual_repr,
                "status": "pass" if ok else "fail",
                "reason": "ok" if ok else "value_mismatch",
            })
    return checks


def retrieval_queries(cases: list[EvalCase]) -> list[tuple[str, str]]:
    return [
        (case.question, source)
        for case in cases
        for source in case.expected_sources
    ]


def run_deterministic(cases: list[EvalCase]) -> dict:
    value_checks = verify_expected_values(cases)
    verified = [c for c in value_checks if c["status"] != "environment_unavailable"]
    retrieval = evaluate_retrieval(retrieval_queries(cases))
    return {
        "generated_at": _now_iso(),
        "mode": "deterministic",
        "model": None,
        "dataset": _dataset_summary(cases),
        "summary": {
            "ground_truth_values": {
                "verified_ok": sum(1 for c in verified if c["status"] == "pass"),
                "total": len(verified),
                "environment_unavailable": sum(
                    1 for c in value_checks
                    if c["status"] == "environment_unavailable"
                ),
            },
            "retrieval": {
                "hit_at_1": retrieval["hit_at_1"],
                "hit_at_3": retrieval["hit_at_3"],
                "hit_at_4": retrieval["hit_at_4"],
            },
        },
        "ground_truth_checks": value_checks,
        "retrieval_details": retrieval["details"],
        "notes": REPORT_NOTES,
    }


# ---------------------------------------------------------------------------
# Mode live: jalankan agent per case, evaluasi penuh
# ---------------------------------------------------------------------------
def evaluate_case_result(case: EvalCase, result: dict) -> dict:
    """Semua evaluator deterministik untuk satu hasil eksekusi agent."""
    answer = result["answer"]
    tools_used = result["tools_used"]
    tool_results = result["tool_results"]

    checks: dict = {}
    checks["tool_selection"] = {
        "expected": case.expected_tools, "actual": tools_used,
        "pass": tool_selection_pass(case.expected_tools, tools_used),
    }

    if case.expected_values:
        numeric = numeric_answer_check(answer, case.expected_values)
        checked = sum(1 for ev in case.expected_values if ev.in_answer)
        numeric["checked"] = checked
        numeric["matched"] = checked - len(numeric["missing"])
        numeric["pass"] = numeric["ok"]
        checks["numeric"] = numeric

    if case.expected_answer_terms:
        checks["answer_terms"] = {
            "terms": case.expected_answer_terms,
            "pass": answer_terms_check(answer, case.expected_answer_terms),
        }

    if case.category != "OUT_OF_DOMAIN":
        grounded = groundedness_check(answer, tool_results)
        grounded["pass"] = grounded["ok"]
        checks["groundedness"] = grounded

    if case.expected_sources:
        retrieved = retrieved_sources_from_tool_results(tool_results)
        citation = citation_check(answer, retrieved, required=True)
        citation["pass"] = citation["valid"]
        checks["citation"] = citation
        found = [s for s in case.expected_sources if s in set(retrieved)]
        checks["sources_retrieved"] = {
            "expected": case.expected_sources,
            "retrieved_in_run": sorted(set(retrieved)),
            "found": found,
            "pass": len(found) == len(case.expected_sources),
        }

    if case.category == "OUT_OF_DOMAIN":
        ood = out_of_domain_check(
            answer, case.expect_unavailable, tool_results
        )
        ood["pass"] = ood["ok"]
        checks["out_of_domain"] = ood

    return checks


def _checks_pass(checks: dict) -> bool:
    for value in checks.values():
        ok = value["pass"] if isinstance(value, dict) else bool(value)
        if not ok:
            return False
    return True


def run_case_live(case: EvalCase, llm=None) -> dict:
    """Eksekusi satu case; environment_unavailable != failure."""
    start = time.monotonic()
    try:
        from ..agent.graph import run_agent_chat_collect

        result = run_agent_chat_collect(case.question, llm=llm)
    except LLMNotConfiguredError as exc:
        return {
            "id": case.id, "category": case.category,
            "status": "environment_unavailable",
            "reason": f"LLMNotConfiguredError: {exc}"[:200],
        }
    except Exception as exc:  # noqa: BLE001 - dicatat apa adanya
        return {
            "id": case.id, "category": case.category, "status": "error",
            "reason": f"{type(exc).__name__}: {exc}"[:200],
        }
    latency_ms = int((time.monotonic() - start) * 1000)

    checks = evaluate_case_result(case, result)
    status = "pass" if _checks_pass(checks) else "fail"
    entry = {
        "id": case.id, "category": case.category, "status": status,
        "latency_ms": latency_ms,
        "tools_used": result["tools_used"],
        "answer": result["answer"],
        "checks": checks,
    }
    if "+" in case.category:  # multi-tool: SQL+RAG, SQL+ML, dst.
        entry["multi_tool_success"] = multi_tool_success(
            case, {"tools_used": result["tools_used"], **checks}
        )
    return entry


def _safe_model_name() -> str | None:
    try:
        from ..agent.llm import get_llm_config

        return get_llm_config().get("model")
    except LLMNotConfiguredError:
        return None


def summarize_live(entries: list[dict]) -> dict:
    evaluated = [e for e in entries if e["status"] in ("pass", "fail")]
    unavailable = sum(
        1 for e in entries if e["status"] == "environment_unavailable"
    )
    errors = sum(1 for e in entries if e["status"] == "error")
    latencies = [e["latency_ms"] for e in evaluated]

    def _check_count(check_name: str) -> dict:
        """Hitung pass/total untuk SATU check spesifik (bukan status case):
        kegagalan tool_selection tidak boleh teratribusi ke metric lain."""
        applicable = [
            e for e in evaluated if check_name in e.get("checks", {})
        ]
        passed = 0
        for e in applicable:
            c = e["checks"][check_name]
            passed += 1 if (c["pass"] if isinstance(c, dict) else c) else 0
        return {"pass": passed, "total": len(applicable)}

    numeric_matched = numeric_total = 0
    for e in evaluated:
        numeric = e.get("checks", {}).get("numeric")
        if numeric:
            numeric_matched += numeric["matched"]
            numeric_total += numeric["checked"]

    return {
        "cases": {
            "pass": sum(1 for e in evaluated if e["status"] == "pass"),
            "fail": sum(1 for e in evaluated if e["status"] == "fail"),
            "error": errors,
            "environment_unavailable": unavailable,
            "total": len(entries),
        },
        "tool_selection_accuracy": _check_count("tool_selection"),
        "numerical_accuracy_values": {
            "matched": numeric_matched, "total": numeric_total,
        },
        "groundedness": _check_count("groundedness"),
        "citation_correctness": _check_count("citation"),
        "sources_retrieved_in_run": _check_count("sources_retrieved"),
        "out_of_domain_safety": _check_count("out_of_domain"),
        "multi_tool_success": {
            "pass": sum(1 for e in evaluated if e.get("multi_tool_success")),
            "total": sum(1 for e in evaluated if "multi_tool_success" in e),
        },
        "latency": latency_stats(latencies),
    }


def run_live(cases: list[EvalCase], llm=None, limit: int | None = None) -> dict:
    selected = cases[:limit] if limit else cases
    entries = [run_case_live(case, llm=llm) for case in selected]
    retrieval = evaluate_retrieval(retrieval_queries(selected))
    return {
        "generated_at": _now_iso(),
        "mode": "live",
        "model": _safe_model_name(),
        "dataset": _dataset_summary(selected),
        "summary": {
            **summarize_live(entries),
            "retrieval": {
                "hit_at_1": retrieval["hit_at_1"],
                "hit_at_3": retrieval["hit_at_3"],
                "hit_at_4": retrieval["hit_at_4"],
            },
        },
        "cases": entries,
        "notes": REPORT_NOTES,
    }


# ---------------------------------------------------------------------------
# Mode live multi-run (Phase 5.2): N x dataset penuh, agregasi mean/min/max.
# TIDAK ada aggregate score tunggal - tiap metric dilaporkan terpisah.
# ---------------------------------------------------------------------------
# (label, path pass-count, path total-count) pada summary tiap run
MULTI_RUN_METRICS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("Tool Selection", ("tool_selection_accuracy", "pass"),
     ("tool_selection_accuracy", "total")),
    ("Numerical Accuracy", ("numerical_accuracy_values", "matched"),
     ("numerical_accuracy_values", "total")),
    ("Retrieval Hit@1", ("retrieval", "hit_at_1", "hits"),
     ("retrieval", "hit_at_1", "total")),
    ("Retrieval Hit@3", ("retrieval", "hit_at_3", "hits"),
     ("retrieval", "hit_at_3", "total")),
    ("Citation", ("citation_correctness", "pass"),
     ("citation_correctness", "total")),
    ("Groundedness", ("groundedness", "pass"), ("groundedness", "total")),
    ("OOD", ("out_of_domain_safety", "pass"),
     ("out_of_domain_safety", "total")),
    ("Multi-tool", ("multi_tool_success", "pass"),
     ("multi_tool_success", "total")),
]


def _get_path(obj, path: tuple[str, ...]):
    cur = obj
    for key in path:
        cur = cur[key]
    return cur


def aggregate_runs(summaries: list[dict]) -> dict:
    """Agregasi mean/min/max pass-count untuk tiap metric MULTI_RUN_METRICS.
    Total (denominator) harus identik antar run; jika tidak, total=None."""
    aggregates: dict[str, dict] = {}
    for label, pass_path, total_path in MULTI_RUN_METRICS:
        passes = [_get_path(s, pass_path) for s in summaries]
        totals = {_get_path(s, total_path) for s in summaries}
        aggregates[label] = {
            "mean": round(sum(passes) / len(passes), 2),
            "min": min(passes),
            "max": max(passes),
            "total": totals.pop() if len(totals) == 1 else None,
            "runs": len(passes),
        }
    return aggregates


def run_live_multi(cases: list[EvalCase], runs: int = 1, llm=None,
                   limit: int | None = None) -> dict:
    """Jalankan mode live ``runs`` kali pada dataset yang sama; kumpulkan
    metric tiap run + agregasi mean/min/max. Laporan per run (dengan jawaban
    lengkap) disimpan pada key 'reports' agar bisa diaudit."""
    if runs < 1:
        raise ValueError("runs harus >= 1")
    reports = [run_live(cases, llm=llm, limit=limit) for _ in range(runs)]
    summaries = [r["summary"] for r in reports]
    return {
        "generated_at": _now_iso(),
        "mode": "live_multi",
        "runs": runs,
        "model": reports[0]["model"],
        "dataset": reports[0]["dataset"],
        "aggregates": aggregate_runs(summaries),
        "per_run": [
            {
                "run": i + 1,
                "generated_at": r["generated_at"],
                "summary": r["summary"],
                "failed_cases": [
                    {"id": c["id"], "category": c["category"],
                     "checks": [k for k, v in c.get("checks", {}).items()
                                if not (v["pass"] if isinstance(v, dict)
                                        else v)]}
                    for c in r["cases"] if c["status"] == "fail"
                ],
            }
            for i, r in enumerate(reports)
        ],
        "reports": reports,
        "notes": REPORT_NOTES + [
            "Multi-run: mean/min/max dihitung atas pass-count tiap metric "
            "per run; tidak ada aggregate score tunggal.",
        ],
    }


# ---------------------------------------------------------------------------
# Mode live session multi-turn (Phase 5.2): regression OOD interaktif.
# ---------------------------------------------------------------------------
def run_session_live(session_case: SessionCase, llm=None) -> dict:
    """Jalankan case multi-turn DENGAN konteks percakapan (jawaban turn
    sebelumnya ikut dikirim sebagai history), TANPA menulis
    agent_messages/agent_runs - meniru semantik injeksi memory produksi
    (history di-inject setelah SystemMessage) secara stateless.

    Tiap turn dinilai: tool selection (set comparison) dan, bila
    expect_unavailable, out-of-domain check dengan frasa kontrak.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # Import privat graph sengaja: tidak mengubah production code agent
    # (spec Phase 5.2 - hanya evaluation harness yang boleh berubah).
    from ..agent.graph import (  # noqa: PLC2701
        SYSTEM_PROMPT,
        _answer_text,
        _cached_graph,
        build_agent_graph,
    )

    start = time.monotonic()
    try:
        graph = build_agent_graph(llm) if llm is not None else _cached_graph()
        messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
        turns: list[dict] = []
        for turn in session_case.turns:
            state = graph.invoke(
                {
                    "messages": [*messages, HumanMessage(content=turn.question)],
                    "tools_used": [],
                },
                config={"recursion_limit": 24},
            )
            new_messages = state["messages"][len(messages):]
            messages = list(state["messages"])
            tool_results = []
            for m in new_messages:
                if isinstance(m, ToolMessage):
                    try:
                        tool_results.append(json.loads(m.content))
                    except (TypeError, ValueError):
                        tool_results.append(m.content)
            answer = _answer_text(messages[-1])
            checks: dict = {
                "tool_selection": {
                    "expected": turn.expected_tools,
                    "actual": list(state["tools_used"]),
                    "pass": tool_selection_pass(
                        turn.expected_tools, list(state["tools_used"])
                    ),
                }
            }
            if turn.expect_unavailable:
                ood = out_of_domain_check(answer, True, tool_results)
                ood["pass"] = ood["ok"]
                checks["out_of_domain"] = ood
            turns.append({
                "question": turn.question,
                "answer": answer,
                "tools_used": list(state["tools_used"]),
                "checks": checks,
                "pass": _checks_pass(checks),
            })
    except LLMNotConfiguredError as exc:
        return {
            "id": session_case.id, "status": "environment_unavailable",
            "reason": f"LLMNotConfiguredError: {exc}"[:200],
        }
    except Exception as exc:  # noqa: BLE001 - dicatat apa adanya
        return {
            "id": session_case.id, "status": "error",
            "reason": f"{type(exc).__name__}: {exc}"[:200],
        }
    latency_ms = int((time.monotonic() - start) * 1000)
    return {
        "id": session_case.id,
        "status": "pass" if all(t["pass"] for t in turns) else "fail",
        "latency_ms": latency_ms,
        "turns": turns,
    }


def run_sessions_live(sessions: list[SessionCase], llm=None) -> dict:
    """Laporan penuh mode session: jalankan tiap sesi multi-turn lalu
    agregasi per-turn (tool selection & out-of-domain) + per-session."""
    entries = [run_session_live(s, llm=llm) for s in sessions]
    evaluated = [e for e in entries if e["status"] in ("pass", "fail")]
    unavailable = sum(
        1 for e in entries if e["status"] == "environment_unavailable"
    )
    errors = sum(1 for e in entries if e["status"] == "error")

    def _turn_count(check: str) -> dict:
        checked = [
            t for e in evaluated for t in e["turns"] if check in t["checks"]
        ]
        return {
            "pass": sum(1 for t in checked if t["checks"][check]["pass"]),
            "total": len(checked),
        }

    total_turns = sum(len(s.turns) for s in sessions)
    return {
        "generated_at": _now_iso(),
        "mode": "session",
        "model": _safe_model_name(),
        "dataset": {
            "total_sessions": len(sessions),
            "total_turns": total_turns,
        },
        "summary": {
            "sessions": {
                "pass": sum(1 for e in evaluated if e["status"] == "pass"),
                "fail": sum(1 for e in evaluated if e["status"] == "fail"),
                "error": errors,
                "environment_unavailable": unavailable,
                "total": len(entries),
            },
            "turn_tool_selection": _turn_count("tool_selection"),
            "turn_out_of_domain": _turn_count("out_of_domain"),
            "latency": latency_stats([e["latency_ms"] for e in evaluated]),
        },
        "sessions": entries,
        "notes": REPORT_NOTES + [
            "Mode session: eksekusi stateless dengan konteks percakapan "
            "di-inject manual (semantik memory produksi) - TIDAK menulis "
            "agent_messages/agent_runs.",
            "Metric dinilai per-TURN, status sesi = semua turn lolos.",
        ],
    }


# ---------------------------------------------------------------------------
# Helper bersama
# ---------------------------------------------------------------------------
def _dataset_summary(cases: list[EvalCase]) -> dict:
    by_category: dict[str, int] = {}
    for case in cases:
        by_category[case.category] = by_category.get(case.category, 0) + 1
    return {"total_cases": len(cases), "by_category": by_category}


__all__ = [
    "load_cases",
    "run_deterministic",
    "run_live",
    "run_live_multi",
    "run_session_live",
    "run_sessions_live",
    "aggregate_runs",
    "run_case_live",
    "evaluate_case_result",
    "verify_expected_values",
]

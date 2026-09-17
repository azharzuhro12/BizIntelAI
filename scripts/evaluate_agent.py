#!/usr/bin/env python3
"""
BizIntel AI - Evaluation runner AI agent (Phase 5/5.2).

Tiga mode:
  deterministic (default) : verifikasi ground-truth dataset via tool aktual
                            (PostgreSQL / forecast_service / ChromaDB) +
                            retrieval Hit@1/3/4. TIDAK butuh kredensial LLM.
  live                    : jalankan agent per case (run_agent_chat_collect)
                            lalu nilai semua evaluator deterministik.
                            Butuh kredensial LLM pada environment/.env.
  session                 : regresi multi-turn (Phase 5.2) - jalankan sesi
                            dengan konteks percakapan (stateless, tanpa
                            menulis agent_messages/agent_runs); tiap turn
                            dinilai tool selection + out-of-domain.

Output: ringkasan numerator/denominator ke stdout + laporan JSON lengkap ke
data/evaluation/latest_evaluation.json (mode session:
latest_session_evaluation.json). Dengan --runs N (>1, mode live):
N x dataset penuh, agregasi mean/min/max per metric (TIDAK ada aggregate
score tunggal) + laporan data/evaluation/multi_run_evaluation.json.

Exit code:
  0 = tidak ada failure (environment_unavailable TIDAK dihitung failure)
  1 = ada case/check yang FAIL

Pemakaian:
  python3 scripts/evaluate_agent.py
  python3 scripts/evaluate_agent.py --mode live
  python3 scripts/evaluate_agent.py --mode live --limit 5
  python3 scripts/evaluate_agent.py --mode live --runs 10
  python3 scripts/evaluate_agent.py --mode session
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.evaluation.cases import (  # noqa: E402
    DEFAULT_CASES_FILE,
    DEFAULT_SESSION_CASES_FILE,
    load_cases,
    load_session_cases,
)
from app.evaluation.runner import (  # noqa: E402
    MULTI_RUN_METRICS,
    run_deterministic,
    run_live,
    run_live_multi,
    run_sessions_live,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "evaluation" / "latest_evaluation.json"
DEFAULT_MULTI_OUTPUT = (
    PROJECT_ROOT / "data" / "evaluation" / "multi_run_evaluation.json"
)
DEFAULT_SESSION_OUTPUT = (
    PROJECT_ROOT / "data" / "evaluation" / "latest_session_evaluation.json"
)


def _print_ratio(label: str, num: int, den: int) -> None:
    if den == 0:
        print(f"  {label:<28} NOT MEASURED (tidak ada case yang relevan)")
    else:
        pct = num / den * 100
        print(f"  {label:<28} {num}/{den} ({pct:.1f}%)")


def _print_summary(report: dict) -> None:
    mode = report["mode"]
    print(f"\n=== EVALUASI AGENT BIZINTEL (mode: {mode}) ===")
    ds = report["dataset"]
    print(f"Cases: {ds['total_cases']}  "
          f"({', '.join(f'{k}={v}' for k, v in ds['by_category'].items())})")

    if mode == "deterministic":
        gt = report["summary"]["ground_truth_values"]
        _print_ratio("Ground-truth values", gt["verified_ok"], gt["total"])
        if gt["environment_unavailable"]:
            print(f"  environment_unavailable     {gt['environment_unavailable']} "
                  "(DB/model tidak bisa diakses - bukan failure)")
        r = report["summary"]["retrieval"]
        _print_ratio("Retrieval Hit@1", r["hit_at_1"]["hits"], r["hit_at_1"]["total"])
        _print_ratio("Retrieval Hit@3", r["hit_at_3"]["hits"], r["hit_at_3"]["total"])
        _print_ratio("Retrieval Hit@4", r["hit_at_4"]["hits"], r["hit_at_4"]["total"])
        return

    s = report["summary"]
    c = s["cases"]
    print(f"Hasil case: pass={c['pass']} fail={c['fail']} "
          f"error={c['error']} environment_unavailable={c['environment_unavailable']} "
          f"(total {c['total']})")
    _print_ratio("Tool Selection Accuracy",
                 s["tool_selection_accuracy"]["pass"],
                 s["tool_selection_accuracy"]["total"])
    _print_ratio("Numerical Accuracy (values)",
                 s["numerical_accuracy_values"]["matched"],
                 s["numerical_accuracy_values"]["total"])
    _print_ratio("Groundedness",
                 s["groundedness"]["pass"], s["groundedness"]["total"])
    _print_ratio("Citation Correctness",
                 s["citation_correctness"]["pass"],
                 s["citation_correctness"]["total"])
    _print_ratio("Sources retrieved in run",
                 s["sources_retrieved_in_run"]["pass"],
                 s["sources_retrieved_in_run"]["total"])
    _print_ratio("Out-of-domain Safety",
                 s["out_of_domain_safety"]["pass"],
                 s["out_of_domain_safety"]["total"])
    _print_ratio("Multi-tool Task Success",
                 s["multi_tool_success"]["pass"],
                 s["multi_tool_success"]["total"])
    r = s["retrieval"]
    _print_ratio("Retrieval Hit@1", r["hit_at_1"]["hits"], r["hit_at_1"]["total"])
    _print_ratio("Retrieval Hit@3", r["hit_at_3"]["hits"], r["hit_at_3"]["total"])
    _print_ratio("Retrieval Hit@4", r["hit_at_4"]["hits"], r["hit_at_4"]["total"])
    lat = s["latency"]
    if lat.get("count"):
        print(f"  Latency (ms)                mean={lat['mean_ms']} "
              f"median={lat['median_ms']} p95={lat['p95_ms']} "
              f"min={lat['min_ms']} max={lat['max_ms']} (n={lat['count']})")
        if lat.get("note"):
            print(f"    catatan: {lat['note']}")
    else:
        print("  Latency (ms)                NOT MEASURED (tidak ada sampel)")

    print("\nCase gagal:")
    printed = False
    for entry in report["cases"]:
        if entry["status"] == "fail":
            printed = True
            failed = [
                f"{name}({(val.get('reason') if isinstance(val, dict) else None) or 'check tidak lolos'})"
                for name, val in entry.get("checks", {}).items()
                if not (val["pass"] if isinstance(val, dict) else val)
            ]
            print(f"  - {entry['id']} [{entry['category']}] "
                  f"tools={entry['tools_used']} :: {'; '.join(failed) or '-'}")
        elif entry["status"] in ("error", "environment_unavailable"):
            printed = True
            print(f"  - {entry['id']} [{entry['category']}] "
                  f"{entry['status'].upper()}: {entry.get('reason', '')}")
    if not printed:
        print("  (tidak ada)")


def _print_multi_run_summary(report: dict) -> None:
    """Tabel variance N-run (mean/min/max pass-count per metric)."""
    runs = report["runs"]
    print(f"\n=== EVALUASI AGENT BIZINTEL (mode: live, {runs} runs) ===")
    print(f"Model: {report['model'] or '-'}")
    line = "=" * 56
    print(line)
    print(f"{runs}-RUN EVALUATION")
    print(line)
    print(f"{'Metric':<24}{'Mean':>7}{'Min':>10}{'Max':>10}")
    for label, _, _ in MULTI_RUN_METRICS:
        agg = report["aggregates"][label]
        total = agg["total"]
        if total is None or total == 0:
            print(f"{label:<24}{'NOT MEASURED':>7}")
            continue
        print(f"{label:<24}{agg['mean']:>7.1f}"
              f"{agg['min']:>6}/{total}{agg['max']:>6}/{total}")
    print(line)
    identical = all(
        agg["min"] == agg["max"] for agg in report["aggregates"].values()
    )
    if runs > 1:
        print("Catatan variance: " + (
            "SEMUA run identik pada setiap metric (min == max)."
            if identical else
            "metric dengan min != max bervariasi antar run "
            "(lihat kolom Min/Max; detail per run di JSON)."
        ))
    case_fails = [
        (pr["run"], pr["summary"]["cases"]["fail"]) for pr in report["per_run"]
    ]
    print(f"Case fail per run: {case_fails}")


def _print_session_summary(report: dict) -> None:
    print(f"\n=== EVALUASI AGENT BIZINTEL (mode: session) ===")
    print(f"Model: {report['model'] or '-'}")
    ds = report["dataset"]
    print(f"Sesi: {ds['total_sessions']}  (total {ds['total_turns']} turn)")
    c = report["summary"]["sessions"]
    print(f"Hasil sesi: pass={c['pass']} fail={c['fail']} "
          f"error={c['error']} environment_unavailable={c['environment_unavailable']} "
          f"(total {c['total']})")
    _print_ratio("Turn Tool Selection",
                 report["summary"]["turn_tool_selection"]["pass"],
                 report["summary"]["turn_tool_selection"]["total"])
    _print_ratio("Turn Out-of-domain Safety",
                 report["summary"]["turn_out_of_domain"]["pass"],
                 report["summary"]["turn_out_of_domain"]["total"])
    lat = report["summary"]["latency"]
    if lat.get("count"):
        print(f"  Latency sesi (ms)           mean={lat['mean_ms']} "
              f"median={lat['median_ms']} p95={lat['p95_ms']} "
              f"(n={lat['count']})")

    print("\nTurn gagal:")
    printed = False
    for entry in report["sessions"]:
        if entry["status"] in ("error", "environment_unavailable"):
            printed = True
            print(f"  - {entry['id']} {entry['status'].upper()}: "
                  f"{entry.get('reason', '')}")
            continue
        for i, turn in enumerate(entry["turns"], start=1):
            if turn["pass"]:
                continue
            printed = True
            failed = [
                f"{name}({val.get('reason') or 'check tidak lolos'})"
                for name, val in turn["checks"].items()
                if not val["pass"]
            ]
            print(f"  - {entry['id']} turn {i} "
                  f"tools={turn['tools_used']} :: {'; '.join(failed)}")
    if not printed:
        print("  (tidak ada)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluation runner AI agent BizIntel AI (Phase 5/5.2)."
    )
    parser.add_argument(
        "--mode", choices=["deterministic", "live", "session"],
        default="deterministic",
        help="deterministic = tanpa LLM (default); live = jalankan agent; "
             "session = regresi multi-turn (Phase 5.2)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="batasi jumlah case (mode live; untuk smoke test)",
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        help="jumlah pengulangan evaluasi live penuh (default 1); "
             ">1 -> agregasi mean/min/max + multi_run_evaluation.json",
    )
    parser.add_argument(
        "--cases", type=Path, default=DEFAULT_CASES_FILE,
        help="path dataset evaluasi (default: data/evaluation/agent_eval_cases.json)",
    )
    parser.add_argument(
        "--sessions", type=Path, default=DEFAULT_SESSION_CASES_FILE,
        help="path dataset sesi multi-turn (mode session; default: "
             "data/evaluation/agent_session_cases.json)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="path laporan JSON (default: data/evaluation/"
             "latest_evaluation.json; mode session: "
             "latest_session_evaluation.json)",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="jangan tulis file laporan (cetak ringkasan saja)",
    )
    args = parser.parse_args()

    if args.runs < 1:
        parser.error("--runs harus >= 1")
    if args.runs > 1 and args.mode != "live":
        parser.error("--runs > 1 hanya didukung untuk --mode live")
    if args.limit is not None and args.mode != "live":
        parser.error("--limit hanya didukung untuk --mode live")

    if args.mode == "session":
        sessions = load_session_cases(args.sessions)
        print(f"Memuat {len(sessions)} sesi dari {args.sessions}")
        report = run_sessions_live(sessions)
        c = report["summary"]["sessions"]
        failed = c["fail"] + c["error"]
        _print_session_summary(report)
        output_path = args.output or DEFAULT_SESSION_OUTPUT
    else:
        cases = load_cases(args.cases)
        print(f"Memuat {len(cases)} case dari {args.cases}")

        if args.mode == "deterministic":
            report = run_deterministic(cases)
            failed = report["summary"]["ground_truth_values"]["total"] - \
                report["summary"]["ground_truth_values"]["verified_ok"]
            _print_summary(report)
            output_path = args.output or DEFAULT_OUTPUT
        elif args.runs == 1:
            report = run_live(cases, limit=args.limit)
            failed = report["summary"]["cases"]["fail"] + \
                report["summary"]["cases"]["error"]
            _print_summary(report)
            output_path = args.output or DEFAULT_OUTPUT
        else:
            multi = run_live_multi(cases, runs=args.runs, limit=args.limit)
            failed = sum(
                pr["summary"]["cases"]["fail"] + pr["summary"]["cases"]["error"]
                for pr in multi["per_run"]
            )
            unavailable = sum(
                pr["summary"]["cases"]["environment_unavailable"]
                for pr in multi["per_run"]
            )
            _print_multi_run_summary(multi)
            if unavailable:
                print(f"environment_unavailable: {unavailable} run-case "
                      "(bukan failure)")
            report = multi
            output_path = DEFAULT_MULTI_OUTPUT

    if not args.no_write:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str)
        )
        print(f"\nLaporan lengkap: {output_path}")

    for note in report["notes"]:
        print(f"CATATAN: {note}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

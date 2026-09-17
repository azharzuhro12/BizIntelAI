"""Evaluator deterministik Phase 5 (TANPA LLM-as-a-judge).

Semua fungsi menerima data hasil eksekusi (tools_used, output tool, jawaban,
hasil retrieval) dan menilai dengan aturan eksplisit yang bisa diaudit.
"""

import re
import statistics
from typing import Optional

from ..rag.retriever import search_knowledge
from .numerics import (
    claims,
    collect_tool_numbers,
    contains_value,
    derived_values,
    extract_numbers,
    parse_number,
    range_claims,
)

# ---------------------------------------------------------------------------
# 1. Tool selection (set comparison - urutan tidak dinilai, spec Phase 5 #4)
# ---------------------------------------------------------------------------
def tool_selection_pass(expected: list[str], actual: list[str]) -> bool:
    return set(expected) == set(actual)


# ---------------------------------------------------------------------------
# 2. Retrieval Hit@K (dari ChromaDB aktual)
# ---------------------------------------------------------------------------
def retrieval_results(query: str, top_k: int = 4) -> list[dict]:
    return search_knowledge(query, top_k=top_k)["results"]


def retrieval_rank(results: list[dict], expected_source: str) -> Optional[int]:
    """0-based rank source pertama yang cocok, None jika tidak ada."""
    for i, r in enumerate(results):
        if r["source"] == expected_source:
            return i
    return None


def hit_at(results: list[dict], expected_source: str, k: int) -> bool:
    rank = retrieval_rank(results, expected_source)
    return rank is not None and rank < k


def evaluate_retrieval(queries: list[tuple[str, str]], top_k: int = 4) -> dict:
    """queries: [(question, expected_source)]. Hit@1/3/4 dari eksekusi nyata."""
    hits1 = hits3 = hits4 = 0
    details = []
    for question, source in queries:
        results = retrieval_results(question, top_k)
        rank = retrieval_rank(results, source)
        h1 = rank is not None and rank < 1
        h3 = rank is not None and rank < 3
        h4 = rank is not None and rank < 4
        hits1 += h1
        hits3 += h3
        hits4 += h4
        details.append({
            "question": question, "expected_source": source,
            "rank": rank, "hit@1": h1, "hit@3": h3, "hit@4": h4,
        })
    total = len(queries)
    return {
        "total": total,
        "hit_at_1": {"hits": hits1, "total": total},
        "hit_at_3": {"hits": hits3, "total": total},
        "hit_at_4": {"hits": hits4, "total": total},
        "details": details,
    }


# ---------------------------------------------------------------------------
# 3. Citation correctness (dari retrieved results aktual, bukan teks saja)
# ---------------------------------------------------------------------------
_CITATION_RE = re.compile(r"\[([A-Za-z0-9_\-]+\.md)\]")


def extract_citations(answer: str) -> list[str]:
    return _CITATION_RE.findall(answer)


def citation_check(answer: str, retrieved_sources: list[str],
                   required: bool = True) -> dict:
    """Valid bila: setiap [file.md] yang disebut ADA di retrieved results,
    dan (bila required) minimal satu citation diberikan."""
    citations = extract_citations(answer)
    retrieved = set(retrieved_sources)
    fabricated = sorted(set(citations) - retrieved)
    valid = not fabricated and (bool(citations) if required else True)
    reason = "ok"
    if fabricated:
        reason = f"fabricated_citation:{fabricated}"
    elif required and not citations:
        reason = "missing_citation"
    return {"citations": citations, "fabricated": fabricated,
            "valid": valid, "reason": reason}


def retrieved_sources_from_tool_results(tool_results: list) -> list[str]:
    """Kumpulkan source dari hasil search_business_knowledge pada run."""
    sources: list[str] = []
    for out in tool_results:
        if isinstance(out, dict) and isinstance(out.get("results"), list):
            for r in out["results"]:
                if isinstance(r, dict) and r.get("source"):
                    sources.append(r["source"])
    return sources


# ---------------------------------------------------------------------------
# 4. Groundedness (konservatif; derived sederhana diizinkan)
# ---------------------------------------------------------------------------
def _supported(value: float, tol: float,
               universe: list[tuple[float, float]]) -> bool:
    """Cocok dengan nilai tool / turunan (identitas atau pembulatan integer).
    Toleransi efektif = maksimum antara toleransi klaim dan toleransi turunan."""
    return any(
        abs(value - v) <= max(tol, utol) + 1e-9 or
        abs(value - round(v)) <= max(tol, utol) + 1e-9
        for v, utol in universe
    )


def groundedness_check(answer: str, tool_outputs: list) -> dict:
    """Setiap angka klaim (>=10, non-tanggal) di jawaban harus cocok dengan:
    angka output tool, atau turunan pairwise 1-langkah (lihat
    numerics.derived_values).
    Klaim aproksimasi ('~16 ribu', 'sekitar 31,7%', '≈ €13.838') diberi
    toleransi relatif 1,5% oleh numerics.claims.

    KLAIM RENTANG (Phase 5.2): 'kisaran €15.000-16.500' dinilai sebagai
    CONTAINMENT - valid bila ada nilai universe di dalam [lo, hi] (rentang
    aproksimasi diberi bantalan relatif 1,5%). Endpoint rentang TIDAK
    dibandingkan sebagai klaim eksak ('Forecast = €15.000' tetap klaim titik).
    Konservatif: tak dikenal -> unsupported_claim_detected."""
    universe = derived_values(collect_tool_numbers(tool_outputs))
    unsupported = []
    for n, tol in claims(answer):
        if not _supported(n, tol, universe):
            unsupported.append(n)
    unsupported_ranges = []
    for lo, hi, approx in range_claims(answer):
        pad = 0.015 * max(abs(lo), abs(hi)) if approx else 0.0
        if not any(lo - pad <= v <= hi + pad for v, _ in universe):
            unsupported_ranges.append([lo, hi])
    reasons = []
    if unsupported:
        reasons.append("unsupported_claim_detected")
    if unsupported_ranges:
        reasons.append("unsupported_range_detected")
    return {"unsupported": unsupported,
            "unsupported_ranges": unsupported_ranges,
            "ok": not unsupported and not unsupported_ranges,
            "reason": "ok" if not reasons else ";".join(reasons)}


# ---------------------------------------------------------------------------
# 5. Out-of-domain / hallucination guard
# ---------------------------------------------------------------------------
# Tanda minus boleh sebelum ATAU sesudah simbol mata uang (Phase 5.2):
# "-€9.007,63" dan "€-9.007,63" keduanya -> -9007.63. Minus harus menempel
# pada simbol agar rentang berspasi "€15.000 - €16.500" tidak berubah tanda.
_CURRENCY_RE = re.compile(
    r"(-?)(?:Rp|EUR|USD|\$|€|£)\s*(-?)(-?[\d.,]*\d)"
)


def _currency_values(answer: str) -> list[float]:
    """Nilai bermata-uang dari jawaban, lengkap dengan tandanya."""
    values = []
    for minus_before, minus_after, digits in _CURRENCY_RE.findall(answer):
        sign = "-" if (minus_before or minus_after) else ""
        values.append(parse_number(sign + digits))
    return values
_CREDENTIAL_RE = re.compile(r"sk-[A-Za-z0-9]{8,}|ANTHROPIC[A-Z_]*|POSTGRES[A-Z_]*")


def out_of_domain_check(answer: str, expect_unavailable: bool = False,
                        tool_outputs: list | None = None) -> dict:
    """Deteksi jawaban out-of-domain yang mengarang bukti bisnis.

    Aman bila: citation hanya menyebut source yang benar-benar ter-retrieve
    pada run (citation tanpa retrieval = karangan), tanpa klaim
    angka bermata-uang/bernilai besar yang TIDAK didukung output tool pada
    run yang sama, tanpa pola credential; bila expect_unavailable, wajib
    menyatakan 'tidak tersedia'. Angka/citation yang memang berasal dari
    tool call run tersebut bukan halusinasi - tidak ditandai."""
    tool_outputs = list(tool_outputs or [])
    universe = derived_values(collect_tool_numbers(tool_outputs))
    citations = extract_citations(answer)
    retrieved = set(retrieved_sources_from_tool_results(tool_outputs))
    fabricated_citations = sorted(set(citations) - retrieved)
    currency_values = _currency_values(answer)
    unsupported_currency = [
        n for n in currency_values
        if abs(n) >= 100 and not _supported(n, max(1.0, abs(n) * 0.015),
                                            universe)
    ]
    big_unsupported = [
        n for n in extract_numbers(answer)
        if abs(n) >= 10000 and not _supported(n, 0.01, universe)
    ]
    credentials = _CREDENTIAL_RE.findall(answer)
    reasons = []
    if fabricated_citations:
        reasons.append(f"fabricated_citation:{fabricated_citations}")
    if unsupported_currency:
        reasons.append(f"currency_claim_without_tool:{unsupported_currency}")
    if big_unsupported:
        reasons.append(f"large_number_claim:{big_unsupported}")
    if credentials:
        reasons.append("credential_pattern")
    if expect_unavailable and "tidak tersedia" not in answer.lower():
        reasons.append("missing_unavailability_statement")
    ok = not reasons
    return {"ok": ok, "reason": "ok" if ok else ";".join(reasons)}


# ---------------------------------------------------------------------------
# 6. Numerical accuracy (tool-side ground truth + answer-side presence)
# ---------------------------------------------------------------------------
def numeric_answer_check(answer: str, expected_values: list) -> dict:
    """Untuk expected value dengan in_answer=True: angka harus muncul di
    jawaban (toleransi + pembulatan integer diizinkan)."""
    numbers = extract_numbers(answer)
    missing = []
    for ev in expected_values:
        if not ev.in_answer:
            continue
        if not contains_value(numbers, ev.value, ev.tolerance):
            missing.append({"value": ev.value, "path": ev.path,
                            "tool": ev.tool})
    ok = not missing
    return {"ok": ok,
            "reason": "ok" if ok else "missing_in_answer",
            "missing": missing}


def answer_terms_check(answer: str, terms: list[str]) -> bool:
    low = answer.lower()
    return all(t.lower() in low for t in terms)


# ---------------------------------------------------------------------------
# 7. Multi-tool task success
# ---------------------------------------------------------------------------
def multi_tool_success(case, evaluation: dict) -> bool:
    """Sukses bila semua tool expected terpanggil + semua sub-check lolos
    (numerik, groundedness, citation bila ada expected_sources)."""
    if not tool_selection_pass(case.expected_tools, evaluation["tools_used"]):
        return False
    if case.expected_values and not evaluation["numeric"]["ok"]:
        return False
    if not evaluation["groundedness"]["ok"]:
        return False
    if case.expected_sources and not evaluation["citation"]["valid"]:
        return False
    return True


# ---------------------------------------------------------------------------
# 8. Latency statistics (angka saja, tanpa penilaian bagus/buruk)
# ---------------------------------------------------------------------------
def latency_stats(latencies_ms: list[int]) -> dict:
    if not latencies_ms:
        return {"count": 0, "note": "no_samples"}
    ordered = sorted(latencies_ms)
    count = len(ordered)
    p95_index = min(count - 1, max(0, round(0.95 * (count - 1))))
    return {
        "count": count,
        "mean_ms": round(statistics.fmean(ordered), 1),
        "median_ms": round(statistics.median(ordered), 1),
        "p95_ms": ordered[p95_index],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "note": (
            "sample kecil (<20): p95 belum representatif" if count < 20 else ""
        ),
    }

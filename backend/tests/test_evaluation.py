"""Test evaluation layer Phase 5 (deterministik, TANPA paid LLM).

Strategi:
- Parser & evaluator diuji unit-level, termasuk kasus NEGATIF (angka salah
  TIDAK boleh dianggap benar - parser tidak boleh terlalu permisif).
- Retrieval Hit@k diuji terhadap ChromaDB lokal (embedding deterministik).
- Ground-truth dataset diverifikasi lewat tool aktual (PostgreSQL/forecast).
- Mode live diuji dengan ScriptedLLM (deterministik) + kasus LLM tidak
  terkonfigurasi (environment_unavailable != failure).
"""

import json
import sys
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.llm import LLMNotConfiguredError  # noqa: E402
from app.agent.tools import AGENT_TOOLS  # noqa: E402
from app.evaluation.cases import (  # noqa: E402
    CATEGORIES,
    DEFAULT_CASES_FILE,
    DEFAULT_SESSION_CASES_FILE,
    ExpectedValue,
    SessionCase,
    get_value_at_path,
    load_cases,
    load_session_cases,
)
from app.evaluation.metrics import (  # noqa: E402
    citation_check,
    evaluate_retrieval,
    extract_citations,
    groundedness_check,
    hit_at,
    latency_stats,
    multi_tool_success,
    numeric_answer_check,
    out_of_domain_check,
    retrieval_rank,
    retrieval_results,
    tool_selection_pass,
)
from app.evaluation.numerics import (  # noqa: E402
    extract_numbers,
    matches,
    matches_answer,
    parse_number,
    contains_value,
    derived_values,
    range_claims,
)
from app.evaluation.runner import (  # noqa: E402
    evaluate_case_result,
    run_case_live,
    run_session_live,
    summarize_live,
    verify_expected_values,
)

CASES = load_cases()
CASES_BY_ID = {c.id: c for c in CASES}
TOOL_NAMES = {t.name for t in AGENT_TOOLS}
KNOWLEDGE_FILES = {p.name for p in
                   (DEFAULT_CASES_FILE.parents[1] / "knowledge").glob("*.md")}


# ---------------------------------------------------------------------------
# LLM palsu deterministik (pola test_agent*.py)
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


class UnavailableLLM(BaseChatModel):
    """Simulasi environment tanpa kredensial LLM."""

    @property
    def _llm_type(self) -> str:
        return "unavailable-test-llm"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise LLMNotConfiguredError("tidak ada kredensial LLM (test)")

    def bind_tools(self, tools, **kwargs):
        return self


def ai_tool_call(name, args=None, call_id="call_1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {}, "id": call_id,
                     "type": "tool_call"}],
    )


# ---------------------------------------------------------------------------
# A. Dataset: schema + integritas
# ---------------------------------------------------------------------------
class TestDatasetSchema:
    def test_at_least_20_cases(self):
        assert len(CASES) >= 20

    def test_unique_ids(self):
        ids = [c.id for c in CASES]
        assert len(ids) == len(set(ids))

    def test_all_categories_present(self):
        present = {c.category for c in CASES}
        assert present == set(CATEGORIES)

    def test_expected_tools_exist_in_registry(self):
        for c in CASES:
            for t in c.expected_tools:
                assert t in TOOL_NAMES, f"{c.id}: tool {t} tidak ada"

    def test_expected_sources_exist_in_knowledge_base(self):
        for c in CASES:
            for s in c.expected_sources:
                assert s in KNOWLEDGE_FILES, f"{c.id}: source {s} tidak ada"

    def test_every_expected_value_has_documented_source(self):
        for c in CASES:
            for ev in c.expected_values:
                assert ev.source and ev.source.strip(), f"{c.id}: tanpa source"

    def test_has_security_injection_case(self):
        ood = [c for c in CASES if c.category == "OUT_OF_DOMAIN"]
        assert any("ignore" in c.question.lower() for c in ood)

    def test_unavailable_case_only_when_no_expected_values(self):
        for c in CASES:
            if c.expect_unavailable:
                assert not c.expected_values and not c.expected_sources

    def test_ood_cases_expect_no_tools(self):
        for c in CASES:
            if c.category == "OUT_OF_DOMAIN":
                assert c.expected_tools == []


# ---------------------------------------------------------------------------
# B. Parser angka: format yang diterima
# ---------------------------------------------------------------------------
class TestParserFormats:
    @pytest.mark.parametrize("token,expected", [
        ("769515.86", 769515.86),
        ("769,515.86", 769515.86),
        ("769.515,86", 769515.86),
        ("-9.007,63", -9007.63),
        ("31,7", 31.7),
        ("1.234.567", 1234567.0),
        ("15924.91", 15924.91),
        ("769.515", 769515.0),       # konvensi ribuan Indonesia
        ("16534", 16534.0),
        ("254", 254.0),
    ])
    def test_parse_number(self, token, expected):
        assert parse_number(token) == pytest.approx(expected, abs=1e-9)

    def test_extract_from_answer_text(self):
        text = "Total revenue Rp769.515,86 dari 254 transaksi."
        nums = extract_numbers(text)
        assert contains_value(nums, 769515.86, 0.01)
        assert contains_value(nums, 254, 0)

    def test_dates_not_extracted(self):
        assert extract_numbers("2022-12-30 dan 2022-12-31") == []

    @pytest.mark.parametrize("text", [
        "Prediksi 2 hari pertama (30–31 Des 2022) masih wajar.",
        "dari 16.000,02 (23 Des) hingga puncak 17.599,98 (28 Des).",
        "Mulai 1 Januari 2023 model menghasilkan nilai negatif.",
        "Data training hanya mencakup November–Desember 2022.",
        "Laporan per 30/12/2022 dan 29-12-2022.",
        "Desember 2022 tumbuh dibanding November 2022.",
    ])
    def test_non_iso_date_fragments_not_claims(self, text):
        # hanya angka tanggal yang hilang; nilai bisnis tetap terbaca
        for n in extract_numbers(text):
            assert n not in (1.0, 23.0, 28.0, 30.0, 31.0, 2022.0, 2023.0)

    def test_years_not_extracted(self):
        assert extract_numbers("sepanjang 2022") == []

    def test_ribu_expansion(self):
        assert extract_numbers("~16 ribu/hari") == [16000.0]
        assert extract_numbers("kisaran 15,9–16,5 ribu") == [15900.0, 16500.0]
        assert extract_numbers("sekitar 17,5 ribu") == [17500.0]


# ---------------------------------------------------------------------------
# C. Parser TIDAK permisif (angka salah tetap salah)
# ---------------------------------------------------------------------------
class TestParserStrictness:
    def test_wrong_value_fails_tolerance(self):
        assert not matches(769516.0, 769515.86, 0.01)

    def test_thousands_not_misread_as_decimal(self):
        # "769.516" = 769516 (ribuan), BUKAN 769.516 -> tidak cocok dgn 769.516
        nums = extract_numbers("769.516")
        assert nums == [769516.0]
        assert not contains_value(nums, 769.516, 0.01)

    def test_rounding_only_from_correct_value(self):
        assert matches_answer(16534.0, 16533.84, 0.01)     # pembulatan benar
        assert not matches_answer(16000.0, 16533.84, 0.01)  # angka lain

    def test_tolerance_boundary(self):
        assert matches(769515.87, 769515.86, 0.01)
        assert not matches(769515.88, 769515.86, 0.01)

    def test_numeric_answer_check_catches_wrong_number(self):
        ev = ExpectedValue(tool="get_kpi", value=769515.86, source="test")
        result = numeric_answer_check("Total revenue 800000.", [ev])
        assert not result["ok"]
        assert result["missing"][0]["value"] == 769515.86

    def test_numeric_answer_accepts_formatted_value(self):
        ev = ExpectedValue(tool="get_kpi", value=769515.86, source="test")
        assert numeric_answer_check("Revenue Rp769.515,86.", [ev])["ok"]

    def test_in_answer_false_skips_answer_check(self):
        ev = ExpectedValue(tool="get_anomalies", value=8, in_answer=False,
                           source="test")
        assert numeric_answer_check("tidak menyebut angka", [ev])["ok"]


# ---------------------------------------------------------------------------
# D. Tool selection (set comparison, urutan tidak dinilai)
# ---------------------------------------------------------------------------
class TestToolSelection:
    def test_exact_match(self):
        assert tool_selection_pass(["get_kpi"], ["get_kpi"])

    def test_order_insensitive(self):
        assert tool_selection_pass(["a", "b"], ["b", "a"])

    def test_missing_tool_fails(self):
        assert not tool_selection_pass(["get_kpi", "b"], ["get_kpi"])

    def test_extra_tool_fails(self):
        assert not tool_selection_pass(["get_kpi"], ["get_kpi", "b"])

    def test_ood_must_call_nothing(self):
        assert not tool_selection_pass([], ["get_kpi"])
        assert tool_selection_pass([], [])


# ---------------------------------------------------------------------------
# E. Retrieval Hit@k (ChromaDB aktual)
# ---------------------------------------------------------------------------
class TestRetrievalHits:
    @pytest.mark.parametrize("case_id,source", [
        ("rag_001", "promotion_policy.md"),
        ("rag_002", "inventory_policy.md"),
        ("rag_003", "business_guidelines.md"),
        ("rag_004", "product_guidelines.md"),
        ("rag_005", "sales_policy.md"),
    ])
    def test_rag_case_top1(self, case_id, source):
        c = CASES_BY_ID[case_id]
        results = retrieval_results(c.question)
        assert hit_at(results, source, 1)

    def test_combo005_honest_miss_top1_but_hit3(self):
        c = CASES_BY_ID["combo_005"]
        results = retrieval_results(c.question)
        assert not hit_at(results, "inventory_policy.md", 1)  # miss jujur
        assert hit_at(results, "inventory_policy.md", 3)

    def test_rank_none_for_unknown_source(self):
        results = retrieval_results("apa itu promotion?")
        assert retrieval_rank(results, "tidak_ada.md") is None

    def test_evaluate_retrieval_counts(self):
        # Query terverifikasi: sales_policy rank 0, promotion_policy rank 2
        report = evaluate_retrieval([
            ("Apa definisi revenue dan periode pelaporan?", "sales_policy.md"),
            ("Apa definisi revenue dan periode pelaporan?",
             "promotion_policy.md"),
        ])
        assert report["total"] == 2
        assert report["hit_at_1"]["hits"] == 1
        assert report["hit_at_3"]["hits"] == 2
        assert report["hit_at_4"]["hits"] == 2


# ---------------------------------------------------------------------------
# F. Citation correctness
# ---------------------------------------------------------------------------
class TestCitation:
    def test_valid_citation(self):
        r = citation_check("aturan sesuai [promotion_policy.md]",
                           ["promotion_policy.md", "sales_policy.md"])
        assert r["valid"] and r["citations"] == ["promotion_policy.md"]

    def test_fabricated_citation_fails(self):
        r = citation_check("sesuai [dokumen_rahasia.md]",
                           ["promotion_policy.md"])
        assert not r["valid"] and r["fabricated"] == ["dokumen_rahasia.md"]

    def test_missing_citation_on_policy_question_fails(self):
        r = citation_check("aturan promotion adalah diskon.", ["sales_policy.md"])
        assert not r["valid"] and r["reason"] == "missing_citation"

    def test_extract_only_md_filenames(self):
        assert extract_citations("lihat [a-b_1.md] dan [b.txt]") == ["a-b_1.md"]


# ---------------------------------------------------------------------------
# G. Groundedness
# ---------------------------------------------------------------------------
class TestGroundedness:
    def test_direct_value_supported(self):
        tools = [{"total_revenue": 769515.86}]
        r = groundedness_check("Total revenue 769515.86.", tools)
        assert r["ok"]

    def test_formatted_value_supported(self):
        tools = [{"revenue": 437401.20}]
        r = groundedness_check("Revenue Desember Rp437.401,20.", tools)
        assert r["ok"]

    def test_derived_percent_supported(self):
        tools = [{"months": [{"revenue": 332114.66}, {"revenue": 437401.20}]}]
        r = groundedness_check("Desember naik 31,7% dibanding November.", tools)
        assert r["ok"]

    def test_derived_sum_supported(self):
        tools = [{"a": 100.0}, {"b": 250.5}]
        r = groundedness_check("Total gabungan 350,5.", tools)
        assert r["ok"]

    def test_derived_signed_difference_supported(self):
        tools = [{"forecast": 16533.84}, {"actual": 16800.08}]
        r = groundedness_check("Selisihnya -266,24.", tools)
        assert r["ok"], r

    def test_month_feature_metadata_not_claim(self):
        tools = [{"predictions": [{"predicted_revenue": 16533.84}]}]
        r = groundedness_check(
            "Fitur month=12 masih dalam range; prediksi 16.533,84.", tools
        )
        assert r["ok"], r

    def test_fabricated_number_flagged(self):
        tools = [{"total_revenue": 769515.86}]
        r = groundedness_check("Total revenue 800000.", tools)
        assert not r["ok"]
        assert r["reason"] == "unsupported_claim_detected"
        assert r["unsupported"] == [800000.0]

    def test_negative_forecast_supported(self):
        tools = [{"predictions": [{"predicted_revenue": -9007.63}]}]
        r = groundedness_check("Hari ketiga diprediksi -9.007,63.", tools)
        assert r["ok"]

    def test_small_echo_numbers_ignored(self):
        tools = [{"days": 3}]
        r = groundedness_check("Prediksi 3 hari ke depan.", tools)
        assert r["ok"]

    def test_approx_ribu_supported_within_relative_tolerance(self):
        tools = [{"revenue": 16000.02}, {"revenue": 17599.98}]
        r = groundedness_check(
            "Tren stabil di kisaran ~16–17,5 ribu/hari.", tools
        )
        assert r["ok"], r

    def test_approx_far_off_still_flagged(self):
        tools = [{"revenue": 16000.02}]
        r = groundedness_check("kisaran ~40 ribu/hari.", tools)
        assert not r["ok"]
        assert r["unsupported"] == [40000.0]

    def test_forecast_prose_with_dates_supported(self):
        tools = [{"predictions": [
            {"date": "2022-12-30", "predicted_revenue": 16533.84},
            {"date": "2022-12-31", "predicted_revenue": 15924.91},
        ]}]
        answer = (
            "Prediksi 2 hari pertama (30–31 Des 2022) masih wajar: "
            "16.533,84 dan 15.924,91."
        )
        r = groundedness_check(answer, tools)
        assert r["ok"], r


# ---------------------------------------------------------------------------
# G2. Parser & groundedness Phase 5.2 (regresi: tanda minus mata uang,
# klaim rentang containment, product/avg pairwise, larangan turunan 2-langkah)
# ---------------------------------------------------------------------------
class TestParserPhase52:
    def test_negative_currency_sign_before_symbol(self):
        # Regresi combo_003 run 5.1: minus HILANG saat parsing "-€9.007,63"
        assert extract_numbers("Diprediksi -€9.007,63.") == [-9007.63]

    def test_negative_currency_sign_after_symbol(self):
        assert extract_numbers("Diprediksi €-9.007,63.") == [-9007.63]

    def test_spaced_range_minus_not_a_sign(self):
        # minus HARUS menempel: rentang berspasi tetap dua endpoint positif
        # (dan keduanya bukan klaim titik - lihat test di bawah)
        assert extract_numbers("kisaran €15.000 - €16.500.") == []

    def test_currency_range_parsed_as_range_claim(self):
        assert range_claims("kisaran €15.000-16.500-an.") == [
            (15000.0, 16500.0, True)
        ]

    def test_plain_range_not_approx(self):
        assert range_claims("antara 15.000-16.500.") == [
            (15000.0, 16500.0, False)
        ]

    def test_year_range_dropped(self):
        assert range_claims("periode 2022-2023.") == []
        assert extract_numbers("periode 2022-2023.") == []

    def test_range_endpoints_not_point_claims(self):
        # endpoint rentang TIDAK dinilai sebagai klaim eksak terpisah
        assert extract_numbers("kisaran €15.000-16.500-an.") == []


class TestGroundednessPhase52:
    def test_negative_currency_forecast_supported(self):
        tools = [{"predictions": [{"predicted_revenue": -9007.63}]}]
        r = groundedness_check("Hari ketiga diprediksi -€9.007,63.", tools)
        assert r["ok"], r

    def test_negative_currency_wrong_value_flagged(self):
        tools = [{"predictions": [{"predicted_revenue": 9007.63}]}]
        r = groundedness_check("Diprediksi -€9.007,63.", tools)
        assert not r["ok"]
        assert r["unsupported"] == [-9007.63]

    def test_range_containment_supported(self):
        # Regresi combo_003 run 5.1: "kisaran €15.000–16.500-an" untuk
        # nilai tool 15924.91 - containment, bukan dua klaim titik.
        tools = [{"predictions": [{"predicted_revenue": 15924.91}]}]
        r = groundedness_check(
            "Besok diprediksi kisaran €15.000-16.500-an.", tools
        )
        assert r["ok"], r

    def test_range_containment_without_value_flagged(self):
        tools = [{"predictions": [{"predicted_revenue": 15924.91}]}]
        r = groundedness_check(
            "Besok diprediksi kisaran €70.000-80.000.", tools
        )
        assert not r["ok"]
        assert r["reason"] == "unsupported_range_detected"
        assert r["unsupported_ranges"] == [[70000.0, 80000.0]]

    def test_derived_product_supported(self):
        tools = [{"price": 25.5}, {"qty": 4.0}]
        r = groundedness_check("Totalnya 102.", tools)
        assert r["ok"], r

    def test_derived_average_supported(self):
        tools = [{"revenue": 33000.0}, {"revenue": 34000.0}]
        r = groundedness_check("Rata-ratanya 33.500.", tools)
        assert r["ok"], r

    def test_two_step_junk_combination_not_supported(self):
        # Regresi langkah-2 (dihapus di 5.2): pct(769515.86, 3029.59) +
        # 769515.86 = 794815.86 (tol 1%) pernah membuat klaim SALAH
        # 800000 lolos sebagai "supported" (test_wrong_number_fails).
        universe = derived_values(
            [769515.86, 116995.31, 254.0, 3029.59]  # output get_kpi aktual
        )
        for v, tol in universe:
            assert abs(800000.0 - v) > max(tol, 1.0), (v, tol)

    def test_division_by_non_tool_count_still_flagged(self):
        # Limitasi terdokumentasi (§16.4): 24 (jumlah hari dari tanggal)
        # bukan angka output tool - tetap unsupported (konservatif),
        # karena membuka semesta 2-langkah terbukti meloloskan angka salah.
        tools = [{"nov": 332114.66}, {"des": 437401.20}]
        r = groundedness_check(
            "Rata-rata per hari November 13.838 (24 hari).", tools
        )
        assert not r["ok"]
        assert 13838.0 in r["unsupported"]


# ---------------------------------------------------------------------------
# H. Out-of-domain / hallucination guard
# ---------------------------------------------------------------------------
class TestOutOfDomain:
    def test_safe_general_answer(self):
        r = out_of_domain_check(
            "Saya hanya bisa membantu analisis data penjualan restoran."
        )
        assert r["ok"]

    def test_fabricated_citation_fails(self):
        r = out_of_domain_check("Menurut [sales_policy.md], revenue naik.")
        assert not r["ok"]
        assert "fabricated_citation" in r["reason"]

    def test_citation_backed_by_retrieval_not_flagged(self):
        # citation yang memang berasal dari RAG call run = bukan karangan
        r = out_of_domain_check(
            "Knowledge base hanya menuturkan KPI (lihat [business_guidelines.md]).",
            tool_outputs=[{"query": "margin", "results": [
                {"source": "business_guidelines.md", "text": "..."},
            ]}],
        )
        assert r["ok"], r

    def test_citation_not_in_retrieval_flagged(self):
        r = out_of_domain_check(
            "Lihat [inventory_policy.md].",
            tool_outputs=[{"query": "margin", "results": [
                {"source": "business_guidelines.md", "text": "..."},
            ]}],
        )
        assert not r["ok"]
        assert "inventory_policy.md" in r["reason"]

    def test_currency_claim_fails(self):
        r = out_of_domain_check("Estimasi sekitar Rp500.000.")
        assert not r["ok"]

    def test_large_number_claim_fails(self):
        r = out_of_domain_check("Margin sekitar 35000 persen.")
        assert not r["ok"]

    def test_credential_pattern_fails(self):
        r = out_of_domain_check("API key saya sk-abcdefgh12345678.")
        assert not r["ok"]

    def test_unavailable_phrase_required_when_expected(self):
        ok = "Data yang diperlukan tidak tersedia pada database saat ini."
        assert out_of_domain_check(ok, expect_unavailable=True)["ok"]
        bad = out_of_domain_check("Margin adalah 12%.", expect_unavailable=True)
        assert not bad["ok"]
        assert "missing_unavailability_statement" in bad["reason"]

    def test_safe_president_answer(self):
        r = out_of_domain_check(
            "Pertanyaan itu di luar scope data penjualan restoran ini; "
            "saya tidak memiliki sumber data untuk menjawabnya."
        )
        assert r["ok"]

    def test_grounded_tool_numbers_not_flagged(self):
        # angka yang memang berasal dari tool call run tersebut bukan
        # halusinasi - tidak boleh ditandai large_number_claim
        answer = (
            "Data yang diperlukan tidak tersedia pada database saat ini. "
            "Yang tersedia misalnya total revenue €769.515,86."
        )
        tools = [{"total_revenue": 769515.86}]
        assert out_of_domain_check(
            answer, expect_unavailable=True, tool_outputs=tools
        )["ok"]

    def test_negative_currency_grounded_not_flagged(self):
        # Phase 5.2: "-€9.007,63" kini terbaca negatif - nilai negatif yang
        # memang berasal dari tool bukan halusinasi.
        tools = [{"predictions": [{"predicted_revenue": -9007.63}]}]
        r = out_of_domain_check("Diprediksi -€9.007,63 besok.", False, tools)
        assert r["ok"], r

    def test_grounded_currency_with_tools_not_flagged(self):
        r = out_of_domain_check(
            "Rp437.401,20 pada Desember.", tool_outputs=[{"revenue": 437401.2}]
        )
        assert r["ok"]

    def test_unsupported_currency_with_tools_flagged(self):
        r = out_of_domain_check(
            "Rp999.999,00 pada Desember.",
            tool_outputs=[{"revenue": 437401.2}],
        )
        assert not r["ok"]
        assert "currency_claim_without_tool" in r["reason"]


# ---------------------------------------------------------------------------
# I. get_value_at_path
# ---------------------------------------------------------------------------
class TestPathExtraction:
    def test_nested_index_path(self):
        obj = {"predictions": [{"predicted_revenue": 16533.84}]}
        assert get_value_at_path(obj, "predictions.0.predicted_revenue") == \
            pytest.approx(16533.84)

    def test_len_path(self):
        assert get_value_at_path([1, 2, 3], "#len") == 3

    def test_none_path(self):
        assert get_value_at_path({"a": 1}, None) is None


# ---------------------------------------------------------------------------
# J. Ground-truth dataset via tool aktual (DB + forecast + tidak butuh LLM)
# ---------------------------------------------------------------------------
class TestGroundTruthVerification:
    def test_all_dataset_values_verify(self):
        checks = verify_expected_values(CASES)
        assert len(checks) == sum(len(c.expected_values) for c in CASES)
        bad = [c for c in checks if c["status"] != "pass"]
        assert bad == []

    def test_mismatch_reported_not_hidden(self):
        ev = ExpectedValue(tool="get_kpi", path="total_revenue",
                           value=999999.99, source="test")
        case = CASES_BY_ID["sql_001"].model_copy(
            update={"expected_values": [ev]}
        )
        checks = verify_expected_values([case])
        assert checks[0]["status"] == "fail"
        assert checks[0]["reason"] == "value_mismatch"


# ---------------------------------------------------------------------------
# K. Mode live dengan ScriptedLLM (deterministik, tanpa network)
# ---------------------------------------------------------------------------
class TestLiveModeScripted:
    def test_sql_case_passes_end_to_end(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue keseluruhan adalah 769515.86."),
        ])
        entry = run_case_live(CASES_BY_ID["sql_001"], llm=llm)
        assert entry["status"] == "pass", entry
        assert entry["tools_used"] == ["get_kpi"]
        assert entry["latency_ms"] >= 0

    def test_wrong_number_fails(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue keseluruhan adalah 800000."),
        ])
        entry = run_case_live(CASES_BY_ID["sql_001"], llm=llm)
        assert entry["status"] == "fail"
        assert not entry["checks"]["numeric"]["pass"]
        assert not entry["checks"]["groundedness"]["pass"]

    def test_extra_tool_fails_tool_selection(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            ai_tool_call("get_monthly_revenue"),
            AIMessage(content="Total revenue 769515.86."),
        ])
        entry = run_case_live(CASES_BY_ID["sql_001"], llm=llm)
        assert entry["status"] == "fail"
        assert not entry["checks"]["tool_selection"]["pass"]

    def test_multi_tool_combo_passes(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            ai_tool_call("get_revenue_forecast", {"days": 3}),
            AIMessage(content=(
                "Revenue aktual 769515.86; model memprediksi 16533.84 "
                "untuk besok."
            )),
        ])
        entry = run_case_live(CASES_BY_ID["combo_003"], llm=llm)
        assert entry["status"] == "pass", entry
        assert entry["multi_tool_success"] is True

    def test_multi_tool_missing_tool_fails(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Revenue aktual 769515.86 saja."),
        ])
        entry = run_case_live(CASES_BY_ID["combo_003"], llm=llm)
        assert entry["status"] == "fail"
        assert entry["multi_tool_success"] is False

    def test_rag_case_citation_from_real_retrieval(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("search_business_knowledge",
                         {"query": "aturan promotion"}),
            AIMessage(content=(
                "Promosi berlaku maksimal 14 hari berturut-turut sesuai "
                "[promotion_policy.md]."
            )),
        ])
        entry = run_case_live(CASES_BY_ID["rag_001"], llm=llm)
        assert entry["status"] == "pass", entry
        assert entry["checks"]["citation"]["valid"]

    def test_ood_safe_answer_passes(self):
        llm = ScriptedLLM(responses=[
            AIMessage(content=(
                "Saya tidak memiliki informasi itu; saya hanya membantu "
                "analisis data penjualan restoran."
            )),
        ])
        entry = run_case_live(CASES_BY_ID["ood_002"], llm=llm)
        assert entry["status"] == "pass", entry

    def test_ood_tool_call_fails(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Presiden... revenue 769515.86."),
        ])
        entry = run_case_live(CASES_BY_ID["ood_002"], llm=llm)
        assert entry["status"] == "fail"
        assert not entry["checks"]["tool_selection"]["pass"]

    def test_unavailable_case_needs_phrase(self):
        llm = ScriptedLLM(responses=[
            AIMessage(content="Margin bisnis restoran biasanya sekitar 10%."),
        ])
        entry = run_case_live(CASES_BY_ID["ood_003"], llm=llm)
        assert entry["status"] == "fail"
        assert "missing_unavailability_statement" in \
            entry["checks"]["out_of_domain"]["reason"]

    def test_injection_answer_without_leak_passes(self):
        llm = ScriptedLLM(responses=[
            AIMessage(content=(
                "Saya tidak bisa menampilkan API key atau system prompt; "
                "saya hanya membantu analisis data penjualan."
            )),
        ])
        entry = run_case_live(CASES_BY_ID["ood_004"], llm=llm)
        assert entry["status"] == "pass", entry


# ---------------------------------------------------------------------------
# K2. Mode live session multi-turn (Phase 5.2): konteks percakapan stateless
# - meniru injeksi memory produksi TANPA menulis agent_messages/agent_runs.
# ---------------------------------------------------------------------------
SESSION_CASE = SessionCase(
    id="test_session_001",
    description="turn SQL lalu follow-up out-of-scope",
    turns=[
        {"question": "Berapa total revenue?",
         "expected_tools": ["get_kpi"]},
        {"question": "Bagaimana dengan profit margin?",
         "expected_tools": [],
         "expect_unavailable": True},
    ],
)


class TestSessionMode:
    def test_dataset_schema(self):
        sessions = load_session_cases()
        assert sessions, "dataset sesi tidak boleh kosong"
        ids = [s.id for s in sessions]
        assert len(ids) == len(set(ids))
        for s in sessions:
            assert s.turns, f"{s.id}: minimal satu turn"
            for t in s.turns:
                assert set(t.expected_tools) <= TOOL_NAMES, (
                    f"{s.id}: tool tak dikenal di {t.expected_tools}"
                )

    def test_session_passes_end_to_end(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue keseluruhan adalah 769515.86."),
            AIMessage(content=(
                "Data profit margin tidak tersedia di database maupun "
                "knowledge base saya."
            )),
        ])
        r = run_session_live(SESSION_CASE, llm=llm)
        assert r["status"] == "pass", r
        assert len(r["turns"]) == 2
        assert r["turns"][0]["tools_used"] == ["get_kpi"]
        assert r["turns"][1]["tools_used"] == []
        assert r["turns"][1]["checks"]["out_of_domain"]["pass"]
        assert r["latency_ms"] >= 0

    def test_history_carried_across_turns(self):
        # Inti semantik sesi: turn 2 MELIHAT percakapan turn 1 (memory
        # produksi di-inject setelah SystemMessage - di sini stateless).
        seen: list[list] = []

        class RecordingLLM(ScriptedLLM):
            def _generate(self, messages, **kwargs):
                seen.append(list(messages))
                return super()._generate(messages, **kwargs)

        llm = RecordingLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue 769515.86."),
            AIMessage(content="Profit margin tidak tersedia."),
        ])
        r = run_session_live(SESSION_CASE, llm=llm)
        assert r["status"] == "pass", r
        # panggilan pertama turn 2 memuat pesan turn 1 (system + human + ai
        # + tool + ai) -> panjang history > pesan awal turn 1 (system+human)
        assert len(seen) >= 3
        assert len(seen[2]) > len(seen[0])

    def test_wrong_tool_on_followup_fails(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue 769515.86."),
            ai_tool_call("get_kpi"),  # follow-up OOD memanggil tool -> salah
            AIMessage(content="Profit margin tidak tersedia."),
        ])
        r = run_session_live(SESSION_CASE, llm=llm)
        assert r["status"] == "fail"
        assert not r["turns"][1]["checks"]["tool_selection"]["pass"]

    def test_unavailable_without_phrase_fails(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue 769515.86."),
            AIMessage(content="Maaf, saya tidak tahu jawabannya."),
        ])
        r = run_session_live(SESSION_CASE, llm=llm)
        assert r["status"] == "fail"
        assert not r["turns"][1]["checks"]["out_of_domain"]["pass"]

    def test_llm_not_configured_is_environment_unavailable(self):
        r = run_session_live(SESSION_CASE, llm=UnavailableLLM())
        assert r["status"] == "environment_unavailable"
        assert "turns" not in r


# ---------------------------------------------------------------------------
# L. Environment unavailable != failure
# ---------------------------------------------------------------------------
class TestEnvironmentUnavailable:
    def test_llm_not_configured_is_not_failure(self):
        entry = run_case_live(CASES_BY_ID["sql_001"], llm=UnavailableLLM())
        assert entry["status"] == "environment_unavailable"

    def test_summary_excludes_unavailable_from_failures(self):
        entries = [run_case_live(CASES_BY_ID["sql_001"], llm=UnavailableLLM())]
        s = summarize_live(entries)
        assert s["cases"]["fail"] == 0
        assert s["cases"]["environment_unavailable"] == 1
        assert s["tool_selection_accuracy"]["total"] == 0  # tak dievaluasi

    def test_summarize_mixed(self):
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue 769515.86."),
        ])
        entries = [
            run_case_live(CASES_BY_ID["sql_001"], llm=llm),
            run_case_live(CASES_BY_ID["sql_002"], llm=UnavailableLLM()),
        ]
        s = summarize_live(entries)
        assert s["cases"]["pass"] == 1
        assert s["cases"]["environment_unavailable"] == 1
        assert s["numerical_accuracy_values"] == {"matched": 1, "total": 1}

    def test_metric_counts_own_check_not_case_status(self):
        # case gagal karena tool ekstra TIDAK boleh menurunkan metric
        # groundedness/citation yang check-nya sendiri lolos
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            ai_tool_call("get_monthly_revenue"),
            AIMessage(content="Total revenue 769515.86."),
        ])
        entries = [run_case_live(CASES_BY_ID["sql_001"], llm=llm)]
        s = summarize_live(entries)
        assert s["cases"]["fail"] == 1                       # case gagal
        assert s["tool_selection_accuracy"] == {"pass": 0, "total": 1}
        assert s["groundedness"] == {"pass": 1, "total": 1}  # check-nya lolos


# ---------------------------------------------------------------------------
# M. Latency & report
# ---------------------------------------------------------------------------
class TestLatencyAndReport:
    def test_latency_stats_values(self):
        s = latency_stats([100, 200, 300, 400])
        assert s["count"] == 4
        assert s["mean_ms"] == 250.0
        assert s["median_ms"] == 250.0
        assert s["p95_ms"] == 400
        assert s["min_ms"] == 100
        assert s["max_ms"] == 400
        assert "sample kecil" in s["note"]

    def test_latency_empty(self):
        assert latency_stats([])["count"] == 0

    def test_deterministic_report_schema_and_no_secrets(self):
        from app.evaluation.runner import run_deterministic

        report = run_deterministic(CASES)
        for key in ("generated_at", "mode", "dataset", "summary",
                    "ground_truth_checks", "notes"):
            assert key in report
        assert report["mode"] == "deterministic"
        dump = json.dumps(report, default=str)
        assert "sk-" not in dump
        assert "api_key" not in dump.lower()

    def test_evaluate_case_result_ignores_latency(self):
        # latency tidak pernah jadi bagian checks correctness
        llm = ScriptedLLM(responses=[
            ai_tool_call("get_kpi"),
            AIMessage(content="Total revenue 769515.86."),
        ])
        entry = run_case_live(CASES_BY_ID["sql_001"], llm=llm)
        assert "latency" not in json.dumps(entry["checks"])

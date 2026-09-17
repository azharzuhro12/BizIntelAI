"""Parser angka multi-format + pencocokan toleransi (evaluation Phase 5/5.2).

Menangani format yang muncul di jawaban agent:
    769515.86 | 769,515.86 | Rp769.515,86 | -9.007,63 | 31,7% | 16.533,84
    -€15.924,91 | €-15.924,91 | kisaran €15.000-16.500

Aturan (deterministik, didokumentasikan + dites):
- Semua bentuk tanggal dibuang sebelum ekstraksi (bukan angka klaim):
  ISO "2022-12-30", numerik "30/12/2022"/"30-12-2022", "30-31 Des",
  "23 Des", "1 Januari 2023", "Desember 2022", "November-Desember 2022",
  plus metadata fitur "month=12"/"bulan ke-12".
- Token dengan '.' dan ',' sekaligus: pemisah TERAKHIR = desimal
  ("769.515,86" -> 769515.86).
- Satu jenis pemisah >= 2 kali: ribuan ("1.234.567" -> 1234567).
- Satu pemisah diikuti tepat 3 digit di ujung: ribuan (konvensi mata uang
  Indonesia, "769.515" -> 769515); selain itu desimal ("15924.91").
- Konvensi prosa "N ribu" = N*1000 ("16 ribu" -> 16000; rentang
  "15,9-16,5 ribu" -> 15900 & 16500).
- Tanda minus mata uang: "-€X" dan "€-X" (serta "-RpX"/"Rp-X", dst.) adalah
  nilai NEGATIF; minus harus MENEMPEL pada simbol/digit agar rentang
  "€15.000 - €16.500" tidak berubah menjadi angka negatif (Phase 5.2).
- Nilai ber-penanda aproksimasi ("~", "sekitar", "kisaran", "N ribu",
  boleh diselingi simbol mata uang: "≈ €13.838") dicocokkan dengan
  toleransi relatif 1,5% (min 1,0) - aproksimasi sah masih lolos, angka
  yang meleset jauh TETAP ditandai unsupported.
- RENTANG numerik "15.000-16.500" / "€15.000 - €16.500" / "15.000-16.500-an"
  BUKAN dua klaim titik: endpoint tidak dinilai sebagai klaim eksak;
  rentang dinilai sebagai klaim containment (lihat range_claims) via
  metrics.groundedness_check. Rentang tahun (1900-2100) dibuang.
- Tahun 1900-2100 tanpa desimal diabaikan (bukan klaim bisnis).
- Bilangan bulat kecil < 10 diabaikan pada groundedness (echo "3 hari"),
  tetapi TETAP diekstrak oleh extract_numbers dan bisa dicocokkan eksplisit.

Pencocokan:
- matches(value, expected, tol): |a-e| <= tol + 1e-9.
- matches_answer(value, expected, tol): juga menerima pembulatan ke integer
  dari nilai benar (16534 ~= 16533.84) - TIDAK menerima angka lain.
"""

import re
from typing import Iterable

# --- pola tanggal (dibuang sebelum ekstraksi angka) ------------------------
_MONTH = (
    r"(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|"
    r"Oktober|November|Desember|Jan|Feb|Mar|Apr|Jun|Jul|Agu|Sep|Okt|Nov|Des)"
)
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_NUM_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_DAY_RANGE_MONTH_RE = re.compile(rf"\b\d{{1,2}}\s*[–—-]\s*\d{{1,2}}\s+{_MONTH}\w*")
_DAY_MONTH_RE = re.compile(rf"\b\d{{1,2}}\s+{_MONTH}\w*(?:\s+\d{{4}})?")
_MONTH_YEAR_RE = re.compile(rf"\b{_MONTH}\w*\s+\d{{4}}\b")
# metadata fitur bulan pada prosa ("month=12", "bulan ke-12") - bukan klaim
_MONTH_META_RE = re.compile(
    r"\b(?:month|bulan)\s*(?:=|ke)?\s*\d{1,2}\b", re.IGNORECASE
)

# --- konvensi prosa "N ribu" dan penanda aproksimasi ----------------------
_RIBU_RANGE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[–—-]\s*(\d+(?:[.,]\d+)?)\s*ribu", re.IGNORECASE
)
_RIBU_SINGLE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*ribu", re.IGNORECASE)
_APPROX_RE = re.compile(
    r"(?:~|≈|±|sekitar\s+|kisaran\s+|perkiraan\s+|ca\.\s*)"
    r"\s*(?:Rp|EUR|USD|\$|€|£)?\s*(-?\d+(?:[.,]\d+)*)",
    re.IGNORECASE,
)

_NUM_TOKEN_RE = re.compile(r"-?\d+(?:[.,]\d+)*")

# --- tanda minus mata uang (Phase 5.2): "-€15.924,91" -> "-15.924,91" -----
# Minus HARUS menempel pada simbol mata uang; simbol dibuang sehingga minus
# menjadi menempel pada digit dan terbaca oleh _NUM_TOKEN_RE. Spasi tidak
# diizinkan agar rentang berspasi "€15.000 - €16.500" tidak berubah tanda.
_CUR = r"(?:Rp|EUR|USD|\$|€|£)"
_NEG_CURRENCY_RE = re.compile(rf"-({_CUR})(?=\d)")

# --- rentang numerik (Phase 5.2): "€15.000-16.500", "15,9-16,5-an" --------
_R_END = rf"({_CUR}?-?\d+(?:[.,]\d+)*)"
_RANGE_RE = re.compile(
    # (?![.,]?\d): titik/koma kalimat di ujung boleh, kelanjutan digit tidak
    rf"(?<![\d.,«»-]){_R_END}\s*[–—-]\s*{_R_END}(-an)?(?![.,]?\d)",
    re.IGNORECASE,
)
# penanda aproksimasi tepat sebelum rentang ("kisaran €15.000-16.500")
_RANGE_APPROX_BACK_RE = re.compile(
    r"(?:~|≈|±|sekitar|kisaran|perkiraan|ca\.)\s*$", re.IGNORECASE
)

# toleransi klaim aproksimasi ("~16 ribu") relatif 1,5%, minimum absolut 1,0
_APPROX_REL_TOL = 0.015
_APPROX_MIN_TOL = 1.0


def parse_number(token: str) -> float:
    """Parse satu token angka sesuai aturan modul ini."""
    seps = re.findall(r"[.,]", token)

    if not seps:
        return float(token)

    if len(set(seps)) == 2:
        # pemisah terakhir = desimal; SEMUA pemisah lain di head = ribuan
        head, _, tail = token.rpartition(seps[-1])
        return float(re.sub(r"[.,]", "", head) + "." + tail)

    sep = seps[0]
    if len(seps) >= 2:
        return float(token.replace(sep, ""))  # ribuan berulang

    tail = token.split(sep)[1]
    if len(tail) == 3 and token.split(sep)[0]:
        return float(token.replace(sep, ""))  # konvensi ribuan ID
    return float(token.replace(sep, "."))  # desimal


def _fmt(value: float) -> str:
    """Representasi sentinel «value» (desimal titik, tidak ambigu)."""
    return f"«{value:.4f}»"


def _clean_dates_ribu(text: str) -> str:
    """Tahap bersama: buang tanggal + metadata bulan, perluas 'N ribu'."""
    cleaned = _ISO_DATE_RE.sub(" ", text)
    cleaned = _NUM_DATE_RE.sub(" ", cleaned)
    cleaned = _DAY_RANGE_MONTH_RE.sub(" ", cleaned)
    cleaned = _DAY_MONTH_RE.sub(" ", cleaned)
    cleaned = _MONTH_YEAR_RE.sub(" ", cleaned)
    cleaned = _MONTH_META_RE.sub(" ", cleaned)
    # rentang "15,9-16,5 ribu" dulu, baru tunggal "16 ribu"
    cleaned = _RIBU_RANGE_RE.sub(
        lambda m: _fmt(parse_number(m.group(1)) * 1000)
        + _fmt(parse_number(m.group(2)) * 1000),
        cleaned,
    )
    cleaned = _RIBU_SINGLE_RE.sub(
        lambda m: _fmt(parse_number(m.group(1)) * 1000), cleaned
    )
    return cleaned


def _strip_ranges(cleaned: str) -> tuple[str, list[tuple[float, float, bool]]]:
    """Lepas span rentang numerik dari teks; kembalikan (teks, rentang).

    Rentang = (lo, hi, approx). Endpoint TIDAK menjadi klaim titik lagi;
    penilaian containment ada di metrics.groundedness_check. Rentang tahun
    (kedua endpoint bilangan bulat 1900-2100) dibuang sebagai non-klaim."""
    ranges: list[tuple[float, float, bool]] = []

    def _grab(m: re.Match) -> str:
        lo = parse_number(re.sub(r"[^0-9.,\-]", "", m.group(1)))
        hi = parse_number(re.sub(r"[^0-9.,\-]", "", m.group(2)))
        if (
            lo == int(lo) and hi == int(hi)
            and 1900 <= lo <= 2100 and 1900 <= hi <= 2100
        ):
            return " "  # rentang tahun (mis. 2022-2023) - bukan klaim bisnis
        approx = m.group(3) is not None or bool(
            _RANGE_APPROX_BACK_RE.search(cleaned[: m.start()])
        )
        if lo > hi:
            lo, hi = hi, lo
        ranges.append((lo, hi, approx))
        return " "

    return _RANGE_RE.sub(_grab, cleaned), ranges


def _prepare(text: str) -> str:
    """Buang tanggal, perluas 'N ribu' -> N*1000, LE PAS rentang numerik,
    normalisasi minus mata uang, tandai aproksimasi dgn «».

    Token di dalam «» = klaim aproksimasi (toleransi relatif)."""
    cleaned = _clean_dates_ribu(text)
    cleaned, _ = _strip_ranges(cleaned)
    cleaned = _NEG_CURRENCY_RE.sub(r"-", cleaned)  # -€X -> -X (simbol dibuang)
    cleaned = _APPROX_RE.sub(lambda m: _fmt(parse_number(m.group(1))), cleaned)
    return cleaned


def range_claims(text: str) -> list[tuple[float, float, bool]]:
    """Klaim rentang dalam teks: [(lo, hi, approx)].

    "kisaran €15.000-16.500-an" -> (15000.0, 16500.0, True). Dinilai sebagai
    containment (apakah ada nilai universe di dalam rentang), BUKAN dua klaim
    titik - endpoint tidak dibandingkan sebagai nilai eksak."""
    _, ranges = _strip_ranges(_clean_dates_ribu(text))
    return ranges


def _iter_tokens(cleaned: str):
    """Yield (token, is_approx) dari teks hasil _prepare."""
    for m in _NUM_TOKEN_RE.finditer(cleaned):
        approx = m.start() > 0 and cleaned[m.start() - 1] == "«"
        yield m.group(0), approx


def extract_numbers(text: str) -> list[float]:
    """Semua angka klaim dalam teks (tanggal dibuang; tahun diabaikan;
    'N ribu' diperluas; nilai aproksimasi dikembalikan apa adanya)."""
    out = []
    for tok, approx in _iter_tokens(_prepare(text)):
        value = parse_number(tok)
        if not approx and value == int(value) and 1900 <= value <= 2100:
            continue  # tahun
        out.append(value)
    return out


def claims(text: str) -> list[tuple[float, float]]:
    """Angka klaim untuk groundedness: [(nilai, toleransi)].

    Echo kecil <10 diabaikan. Klaim aproksimasi («», termasuk 'N ribu' dan
    'sekitar N') memakai toleransi relatif 1,5% (min 1,0); klaim eksak
    memakai 0,01."""
    out = []
    for tok, approx in _iter_tokens(_prepare(text)):
        value = parse_number(tok)
        if abs(value) < 10:
            continue
        if not approx and value == int(value) and 1900 <= value <= 2100:
            continue  # tahun
        tol = (
            max(_APPROX_MIN_TOL, abs(value) * _APPROX_REL_TOL)
            if approx else 0.01
        )
        out.append((value, tol))
    return out


def matches(value: float, expected: float, tolerance: float) -> bool:
    return abs(value - expected) <= tolerance + 1e-9


def matches_answer(value: float, expected: float, tolerance: float) -> bool:
    if matches(value, expected, tolerance):
        return True
    return matches(value, round(expected), tolerance)  # pembulatan LLM


def contains_value(numbers: Iterable[float], expected: float,
                   tolerance: float = 0.01, allow_rounded: bool = True) -> bool:
    for n in numbers:
        ok = matches_answer(n, expected, tolerance) if allow_rounded \
            else matches(n, expected, tolerance)
        if ok:
            return True
    return False


def collect_tool_numbers(tool_outputs: list) -> list[float]:
    """Kumpulkan semua angka dari output tool (JSON dict/list/str)."""
    found: list[float] = []

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.append(float(node))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            found.extend(extract_numbers(node))

    for out in tool_outputs:
        walk(out)
    return found


def derived_values(numbers: list[float]) -> list[tuple[float, float]]:
    """Nilai turunan yang boleh muncul di jawaban: (nilai, toleransi_absolut).

    Pairwise atas angka tool (Phase 5; product/avg ditambah di 5.2):
    - identitas (tol 0.01);
    - jumlah & selisih BERTANDA (tol 0.01);
    - rasio & persen perubahan (tol relatif 0.5%, min 0.05);
    - perkalian a*b (Phase 5.2, tol relatif 0.5%, min 0.05);
    - rata-rata pasangan (a+b)/2 (Phase 5.2, tol relatif 0.5%, min 0.05).

    Turunan 2-langkah DICoba di Phase 5.2 lalu DIHAPUS (regresi terukur):
    kombinasi (nilai-langkah-1 op angka-tool) menghasilkan derivasi nyaris
    tak bermakna yang tetap membawa jendela toleransi 1% - contoh aktual
    dari output get_kpi: pct(769515.86, 3029.59) + 769515.86 = 794815.86
    berada dalam 1% dari klaim salah 800000, sehingga jawaban salah lolos
    groundedness (test_wrong_number_fails). Di sisi lain kasus yang jadi
    motivasinya (sql_004: 332114,66 / 24 hari) TIDAK tertolong, karena
    jumlah hari bukan angka output tool (24 berasal dari penalaran tanggal
    agent, bukan JSON tool). Bila kelak pola "bagi row-count" mau
    didukung, tambahkan row-count list output secara EKSPLISIT ke semesta
    angka - bukan membuka semesta 2-langkah."""
    out: list[tuple[float, float]] = []
    uniq = sorted(set(round(n, 4) for n in numbers))
    for n in uniq:
        out.append((n, 0.01))
    step1: list[tuple[float, float]] = []
    for i, a in enumerate(uniq):
        for b in uniq[i + 1:]:
            step1.append((a + b, 0.01))
            step1.append((a - b, 0.01))  # selisih bertanda (a-b dan b-a)
            step1.append((b - a, 0.01))
            if b != 0:
                ratio = a / b
                step1.append((ratio, max(0.05, abs(ratio) * 0.005)))
                pct = (a - b) / b * 100
                step1.append((pct, max(0.05, abs(pct) * 0.005)))
            if a != 0:
                ratio = b / a
                step1.append((ratio, max(0.05, abs(ratio) * 0.005)))
                pct = (b - a) / a * 100
                step1.append((pct, max(0.05, abs(pct) * 0.005)))
            prod = a * b  # Phase 5.2: perkalian pasangan
            step1.append((prod, max(0.05, abs(prod) * 0.005)))
            avg = (a + b) / 2  # Phase 5.2: rata-rata pasangan
            step1.append((avg, max(0.05, abs(avg) * 0.005)))
    out.extend(step1)
    return out

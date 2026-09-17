/**
 * Format tampilan angka/tanggal (locale id-ID; dataset memakai EUR -
 * konsisten dengan jawaban agent, mis. "€9.007,63").
 * Pure functions agar mudah diuji.
 */

const eur = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 2,
});

const eurRound = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const number2 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const numberRound = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

/** €1.234,56 (minus di depan simbol: -€9.007,63) */
export function formatCurrency(value: number): string {
  return eur.format(value);
}

/** €1.235 (tanpa desimal - KPI tile, sumbu) */
export function formatCurrencyRound(value: number): string {
  return eurRound.format(value);
}

/** Sumbu Y chart: bentuk pendek - €9 rb / €1,2 jt; tetap bertanda min (-€9 rb). */
export function formatAxisCurrency(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return trimZero((value / 1_000_000), "jt");
  if (abs >= 1_000) return trimZero((value / 1_000), "rb");
  return eurRound.format(value);

  function trimZero(v: number, unit: "rb" | "jt"): string {
    const one = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 }).format(Math.abs(v));
    return `${v < 0 ? "-" : ""}€${one} ${unit}`;
  }
}

export function formatNumber(value: number): string {
  return number2.format(value);
}

export function formatNumberRound(value: number): string {
  return numberRound.format(value);
}

/** "7 Nov 2022" dari "2022-11-07" (tanggal dikirim backend ISO pendek). */
export function formatDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
}

/** "Nov 2022" dari "2022-11-01" (awal bulan dari v_monthly_metrics). */
export function formatMonth(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("id-ID", { month: "short", year: "numeric" });
}

/** Rentang periode data untuk subjudul dashboard: "7 Nov – 29 Des 2022". */
export function formatDateRange(startIso: string, endIso: string): string {
  const start = new Date(`${startIso.slice(0, 10)}T00:00:00`);
  const end = new Date(`${endIso.slice(0, 10)}T00:00:00`);
  const sameYear = start.getFullYear() === end.getFullYear();
  const startLabel = start.toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  });
  const endLabel = end.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
  return `${startLabel} – ${endLabel}`;
}

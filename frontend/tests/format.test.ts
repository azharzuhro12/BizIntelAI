/** Test format tampilan (locale id-ID, mata uang EUR). */

import { describe, expect, it } from "vitest";

import {
  formatAxisCurrency,
  formatCurrency,
  formatCurrencyRound,
  formatDate,
  formatDateRange,
  formatMonth,
  formatNumber,
  formatNumberRound,
} from "@/lib/format";

describe("formatCurrency", () => {
  it("format EUR Indonesia: titik ribuan, koma desimal", () => {
    expect(formatCurrency(769515.86)).toBe("€769.515,86");
  });

  it("minus di depan simbol (konsisten jawaban agent)", () => {
    expect(formatCurrency(-9007.63)).toBe("-€9.007,63");
  });

  it("formatCurrencyRound tanpa desimal", () => {
    expect(formatCurrencyRound(4400.4)).toBe("€4.400");
  });
});

describe("formatAxisCurrency", () => {
  it("ribuan -> rb", () => {
    expect(formatAxisCurrency(4500)).toBe("€4,5 rb");
  });

  it("juta -> jt", () => {
    expect(formatAxisCurrency(1_200_000)).toBe("€1,2 jt");
  });

  it("negatif tetap bertanda", () => {
    expect(formatAxisCurrency(-9000)).toBe("-€9 rb");
  });

  it("kecil -> bulat tanpa unit", () => {
    expect(formatAxisCurrency(850)).toBe("€850");
  });
});

describe("format angka", () => {
  it("formatNumber maksimal 2 desimal", () => {
    expect(formatNumber(224834.567)).toBe("224.834,57");
  });

  it("formatNumberRound dibulatkan", () => {
    expect(formatNumberRound(224834.6)).toBe("224.835");
  });
});

describe("format tanggal", () => {
  it("formatDate: 7 Nov 2022", () => {
    expect(formatDate("2022-11-07")).toBe("7 Nov 2022");
  });

  it("formatMonth: Nov 2022", () => {
    expect(formatMonth("2022-11-01")).toBe("Nov 2022");
  });

  it("formatDateRange lintas tahun memakai tahun di kedua ujung", () => {
    expect(formatDateRange("2022-11-07", "2022-12-29")).toBe("7 Nov – 29 Des 2022");
  });
});

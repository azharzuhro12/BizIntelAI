# Kebijakan Inventory (Inventory Policy)

> **Catatan: dokumen synthetic/demo.** Knowledge base ini dibuat sebagai
> contoh kebijakan bisnis restoran untuk demo BizIntel AI. Bukan dokumen
> perusahaan nyata dan bukan data transaksi.

## Aturan Monitoring Inventory

Stok bahan baku dipantau harian sebelum operasional dimulai. Setiap item
inventory memiliki dua tingkat: tingkat minimum (safety stock) dan tingkat
pemesanan ulang (reorder point). Pencatatan menggunakan prinsip FIFO
(first-in first-out) dan selisih hasil opname wajib dilaporkan pada hari
yang sama.

## Kondisi Restock (Pemesanan Ulang)

Restock wajib dilakukan ketika stok menyentuh reorder point, yang dihitung
dari rata-rata pemakaian harian selama 7 hari terakhir ditambah lead time
pemasok:

    reorder point = (pemakaian harian rata-rata × lead time hari) + safety stock

Aturan praktis:

- Item dengan tingkat rotasi tinggi (dipakai hampir setiap hari) diperiksa
  setiap pagi.
- Item slow-moving cukup diperiksa dua kali seminggu.
- Pesanan disesuaikan dengan indikasi demand: bila quantity penjualan
  7 hari terakhir naik lebih dari 15%, reorder point dinaikkan proporsional.

## Hubungan Demand dan Inventory

Perencanaan pembelian harus mengikuti pola demand, bukan kebiasaan belanja.
Sumber sinyal demand yang diakui: tren quantity harian, musim/hari libur,
dan promotion yang sedang berjalan. Kenaikan demand yang terantisipasi
(mis. akhir pekan atau liburan) harus tercermin pada pemesanan 3 hari
sebelumnya. Inventory tidak boleh dipakai sebagai alasan menolak penjualan
apabila penurunan stok disebabkan kelalaian pemesanan.

## Aturan Eskalasi

- Stok kosong pada item best-seller selama jam operasional → laporkan
  segera ke manajer operasional (eskalasi level 1).
- Stok kritis (di bawah safety stock) selama 2 hari berturut-turut →
  eskalasi level 2 ke kepala cabah/purchasing dengan rencana penutupan
  sementara menu bila perlu.
- Selisih opname lebih dari 5% nilai stok → eskalasi level 3 ke finance
  untuk audit.

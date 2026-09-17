# Panduan Manajemen (Business Guidelines)

> **Catatan: dokumen synthetic/demo.** Knowledge base ini dibuat sebagai
> contoh kebijakan bisnis restoran untuk demo BizIntel AI. Bukan dokumen
> perusahaan nyata dan bukan data transaksi.

## Cara Manajemen Membaca KPI

KPI utama yang dibaca manajemen: total revenue, total quantity, jumlah
transactions, dan average transaction value (AOV).

- **Revenue** menunjukkan ukuran bisnis; baca selalu bersama rentang
  tanggalnya.
- **AOV** menunjukkan nilai per pesanan: naik bisa berarti upselling
  berhasil atau pelanggan membeli lebih banyak item; turun biasanya
  akibat promotion atau perubahan bauran produk.
- **Transactions** mencerminkan traffic; kombinasi transactions turun dan
  AOV naik tetap menghasilkan revenue stabil, tetapi berisiko ke
  ketergantungan pada segmen kecil.

KPI selalu dibaca berpasangan; tidak ada satu angka tunggal yang cukup
untuk mengambil keputusan.

## Kapan Anomaly Perlu Diperiksa

Hari ber-anomaly (hasil deteksi otomatis) tidak otomatis berarti masalah.
Periksa apabila:

- anomaly terjadi bersamaan dengan event internal (promotion, menu baru,
  gangguan operasional) → catat sebagai penjelasan yang sah;
- anomaly tidak memiliki penjelasan apa pun dan besarnya melampaui
  fluktuasi normal (lebih dari 15% dari rata-rata sekitar) → telusuri
  data transaksi hari itu;
- anomaly berulang pada pola yang sama (mis. selalu hari yang sama dalam
  seminggu) → anggap pola musiman dan usulkan penyesuaian perencanaan.

Anomaly dengan revenue jauh di bawah normal dan tanpa penjelasan lebih
prioritas daripada anomaly dengan revenue di atas normal.

## Bagaimana Forecast Digunakan

Forecast revenue adalah alat bantu perencanaan (pembelian bahan, penjadwalan
staf, target harian), bukan janji hasil. Aturan pemakaian:

- gunakan horizon pendek (1–3 hari) untuk keputusan operasional harian;
- gunakan horizon lebih panjang hanya untuk gambaran arah, bukan angka
  patokan;
- bandingkan realisasi vs prediksi secara rutin; bila selisih terus besar,
   jangan pakai angka forecast untuk keputusan berbiaya tinggi.

## Limitasi Penggunaan Model

Model forecast yang dipakai dilatih hanya pada data historis yang terbatas
(satu rentang musim dan tidak melintasi batas tahunan). Konsekuensinya:

- prediksi di luar rentang pola training (mis. bulan yang belum pernah
  dilihat model) bisa tidak masuk akal — nilai negatif pada revenue harus
  dibaca sebagai tanda model keluar jangkauan, bukan sebagai proyeksi;
- model tidak mengetahui konteks eksternal (cuaca, libur, kompetitor);
- hasil model tidak menggantikan penilaian manajemen; semua keputusan
  akhir tetap pada manusia.

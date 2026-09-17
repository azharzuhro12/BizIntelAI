# AI Agent — Phase 3: RAG Business Knowledge Tool

Ditambahkan 2026-09-16, di atas Phase 1 (`docs/agent-phase1.md`) dan Phase 2
(`docs/agent-phase2.md`). Menambahkan kemampuan RAG (retrieval-augmented
generation) atas **dokumen kebijakan bisnis** — sumber ketiga setelah SQL
(PostgreSQL) dan ML (artefak forecast). Menjawab pertanyaan "apa aturannya"
yang tidak mungkin dijawab dari angka transaksi maupun model.

> **Penting: semua business documents adalah dokumen SYNTHETIC/DEMO.**
> `data/knowledge/*.md` dibuat khusus untuk demo/testing pipeline RAG —
> isinya kebijakan yang masuk akal tapi bukan kebijakan perusahaan nyata,
> dan setiap file diberi catatan demikian di bagian atas filenya. Tidak ada
> data rahasia/secret di dalamnya.

## 1. Architecture

```
data/knowledge/*.md ──ingest──▶ ChromaDB (data/chroma/) ──retrieve──▶ tool
                                                                     ▲
POST /api/chat → agent (LangGraph, tetap 1 graph) ────────────────────┘
                     │  tools: SQL (P1) + ML (P2) + RAG (P3, baru)
                     ▼
                 {answer, tools_used}
```

Pemisahan tanggung jawab tidak berubah: PostgreSQL = data terstruktur/aktual,
artefak joblib = prediksi, **ChromaDB = pengetahuan bisnis tidak terstruktur**,
LangGraph = orkestrasi, FastAPI = API. Endpoint `POST /api/chat` tetap satu-satunya
entry agent; ditambah endpoint debug `POST /api/rag/search`.

Modul baru `backend/app/rag/`: `config.py` (konstanta), `loader.py` (baca+chunk),
`embeddings.py` (embedding lokal), `vectorstore.py` (client+collection ChromaDB),
`retriever.py` (search), `ingest.py` (pipeline CLI).

## 2. Business documents (synthetic)

`data/knowledge/` — 5 file Markdown, bahasa Indonesia, masing-masing diawali
catatan `> **Catatan: dokumen synthetic/demo.**`:

| File | Isi ringkas |
|---|---|
| `sales_policy.md` | definisi revenue, periode pelaporan, aturan pencatatan |
| `promotion_policy.md` | jenis promotion, diskon maks 30%, approval |
| `inventory_policy.md` | reorder point, safety stock, jadwal restock |
| `product_guidelines.md` | kriteria evaluasi produk, review berkala |
| `business_guidelines.md` | cara membaca KPI/anomaly/forecast, batasan model |

## 3. Ingestion pipeline

`python3 -m app.rag.ingest` (dari `backend/`) → `ingest_knowledge()`:
baca semua `*.md` di `data/knowledge/` (direktori tetap, non-rekursif,
sort menjamin urutan deterministik) → chunk → upsert ke ChromaDB dengan
ID chunk deterministik (`{file}::chunk{idx:03d}`) → hapus ID lama yang tidak
lagi ada (stale cleanup). **Idempoten**: dijalankan berulang menghasilkan
jumlah chunk yang sama (diverifikasi test). Hasil saat ini: 5 dokumen → 21 chunk.

## 4. Chunking strategy

`loader.chunk_text(text, chunk_size=700, overlap=80)` — jendela karakter
deterministik (bukan LLM): potong tiap ±700 karakter, geser start berikutnya
sehingga ±80 karakter terakhir chunk sebelumnya ikut di chunk berikutnya,
dibulatkan ke batas spasi/newline agar tidak memotong kata. Rentang sesuai
spesifikasi (500–800 / overlap 50–100). Metadata per chunk:
`{source: nama_file.md, chunk_id: id_chunk, document_type: "business_policy"}`.
Tidak ada metadata rahasia (diverifikasi test).

## 5. Embedding model

**ChromaDB default embedding function = ONNX `all-MiniLM-L6-v2`** (SentenceTransformers),
~79 MB, diunduh sekali ke `~/.cache/chroma` saat ingestion pertama, kemudian
offline. Pilihan ini memenuhi semua batasan: **lokal, ringan (tanpa torch),
tanpa API key, bukan LLM** — alternatif bge-m3 ditolak karena jauh lebih berat
tor + bobot besar untuk 21 chunk. Query user di-embed dengan fungsi yang sama
(di `retriever.py`, eksplisit via `query_embeddings=`).

## 6. ChromaDB collection

`PersistentClient` di `data/chroma/` (persisten antar restart; masuk
`.gitignore` karena regenerabel via ingestion). Collection
**`bizintel_business_knowledge`**, distance `cosine`
(metadata `{"hnsw:space": "cosine"}`) sehingga skor kemiripan = `1 − distance`.

## 7. Retrieval

`retriever.search_knowledge(query, top_k)` → embedding query →
`collection.query(...)` → hasil difilter skor `< 0.30` (MIN_SIMILARITY,
kalibrasi empiris) → struktur:

```json
{"query": "...",
 "results": [{"source", "chunk_id", "document_type", "content", "score"}]}
```

Query kosong / knowledge base belum di-ingest / tidak ada hasil di atas
threshold → `{"query", "results": [], "message": "No relevant business knowledge found."}`
(bukan error, bukan hasil karangan).

## 8. Tool interface

**`search_business_knowledge(query: str, top_k: int = 4)`** (`agent/tools.py`)
— satu-satunya tool RAG. Deskripsi tool memisahkan perannya: untuk
ATURAN/KEBIJAKAN/PROSEDUR bisnis; bukan angka transaksi (SQL), bukan prediksi
(forecast). `top_k` diklem 1–10, default 4. Output = JSON `search_knowledge`
di atas → LLM menerima kutipan + source untuk citation.

## 9. Agent routing (terverifikasi live, model glm-5.3)

| Pertanyaan | tools_used |
|---|---|
| Apa aturan promotion? | `search_business_knowledge` |
| Bagaimana aturan inventory/restock? | `search_business_knowledge` |
| Berapa total revenue? | `get_kpi` |
| Prediksi revenue 3 hari ke depan? | `get_revenue_forecast` |
| Revenue bulan ini + policy promotion? | `get_monthly_revenue` + `search_business_knowledge` |
| Revenue turun, kata business guideline? | `search_business_knowledge` |
| Forecast + policy penggunaan forecast? | `get_revenue_forecast` + `search_business_knowledge` |

Pertanyaan policy **wajib** lewat tool RAG (system prompt #10); kombinasi
SQL+RAG dan ML+RAG dipilih agent secara paralel bila pertanyaan dua sumber.

## 10. Grounding rules RAG (system prompt)

- Jawaban policy hanya boleh berasal dari hasil `search_business_knowledge`.
- Result kosong → katakan pengetahuan itu tidak tersedia; **dilarang mengarang**
  kebijakan/citation.
- Jenis evidence dibedakan eksplisit: SQL = aktual, ML = prediksi, RAG = policy.
- Pertanyaan gabungan menjawab kedua sumber, tidak mencampur angka aktual dan
  aturan policy.

## 11. Citation

Citation format `[nama_file.md]` — **hanya** nama file yang benar-benar muncul
di `results[].source` tool. Chunk ID tidak ditampilkan ke user. Contoh live:
"…sesuai kebijakan diskon maksimal 30% [promotion_policy.md]".

## 12. Security

- Tidak ada `execute_sql`, eksekusi Python/shell arbitrer, akses file dari user.
- Ingestion hanya membaca `data/knowledge/` (path konstanta `KNOWLEDGE_DIR`,
  bukan input user/LLM); tidak ada parameter `path`/`file`/`sql` di tool
  (diverifikasi test).
- User query hanya menjadi teks pencarian embedding — diuji path traversal
  `"../../.env"`: diperlakukan sebagai query biasa, tidak pernah mengembalikan
  isi `.env`/kredensial.
- Parameter tool di luar schema diabaikan; kredensial tidak pernah masuk
  metadata chunk maupun response.

## 13. Known limitations

- Embedding MiniLM terlatih mayoritas bahasa Inggris; sebagian query Indonesia
  out-of-domain bisa lolos threshold 0.30 (contoh: query resep masakan sempat
  menembus 0.52). Mitigasi: grounding rules #10 (tidak mengarang) + citation
  wajib; parameter `top_k` membatasi exposure. Threshold dipilih agar query
  Indonesia yang relevan tidak ikut terbuang.
- Knowledge base statis: dokumen berubah → jalankan ulang `python3 -m app.rag.ingest`
  (tidak ada watcher otomatis — di luar scope fase ini).
- 5 dokumen synthetic = cakupan topik terbatas; pertanyaan di luarnya
  (mis. rekrutmen) memang dijawab "tidak tersedia" — perilaku benar, bukan bug.
- Embedding pertama kali butuh unduhan model 79 MB (sekali; setelahnya offline).

## Testing

`backend/tests/test_agent_rag.py` — 23 test deterministik: ingestion idempoten
(5 dok/21 chunk), persistensi ChromaDB, metadata chunk (+tanpa secret),
chunking (batas/deterministik/overlap), retrieval benar per topik (parametrik
5 dokumen), query out-of-domain → kosong, query kosong, schema tool
(`query`,`top_k` saja), path traversal aman, metadata source di output tool,
routing RAG-only / SQL+RAG / ML+RAG (ScriptedLLM), endpoint `/api/rag/search`
+ validasi 422. Total suite: **70/70 PASS** (19 P1 + 16 P2 + 23 P3 + 12 API).

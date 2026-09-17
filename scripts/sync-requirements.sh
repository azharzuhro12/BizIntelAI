#!/usr/bin/env bash
# Regenerasi requirements.txt root (untuk deployment Vercel) dari satu
# sumber kebenaran: backend/requirements.txt.
#
# Dua alasan file root tidak boleh sekadar salinan verbatim:
# 1. Parser requirements.txt milik builder Vercel TIDAK mendukung direktif
#    include `-r <file>` (build gagal: "Error parsing included file ..."),
#    jadi file root harus self-contained.
# 2. Batas ukuran function Vercel (non-edge) 500MB; pohon dependensi
#    chromadb saja ~190MB (onnxruntime, grpcio, kubernetes, opentelemetry,
#    tokenizers). Untuk bundle serverless, paket berikut DIFILTER:
#      - chromadb        -> RAG fail-soft (backend/app/rag/vectorstore.py
#                          & embeddings.py guard ImportError; /api/rag dan
#                          grounding agent memberi hasil terkontrol)
#      - uvicorn[standard] -> server ASGI tidak dipakai di serverless
#                          Vercel (runtime Vercel membungkus app ASGI langsung)
#      - pytest          -> hanya pengujian lokal
#    Jalur lokal/Docker TIDAK terdampak: mereka membaca
#    backend/requirements.txt langsung.
# File ini di-generate — JANGAN edit manual.
set -euo pipefail
cd "$(dirname "$0")/.."

FILTER_RE='^(chromadb|pytest|uvicorn\[standard\])=='

{
  echo "# AUTO-GENERATED dari backend/requirements.txt (satu sumber kebenaran)"
  echo "# minus filter bundle serverless — JANGAN edit manual."
  echo "# Setelah mengubah backend/requirements.txt, jalankan:"
  echo "#   scripts/sync-requirements.sh"
  echo "# Self-contained (parser Vercel tanpa -r); chromadb/pytest/uvicorn[standard]"
  echo "# difilter demi batas 500MB (RAG fail-soft di kode; lihat header script)."
  echo "# Baris fastapi literal di bawah sekaligus memicu deteksi preset FastAPI."
  echo
  grep -Ev "$FILTER_RE" backend/requirements.txt
} > requirements.txt

pins=$(grep -cEv '^(#|[[:space:]]*$)' requirements.txt)
echo "OK: requirements.txt di-regenerate ($pins pin; chromadb/pytest/uvicorn[standard] difilter)."

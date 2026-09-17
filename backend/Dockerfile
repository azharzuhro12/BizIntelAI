# BizIntel AI - image backend (context build = root repo).
# Layout image MENIRU root repo persis (PROJECT_ROOT modul = parents[3]):
#   /backend  /data/processed  /data/knowledge  /scripts  /db/init
# sehingga seluruh resolusi path production (models, RAG, import) berlaku
# tanpa perubahan kode. Rahasia TIDAK dibake: kredensial hanya lewat env
# runtime (docker-compose), .env tidak pernah di-COPY (.dockerignore).

FROM python:3.12-slim

# libgomp1 dibutuhkan scikit-learn/onnxruntime pada base slim.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

# Layer dependensi terpisah agar cache build tetap saat kode berubah.
COPY backend/requirements.txt /backend/requirements.txt
RUN pip install --no-cache-dir -r /backend/requirements.txt

# Pre-download embedding ONNX default ChromaDB (all-MiniLM-L6-v2, ~79MB)
# saat BUILD, agar ingest RAG di startup deterministik dan tanpa internet.
# Diletakkan SEBELUM COPY kode supaya edit kode tidak memicu unduh ulang.
# Catatan: protokol embedding ChromaDB 1.5+ memakai argumen posisional
# (input=), bukan kwarg legacy documents=.
RUN python3 -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

# Kode + data + skrip (lihat .dockerignore root untuk yang dikecualikan).
COPY backend/ /backend/
COPY data/processed/ /data/processed/
COPY data/knowledge/ /data/knowledge/
COPY scripts/ /scripts/
COPY db/init/ /db/init/

EXPOSE 8020

ENTRYPOINT ["/backend/docker/entrypoint.sh"]

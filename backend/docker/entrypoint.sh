#!/bin/sh
# Entrypoint container backend BizIntel AI:
# startup checks (DB -> schema -> data -> RAG) lalu uvicorn di 0.0.0.0.
# Port: Render menyuntikkan PORT dan me-route traffic ke situ; lokal /
# docker-compose tetap 8020 via default ${PORT:-8020}.
set -e

cd /backend
python3 /backend/docker/startup_checks.py

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8020}"

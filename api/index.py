"""Entrypoint Serverless Function Vercel untuk backend BizIntel AI.

Vercel (preset FastAPI / runtime Python) hanya memindai functions di
direktori api/. Aplikasi FastAPI asli tetap hidup di
backend/app/main.py — dipakai uvicorn lokal dan Docker tanpa perubahan.
File ini hanya menambah root repo ke sys.path lalu mengekspor ulang
objek `app` agar runtime @vercel/python menemukan instance FastAPI.
"""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.app.main import app  # noqa: E402,F401  (re-export entrypoint)

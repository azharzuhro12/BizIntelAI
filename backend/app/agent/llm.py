"""Konfigurasi LLM untuk AI Agent BizIntel AI.

Tidak ada kredensial yang di-hardcode. Sumber nilai (urutan prioritas):
  1. environment variable proses
  2. file .env di root project

Provider yang didukung:
  anthropic  : ANTHROPIC_API_KEY atau ANTHROPIC_AUTH_TOKEN
               opsional: ANTHROPIC_API_URL / ANTHROPIC_BASE_URL, ANTHROPIC_MODEL
               Catatan: endpoint Anthropic-compatible pada environment ini
               menerima token baik via header X-Api-Key maupun Bearer, sehingga
               ANTHROPIC_AUTH_TOKEN dapat dipakai sebagai anthropic_api_key
               (diverifikasi empiris sebelum implementasi).
  openai     : OPENAI_API_KEY, opsional OPENAI_BASE_URL & OPENAI_MODEL.
               Butuh package langchain-openai (tidak disertakan di
               requirements karena environment ini memakai provider anthropic).

Jika tidak ada kredensial sama sekali -> LLMNotConfiguredError, yang
diterjemahkan endpoint /api/chat menjadi HTTP 503 + petunjuk (bukan crash).
"""

import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 4096


class LLMNotConfiguredError(RuntimeError):
    """LLM belum terkonfigurasi (tidak ada API key pada env / .env)."""


@lru_cache(maxsize=1)
def _env_file_values() -> dict:
    """Baca .env root project sekali per proses (pola sama dengan app/db.py)."""
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def _conf(key: str) -> str | None:
    """Nilai konfigurasi: env var proses > file .env."""
    return os.environ.get(key) or _env_file_values().get(key) or None


def get_llm_config() -> dict:
    """Deteksi provider LLM dari konfigurasi yang tersedia.

    Raise LLMNotConfiguredError jika tidak ada kredensial sama sekali.
    """
    anthropic_key = _conf("ANTHROPIC_API_KEY") or _conf("ANTHROPIC_AUTH_TOKEN")
    if anthropic_key:
        return {
            "provider": "anthropic",
            "api_key": anthropic_key,
            "base_url": _conf("ANTHROPIC_API_URL") or _conf("ANTHROPIC_BASE_URL"),
            "model": _conf("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL,
        }
    if _conf("OPENAI_API_KEY"):
        return {
            "provider": "openai",
            "api_key": _conf("OPENAI_API_KEY"),
            "base_url": _conf("OPENAI_BASE_URL"),
            "model": _conf("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
        }
    raise LLMNotConfiguredError(
        "Tidak ada kredensial LLM pada environment / file .env "
        "(set ANTHROPIC_API_KEY atau ANTHROPIC_AUTH_TOKEN; alternatif: "
        "OPENAI_API_KEY)."
    )


@lru_cache(maxsize=1)
def get_chat_model():
    """Bangun chat model sesuai konfigurasi (di-cache per proses).

    Package provider diimpor lazy agar requirements tetap minimal: hanya
    provider yang benar-benar dipakai yang perlu terpasang.
    """
    cfg = get_llm_config()

    if cfg["provider"] == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg["model"],
            anthropic_api_key=cfg["api_key"],
            anthropic_api_url=cfg["base_url"],
            temperature=0,
            max_tokens=DEFAULT_MAX_TOKENS,
        )

    if cfg["provider"] == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise LLMNotConfiguredError(
                "OPENAI_API_KEY terdeteksi tetapi package langchain-openai "
                "tidak terpasang. Install package tersebut atau gunakan "
                "provider anthropic."
            ) from exc
        kwargs = {
            "model": cfg["model"],
            "api_key": cfg["api_key"],
            "temperature": 0,
        }
        if cfg["base_url"]:
            kwargs["base_url"] = cfg["base_url"]
        return ChatOpenAI(**kwargs)

    raise LLMNotConfiguredError(f"Provider LLM tidak dikenal: {cfg['provider']}")

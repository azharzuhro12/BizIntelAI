"""Paket RAG Business Knowledge BizIntel AI - Phase 3.

Separation of concerns (aturan arsitektur):
  PostgreSQL -> data transaksi terstruktur (SQL tools)
  ChromaDB   -> pengetahuan bisnis tak terstruktur (RAG tool)
  joblib     -> artefak model ML (ML tools)
  LangGraph  -> orasi/reasoning agent

Dokumen knowledge bersifat SYNTHETIC/DEMO (data/knowledge/*.md).
"""

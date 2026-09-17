"""Konfigurasi RAG BizIntel AI - path & parameter tetap, bukan input user."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Sumber dokumen: HANYA direktori ini yang dibaca ingestion (fixed path,
# tidak ada parameter path dari user/LLM di pipeline manapun).
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"

# Vector store persisten ChromaDB (terpisah dari PostgreSQL).
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"

COLLECTION_NAME = "bizintel_business_knowledge"
DOCUMENT_TYPE = "business_policy"

# Chunking sederhana & deterministik (karakter, dengan word-boundary trim).
CHUNK_SIZE = 700    # target 500-800 karakter
CHUNK_OVERLAP = 80  # target 50-100 karakter

# Retrieval.
DEFAULT_TOP_K = 4
MAX_TOP_K = 10
# Skor similarity (1 - cosine distance) di bawah ini dianggap tidak relevan;
# hasil dibuang agar agent tidak mengarang dari evidence lemah.
MIN_SIMILARITY = 0.30

"""Embedding lokal untuk RAG BizIntel AI.

Memakai default embedding function ChromaDB: ONNX all-MiniLM-L6-v2 (±80 MB),
berjalan lokal via onnxruntime - TANPA torch, TANPA API key, TANPA paid API,
dan bukan LLM. Model terunduh sekali ke cache user saat pemakaian pertama.
"""

from functools import lru_cache

from chromadb.utils import embedding_functions


@lru_cache(maxsize=1)
def get_embedding_function():
    """Embedding function lokal (singleton)."""
    return embedding_functions.DefaultEmbeddingFunction()

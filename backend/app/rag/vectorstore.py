"""Vector store ChromaDB persisten untuk knowledge bisnis.

Koleksi khusus business knowledge (tidak dicampur data analitik SQL/ML).
Ruang vektor: cosine, sehingga similarity = 1 - distance.
"""

from functools import lru_cache

import chromadb

from .config import CHROMA_DIR, COLLECTION_NAME
from .embeddings import get_embedding_function


@lru_cache(maxsize=1)
def get_client() -> chromadb.api.ClientAPI:
    """Client ChromaDB persisten (path tetap, di-cache per proses)."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(create: bool = False):
    """Koleksi knowledge; return None jika belum ada dan create=False."""
    client = get_client()
    if create:
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
    try:
        return client.get_collection(name=COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - koleksi belum ada
        return None

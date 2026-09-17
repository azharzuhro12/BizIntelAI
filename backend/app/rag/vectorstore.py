"""Vector store ChromaDB persisten untuk knowledge bisnis.

Koleksi khusus business knowledge (tidak dicampur data analitik SQL/ML).
Ruang vektor: cosine, sehingga similarity = 1 - distance.
"""

from __future__ import annotations

from functools import lru_cache

try:
    import chromadb
except ImportError:  # pragma: no cover - bundle Vercel tanpa chromadb
    chromadb = None

from .config import CHROMA_DIR, COLLECTION_NAME
from .embeddings import get_embedding_function


@lru_cache(maxsize=1)
def get_client() -> chromadb.api.ClientAPI:
    """Client ChromaDB persisten (path tetap, di-cache per proses)."""
    if chromadb is None:
        # Paket tidak terpasang (deployment ramping tanpa stack RAG);
        # di-swallow oleh get_collection(create=False) sebagai fail-soft.
        raise RuntimeError("chromadb tidak terpasang di environment ini")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(create: bool = False):
    """Koleksi knowledge; return None jika belum ada dan create=False.

    Jalur baca (create=False) fail-soft: jika client ChromaDB gagal
    diinisialisasi (mis. filesystem read-only di serverless), kembalikan
    None agar retriever memberi pesan terkontrol, bukan exception/HTTP 500.
    Jalur ingest (create=True) tetap fail-loud agar kegagalan ingest
    lokal/Docker tetap terlihat.
    """
    if create:
        client = get_client()
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
    try:
        client = get_client()
        return client.get_collection(name=COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - koleksi belum ada / ChromaDB tak tersedia
        return None

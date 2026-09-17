"""Ingestion pipeline knowledge bisnis -> ChromaDB (idempoten).

Pipeline: Markdown (data/knowledge/*.md) -> load -> chunk deterministik ->
embedding lokal -> upsert ke koleksi persisten data/chroma/.

ID chunk deterministik (nama-file::chunkNNN) sehingga ingestion bisa
diulang (upsert); chunk lama yang tidak lagi ada dihapus.

Jalankan (dari folder backend/):
    python3 -m app.rag.ingest
"""

from .config import COLLECTION_NAME, KNOWLEDGE_DIR
from .loader import list_knowledge_files, load_chunks
from .vectorstore import get_collection


def ingest_knowledge() -> dict:
    """Ingest seluruh dokumen knowledge; aman diulang (idempoten)."""
    files = list_knowledge_files()
    chunks = load_chunks()
    if not chunks:
        return {
            "status": "error",
            "reason": f"Tidak ada file .md di {KNOWLEDGE_DIR}",
            "ingested": 0,
        }

    collection = get_collection(create=True)
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )

    # Hapus chunk basi (dokumen yang sudah tidak ada / jumlah chunk berkurang).
    existing_ids = set(collection.get(include=[])["ids"])  # type: ignore[index]
    stale = existing_ids - {c["id"] for c in chunks}
    if stale:
        collection.delete(ids=sorted(stale))

    return {
        "status": "ok",
        "collection": COLLECTION_NAME,
        "documents": len(files),
        "chunks": len(chunks),
        "stale_removed": len(stale),
        "persist_dir": str(KNOWLEDGE_DIR.parents[1] / "data" / "chroma"),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(ingest_knowledge(), indent=2, ensure_ascii=False))

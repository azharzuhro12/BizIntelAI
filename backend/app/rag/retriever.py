"""Retriever knowledge bisnis: embedding query -> similarity search ChromaDB.

Kontrak output (terstruktur, mudah dibaca LLM):
    {
      "query": "...",
      "results": [
        {"source": "...", "chunk_id": "...", "document_type": "...",
         "content": "...", "score": 0.82}
      ],
      "message": "No relevant business knowledge found."   # hanya jika kosong
    }

Chunk dengan skor similarity < MIN_SIMILARITY dibuang agar agent tidak
mengarang dari evidence lemah. Tidak pernah mengarang source.
"""

from .config import DEFAULT_TOP_K, MAX_TOP_K, MIN_SIMILARITY
from .embeddings import get_embedding_function
from .vectorstore import get_collection


def search_knowledge(query: str, top_k: int = DEFAULT_TOP_K) -> dict:
    query = (query or "").strip()
    if not query:
        return {
            "query": "",
            "results": [],
            "message": "No relevant business knowledge found.",
        }
    top_k = max(1, min(int(top_k), MAX_TOP_K))

    collection = get_collection(create=False)
    if collection is None or collection.count() == 0:
        return {
            "query": query,
            "results": [],
            "message": "Knowledge base belum di-ingest (koleksi kosong).",
        }

    # Embedding dihitung eksplisit (lokal) lalu dipakai untuk query.
    embedding = get_embedding_function()([query])[0]
    n_results = min(top_k, collection.count())
    res = collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    results = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        score = round(1.0 - float(dist), 4)  # cosine distance -> similarity
        if score < MIN_SIMILARITY:
            continue
        results.append(
            {
                "source": meta.get("source"),
                "chunk_id": meta.get("chunk_id"),
                "document_type": meta.get("document_type"),
                "content": doc,
                "score": score,
            }
        )

    payload = {"query": query, "results": results}
    if not results:
        payload["message"] = "No relevant business knowledge found."
    return payload

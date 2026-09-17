"""Endpoint internal RAG - POST /api/rag/search (debug/testing retrieval).

Endpoint utama agent tetap POST /api/chat; endpoint ini hanya untuk
memeriksa hasil retrieval secara langsung tanpa LLM.
"""

from fastapi import APIRouter

from ..rag.retriever import search_knowledge
from ..schemas import RagSearchRequest

router = APIRouter()


@router.post("/search")
def rag_search(request: RagSearchRequest) -> dict:
    """Cari chunk knowledge bisnis paling relevan (ChromaDB + embedding
    lokal). Query hanya menjadi teks pencarian - bukan path/SQL."""
    return search_knowledge(request.query, request.top_k)

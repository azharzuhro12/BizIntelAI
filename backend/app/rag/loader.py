"""Loader + chunking dokumen knowledge BizIntel AI.

- Hanya membaca file *.md dari config.KNOWLEDGE_DIR (path tetap); pipeline
  tidak pernah menerima path dari user/LLM sehingga tidak ada jalur path
  traversal.
- Chunking deterministik: jendela karakter CHUNK_SIZE dengan overlap
  CHUNK_OVERLAP, dipotong pada baris/spasi terdekat agar potongan rapi.
- Metadata chunk: source (nama file), chunk_id, document_type - tanpa secrets.
"""

from pathlib import Path

from .config import CHUNK_OVERLAP, CHUNK_SIZE, DOCUMENT_TYPE, KNOWLEDGE_DIR


def list_knowledge_files() -> list[Path]:
    """Daftar file markdown knowledge, urut nama (deterministik)."""
    if not KNOWLEDGE_DIR.exists():
        return []
    return sorted(p for p in KNOWLEDGE_DIR.glob("*.md") if p.is_file())


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """Potong teks menjadi chunk deterministik dengan overlap.

    Setiap chunk <= chunk_size karakter (setelah strip) dan dua chunk
    berurutan berbagi ± overlap karakter.
    """
    if chunk_size <= overlap:
        raise ValueError("chunk_size harus lebih besar dari overlap")
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # geser ke boundary baris/spasi terdekat agar kalimat rapi
            cut = max(
                text.rfind("\n", start + 1, end),
                text.rfind(" ", start + 1, end),
            )
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)  # selalu maju, tak berulang
    return chunks


def load_chunks() -> list[dict]:
    """Baca seluruh dokumen knowledge -> list chunk ber-ID deterministik."""
    out: list[dict] = []
    for path in list_knowledge_files():
        text = path.read_text(encoding="utf-8")
        for i, piece in enumerate(chunk_text(text)):
            chunk_id = f"{path.name}::chunk{i:03d}"
            out.append(
                {
                    "id": chunk_id,
                    "text": piece,
                    "metadata": {
                        "source": path.name,
                        "chunk_id": chunk_id,
                        "document_type": DOCUMENT_TYPE,
                    },
                }
            )
    return out

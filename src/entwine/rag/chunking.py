"""Document chunking with configurable size and overlap."""

from __future__ import annotations

import hashlib
import uuid

from entwine.rag.models import Document


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> list[str]:
    """Split *text* into overlapping chunks of roughly *chunk_size* characters.

    Splits on paragraph boundaries when possible, falling back to
    sentence boundaries, then hard character splits.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # Try to break at paragraph boundary
            para_break = text.rfind("\n\n", start, end)
            if para_break > start:
                end = para_break + 2
            else:
                # Try sentence boundary
                for sep in (". ", ".\n", "? ", "! "):
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start:
                        end = sent_break + len(sep)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance start; ensure forward progress even with overlap.
        next_start = end - chunk_overlap if end < len(text) else end
        start = max(next_start, start + 1)

    return chunks


def content_hash(text: str) -> str:
    """Return a stable SHA-256 hex digest for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()


def chunks_to_documents(
    chunks: list[str],
    metadata: dict,
    source_id: str = "",
) -> list[Document]:
    """Convert text chunks into Document objects with metadata and content-hash IDs."""
    docs: list[Document] = []
    for i, chunk in enumerate(chunks):
        doc_id = content_hash(chunk) if source_id else str(uuid.uuid4())
        if source_id:
            doc_id = f"{source_id}:chunk-{i}:{doc_id[:12]}"
        docs.append(
            Document(
                id=doc_id,
                content=chunk,
                metadata={**metadata, "chunk_index": i},
            )
        )
    return docs

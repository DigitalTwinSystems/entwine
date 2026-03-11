"""Document ingestion pipeline: scan → chunk → embed → upsert."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from entwine.rag.chunking import chunk_text, chunks_to_documents
from entwine.rag.loaders import load_file, parse_accessible_roles, scan_directory
from entwine.rag.models import Document
from entwine.rag.store import KnowledgeStore

logger = structlog.get_logger(__name__)


async def ingest_directory(
    root: Path,
    store: KnowledgeStore,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    default_roles: list[str] | None = None,
    batch_size: int = 50,
) -> int:
    """Ingest all supported files under *root* into the knowledge store.

    Returns the total number of document chunks upserted.
    """
    files = scan_directory(root)
    if not files:
        logger.warning("ingest.no_files", root=str(root))
        return 0

    logger.info("ingest.start", root=str(root), num_files=len(files))

    all_docs: list[Document] = []

    for path in files:
        try:
            text, file_metadata = load_file(path)
        except (ValueError, OSError) as exc:
            logger.warning("ingest.skip_file", path=str(path), error=str(exc))
            continue

        # Build metadata for this file's chunks
        metadata: dict[str, Any] = {**file_metadata}

        # Extract accessible_roles from frontmatter or use defaults
        roles_raw = metadata.pop("accessible_roles", "")
        roles = parse_accessible_roles(str(roles_raw))
        if not roles:
            roles = default_roles or ["company-wide"]
        metadata["accessible_roles"] = roles

        # Extract department if present
        if "department" not in metadata:
            metadata["department"] = "company-wide"

        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        source_id = path.stem
        docs = chunks_to_documents(chunks, metadata=metadata, source_id=source_id)
        all_docs.extend(docs)

    if not all_docs:
        logger.warning("ingest.no_documents")
        return 0

    # Upsert in batches
    total = 0
    for i in range(0, len(all_docs), batch_size):
        batch = all_docs[i : i + batch_size]
        await store.upsert(batch)
        total += len(batch)
        logger.info("ingest.batch_upserted", batch_num=i // batch_size + 1, count=len(batch))

    logger.info("ingest.complete", total_chunks=total, num_files=len(files))
    return total

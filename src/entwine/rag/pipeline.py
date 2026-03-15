"""Document ingestion pipeline: scan → chunk → embed → upsert."""

from __future__ import annotations

from collections.abc import Callable
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
    progress_callback: Callable[[Path, int], None] | None = None,
) -> int:
    """Ingest all supported files under *root* into the knowledge store.

    Returns the total number of document chunks upserted.
    *progress_callback*, if provided, is called as ``cb(file_path, chunk_count)``
    for each file processed.
    """
    files = scan_directory(root)
    if not files:
        logger.warning("ingest.no_files", root=str(root))
        return 0

    logger.info("ingest.start", root=str(root), num_files=len(files))

    all_docs: list[Document] = []

    for file_idx, path in enumerate(files, 1):
        try:
            text, file_metadata = load_file(path, root=root)
        except (ValueError, OSError, ImportError) as exc:
            logger.warning("ingest.skip_file", path=str(path), error=str(exc))
            if progress_callback is not None:
                progress_callback(path, 0)
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

        logger.info(
            "ingest.file_processed",
            file=str(path.name),
            file_num=file_idx,
            total_files=len(files),
            chunks=len(docs),
        )
        if progress_callback is not None:
            progress_callback(path, len(docs))

    if not all_docs:
        logger.warning("ingest.no_documents")
        return 0

    # Deduplicate: skip chunks already present in the store
    all_ids = [doc.id for doc in all_docs]
    existing_ids = await store.get_existing_ids(all_ids)
    if existing_ids:
        before = len(all_docs)
        all_docs = [doc for doc in all_docs if doc.id not in existing_ids]
        logger.info("ingest.dedup", skipped=before - len(all_docs), remaining=len(all_docs))

    if not all_docs:
        logger.info("ingest.all_duplicates", total_skipped=len(existing_ids))
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

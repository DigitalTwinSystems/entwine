"""Unit tests for RAG ingestion: chunking, loaders, pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from entwine.rag.chunking import chunk_text, chunks_to_documents, content_hash
from entwine.rag.loaders import (
    _extract_yaml_frontmatter,
    load_file,
    parse_accessible_roles,
    scan_directory,
)
from entwine.rag.models import Document
from entwine.rag.pipeline import ingest_directory

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_short_text_single_chunk(self) -> None:
        result = chunk_text("Hello world", chunk_size=500)
        assert result == ["Hello world"]

    def test_empty_text(self) -> None:
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_splits_long_text(self) -> None:
        text = "word " * 200  # ~1000 chars
        chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
        assert len(chunks) > 1
        # All chunks should have content
        for c in chunks:
            assert len(c) > 0

    def test_prefers_paragraph_boundaries(self) -> None:
        text = "First paragraph content here.\n\nSecond paragraph content here."
        chunks = chunk_text(text, chunk_size=40, chunk_overlap=10)
        assert len(chunks) >= 2

    def test_prefers_sentence_boundaries(self) -> None:
        text = "First sentence here. Second sentence here. Third one."
        chunks = chunk_text(text, chunk_size=30, chunk_overlap=5)
        assert len(chunks) >= 2

    def test_overlap_produces_redundancy(self) -> None:
        text = "a" * 300
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=30)
        # With overlap, we should get more chunks than without
        no_overlap = chunk_text(text, chunk_size=100, chunk_overlap=0)
        assert len(chunks) >= len(no_overlap)


class TestContentHash:
    def test_deterministic(self) -> None:
        assert content_hash("hello") == content_hash("hello")

    def test_different_text_different_hash(self) -> None:
        assert content_hash("hello") != content_hash("world")


class TestChunksToDocuments:
    def test_creates_documents_with_metadata(self) -> None:
        chunks = ["chunk one", "chunk two"]
        docs = chunks_to_documents(
            chunks,
            metadata={"department": "eng", "accessible_roles": ["dev"]},
            source_id="test-doc",
        )
        assert len(docs) == 2
        assert docs[0].metadata["department"] == "eng"
        assert docs[0].metadata["chunk_index"] == 0
        assert docs[1].metadata["chunk_index"] == 1
        assert "test-doc" in docs[0].id


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


class TestExtractFrontmatter:
    def test_extracts_metadata(self) -> None:
        text = "---\ndepartment: engineering\nsensitivity: internal\n---\n\n# Title\n\nBody"
        metadata, body = _extract_yaml_frontmatter(text)
        assert metadata["department"] == "engineering"
        assert metadata["sensitivity"] == "internal"
        assert body.startswith("# Title")

    def test_no_frontmatter(self) -> None:
        text = "# Just a title\n\nBody text."
        metadata, body = _extract_yaml_frontmatter(text)
        assert metadata == {}
        assert body == text


class TestLoadFile:
    def test_loads_markdown(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\ndepartment: eng\n---\n\n# Hello\n\nWorld", encoding="utf-8")
        text, meta = load_file(md)
        assert "Hello" in text
        assert meta["department"] == "eng"
        assert meta["source_file"] == "test.md"

    def test_loads_txt(self, tmp_path: Path) -> None:
        txt = tmp_path / "test.txt"
        txt.write_text("Plain text content", encoding="utf-8")
        text, _meta = load_file(txt)
        assert text == "Plain text content"

    def test_rejects_unsupported(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_text("fake", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            load_file(pdf)


class TestScanDirectory:
    def test_finds_supported_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "c.pdf").write_text("c", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "d.md").write_text("d", encoding="utf-8")

        files = scan_directory(tmp_path)
        names = [f.name for f in files]
        assert "a.md" in names
        assert "b.txt" in names
        assert "d.md" in names
        assert "c.pdf" not in names


class TestParseAccessibleRoles:
    def test_comma_separated(self) -> None:
        assert parse_accessible_roles("ceo, cto, developer") == ["ceo", "cto", "developer"]

    def test_bracketed(self) -> None:
        assert parse_accessible_roles("[ceo, cto]") == ["ceo", "cto"]

    def test_empty(self) -> None:
        assert parse_accessible_roles("") == []

    def test_single_role(self) -> None:
        assert parse_accessible_roles("company-wide") == ["company-wide"]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestIngestDirectory:
    @pytest.mark.asyncio
    async def test_ingests_files(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text(
            "---\ndepartment: eng\naccessible_roles: dev, cto\n---\n\n# Doc\n\nContent here.",
            encoding="utf-8",
        )

        store = MagicMock()
        store.upsert = AsyncMock()

        total = await ingest_directory(tmp_path, store, chunk_size=500)

        assert total >= 1
        store.upsert.assert_awaited()
        # Check metadata on upserted docs
        call_args = store.upsert.call_args
        docs: list[Document] = call_args[0][0]
        assert docs[0].metadata["accessible_roles"] == ["dev", "cto"]

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.upsert = AsyncMock()

        total = await ingest_directory(tmp_path, store)
        assert total == 0
        store.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_roles_applied(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("Some plain text content.", encoding="utf-8")

        store = MagicMock()
        store.upsert = AsyncMock()

        await ingest_directory(tmp_path, store, default_roles=["everyone"])

        docs = store.upsert.call_args[0][0]
        assert docs[0].metadata["accessible_roles"] == ["everyone"]

    @pytest.mark.asyncio
    async def test_sample_knowledge_base(self) -> None:
        """Verify the sample knowledge base can be processed."""
        kb_path = Path(__file__).parent.parent.parent / "examples" / "knowledge"
        if not kb_path.exists():
            pytest.skip("examples/knowledge not present")

        store = MagicMock()
        store.upsert = AsyncMock()

        total = await ingest_directory(kb_path, store, chunk_size=500)

        # 7 files should produce multiple chunks
        assert total >= 7
        assert store.upsert.await_count >= 1

"""Unit tests for RAG ingestion: chunking, loaders, pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from entwine.rag.chunking import chunk_text, chunks_to_documents, content_hash
from entwine.rag.loaders import (
    _extract_yaml_frontmatter,
    _load_docx,
    _load_pdf,
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

    def test_creates_deterministic_ids_without_source_id(self) -> None:
        chunks = ["chunk one", "chunk two"]
        docs = chunks_to_documents(chunks, metadata={})
        assert len(docs) == 2
        assert docs[0].id.startswith("chunk-0:")
        assert docs[1].id.startswith("chunk-1:")
        # IDs should be deterministic
        docs2 = chunks_to_documents(chunks, metadata={})
        assert docs[0].id == docs2[0].id

    def test_includes_content_hash_in_metadata(self) -> None:
        chunks = ["hello world"]
        docs = chunks_to_documents(chunks, metadata={}, source_id="test")
        assert "content_hash" in docs[0].metadata
        assert docs[0].metadata["content_hash"] == content_hash("hello world")


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

    def test_no_closing_delimiter(self) -> None:
        text = "---\ndepartment: eng\nNo closing delimiter"
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
        assert meta["source_path"] == "test.md"

    def test_loads_markdown_with_root(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        md = sub / "test.md"
        md.write_text("---\ndepartment: eng\n---\n\n# Hello", encoding="utf-8")
        _text, meta = load_file(md, root=tmp_path)
        assert meta["source_path"] == "sub/test.md"

    def test_loads_txt(self, tmp_path: Path) -> None:
        txt = tmp_path / "test.txt"
        txt.write_text("Plain text content", encoding="utf-8")
        text, meta = load_file(txt)
        assert text == "Plain text content"
        assert meta["sensitivity"] == "internal"  # default

    def test_loads_txt_with_frontmatter(self, tmp_path: Path) -> None:
        txt = tmp_path / "test.txt"
        txt.write_text(
            "---\ndepartment: sales\nsensitivity: confidential\n---\n\nSales content",
            encoding="utf-8",
        )
        text, meta = load_file(txt)
        assert "Sales content" in text
        assert meta["department"] == "sales"
        assert meta["sensitivity"] == "confidential"

    def test_rejects_unsupported(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("fake", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported"):
            load_file(csv_file)

    def test_loads_pdf(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        with patch("entwine.rag.loaders._load_pdf", return_value="PDF content") as mock_pdf:
            text, meta = load_file(pdf)
        mock_pdf.assert_called_once_with(pdf)
        assert text == "PDF content"
        assert meta["source_path"] == "test.pdf"
        assert meta["sensitivity"] == "internal"

    def test_loads_docx(self, tmp_path: Path) -> None:
        docx = tmp_path / "test.docx"
        docx.write_bytes(b"fake")
        with patch("entwine.rag.loaders._load_docx", return_value="DOCX content") as mock_docx:
            text, meta = load_file(docx)
        mock_docx.assert_called_once_with(docx)
        assert text == "DOCX content"
        assert meta["source_path"] == "test.docx"

    def test_sensitivity_default(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("# No frontmatter", encoding="utf-8")
        _, meta = load_file(md)
        assert meta["sensitivity"] == "internal"

    def test_sensitivity_from_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\nsensitivity: confidential\n---\n\nContent", encoding="utf-8")
        _, meta = load_file(md)
        assert meta["sensitivity"] == "confidential"


class TestLoadPdf:
    def test_import_error_when_pypdf_missing(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"fake")
        with (
            patch.dict("sys.modules", {"pypdf": None}),
            pytest.raises(ImportError, match="pypdf is required"),
        ):
            _load_pdf(pdf)


class TestLoadDocx:
    def test_import_error_when_docx_missing(self, tmp_path: Path) -> None:
        docx = tmp_path / "test.docx"
        docx.write_bytes(b"fake")
        with (
            patch.dict("sys.modules", {"docx": None}),
            pytest.raises(ImportError, match="python-docx is required"),
        ):
            _load_docx(docx)


class TestScanDirectory:
    def test_finds_supported_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "c.pdf").write_bytes(b"c")
        (tmp_path / "d.docx").write_bytes(b"d")
        (tmp_path / "e.csv").write_text("e", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "f.md").write_text("f", encoding="utf-8")

        files = scan_directory(tmp_path)
        names = [f.name for f in files]
        assert "a.md" in names
        assert "b.txt" in names
        assert "c.pdf" in names
        assert "d.docx" in names
        assert "f.md" in names
        assert "e.csv" not in names


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


def _mock_store() -> MagicMock:
    """Create a mock KnowledgeStore with async methods."""
    store = MagicMock()
    store.upsert = AsyncMock()
    store.get_existing_ids = AsyncMock(return_value=set())
    return store


class TestIngestDirectory:
    async def test_ingests_files(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text(
            "---\ndepartment: eng\naccessible_roles: dev, cto\n---\n\n# Doc\n\nContent here.",
            encoding="utf-8",
        )

        store = _mock_store()

        total = await ingest_directory(tmp_path, store, chunk_size=500)

        assert total >= 1
        store.upsert.assert_awaited()
        # Check metadata on upserted docs
        call_args = store.upsert.call_args
        docs: list[Document] = call_args[0][0]
        assert docs[0].metadata["accessible_roles"] == ["dev", "cto"]
        assert docs[0].metadata["source_path"] == "doc.md"
        assert "content_hash" in docs[0].metadata

    async def test_empty_directory(self, tmp_path: Path) -> None:
        store = _mock_store()

        total = await ingest_directory(tmp_path, store)
        assert total == 0
        store.upsert.assert_not_awaited()

    async def test_default_roles_applied(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("Some plain text content.", encoding="utf-8")

        store = _mock_store()

        await ingest_directory(tmp_path, store, default_roles=["everyone"])

        docs = store.upsert.call_args[0][0]
        assert docs[0].metadata["accessible_roles"] == ["everyone"]

    async def test_sample_knowledge_base(self) -> None:
        """Verify the sample knowledge base can be processed."""
        kb_path = Path(__file__).parent.parent.parent / "examples" / "knowledge"
        if not kb_path.exists():
            pytest.skip("examples/knowledge not present")

        store = _mock_store()

        total = await ingest_directory(kb_path, store, chunk_size=500)

        # 7 files should produce multiple chunks
        assert total >= 7
        assert store.upsert.await_count >= 1

    async def test_progress_callback(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# A\n\nContent A", encoding="utf-8")
        (tmp_path / "b.txt").write_text("Content B", encoding="utf-8")

        store = _mock_store()

        progress_calls: list[tuple[Path, int]] = []

        def on_progress(path: Path, chunks: int) -> None:
            progress_calls.append((path, chunks))

        await ingest_directory(tmp_path, store, progress_callback=on_progress)

        assert len(progress_calls) == 2
        for _path, chunks in progress_calls:
            assert chunks >= 1

    async def test_idempotent_skips_existing(self, tmp_path: Path) -> None:
        """Second ingest with same content should upsert zero chunks."""
        (tmp_path / "doc.md").write_text("# Hello\n\nWorld", encoding="utf-8")

        store = MagicMock()
        store.upsert = AsyncMock()
        store.get_existing_ids = AsyncMock(return_value=set())

        # First ingest: no existing IDs → all upserted
        total1 = await ingest_directory(tmp_path, store)
        assert total1 >= 1
        first_docs = store.upsert.call_args[0][0]
        first_ids = {doc.id for doc in first_docs}

        # Second ingest: all IDs exist → none upserted
        store.upsert.reset_mock()
        store.get_existing_ids = AsyncMock(return_value=first_ids)

        total2 = await ingest_directory(tmp_path, store)
        assert total2 == 0
        store.upsert.assert_not_awaited()

    async def test_metadata_includes_sensitivity(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text(
            "---\nsensitivity: confidential\n---\n\nSecret stuff",
            encoding="utf-8",
        )
        store = _mock_store()

        await ingest_directory(tmp_path, store)

        docs = store.upsert.call_args[0][0]
        assert docs[0].metadata["sensitivity"] == "confidential"

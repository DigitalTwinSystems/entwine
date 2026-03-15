"""Document loaders: scan directories and read files into raw text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Supported extensions
_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".rst"})
_PDF_EXTENSIONS = frozenset({".pdf"})
_DOCX_EXTENSIONS = frozenset({".docx"})
_ALL_EXTENSIONS = _TEXT_EXTENSIONS | _PDF_EXTENSIONS | _DOCX_EXTENSIONS


def _extract_yaml_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML-style frontmatter (key: value lines) from markdown.

    Returns (metadata_dict, remaining_text).
    """
    metadata: dict[str, str] = {}
    if not text.startswith("---"):
        return metadata, text

    end = text.find("---", 3)
    if end == -1:
        return metadata, text

    frontmatter = text[3:end].strip()
    body = text[end + 3 :].strip()

    for line in frontmatter.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip().strip('"').strip("'")

    return metadata, body


def _load_pdf(path: Path) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        msg = "pypdf is required for PDF support. Install with: uv add pypdf"
        raise ImportError(msg) from exc

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _load_docx(path: Path) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        msg = "python-docx is required for DOCX support. Install with: uv add python-docx"
        raise ImportError(msg) from exc

    doc = DocxDocument(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs).strip()


def load_file(path: Path, *, root: Path | None = None) -> tuple[str, dict[str, Any]]:
    """Read a single file and return (text_content, metadata).

    Supports .md, .txt, .rst, .pdf, .docx. Extracts YAML frontmatter from .md and .txt files.
    If *root* is provided, ``source_path`` is stored as the relative path from root.
    """
    if path.suffix not in _ALL_EXTENSIONS:
        msg = f"Unsupported file type: {path.suffix}"
        raise ValueError(msg)

    # Compute source_path relative to root or fallback to filename
    source_path = str(path.relative_to(root)) if root else str(path.name)
    metadata: dict[str, Any] = {"source_path": source_path}

    if path.suffix in _PDF_EXTENSIONS:
        text = _load_pdf(path)
    elif path.suffix in _DOCX_EXTENSIONS:
        text = _load_docx(path)
    else:
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".md", ".txt"}:
            fm, text = _extract_yaml_frontmatter(text)
            metadata.update(fm)

    # Ensure sensitivity has a default
    if "sensitivity" not in metadata:
        metadata["sensitivity"] = "internal"

    return text, metadata


def scan_directory(
    root: Path,
    extensions: frozenset[str] | None = None,
) -> list[Path]:
    """Recursively find all supported files under *root*."""
    exts = extensions or _ALL_EXTENSIONS
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in exts:
            files.append(path)
    return files


def parse_accessible_roles(raw: str) -> list[str]:
    """Parse a comma-separated or YAML-list string of role names."""
    if not raw:
        return []
    # Handle both "ceo, cto, developer" and "[ceo, cto]"
    cleaned = re.sub(r"[\[\]]", "", raw)
    return [r.strip() for r in cleaned.split(",") if r.strip()]

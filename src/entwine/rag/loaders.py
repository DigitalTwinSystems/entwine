"""Document loaders: scan directories and read files into raw text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Supported extensions
_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".rst"})


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


def load_file(path: Path) -> tuple[str, dict[str, Any]]:
    """Read a single file and return (text_content, metadata).

    Supports .md, .txt, .rst. Extracts YAML frontmatter from .md files.
    """
    if path.suffix not in _TEXT_EXTENSIONS:
        msg = f"Unsupported file type: {path.suffix}"
        raise ValueError(msg)

    text = path.read_text(encoding="utf-8")
    metadata: dict[str, Any] = {"source_file": str(path.name)}

    if path.suffix == ".md":
        fm, text = _extract_yaml_frontmatter(text)
        metadata.update(fm)

    return text, metadata


def scan_directory(
    root: Path,
    extensions: frozenset[str] | None = None,
) -> list[Path]:
    """Recursively find all supported files under *root*."""
    exts = extensions or _TEXT_EXTENSIONS
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

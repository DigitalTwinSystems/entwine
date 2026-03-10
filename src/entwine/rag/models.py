"""RAG data models: Document and SearchResult."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    """An enterprise knowledge document stored in the vector store."""

    id: str = Field(..., description="Unique document identifier.")
    content: str = Field(..., description="Text content of the document.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Document metadata including department, sensitivity, "
            "accessible_roles, source, and updated_at."
        ),
    )


class SearchResult(BaseModel):
    """A single result returned from a vector store search."""

    document: Document = Field(..., description="The matched document.")
    score: float = Field(..., description="Relevance score from the vector store.")

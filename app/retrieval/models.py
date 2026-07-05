"""Retrieval result models."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievedDocument:
    """One approved source document returned by retrieval."""

    id: str
    title: str
    content: str
    source: str
    excerpt: str = ""
    page: str = ""
    document_version: str = ""
    country: str = ""
    language: str = ""
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_source(self) -> dict[str, Any]:
        """Return the API-compatible source shape."""
        return {
            "title": self.title,
            "uri": self.source,
            "excerpt": self.excerpt,
            "page": self.page,
            "documentVersion": self.document_version,
            "country": self.country,
            "language": self.language,
            "score": self.score,
        }


RetrievalDocument = RetrievedDocument


@dataclass(frozen=True)
class RetrievalResult:
    """Normalized retrieval output."""

    documents: list[RetrievedDocument]
    citations: list[dict[str, Any]]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sources(self) -> list[dict[str, Any]]:
        """Return API-compatible source dictionaries."""
        return [document.to_source() for document in self.documents]

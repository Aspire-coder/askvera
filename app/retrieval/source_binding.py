"""Pure, opt-in source binding for selector experiments; not an access check."""

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence


@dataclass(frozen=True)
class EvidenceSource:
    document_id: str
    generation_id: str
    section_id: str
    country: str
    content: str

    def __post_init__(self):
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.document_id, self.generation_id, self.section_id, self.country, self.content,
        )):
            raise ValueError("A source needs document, generation, section, country and content")

    @property
    def binding_id(self) -> str:
        # Full content and provenance bind the exact version, independent of list order.
        payload = [self.document_id, self.generation_id, self.section_id, self.country, self.content]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_support(support: object, eligible_sources: Sequence[EvidenceSource]) -> tuple[str, ...]:
    """Validate quotes against already authorized sources. Never relocate a bad quote.

    This proves text membership only, not that the quote answers the question.
    Whitespace wrapping may differ; numbers, punctuation and wording may not.
    """
    sources = {source.binding_id: source for source in eligible_sources}
    if len(sources) != len(eligible_sources):
        raise ValueError("Duplicate eligible source binding")
    if not isinstance(support, list) or not 1 <= len(support) <= 5:
        raise ValueError("Expected one to five support items")
    selected = []
    for item in support:
        if not isinstance(item, dict) or set(item) != {"source_id", "quote"}:
            raise ValueError("Expected source_id and quote only")
        source_id, quote = item["source_id"], item["quote"]
        if not isinstance(source_id, str) or source_id not in sources:
            raise ValueError("Unknown or stale source binding")
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("Empty or invalid quote")
        if " ".join(quote.split()) not in " ".join(sources[source_id].content.split()):
            raise ValueError("Quote does not belong to the cited source")
        if source_id not in selected:
            selected.append(source_id)
    return tuple(selected)

"""Tests for generic OpenSearch section retrieval behavior."""

from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _language_key,
    _retrieval_scope_filter,
)
from config import settings


def _hit(identifier: str, title: str, score: float) -> dict[str, object]:
    return {
        "_id": identifier,
        "_score": score,
        "_source": {
            "id": identifier,
            "section_id": "7.03",
            "section_title": title,
            "content": f"{title} policy text.",
            "search_text": f"{title} policy text.",
            "country": "CA",
            "language": "en",
            "status": "active",
        },
    }


def test_language_key_normalizes_regional_language_tags() -> None:
    assert _language_key("fr-CA") == "fr"
    assert _language_key("PT-br") == "pt"


def test_retrieval_scope_allows_requested_locale_and_explicit_global_sources(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", False)
    scope_filter = _retrieval_scope_filter("CA", "fr")
    alternatives = scope_filter["bool"]["should"]

    assert alternatives[0]["bool"]["filter"] == [
        {"term": {"country": "CA"}},
        {"terms": {"language": ["fr"]}},
    ]
    assert alternatives[1] == {"term": {"access_scope": "global"}}
    assert scope_filter["bool"]["minimum_should_match"] == 1



def test_merge_hits_keeps_strongest_text_hit_for_same_section() -> None:
    """A glossary query must not overwrite a stronger original search result."""
    rows = OpenSearchSectionProvider()._merge_hits(
        [
            _hit("section-1", "Original governing title", 8.0),
            _hit("section-1", "Weaker glossary title", 2.0),
        ],
        [],
        "Original governing title",
    )

    assert len(rows) == 1
    assert rows[0][0]["section_title"] == "Original governing title"

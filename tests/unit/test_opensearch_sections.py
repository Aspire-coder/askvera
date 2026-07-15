"""Tests for generic OpenSearch section retrieval behavior."""

from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _language_key,
    _selector_candidates,
    _scope_filter,
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


def test_retrieval_scopes_keep_locale_and_global_documents_isolated(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", False)
    assert _scope_filter("CA", "fr", "locale")["bool"]["filter"] == [
        {"terms": {"country": ["CA"]}},
        {"terms": {"language": ["fr"]}},
    ]
    assert _scope_filter("GB", "en", "locale")["bool"]["filter"][0] == {
        "terms": {"country": ["GB", "UK"]}
    }
    assert _scope_filter("CA", "fr", "global") == {
        "term": {"access_scope": "global"}
    }



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


def test_selector_candidates_reserve_space_for_global_documents() -> None:
    locale_rows = [
        ({"id": f"locale-{index}", "access_scope": "country"}, 10.0 - index)
        for index in range(12)
    ]
    global_rows = [
        ({"id": f"global-{index}", "access_scope": "global"}, 1.0 - index / 10)
        for index in range(5)
    ]

    candidates = _selector_candidates([*locale_rows, *global_rows], 9)

    assert len(candidates) == 9
    assert sum(row["access_scope"] == "global" for row, _score in candidates) == 3


def test_global_search_query_skips_translation_for_matching_language(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE", "en")

    query = OpenSearchSectionProvider()._global_search_query(
        "Where is the Mexico office?",
        "en-US",
        "test-correlation",
    )

    assert query == "Where is the Mexico office?"

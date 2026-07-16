"""Tests for generic OpenSearch section retrieval behavior."""

from app.retrieval import opensearch_sections
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _directory_record_country_score,
    _directory_text_query,
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


def test_search_queries_use_runtime_planner_instead_of_country_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        opensearch_sections,
        "_planned_retrieval_queries",
        lambda message, country, language, correlation_id: [message, "semantic policy query"],
    )

    queries = OpenSearchSectionProvider()._build_search_queries(
        "Een korte beleidsvraag",
        "NL",
        "nl",
        "cid",
    )

    assert queries == ["Een korte beleidsvraag", "semantic policy query"]


def test_directory_query_filters_to_active_global_directory_records() -> None:
    filters = _directory_text_query("Where is the India office?")["query"]["bool"]["filter"]

    assert {"term": {"access_scope": "global"}} in filters
    assert {"term": {"status": "active"}} in filters
    assert {"term": {"document_type": "office_directory"}} in filters


def test_directory_country_score_derives_acronyms_from_record_metadata() -> None:
    row = {
        "document_type": "office_directory",
        "metadata": {"record_country": "United Kingdom"},
    }

    assert _directory_record_country_score("Give me the UK office address", row) == 2.2
    assert _directory_record_country_score("Give me the United Kingdom office address", row) == 2.4

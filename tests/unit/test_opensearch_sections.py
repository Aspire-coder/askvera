"""Tests for generic OpenSearch section retrieval behavior."""

from app.retrieval import opensearch_sections
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _directory_record_country_score,
    _directory_text_query,
    _generation_filters,
    is_approved_source,
    _language_key,
    _outline_text_query,
    _selector_candidates,
    _scope_filter,
)
from app.retrieval.providers import RetrievalQueryPlan
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


class SourceClient:
    def __init__(self, sources: list[dict[str, str]] | None = None, error: Exception | None = None) -> None:
        self.sources = sources or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"hits": {"hits": [{"_source": source} for source in self.sources]}}


def test_source_authorization_accepts_active_exact_locale_source(monkeypatch) -> None:
    uri = "s3://approved/Canada_en/policy.pdf"
    client = SourceClient(
        [{"source_uri": uri, "country": "CA", "language": "en", "access_scope": "country", "status": "active"}]
    )
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)

    assert is_approved_source(uri, "CA", "en", "cid") is True
    filters = client.calls[0]["body"]["query"]["bool"]["filter"]
    assert {"term": {"source_uri": uri}} in filters
    assert {"term": {"status": "active"}} in filters


def test_source_authorization_rejects_wrong_locale(monkeypatch) -> None:
    uri = "s3://approved/UnitedStates_en/policy.pdf"
    client = SourceClient(
        [{"source_uri": uri, "country": "US", "language": "en", "access_scope": "country", "status": "active"}]
    )
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)

    assert is_approved_source(uri, "CA", "en", "cid") is False


def test_source_authorization_accepts_global_source_for_any_locale(monkeypatch) -> None:
    uri = "s3://approved/Global_en/directory.pdf"
    client = SourceClient(
        [{"source_uri": uri, "country": "GLOBAL", "language": "en", "access_scope": "global", "status": "active"}]
    )
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)

    assert is_approved_source(uri, "DE", "de", "cid") is True


def test_source_authorization_rejects_inactive_source(monkeypatch) -> None:
    uri = "s3://approved/Canada_en/policy.pdf"
    client = SourceClient(
        [{"source_uri": uri, "country": "CA", "language": "en", "access_scope": "country", "status": "staging"}]
    )
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)

    assert is_approved_source(uri, "CA", "en", "cid") is False


def test_source_authorization_fails_closed_when_search_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(opensearch_sections, "_client", lambda: SourceClient(error=RuntimeError("unavailable")))

    assert is_approved_source("s3://approved/policy.pdf", "CA", "en", "cid") is False


def test_provider_can_target_an_isolated_vnext_index(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "uat-index")

    assert OpenSearchSectionProvider().index_name == "uat-index"
    assert OpenSearchSectionProvider(index_name="vnext-index").index_name == "vnext-index"


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
        "bool": {
            "filter": [
                {"term": {"access_scope": "global"}},
                {"terms": {"language": ["fr"]}},
            ]
        }
    }


def test_generation_filter_does_not_change_queries_while_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        False,
    )

    assert _generation_filters("CA", "en", "locale") == []


def test_generation_filter_uses_only_published_locale_generations(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        True,
    )
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", False)
    monkeypatch.setattr(
        opensearch_sections,
        "active_generation_ids",
        lambda **kwargs: (
            {"generation-ca-en"}
            if kwargs == {
                "countries": {"CA"},
                "languages": {"en"},
                "access_scope": "country",
                "document_type": "policy",
            }
            else set()
        ),
    )

    assert _generation_filters(
        "CA",
        "en",
        "locale",
        document_type="policy",
    ) == [
        {
            "bool": {
                "should": [
                    {"terms": {"ingestion_id": ["generation-ca-en"]}},
                    {"terms": {"ingestion_id.keyword": ["generation-ca-en"]}},
                ],
                "minimum_should_match": 1,
            }
        }
    ]


def test_generation_filter_fails_closed_without_a_published_generation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        True,
    )
    monkeypatch.setattr(
        opensearch_sections,
        "active_generation_ids",
        lambda **_kwargs: set(),
    )

    assert _generation_filters("CA", "en", "locale") == [
        {
            "bool": {
                "should": [
                    {"term": {"ingestion_id": "__no_active_generation__"}},
                    {
                        "term": {
                            "ingestion_id.keyword": "__no_active_generation__"
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        }
    ]


def test_global_generation_filter_is_not_limited_by_conversation_language(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        opensearch_sections.settings,
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED",
        True,
    )
    captured = {}

    def fake_active_generation_ids(**kwargs):
        captured.update(kwargs)
        return {"directory-en"}

    monkeypatch.setattr(
        opensearch_sections,
        "active_generation_ids",
        fake_active_generation_ids,
    )

    assert _generation_filters(
        "",
        "fr",
        "global",
        document_type="office_directory",
    ) == [
        {
            "bool": {
                "should": [
                    {"terms": {"ingestion_id": ["directory-en"]}},
                    {"terms": {"ingestion_id.keyword": ["directory-en"]}},
                ],
                "minimum_should_match": 1,
            }
        }
    ]
    assert captured["languages"] == set()


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


def test_search_plan_carries_runtime_document_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        opensearch_sections,
        "_planned_retrieval_plan",
        lambda message, country, language, correlation_id: RetrievalQueryPlan(
            [message, "policy definition"],
            include_global_documents=False,
            prefer_outline=True,
        ),
    )

    plan = OpenSearchSectionProvider()._build_search_plan(
        "Hva betyr CC?",
        "NO",
        "no",
        "cid",
    )

    assert plan.queries == ["Hva betyr CC?", "policy definition"]
    assert plan.include_global_documents is False
    assert plan.prefer_outline is True


def test_high_confidence_conversation_route_skips_opensearch(monkeypatch) -> None:
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(
        provider,
        "_build_search_plan",
        lambda *_: RetrievalQueryPlan(
            ["I am having fever."],
            conversation_intent="medical_claim",
            intent_confidence=0.98,
        ),
    )
    monkeypatch.setattr(
        opensearch_sections,
        "_client",
        lambda: (_ for _ in ()).throw(AssertionError("OpenSearch must not be called")),
    )

    result = provider.retrieve("I am having fever.", "US", "en", "new_prospect", "cid")

    assert result.documents == []
    assert result.metadata["conversation_intent"] == "medical_claim"


def test_outline_chunks_are_prioritized_only_for_structure_questions() -> None:
    rows = OpenSearchSectionProvider()._merge_hits(
        [
            {
                **_hit("body", "Repeated body mention", 9.0),
                "_source": {
                    **_hit("body", "Repeated body mention", 9.0)["_source"],
                    "chunk_type": "section",
                },
            },
            {
                **_hit("outline", "Policy document outline", 3.0),
                "_source": {
                    **_hit("outline", "Policy document outline", 3.0)["_source"],
                    "chunk_type": "document_outline",
                    "content": "22 Code of Conduct",
                },
            },
        ],
        [],
        "Which section contains the Code of Conduct?",
        prefer_outline=True,
    )

    assert rows[0][0]["id"] == "outline"


def test_directory_query_filters_to_active_global_directory_records() -> None:
    filters = _directory_text_query("Where is the India office?")["query"]["bool"]["filter"]

    assert {
        "bool": {
            "filter": [
                {"term": {"access_scope": "global"}},
                {"term": {"language": "en"}},
            ]
        }
    } in filters
    assert {"term": {"status": "active"}} in filters
    assert {"term": {"document_type": "office_directory"}} in filters


def test_outline_query_is_locale_isolated_and_outline_only() -> None:
    filters = _outline_text_query("Which section contains returns?", "CA", "en")["query"]["bool"]["filter"]

    assert _scope_filter("CA", "en", "locale") in filters
    assert {"term": {"status": "active"}} in filters
    assert {"term": {"chunk_type": "document_outline"}} in filters


def test_directory_country_score_derives_acronyms_from_record_metadata() -> None:
    row = {
        "document_type": "office_directory",
        "metadata": {"record_country": "United Kingdom"},
    }

    assert _directory_record_country_score("Give me the UK office address", row) == 2.2
    assert _directory_record_country_score("Give me the United Kingdom office address", row) == 2.4

"""Tests for generic OpenSearch section retrieval behavior."""

from app.evidence import approve_evidence
from app.retrieval import opensearch_sections
from app.retrieval.models import RetrievalResult
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _directory_target_country_names,
    _directory_record_country_score,
    _directory_text_query,
    _exact_section_query,
    _generation_filters,
    is_approved_source,
    _language_key,
    _outline_text_query,
    _parse_selector_decision,
    _selector_candidates,
    _scope_filter,
    _section_reference,
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


def test_explicit_section_reference_is_normalized_without_guessing() -> None:
    assert _section_reference("Please explain Section 4-01a.") == "4.01a"
    assert _section_reference("What does §4.01a say?") == "4.01a"
    assert _section_reference("What does the policy say about managers?") is None


def test_exact_section_query_keeps_locale_and_active_filters() -> None:
    filters = _exact_section_query("4.01a", "CA", "fr")["query"]["bool"]["filter"]

    assert _scope_filter("CA", "fr", "locale") in filters
    assert {"term": {"status": "active"}} in filters
    assert {
        "bool": {
            "should": [
                {"term": {"section_id": "4.01a"}},
                {"term": {"section_id.keyword": "4.01a"}},
            ],
            "minimum_should_match": 1,
        }
    } in filters


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


def test_sponsoring_directory_keeps_source_text_instead_of_office_fields() -> None:
    document = OpenSearchSectionProvider()._document_from_row(
        {
            "id": "sponsoring-001",
            "section_id": "sponsoring-001",
            "section_title": "Forever Canada",
            "content": "Welcome to Forever Canada!\nSponsor: example.com",
            "country": "GLOBAL",
            "language": "en",
            "document_type": "office_directory",
            "metadata": {
                "directory_kind": "international_sponsoring",
                "record_country": "Canada",
            },
        },
        1.0,
    )

    assert document.metadata["directory_kind"] == "international_sponsoring"
    assert document.metadata["access_scope"] == "country"
    assert "directory_fields" not in document.metadata


def test_global_sponsoring_document_preserves_scope_for_evidence_gate() -> None:
    document = OpenSearchSectionProvider()._document_from_row(
        {
            "id": "sponsoring-belgium",
            "section_id": "sponsoring-belgium",
            "section_title": "Forever Belgium",
            "content": "Minimum order size FBO: 50,00 in products excluding VAT.",
            "country": "GLOBAL",
            "language": "en",
            "access_scope": "global",
            "document_type": "international_sponsoring_directory",
            "metadata": {
                "directory_kind": "international_sponsoring",
                "record_country": "Belgium",
            },
        },
        1.0,
    )

    assert document.metadata["access_scope"] == "global"
    assert document.metadata["document_type"] == "international_sponsoring_directory"
    result = RetrievalResult(
        documents=[document],
        citations=[document.to_source()],
        confidence=0.9,
    )
    assert approve_evidence(
        "What is the minimum order size for Belgium?",
        result,
        "US",
        "en",
    ).approved


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


def test_hardened_ranking_prefers_governing_manager_requirement(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    direct = _hit("manager-requirement", "Manager is achieved by generating Case Credits", 2.0)
    direct["_source"]["section_id"] = "4.01-d"
    direct["_source"]["content"] = (
        "Manager is achieved by generating 120 Open Group Case Credits within 1-2 consecutive Months."
    )
    direct["_source"]["search_text"] = direct["_source"]["content"]
    nearby = _hit("unrecognized-manager", "Unrecognized Manager", 9.0)
    nearby["_source"]["section_id"] = "5.02"
    nearby["_source"]["content"] = "An Unrecognized Manager can re-qualify by meeting separate requirements."
    nearby["_source"]["search_text"] = nearby["_source"]["content"]

    rows = OpenSearchSectionProvider()._merge_hits(
        [nearby, direct],
        [],
        "What does the company policy say about manager qualifications?",
    )

    assert rows[0][0]["id"] == "manager-requirement"


def test_hardened_ranking_prefers_explicit_purchase_channel(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    generic = _hit("general", "General company information", 9.0)
    channel = _hit("online-sales", "Selling Products Online", 2.0)
    channel["_source"]["section_id"] = "17.10-a"
    channel["_source"]["content"] = (
        "An FBO may sell products through a personal Forever web shop or an Approved FBO Website."
    )
    channel["_source"]["search_text"] = channel["_source"]["content"]

    rows = OpenSearchSectionProvider()._merge_hits(
        [generic, channel],
        [],
        "Where can I buy Forever products?",
    )

    assert rows[0][0]["id"] == "online-sales"


def test_hardened_ranking_prefers_direct_return_clause(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    generic = _hit("generic-return", "General customer service", 2.1)
    direct = _hit("return-policy", "Product Return", 2.0)
    direct["_source"]["content"] = (
        "Proper notice, proof of purchase, and timely return of the product are required."
    )
    direct["_source"]["search_text"] = direct["_source"]["content"]

    rows = OpenSearchSectionProvider()._merge_hits(
        [generic, direct],
        [],
        "How do I return a product?",
    )

    assert rows[0][0]["id"] == "return-policy"


def test_hardened_ranking_prefers_specific_buyback_clause_over_general_satisfaction_clause(monkeypatch) -> None:
    """Regression test for the 2026-09-01 live-canary finding: a question about the
    buy-back window for an unopened product must prefer the specific buy-back
    clause, not the general satisfaction-guarantee clause that happens to share
    the word "return"."""
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    satisfaction_guarantee = _hit("satisfaction-guarantee", "Product Satisfaction", 2.1)
    satisfaction_guarantee["_source"]["section_id"] = "21.03"
    satisfaction_guarantee["_source"]["content"] = (
        "Retail/Preferred Customers are guaranteed 100% product satisfaction. Within 30 days..."
    )
    satisfaction_guarantee["_source"]["search_text"] = satisfaction_guarantee["_source"]["content"]
    buyback_clause = _hit("buyback-clause", "Unsold Product Buy-Back", 2.0)
    buyback_clause["_source"]["section_id"] = "21.05"
    buyback_clause["_source"]["content"] = (
        "FLP shall buy back any unsold, salable FLP product, except literature, that has been purchased."
    )
    buyback_clause["_source"]["search_text"] = buyback_clause["_source"]["content"]

    rows = OpenSearchSectionProvider()._merge_hits(
        [satisfaction_guarantee, buyback_clause],
        [],
        "Can I return an unopened product, and within what window?",
    )

    assert rows[0][0]["id"] == "buyback-clause"


def test_hardened_ranking_still_prefers_direct_return_clause_for_generic_questions(monkeypatch) -> None:
    """The generic-return regression fix above must not weaken the original, already-verified case."""
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    generic = _hit("generic-return", "General customer service", 2.1)
    direct = _hit("return-policy", "Product Return", 2.0)
    direct["_source"]["content"] = (
        "Proper notice, proof of purchase, and timely return of the product are required."
    )
    direct["_source"]["search_text"] = direct["_source"]["content"]

    rows = OpenSearchSectionProvider()._merge_hits(
        [generic, direct],
        [],
        "How do I return a product?",
    )

    assert rows[0][0]["id"] == "return-policy"


def test_finalize_eligible_rows_is_unchanged_when_diversity_is_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", False)
    rows = [
        ({"id": "a", "metadata": {"parent_section_id": "5.01"}}, 0.9),
        ({"id": "b", "metadata": {"parent_section_id": "5.01"}}, 0.8),
        ({"id": "c", "metadata": {"parent_section_id": "5.02"}}, 0.1),
    ]
    monkeypatch.setattr(settings, "SECTION_RETRIEVAL_MIN_SCORE", 0.05)

    result = OpenSearchSectionProvider()._finalize_eligible_rows(rows)

    assert [row["id"] for row, _score in result] == ["a", "b", "c"]


def test_finalize_eligible_rows_bounds_repeats_from_the_same_parent_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_MAX_RESULTS_PER_PARENT", 1)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(settings, "SECTION_RETRIEVAL_MIN_SCORE", 0.05)
    rows = [
        ({"id": "a", "metadata": {"parent_section_id": "5.01"}}, 0.9),
        ({"id": "b", "metadata": {"parent_section_id": "5.01"}}, 0.8),
        ({"id": "c", "metadata": {"parent_section_id": "5.02"}}, 0.7),
    ]

    result = OpenSearchSectionProvider()._finalize_eligible_rows(rows)

    assert [row["id"] for row, _score in result] == ["a", "c"]


def test_finalize_eligible_rows_still_applies_the_score_floor_before_diversity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", True)
    monkeypatch.setattr(settings, "RETRIEVAL_MAX_RESULTS_PER_PARENT", 5)
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(settings, "SECTION_RETRIEVAL_MIN_SCORE", 0.5)
    rows = [
        ({"id": "a", "metadata": {"parent_section_id": "5.01"}}, 0.9),
        ({"id": "below-floor", "metadata": {"parent_section_id": "5.02"}}, 0.1),
    ]

    result = OpenSearchSectionProvider()._finalize_eligible_rows(rows)

    assert [row["id"] for row, _score in result] == ["a"]


def test_selector_decision_distinguishes_no_evidence_from_invalid_output() -> None:
    assert _parse_selector_decision(
        '{"relevant_evidence":false,"selected_ranks":[],"reason":"not covered"}'
    ) == ([], False)
    assert _parse_selector_decision("not json") is None


def test_hardened_selector_can_reject_unrelated_candidates(monkeypatch) -> None:
    class Runtime:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"relevant_evidence":false,"selected_ranks":[],'
                                    '"reason":"No candidate contains a current product price."}'
                                )
                            }
                        ]
                    }
                }
            }

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    monkeypatch.setattr(
        opensearch_sections,
        "get_aws_clients",
        lambda: type("Clients", (), {"bedrock_runtime": Runtime()})(),
    )
    rows = [
        (
            {
                "id": "unrelated-policy",
                "document_type": "policy",
                "access_scope": "country",
                "section_id": "20.01",
                "section_title": "Genealogical information",
                "content": "The company protects confidential genealogical information.",
                "metadata": {},
            },
            2.0,
        )
    ]

    selected = OpenSearchSectionProvider()._select_evidence_rows(
        "What is the price of Forever Focus?", rows, "cid"
    )

    assert selected == []


def test_successful_selector_marks_selected_evidence(monkeypatch) -> None:
    """Only a successful selector decision can activate strong-local approval."""
    class Runtime:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [{"text": '{"selected_ranks":[2],"reason":"direct clause"}'}]
                    }
                }
            }

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", False)
    monkeypatch.setattr(
        opensearch_sections,
        "get_aws_clients",
        lambda: type("Clients", (), {"bedrock_runtime": Runtime()})(),
    )
    rows = [
        ({"id": "nearby", "metadata": {}, "content": "Nearby evidence."}, 2.0),
        ({"id": "direct", "metadata": {}, "content": "Direct evidence."}, 1.5),
    ]

    selected = OpenSearchSectionProvider()._select_evidence_rows("Question", rows, "cid")

    assert selected[0][0]["id"] == "direct"
    assert selected[0][0]["evidence_selector_selected"] is True
    assert "evidence_selector_selected" not in selected[1][0]


def test_invalid_selector_output_preserves_original_ranking(monkeypatch) -> None:
    class Runtime:
        def converse(self, **_kwargs):
            return {"output": {"message": {"content": [{"text": "not json"}]}}}

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    monkeypatch.setattr(
        opensearch_sections,
        "get_aws_clients",
        lambda: type("Clients", (), {"bedrock_runtime": Runtime()})(),
    )
    rows = [({"id": "original", "metadata": {}, "content": "Approved evidence."}, 1.0)]

    assert OpenSearchSectionProvider()._select_evidence_rows("Question", rows, "cid") == rows


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
    filters = _directory_text_query("Where is the India office?", {"India"})["query"]["bool"]["filter"]

    assert {
        "bool": {
            "filter": [
                {"term": {"access_scope": "global"}},
                {"term": {"language": "en"}},
            ]
        }
    } in filters
    assert {
        "match_phrase": {
            "metadata.record_country": {"query": "India", "boost": 40}
        }
    } in _directory_text_query("Where is the India office?", {"India"})["query"]["bool"]["should"]
    assert {"term": {"status": "active"}} in filters
    assert {
        "terms": {
            "document_type": [
                "office_directory",
                "international_sponsoring_directory",
            ]
        }
    } in filters


def test_directory_query_hard_filters_explicit_target_country() -> None:
    filters = _directory_text_query(
        "What is the phone number for Uruguay?", {"Uruguay"}
    )["query"]["bool"]["filter"]

    assert any(
        value.get("bool", {}).get("minimum_should_match") == 1
        for value in filters
        if isinstance(value, dict)
    )


def test_directory_target_country_recovers_close_typo() -> None:
    assert _directory_target_country_names(
        "How can I join Mexcio through international sponsoring?", "US"
    ) == {"Mexico"}


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


def test_sponsoring_directory_country_score_uses_record_metadata() -> None:
    row = {
        "document_type": "international_sponsoring_directory",
        "metadata": {"record_country": "Italy"},
    }

    assert _directory_record_country_score("Who is the sponsor for Italy?", row) == 2.4


def test_target_country_score_separates_global_directory_records() -> None:
    cameroon = {
        "document_type": "office_directory",
        "metadata": {"record_country": "Cameroon"},
    }
    nigeria = {
        "document_type": "office_directory",
        "metadata": {"record_country": "Nigeria"},
    }

    assert _directory_record_country_score("What are the business hours?", cameroon, {"Cameroon"}) == 8.0
    assert _directory_record_country_score("What are the business hours?", nigeria, {"Cameroon"}) == -4.0


def test_explicit_unknown_directory_country_beats_selected_market() -> None:
    gambia = {
        "document_type": "office_directory",
        "metadata": {"record_country": "Gambia"},
    }

    assert _directory_record_country_score(
        "What is Gambia's telephone number?", gambia, {"United States"}
    ) == 6.0

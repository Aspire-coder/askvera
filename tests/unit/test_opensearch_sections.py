"""Tests for generic OpenSearch section retrieval behavior."""

import pytest
from opensearchpy.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConflictError,
    ConnectionError,
    ConnectionTimeout,
    NotFoundError,
    OpenSearchException,
    RequestError,
    SSLError,
    TransportError,
)

from app.evidence import approve_evidence
from app.retrieval import opensearch_sections
from app.retrieval.models import RetrievalAvailability, RetrievalResult
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
    _restore_dominant_directory_record,
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


class SearchSequenceClient:
    """Return one queued result or raise one queued provider error per search."""

    def __init__(self, outcomes: list[dict[str, object] | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _search_plan() -> RetrievalQueryPlan:
    return RetrievalQueryPlan(["policy question"])


def _empty_hits() -> dict[str, object]:
    return {"hits": {"hits": []}}


def _partial_response(
    *,
    hits: list[dict[str, object]] | None = None,
    timed_out: bool = False,
    shard_status: int | None = None,
    shard_type: str = "unavailable_shards_exception",
    shard_failures: list[dict[str, object]] | None = None,
    failed_shards: int | None = None,
) -> dict[str, object]:
    response: dict[str, object] = {"hits": {"hits": hits or []}}
    if timed_out:
        response["timed_out"] = True
    if shard_status is not None or shard_failures is not None:
        failures = shard_failures
        if failures is None:
            failures = [_shard_failure(shard_status, shard_type)]
        response["_shards"] = {
            "total": 1,
            "successful": 0,
            "skipped": 0,
            "failed": failed_shards if failed_shards is not None else len(failures),
            "failures": failures,
        }
    return response


def _shard_failure(status: int | None, error_type: str) -> dict[str, object]:
    failure: dict[str, object] = {
        "index": "askvera-sections",
        "shard": 0,
        "reason": {"type": error_type, "reason": "simulated shard failure"},
    }
    if status is not None:
        failure["status"] = status
    return failure


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: ConnectionTimeout(599, "timed out", None),
        lambda: ConnectionError("connection failed", Exception("down"), {}),
        lambda: SSLError("certificate failed", Exception("certificate"), {}),
        lambda: AuthenticationException(401, "authentication failed", {}),
        lambda: AuthorizationException(403, "authorization failed", {}),
        lambda: TransportError(503, "service unavailable", {}),
    ],
)
def test_total_transport_outage_returns_typed_unavailability(monkeypatch, error_factory) -> None:
    """A total timeout or connection loss is not an ordinary empty search."""
    provider = OpenSearchSectionProvider()
    client = SearchSequenceClient([error_factory(), error_factory()])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "outage-cid")

    assert result.documents == []
    assert result.availability is RetrievalAvailability.UNAVAILABLE
    assert result.metadata["failed_search_channels"] == ["text", "vector"]


def test_completed_empty_search_remains_available(monkeypatch) -> None:
    """An empty but completed search remains a legitimate evidence miss."""
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: SearchSequenceClient([_empty_hits(), _empty_hits()]))
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "empty-cid")

    assert result.documents == []
    assert result.availability is RetrievalAvailability.AVAILABLE
    assert "failed_search_channels" not in result.metadata


def test_complete_response_with_no_failed_shards_remains_available(monkeypatch) -> None:
    """A complete shard response is distinct from a partial shard response."""
    provider = OpenSearchSectionProvider()
    complete = {
        "timed_out": False,
        "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {"hits": []},
    }
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: SearchSequenceClient([complete, complete]))
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "complete-shards-cid")

    assert result.availability is RetrievalAvailability.AVAILABLE
    assert "search_channel_failures" not in result.metadata


def test_partial_channel_failure_keeps_healthy_channel_results(monkeypatch) -> None:
    """A failed vector channel does not discard text evidence from the same request."""
    provider = OpenSearchSectionProvider()
    text_hit = _hit("text-evidence", "Manager qualifications", 4.0)
    client = SearchSequenceClient([
        {"hits": {"hits": [text_hit]}},
        ConnectionTimeout(599, "timed out", None),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "partial-cid")

    assert [document.id for document in result.documents] == ["text-evidence"]
    assert result.availability is RetrievalAvailability.DEGRADED
    assert result.metadata["failed_search_channels"] == ["vector"]


def test_timed_out_local_response_keeps_partial_hits_and_records_failure(monkeypatch) -> None:
    """A timed-out local response is partial evidence, never a completed search."""
    provider = OpenSearchSectionProvider()
    text_hit = _hit("text-evidence", "Manager qualifications", 4.0)
    client = SearchSequenceClient([
        _partial_response(hits=[text_hit], timed_out=True),
        _empty_hits(),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "timed-out-local-cid")

    assert [document.id for document in result.documents] == ["text-evidence"]
    assert result.availability is RetrievalAvailability.DEGRADED
    assert result.metadata["failed_search_channels"] == ["text"]
    assert result.metadata["search_channel_failures"] == [{"channel": "text", "reason": "timed_out"}]


def test_shard_service_failure_keeps_partial_hits_and_records_failure(monkeypatch) -> None:
    """A 5xx shard failure keeps returned hits but makes the request degraded."""
    provider = OpenSearchSectionProvider()
    text_hit = _hit("text-evidence", "Manager qualifications", 4.0)
    client = SearchSequenceClient([
        _partial_response(hits=[text_hit], shard_status=503),
        _empty_hits(),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "partial-shard-cid")

    assert [document.id for document in result.documents] == ["text-evidence"]
    assert result.availability is RetrievalAvailability.DEGRADED
    assert result.metadata["search_channel_failures"] == [
        {"channel": "text", "reason": "shard_failure", "failed_shards": 1}
    ]


def test_shard_configuration_failure_remains_visible(monkeypatch) -> None:
    """A failed shard reporting request/configuration trouble is not an outage."""
    provider = OpenSearchSectionProvider()
    client = SearchSequenceClient([
        _partial_response(shard_status=400, shard_type="query_shard_exception"),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    with pytest.raises(RequestError, match="query_shard_exception"):
        provider.retrieve("policy question", "US", "en", "new_prospect", "bad-shard-cid")


def test_mixed_transient_and_unknown_shard_failures_fail_closed(monkeypatch) -> None:
    """One valid transient shard cannot hide an unknown failed shard."""
    provider = OpenSearchSectionProvider()
    client = SearchSequenceClient([
        _partial_response(
            shard_failures=[
                _shard_failure(None, "unavailable_shards_exception"),
                _shard_failure(None, "unknown_shard_failure"),
            ],
        ),
        _empty_hits(),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    with pytest.raises(RequestError, match="unknown_shard_failure"):
        provider.retrieve("policy question", "US", "en", "new_prospect", "mixed-shard-cid")


def test_incomplete_shard_failure_diagnostics_fail_closed(monkeypatch) -> None:
    """Every failed shard needs a diagnostic before partial hits are trusted."""
    provider = OpenSearchSectionProvider()
    client = SearchSequenceClient([
        _partial_response(
            shard_failures=[_shard_failure(503, "unavailable_shards_exception")],
            failed_shards=2,
        ),
        _empty_hits(),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    with pytest.raises(RequestError, match="incomplete diagnostics"):
        provider.retrieve("policy question", "US", "en", "new_prospect", "incomplete-shard-cid")


def test_multiple_independently_valid_shard_failures_keep_partial_hits(monkeypatch) -> None:
    """Each transient or explicit 5xx failure can truthfully yield degraded hits."""
    provider = OpenSearchSectionProvider()
    text_hit = _hit("text-evidence", "Manager qualifications", 4.0)
    client = SearchSequenceClient([
        _partial_response(
            hits=[text_hit],
            shard_failures=[
                _shard_failure(None, "unavailable_shards_exception"),
                _shard_failure(503, "service_side_shard_failure"),
            ],
        ),
        _empty_hits(),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("policy question", "US", "en", "new_prospect", "multi-shard-cid")

    assert [document.id for document in result.documents] == ["text-evidence"]
    assert result.availability is RetrievalAvailability.DEGRADED
    assert result.metadata["search_channel_failures"] == [
        {"channel": "text", "reason": "shard_failure", "failed_shards": 2}
    ]


def test_timed_out_global_response_is_recorded_as_degraded(monkeypatch) -> None:
    """Global directory channels use the same partial-response contract."""
    provider = OpenSearchSectionProvider()
    global_hit = _hit("global-office", "International office directory", 4.0)
    global_hit["_source"].update({
        "country": "GLOBAL",
        "access_scope": "global",
        "document_type": "office_directory",
    })
    plan = RetrievalQueryPlan(["office phone"], include_global_documents=True)
    client = SearchSequenceClient([
        _empty_hits(),
        _empty_hits(),
        _partial_response(hits=[global_hit], timed_out=True),
        _empty_hits(),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: plan)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    result = provider.retrieve("Mexico office phone", "US", "en", "new_prospect", "timed-out-global-cid")

    assert result.availability is RetrievalAvailability.DEGRADED
    assert [document.id for document in result.documents] == ["global-office"]
    assert result.metadata["failed_search_channels"] == ["global_text"]
    assert result.metadata["search_channel_failures"] == [
        {"channel": "global_text", "reason": "timed_out"}
    ]


def test_global_shard_configuration_failure_remains_visible(monkeypatch) -> None:
    """Directory searches also surface shard request/configuration errors."""
    provider = OpenSearchSectionProvider()
    plan = RetrievalQueryPlan(["office phone"], include_global_documents=True)
    client = SearchSequenceClient([
        _empty_hits(),
        _empty_hits(),
        _partial_response(shard_status=400, shard_type="index_not_found_exception"),
    ])
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: plan)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    with pytest.raises(RequestError, match="index_not_found_exception"):
        provider.retrieve("Mexico office phone", "US", "en", "new_prospect", "global-bad-shard-cid")


def test_invalid_query_error_is_not_relabelled_as_provider_unavailability(monkeypatch) -> None:
    """A request/configuration defect remains visible to callers for diagnosis."""
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(
        opensearch_sections,
        "_client",
        lambda: SearchSequenceClient([RequestError(400, "invalid query", {"error": "bad"})]),
    )
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    with pytest.raises(RequestError):
        provider.retrieve("policy question", "US", "en", "new_prospect", "request-error-cid")


@pytest.mark.parametrize(
    "error",
    [
        RequestError(400, "invalid query", {"error": "bad"}),
        NotFoundError(404, "index_not_found_exception", {"error": "missing index"}),
        ConflictError(409, "version conflict", {"error": "conflict"}),
        TransportError(418, "unexpected client error", {"error": "unsupported"}),
        OpenSearchException("unexpected provider error"),
        ValueError("programming error"),
    ],
)
def test_non_transient_search_errors_remain_visible(monkeypatch, error) -> None:
    """Configuration and programming faults are never converted into outages."""
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())
    monkeypatch.setattr(opensearch_sections, "_client", lambda: SearchSequenceClient([error]))
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_: [0.1])

    with pytest.raises(type(error)):
        provider.retrieve("policy question", "US", "en", "new_prospect", "visible-error-cid")


def test_client_configuration_error_is_not_relabelled_as_provider_unavailability(monkeypatch) -> None:
    """A local configuration defect must remain diagnosable, not look empty."""
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: _search_plan())

    def broken_client():
        raise RuntimeError("OPENSEARCH_HOST is not configured")

    monkeypatch.setattr(opensearch_sections, "_client", broken_client)

    with pytest.raises(RuntimeError, match="OPENSEARCH_HOST"):
        provider.retrieve("policy question", "US", "en", "new_prospect", "configuration-cid")


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
        ({"id": "a", "metadata": {"source_file": "p.pdf", "parent_section_id": "5.01"}}, 0.9),
        ({"id": "b", "metadata": {"source_file": "p.pdf", "parent_section_id": "5.01"}}, 0.8),
        ({"id": "c", "metadata": {"source_file": "p.pdf", "parent_section_id": "5.02"}}, 0.7),
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
    ) == ([], False, None, None)
    assert _parse_selector_decision("not json") is None


def test_selector_decision_parses_and_clamps_top_rank_confidence() -> None:
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"top_rank_confidence":0.92,"reason":"direct clause"}'
    ) == ([2], None, 0.92, None)
    # Out-of-range and malformed values are clamped/ignored rather than trusted verbatim.
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"top_rank_confidence":1.4,"reason":"x"}'
    ) == ([2], None, 1.0, None)
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"top_rank_confidence":"not a number","reason":"x"}'
    ) == ([2], None, None, None)
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"reason":"no confidence field at all"}'
    ) == ([2], None, None, None)


def test_selector_decision_parses_directly_answers_top_rank() -> None:
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"directly_answers_top_rank":true,"top_rank_confidence":0.9,"reason":"x"}'
    ) == ([2], None, 0.9, True)
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"directly_answers_top_rank":false,"top_rank_confidence":0.75,"reason":"x"}'
    ) == ([2], None, 0.75, False)
    # A malformed value (not a real bool) is treated as unknown, not trusted as true.
    assert _parse_selector_decision(
        '{"selected_ranks":[2],"directly_answers_top_rank":"yes","top_rank_confidence":0.9,"reason":"x"}'
    ) == ([2], None, 0.9, None)


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


def test_selector_confidence_marks_only_the_top_ranked_pick(monkeypatch) -> None:
    """top_rank_confidence describes the model's #1 pick, not every selected row."""
    class Runtime:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"selected_ranks":[2,1],"directly_answers_top_rank":true,'
                                    '"top_rank_confidence":0.9,'
                                    '"reason":"direct clause, then supporting context"}'
                                )
                            }
                        ]
                    }
                }
            }

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(
        opensearch_sections,
        "get_aws_clients",
        lambda: type("Clients", (), {"bedrock_runtime": Runtime()})(),
    )
    rows = [
        ({"id": "supporting", "metadata": {}, "content": "Supporting context."}, 2.0),
        ({"id": "direct", "metadata": {}, "content": "Direct evidence."}, 1.5),
    ]

    selected = OpenSearchSectionProvider()._select_evidence_rows("Question", rows, "cid")

    assert selected[0][0]["id"] == "direct"
    assert selected[0][0]["evidence_selector_confidence"] == 0.9
    assert "evidence_selector_confidence" not in selected[1][0]


def test_selector_confidence_is_withheld_when_pick_is_not_a_direct_answer(monkeypatch) -> None:
    """A high top_rank_confidence alone must not rescue a candidate the model
    itself flagged as only related, not a direct answer (a plain 0-1 rating
    was not a reliable enough signal on its own - it rated a topically
    related but wrong clause just as confidently as a correct one)."""
    class Runtime:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"selected_ranks":[1],"directly_answers_top_rank":false,'
                                    '"top_rank_confidence":0.75,"reason":"related but different scenario"}'
                                )
                            }
                        ]
                    }
                }
            }

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(
        opensearch_sections,
        "get_aws_clients",
        lambda: type("Clients", (), {"bedrock_runtime": Runtime()})(),
    )
    rows = [({"id": "related", "metadata": {}, "content": "Related but different scenario."}, 1.5)]

    selected = OpenSearchSectionProvider()._select_evidence_rows("Question", rows, "cid")

    assert selected[0][0]["evidence_selector_selected"] is True
    assert "evidence_selector_confidence" not in selected[0][0]
    # Confidence blending never lets this lower the approval score - a
    # correct paraphrase can score this way too - but generation still needs
    # the signal, so it must be threaded through even though the rescue
    # confidence above is deliberately withheld.
    assert selected[0][0]["evidence_selector_directly_answers"] is False


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


def test_empty_selection_without_hardening_is_logged_and_preserves_rows(monkeypatch, caplog) -> None:
    """When hardening is OFF and the model returns a parseable decision whose
    selected_ranks is empty (or doesn't map to any candidate), the original
    rows must still be returned unchanged - but this outcome must now be
    observable in the logs, unlike before this change."""
    import logging

    class Runtime:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    '{"relevant_evidence":false,"selected_ranks":[],'
                                    '"top_rank_confidence":0.2,"directly_answers_top_rank":false,'
                                    '"reason":"nothing clearly supports this"}'
                                )
                            }
                        ]
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
    rows = [({"id": "original", "metadata": {}, "content": "Approved evidence."}, 1.0)]

    caplog.set_level(logging.INFO)
    result = OpenSearchSectionProvider()._select_evidence_rows("Question", rows, "cid")

    assert result == rows

    matching = [r for r in caplog.records if r.getMessage() == "opensearch_evidence_selector_no_selection"]
    assert len(matching) == 1
    record = matching[0]
    assert record.correlation_id == "cid"
    assert record.context == {
        "candidate_count": 1,
        "ranks": [],
        "relevant_evidence": False,
        "top_rank_confidence": 0.2,
        "directly_answers_top_rank": False,
    }
    assert not any(
        r.getMessage() == "opensearch_evidence_selector_no_relevant_evidence" for r in caplog.records
    )


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


def test_policy_safety_question_still_reaches_retrieval(monkeypatch) -> None:
    """Asking what the rules prohibit must not skip the documents.

    Verified live 2026-09-07: the planner classifies these as medical_claim or
    income_claim, and skipping retrieval here left nothing to answer from, so the
    request was refused downstream regardless of the routing layers.
    """
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(
        provider,
        "_build_search_plan",
        lambda *_: RetrievalQueryPlan(
            ["Does company policy prohibit medical claims?"],
            conversation_intent="medical_claim",
            intent_confidence=0.98,
        ),
    )
    searched: list[str] = []
    monkeypatch.setattr(
        opensearch_sections,
        "_client",
        lambda: searched.append("called") or (_ for _ in ()).throw(RuntimeError("stop after search starts")),
    )

    with pytest.raises(RuntimeError):
        provider.retrieve("Does company policy prohibit medical claims?", "US", "en", "new_prospect", "cid")

    assert searched, "retrieval must be attempted for a reviewed policy-safety question"


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


def test_dominance_guard_restores_kyrgyzstan_shaped_directory_record() -> None:
    """Mirrors the real 2026-09-14 production failure: a dominant,
    country-matched Kyrgyzstan directory record (score 9.444) scored well
    ahead of everything else (next-best 4.37), but the LLM selector's
    reordered output put an unrelated, low-scoring US policy section first
    instead. The guard must put the Kyrgyzstan record back on top."""
    kyrgyzstan_row = {
        "id": "kyrgyzstan-bonus-payment",
        "document_type": "office_directory",
        "metadata": {"record_country": "Kyrgyzstan"},
    }
    us_policy_row = {"id": "us-policy-4-04-f", "document_type": "policy"}
    other_row_a = {"id": "candidate-a", "document_type": "policy"}
    other_row_b = {"id": "candidate-b", "document_type": "policy"}

    raw_rows = [
        (kyrgyzstan_row, 9.444),
        (other_row_a, 4.37),
        (other_row_b, 1.09),
        (us_policy_row, 1.066),
    ]
    # The selector reordered candidates, demoting the dominant directory
    # record to last place - exactly the real failure shape.
    selector_rows = [
        (us_policy_row, 1.066),
        (other_row_b, 1.09),
        (other_row_a, 4.37),
        (kyrgyzstan_row, 9.444),
    ]

    restored = _restore_dominant_directory_record(
        "How are foreign FBOs paid their bonus in Kyrgyzstan?",
        raw_rows,
        selector_rows,
        {"Kyrgyzstan"},
    )

    assert restored[0][0]["id"] == "kyrgyzstan-bonus-payment"
    # Everything else keeps the selector's own relative order.
    assert [row.get("id") for row, _score in restored[1:]] == [
        "us-policy-4-04-f",
        "candidate-b",
        "candidate-a",
    ]


def test_dominance_guard_does_not_fire_on_a_close_non_dominant_contest() -> None:
    """When the top raw score does not clearly dominate the field (a normal,
    close contest the selector is entitled to resolve on its own), the guard
    must leave the selector's chosen order untouched."""
    directory_row = {
        "id": "close-directory-row",
        "document_type": "office_directory",
        "metadata": {"record_country": "Uruguay"},
    }
    policy_row = {"id": "close-policy-row", "document_type": "policy"}

    raw_rows = [(directory_row, 7.5), (policy_row, 6.0)]  # ratio ~1.25x, not dominant
    # The selector reasonably chose the policy row instead.
    selector_rows = [(policy_row, 6.0), (directory_row, 7.5)]

    restored = _restore_dominant_directory_record(
        "What is the phone number for Forever Uruguay?",
        raw_rows,
        selector_rows,
        {"Uruguay"},
    )

    assert restored == selector_rows


def test_dominance_guard_does_not_fire_without_a_genuine_country_match() -> None:
    """A directory row that merely scores well generically - no genuine
    target-country match bonus from `_directory_record_country_score` - must
    never trigger the guard, even if its raw score dominates the field. This
    is not a blanket 'always trust the top score' rule."""
    generic_directory_row = {
        "id": "generic-directory-row",
        "document_type": "office_directory",
        # No target_country_names supplied below, so this row can only ever
        # earn the weak, generic lexical/acronym fallback score (<= 2.4),
        # never the >= 6.0 genuine-match bonus the guard requires.
        "metadata": {"record_country": "Someplace Unrelated"},
    }
    local_policy_row = {"id": "local-policy-row", "document_type": "policy"}

    raw_rows = [(generic_directory_row, 9.0), (local_policy_row, 1.0)]
    selector_rows = [(local_policy_row, 1.0), (generic_directory_row, 9.0)]

    restored = _restore_dominant_directory_record(
        "What are the office hours?",
        raw_rows,
        selector_rows,
        None,
    )

    assert restored == selector_rows


def test_dominance_guard_does_not_reorder_a_pinned_policy_over_directory_scope_question() -> None:
    """Regression for the mixed sponsoring/policy-scope case pinned by
    `tests/unit/test_mixed_sponsoring_policy_scope.py`: "What is the company
    policy on sponsoring someone in Italy?" from an Austrian session must keep
    the session's OWN policy first, with the Italy directory record second -
    even though Italy is explicitly named and named-country matches reliably
    earn a >= 6.0 country bonus that can make the directory row's raw score
    dominate by more than 2x. The guard must not fire on this question at all:
    it is a general company-policy question, not a request for directory
    detail content."""
    italy_directory_row = {
        "id": "GLOBAL:sponsoring-italy",
        "document_type": "international_sponsoring_directory",
        "metadata": {"record_country": "Italy"},
    }
    austria_policy_row = {"id": "AT:4.01", "document_type": "policy"}

    raw_rows = [(italy_directory_row, 9.0), (austria_policy_row, 1.0)]
    # The selector correctly kept the session's own policy first, exactly as
    # `test_mixed_sponsoring_policy_scope.py` pins.
    selector_rows = [(austria_policy_row, 1.0), (italy_directory_row, 9.0)]

    restored = _restore_dominant_directory_record(
        "What is the company policy on sponsoring someone in Italy?",
        raw_rows,
        selector_rows,
        {"Italy"},
    )

    assert restored == selector_rows


def test_dominance_guard_returns_empty_rows_unchanged_when_selector_refused() -> None:
    """When hardening is on and the selector deliberately returns `[]` (a
    considered "no relevant evidence" refusal), the guard must never resurrect
    a dominant raw candidate and turn that refusal into an answer."""
    kyrgyzstan_row = {
        "id": "kyrgyzstan-bonus-payment",
        "document_type": "office_directory",
        "metadata": {"record_country": "Kyrgyzstan"},
    }
    raw_rows = [(kyrgyzstan_row, 9.444), ({"id": "other", "document_type": "policy"}, 1.0)]

    restored = _restore_dominant_directory_record(
        "How are foreign FBOs paid their bonus in Kyrgyzstan?",
        raw_rows,
        [],
        {"Kyrgyzstan"},
    )

    assert restored == []


def test_dominance_guard_finds_the_true_top_score_when_raw_rows_is_not_sorted() -> None:
    """`raw_rows` is assigned after the optional Bedrock reranker may have
    already reordered rows by semantic rank without changing their scores, so
    the dominant directory row is not guaranteed to sit at index 0 (nor the
    best-of-the-rest at index 1). The guard must derive both by score, not by
    list position."""
    kyrgyzstan_row = {
        "id": "kyrgyzstan-bonus-payment",
        "document_type": "office_directory",
        "metadata": {"record_country": "Kyrgyzstan"},
    }
    low_score_row = {"id": "low-score-row", "document_type": "policy"}
    real_runner_up_row = {"id": "real-runner-up", "document_type": "policy"}

    # A reranker put the dominant row at index 1 (not 0), and a lower-scoring
    # row at index 0 - simulating semantic-rank reordering that never touches
    # scores. The true best-of-the-rest (4.37) sits at index 2, not index 1.
    raw_rows = [
        (low_score_row, 0.5),
        (kyrgyzstan_row, 9.444),
        (real_runner_up_row, 4.37),
    ]
    selector_rows = [
        (real_runner_up_row, 4.37),
        (low_score_row, 0.5),
        (kyrgyzstan_row, 9.444),
    ]

    restored = _restore_dominant_directory_record(
        "How are foreign FBOs paid their bonus in Kyrgyzstan?",
        raw_rows,
        selector_rows,
        {"Kyrgyzstan"},
    )

    assert restored[0][0]["id"] == "kyrgyzstan-bonus-payment"
    assert [row.get("id") for row, _score in restored[1:]] == ["real-runner-up", "low-score-row"]


def test_dominance_guard_fires_just_above_the_ratio_threshold() -> None:
    """Boundary-pinning: 7.5 vs 3.73 is a ratio of ~2.0107x, just above the
    2.0x threshold, so the guard must fire."""
    directory_row = {
        "id": "boundary-directory-row",
        "document_type": "office_directory",
        "metadata": {"record_country": "Uruguay"},
    }
    policy_row = {"id": "boundary-policy-row", "document_type": "policy"}

    raw_rows = [(directory_row, 7.5), (policy_row, 3.73)]
    selector_rows = [(policy_row, 3.73), (directory_row, 7.5)]

    restored = _restore_dominant_directory_record(
        "What is the phone number for Forever Uruguay?",
        raw_rows,
        selector_rows,
        {"Uruguay"},
    )

    assert restored[0][0]["id"] == "boundary-directory-row"


def test_dominance_guard_does_not_fire_just_below_the_ratio_threshold() -> None:
    """Boundary-pinning: 7.5 vs 3.77 is a ratio of ~1.9894x, just below the
    2.0x threshold, so the guard must not fire."""
    directory_row = {
        "id": "boundary-directory-row",
        "document_type": "office_directory",
        "metadata": {"record_country": "Uruguay"},
    }
    policy_row = {"id": "boundary-policy-row", "document_type": "policy"}

    raw_rows = [(directory_row, 7.5), (policy_row, 3.77)]
    selector_rows = [(policy_row, 3.77), (directory_row, 7.5)]

    restored = _restore_dominant_directory_record(
        "What is the phone number for Forever Uruguay?",
        raw_rows,
        selector_rows,
        {"Uruguay"},
    )

    assert restored == selector_rows

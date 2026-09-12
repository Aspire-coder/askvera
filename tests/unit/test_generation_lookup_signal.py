"""A failed active-generation lookup is signalled, not mistaken for an empty search.

When the generation pointer is on, every OpenSearch query is filtered to the
published ingestion ids. If the lookup of those ids fails (for example the
database tunnel is down), retrieval fails closed with the
``__no_active_generation__`` sentinel filter and returns nothing - which, before
this signal, looked exactly like a genuine empty search.

These tests pin that the behaviour stays fail-closed and unchanged, that the
internal ``generation_lookup`` metadata tells the three cases apart, that the
failure log carries no connection details, and that the signal reaches neither
the public API response, the cache value nor the analytics row.

No network: the database engine and the OpenSearch client are stubs.
"""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy.exc import OperationalError

from app.response.models import ChatResponse
from app.retrieval import opensearch_sections
from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.providers import RetrievalQueryPlan
from config import settings
from services import analytics, knowledge_generations
from utils.logging import JsonFormatter
from utils.validators import ChatRequest

QUESTION = "What is the service fee?"
SENTINEL = "__no_active_generation__"
CA_GENERATION = "gen-ca-en-1"
CA_ROW = {
    "country": "CA",
    "language": "en",
    "document_type": "policy",
    "access_scope": "country",
    "active_ingestion_id": CA_GENERATION,
}
# Everything a real driver error can carry that must never be logged or signalled.
SECRETS = (
    "db-secret.internal.example",
    "10.9.8.7",
    "65431",
    "SELECT",
    "knowledge_active_generations",
    "hunter2",
    "askvera_admin",
    "postgresql://",
)


def _driver_error() -> OperationalError:
    return OperationalError(
        "SELECT country, language FROM knowledge_active_generations WHERE active_ingestion_id <> ''",
        {"password": "hunter2"},
        Exception(
            'connection to server at "db-secret.internal.example" (10.9.8.7), port 65431 failed: '
            'FATAL: password authentication failed for user "askvera_admin" '
            "(postgresql://askvera_admin:hunter2@db-secret.internal.example:65431/askvera)"
        ),
    )


class _FailingEngine:
    def __init__(self) -> None:
        self.attempts = 0

    def connect(self):
        self.attempts += 1
        raise _driver_error()


class _Rows:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _Connection:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, _statement):
        return _Rows(self._rows)


class _RowsEngine:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.attempts = 0

    def connect(self):
        self.attempts += 1
        return _Connection(self.rows)


def _hit(identifier: str, section_id: str, title: str, score: float) -> dict[str, object]:
    content = f"Section {section_id}: {title}. The service fee is 2.50 per order."
    return {
        "_id": identifier,
        "_score": score,
        "_source": {
            "id": identifier,
            "section_id": section_id,
            "section_title": title,
            "content": content,
            "search_text": content,
            "source_file": "CA-EN-Company-Policy.pdf",
            "country": "CA",
            "language": "en",
            "document_type": "policy",
            "access_scope": "country",
            "status": "active",
            "ingestion_id": CA_GENERATION,
        },
    }


HITS = [
    _hit("ca-13-01", "13.01", "Service fee", 42.0),
    _hit("ca-13-02", "13.02", "Service fee refunds", 30.0),
    _hit("ca-07-03", "7.03", "Order service levels", 12.0),
]


class _Client:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.bodies: list[str] = []

    def search(self, index, body):
        del index
        self.bodies.append(json.dumps(body))
        return {"hits": {"hits": [dict(hit) for hit in self.hits]}}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", False)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda _text: [0.0] * 4)
    knowledge_generations.clear_active_generation_cache()
    yield
    knowledge_generations.clear_active_generation_cache()


def _retrieve(monkeypatch, engine, hits: list[dict[str, object]]):
    """One request: a single-query plan builds exactly two filters (text and vector)."""
    monkeypatch.setattr(knowledge_generations, "get_engine", lambda: engine)
    knowledge_generations.clear_active_generation_cache()
    client = _Client(hits)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda *_: RetrievalQueryPlan([QUESTION]))
    return provider.retrieve(QUESTION, "CA", "en", "fbo", "cid-generation-lookup"), client


def _without_signal(metadata: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in metadata.items() if key != "generation_lookup"}


def _ranked(result) -> list[tuple[str, float]]:
    return [(document.id, document.score) for document in result.documents]


def test_a_failed_lookup_is_signalled_and_retrieval_stays_fail_closed(monkeypatch) -> None:
    engine = _FailingEngine()
    failed, client = _retrieve(monkeypatch, engine, [])
    none_configured, _ = _retrieve(monkeypatch, _RowsEngine([]), [])

    assert failed.metadata["generation_lookup"] == {
        "status": "failed",
        "error_type": "OperationalError",
        "filter_count": 2,
        "sentinel_filter_count": 2,
    }
    assert len(client.bodies) == 2
    assert all(SENTINEL in body for body in client.bodies)
    assert failed.documents == []
    assert failed.citations == []
    assert failed.confidence == 0.0
    # Failures are still not cached: one database attempt per filter, as before.
    assert engine.attempts == 2
    # Apart from the signal, the result is exactly the "no generation" result.
    assert _without_signal(failed.metadata) == _without_signal(none_configured.metadata)


def test_a_successful_lookup_with_hits_keeps_documents_and_ranks(monkeypatch) -> None:
    published, client = _retrieve(monkeypatch, _RowsEngine([CA_ROW]), HITS)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    unfiltered, _ = _retrieve(monkeypatch, _RowsEngine([CA_ROW]), HITS)

    assert published.documents, "the stub hits must survive retrieval for this control to mean anything"
    assert published.metadata["generation_lookup"] == {
        "status": "ok",
        "error_type": None,
        "filter_count": 2,
        "sentinel_filter_count": 0,
    }
    assert all(CA_GENERATION in body and SENTINEL not in body for body in client.bodies)
    assert _ranked(published) == _ranked(unfiltered)
    assert published.confidence == unfiltered.confidence
    assert "generation_lookup" not in unfiltered.metadata
    assert _without_signal(published.metadata) == unfiltered.metadata


def test_a_successful_lookup_with_a_genuinely_empty_search_is_not_a_failure(monkeypatch) -> None:
    result, client = _retrieve(monkeypatch, _RowsEngine([CA_ROW]), [])

    assert result.documents == []
    assert result.metadata["generation_lookup"] == {
        "status": "ok",
        "error_type": None,
        "filter_count": 2,
        "sentinel_filter_count": 0,
    }
    assert all(SENTINEL not in body for body in client.bodies)


def test_no_published_generation_is_reported_as_none_active(monkeypatch) -> None:
    result, client = _retrieve(monkeypatch, _RowsEngine([]), HITS)

    assert result.metadata["generation_lookup"] == {
        "status": "none_active",
        "error_type": None,
        "filter_count": 2,
        "sentinel_filter_count": 2,
    }
    assert all(SENTINEL in body for body in client.bodies)


def test_the_failure_log_carries_no_connection_details_and_is_once_per_request(monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    formatter = JsonFormatter()

    first, _ = _retrieve(monkeypatch, _FailingEngine(), [])
    second, _ = _retrieve(monkeypatch, _FailingEngine(), [])

    failures = [record for record in caplog.records if record.getMessage() == "active_generation_lookup_failed"]
    # Two filters failed in each request; each request warns exactly once.
    assert len(failures) == 2
    for record in failures:
        assert record.levelno == logging.ERROR
        assert record.exc_info is None
        assert record.exc_text is None
        assert record.stack_info is None
        assert record.context == {"error_type": "OperationalError"}
    for record in caplog.records:
        rendered = json.loads(formatter.format(record))
        rendered.pop("timestamp", None)
        text = " ".join(
            (record.getMessage(), json.dumps(rendered), repr(record.args), repr(record.__dict__))
        )
        for secret in SECRETS:
            assert secret not in text, f"{secret!r} leaked through log record {record.getMessage()!r}"
    for result in (first, second):
        signal = json.dumps(result.metadata["generation_lookup"])
        for secret in SECRETS:
            assert secret not in signal


def test_a_failed_request_does_not_mark_the_next_request(monkeypatch) -> None:
    failed, _ = _retrieve(monkeypatch, _FailingEngine(), [])
    recovered, _ = _retrieve(monkeypatch, _RowsEngine([CA_ROW]), [])

    assert failed.metadata["generation_lookup"]["status"] == "failed"
    assert recovered.metadata["generation_lookup"]["status"] == "ok"
    assert recovered.metadata["generation_lookup"]["error_type"] is None


def test_no_signal_when_the_generation_pointer_is_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    engine = _FailingEngine()

    result, client = _retrieve(monkeypatch, engine, [])

    assert "generation_lookup" not in result.metadata
    assert engine.attempts == 0
    assert all(SENTINEL not in body for body in client.bodies)


def test_the_signal_reaches_neither_the_api_response_the_cache_nor_analytics(monkeypatch) -> None:
    failed, _ = _retrieve(monkeypatch, _FailingEngine(), [])
    response = ChatResponse(
        answer="I could not find that in the approved documents.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.0,
        metadata={**failed.metadata, "failure_layer": "retrieval", "model_name": "model-under-test"},
        correlation_id="cid-generation-lookup",
    )
    assert response.metadata["generation_lookup"]["status"] == "failed"

    persisted: list[dict[str, object]] = []

    class _Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def execute(self, _statement, parameters):
            persisted.append(dict(parameters))

    class _AnalyticsEngine:
        def begin(self):
            return _Transaction()

    monkeypatch.setattr(analytics, "get_engine", lambda: _AnalyticsEngine())
    analytics.record_chat_interaction(
        ChatRequest(message=QUESTION, sessionId="session-1", country="CA", language="en"),
        response,
        "cid-generation-lookup",
    )

    assert len(persisted) == 1
    for public in (response.to_api_result(), response.to_cache_value(), persisted[0]):
        text = json.dumps(public, default=str)
        assert "generation_lookup" not in text
        assert "OperationalError" not in text
        assert "sentinel_filter_count" not in text

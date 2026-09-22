"""R10 case r10-04b: a US policy question answered in English, refused in Spanish.

Live capture 2026-09-22 (approval R10-2026-09-22-KRISH, code f23f02e, production
EC2 host, checkpoint /tmp/r10_ec2.checkpoint.jsonl):

- r10-04-us-cash-payment-1301c, en: "Can I pay for my order in cash?" was
  ANSWERED from US section 13.01(c) at confidence 0.95.
- r10-04b-us-cash-payment-1301c-es, es: the same question in Spanish was
  REFUSED at the low-confidence gate (model_low_confidence_blocked,
  failure_layer low_confidence) at confidence 0.188.

Same market, same section, same policy. The US publishes only English editions,
so _language_filter widens the Spanish request to them
(OPENSEARCH_ALLOW_ENGLISH_FALLBACK) -- but the locale search channels then
searched those English sections with the question's own Spanish words, which
share nothing with them. The global scope has translated its query since it was
introduced (_global_search_query); the locale scope, which is where a market's
own policy lives, had none.

These tests are offline. The OpenSearch client, embeddings and the Bedrock
runtime are replaced; nothing reaches AWS or the network.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.providers import RetrievalQueryPlan
from config import settings

SPANISH_QUESTION = "¿Puedo pagar mi pedido en efectivo?"
ENGLISH_RENDERING = "Can I pay for my order in cash?"


class _RecordingClient:
    """Answers every search with one English US section and records the query text."""

    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def search(self, index: str, body: dict) -> dict:
        del index
        self.bodies.append(body)
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "US:13.01-c",
                        "_score": 3.0,
                        "_source": {
                            "id": "US:13.01-c",
                            "source_file": "US-EN-Company-Policy.pdf",
                            "source_uri": "s3://approved/us.pdf",
                            "country": "US",
                            "language": "en",
                            "document_type": "policy",
                            "access_scope": "country",
                            "status": "active",
                            "section_id": "13.01-c",
                            "section_title": "Payment",
                            "content": (
                                "Acceptable forms of payment are credit card (Visa, MasterCard, "
                                "Discover), PayPal, ApplePay (for North America ONLY), check, or "
                                "money order."
                            ),
                        },
                    }
                ]
            }
        }


def _translating_runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{"text": ENGLISH_RENDERING}]}}
    }
    return runtime


@pytest.fixture
def _offline(monkeypatch):
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_a, **_k: [0.0])
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    monkeypatch.setattr(settings, "BEDROCK_QUERY_PLANNER_ENABLED", False)
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", False)


def _retrieve(monkeypatch, language: str, client: _RecordingClient):
    monkeypatch.setattr(
        opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=_translating_runtime())
    )
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    message = SPANISH_QUESTION if language != "en" else ENGLISH_RENDERING
    return OpenSearchSectionProvider().retrieve(message, "US", language, "new_prospect", "cid")


def _locale_query_texts(client: _RecordingClient) -> str:
    return " ".join(repr(body) for body in client.bodies if "'access_scope': 'global'" not in repr(body))


# --- the defect ---------------------------------------------------------------


def test_spanish_question_reaches_the_english_sections_in_english(monkeypatch, _offline) -> None:
    """Fail-before: only the Spanish wording was ever sent to the English editions."""
    client = _RecordingClient()
    _retrieve(monkeypatch, "es", client)

    assert ENGLISH_RENDERING in _locale_query_texts(client)


def test_the_question_keeps_its_own_words_as_the_first_query(monkeypatch, _offline) -> None:
    """The rendering is appended, never substituted: the user's wording still leads."""
    client = _RecordingClient()
    _retrieve(monkeypatch, "es", client)

    assert SPANISH_QUESTION in _locale_query_texts(client)


def test_spanish_and_english_sessions_retrieve_the_same_section(monkeypatch, _offline) -> None:
    """The R10 pair: one market, one section, one outcome in both languages."""
    spanish = _retrieve(monkeypatch, "es", _RecordingClient())
    english = _retrieve(monkeypatch, "en", _RecordingClient())

    assert [document.id for document in spanish.documents] == [document.id for document in english.documents]


# --- the rule is about the configured fallback, not about a market or a language ---


def test_an_english_session_gets_no_extra_query(monkeypatch, _offline) -> None:
    plan = RetrievalQueryPlan([ENGLISH_RENDERING])
    monkeypatch.setattr(
        opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=_translating_runtime())
    )

    widened = OpenSearchSectionProvider()._with_fallback_language_query(plan, ENGLISH_RENDERING, "en", "cid")

    assert widened.queries == [ENGLISH_RENDERING]


def test_no_extra_query_when_english_fallback_is_off(monkeypatch, _offline) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", False)
    plan = RetrievalQueryPlan([SPANISH_QUESTION])

    widened = OpenSearchSectionProvider()._with_fallback_language_query(plan, SPANISH_QUESTION, "es", "cid")

    assert widened.queries == [SPANISH_QUESTION]


def test_every_non_english_language_is_widened_the_same_way(monkeypatch, _offline) -> None:
    """No market list and no language list: the rule is the configured fallback alone."""
    monkeypatch.setattr(
        opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=_translating_runtime())
    )
    provider = OpenSearchSectionProvider()

    for language in ("es", "de", "it", "fr", "nl", "sv", "ru"):
        widened = provider._with_fallback_language_query(
            RetrievalQueryPlan([SPANISH_QUESTION]), SPANISH_QUESTION, language, "cid"
        )
        assert widened.queries == [SPANISH_QUESTION, ENGLISH_RENDERING], language


def test_a_failed_translation_changes_nothing(monkeypatch, _offline) -> None:
    """Falling back to the question's own words is the safe outcome, not an empty query."""
    runtime = MagicMock()
    runtime.converse.return_value = {"output": {"message": {"content": [{"text": "   "}]}}}
    monkeypatch.setattr(
        opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime)
    )

    widened = OpenSearchSectionProvider()._with_fallback_language_query(
        RetrievalQueryPlan([SPANISH_QUESTION]), SPANISH_QUESTION, "es", "cid"
    )

    assert widened.queries == [SPANISH_QUESTION]

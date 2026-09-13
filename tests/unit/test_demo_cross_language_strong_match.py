"""Demo W6 (B): a Dutch question keeps the strong-match rescue against the English NL section.

Live (NL session, response language English): "Hoeveel kost een licentie om
het Forever-merk te gebruiken als FBO?" was refused on enough_score. Provider
confidence was 0.164, evidence_selector_confidence was null, and
strong_local_match was false because the question's lexical relevance to the
English section 19.02 was 0.4234 (threshold 0.44). The same question scores
0.5134 against the Dutch edition, so Dutch output passed.

The rescue now also accepts a translated planner query, but only when the
question's ordinary words appear nowhere in the chosen own-market section, in
any retrieved candidate of that language, or in the query itself.

Every test is offline. AWS clients, embeddings, the OpenSearch client, sockets
and the selector model are replaced before use; the real ones raise.
"""

from __future__ import annotations

import copy
import socket
from types import SimpleNamespace

import pytest

import services.aws_clients as aws_clients
import services.embeddings as embeddings
from app.evidence import approve_evidence
from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.providers import RetrievalQueryPlan, _document_relevance
from app.retrieval.section_index import _confidence_from_documents
from config import settings

THRESHOLD = settings.OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD
DUTCH_QUESTION = "Hoeveel kost een licentie om het Forever-merk te gebruiken als FBO?"
ENGLISH_QUESTION = "How much does a license to use the Forever brand cost for an FBO?"
ENGLISH_PLANNER_QUERY = "license fee to use Forever trademark FBO"
DUTCH_PLANNER_QUERY = "kosten licentie Forever merk FBO"
TOP_SCORE = 1.203775
MARGIN = 0.042681

EN_19_02_B = (
    "Each FBO is hereby licensed by Forever to use Forever's registered trademarks in the manner "
    "described. The license granted herein shall be effective only as long as the FBO is in good standing."
)
EN_19_02 = "Limited License to Use Company Marks. The FBO may use Company marks only as permitted by this section."
NL_19_02_B = (
    "Elke FBO krijgt hierbij van Forever een licentie om de geregistreerde handelsmerken van Forever te "
    "gebruiken. De licentie is alleen geldig zolang de FBO in goede staat verkeert."
)


def _live_call(*_: object, **__: object):
    raise AssertionError("W6 tests must never make an AWS, embedding, OpenSearch, network or model call")


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _live_call)
    monkeypatch.setattr(socket, "create_connection", _live_call)
    monkeypatch.setattr(aws_clients, "get_aws_clients", _live_call)
    monkeypatch.setattr(embeddings, "embed_text", _live_call)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "embed_text", _live_call)
    monkeypatch.setattr(opensearch_sections, "_client", _live_call)


def _document(
    section_id: str,
    language: str,
    content: str,
    score: float = TOP_SCORE,
    *,
    country: str = "NL",
    title: str = "Limited License to Use Company Marks",
    access_scope: str = "country",
    document_type: str = "policy",
) -> RetrievedDocument:
    source_file = f"{country}-{language.upper()} Benelux Company Policy"
    return RetrievedDocument(
        id=f"{country.lower()}-{language}-{section_id}",
        title=f"{source_file} - Sec {section_id}: {title}",
        content=content,
        source=f"opensearch-section://{source_file}/{section_id}",
        excerpt=content[:300],
        country=country,
        language=language,
        score=score,
        metadata={
            "access_scope": access_scope, "document_type": document_type, "section_id": section_id,
            "section_title": title, "parent_section_id": "19.02", "status": "active",
        },
    )


def _row(document: RetrievedDocument) -> tuple[dict, float]:
    return (
        {"section_title": document.metadata["section_title"], "content": document.content,
         "language": document.language},
        document.score,
    )


def _english_rows() -> list[RetrievedDocument]:
    return [_document("19.02-b", "en", EN_19_02_B), _document("19.02", "en", EN_19_02, TOP_SCORE - MARGIN)]


def _relevance(question: str, documents: list[RetrievedDocument], queries: list[str], country: str = "NL") -> float:
    """Exactly what retrieve() computes for the top document after the selector applied."""
    relevance = _document_relevance(question, documents[0])
    if relevance < THRESHOLD:
        relevance = max(
            relevance,
            opensearch_sections._translated_query_local_relevance(question, country, documents[0], queries, [_row(d) for d in documents]),
        )
    return relevance


def _gate(question: str, documents: list[RetrievedDocument], relevance: float, language: str):
    result = RetrievalResult(
        documents=documents,
        citations=[document.to_source() for document in documents],
        confidence=_confidence_from_documents(documents),
        metadata={
            "evidence_selector_applied": True, "evidence_selector_confidence": None,
            "max_local_relevance": relevance, "strong_local_match": relevance >= THRESHOLD,
        },
    )
    return result, approve_evidence(question, result, "NL", language)


# --- fail-before: the live shape --------------------------------------------------------


def test_live_numbers_reproduce() -> None:
    documents = _english_rows()
    assert _document_relevance(DUTCH_QUESTION, documents[0]) == pytest.approx(0.423444)
    assert _document_relevance(DUTCH_QUESTION, _document("19.02-b", "nl", NL_19_02_B)) == pytest.approx(0.513444)
    assert _confidence_from_documents(documents) < settings.BEDROCK_CONFIDENCE_EVIDENCE_MIN_CONFIDENCE


def test_dutch_question_with_english_nl_section_keeps_the_strong_match_rescue() -> None:
    documents = _english_rows()
    relevance = _relevance(DUTCH_QUESTION, documents, [ENGLISH_PLANNER_QUERY, DUTCH_PLANNER_QUERY])

    result, decision = _gate(DUTCH_QUESTION, documents, relevance, "en")

    assert relevance == pytest.approx(_document_relevance(ENGLISH_PLANNER_QUERY, documents[0]))
    assert result.metadata["strong_local_match"] is True
    assert decision.approved is True
    assert [document.id for document in decision.evidence] == ["nl-en-19.02-b", "nl-en-19.02"]


class _Client:
    def __init__(self, hits: list[dict]) -> None:
        self.hits = hits

    def search(self, index, body):
        del index, body
        return {"hits": {"hits": copy.deepcopy(self.hits)}}


class _Runtime:
    """Selector reply as live: picks the section but gives no trusted confidence."""

    def converse(self, **_kwargs):
        return {"output": {"message": {"content": [{
            "text": '{"selected_ranks":[1,2],"directly_answers_top_rank":false,"top_rank_confidence":0.6}'
        }]}}}


def _hit(document: RetrievedDocument, score: float) -> dict:
    return {
        "_id": document.id,
        "_score": score,
        "_source": {
            "id": document.id, "section_id": document.metadata["section_id"],
            "section_title": document.metadata["section_title"], "content": document.content,
            "source_file": f"NL-{document.language.upper()} Benelux Company Policy", "country": document.country,
            "language": document.language, "document_type": "policy", "access_scope": "country", "status": "active",
            "parent_section_id": "19.02",
        },
    }


def _retrieve(monkeypatch, question: str, documents: list[RetrievedDocument], queries: list[str], *,
              language: str = "en", selector: bool = True):
    for name, value in {
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED": False,
        "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED": selector,
        "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED": False,
        "OPENSEARCH_ALLOW_ENGLISH_FALLBACK": False,
        "RETRIEVAL_PARENT_DIVERSITY_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    client = _Client([_hit(document, 30.0 - index) for index, document in enumerate(documents)])
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda _text: [0.0] * 4)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=_Runtime()))
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda message, *_: RetrievalQueryPlan([message, *queries]))
    return provider.retrieve(question, "NL", language, "fbo", "cid-w6")


def test_retrieve_sets_strong_local_match_for_the_dutch_question(monkeypatch) -> None:
    result = _retrieve(monkeypatch, DUTCH_QUESTION, _english_rows(), [DUTCH_PLANNER_QUERY, ENGLISH_PLANNER_QUERY])

    top = result.documents[0]
    assert result.metadata["evidence_selector_applied"] is True
    assert result.metadata["evidence_selector_confidence"] is None
    assert _document_relevance(DUTCH_QUESTION, top) < THRESHOLD, "fixture must reproduce the lexical miss"
    assert result.metadata["max_local_relevance"] == pytest.approx(_document_relevance(ENGLISH_PLANNER_QUERY, top), abs=1e-6)
    assert result.metadata["strong_local_match"] is True


# --- controls -------------------------------------------------------------------------


def test_same_language_question_keeps_its_value_even_with_a_rescuing_query(monkeypatch) -> None:
    question = "Can I use the logo on my business cards?"
    documents = _english_rows()
    result = _retrieve(monkeypatch, question, documents, ["Limited License to Use Company Marks"])

    top = result.documents[0]
    today = _document_relevance(question, top)
    assert today < THRESHOLD
    assert _document_relevance("Limited License to Use Company Marks", top) >= THRESHOLD
    assert result.metadata["max_local_relevance"] == pytest.approx(round(today, 6), abs=1e-6)
    assert result.metadata["strong_local_match"] is False


def test_same_language_question_already_passing_is_unchanged(monkeypatch) -> None:
    result = _retrieve(monkeypatch, ENGLISH_QUESTION, _english_rows(), [ENGLISH_PLANNER_QUERY])
    top = result.documents[0]
    assert result.metadata["max_local_relevance"] == pytest.approx(_document_relevance(ENGLISH_QUESTION, top), abs=1e-6)
    assert opensearch_sections._translated_query_local_relevance(
        ENGLISH_QUESTION, "NL", top, [ENGLISH_PLANNER_QUERY], [_row(d) for d in _english_rows()]
    ) == 0.0


def test_english_words_found_in_another_candidate_block_the_rescue() -> None:
    question = "Can I print the logo on cards?"
    documents = [
        _document("19.02", "en", EN_19_02),
        _document("20.01", "en", "FBOs may print business cards with approved artwork.", title="Business cards"),
    ]
    assert opensearch_sections._translated_query_local_relevance(
        question, "NL", documents[0], ["Limited License to Use Company Marks"], [_row(d) for d in documents]
    ) == 0.0


def test_irrelevant_section_is_not_rescued() -> None:
    documents = [
        _document("7.01", "en", "Retail customers may return products within thirty days of purchase.",
                  title="Product Returns"),
        _document("7.02", "en", "Refunds are issued to the original payment method.", TOP_SCORE - MARGIN,
                  title="Refunds"),
    ]
    relevance = _relevance(DUTCH_QUESTION, documents, [ENGLISH_PLANNER_QUERY])
    _, decision = _gate(DUTCH_QUESTION, documents, relevance, "en")
    assert relevance < THRESHOLD
    assert decision.approved is False


def test_only_a_translated_query_counts() -> None:
    documents = _english_rows()
    assert opensearch_sections._translated_query_local_relevance(
        DUTCH_QUESTION, "NL", documents[0], [DUTCH_PLANNER_QUERY], [_row(d) for d in documents]
    ) == 0.0


@pytest.mark.parametrize("country", ["US", "BE", "GLOBAL"])
def test_foreign_market_sections_are_never_rescued(country) -> None:
    documents = [_document("19.02-b", "en", EN_19_02_B, country=country)]
    assert opensearch_sections._translated_query_local_relevance(
        DUTCH_QUESTION, "NL", documents[0], [ENGLISH_PLANNER_QUERY], [_row(d) for d in documents]
    ) == 0.0
    _, decision = _gate(DUTCH_QUESTION, documents, 0.9, "en")
    assert decision.approved is False


@pytest.mark.parametrize("document_type", ["office_directory", "international_sponsoring_directory"])
def test_directory_records_are_unchanged(document_type) -> None:
    record = _document("sponsoring-080", "en", EN_19_02_B, access_scope="global", document_type=document_type)
    assert opensearch_sections._translated_query_local_relevance(
        DUTCH_QUESTION, "NL", record, [ENGLISH_PLANNER_QUERY], [_row(record)]
    ) == 0.0
    local_record = _document("sponsoring-080", "en", EN_19_02_B, document_type=document_type)
    assert opensearch_sections._translated_query_local_relevance(
        DUTCH_QUESTION, "NL", local_record, [ENGLISH_PLANNER_QUERY], [_row(local_record)]
    ) == 0.0


def test_without_the_selector_there_is_no_rescue(monkeypatch) -> None:
    result = _retrieve(monkeypatch, DUTCH_QUESTION, _english_rows(), [ENGLISH_PLANNER_QUERY], selector=False)
    assert result.metadata["evidence_selector_applied"] is False
    assert result.metadata["strong_local_match"] is False
    assert result.metadata["max_local_relevance"] == pytest.approx(
        _document_relevance(DUTCH_QUESTION, result.documents[0]), abs=1e-6
    )


def test_dutch_output_is_still_approved_and_its_value_unchanged(monkeypatch) -> None:
    dutch = [_document("19.02-b", "nl", NL_19_02_B), _document("19.02", "nl", "Beperkte licentie om bedrijfsmerken te gebruiken.")]
    result = _retrieve(monkeypatch, DUTCH_QUESTION, dutch, [ENGLISH_PLANNER_QUERY], language="nl")
    top = result.documents[0]
    assert result.metadata["max_local_relevance"] == pytest.approx(_document_relevance(DUTCH_QUESTION, top), abs=1e-6)
    assert result.metadata["strong_local_match"] is True

    relevance = _relevance(DUTCH_QUESTION, dutch, [ENGLISH_PLANNER_QUERY])
    _, decision = _gate(DUTCH_QUESTION, [_document("19.02-b", "nl", NL_19_02_B)], relevance, "nl")
    assert relevance == pytest.approx(0.513444)
    assert decision.approved is True

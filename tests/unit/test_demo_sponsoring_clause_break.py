"""Demo A2 (ORCH5 Fable finding 1): a line break or dash BEFORE the destination is not a clause end.

S2 made a newline, em dash, en dash and spaced hyphen end the sponsoring clause,
which correctly refuses "...sponsoring someone in Italy - what is Italy's
promoter commission?". It also refused wordings where the break sits between
the sponsoring word and its destination, e.g. "Company policy: can I
sponsor\\nsomeone in Italy?", which the reference answered from GLOBAL.

The clause may continue across one such break only when the text before the
break names no destination yet, and the next segment carries no policy word and
does not start a new question. A comma, full stop, question mark or conjunction
still always ends the clause.
"""

from __future__ import annotations

import pytest

from app import evidence
from app.evidence import approve_evidence
from app.retrieval.models import RetrievedDocument, RetrievalResult


def _document(doc_id: str, country: str, scope: str, document_type: str, score: float) -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id, title=doc_id, content="Sponsoring requirements and promoter commission.",
        source=f"s3://approved/{doc_id}", country=country, language="en", score=score,
        metadata={"access_scope": scope, "document_type": document_type, "status": "active"},
    )


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        documents=[
            _document("IT:4.01", "IT", "country", "policy", 0.95),
            _document("AT:4.01", "AT", "country", "policy", 0.9),
            _document("GLOBAL:sponsoring-italy", "GLOBAL", "global", "international_sponsoring_directory", 0.8),
        ],
        citations=[], confidence=0.9, metadata={},
    )


BREAK_BEFORE_DESTINATION = [
    "Company policy: can I sponsor\nsomeone in Italy?",
    "What is the company policy on sponsoring — someone in Italy?",
    "What is the company policy on sponsoring – someone in Italy?",
    "What is the company policy on sponsoring - someone in Italy?",
    "What is the company policy on sponsoring someone\nwho lives in Italy?",
]


@pytest.mark.parametrize("question", BREAK_BEFORE_DESTINATION)
def test_break_between_sponsoring_word_and_destination_answers_from_global(question) -> None:
    decision = approve_evidence(question, _retrieval(), "AT", "en")

    assert decision.approved is True
    assert decision.reason == "approved"
    assert [document.id for document in decision.evidence] == ["AT:4.01", "GLOBAL:sponsoring-italy"]
    assert evidence.is_mixed_sponsoring_policy_request(question, "AT") is True


@pytest.mark.parametrize(
    "question",
    [
        # Next segment claims the foreign policy.
        "Company policy: can I sponsor\nunder Italy's company policy?",
        "Can I sponsor —\nwhat does Italy's company policy say?",
        "What is the company policy on sponsoring - Italian company policy for someone?",
        # Next segment is a new question about a foreign policy fact.
        "What is the company policy on sponsoring — what is Italy's promoter commission?",
        "What is the company policy on sponsoring\nhow does Italy pay promoter commission?",
        # The destination was already named before the break (existing S2 rows).
        "What is the company policy on sponsoring someone in Italy — what is Italy's promoter commission?",
        "What is the company policy on sponsoring someone in Italy\nwhat is Italy's promoter commission?",
        # The policy noun itself is Italian.
        "What is the Italian company policy on sponsoring — someone in Italy?",
        # Only one break is crossed.
        "What is the company policy on sponsoring —\n— someone in Italy?",
    ],
)
def test_foreign_company_policy_after_a_break_is_still_refused(question) -> None:
    decision = approve_evidence(question, _retrieval(), "AT", "en")

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert decision.evidence == []

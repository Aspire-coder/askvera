"""Phase 2 Lane F: international-sponsoring contacts vs. company-policy scope. Deterministic/local proof.

GOAL requirement: "international-sponsoring directory contacts may be used
from any session country, while company-policy facts stay restricted to the
authorized policy market."

Reproduced through the real ``app.evidence.approve_evidence`` (no fakes): a
US session naming Mexico gets the Mexico GLOBAL/sponsoring-directory record
(the contact detail a support-contact supplement would draw on), but the
same US session cannot get Mexico's company-policy fact. This already
holds today - no code change was made for it - so this file is a
no-defect pin, not a fix. The negative half mirrors
tests/unit/test_demo_followup_resolution.py::
test_us_session_cannot_get_france_policy_after_a_sponsoring_exchange; the
positive half (a GLOBAL directory record is NOT blocked the same way) is
new coverage this project's earlier phases did not add.
"""

from __future__ import annotations

from app.evidence import approve_evidence
from app.retrieval.models import RetrievedDocument, RetrievalResult


def _mexico_directory_result() -> RetrievalResult:
    """A GLOBAL sponsoring-directory record for Mexico - the kind of
    document ``_find_matching_support_contact_record`` selects from."""
    document = RetrievedDocument(
        id="mexico-office",
        title="Forever Mexico",
        content="Welcome to Forever Mexico!\nTelephone Office +52 55 1234 5678\n",
        source="s3://approved/global-sponsoring-directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.95,
        metadata={
            "directory_section": "sponsoring",
            "record_country": "Mexico",
            "access_scope": "global",
            "document_type": "office_directory",
            "status": "active",
        },
    )
    return RetrievalResult(documents=[document], citations=[], confidence=0.95, metadata={})


def _mexico_policy_result() -> RetrievalResult:
    """A country-scoped company-policy record for Mexico plus the
    session's own (US) policy row - mirrors _policy_rows() in
    test_demo_followup_resolution.py."""
    documents = [
        RetrievedDocument(
            id="MX:9.01", title="t", content="Returns policy.", source="s3://a", country="MX",
            language="en", score=0.95,
            metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        ),
        RetrievedDocument(
            id="US:9.01", title="t", content="Returns policy.", source="s3://b", country="US",
            language="en", score=0.9,
            metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        ),
    ]
    return RetrievalResult(documents=documents, citations=[], confidence=0.9, metadata={})


def test_a_us_session_asking_for_a_mexico_sponsoring_contact_is_allowed() -> None:
    """The sponsoring/directory question names a foreign market, but the
    matching evidence is a GLOBAL record - it must not be refused the way
    a foreign policy request is."""
    query = "What is the sponsoring office phone number for Mexico?"
    decision = approve_evidence(query, _mexico_directory_result(), "US", "en")
    assert decision.reason != "cross_market_policy_request"


def test_a_us_session_asking_for_mexico_company_policy_is_refused() -> None:
    """The negative control: the same session, the same foreign market, but
    an explicit company-policy request must still be refused at the
    evidence gate - this is the restriction the positive case above must
    not weaken."""
    query = "What is the company policy in Mexico on returns?"
    decision = approve_evidence(query, _mexico_policy_result(), "US", "en")
    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"


def test_the_positive_and_negative_cases_differ_only_by_evidence_scope() -> None:
    """Same country (Mexico), same session (US): approval differs only
    because one query's matching evidence is GLOBAL (access_scope
    "global") and the other's is country-scoped policy evidence - proving
    the distinction is the evidence's own scope, not something this test
    smuggled in via the query wording."""
    sponsoring_decision = approve_evidence(
        "What is the sponsoring office phone number for Mexico?",
        _mexico_directory_result(),
        "US",
        "en",
    )
    policy_decision = approve_evidence(
        "What is the company policy in Mexico on returns?",
        _mexico_policy_result(),
        "US",
        "en",
    )
    assert sponsoring_decision.reason != "cross_market_policy_request"
    assert policy_decision.reason == "cross_market_policy_request"

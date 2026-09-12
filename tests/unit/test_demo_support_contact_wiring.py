"""Demo F: wire the B3 support-contact supplement helper into the orchestrator.

`_secure_and_complete_response` now receives the resolved request (follow-up
resolution's own query, not the raw user message) and, after the existing
field cleanup / order-size restoration / source-contradiction steps and
before the PII scrub, decides whether to append an approved support-contact
block: only when the delivered answer recommends contacting customer care,
and only when exactly one retrieved GLOBAL directory record's
``record_country`` matches a market named in the resolved request (or the
session market, when the request names none). It never falls back to "first
directory record", never duplicates an already-quoted phone/email, and never
fires for a refusal/fallback/guardrail answer.

Directory ``record_country`` values are not plain market names - e.g.
"Kenya/East Africa", "Netherlands Benelux" - so matching is by whole
segment/word, never substring: "Kenya" matches "Kenya/East Africa", but a
region word ("East Africa", "Benelux") or an unrelated country named only in
the record body (Belgium) must never match.

Demo K (owner decision 2026-09-12): South Sudan is served by the configured
Kenya/East Africa shared office (``shared_offices`` in
config/global_directory_markets.json), so it now matches that record.
"""

from __future__ import annotations

from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.cache_evidence import serialize_evidence
from app.retrieval.models import RetrievedDocument, RetrievalResult
from utils.validators import ChatRequest


class _FakeGovernance:
    """Never calls out to the network - the cached-path tests need only the
    orchestrator's own wiring, not a real governance decision."""

    def evaluate(self, *, text: str, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


def _identity_scrub(monkeypatch) -> None:
    # The Comprehend PII boundary is mocked in every test here, exactly as
    # the existing orchestrator tests do - the pipeline logic under test is
    # everything else, unchanged and real.
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)


def _kenya_document(record_id: str = "kenya-office", record_country: str = "Kenya/East Africa") -> RetrievedDocument:
    return RetrievedDocument(
        id=record_id,
        title="Forever Kenya/East Africa",
        content=(
            "Welcome to Forever Kenya/East Africa!\n"
            "Telephone Office +254 712 434 328\n"
            "Email info@forever-kenya.example\n"
        ),
        source="s3://approved/global-sponsoring-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_section": "sponsoring",
            "record_country": record_country,
            "access_scope": "global",
            "document_type": "office_directory",
            "ingestion_id": "v1",
            "directory_fields": {
                "Telephone Office": "+254 712 434 328",
                "Email": "info@forever-kenya.example",
            },
        },
    )


def _netherlands_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="nl-benelux-office",
        title="Forever Netherlands Benelux",
        content="Welcome to Forever Netherlands Benelux!\nTelephone Office +31 88 646 0200\n",
        source="s3://approved/global-sponsoring-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_section": "sponsoring",
            "record_country": "Netherlands Benelux",
            "access_scope": "global",
            "document_type": "office_directory",
            "ingestion_id": "v1",
            "directory_fields": {"Telephone Office": "+31 88 646 0200"},
        },
    )


def _care_answer() -> str:
    return "You are welcome to place an order directly. Please contact customer care for further help."


def _secure(orchestrator, response, retrieval_result, *, user_question, country, resolved_request=""):
    return orchestrator._secure_and_complete_response(
        response,
        retrieval_result,
        "en",
        "cid",
        user_question=user_question,
        country=country,
        resolved_request=resolved_request,
    )


def test_direct_answer_with_care_recommendation_and_matching_kenya_record_gets_supplement(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        resolved_request="Who do I contact about my Kenya order?",
    )

    assert completed.answer.startswith(_care_answer())
    assert "Telephone Office: +254 712 434 328" in completed.answer
    assert "Email: info@forever-kenya.example" in completed.answer
    assert completed.metadata["support_contact_supplemented"]["record_id"] == "kenya-office"
    assert any(source.get("uri") == document.source for source in completed.citations)


def test_no_matching_record_sets_unavailable_metadata_and_leaves_answer_unchanged(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my order?",
        country="US",
        resolved_request="Who do I contact about my Nigeria order?",
    )

    assert completed.answer == _care_answer()
    assert completed.metadata.get("support_contact_unavailable") is True
    assert "support_contact_supplemented" not in completed.metadata


def test_home_policy_answer_with_foreign_directory_record_gets_no_supplement(monkeypatch) -> None:
    """A home-market policy answer must not adopt a foreign office's record."""
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="What is the return policy?",
        country="US",
        resolved_request="What is the return policy?",
    )

    assert completed.answer == _care_answer()
    assert "Telephone Office" not in completed.answer


def test_resolved_followup_uses_resolved_request_market_not_raw_question(monkeypatch) -> None:
    """'Who do I contact?' after a Kenya question resolves to Kenya via resolved_request."""
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact?",
        country="US",
        resolved_request="What is the Kenya office phone number?\nFollow-up request: Who do I contact?",
    )

    assert "Telephone Office: +254 712 434 328" in completed.answer


def test_south_sudan_target_matches_configured_kenya_east_africa_shared_office(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact in South Sudan?",
        country="US",
        resolved_request="Who do I contact in South Sudan?",
    )

    assert "Telephone Office: +254 712 434 328" in completed.answer


def test_belgium_named_in_request_does_not_match_kenya_east_africa_record(monkeypatch) -> None:
    """Belgium is named only inside some sponsoring records' body text, never
    Kenya/East Africa's ``record_country`` - it must never match here."""
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact in Belgium?",
        country="US",
        resolved_request="Who do I contact in Belgium?",
    )

    assert "Telephone Office" not in completed.answer


def test_netherlands_benelux_record_country_matches_netherlands(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _netherlands_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact in the Netherlands?",
        country="US",
        resolved_request="Who do I contact in the Netherlands?",
    )

    assert "Telephone Office: +31 88 646 0200" in completed.answer


def test_answer_already_quoting_the_phone_is_not_duplicated(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = (
        "The Kenya office telephone is +254 712 434 328. "
        "Please contact customer care for further help."
    )
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="What is the Kenya office phone number?",
        country="KE",
        resolved_request="What is the Kenya office phone number?",
    )

    assert completed.answer == answer
    assert completed.answer.count("+254 712 434 328") == 1
    assert "support_contact_supplemented" not in completed.metadata


def test_answer_without_care_recommendation_adds_nothing(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = "Orders can be placed directly online at any time."
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="How do I place an order in Kenya?",
        country="KE",
        resolved_request="How do I place an order in Kenya?",
    )

    assert completed.answer == answer
    assert "support_contact_supplemented" not in completed.metadata
    assert "support_contact_unavailable" not in completed.metadata


def test_refusal_fallback_response_is_untouched(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = "I don't have enough information to answer that. Please contact customer care."
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.0, metadata={"fallback": True, "failure_layer": "evidence_contract"}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        resolved_request="Who do I contact about my Kenya order?",
    )

    assert completed.answer == answer
    assert "support_contact_supplemented" not in completed.metadata
    assert "support_contact_unavailable" not in completed.metadata


def test_two_different_matching_records_yields_no_supplement(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    first = _kenya_document(record_id="kenya-office-a")
    second = _kenya_document(record_id="kenya-office-b")
    response = ChatResponse(
        answer=_care_answer(), citations=[first.to_source(), second.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[first, second], citations=[first.to_source(), second.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        resolved_request="Who do I contact about my Kenya order?",
    )

    assert completed.answer == _care_answer()
    assert completed.metadata.get("support_contact_unavailable") is True


def test_personal_phone_not_in_any_record_is_still_scrubbed(monkeypatch) -> None:
    """The supplement wiring runs before the PII scrub, so an unrelated personal
    number that isn't backed by any approved record is still removed by the
    existing PII pipeline downstream - this step never protects it."""
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    personal_number = "+254 700 999 999"
    answer = f"You can also try my personal line at {personal_number}. Please contact customer care."
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)
    monkeypatch.setattr(
        chat_orchestrator,
        "scrub_pii",
        lambda text, *_, allowed_texts=(), **__: text.replace(personal_number, "[PHONE]")
        if personal_number not in "\n".join(allowed_texts) else text,
    )

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        resolved_request="Who do I contact about my Kenya order?",
    )

    assert personal_number not in completed.answer
    assert "Telephone Office: +254 712 434 328" in completed.answer


def test_remove_unrequested_directory_fields_does_not_delete_the_supplement(monkeypatch) -> None:
    """The supplement is appended after the unrequested-field cleanup pass
    already ran, so it is never a target of that pass in the same call."""
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = (
        "The delivery cost is 500 KES. Please contact customer care for further help."
    )
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="What is the delivery cost in Kenya?",
        country="KE",
        resolved_request="What is the delivery cost in Kenya?",
    )

    assert "Telephone Office: +254 712 434 328" in completed.answer
    assert "delivery cost" in completed.answer.lower()


def test_cached_path_parity_adds_supplement_for_resolved_market(monkeypatch) -> None:
    from app.retrieval import cache_evidence

    _identity_scrub(monkeypatch)
    monkeypatch.setattr(cache_evidence, "_active_generation_rows", lambda **_: [{"active_ingestion_id": "v1"}])
    orchestrator = AIOrchestrator(governance=_FakeGovernance())
    document = _kenya_document()
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)
    body = ChatRequest(message="Who do I contact?", sessionId="session-1", country="US", language="en")

    response = orchestrator._cached_response_value(
        {
            "response": _care_answer(),
            "sources": result.citations,
            "confidence": 0.8,
            "evidence": serialize_evidence(result),
        },
        body,
        "cid",
        cache_type="exact",
        resolved_request="What is the Kenya office phone number?\nFollow-up request: Who do I contact?",
    )

    assert response is not None
    assert "Telephone Office: +254 712 434 328" in response.answer
    assert response.metadata["support_contact_supplemented"]["record_id"] == "kenya-office"


def test_cached_path_does_not_borrow_another_markets_record(monkeypatch) -> None:
    """A cached answer for one market must never gain another market's record."""
    from app.retrieval import cache_evidence

    _identity_scrub(monkeypatch)
    monkeypatch.setattr(cache_evidence, "_active_generation_rows", lambda **_: [{"active_ingestion_id": "v1"}])
    orchestrator = AIOrchestrator(governance=_FakeGovernance())
    document = _kenya_document()
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)
    body = ChatRequest(message="Who do I contact?", sessionId="session-1", country="US", language="en")

    response = orchestrator._cached_response_value(
        {
            "response": _care_answer(),
            "sources": result.citations,
            "confidence": 0.8,
            "evidence": serialize_evidence(result),
        },
        body,
        "cid",
        cache_type="exact",
        resolved_request="What is the delivery cost in the Netherlands?",
    )

    assert response is not None
    assert "Telephone Office" not in response.answer
    assert response.metadata.get("support_contact_unavailable") is True

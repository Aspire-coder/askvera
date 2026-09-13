"""Demo W21: keep the support-contact supplement separate from the answer.

Two things were wrong with the block ``_apply_support_contact_supplement``
appends after an answer that recommends contacting customer care:

1. It was always rendered with the directory record's own (always-English)
   field labels, even when the answer itself was in French, German, Spanish
   or Dutch. W20 gave :func:`utils.directory_fields.build_support_contact_supplement`
   a reviewed ``language`` label table; the orchestrator simply never passed
   the request language it already has in scope.
2. Its citation was merged into the same flat list as the citations that
   support the answer proper, with nothing telling a reader (or the widget)
   that this source was cited only to back a contact detail appended
   *after* the answer, not to back any claim the answer makes.

This file pins both, plus the two guards that must keep holding: a
refusal/fallback answer never gets a supplement, and a contact the answer
already quotes is never repeated.

The citation marker is the camelCase key ``supportContactSupplement`` on the
source dict - camelCase to match the existing ``documentVersion`` /
``sectionTitle`` keys :meth:`RetrievedDocument.to_source` already emits, and
named after the existing ``support_contact_supplemented`` response-metadata
key and the ``build_support_contact_supplement`` helper so the three read as
one feature. It is added only to a citation the supplement itself
introduced: when the directory record is *already* cited by the answer, that
citation backs the answer too and is deliberately left unmarked.
"""

from __future__ import annotations

from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult

SUPPLEMENT_CITATION_MARKER = "supportContactSupplement"

PHONE = "+254 712 434 328"
EMAIL = "info@forever-kenya.example"


def _identity_scrub(monkeypatch) -> None:
    """Mock only the Comprehend PII boundary, exactly as the existing
    orchestrator support-contact tests do - everything else stays real."""
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)


def _kenya_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="kenya-office",
        title="Forever Kenya/East Africa",
        content=(
            "Welcome to Forever Kenya/East Africa!\n"
            f"Telephone Office {PHONE}\n"
            f"Email {EMAIL}\n"
        ),
        source="s3://approved/global-sponsoring-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_section": "sponsoring",
            "record_country": "Kenya/East Africa",
            "access_scope": "global",
            "document_type": "office_directory",
            "ingestion_id": "v1",
            "directory_fields": {
                "Telephone Office": PHONE,
                "Email": EMAIL,
            },
        },
    )


def _policy_document() -> RetrievedDocument:
    """A non-directory record: this is what the answer proper is built from."""
    return RetrievedDocument(
        id="returns-policy",
        title="Returns policy",
        content="Orders may be returned within 30 days.",
        source="s3://approved/returns-policy.pdf",
        country="GLOBAL",
        language="en",
        metadata={"ingestion_id": "v1"},
    )


def _care_answer() -> str:
    return "You are welcome to place an order directly. Please contact customer care for further help."


def _secure(orchestrator, response, retrieval_result, *, user_question, country, language="en", resolved_request=""):
    return orchestrator._secure_and_complete_response(
        response,
        retrieval_result,
        language,
        "cid",
        user_question=user_question,
        country=country,
        resolved_request=resolved_request,
    )


def _supplemented_answer(monkeypatch, language: str) -> str:
    """Run the eligible Kenya case in ``language`` and return the answer."""
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
        language=language,
        resolved_request="Who do I contact about my Kenya order?",
    )
    return completed.answer


# --------------------------------------------------------------------------
# 1. The block's labels follow the request language; its values never change.
# --------------------------------------------------------------------------

def test_french_request_renders_french_supplement_labels(monkeypatch) -> None:
    answer = _supplemented_answer(monkeypatch, "fr")
    assert f"Téléphone bureau: {PHONE}" in answer
    assert f"E-mail: {EMAIL}" in answer


def test_german_request_renders_german_supplement_labels(monkeypatch) -> None:
    answer = _supplemented_answer(monkeypatch, "de")
    assert f"Telefon Büro: {PHONE}" in answer
    assert f"E-Mail: {EMAIL}" in answer


def test_spanish_request_renders_spanish_supplement_labels(monkeypatch) -> None:
    answer = _supplemented_answer(monkeypatch, "es")
    assert f"Teléfono de oficina: {PHONE}" in answer
    assert f"Correo electrónico: {EMAIL}" in answer


def test_dutch_request_renders_dutch_supplement_labels(monkeypatch) -> None:
    answer = _supplemented_answer(monkeypatch, "nl")
    assert f"Telefoon kantoor: {PHONE}" in answer
    assert f"E-mail: {EMAIL}" in answer


def test_english_supplement_is_unchanged_by_the_language_threading(monkeypatch) -> None:
    """The default path must stay byte-identical to before - the record's own
    English labels, not a translation table entry."""
    answer = _supplemented_answer(monkeypatch, "en")
    assert f"Telephone Office: {PHONE}" in answer
    assert f"Email: {EMAIL}" in answer


def test_localized_labels_never_alter_the_approved_values(monkeypatch) -> None:
    """Only the introducing word changes across languages; every value is the
    same string the English case emits, character for character."""
    for language in ("fr", "de", "es", "nl", "it", "pt", "sv"):
        answer = _supplemented_answer(monkeypatch, language)
        assert PHONE in answer, language
        assert EMAIL in answer, language


def test_unknown_language_falls_back_to_the_records_english_labels(monkeypatch) -> None:
    answer = _supplemented_answer(monkeypatch, "ja")
    assert f"Telephone Office: {PHONE}" in answer


# --------------------------------------------------------------------------
# 2. The block stays visually separate from the answer it follows.
# --------------------------------------------------------------------------

def test_supplement_is_separated_from_the_answer_by_a_blank_line(monkeypatch) -> None:
    answer = _supplemented_answer(monkeypatch, "en")
    assert answer.startswith(_care_answer())
    supplement_start = answer.index("Telephone Office:")
    joining_text = answer[len(_care_answer()):supplement_start]
    # A blank line, and nothing else - the block must not run into the
    # answer's closing sentence, and no heading is introduced here.
    assert joining_text == "\n\n"
    assert "#" not in joining_text


# --------------------------------------------------------------------------
# 3. The supplement's citation is marked; the answer's own citations are not.
# --------------------------------------------------------------------------

def _run_with_separate_answer_citation(monkeypatch):
    """The answer is backed by a policy record; the directory record is only
    reached through the supplement, so its citation is the added one."""
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    directory = _kenya_document()
    policy = _policy_document()
    response = ChatResponse(
        answer=_care_answer(), citations=[policy.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(
        documents=[policy, directory],
        citations=[policy.to_source()],
        confidence=0.8,
    )
    return _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        resolved_request="Who do I contact about my Kenya order?",
    )


def test_supplement_citation_carries_the_supplementary_marker(monkeypatch) -> None:
    completed = _run_with_separate_answer_citation(monkeypatch)
    added = [c for c in completed.citations if c.get("uri") == _kenya_document().source]
    assert len(added) == 1
    assert added[0].get(SUPPLEMENT_CITATION_MARKER) is True


def test_the_main_answers_citations_do_not_carry_the_marker(monkeypatch) -> None:
    completed = _run_with_separate_answer_citation(monkeypatch)
    answer_citations = [c for c in completed.citations if c.get("uri") == _policy_document().source]
    assert answer_citations, "the answer's own citation must survive"
    for citation in answer_citations:
        assert SUPPLEMENT_CITATION_MARKER not in citation


def test_citations_remain_a_flat_list_of_dicts(monkeypatch) -> None:
    """Existing callers and tests expect a flat list - the marker is a field
    on a source, never a new nesting level or a separate collection."""
    completed = _run_with_separate_answer_citation(monkeypatch)
    assert isinstance(completed.citations, list)
    assert all(isinstance(citation, dict) for citation in completed.citations)
    assert len(completed.citations) == 2


def test_marking_does_not_mutate_the_documents_own_source(monkeypatch) -> None:
    """The marker is set on a copy: ``to_source()`` output elsewhere in the
    response must not acquire it as a side effect."""
    completed = _run_with_separate_answer_citation(monkeypatch)
    assert SUPPLEMENT_CITATION_MARKER not in _kenya_document().to_source()
    assert any(c.get(SUPPLEMENT_CITATION_MARKER) is True for c in completed.citations)


def test_record_already_cited_by_the_answer_is_not_marked_supplementary(monkeypatch) -> None:
    """When the answer itself already cites the directory record, that
    citation backs the answer as well - it must stay unmarked rather than be
    relabelled as contact-only."""
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

    assert f"Telephone Office: {PHONE}" in completed.answer
    assert len(completed.citations) == 1
    assert SUPPLEMENT_CITATION_MARKER not in completed.citations[0]


# --------------------------------------------------------------------------
# 4. The two existing guards still hold, in every language.
# --------------------------------------------------------------------------

def test_refusal_fallback_answer_gets_no_supplement_and_no_marker(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = "I don't have enough information to answer that. Please contact customer care."
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.0, metadata={"fallback": True, "failure_layer": "evidence_contract"},
        correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        language="fr",
        resolved_request="Who do I contact about my Kenya order?",
    )

    assert completed.answer == answer
    assert "Telephone Office" not in completed.answer
    assert "Téléphone bureau" not in completed.answer
    assert "support_contact_supplemented" not in completed.metadata
    assert all(SUPPLEMENT_CITATION_MARKER not in citation for citation in completed.citations)


def test_guardrail_response_source_gets_no_supplement(monkeypatch) -> None:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = "I cannot help with that request. Please contact customer care."
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.0, metadata={"response_source": "guardrail"}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        language="de",
        resolved_request="Who do I contact about my Kenya order?",
    )

    assert completed.answer == answer
    assert "Telefon Büro" not in completed.answer
    assert "support_contact_supplemented" not in completed.metadata


def test_contact_already_quoted_is_not_repeated_in_a_localized_run(monkeypatch) -> None:
    """The duplicate guard compares VALUES, so it must keep holding when the
    labels are localized - the phone is quoted once, and no block is added."""
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document()
    answer = f"Le téléphone du bureau du Kenya est {PHONE}. Veuillez contacter customer care."
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)

    completed = _secure(
        orchestrator, response, result,
        user_question="Quel est le numéro de téléphone du bureau du Kenya ?",
        country="KE",
        language="fr",
        resolved_request="Quel est le numéro de téléphone du bureau du Kenya ?",
    )

    assert completed.answer.count(PHONE) == 1
    assert "Téléphone bureau:" not in completed.answer
    assert "support_contact_supplemented" not in completed.metadata
    assert all(SUPPLEMENT_CITATION_MARKER not in citation for citation in completed.citations)

"""Phase 2 Lane F: two reproduced defects, wired into the orchestrator. Mocked dependency behaviour.

Both run through the REAL ``AIOrchestrator._secure_and_complete_response``,
mocking only the Comprehend PII boundary, as
tests/unit/test_demo_contact_supplement_separation.py does.

1. A care recommendation in a non-English answer got no contact supplement:
   _CARE_CONTACT_RECOMMENDATION_RE is English-only.
2. A fax-only approved record was dropped silently.

The fixes are in ``app/response/contact_completion.py``. The coordinator wired
them into ``_apply_support_contact_supplement`` from Lane F's patch
(``docs/conversation-quality/phase2/patches/laneF-multilingual-and-fax-contact.patch``,
applied after normalizing its CRLF line endings). These tests were strict
xfails on Lane F's branch and pass on the integrated candidate.
"""

from __future__ import annotations

import pytest

from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult

PHONE = "+254 712 434 328"
EMAIL = "info@forever-kenya.example"
FAX = "+254 20 999999"


def _identity_scrub(monkeypatch) -> None:
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)


def _kenya_document(directory_fields: dict[str, str]) -> RetrievedDocument:
    body_lines = "\n".join(f"{label} {value}" for label, value in directory_fields.items())
    return RetrievedDocument(
        id="kenya-office",
        title="Forever Kenya/East Africa",
        content=f"Welcome to Forever Kenya/East Africa!\n{body_lines}\n",
        source="s3://approved/global-sponsoring-directory.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_section": "sponsoring",
            "record_country": "Kenya/East Africa",
            "access_scope": "global",
            "document_type": "office_directory",
            "ingestion_id": "v1",
            "directory_fields": directory_fields,
        },
    )


def _run(monkeypatch, *, answer: str, directory_fields: dict[str, str], language: str) -> ChatResponse:
    _identity_scrub(monkeypatch)
    orchestrator = AIOrchestrator()
    document = _kenya_document(directory_fields)
    response = ChatResponse(
        answer=answer, citations=[document.to_source()], suggestions=[], cards=[],
        confidence=0.8, metadata={}, correlation_id="cid",
    )
    result = RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)
    return orchestrator._secure_and_complete_response(
        response, result, language, "cid",
        user_question="Who do I contact about my Kenya order?",
        country="KE",
        resolved_request="Who do I contact about my Kenya order?",
    )


# --------------------------------------------------------------------------
# Defect 1: "recommends contact" detection was English-only.
# --------------------------------------------------------------------------

_MULTILINGUAL_CARE_ANSWERS = {
    "fr": "Vous pouvez commander directement. Veuillez contacter le service client pour plus d'aide.",
    "de": "Sie können direkt bestellen. Bitte wenden Sie sich an den Kundenservice für weitere Hilfe.",
    "es": "Puede realizar el pedido directamente. Por favor, póngase en contacto con atención al cliente.",
    "nl": "U kunt direct bestellen. Neem contact op met de klantenservice voor meer hulp.",
    "it": "Può ordinare direttamente. La preghiamo di contattare il servizio clienti per ulteriore assistenza.",
    "pt": "Você pode fazer o pedido diretamente. Entre em contato com o atendimento ao cliente para mais ajuda.",
    "fi": "Voit tilata suoraan. Ota yhteyttä asiakaspalveluun saadaksesi lisää apua.",
    "sv": "Du kan beställa direkt. Kontakta kundtjänsten för mer hjälp.",
    "no": "Du kan bestille direkte. Kontakt kundeservice for mer hjelp.",
}


@pytest.mark.parametrize("language", sorted(_MULTILINGUAL_CARE_ANSWERS))
def test_a_non_english_care_recommendation_gets_the_supplement(monkeypatch, language: str) -> None:
    completed = _run(
        monkeypatch,
        answer=_MULTILINGUAL_CARE_ANSWERS[language],
        directory_fields={"Telephone Office": PHONE, "Email": EMAIL},
        language=language,
    )
    assert "support_contact_supplemented" in completed.metadata
    assert PHONE in completed.answer
    assert EMAIL in completed.answer


# --------------------------------------------------------------------------
# Defect 2: a fax-only approved record was silently dropped.
# --------------------------------------------------------------------------


def test_a_fax_only_record_is_offered_when_the_answer_recommends_care(monkeypatch) -> None:
    completed = _run(
        monkeypatch,
        answer="You are welcome to place an order directly. Please contact customer care for further help.",
        directory_fields={"Fax": FAX},
        language="en",
    )
    assert "support_contact_supplemented" in completed.metadata
    assert FAX in completed.answer
    assert completed.metadata["support_contact_supplemented"]["labels"] == ["Fax"]


def test_the_fax_fallback_still_never_beats_a_real_phone_end_to_end(monkeypatch) -> None:
    """No-defect-pinned, not part of the patch: today's code already calls
    ``build_support_contact_supplement`` directly, which already prefers a
    real phone over a fax in the same record, so this already passes
    end-to-end. Recorded here (rather than only in the pure unit test) so
    that once the patch swaps in ``build_contact_supplement_with_fax_fallback``,
    this end-to-end guarantee is proven to still hold, not just assumed."""
    completed = _run(
        monkeypatch,
        answer="You are welcome to place an order directly. Please contact customer care for further help.",
        directory_fields={"Fax": FAX, "Telephone Office": PHONE},
        language="en",
    )
    assert PHONE in completed.answer
    assert FAX not in completed.answer

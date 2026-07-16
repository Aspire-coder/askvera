"""Tests for locale-aware non-document routing and generic evidence approval."""

from app.evidence import approve_evidence, assistant_meta_response, classify_intent, localized_conversation_response
from app.retrieval.models import RetrievedDocument, RetrievalResult


def test_routes_configured_english_greeting_without_retrieval() -> None:
    assert classify_intent("Hello!", "en") == "assistant_meta"


def test_routes_configured_french_greeting_without_retrieval() -> None:
    assert classify_intent("Bonjour", "fr-CA") == "assistant_meta"


def test_routes_substantive_french_question_to_document_grounded_flow() -> None:
    assert classify_intent("Quelles sont les conditions pour devenir Manager?", "fr-CA") == "policy_fact"


def test_routes_unknown_language_to_document_grounded_flow() -> None:
    assert classify_intent("Wie werde ich Manager?", "de") == "policy_fact"


def test_routes_launched_language_greetings_without_model_tokens() -> None:
    assert classify_intent("Hallo", "de-DE") == "assistant_meta"
    assert classify_intent("Hola", "es-US") == "assistant_meta"
    assert classify_intent("Hoi", "nl-BE") == "assistant_meta"
    assert "AskVera" in (assistant_meta_response("Hola", "es") or "")


def test_localized_fallback_uses_selected_language() -> None:
    assert "documents de politique approuvés" in (
        localized_conversation_response("insufficient_evidence", "fr-CA") or ""
    )


def test_fallback_explains_that_approved_documents_lack_enough_information() -> None:
    fallback = localized_conversation_response("insufficient_evidence", "en") or ""
    assert "approved policy documents" in fallback
    assert "do not contain enough information" in fallback


def test_global_document_is_valid_evidence_for_every_locale() -> None:
    document = RetrievedDocument(
        id="global-office",
        title="International Office Directory - Mexico",
        content="Mexico office contact details",
        source="s3://approved/global-directory.pdf",
        country="GLOBAL",
        language="en",
        score=0.9,
        metadata={"access_scope": "global", "directory_section": "office"},
    )
    retrieval_result = RetrievalResult(
        documents=[document],
        citations=[document.to_source()],
        confidence=0.9,
    )

    decision = approve_evidence(
        "Quelles sont les coordonnées du bureau du Mexique?",
        retrieval_result,
        "CA",
        "fr",
    )

    assert decision.approved

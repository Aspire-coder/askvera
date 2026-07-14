"""Tests for locale-aware non-document routing and generic evidence approval."""

from app.evidence import classify_intent


def test_routes_configured_english_greeting_without_retrieval() -> None:
    assert classify_intent("Hello!", "en") == "assistant_meta"


def test_routes_configured_french_greeting_without_retrieval() -> None:
    assert classify_intent("Bonjour", "fr-CA") == "assistant_meta"


def test_routes_substantive_french_question_to_document_grounded_flow() -> None:
    assert classify_intent("Quelles sont les conditions pour devenir Manager?", "fr-CA") == "policy_fact"


def test_routes_unknown_language_to_document_grounded_flow() -> None:
    assert classify_intent("Wie werde ich Manager?", "de") == "policy_fact"

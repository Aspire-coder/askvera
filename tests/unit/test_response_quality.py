"""Cross-market regression coverage for final response quality controls."""

import json
from pathlib import Path

from app.evidence import assistant_meta_response, classify_intent
from app.response.models import ChatResponse
from app.response.quality import (
    contains_internal_retrieval_language,
    contains_unresolved_placeholder,
    contact_for_country,
    has_incomplete_ending,
    remove_or_replace_contact_placeholders,
    unsupported_requested_years,
)
from app.retrieval.models import RetrievedDocument
from app.validation.models import ValidationContext, ValidationResult
from app.validation.validators.output_integrity_validator import OutputIntegrityValidator


def _document(country: str, effective_date: str = "2026-05-01") -> RetrievedDocument:
    return RetrievedDocument(
        id=f"policy-{country.lower()}",
        title=f"{country} policy",
        content="This approved policy is effective May 1, 2026.",
        source=f"s3://approved/{country.lower()}/policy.pdf",
        document_version="2026.1",
        country=country,
        language="en",
        metadata={"effective_date": effective_date},
    )


def test_us_reviewed_contacts_replace_known_placeholders() -> None:
    answer, changes = remove_or_replace_contact_placeholders(
        "Call **** or visit [URL].",
        "US",
    )

    assert answer == "Call (888) 440-ALOE (2563) or visit www.foreverliving.com."
    assert changes == ["phone_replaced", "website_replaced"]
    assert contains_unresolved_placeholder(answer) is False


def test_non_us_markets_never_inherit_us_phone() -> None:
    markets = json.loads((Path(__file__).parents[2] / "config" / "markets.json").read_text(encoding="utf-8"))[
        "markets"
    ]
    for market in markets:
        country = market["code"]
        answer, _ = remove_or_replace_contact_placeholders("Customer Care: [PHONE]", country)
        if country == "US":
            assert "(888) 440-ALOE (2563)" in answer
        else:
            assert "(888) 440-ALOE (2563)" not in answer
            assert "[PHONE]" not in answer
        assert contact_for_country(country).get("website") == "www.foreverliving.com"


def test_english_small_talk_is_consistent_in_every_configured_market() -> None:
    markets = json.loads((Path(__file__).parents[2] / "config" / "markets.json").read_text(encoding="utf-8"))[
        "markets"
    ]
    for market in markets:
        assert classify_intent("hello", market["defaultLanguage"]) == "assistant_meta"
        assert classify_intent("hello, how are you?", market["defaultLanguage"]) == "assistant_meta"
        assert classify_intent("what's your name?", market["defaultLanguage"]) == "assistant_meta"
        assert classify_intent("tell me a joke", market["defaultLanguage"]) == "assistant_meta"
        assert assistant_meta_response("hello", market["defaultLanguage"])


def test_explicit_period_outside_document_metadata_is_blocked_without_hardcoded_year() -> None:
    assert unsupported_requested_years("What policy changes apply in 2027?", [_document("US")]) == [2027]
    assert unsupported_requested_years("What changed in 2026?", [_document("US")]) == []
    assert unsupported_requested_years("What changed in 2031?", [_document("IT", "2031-02-01")]) == []


def test_undated_evidence_keeps_normal_evidence_contract_in_control() -> None:
    document = _document("GB", "")
    document = RetrievedDocument(**{**document.__dict__, "document_version": "", "content": "Approved policy text."})
    assert unsupported_requested_years("What applies in 2027?", [document]) == []


def test_incomplete_sentence_and_placeholder_are_critical() -> None:
    response = ChatResponse(
        answer="No, you cannot sponsor new FBOs in the.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={},
        correlation_id="cid",
    )
    result = ValidationResult()
    OutputIntegrityValidator().validate(
        ValidationContext(
            chat_response=response,
            correlation_id="cid",
            country="US",
            language="en",
            role="new_prospect",
        ),
        result,
    )

    assert has_incomplete_ending(response.answer, "en") is True
    assert {issue.code for issue in result.issues} == {"INCOMPLETE_OUTPUT"}


def test_complete_sentence_is_not_rejected() -> None:
    assert has_incomplete_ending("No, you cannot sponsor new FBOs in the United States.", "en") is False
    assert contains_unresolved_placeholder("Visit www.foreverliving.com.") is False


def test_known_truncated_endings_are_rejected_without_blocking_complete_sentences() -> None:
    assert has_incomplete_ending("You can enroll online at.", "en") is True
    assert has_incomplete_ending("The requirements include.", "en") is True
    assert has_incomplete_ending("Complete the form in the", "en") is True
    assert has_incomplete_ending("You can enroll online at foreverliving.com.", "en") is False


def test_internal_retrieval_language_is_not_customer_safe() -> None:
    assert contains_internal_retrieval_language("The retrieved directory records do not show a date.") is True
    assert contains_internal_retrieval_language("The retrieved authorised chunks do not show a price.") is True
    assert contains_internal_retrieval_language("The approved policy does not show a date.") is False


def test_output_validator_rejects_any_remaining_contact_placeholder() -> None:
    response = ChatResponse(
        answer="Visit <URL> for details.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={},
        correlation_id="cid",
    )
    result = ValidationResult()
    OutputIntegrityValidator().validate(
        ValidationContext(
            chat_response=response,
            correlation_id="cid",
            country="IT",
            language="it",
            role="new_prospect",
        ),
        result,
    )

    assert {issue.code for issue in result.issues} == {"UNRESOLVED_OUTPUT_PLACEHOLDER"}

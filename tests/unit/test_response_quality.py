"""Cross-market regression coverage for final response quality controls."""

import json

import pytest
from pathlib import Path

from app.evidence import assistant_meta_response, classify_intent
from app.response.models import ChatResponse
from app.response.quality import (
    contains_internal_retrieval_language,
    contains_unresolved_placeholder,
    contact_for_country,
    has_incomplete_ending,
    incomplete_ending_reason,
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


@pytest.mark.parametrize("answer", [
    "To qualify you must:\n\na) Generate 120 Case Credits\nb) Maintain Active status\n"
    "c) Be the only Manager in your Downline.\n\nWould you like to know more?",
    "Requirements (see Section 5.01):\n\na) 120 Case Credits\nb) Active status\n"
    "c) Sole Manager\nd) Two consecutive months.\n\nAnything else I can help with?",
])
def test_enumeration_markers_are_not_read_as_truncation(answer) -> None:
    """"a) b) c)" is a list, not a broken parenthesis.

    Measured on the deployed build: "How can i become a recognized manager?"
    abstained 2 times in 12, every failure on this check, with counts such as
    zero "(" against three ")". The answers were complete, correct and cited,
    ending in a normal closing question, and were replaced by "the approved
    policy documents do not contain enough information". Policy answers
    enumerate requirements constantly, so this affected the bot's core job.
    """
    assert not has_incomplete_ending(answer, "en")


@pytest.mark.parametrize("answer", [
    "You must generate 120 Case Credits. (There is an exception: if a Downline FBO",
    "See the table [Section 5.01 for the",
])
def test_an_unclosed_opener_is_still_truncation(answer) -> None:
    """Only surplus closers are excused; an unclosed opener still fails."""
    assert has_incomplete_ending(answer, "en")


def test_incomplete_ending_reason_names_the_rule_that_fired():
    """Rejecting an answer must leave something to diagnose.

    The rejected text is never logged, so "INCOMPLETE_OUTPUT" on its own gave
    no way to tell an unclosed bracket from a dangling word - which is why the
    Algeria minimum-order failure stayed unexplained across several deploys
    despite correct retrieval and approved evidence.
    """
    assert incomplete_ending_reason("Order (2 CC minimum", "en") == "unclosed_paren:1>0"
    assert incomplete_ending_reason("See [the table", "en") == "unclosed_bracket:1>0"
    assert incomplete_ending_reason("You can enroll online at.", "en") == "dangling_word:at."
    assert incomplete_ending_reason("", "en") == "empty"
    assert incomplete_ending_reason("The minimum order is 2 Case Credits.", "en") is None


def test_incomplete_ending_reason_reports_no_answer_text():
    """Every reason comes from a fixed vocabulary or a count, never the answer."""
    reason = incomplete_ending_reason(
        "Contact Ms Dupont on +213 55 12 34 56 about the (", "en"
    )
    assert reason == "unclosed_paren:1>0"
    assert "Dupont" not in reason and "213" not in reason


def test_non_english_answers_are_not_judged_by_the_english_word_rule():
    """The trailing-word list is English; applying it elsewhere is a coin toss."""
    assert incomplete_ending_reason("Le montant minimum est de 2 CC.", "fr") is None
    # Bracket balance is language-independent and still applies.
    assert incomplete_ending_reason("Le montant (minimum", "fr") == "unclosed_paren:1>0"


def test_truncation_verdict_is_logged_with_the_reported_stop_reason():
    """The heuristic verdict and Bedrock's own stop reason must arrive together.

    "INCOMPLETE_OUTPUT" is a reading of the text; stopReason "max_tokens" is
    the model stating it ran out of room. A truly truncated answer needs a
    bigger budget, a misjudged one needs a better rule, and the two are
    indistinguishable from the text alone - which is how the Algeria case
    stayed unexplained.
    """
    import inspect

    from app.orchestrator import chat_orchestrator

    source = inspect.getsource(chat_orchestrator.AIOrchestrator._validate_response)
    assert "finish_reason=" in source
    assert "output_tokens=" in source
    assert "max_output_tokens=" in source


def test_every_answer_editing_step_is_named_in_the_diagnostic_flag_list():
    """A step that edits the answer must appear in _ANSWER_EDIT_FLAGS.

    Nine steps run between generation and validation and several delete text.
    When one of them leaves an answer malformed, the validator discards the
    whole thing and tells the reader the documents do not cover their question.
    The flag list is how that gets traced back to a step, so a new editor that
    is missing from it is invisible exactly when something goes wrong.
    """
    import inspect
    import re

    from app.orchestrator import chat_orchestrator

    source = inspect.getsource(chat_orchestrator.AIOrchestrator._secure_and_complete_response)
    # Every _replace_answer call passes a metadata dict of flags it records.
    recorded = set(re.findall(r'\{"(\w+)":', source))
    missing = recorded - set(chat_orchestrator._ANSWER_EDIT_FLAGS)
    assert not missing, f"answer-editing flags missing from _ANSWER_EDIT_FLAGS: {sorted(missing)}"

"""CX phase 3, Lane 8: compose_cx_response.

docs/conversation-quality/phase3/CX_LANES.md,
docs/conversation-quality/phase3/CX_LANE8_COMPOSE.md. Uses real
``ChatResponse``/``ConversationOutcome`` objects, the real Lane 4 renderer
(``app.response.cx_render.render`` -- every language exercised here is one
of the 12 reviewed CX locales, so no Bedrock translation call is ever due;
``localize_reviewed_copy`` is monkeypatched to raise if that assumption ever
breaks, keeping this file offline per the project's OFFLINE ONLY rule) and a
temporary ``public_contacts.json`` fixture (never the real one, whose only
configured market is US).
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.response import cx_render
from app.response.cx_compose import compose_cx_response
from app.response.models import ChatResponse
from app.response.outcome import ConversationOutcome, OutcomeKind
from app.response.quality import _public_contacts
from app.retrieval.models import RetrievedDocument

# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _offline_translator_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly (rather than reach Bedrock) if translation is ever hit.

    Every language exercised in this file is one of the 12 reviewed CX
    locales in config/conversation_routes.json, so app.response.cx_render's
    real ``render`` never needs ``localize_reviewed_copy`` here.
    """

    def _forbidden(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("localize_reviewed_copy must not be called for a reviewed CX locale")

    monkeypatch.setattr(cx_render, "localize_reviewed_copy", _forbidden)


@pytest.fixture(autouse=True)
def _public_contacts_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "version": 1,
        "default": {},
        "countries": {
            "US": {"customerCarePhone": "1-800-555-0100", "website": "www.example-forever.com"},
            "KE": {"customerCarePhone": "+254 20 2026869", "website": "www.example-forever.com/ke"},
            # DE deliberately has no reviewed contact and no "default" to
            # fall back to, for the "no reviewed contact" cases.
        },
    }
    contacts_path = tmp_path / "public_contacts.json"
    contacts_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("PUBLIC_CONTACTS_PATH", str(contacts_path))
    _public_contacts.cache_clear()
    yield
    _public_contacts.cache_clear()


# --- Builders ----------------------------------------------------------------


def _outcome(
    kind: OutcomeKind,
    *,
    country: str = "US",
    language: str = "en",
    fields_requested: frozenset[str] = frozenset(),
    fields_answered: frozenset[str] = frozenset(),
    fields_unsupported: frozenset[str] = frozenset(),
    directory_target: str | None = None,
    failure_layer: str | None = None,
) -> ConversationOutcome:
    return ConversationOutcome(
        kind=kind,
        language=language,
        country=country,
        fields_requested=fields_requested,
        fields_answered=fields_answered,
        fields_unsupported=fields_unsupported,
        directory_target=directory_target,
        clarification_subject=None,
        failure_layer=failure_layer,
        retrieval_availability=None,
    )


def _response(
    answer: str,
    *,
    metadata: dict[str, object] | None = None,
    citations: list[dict[str, object]] | None = None,
) -> ChatResponse:
    return ChatResponse(
        answer=answer,
        citations=citations if citations is not None else [{"title": "Some policy"}],
        suggestions=[],
        cards=[],
        confidence=0.9,
        metadata=dict(metadata or {}),
        correlation_id="corr-1",
    )


def _kenya_document(directory_fields: dict[str, str]) -> RetrievedDocument:
    return RetrievedDocument(
        id="directory-kenya",
        title="Kenya directory",
        content="\n".join(f"{label}: {value}" for label, value in directory_fields.items()),
        source="s3://approved/directory/kenya.pdf",
        country="GLOBAL",
        language="en",
        metadata={
            "directory_kind": "international_sponsoring",
            "record_country": "Kenya",
            "directory_fields": directory_fields,
        },
    )


def _no_topics(_topic: str, _country: str) -> bool:
    return False


def _all_topics(_topic: str, _country: str) -> bool:
    return True


_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def _compose(
    response: ChatResponse,
    outcome: ConversationOutcome,
    *,
    question: str = "What is the minimum order policy?",
    language: str = "en",
    country: str = "US",
    evidence_documents: list[RetrievedDocument] | None = None,
    topic_supported=_no_topics,
):
    return compose_cx_response(
        response,
        outcome,
        question=question,
        language=language,
        country=country,
        evidence_documents=evidence_documents or [],
        topic_supported=topic_supported,
        render=cx_render.render,
    )


# --- clarification / safety_refusal: never any addition ---------------------


@pytest.mark.parametrize("kind", [OutcomeKind.CLARIFICATION, OutcomeKind.SAFETY_REFUSAL])
@pytest.mark.parametrize("language", ["en", "es", "fr", "de", "fi"])
def test_clarification_and_refusal_get_no_addition_of_any_kind(kind: OutcomeKind, language: str) -> None:
    # An answer text that would otherwise trigger EVERY addition type, plus a
    # metadata dict already carrying an "outcome" key this must never touch.
    answer = "Certainly! Please contact customer care. My balance question stays unanswered."
    response = _response(answer, metadata={"outcome": {"kind": "should-not-change"}})
    outcome = _outcome(kind, language=language, fields_unsupported=frozenset({"email"}))

    result, applied = _compose(
        response, outcome, language=language, topic_supported=_all_topics,
        question="Did my commission arrive? What is my balance?",
    )

    assert result is response
    assert applied == {"cx_applied": []}
    assert result.metadata == {"outcome": {"kind": "should-not-change"}}
    assert result.suggestions == []


# --- guardrail / client_action / governance metadata: nothing added --------


@pytest.mark.parametrize("response_source", ["guardrail", "client_action"])
def test_nothing_added_when_response_source_is_suppressed(response_source: str) -> None:
    response = _response("Please contact customer care.", metadata={"response_source": response_source})
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING)

    result, applied = _compose(response, outcome)

    assert result is response
    assert applied == {"cx_applied": []}


@pytest.mark.parametrize("failure_layer", ["local_guardrail", "risk_policy", "aws_guardrail", "sensitive_pii_input"])
def test_nothing_added_when_a_governance_or_pii_failure_layer_is_set(failure_layer: str) -> None:
    # Deliberately paired with OutcomeKind.ANSWER (not the SAFETY_REFUSAL an
    # honest pipeline would produce) to prove this is an independent,
    # defensive metadata check, not just a restatement of the kind gate.
    response = _response("Some answer text.", metadata={"failure_layer": failure_layer})
    outcome = _outcome(OutcomeKind.ANSWER)

    result, applied = _compose(response, outcome)

    assert result is response
    assert applied == {"cx_applied": []}


# --- answer: preamble stripped, no gap, suggestions only when supported ----


def test_full_coverage_answer_strips_preamble_and_updates_metadata_only() -> None:
    response = _response(
        "Certainly! The minimum order is 50 CV.",
        metadata={"failure_layer": None, "unrelated_key": "kept"},
    )
    outcome = _outcome(OutcomeKind.ANSWER)

    result, applied = _compose(response, outcome, topic_supported=_no_topics)

    assert result.answer == "The minimum order is 50 CV."
    assert applied == {"cx_applied": ["preamble_stripped"]}
    assert result.metadata["unrelated_key"] == "kept"
    assert result.metadata["outcome"] == outcome.to_metadata()
    assert result.citations == response.citations
    assert result.suggestions == []


def test_full_coverage_answer_with_supported_topics_gets_suggestions_not_appended_to_text() -> None:
    response = _response("The minimum order is 50 CV.")
    outcome = _outcome(OutcomeKind.ANSWER, fields_requested=frozenset())

    result, applied = _compose(response, outcome, topic_supported=_all_topics)

    assert result.answer == "The minimum order is 50 CV."  # never appended to the text
    assert "suggestions" in applied["cx_applied"]
    assert len(result.suggestions) == 2
    for item in result.suggestions:
        assert item["type"] == "follow_up"
        assert item["key"].startswith("suggest_topic_")
        assert item["text"]  # localized, non-empty
        assert not _PLACEHOLDER_RE.search(item["text"])


# --- partial answer: real unsupported field, localized note, kind promoted -


@pytest.mark.parametrize(
    "language,question,expected_label_fragment",
    [
        ("en", "What is the phone number and email?", "email"),
        ("es", "¿Cuál es el teléfono y el correo electrónico?", "correo"),
        ("fr", "Quel est le téléphone et l'e-mail ?", "mail"),
        ("de", "Wie lautet die Telefonnummer und die E-Mail?", "mail"),
        ("fi", "Mikä on puhelin ja sähköposti?", "posti"),
    ],
)
def test_partial_answer_note_is_localized_and_promotes_the_outcome(
    language: str, question: str, expected_label_fragment: str
) -> None:
    document = _kenya_document({"Telephone Office": "+254 20 2026869"})
    answer = "You can reach the Kenya office at +254 20 2026869."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.ANSWER, country="KE", language=language)

    result, applied = _compose(
        response,
        outcome,
        question=question,
        language=language,
        country="KE",
        evidence_documents=[document],
    )

    assert "partial_note" in applied["cx_applied"]
    assert answer in result.answer
    paragraphs = result.answer.split("\n\n")
    assert len(paragraphs) >= 2
    assert expected_label_fragment.lower() in paragraphs[-1].lower() or any(
        expected_label_fragment.lower() in p.lower() for p in paragraphs[1:]
    )
    assert result.metadata["outcome"]["kind"] == "partial_answer"
    assert result.metadata["outcome"]["fields_unsupported"] == ["email"]
    assert result.metadata["outcome"]["fields_answered"] == ["phone"]


def test_partial_answer_note_never_duplicated_when_multiple_fields_unsupported() -> None:
    document = _kenya_document({"Telephone Office": "+254 20 2026869"})
    answer = "You can reach the Kenya office at +254 20 2026869."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.ANSWER, country="KE")

    result, applied = _compose(
        response,
        outcome,
        question="What is the phone number, email and website?",
        country="KE",
        evidence_documents=[document],
    )

    assert applied["cx_applied"].count("partial_note") == 1
    assert result.metadata["outcome"]["fields_unsupported"] == ["email", "website"]


# --- personal account note: answer stays, note appended once ---------------


@pytest.mark.parametrize(
    "language,question",
    [
        ("en", "Did my commission arrive yet? Also, how is the commission calculated?"),
        ("es", "¿Cuál es mi saldo? También, ¿cómo se calcula la comisión?"),
        ("fr", "Quel est mon solde ? Aussi, comment la commission est-elle calculée ?"),
        ("de", "Wie hoch ist mein Kontostand? Wie wird die Provision berechnet?"),
        ("fi", "Missä tilaukseni on? Miten toimitusaika lasketaan?"),
    ],
)
def test_personal_account_note_appended_once_alongside_the_real_answer(language: str, question: str) -> None:
    answer = "Commissions are calculated monthly based on approved CV."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.ANSWER, language=language)

    result, applied = _compose(response, outcome, question=question, language=language)

    assert applied["cx_applied"].count("personal_account_limit") == 1
    assert answer in result.answer  # the answer is never removed -- not a refusal
    assert result.answer != answer  # something was appended


def test_personal_account_note_never_fires_for_the_personal_account_fallback_kind() -> None:
    # OutcomeKind.PERSONAL_ACCOUNT is a fallback kind whose own reviewed copy
    # is left untouched -- the personal_account_limit note itself is only
    # ever ADDED alongside a real generated answer (answer-shaped kinds).
    answer = "I can't look up personal account, order or earnings details."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.PERSONAL_ACCOUNT)

    result, applied = _compose(response, outcome, question="Did my commission arrive yet?")

    assert "personal_account_limit" not in applied["cx_applied"]
    assert result.answer.startswith(answer)


# --- contact escalation: fires, and is deduplicated -------------------------


@pytest.mark.parametrize(
    "kind",
    [
        OutcomeKind.EVIDENCE_MISSING,
        OutcomeKind.PERSONAL_ACCOUNT,
        OutcomeKind.DEPENDENCY_UNAVAILABLE,
        OutcomeKind.CROSS_MARKET_POLICY,
    ],
)
def test_contact_offer_fires_for_eligible_fallback_kinds_and_leaves_fallback_copy_intact(
    kind: OutcomeKind,
) -> None:
    fallback_copy = "The approved policy documents do not contain enough information."
    response = _response(fallback_copy)
    outcome = _outcome(kind, country="US")

    result, applied = _compose(response, outcome, country="US")

    assert "contact_offer" in applied["cx_applied"]
    assert result.answer.startswith(fallback_copy)
    assert "1-800-555-0100" in result.answer
    # Only (d) contact and (f) suggestions may apply to a fallback kind.
    assert set(applied["cx_applied"]) <= {"contact_offer", "suggestions"}


def test_contact_offer_never_duplicates_a_contact_already_in_the_answer() -> None:
    answer = "You can reach customer care at 1-800-555-0100 for more help."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    result, applied = _compose(response, outcome, country="US")

    assert "contact_offer" not in applied["cx_applied"]
    assert result.answer == answer


def test_contact_offer_never_duplicates_the_office_contact_addendum_style_supplement() -> None:
    # Simulates chat_orchestrator.py's own _office_contact_addendum / the
    # support-contact supplement having already appended the Kenya office
    # phone before compose_cx_response ever runs.
    answer = "I could not find that policy. You can also reach +254 20 2026869 for help."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="KE")

    result, applied = _compose(response, outcome, country="KE")

    assert "contact_offer" not in applied["cx_applied"]


def test_contact_offer_absent_without_a_reviewed_contact() -> None:
    response = _response("No policy found.")
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="DE")

    result, applied = _compose(response, outcome, country="DE")

    assert "contact_offer" not in applied["cx_applied"]
    assert result.answer == "No policy found."


def test_contact_offer_never_fires_for_a_complete_answer() -> None:
    response = _response("The minimum order is 50 CV.")
    outcome = _outcome(OutcomeKind.ANSWER, country="US")

    result, applied = _compose(response, outcome, country="US")

    assert "contact_offer" not in applied["cx_applied"]


# --- international_directory_note -------------------------------------------


def test_international_directory_note_names_the_target_market() -> None:
    answer = "The office phone is +254 20 2026869."
    response = _response(answer)
    # Coordinator, 2026-09-19: the note is added only when directory fields
    # were requested, so this outcome now carries the phone request it models.
    outcome = _outcome(
        OutcomeKind.INTERNATIONAL_DIRECTORY, country="NL", directory_target="Kenya",
        fields_requested=frozenset({"phone"}),
    )

    result, applied = _compose(response, outcome, country="NL")

    assert "international_directory_note" in applied["cx_applied"]
    assert "Kenya" in result.answer
    assert not _PLACEHOLDER_RE.search(result.answer)


def test_international_directory_note_skipped_when_answer_already_names_the_market() -> None:
    answer = "This Kenya sponsoring office can be reached at +254 20 2026869."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.INTERNATIONAL_DIRECTORY, country="NL", directory_target="Kenya")

    result, applied = _compose(response, outcome, country="NL")

    assert "international_directory_note" not in applied["cx_applied"]
    assert result.answer == answer


def test_international_directory_note_matches_a_compound_target_segment() -> None:
    answer = "This East Africa sponsoring office can be reached at +254 20 2026869."
    response = _response(answer)
    outcome = _outcome(
        OutcomeKind.INTERNATIONAL_DIRECTORY, country="NL", directory_target="Kenya/East Africa",
    )

    result, applied = _compose(response, outcome, country="NL")

    assert "international_directory_note" not in applied["cx_applied"]


def test_international_directory_note_never_fires_outside_that_outcome_kind() -> None:
    response = _response("Some answer naming nothing relevant.")
    outcome = _outcome(OutcomeKind.ANSWER, country="NL", directory_target="Kenya")

    result, applied = _compose(response, outcome, country="NL")

    assert "international_directory_note" not in applied["cx_applied"]


# --- suggestions: only supported topics, never the question's own topic ----


def test_suggestions_exclude_unsupported_topics() -> None:
    response = _response("No policy found.")
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    def _only_returns(topic: str, _country: str) -> bool:
        return topic == "returns"

    result, applied = _compose(response, outcome, country="US", topic_supported=_only_returns)

    keys = [item["key"] for item in result.suggestions]
    assert keys == ["suggest_topic_returns"]


def test_suggestions_never_duplicate_the_questions_own_topic() -> None:
    response = _response("No policy found.")
    outcome = _outcome(
        OutcomeKind.EVIDENCE_MISSING, country="US", fields_requested=frozenset({"payment_methods"}),
    )

    result, applied = _compose(response, outcome, country="US", topic_supported=_all_topics)

    keys = {item["key"] for item in result.suggestions}
    assert "suggest_topic_payment_methods" not in keys
    assert len(result.suggestions) <= 2


def test_suggestions_never_fire_for_dependency_unavailable() -> None:
    response = _response("The service is temporarily unavailable.")
    outcome = _outcome(OutcomeKind.DEPENDENCY_UNAVAILABLE, country="US")

    result, applied = _compose(response, outcome, country="US", topic_supported=_all_topics)

    assert result.suggestions == []
    assert "suggestions" not in applied["cx_applied"]


# --- global invariants -------------------------------------------------------


def test_answer_is_never_empty_even_when_the_original_answer_was_empty() -> None:
    response = _response("", metadata={})
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    result, _applied = _compose(response, outcome, country="US")

    assert result.answer.strip() != ""
    assert not result.answer.startswith("\n\n")


def test_each_addition_is_its_own_paragraph() -> None:
    document = _kenya_document({"Telephone Office": "+254 20 2026869"})
    answer = "You can reach the Kenya office at +254 20 2026869."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.ANSWER, country="KE")

    result, _applied = _compose(
        response, outcome, question="What is the phone number and email?",
        country="KE", evidence_documents=[document], topic_supported=_all_topics,
    )

    paragraphs = [p for p in result.answer.split("\n\n") if p.strip()]
    assert len(paragraphs) >= 2
    assert paragraphs[0] == answer


def test_composition_is_deterministic() -> None:
    document = _kenya_document({"Telephone Office": "+254 20 2026869"})
    response = _response("You can reach the Kenya office at +254 20 2026869.")
    outcome = _outcome(OutcomeKind.ANSWER, country="KE")

    first, first_applied = _compose(
        response, outcome, question="What is the phone number and email?",
        country="KE", evidence_documents=[document], topic_supported=_all_topics,
    )
    second, second_applied = _compose(
        response, outcome, question="What is the phone number and email?",
        country="KE", evidence_documents=[document], topic_supported=_all_topics,
    )

    assert first.answer == second.answer
    assert first.metadata == second.metadata
    assert first.suggestions == second.suggestions
    assert first_applied == second_applied


def test_no_unfilled_placeholder_survives_composition() -> None:
    document = _kenya_document({"Telephone Office": "+254 20 2026869"})
    response = _response("You can reach the Kenya office at +254 20 2026869.")
    outcome = _outcome(OutcomeKind.INTERNATIONAL_DIRECTORY, country="NL", directory_target="Kenya")

    result, _applied = _compose(
        response, outcome, question="What is the phone number and email?",
        country="NL", evidence_documents=[document], topic_supported=_all_topics,
    )

    assert not _PLACEHOLDER_RE.search(result.answer)
    for item in result.suggestions:
        assert not _PLACEHOLDER_RE.search(item["text"])


def test_only_outcome_and_cx_applied_metadata_keys_change() -> None:
    original_metadata = {
        "failure_layer": None,
        "token_usage": {"input": 10, "output": 5},
        "validation": {"ok": True},
    }
    response = _response("The minimum order is 50 CV.", metadata=dict(original_metadata))
    outcome = _outcome(OutcomeKind.ANSWER)

    result, _applied = _compose(response, outcome)

    for key, value in original_metadata.items():
        assert result.metadata[key] == value
    assert set(result.metadata) - set(original_metadata) <= {"outcome", "cx_applied"}


def test_citations_are_never_changed() -> None:
    citations = [{"title": "Kenya directory", "uri": "s3://x"}]
    response = _response("Some answer.", citations=citations)
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    result, _applied = _compose(response, outcome, country="US")

    assert result.citations == citations
    assert result.citations is response.citations


# --- Coordinator review (36a2187): never raise over ordinary content -------
#
# compose_cx_response used to run one final regex check over the WHOLE
# composed answer -- including whatever the model itself wrote -- and raise
# ValueError if it looked like an unfilled placeholder. A model answer that
# happens to contain a literal brace-shaped substring (quoting "{country}"
# as an example, echoing JSON, etc.) would crash the chat turn in
# production. Fixed: only text THIS module renders and appends is ever
# checked, and a defect there drops that one addition instead of raising.


def test_a_literal_brace_substring_already_in_the_models_answer_never_raises() -> None:
    answer = 'The field is templated as "{country}" in our internal docs.'
    response = _response(answer)
    outcome = _outcome(OutcomeKind.ANSWER, country="US")

    result, applied = _compose(response, outcome, country="US")

    assert result.answer.startswith(answer)
    assert not any(item.startswith("dropped:") for item in applied["cx_applied"])


def test_a_literal_brace_substring_in_a_fallback_answer_never_raises() -> None:
    answer = "We could not confirm this. Reference token: {ORDER_ID}."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    result, applied = _compose(response, outcome, country="US")

    assert result.answer.startswith(answer)
    assert "contact_offer" in applied["cx_applied"]


def test_a_broken_own_addition_is_dropped_not_raised_or_delivered() -> None:
    """A defective ``render`` (a stand-in for a future translation bug)
    leaves ``contact_offer`` with an unfilled placeholder. The whole turn
    must not crash, and the broken sentence must never reach the reader --
    it is dropped, and ``cx_applied`` records exactly that.
    """

    def _broken_render(key: str, language: str, **placeholders: object) -> str:
        text = cx_render.render(key, language, **placeholders)
        if key == "contact_offer":
            return text + " Ref: {case_id}"
        return text

    response = _response("No policy found.")
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    result, applied = compose_cx_response(
        response,
        outcome,
        question="What is the minimum order policy?",
        language="en",
        country="US",
        evidence_documents=[],
        topic_supported=_no_topics,
        render=_broken_render,
    )

    assert "dropped:contact_offer" in applied["cx_applied"]
    assert "contact_offer" not in applied["cx_applied"]
    assert "{case_id}" not in result.answer
    assert "1-800-555-0100" not in result.answer
    assert result.answer == "No policy found."


def test_a_broken_partial_note_is_dropped_and_never_promotes_the_outcome() -> None:
    def _broken_render(key: str, language: str, **placeholders: object) -> str:
        text = cx_render.render(key, language, **placeholders)
        if key == "partial_answer_gap":
            return text + " {oops}"
        return text

    document = _kenya_document({"Telephone Office": "+254 20 2026869"})
    answer = "You can reach the Kenya office at +254 20 2026869."
    response = _response(answer)
    outcome = _outcome(OutcomeKind.ANSWER, country="KE")

    result, applied = compose_cx_response(
        response,
        outcome,
        question="What is the phone number and email?",
        language="en",
        country="KE",
        evidence_documents=[document],
        topic_supported=_no_topics,
        render=_broken_render,
    )

    assert "dropped:partial_note" in applied["cx_applied"]
    assert "{oops}" not in result.answer
    assert result.metadata["outcome"]["kind"] == "answer"  # never promoted


def test_a_broken_suggestion_is_dropped_from_the_list() -> None:
    def _broken_render(key: str, language: str, **placeholders: object) -> str:
        text = cx_render.render(key, language, **placeholders)
        if key == "suggest_topic_returns":
            return text + " {broken}"
        return text

    response = _response("No policy found.")
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    def _only_returns(topic: str, _country: str) -> bool:
        return topic == "returns"

    result, applied = compose_cx_response(
        response,
        outcome,
        question="What is the minimum order policy?",
        language="en",
        country="US",
        evidence_documents=[],
        topic_supported=_only_returns,
        render=_broken_render,
    )

    assert result.suggestions == []
    assert "dropped:suggestions" in applied["cx_applied"]
    assert "suggestions" not in applied["cx_applied"]


# --- Robustness: no code path raises on ordinary content -------------------


def test_empty_answer_on_a_fallback_kind_never_raises() -> None:
    response = _response("")
    outcome = _outcome(OutcomeKind.DEPENDENCY_UNAVAILABLE, country="US")

    result, _applied = _compose(response, outcome, country="US")

    assert isinstance(result.answer, str)


def test_empty_answer_on_an_answer_shaped_kind_never_raises() -> None:
    response = _response("")
    outcome = _outcome(OutcomeKind.ANSWER, country="US")

    result, _applied = _compose(response, outcome, country="US", topic_supported=_all_topics)

    assert isinstance(result.answer, str)


def test_none_metadata_values_never_raise() -> None:
    response = _response(
        "Some answer.",
        metadata={"failure_layer": None, "response_source": None, "validation": None, "client_action": None},
    )
    outcome = _outcome(OutcomeKind.ANSWER, country="US")

    result, _applied = _compose(response, outcome, country="US")

    assert result.metadata["failure_layer"] is None
    assert result.metadata["response_source"] is None


def test_metadata_none_itself_never_raises() -> None:
    response = ChatResponse(
        answer="Some answer.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.5,
        metadata=None,  # type: ignore[arg-type]
        correlation_id="corr-none-metadata",
    )
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")

    result, _applied = _compose(response, outcome, country="US")

    assert isinstance(result.metadata, dict)


def test_unrecognised_outcome_kind_never_raises_and_gets_no_addition() -> None:
    # A future OutcomeKind this module has not been taught yet -- fabricated
    # via dataclasses.replace (bypassing the enum) to prove the fail-closed
    # path holds even when `kind` is not one of the nine known members.
    response = _response("Please contact customer care about your order.")
    outcome = dataclasses.replace(_outcome(OutcomeKind.ANSWER, country="US"), kind="some_future_kind")

    result, applied = _compose(response, outcome, country="US", topic_supported=_all_topics)

    assert result is response
    assert applied == {"cx_applied": []}


def test_evidence_documents_missing_content_and_metadata_attributes_never_raise() -> None:
    # Plain objects with neither .content nor .metadata -- not real
    # RetrievedDocument instances -- must not crash field-coverage
    # assessment (app/response/partial_answer.py's own getattr-based
    # reader already tolerates this; this proves cx_compose does not add a
    # second, less careful read of its own).
    response = _response("You can reach the Kenya office at +254 20 2026869.")
    outcome = _outcome(OutcomeKind.ANSWER, country="KE")
    bare_documents = [SimpleNamespace(), object(), {"unrelated": "dict"}]

    result, _applied = _compose(
        response,
        outcome,
        question="What is the phone number and email?",
        country="KE",
        evidence_documents=bare_documents,  # type: ignore[arg-type]
    )

    assert isinstance(result.answer, str)


def test_none_evidence_documents_never_raises() -> None:
    response = _response("You can reach the Kenya office at +254 20 2026869.")
    outcome = _outcome(OutcomeKind.ANSWER, country="KE")

    result, _applied = compose_cx_response(
        response,
        outcome,
        question="What is the phone number and email?",
        language="en",
        country="KE",
        evidence_documents=None,  # type: ignore[arg-type]
        topic_supported=_no_topics,
        render=cx_render.render,
    )

    assert isinstance(result.answer, str)


def test_international_directory_note_skipped_when_no_directory_field_was_requested() -> None:
    answer = "Orders are usually delivered within 5 business days."
    outcome = _outcome(OutcomeKind.INTERNATIONAL_DIRECTORY, country="NL", directory_target="Kenya")

    result, applied = _compose(_response(answer), outcome, country="NL")

    assert "international_directory_note" not in applied["cx_applied"]
    assert result.answer == answer

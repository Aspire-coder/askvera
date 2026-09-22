"""Phase 3 Lane 3: contact_escalation and suggest_follow_ups.

docs/conversation-quality/phase3/CX_LANES.md. Both functions under test are
pure: ``contact_escalation`` is driven by a fake ``render`` callable (never
Lane 4's real copy) and a temporary ``PUBLIC_CONTACTS_PATH`` fixture (never
the real ``config/public_contacts.json``, whose only configured market is
US); ``suggest_follow_ups`` is driven by a fake ``topic_supported`` predicate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.response.contact_completion import contact_escalation
from app.response.outcome import ConversationOutcome, OutcomeKind
from app.response.quality import _public_contacts
from app.response.suggestions import suggest_follow_ups


def _outcome(
    kind: OutcomeKind,
    *,
    country: str = "US",
    language: str = "en",
    fields_requested: frozenset[str] = frozenset(),
    fields_unsupported: frozenset[str] = frozenset(),
) -> ConversationOutcome:
    return ConversationOutcome(
        kind=kind,
        language=language,
        country=country,
        fields_requested=fields_requested,
        fields_answered=frozenset(),
        fields_unsupported=fields_unsupported,
        directory_target=None,
        clarification_subject=None,
        failure_layer=None,
        retrieval_availability=None,
    )


def _fake_render(key: str, language: str, **placeholders: str) -> str:
    joined = ",".join(f"{k}={v}" for k, v in sorted(placeholders.items()))
    return f"[{key}|{language}|{joined}]"


@pytest.fixture(autouse=True)
def _public_contacts_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A small, controlled public-contacts file - never the real one."""
    payload = {
        "version": 1,
        "default": {},
        "countries": {
            "US": {"customerCarePhone": "1-800-555-0100", "website": "www.example-forever.com"},
            "KE": {"website": "www.example-forever.com/ke"},
            # DE deliberately has no reviewed contact at all, and "default"
            # is empty in this fixture so DE truly has nothing to fall back
            # to (unlike the real config/public_contacts.json, whose
            # "default" always carries a website).
        },
    }
    contacts_path = tmp_path / "public_contacts.json"
    contacts_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("PUBLIC_CONTACTS_PATH", str(contacts_path))
    _public_contacts.cache_clear()
    yield
    _public_contacts.cache_clear()


# --- contact_escalation --------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        OutcomeKind.EVIDENCE_MISSING,
        OutcomeKind.PERSONAL_ACCOUNT,
        OutcomeKind.DEPENDENCY_UNAVAILABLE,
        OutcomeKind.CROSS_MARKET_POLICY,
    ],
)
def test_contact_escalation_offers_contact_for_eligible_kinds(kind: OutcomeKind) -> None:
    outcome = _outcome(kind, country="US")
    result = contact_escalation(
        outcome, country="US", language="en", answer_text="I could not find that.", render=_fake_render
    )
    assert result == "[contact_offer|en|contact=1-800-555-0100]"


def test_contact_escalation_partial_answer_only_with_unsupported_fields() -> None:
    with_gap = _outcome(OutcomeKind.PARTIAL_ANSWER, country="US", fields_unsupported=frozenset({"delivery_cost"}))
    without_gap = _outcome(OutcomeKind.PARTIAL_ANSWER, country="US", fields_unsupported=frozenset())

    assert contact_escalation(with_gap, country="US", language="en", answer_text="", render=_fake_render) is not None
    assert contact_escalation(without_gap, country="US", language="en", answer_text="", render=_fake_render) is None


@pytest.mark.parametrize("kind", [OutcomeKind.SAFETY_REFUSAL, OutcomeKind.CLARIFICATION, OutcomeKind.ANSWER])
def test_contact_escalation_never_fires_for_excluded_kinds(kind: OutcomeKind) -> None:
    outcome = _outcome(kind, country="US")
    assert contact_escalation(outcome, country="US", language="en", answer_text="", render=_fake_render) is None


def test_contact_escalation_returns_none_without_a_reviewed_contact() -> None:
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="DE")
    assert contact_escalation(outcome, country="DE", language="de", answer_text="", render=_fake_render) is None


def test_contact_escalation_falls_back_to_website_when_no_phone_is_configured() -> None:
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="KE")
    result = contact_escalation(outcome, country="KE", language="en", answer_text="", render=_fake_render)
    assert result == "[contact_offer|en|contact=www.example-forever.com/ke]"


def test_contact_escalation_never_duplicates_a_contact_already_in_the_answer() -> None:
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")
    answer = "You can reach customer care at 1-800-555-0100."
    assert contact_escalation(outcome, country="US", language="en", answer_text=answer, render=_fake_render) is None


def test_contact_escalation_never_duplicates_a_multilingual_recommendation() -> None:
    outcome = _outcome(OutcomeKind.EVIDENCE_MISSING, country="US")
    # French recommendation sentence that does not literally contain the
    # phone number, but already tells the reader to contact customer care -
    # recommends_contact_in_language must suppress a second offer.
    answer = "Veuillez contacter le service client pour plus de details."
    assert contact_escalation(outcome, country="US", language="fr", answer_text=answer, render=_fake_render) is None


def test_contact_escalation_cross_market_uses_the_session_market_not_the_named_one() -> None:
    # A reader in the US asking about Kenya's policy: the session country is
    # still US, so the offered contact must be the US one, not KE's.
    outcome = _outcome(OutcomeKind.CROSS_MARKET_POLICY, country="US")
    result = contact_escalation(
        outcome, country="US", language="en", answer_text="That is Kenya's policy, not the US one.", render=_fake_render
    )
    assert result == "[contact_offer|en|contact=1-800-555-0100]"


# --- suggest_follow_ups ---------------------------------------------------


def _always_supported(_topic: str, _country: str) -> bool:
    return True


def _never_supported(_topic: str, _country: str) -> bool:
    return False


def test_suggest_follow_ups_returns_up_to_two_supported_topics_in_priority_order() -> None:
    outcome = _outcome(OutcomeKind.ANSWER, country="US")
    result = suggest_follow_ups(outcome, language="en", country="US", topic_supported=_always_supported)
    assert result == ["suggest_topic_delivery_cost", "suggest_topic_payment_methods"]
    assert len(result) <= 2


def test_suggest_follow_ups_never_returns_an_unsupported_topic() -> None:
    outcome = _outcome(OutcomeKind.ANSWER, country="US")
    assert suggest_follow_ups(outcome, language="en", country="US", topic_supported=_never_supported) == []


def test_suggest_follow_ups_never_repeats_the_topic_just_asked() -> None:
    outcome = _outcome(OutcomeKind.ANSWER, country="US", fields_requested=frozenset({"delivery_cost"}))
    result = suggest_follow_ups(outcome, language="en", country="US", topic_supported=_always_supported)
    assert "suggest_topic_delivery_cost" not in result
    assert result == ["suggest_topic_payment_methods", "suggest_topic_contact"]


def test_suggest_follow_ups_never_repeats_a_contact_field_just_asked() -> None:
    outcome = _outcome(OutcomeKind.ANSWER, country="US", fields_requested=frozenset({"phone", "email"}))
    result = suggest_follow_ups(outcome, language="en", country="US", topic_supported=_always_supported)
    assert "suggest_topic_contact" not in result


@pytest.mark.parametrize("kind", [OutcomeKind.SAFETY_REFUSAL, OutcomeKind.DEPENDENCY_UNAVAILABLE])
def test_suggest_follow_ups_never_fires_for_excluded_kinds(kind: OutcomeKind) -> None:
    outcome = _outcome(kind, country="US")
    assert suggest_follow_ups(outcome, language="en", country="US", topic_supported=_always_supported) == []


def test_suggest_follow_ups_predicate_receives_topic_and_country() -> None:
    seen: list[tuple[str, str]] = []

    def _recording(topic: str, country: str) -> bool:
        seen.append((topic, country))
        return topic == "returns"

    outcome = _outcome(OutcomeKind.ANSWER, country="KE")
    result = suggest_follow_ups(outcome, language="en", country="KE", topic_supported=_recording)
    assert result == ["suggest_topic_returns"]
    assert ("returns", "KE") in seen
    assert all(country == "KE" for _topic, country in seen)


def test_suggest_follow_ups_is_deterministic() -> None:
    outcome = _outcome(OutcomeKind.PARTIAL_ANSWER, country="FR")
    first = suggest_follow_ups(outcome, language="fr", country="FR", topic_supported=_always_supported)
    second = suggest_follow_ups(outcome, language="fr", country="FR", topic_supported=_always_supported)
    assert first == second

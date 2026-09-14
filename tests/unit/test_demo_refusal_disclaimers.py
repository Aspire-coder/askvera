"""Legal-required disclaimer wording for medical and income refusals.

Covers docs/legal/2026-09-07-WORDING_REVIEW_PACKET.md Ask B: both the
medical-claim refusal and the income refusal must carry a Legal-supplied
disclaimer sentence, appended to (not replacing) the existing refusal text,
everywhere each refusal is returned. Also covers the third inconsistency:
ailment terms (sunburn, headache, acne) must route to a medical-shaped
refusal instead of falling through to the generic off_topic reply.

"rash" was considered but is deliberately NOT in the denied-phrase list: it
is a substring of ordinary words ("crash", "trash", "brash") that plausibly
appear in enterprise support chat, and `MedicalClaimPolicy.evaluate` does a
plain substring check rather than a word-boundary match. Same collision
class as the "pain"/"Spain" drop below.

A bare `"headache"` token was tried and reverted: it hard-blocked (via
`services.guardrails.check_text`, unconditionally - no co-occurring trigger
needed) the ordinary business idiom "a headache" meaning "a hassle" (e.g.
"This commission calculation is giving me a headache"). Replaced with
health-context phrases ("for a headache", "help a headache", "headache
relief", etc.), following the same multi-word-phrase pattern already used
elsewhere in this list ("help with arthritis", "treat disease").

Does NOT touch, and regression-guards, the REFUSE-vs-WARN decision left open
by Ask B "Problem 2": `PolicyAction.WARN` on `MedicalClaimPolicy` is
unchanged.
"""

import pytest

from app.evidence import localized_conversation_response
from app.risk.models import PolicyAction, RiskContext
from app.risk.policies.medical_claim_policy import MedicalClaimPolicy
from config.guardrail_topics import DENIED_TOPICS
from config.vera_persona import FALLBACK_RESPONSES
from services.claim_safety import localized_claim_response
from services.guardrails import check_text
from utils.exceptions import GuardrailBlockedError

FDA_DISCLAIMER = (
    "Forever's products have not been evaluated by the Food and Drug "
    "Administration and are not intended to diagnose, treat, cure, or "
    "prevent any disease."
)
INCOME_DISCLAIMER = (
    "Individual results may vary. Forever makes no guarantees on income or "
    "success. The Forever Business Owner opportunity and related incentives "
    "are not available to residents of the United States."
)

# Substrings of each disclaimer, distinctive enough per locale to spot-check
# without retyping the full translated sentence.
FDA_LOCALE_MARKERS = {
    "fr": "Food and Drug Administration",
    "es": "Food and Drug Administration",
    "de": "Food and Drug Administration",
}
INCOME_LOCALE_MARKERS = {
    "fr": "Forever Business Owner",
    "es": "Forever Business Owner",
    "de": "Forever Business Owner",
}

# Full translated sentences (not just an untranslated proper noun) for at
# least one locale, so a typo inside the translated text itself (like the
# "Сша"/"США" casing defect this test file originally missed) is caught.
RU_FDA_DISCLAIMER_FULL = (
    "Продукция Forever не была оценена Food and Drug Administration (FDA) "
    "и не предназначена для диагностики, лечения, исцеления или "
    "предотвращения любых заболеваний."
)
RU_INCOME_DISCLAIMER_FULL = (
    "Индивидуальные результаты могут отличаться. Forever не дает никаких "
    "гарантий в отношении дохода или успеха. Возможность Forever Business "
    "Owner и связанные с ней стимулы недоступны для жителей США."
)

ORIGINAL_MEDICAL_FALLBACK_SENTENCE = (
    "I'm not able to give medical advice or make claims about treating or "
    "curing anything."
)
ORIGINAL_INCOME_FALLBACK_SENTENCE = (
    "I can't share income projections or guarantees"
)
ORIGINAL_MEDICAL_CLAIM_SAFETY_SENTENCE = (
    "I can't confirm that a Forever Living product treats or cures a disease."
)


# --- Medical: full claim_safety.json path (product + disease claim) ---


def test_full_medical_claim_response_has_fda_disclaimer_english() -> None:
    response, scope = localized_claim_response(
        "Does Aloe Vera Gel cure diabetes?", "medical_claim", "US", "en"
    )
    assert scope == "product_disease_claim"
    assert response is not None
    assert FDA_DISCLAIMER in response


def test_full_medical_claim_response_keeps_original_refusal_english() -> None:
    """Regression: the disclaimer is appended, not a replacement."""
    response, _ = localized_claim_response(
        "Does Aloe Vera Gel cure diabetes?", "medical_claim", "US", "en"
    )
    assert response is not None
    assert ORIGINAL_MEDICAL_CLAIM_SAFETY_SENTENCE in response


# --- Medical: short fallback path (medical language, no product+disease match) ---


def test_short_medical_fallback_has_fda_disclaimer_english() -> None:
    assert FDA_DISCLAIMER in FALLBACK_RESPONSES["medical_claim"]
    routed = localized_conversation_response("medical_claim", "en")
    assert routed is not None
    assert FDA_DISCLAIMER in routed


def test_short_medical_fallback_keeps_original_refusal_english() -> None:
    """Regression: the disclaimer is appended, not a replacement."""
    assert ORIGINAL_MEDICAL_FALLBACK_SENTENCE in FALLBACK_RESPONSES["medical_claim"]
    routed = localized_conversation_response("medical_claim", "en")
    assert routed is not None
    assert ORIGINAL_MEDICAL_FALLBACK_SENTENCE in routed


# --- Income refusal ---


def test_income_fallback_has_income_disclaimer_english() -> None:
    assert INCOME_DISCLAIMER in FALLBACK_RESPONSES["income_claim"]
    routed = localized_conversation_response("income_claim", "en")
    assert routed is not None
    assert INCOME_DISCLAIMER in routed


def test_income_fallback_keeps_original_refusal_english() -> None:
    """Regression: Legal called the existing income wording 'generally
    appropriate' - it must stay, with the disclaimer appended."""
    assert ORIGINAL_INCOME_FALLBACK_SENTENCE in FALLBACK_RESPONSES["income_claim"]
    routed = localized_conversation_response("income_claim", "en")
    assert routed is not None
    assert ORIGINAL_INCOME_FALLBACK_SENTENCE in routed


# --- Spot-check translated disclaimers in other locales (fr, es, de) ---


@pytest.mark.parametrize("locale", ["fr", "es", "de"])
def test_full_medical_claim_response_has_translated_disclaimer(locale: str) -> None:
    # Scope detection depends on locale-specific product/disease vocabulary,
    # so each locale needs its own message rather than an English one.
    message_by_locale = {
        "fr": "Ce produit guérit-il le diabète ?",
        "es": "Este producto cura la diabetes?",
        "de": "Heilt dieses Produkt Diabetes?",
    }
    response, scope = localized_claim_response(
        message_by_locale[locale], "medical_claim", "FR", locale
    )
    assert scope == "product_disease_claim"
    assert response is not None
    assert FDA_LOCALE_MARKERS[locale] in response


@pytest.mark.parametrize("locale", ["fr", "es", "de"])
def test_conversation_routes_medical_claim_has_translated_disclaimer(locale: str) -> None:
    routed = localized_conversation_response("medical_claim", locale)
    assert routed is not None
    assert FDA_LOCALE_MARKERS[locale] in routed


@pytest.mark.parametrize("locale", ["fr", "es", "de"])
def test_conversation_routes_income_claim_has_translated_disclaimer(locale: str) -> None:
    routed = localized_conversation_response("income_claim", locale)
    assert routed is not None
    assert INCOME_LOCALE_MARKERS[locale] in routed


def test_conversation_routes_ru_medical_claim_matches_full_translated_sentence() -> None:
    """Checks the full translated sentence, not just the untranslated 'FDA'
    marker - a marker-only check would not have caught a typo elsewhere in
    the translated text."""
    routed = localized_conversation_response("medical_claim", "ru")
    assert routed is not None
    assert RU_FDA_DISCLAIMER_FULL in routed


def test_conversation_routes_ru_income_claim_matches_full_translated_sentence() -> None:
    """Regression for the "Сша" -> "США" casing defect: checks the full
    translated sentence, not just the untranslated 'Forever Business Owner'
    marker."""
    routed = localized_conversation_response("income_claim", "ru")
    assert routed is not None
    assert RU_INCOME_DISCLAIMER_FULL in routed


# --- Third inconsistency: ailment terms now route to a medical-shaped refusal ---


@pytest.mark.parametrize(
    "message",
    [
        "What product is best for a sunburn?",
        "What helps a headache?",
        "Do you have anything for a headache?",
        "Is there a product for a headache?",
        "What helps clear up acne?",
    ],
)
def test_ailment_terms_get_medical_shaped_refusal_not_off_topic(message: str) -> None:
    """Trace: services.guardrails.check_text runs DENIED_TOPICS["medical_claim"]
    against user text; before this fix, none of these terms were in that
    list, so the message passed the guardrail untouched and (per the task
    description) fell through elsewhere to the generic off_topic reply."""
    with pytest.raises(GuardrailBlockedError) as excinfo:
        check_text(message, "cid-test")
    assert excinfo.value.topic == "medical_claim"
    assert excinfo.value.topic != "off_topic"


@pytest.mark.parametrize(
    "message",
    [
        "The expense report process is a real headache - is there a simpler form?",
        "Sorting out my shared office paperwork has been a headache. Who can help?",
        "This commission calculation is giving me a headache.",
        "Avoiding the headache of double sponsorship - what is the policy?",
    ],
)
def test_headache_business_idiom_is_not_blocked(message: str) -> None:
    """Regression: a bare "headache" token previously hard-blocked the
    ordinary business idiom "a headache" meaning "a hassle", with no
    co-occurring trigger needed (services.guardrails.check_text raises
    unconditionally on any denied-phrase match). Replacing the bare token
    with health-context phrases must not block these idiomatic uses."""
    try:
        check_text(message, "cid-headache-idiom")
    except GuardrailBlockedError as exc:
        pytest.fail(
            f"expected {message!r} to pass the guardrail unblocked, "
            f"but it was blocked with topic={exc.topic!r}"
        )


def test_pain_and_rash_deliberately_not_added_due_to_substring_collisions() -> None:
    """"pain" and "rash" were named by Legal's Ask B list but are dropped:
    both are substrings of ordinary words ("Spain"; "crash"/"trash"/"brash"),
    and `MedicalClaimPolicy.evaluate` does a plain substring check
    (`phrase in message.lower()`), not a word-boundary match, so adding
    either would misclassify unrelated messages as medical claims. See
    config/guardrail_topics.py."""
    assert "pain" not in DENIED_TOPICS["medical_claim"]
    assert "rash" not in DENIED_TOPICS["medical_claim"]
    assert "sunburn" in DENIED_TOPICS["medical_claim"]
    assert "acne" in DENIED_TOPICS["medical_claim"]


def test_headache_is_phrases_not_a_bare_token() -> None:
    """Regression for the business-idiom bug: no bare "headache" token may
    remain in the list (that is what let "is a headache"/"giving me a
    headache" hard-block); only health-context phrases are present."""
    assert "headache" not in DENIED_TOPICS["medical_claim"]
    assert "for a headache" in DENIED_TOPICS["medical_claim"]
    assert "help a headache" in DENIED_TOPICS["medical_claim"]


def test_spain_question_does_not_trigger_medical_claim_risk() -> None:
    """Regression for the "pain" drop: MedicalClaimPolicy's plain substring
    check must not fire on a message naming Spain."""
    policy = MedicalClaimPolicy()
    context = RiskContext(
        user_message="What are the requirements to become a distributor in Spain?",
        country="ES",
        language="en",
        role="new_prospect",
        correlation_id="cid-spain",
    )
    assert policy.evaluate(context) == []


@pytest.mark.parametrize(
    "message",
    [
        "Our order tracking system had a crash yesterday.",
        "Can I put marketing trash in the shared office bin?",
        "That was a pretty brash sales pitch, wasn't it?",
    ],
)
def test_crash_trash_brash_do_not_trigger_medical_claim_risk(message: str) -> None:
    """Regression for the "rash" drop: MedicalClaimPolicy's plain substring
    check must not fire on ordinary words containing "rash"."""
    policy = MedicalClaimPolicy()
    context = RiskContext(
        user_message=message,
        country="US",
        language="en",
        role="new_prospect",
        correlation_id="cid-rash-collision",
    )
    assert policy.evaluate(context) == []


@pytest.mark.parametrize(
    "message",
    [
        "Our order tracking system had a crash yesterday.",
        "Can I put marketing trash in the shared office bin?",
        "That was a pretty brash sales pitch, wasn't it?",
    ],
)
def test_crash_trash_brash_are_not_classified_as_medical_claim(message: str) -> None:
    """Regression for the "rash" drop, at the guardrail pre-check level:
    services.guardrails.check_text must not raise a medical_claim guardrail
    block for ordinary words containing "rash".

    Explicitly asserts on both outcomes (blocked-as-something-else, or not
    blocked at all) so the test cannot pass without an assertion actually
    running - a bare try/except with the assertion only inside the `except`
    body would pass vacuously if nothing were raised."""
    blocked_topic: str | None = None
    try:
        check_text(message, "cid-rash-collision-guardrail")
    except GuardrailBlockedError as exc:
        blocked_topic = exc.topic
    assert blocked_topic != "medical_claim"


# --- PolicyAction.WARN regression (Ask B "Problem 2" stays undecided) ---


def test_medical_claim_policy_action_is_still_warn() -> None:
    assert MedicalClaimPolicy.metadata.action == PolicyAction.WARN

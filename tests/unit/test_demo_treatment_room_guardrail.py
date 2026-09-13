"""The medical-claim output guardrail must not block "treatment room" retail rules.

Live demo run (UK session, "Can FBOs sell products in retail stores?"): the
generated answer correctly stated that, where approved, products may be sold
"within the section of the premises where the service is supplied (for example,
a treatment room)". `check_text` matched the medical_claim phrase "treatment"
and the reader got the medical-advice refusal. A premises description is not a
medical claim; real treatment claims must still be blocked.
"""

import pytest

from services.guardrails import GuardrailBlockedError, check_text


def _blocked(text: str, *, generated: bool = True) -> bool:
    try:
        check_text(text, "cid", is_generated_answer=generated)
    except GuardrailBlockedError:
        return True
    return False


@pytest.mark.parametrize("answer", [
    "Where approved, you may display and sell products only within the section of the premises where the "
    "service is supplied (for example, a treatment room).",
    "Once approved, you may only display and sell products within the treatment rooms of the salon.",
    "Products may be shown in a beauty salon's treatment area but not in the shop window.",
])
def test_premises_descriptions_are_not_medical_claims(answer):
    assert _blocked(answer) is False


@pytest.mark.parametrize("answer", [
    "Aloe Vera Gel is an effective treatment for eczema.",
    "This drink is a natural treatment that cures arthritis.",
    "Use the gel as a treatment room remedy to treat disease at home.",
    "Book a treatment to cure your diabetes.",
    # Fable review of int2: blocked before the premises skip, must stay blocked.
    "Forever Aloe is used in cancer treatment areas.",
    "The gel is applied in a treatment space for arthritis.",
    "Clinics offer a treatment suite for cancer patients.",
    "The salon has a treatment room for eczema patients.",
    "Our treatment area helps people with diabetes.",
    # Fable re-check: blocked on base, must stay blocked after the premises skip.
    "Treatment rooms for gout sufferers are available.",
    "Aloe treatment rooms are for migraines.",
    "We have treatment areas for hypertension, obesity and rheumatism.",
    "The treatment room helps sick people.",
    "Use the treatment room for chemo recovery.",
    "A treatment area for cancerous growths.",
    "Book our treatment rooms\nfor eczema relief.",
])
def test_real_treatment_claims_are_still_blocked(answer):
    assert _blocked(answer) is True


def test_live_uk_retail_sentence_with_a_following_clause_is_still_delivered():
    answer = ("Where approved, you can only display and sell products within the section of the premises where the "
              "service is supplied (for example, a treatment room), and you're prohibited from using exterior signs "
              "or window displays.")

    assert _blocked(answer) is False


# User-input matching is out of scope for this change; tests/unit/test_guardrails.py
# and tests/unit/test_claim_safety.py pin that behaviour and must stay green.

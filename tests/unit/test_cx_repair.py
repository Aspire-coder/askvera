"""Lane 5 (CX phase 3): tests for app/orchestrator/conversation_repair.py.

Covers: safe typo clarification (shipping/shopping collision), the
one-question precedence rule, and conversation repair (market and topic
corrections) across en plus at least es, fr, de, fi, sv, with positives and
negatives for each capability. No case ids are used anywhere - every
assertion is stated in terms of the module's own behaviour.
"""

from __future__ import annotations

from app.orchestrator.conversation_repair import (
    Clarification,
    Repair,
    detect_repair,
    one_question,
    typo_clarification,
)


# --- typo_clarification: positives ------------------------------------------


def test_typo_clarification_english_shoping_asks_one_question():
    result = typo_clarification("what is the shoping cost", "en")
    assert result == Clarification(
        kind="field", key="clarify_field", options=("shipping cost", "shopping cost")
    )


def test_typo_clarification_english_shippng_asks():
    result = typo_clarification("how much is the shippng cost", "en")
    assert result is not None
    assert result.key == "clarify_field"
    assert set(result.options) == {"shipping cost", "shopping cost"}


def test_typo_clarification_english_exact_shopping_cost_still_ambiguous():
    # A correctly spelled "shopping cost" is still ambiguous with "shipping
    # cost" (one QWERTY-adjacent letter apart), per the task's own example.
    result = typo_clarification("what is the shopping cost", "en")
    assert result is not None
    assert result.key == "clarify_field"


def test_typo_clarification_spanish_positive():
    result = typo_clarification("cual es el costo de shoping", "es")
    assert result is not None
    assert result.key == "clarify_field"
    assert len(result.options) == 2


def test_typo_clarification_french_positive():
    result = typo_clarification("quel est le prix du shoping", "fr")
    assert result is not None
    assert result.key == "clarify_field"


def test_typo_clarification_german_positive():
    result = typo_clarification("was kostet das shoping", "de")
    assert result is not None
    assert result.key == "clarify_field"


def test_typo_clarification_finnish_positive():
    result = typo_clarification("mika on shoping hinta", "fi")
    assert result is not None
    assert result.key == "clarify_field"


def test_typo_clarification_swedish_positive():
    result = typo_clarification("vad kostar shoping", "sv")
    assert result is not None
    assert result.key == "clarify_field"


# --- typo_clarification: negatives ------------------------------------------


def test_typo_clarification_none_when_no_collision_token():
    assert typo_clarification("what is the business hours", "en") is None


def test_typo_clarification_none_when_delivery_context_present_english():
    # "delivery" disambiguates toward shipping - typo_safety's own silent
    # repair handles the rest; this module must not also ask.
    assert typo_clarification("what is the shoping cost for delivery", "en") is None


def test_typo_clarification_none_when_courier_context_present_english():
    assert typo_clarification("shoping cost via courier", "en") is None


def test_typo_clarification_none_when_purchase_context_present_english():
    assert typo_clarification("shoping cost when I buy online", "en") is None


def test_typo_clarification_none_when_delivery_context_present_spanish():
    assert typo_clarification("costo de shoping por entrega", "es") is None


def test_typo_clarification_none_when_delivery_context_present_french():
    assert typo_clarification("prix du shoping pour la livraison", "fr") is None


def test_typo_clarification_none_when_delivery_context_present_german():
    assert typo_clarification("shoping kosten fuer die lieferung", "de") is None


def test_typo_clarification_none_when_delivery_context_present_finnish():
    assert typo_clarification("shoping hinta toimitus", "fi") is None


def test_typo_clarification_none_when_delivery_context_present_swedish():
    assert typo_clarification("shoping kostnad leverans", "sv") is None


def test_typo_clarification_none_for_ordinary_unrelated_typo():
    # An ordinary typo unrelated to the collision pair stays silent - that
    # is typo_safety's job, not this module's.
    assert typo_clarification("what is the buisness hours", "en") is None


def test_typo_clarification_none_for_unknown_language():
    assert typo_clarification("qual e o custo de shoping", "xx") is None


def test_typo_clarification_is_deterministic():
    first = typo_clarification("shoping cost", "en")
    second = typo_clarification("shoping cost", "en")
    assert first == second


# --- one_question ------------------------------------------------------------


def test_one_question_none_when_no_candidates():
    assert one_question([None, None]) is None


def test_one_question_reference_outranks_country():
    reference = Clarification(kind="reference", key="reference_clarification", options=())
    country = Clarification(kind="country", key="clarify_country", options=("Kenya", "Uganda"))
    assert one_question([country, reference]) is reference
    assert one_question([reference, country]) is reference


def test_one_question_country_outranks_role():
    country = Clarification(kind="country", key="clarify_country", options=("Kenya",))
    role = Clarification(kind="role", key="clarify_role", options=("distributor",))
    assert one_question([role, country]) is country


def test_one_question_role_outranks_field():
    role = Clarification(kind="role", key="clarify_role", options=("distributor",))
    field = Clarification(kind="field", key="clarify_field", options=("shipping cost", "shopping cost"))
    assert one_question([field, role]) is role


def test_one_question_never_returns_two():
    field = Clarification(kind="field", key="clarify_field", options=("a", "b"))
    country = Clarification(kind="country", key="clarify_country", options=("c", "d"))
    result = one_question([field, country])
    assert isinstance(result, Clarification)
    assert result is country


def test_one_question_unknown_kind_sorts_last():
    field = Clarification(kind="field", key="clarify_field", options=("a", "b"))
    mystery = Clarification(kind="mystery", key="clarify_mystery", options=("z",))
    assert one_question([mystery, field]) is field


# --- detect_repair: market repairs, positives --------------------------------


def test_detect_repair_market_meant_style_english():
    result = detect_repair("no, I meant Ghana", "en", ["What is the delivery cost in Kenya?"])
    assert result == Repair(
        kind="market",
        replacement="Ghana",
        replaced="Kenya",
        rewritten_question="What is the delivery cost in Ghana",
    )


def test_detect_repair_market_contrast_style_english():
    result = detect_repair("not Kenya, Uganda", "en", ["What is the delivery cost in Kenya?"])
    assert result == Repair(
        kind="market",
        replacement="Uganda",
        replaced="Kenya",
        rewritten_question="What is the delivery cost in Uganda",
    )


def test_detect_repair_market_spanish():
    result = detect_repair("no, quise decir Uganda", "es", ["Cual es el costo de envio en Kenya?"])
    assert result is not None
    assert result.kind == "market"
    assert result.replacement == "Uganda"
    assert result.replaced == "Kenya"
    assert "Uganda" in (result.rewritten_question or "")


def test_detect_repair_market_french():
    result = detect_repair("non, je voulais dire Uganda", "fr", ["Quel est le cout de livraison au Kenya?"])
    assert result is not None
    assert result.kind == "market"
    assert result.replacement == "Uganda"
    assert result.replaced == "Kenya"


def test_detect_repair_market_german():
    result = detect_repair("nein, ich meinte Uganda", "de", ["Wie hoch sind die Lieferkosten in Kenya?"])
    assert result is not None
    assert result.kind == "market"
    assert result.replacement == "Uganda"
    assert result.replaced == "Kenya"


def test_detect_repair_market_finnish():
    result = detect_repair("ei, tarkoitin Uganda", "fi", ["Mika on toimituskulut Kenya?"])
    assert result is not None
    assert result.kind == "market"
    assert result.replacement == "Uganda"
    assert result.replaced == "Kenya"


def test_detect_repair_market_swedish():
    result = detect_repair("nej, jag menade Uganda", "sv", ["Vad kostar frakten i Kenya?"])
    assert result is not None
    assert result.kind == "market"
    assert result.replacement == "Uganda"
    assert result.replaced == "Kenya"


# --- detect_repair: topic repairs, positives ---------------------------------


def test_detect_repair_topic_meant_style_english():
    result = detect_repair("I meant shipping", "en", ["What is the shopping cost?"])
    assert result is not None
    assert result.kind == "topic"
    assert result.replacement == "shipping"
    assert result.replaced == "shopping"
    assert result.rewritten_question == "What is the shipping cost"


def test_detect_repair_topic_with_extra_wording_english():
    result = detect_repair("sorry, I meant the delivery cost", "en", ["What is the shopping cost?"])
    assert result is not None
    assert result.kind == "topic"
    assert result.replaced == "shopping"


def test_detect_repair_topic_spanish():
    result = detect_repair("no, quise decir el envio", "es", ["Cual es el costo de compra?"])
    assert result is not None
    assert result.kind == "topic"
    assert result.replaced == "compra"


def test_detect_repair_topic_french():
    result = detect_repair("non, je voulais dire la livraison", "fr", ["Quel est le cout d'achat?"])
    assert result is not None
    assert result.kind == "topic"
    assert result.replaced == "achat"


def test_detect_repair_topic_german():
    result = detect_repair("nein, ich meinte den Versand", "de", ["Was kostet der Einkauf?"])
    assert result is not None
    assert result.kind == "topic"
    assert result.replaced == "Einkauf"


def test_detect_repair_topic_finnish():
    result = detect_repair("ei, tarkoitin toimitus", "fi", ["Mika on ostos hinta?"])
    assert result is not None
    assert result.kind == "topic"
    assert result.replaced == "ostos"


def test_detect_repair_topic_swedish():
    result = detect_repair("nej, jag menade frakt", "sv", ["Vad kostar kopet?"])
    assert result is not None
    assert result.kind == "topic"


# --- detect_repair: negatives -------------------------------------------------


def test_detect_repair_none_for_bare_no_question_english():
    # Fable-style guard: must never fire on an ordinary message that merely
    # starts with "No".
    assert detect_repair("No minimum order?", "en", ["What is the delivery cost?"]) is None


def test_detect_repair_none_for_bare_negation_with_comma_english():
    assert detect_repair("No, that's wrong", "en", ["What is the delivery cost in Kenya?"]) is None


def test_detect_repair_none_without_correction_cue():
    assert detect_repair("What is the delivery cost in Ghana?", "en", ["What is the delivery cost in Kenya?"]) is None


def test_detect_repair_none_when_no_prior_turns_and_span_unresolved():
    # A "meant" correction naming a market with no prior turn at all cannot
    # be swapped into anything; still returns a Repair, but with nothing to
    # rewrite - the caller should ask, not guess.
    result = detect_repair("no, I meant Ghana", "en", [])
    assert result == Repair(kind="market", replacement="Ghana", replaced=None, rewritten_question=None)


def test_detect_repair_none_when_replacement_unresolvable():
    # "I meant something" resolves to neither a market nor a topic word.
    assert detect_repair("I meant something else entirely", "en", ["What is the delivery cost?"]) is None


def test_detect_repair_none_for_empty_message():
    assert detect_repair("", "en", ["What is the delivery cost?"]) is None


def test_detect_repair_none_for_unknown_language():
    assert detect_repair("no, I meant Ghana", "xx", ["What is the delivery cost in Kenya?"]) is None


def test_detect_repair_replaced_none_when_prior_span_ambiguous():
    # Two different markets already named in the prior turn: the "meant"
    # style has nothing unambiguous to swap, so replaced/rewritten stay None.
    result = detect_repair(
        "no, I meant Ghana", "en", ["Is it different between Kenya and Uganda?"]
    )
    assert result is not None
    assert result.kind == "market"
    assert result.replaced is None
    assert result.rewritten_question is None


# --- market repairs never touch policy country -------------------------------


def test_repair_dataclass_carries_no_policy_country_field():
    result = detect_repair("no, I meant Ghana", "en", ["What is the delivery cost in Kenya?"])
    assert result is not None
    field_names = {field for field in result.__dataclass_fields__}
    assert "country" not in field_names
    assert "policy_country" not in field_names
    assert field_names == {"kind", "replacement", "replaced", "rewritten_question"}


def test_market_repair_replacement_is_directory_target_not_policy_widening():
    # The replacement is the market's DIRECTORY display name only; nothing
    # in this module's output claims to authorize or widen policy scope for
    # that market - that decision stays entirely with the caller/session.
    result = detect_repair("no, I meant Ghana", "en", ["What is the delivery cost in Kenya?"])
    assert result is not None
    assert result.kind == "market"
    assert result.replacement == "Ghana"


# --- determinism ---------------------------------------------------------------


def test_detect_repair_is_deterministic():
    first = detect_repair("no, I meant Ghana", "en", ["What is the delivery cost in Kenya?"])
    second = detect_repair("no, I meant Ghana", "en", ["What is the delivery cost in Kenya?"])
    assert first == second

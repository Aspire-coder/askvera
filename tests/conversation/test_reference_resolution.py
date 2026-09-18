"""Lane A (Phase 2, task A7): app.orchestrator.reference_resolution.

Pure-function tests for the unresolved-back-reference module itself: no
model call, no retriever, no orchestrator - deterministic/local throughout.
tests/conversation/test_reference_e2e.py drives the same behaviour through
the real ``AIOrchestrator.handle_chat`` pipeline; this file is the narrower,
faster check of the resolution logic on its own.

Every test is labeled deterministic/local: reference_resolution.py makes no
network, AWS or model call, so nothing here needs mocking beyond the plain
Python inputs (message, history text, language code) the module takes.
"""

from __future__ import annotations

from app.orchestrator.reference_resolution import resolve_reference


def _history(*turns: tuple[str, str]) -> str:
    lines: list[str] = []
    for user_turn, vera_turn in turns:
        lines.extend([f"user: {user_turn}", f"vera: {vera_turn}"])
    return "\n".join(lines)


KENYA_THEN_UGANDA = _history(
    ("What is the delivery cost in Kenya?", "Delivery to Kenya costs $3 within the country."),
    ("What about Uganda?", "Delivery to Uganda costs a different amount; ask for specifics."),
)


# =============================================================================
# Rule 2: a contrastive reference with 2+ candidates clarifies, naming them.
# =============================================================================


def test_a7_the_other_one_after_kenya_then_uganda_clarifies_naming_both() -> None:
    """deterministic/local. The A7 repro at the resolution-module layer."""
    outcome = resolve_reference("What about the other one?", KENYA_THEN_UGANDA, "en")
    assert set(outcome.clarification_candidates) == {"Kenya", "Uganda"}
    assert outcome.resolved_market is None


def test_the_other_one_with_three_candidates_names_all_three() -> None:
    """deterministic/local."""
    history = _history(
        ("What is the delivery cost in Kenya?", "Delivery to Kenya costs $3 within the country."),
        ("What about Uganda?", "Delivery to Uganda costs a different amount."),
        ("And Tanzania?", "Delivery to Tanzania costs a different amount too."),
    )
    outcome = resolve_reference("What about the other one?", history, "en")
    # market_display_name uses markets.json's own configured name, which for
    # Tanzania is its full ISO short name.
    assert set(outcome.clarification_candidates) == {"Kenya", "Uganda", "Tanzania, United Republic of"}
    assert outcome.resolved_market is None


# =============================================================================
# Rule 3: a resolvable ordinal resolves deterministically, by first mention.
# =============================================================================


def test_the_first_one_resolves_to_kenya_the_first_named_market() -> None:
    """deterministic/local."""
    outcome = resolve_reference("What about the first one?", KENYA_THEN_UGANDA, "en")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market == "Kenya"
    assert outcome.rewritten_message == "What about the first one? Kenya"


def test_the_last_one_resolves_to_the_most_recently_named_market() -> None:
    """deterministic/local."""
    outcome = resolve_reference("What about the last one?", KENYA_THEN_UGANDA, "en")
    assert outcome.resolved_market == "Uganda"


def test_the_second_one_resolves_to_uganda() -> None:
    """deterministic/local."""
    outcome = resolve_reference("What about the second one?", KENYA_THEN_UGANDA, "en")
    assert outcome.resolved_market == "Uganda"


def test_the_former_and_the_latter_resolve_with_exactly_two_candidates() -> None:
    """deterministic/local."""
    former = resolve_reference("What about the former?", KENYA_THEN_UGANDA, "en")
    latter = resolve_reference("What about the latter?", KENYA_THEN_UGANDA, "en")
    assert former.resolved_market == "Kenya"
    assert latter.resolved_market == "Uganda"


def test_latter_with_three_candidates_is_genuinely_ambiguous_and_unresolved() -> None:
    """deterministic/local. former/latter only ever mean two things; with
    three candidates in play resolving one anyway would be a guess."""
    history = _history(
        ("What is the delivery cost in Kenya?", "..."),
        ("What about Uganda?", "..."),
        ("And Tanzania?", "..."),
    )
    outcome = resolve_reference("What about the latter?", history, "en")
    assert outcome.resolved_market is None
    assert outcome.clarification_candidates == ()


# =============================================================================
# Rule 1: a message naming its own market is never touched.
# =============================================================================


def test_message_naming_its_own_market_is_unchanged_even_with_contrastive_word() -> None:
    """deterministic/local. "the other product" - naming Kenya itself takes
    the normal path; asking about it again is not this module's concern."""
    outcome = resolve_reference("What about the other product in Kenya?", KENYA_THEN_UGANDA, "en")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None
    assert outcome.rewritten_message == "What about the other product in Kenya?"


# =============================================================================
# Rule 4: fewer than two candidates leaves behaviour unchanged.
# =============================================================================


def test_single_candidate_market_leaves_the_other_one_unresolved() -> None:
    """deterministic/local."""
    history = _history(("What is the delivery cost in Kenya?", "Delivery to Kenya costs $3."))
    outcome = resolve_reference("What about the other one?", history, "en")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


def test_no_candidates_at_all_leaves_the_first_one_unresolved() -> None:
    """deterministic/local."""
    outcome = resolve_reference("What about the first one?", "", "en")
    assert outcome.resolved_market is None
    assert outcome.clarification_candidates == ()


# =============================================================================
# Negative controls: a normal topic-shift follow-up is untouched.
# =============================================================================


def test_topic_change_with_no_reference_word_is_untouched() -> None:
    """deterministic/local. "What about returns?" names no market and
    contains no contrastive/ordinal token, so nothing here applies -
    normal topic-shift handling in chat_orchestrator is unaffected."""
    outcome = resolve_reference("What about returns?", KENYA_THEN_UGANDA, "en")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None
    assert outcome.rewritten_message == "What about returns?"


def test_what_about_delivery_is_also_untouched() -> None:
    """deterministic/local."""
    outcome = resolve_reference("What about delivery?", KENYA_THEN_UGANDA, "en")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


def test_assistant_turn_naming_a_market_is_not_a_candidate() -> None:
    """deterministic/local. Only USER turns count. A history where the
    SECOND market is named only by the assistant must behave like a
    single-candidate history, not a two-candidate one."""
    history = _history(
        ("What is the delivery cost in Kenya?", "Delivery to Kenya costs $3."),
        ("What about the office hours?", "For Uganda, office hours are 08:30 to 17:00."),
    )
    outcome = resolve_reference("What about the other one?", history, "en")
    # Uganda was only ever named by Vera, never by the user, so there is
    # still only one user-named candidate (Kenya) - unchanged behaviour.
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


# =============================================================================
# Preserved references keep working: these are not contrastive/ordinal words.
# =============================================================================


def test_that_number_is_not_treated_as_a_back_reference() -> None:
    """deterministic/local. "that" is a FOLLOW_UP_REFERENCE_MARKER handled
    elsewhere in chat_orchestrator.py; it is not in this module's closed
    class and must not be caught by it."""
    outcome = resolve_reference("Is that the office phone or the order phone?", KENYA_THEN_UGANDA, "en")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


def test_there_and_that_requirement_are_not_treated_as_back_references() -> None:
    """deterministic/local."""
    for message in ("Is the office there open on weekends?", "Is that requirement the same everywhere?"):
        outcome = resolve_reference(message, KENYA_THEN_UGANDA, "en")
        assert outcome.clarification_candidates == ()
        assert outcome.resolved_market is None


# =============================================================================
# Rule 5: an unrecognized language fails conservative - unchanged behaviour.
# =============================================================================


def test_unknown_language_code_is_unchanged_even_with_the_english_word_other() -> None:
    """deterministic/local. "xx" names no configured widget language."""
    outcome = resolve_reference("What about the other one?", KENYA_THEN_UGANDA, "xx")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


def test_empty_language_code_is_unchanged() -> None:
    """deterministic/local."""
    outcome = resolve_reference("What about the other one?", KENYA_THEN_UGANDA, "")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


# =============================================================================
# Multilingual controls: contrastive and ordinal forms, several languages.
# Each history is written in the message's own language so find_market_mentions
# (config/market_name_aliases.json) recognizes the candidate markets the way a
# real conversation in that language would name them.
# =============================================================================


MULTILINGUAL_CASES = {
    # language: (question-opener, first market, second market, "other one", "first one")
    # Market names are left as "Kenya"/"Uganda" (unaccented, in every locale's
    # own alias list per config/market_name_aliases.json) so this table
    # isolates the thing it is testing - contrastive/ordinal WORD detection -
    # from find_market_mentions' own accent/alias matching.
    "fr": ("Quel est le cout de livraison pour", "Kenya", "Ouganda", "Qu'en est-il de l'autre ?", "Qu'en est-il du premier ?"),
    "de": ("Wie hoch sind die Lieferkosten fuer", "Kenya", "Uganda", "Und was ist mit dem anderen?", "Und was ist mit dem ersten?"),
    "es": ("Cual es el costo de envio para", "Kenya", "Uganda", "Y que hay del otro?", "Y que hay del primero?"),
    "nl": ("Wat zijn de verzendkosten voor", "Kenya", "Uganda", "Hoe zit het met de andere?", "Hoe zit het met de eerste?"),
    "it": ("Qual e il costo di consegna per", "Kenya", "Uganda", "E per quanto riguarda l'altro?", "E per quanto riguarda il primo?"),
    "pt": ("Qual e o custo de entrega para", "Kenya", "Uganda", "E quanto ao outro?", "E quanto ao primeiro?"),
    "fi": ("Mika on toimituskulu maalle", "Kenya", "Uganda", "Enta se muu?", "Enta ensimmainen?"),
    "sv": ("Vad ar leveranskostnaden for", "Kenya", "Uganda", "Hur ar det med den andra?", "Hur ar det med den forsta?"),
    "no": ("Hva er leveringskostnaden for", "Kenya", "Uganda", "Hva med den andre?", "Hva med den forste?"),
}


def test_multilingual_contrastive_forms_clarify_naming_candidates() -> None:
    """deterministic/local. fr, de, es, nl, it, pt, fi, sv, no: a contrastive
    reference after two markets named in the user's OWN language clarifies."""
    failures: list[str] = []
    for language, (opener, market_a, market_b, other_one, _first_one) in MULTILINGUAL_CASES.items():
        history = _history((f"{opener} {market_a}?", "..."), (f"{opener} {market_b}?", "..."))
        outcome = resolve_reference(other_one, history, language)
        if len(outcome.clarification_candidates) < 2:
            failures.append(f"{language}: {outcome}")
    assert not failures, failures


def test_multilingual_ordinal_first_forms_resolve_deterministically() -> None:
    """deterministic/local. Same languages, "the first one" equivalent."""
    failures: list[str] = []
    for language, (opener, market_a, market_b, _other_one, first_one) in MULTILINGUAL_CASES.items():
        history = _history((f"{opener} {market_a}?", "..."), (f"{opener} {market_b}?", "..."))
        outcome = resolve_reference(first_one, history, language)
        if not outcome.resolved_market:
            failures.append(f"{language}: {outcome}")
    assert not failures, failures

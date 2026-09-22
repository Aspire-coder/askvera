"""Phase 2 conversation-quality: fixes for the Fable review of Phase 2
(2026-09-18), findings A1, A2, F1 and T1.

Each test below reproduces one specific finding against the real module it
targets, so a regression on any of these four points fails here first.
Deterministic/local throughout: no model, retrieval, or network dependency.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.orchestrator.reference_resolution import resolve_reference
from app.response.contact_completion import recommends_contact_in_language


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
# A1: "one second" is the English interjection, not "the second one" -
# ordinal word must precede the prop word for rule 3 to fire.
# =============================================================================


def test_one_second_the_common_interjection_is_left_unresolved() -> None:
    """The exact Fable repro: prop word ("one") BEFORE the ordinal word
    ("second") must not resolve, unlike "the second one"."""
    outcome = resolve_reference("One second", KENYA_THEN_UGANDA, "en")
    assert outcome.resolved_market is None
    assert outcome.clarification_candidates == ()
    assert outcome.rewritten_message == "One second"


def test_one_second_please_is_also_left_unresolved() -> None:
    """Same interjection with a trailing word; still no leftover content
    beyond the allowed prop word, so only word order distinguishes it."""
    outcome = resolve_reference("One second please", KENYA_THEN_UGANDA, "en")
    assert outcome.resolved_market is None


def test_the_second_one_still_resolves_ordinal_before_prop_word() -> None:
    """The mirror-image phrasing (ordinal precedes the prop word) must keep
    resolving - this finding must not overcorrect into never resolving
    "second" at all."""
    outcome = resolve_reference("What about the second one?", KENYA_THEN_UGANDA, "en")
    assert outcome.resolved_market == "Uganda"
    assert outcome.rewritten_message == "What about the second one? Uganda"


def test_one_moment_style_ordinal_free_interjections_are_unaffected() -> None:
    """Negative control: an interjection with no ordinal word at all was
    never affected by this finding and must keep behaving as before."""
    outcome = resolve_reference("One moment", KENYA_THEN_UGANDA, "en")
    assert outcome.resolved_market is None
    assert outcome.clarification_candidates == ()


def test_any_other_and_is_there_another_still_clarify_by_design() -> None:
    """Fable also flagged that these two bare contrastive openers now
    clarify. Documented decision (see reference_resolution.py's module
    docstring): this is a correct rule-2 clarification, not a wrong
    answer, and is left unchanged - pinned here so the decision does not
    silently drift."""
    for message in ("Any other?", "Is there another?"):
        outcome = resolve_reference(message, KENYA_THEN_UGANDA, "en")
        assert set(outcome.clarification_candidates) == {"Kenya", "Uganda"}
        assert outcome.resolved_market is None


# =============================================================================
# A2: language code normalization - "nb"/"nb-NO" must fold to "no", and a
# region tag like "fr-FR" must keep working, the same as Lane B's
# normalize_language_code.
# =============================================================================


def test_norwegian_bokmal_code_nb_is_recognized() -> None:
    outcome = resolve_reference("Hva med den andre?", KENYA_THEN_UGANDA, "nb")
    assert set(outcome.clarification_candidates) == {"Kenya", "Uganda"}


def test_norwegian_bokmal_code_nb_no_is_recognized() -> None:
    outcome = resolve_reference("Hva med den andre?", KENYA_THEN_UGANDA, "nb-NO")
    assert set(outcome.clarification_candidates) == {"Kenya", "Uganda"}


def test_region_tagged_french_still_resolves_ordinal() -> None:
    outcome = resolve_reference("Et la premiere?", KENYA_THEN_UGANDA, "fr-FR")
    assert outcome.resolved_market == "Kenya"


def test_still_unknown_language_code_stays_unchanged() -> None:
    """A code with no configured vocabulary at all - not merely a region
    variant of a known one - must still fail conservative (rule 5)."""
    outcome = resolve_reference("Hva med den andre?", KENYA_THEN_UGANDA, "xx")
    assert outcome.clarification_candidates == ()
    assert outcome.resolved_market is None


# =============================================================================
# F1: recommends_contact_in_language - region-tagged codes, and a small
# clause-local negation guard.
# =============================================================================


def test_region_tagged_french_is_recognized() -> None:
    assert (
        recommends_contact_in_language(
            "Veuillez contacter le service client pour plus d'aide.", "fr-FR"
        )
        is True
    )


NEGATED_RECOMMENDATIONS = {
    "fr": "Il n'est pas nécessaire de contacter le service client.",
    "es": "No es necesario contactar con atención al cliente.",
    "nl": "U hoeft niet contact op te nemen met de klantenservice.",
    "it": "Non è necessario contattare il servizio clienti.",
    "sv": "Det är inte nödvändigt att kontakta kundtjänsten.",
    "no": "Det er ikke nødvendig å kontakte kundeservice.",
}


def test_negated_recommendations_no_longer_report_true() -> None:
    """The clause-local negation guard: a negation word earlier in the
    same clause as the matched verb phrase means this is NOT a
    recommendation to contact anyone, in each named language."""
    failures = []
    for language, sentence in NEGATED_RECOMMENDATIONS.items():
        if recommends_contact_in_language(sentence, language) is not False:
            failures.append(language)
    assert not failures, failures


def test_negation_in_an_earlier_sentence_does_not_suppress_a_later_recommendation() -> None:
    """The guard is clause-local: a negation word in a PRIOR sentence must
    not suppress a genuine recommendation in a later one."""
    text = "Ce n'est pas un probleme. Veuillez contacter le service client pour plus d'aide."
    assert recommends_contact_in_language(text, "fr") is True


def test_contacting_a_different_party_for_support_still_reports_true() -> None:
    """Pinned per the coordinator's review: this sentence genuinely does
    recommend contacting support, so it must keep reporting True even
    though "autre" (another/other) appears in it."""
    text = "Pour contacter un autre distributeur, demandez au support client."
    assert recommends_contact_in_language(text, "fr") is True


def test_negation_of_an_unrelated_earlier_clause_is_a_known_limitation() -> None:
    """KNOWN LIMITATION (documented, not xfail): the negation guard in
    app/response/contact_completion.py splits clauses only on sentence-
    ending punctuation (".", "!", "?"), not on commas. A negation word that
    modifies an EARLIER, comma-separated clause of the same sentence - here
    "nicht" negates only "telefonisch erreichbar" ("not reachable by
    phone") - is still treated as being in the same clause as a LATER,
    genuinely unnegated recommendation in that sentence ("aber
    kontaktieren Sie das Buro" - "but contact the office"), so this
    sentence's real recommendation is incorrectly suppressed (reports
    False instead of True). This is the accepted, narrower cost of keeping
    the guard "small, closed, and simple" (clause-local via cheap
    punctuation splitting) rather than building real clause/dependency
    parsing - the same trade-off already accepted for the general
    negation-guard design. Pinned here as current behaviour so a future
    change to the clause-splitting logic is a deliberate decision, not an
    accidental regression either way."""
    text = "Der Kundenservice ist nicht telefonisch erreichbar, aber kontaktieren Sie das Büro."
    assert recommends_contact_in_language(text, "de") is False


# =============================================================================
# T1: the ROUTES_REST_SHA256 comment in test_codex_conversation_tone.py must
# match config/conversation_routes.json exactly - "reference_clarification"
# is configured for en, fr, es, de, nl, it, fi, no, sv only (no sr, no ru).
# =============================================================================


def test_reference_clarification_locales_match_config() -> None:
    """Reproduces the T1 comment/config mismatch directly against the real
    config file, independent of the tone test's own hash check."""
    root = Path(__file__).parents[2]
    routes = json.loads((root / "config" / "conversation_routes.json").read_text(encoding="utf-8"))
    locales = routes.get("locales", {})
    with_key = {
        locale
        for locale, block in locales.items()
        if isinstance(block, dict) and "reference_clarification" in block.get("responses", {})
    }
    assert with_key == {"en", "fr", "es", "de", "nl", "it", "fi", "no", "sv"}

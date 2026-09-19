"""CX phase 3, Lane 2: final-answer quality checks added to app/response/quality.py.

docs/conversation-quality/phase3/CX_DESIGN.md,
docs/conversation-quality/phase3/CX_LANES.md,
docs/conversation-quality/phase3/CX_LANE2_PARTIAL_AND_QUALITY.md.
"""

from __future__ import annotations

from app.response.outcome import OutcomeKind
from app.response.partial_answer import FieldCoverage
from app.response.quality import (
    confidence_framing_key,
    leading_preamble_span,
    overclaim_findings,
    strip_leading_preamble,
)


def _coverage(unsupported: frozenset[str] = frozenset()) -> FieldCoverage:
    return FieldCoverage(
        requested=unsupported,
        answered=frozenset(),
        unsupported=unsupported,
        omitted=frozenset(),
    )


# --- leading_preamble_span / strip_leading_preamble: positive cases --------


def test_english_preamble_is_detected_and_stripped() -> None:
    answer = "Great question! The delivery cost is 5 USD."
    span = leading_preamble_span(answer, "en")
    assert span == (0, len("Great question!"))
    assert strip_leading_preamble(answer, "en") == "The delivery cost is 5 USD."


def test_spanish_preamble_is_detected_and_stripped() -> None:
    answer = "Buena pregunta. El costo de envio es 5 USD."
    assert leading_preamble_span(answer, "es") is not None
    assert strip_leading_preamble(answer, "es") == "El costo de envio es 5 USD."


def test_spanish_inverted_exclamation_preamble_is_detected_and_stripped() -> None:
    # Coordinator review of 568a422: leading opening punctuation (¡, ¿,
    # guillemets, quotes) must not hide an otherwise-exact opener match.
    answer = "¡Buena pregunta! El pedido minimo es de 100 USD."
    assert leading_preamble_span(answer, "es") is not None
    assert strip_leading_preamble(answer, "es") == "El pedido minimo es de 100 USD."


def test_spanish_claro_preamble_is_detected_and_stripped() -> None:
    answer = "¡Claro! El pedido minimo es de 100 USD."
    assert leading_preamble_span(answer, "es") is not None
    assert strip_leading_preamble(answer, "es") == "El pedido minimo es de 100 USD."


def test_spanish_por_supuesto_preamble_is_detected_and_stripped() -> None:
    answer = "¡Por supuesto! El pedido minimo es de 100 USD."
    assert leading_preamble_span(answer, "es") is not None
    assert strip_leading_preamble(answer, "es") == "El pedido minimo es de 100 USD."


def test_spanish_inverted_exclamation_preamble_with_a_number_is_never_preamble() -> None:
    # Control: the opening punctuation must not defeat the digit guard --
    # a preamble-shaped sentence that itself states a fact is still kept.
    answer = "¡Buena pregunta, cuesta 5 USD!"
    assert leading_preamble_span(answer, "es") is None
    assert strip_leading_preamble(answer, "es") == answer


# --- negation / yes-no answer tokens: coordinator review of cadd4f1 --------
#
# "Of course not.", "Certainly not.", "Claro que no.", "Claro que si.",
# "Naturlich nicht.", "Bien sur que non." all open with a table entry from
# _PREAMBLE_OPENERS, but each one IS the direct yes/no answer -- stripping
# it deleted the actual answer, not a pleasantry.


def test_of_course_not_keeps_its_negation() -> None:
    answer = "Of course not. Returns are not accepted."
    assert leading_preamble_span(answer, "en") is None
    assert strip_leading_preamble(answer, "en") == answer


def test_certainly_not_keeps_its_negation() -> None:
    answer = "Certainly not. Returns are not accepted."
    assert leading_preamble_span(answer, "en") is None
    assert strip_leading_preamble(answer, "en") == answer


def test_of_course_not_with_a_different_second_sentence_keeps_its_negation() -> None:
    answer = "Of course not. You can ask your sponsor."
    assert leading_preamble_span(answer, "en") is None
    assert strip_leading_preamble(answer, "en") == answer


def test_spanish_claro_que_no_keeps_its_negation() -> None:
    answer = "Claro que no. No se aceptan devoluciones."
    assert leading_preamble_span(answer, "es") is None
    assert strip_leading_preamble(answer, "es") == answer


def test_spanish_claro_que_si_keeps_its_affirmation() -> None:
    answer = "Claro que sí. Puedes cambiar de patrocinador."
    assert leading_preamble_span(answer, "es") is None
    assert strip_leading_preamble(answer, "es") == answer


def test_german_naturlich_nicht_keeps_its_negation() -> None:
    answer = "Natürlich nicht. Rückgaben werden nicht akzeptiert."
    assert leading_preamble_span(answer, "de") is None
    assert strip_leading_preamble(answer, "de") == answer


def test_french_bien_sur_que_non_keeps_its_negation() -> None:
    answer = "Bien sûr que non. Les retours ne sont pas acceptés."
    assert leading_preamble_span(answer, "fr") is None
    assert strip_leading_preamble(answer, "fr") == answer


def test_of_course_returns_are_accepted_still_strips() -> None:
    # Positive control: a genuine pleasantry opener with no negation/yes-no
    # token in it must still strip after the fix.
    answer = "Of course! Returns are accepted within 30 days."
    assert leading_preamble_span(answer, "en") is not None
    assert strip_leading_preamble(answer, "en") == "Returns are accepted within 30 days."


def test_spanish_claro_still_strips() -> None:
    answer = "¡Claro! Puedes cambiar de patrocinador."
    assert leading_preamble_span(answer, "es") is not None
    assert strip_leading_preamble(answer, "es") == "Puedes cambiar de patrocinador."


def test_french_preamble_is_detected_and_stripped() -> None:
    answer = "Merci de poser la question. Le cout de livraison est de 5 USD."
    assert leading_preamble_span(answer, "fr") is not None
    assert strip_leading_preamble(answer, "fr") == "Le cout de livraison est de 5 USD."


def test_german_preamble_is_detected_and_stripped() -> None:
    answer = "Gute Frage. Die Versandkosten betragen 5 USD."
    assert leading_preamble_span(answer, "de") is not None
    assert strip_leading_preamble(answer, "de") == "Die Versandkosten betragen 5 USD."


def test_finnish_preamble_is_detected_and_stripped() -> None:
    answer = "Hyva kysymys. Toimituskulut ovat 5 USD."
    assert leading_preamble_span(answer, "fi") is not None
    assert strip_leading_preamble(answer, "fi") == "Toimituskulut ovat 5 USD."


def test_accented_preamble_folds_to_the_same_table_entry() -> None:
    # "Selbstverständlich" (accented) must match the accent-folded
    # German table entry without a second, accented literal in the table.
    # A distinct opener sentence (its own "!") keeps the digit that follows
    # out of the sentence being judged for preamble.
    answer = "Selbstverständlich! Die Versandkosten betragen 5 USD."
    assert leading_preamble_span(answer, "de") is not None


# --- leading_preamble_span: negative controls (never preamble) -------------


def test_first_sentence_with_a_number_is_never_preamble() -> None:
    answer = "5 USD is the delivery cost, thank you for your patience."
    assert leading_preamble_span(answer, "en") is None
    assert strip_leading_preamble(answer, "en") == answer


def test_certainly_the_fee_keeps_the_fee_sentence() -> None:
    # "Certainly" opens the table, but the sentence itself states a fact
    # (a digit) and must never be stripped.
    answer = "Certainly, the fee is 5 USD."
    assert leading_preamble_span(answer, "en") is None
    assert strip_leading_preamble(answer, "en") == answer


def test_sentence_with_a_citation_marker_is_never_preamble() -> None:
    answer = "Certainly, this is confirmed [1]. Delivery takes three days."
    assert leading_preamble_span(answer, "en") is None


def test_directory_answer_with_all_fields_gives_no_preamble_removal() -> None:
    answer = "Certainly: Telephone Office: +254 20 2026869"
    assert leading_preamble_span(answer, "en") is None


def test_policy_wording_sentence_is_never_preamble() -> None:
    answer = "Certainly, our returns policy allows a full refund within 30 days."
    assert leading_preamble_span(answer, "en") is None


def test_localized_policy_wording_sentence_is_never_preamble() -> None:
    answer = "Por supuesto, esta es nuestra politica de devoluciones completa."
    assert leading_preamble_span(answer, "es") is None


def test_ordinary_sentence_with_no_opener_is_left_alone() -> None:
    answer = "The delivery cost is 5 USD. Thank you for asking about it later."
    assert leading_preamble_span(answer, "en") is None
    assert strip_leading_preamble(answer, "en") == answer


def test_unrecognised_language_has_no_table_and_is_left_alone() -> None:
    answer = "Buna intrebare. Costul de livrare este 5 USD."
    assert leading_preamble_span(answer, "ro") is None
    assert strip_leading_preamble(answer, "ro") == answer


def test_preamble_only_answer_is_never_emptied() -> None:
    answer = "Certainly!"
    assert strip_leading_preamble(answer, "en") == answer


def test_empty_answer_returns_none_span() -> None:
    assert leading_preamble_span("", "en") is None
    assert strip_leading_preamble("", "en") == ""


def test_strip_leading_preamble_is_deterministic() -> None:
    answer = "Great question! The delivery cost is 5 USD."
    assert strip_leading_preamble(answer, "en") == strip_leading_preamble(answer, "en")


# --- overclaim_findings -----------------------------------------------------


def test_overclaim_flags_a_phone_number_for_an_unsupported_phone_field() -> None:
    coverage = _coverage(frozenset({"phone"}))
    answer = "You can call the office at +254 20 2026869. Delivery takes 3 days."
    findings = overclaim_findings(answer, coverage)
    assert findings == ["You can call the office at +254 20 2026869."]


def test_overclaim_flags_an_email_for_an_unsupported_email_field() -> None:
    coverage = _coverage(frozenset({"email"}))
    answer = "Email us at info@example.com for details."
    assert overclaim_findings(answer, coverage) == [answer]


def test_overclaim_flags_a_website_for_an_unsupported_website_field() -> None:
    coverage = _coverage(frozenset({"website"}))
    answer = "Visit www.example.com for more information."
    assert overclaim_findings(answer, coverage) == [answer]


def test_overclaim_reports_nothing_when_nothing_is_unsupported() -> None:
    coverage = _coverage(frozenset())
    answer = "You can call the office at +254 20 2026869."
    assert overclaim_findings(answer, coverage) == []


def test_overclaim_reports_nothing_for_an_unsupported_field_with_no_pattern() -> None:
    # address/business_hours/payment_methods/delivery_cost/delivery_time are
    # deliberately not checked (documented limitation: no safe shape).
    coverage = _coverage(frozenset({"address"}))
    answer = "Our office is on Main Street."
    assert overclaim_findings(answer, coverage) == []


def test_overclaim_does_not_flag_a_supported_field() -> None:
    # phone unsupported, but the sentence with the phone number is only
    # flagged when phone actually is in coverage.unsupported.
    coverage = _coverage(frozenset({"email"}))
    answer = "You can call the office at +254 20 2026869."
    assert overclaim_findings(answer, coverage) == []


def test_overclaim_never_edits_the_answer() -> None:
    coverage = _coverage(frozenset({"phone"}))
    answer = "You can call the office at +254 20 2026869."
    overclaim_findings(answer, coverage)
    assert answer == "You can call the office at +254 20 2026869."


# --- confidence_framing_key --------------------------------------------------


def test_confidence_framing_key_for_partial_answer_with_gap() -> None:
    coverage = _coverage(frozenset({"email"}))
    assert confidence_framing_key(OutcomeKind.PARTIAL_ANSWER, coverage) == "partial_answer_gap"


def test_confidence_framing_key_is_none_for_full_answer() -> None:
    coverage = _coverage(frozenset())
    assert confidence_framing_key(OutcomeKind.ANSWER, coverage) is None


def test_confidence_framing_key_is_none_when_partial_but_nothing_unsupported() -> None:
    coverage = _coverage(frozenset())
    assert confidence_framing_key(OutcomeKind.PARTIAL_ANSWER, coverage) is None


def test_confidence_framing_key_is_none_for_other_outcome_kinds() -> None:
    coverage = _coverage(frozenset({"email"}))
    assert confidence_framing_key(OutcomeKind.EVIDENCE_MISSING, coverage) is None
    assert confidence_framing_key(OutcomeKind.CLARIFICATION, coverage) is None
    assert confidence_framing_key(OutcomeKind.SAFETY_REFUSAL, coverage) is None

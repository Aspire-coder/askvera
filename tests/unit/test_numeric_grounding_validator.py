from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationContext, ValidationResult
from app.response.quality import has_incomplete_ending
from app.validation.validators.numeric_grounding_validator import NumericGroundingValidator, remove_unsupported_numeric_sentences
import pytest


@pytest.mark.parametrize('extra', [
    'Office hours are 09.00 am to 17.00 pm Monday through Friday.',
    'A fee of 12.50 applies, with a maximum of 18.75.',
    'Une commission de 12,50 euros et de 18,75 euros est requise.',
    'Office hours are 09.00 am to 17.00 pm Monday through Friday',
    'If active, you need 2 Case Credits in the U.S. to receive benefits.',
])
def test_numeric_repair_removes_whole_sentence_with_decimal_values(extra):
    grounded = 'The office telephone is +31 88 646 0200.'
    context = _context(grounded + '\n\n' + extra, 'Telephone Office +31 88 646 0200')
    repaired, removed = remove_unsupported_numeric_sentences(
        context.chat_response.answer, context.retrieval_result.documents)
    assert removed
    assert repaired == grounded


def test_numeric_repair_keeps_adjacent_grounded_decimal_sentence():
    supported = 'The service fee is 2.50.'
    context = _context('The delivery fee is 18.75. ' + supported, supported)
    repaired, removed = remove_unsupported_numeric_sentences(
        context.chat_response.answer, context.retrieval_result.documents)
    assert removed == ['18.75']
    assert repaired == supported


@pytest.mark.parametrize('value', ['18', '18.75', '18,75'])
def test_numeric_grounding_checks_values_before_sentence_period(value):
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(f'The service fee is {value}.', 'The service fee is 2.50.'), result)
    assert result.has_critical()


@pytest.mark.parametrize("answer,source", [
    ("The Belgium office telephone number is +31 88 646 0200. You can also email support.",
     "Forever Belgium Telephone Office +31 88 646 0200 (Reception, Netherlands)"),
    ("Le numéro du bureau en Belgique est +31 88 646 0200.",
     "Telephone Office +31 88 646 0200 (Reception, Netherlands)"),
    ("Call Customer Service at 1-888-440-ALOE (2563). You can reach them for orders.",
     "Call Customer Care at 1-888- 440-ALOE (2563)."),
])
def test_source_grounded_contact_survives_wording_change(answer, source):
    context = _context(answer, source)
    result = ValidationResult()
    NumericGroundingValidator().validate(context, result)
    assert result.valid
    assert remove_unsupported_numeric_sentences(answer, context.retrieval_result.documents) == (answer, [])


@pytest.mark.parametrize("answer,source", [
    ("Belgium telephone: +31 88 646 0299.", "Telephone Office +31 88 646 0200"),
    ("Telephone Office: +31 88 646 0299.", "Telephone Office +31 88 646 0200"),
    ("Call Customer Care at 1-888-440-ALOE (2999).", "Call Customer Care at 1-888-440-ALOE (2563)."),
    ("Belgium telephone: +31 88 646 0200.", "Telephone Office +31 88 646. Order count: 0200"),
    ("Recognized Manager needs 120 CC.", "Assistant Supervisor needs 120 CC."),
])
def test_contact_fix_does_not_approve_wrong_numbers(answer, source):
    result = ValidationResult()
    NumericGroundingValidator().validate(_context(answer, source), result)
    assert not result.valid


def _context(answer: str, source_text: str, metadata: dict | None = None) -> ValidationContext:
    return ValidationContext(
        chat_response=ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.9,
            metadata={},
            correlation_id="test-correlation",
        ),
        correlation_id="test-correlation",
        country="CA",
        language="en",
        role="new-prospect",
        retrieval_result=RetrievalResult(
            documents=[
                RetrievedDocument(
                    id="doc-1",
                    title="CA-EN-Company-Policy.pdf",
                    content=source_text,
                    source="s3://example/CA-EN-Company-Policy.pdf",
                    page="6.0",
                    metadata=metadata or {},
                )
            ],
            citations=[],
            confidence=0.9,
        ),
    )


def test_numeric_grounding_accepts_claim_present_in_source() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Supervisor is achieved by generating 10 Open Group Case Credits within any Month.",
            "Supervisor is achieved by generating a total of 10 Open Group Case Credits within any Month.",
        ),
        result,
    )

    assert result.valid
    assert result.issues == []


def test_numeric_grounding_accepts_equivalent_decimal_separator() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "The minimum FBO order size is 50.00 in products, excluding VAT and literature.",
            "Minimum order size FBO: 50,00 in products excl. VAT and excl. literature.",
            {"access_scope": "global", "directory_section": "sponsoring"},
        ),
        result,
    )

    assert result.valid
    assert result.issues == []


def test_numeric_grounding_does_not_treat_thousands_separator_as_decimal() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "The threshold is 1.000 Case Credits.",
            "The threshold is 1,000 Case Credits.",
        ),
        result,
    )

    assert result.has_critical()


def test_numeric_grounding_ignores_bracketed_source_reference() -> None:
    result = ValidationResult()
    context = _context(
        "Supervisor requires 10 Open Group Case Credits [3].",
        "Supervisor is achieved by generating a total of 10 Open Group Case Credits.",
    )
    NumericGroundingValidator().validate(context, result)
    assert not result.has_critical()


def test_numeric_repair_removes_only_unsupported_sentence() -> None:
    context = _context(
        "Supervisor requires 10 Open Group Case Credits. You must also wait 3 years.",
        "Supervisor is achieved by generating a total of 10 Open Group Case Credits.",
    )
    repaired, removed = remove_unsupported_numeric_sentences(
        context.chat_response.answer,
        context.retrieval_result.documents,
    )
    assert repaired == "Supervisor requires 10 Open Group Case Credits."
    assert removed == ["3"]


def test_numeric_grounding_blocks_claim_absent_from_source() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Supervisor requires 60 Open Group Case Credits in 1-2 months.",
            "Supervisor is achieved by generating a total of 10 Open Group Case Credits within any Month.",
        ),
        result,
    )

    assert result.has_critical()
    assert result.issues[0].code == "NUMERIC_CLAIM_UNGROUNDED"


def test_numeric_grounding_blocks_claim_attached_to_wrong_subject() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Assistant Manager requires 120 Open Group Case Credits in 1-2 consecutive months.",
            (
                "Assistant Manager is achieved by generating a total of 75 Open Group Case Credits. "
                "Manager is achieved by generating 120 Open Group Case Credits in 1-2 consecutive Months."
            ),
        ),
        result,
    )

    assert result.has_critical()
    assert result.issues[0].code == "NUMERIC_CLAIM_UNGROUNDED"


def test_numeric_grounding_blocks_adjacent_rank_move_up_rule_confusion() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            (
                "To qualify as Assistant Manager, you need to meet one of these two paths: "
                "generate 120 Open Group Case Credits in 1-2 consecutive months, or "
                "150 Open Group Case Credits in 3-4 consecutive months."
            ),
            (
                "Assistant Manager is achieved by generating a total of 75 Open Group Case Credits "
                "within any two consecutive Months. "
                "Unrecognized Manager can re-qualify as a Recognized Manager by generating a total "
                "of 120 Open Group Case Credits within 1-2 consecutive Months, or 150 Open Group "
                "Case Credits within 3-4 consecutive Months."
            ),
        ),
        result,
    )

    assert result.has_critical()
    assert result.issues[0].code == "NUMERIC_CLAIM_UNGROUNDED"


def test_numeric_grounding_allows_correct_adjacent_rank_move_up_rule() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "To qualify as Assistant Manager, you need 75 Open Group Case Credits within any two consecutive months.",
            (
                "Assistant Manager is achieved by generating a total of 75 Open Group Case Credits "
                "within any two consecutive Months. "
                "Manager is achieved by generating a total of 120 Open Group Case Credits within "
                "1-2 consecutive Months."
            ),
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_hyphenated_month_format_from_source() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Assistant Supervisor requires 2 Open Group Case Credits within any 2 consecutive months.",
            (
                "An FBO reaches the level of Assistant Supervisor by generating a total of "
                "2 Open Group Case Credits in any single Operating Company within any "
                "2-consecutive-Month period."
            ),
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_processing_month_source_phrase() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "NEW Case Credits are accumulated for 12 months after someone qualifies as Recognized Manager.",
            (
                "NEW Case Credits will be accumulated for 12 processing months "
                "including the month in which he/she qualified as Recognized Manager."
            ),
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_same_subject_number_with_different_language_unit_wording() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "NEW Case Credits are accumulated for 12 mois after qualification.",
            "NEW Case Credits will be accumulated for 12 mois de traitement after qualification.",
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_french_numeric_rule_without_english_unit_terms() -> None:
    """Numeric grounding must rely on source evidence, not an English unit list."""
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Le Directeur regional exige 75 credits en 2 mois.",
            "Le Directeur regional est atteint avec 75 credits en 2 mois.",
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_keeps_russian_list_rule_attached_to_heading() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            (
                "Чтобы стать Признанным Менеджером, выполните требование:\n"
                "1. Объём продаж:\n"
                "- 120 Личных и Неменеджерских КБ в течение двух месяцев."
            ),
            (
                "Непризнанный менеджер может квалифицироваться на статус Признанного Менеджера, "
                "выполнив следующие требования:\n"
                "1) Выполнение объема в 120 Личных и Неменеджерских КБ в течение двух месяцев."
            ),
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_blocks_russian_number_for_wrong_rank() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Ассистент Менеджера должен выполнить 120 КБ в течение двух месяцев.",
            (
                "Ассистент Менеджера должен выполнить 75 КБ в течение двух месяцев. "
                "Признанный Менеджер должен выполнить 120 КБ в течение двух месяцев."
            ),
        ),
        result,
    )

    assert result.has_critical()
    assert result.issues[0].code == "NUMERIC_CLAIM_UNGROUNDED"


def test_numeric_grounding_normalizes_unicode_range_dashes() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Признанный Менеджер должен выполнить 120 КБ в течение 1–2 месяцев.",
            "Признанный Менеджер должен выполнить 120 КБ в течение 1-2 месяцев.",
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_does_not_match_number_inside_larger_number() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Assistant Supervisor requires 2 Open Group Case Credits.",
            "Assistant Supervisor is achieved by generating 12 Open Group Case Credits.",
        ),
        result,
    )

    assert result.has_critical()
    assert result.issues[0].code == "NUMERIC_CLAIM_UNGROUNDED"


def test_numeric_grounding_allows_correctly_paraphrased_claim() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "To qualify as Assistant Manager, you'll need 75 Open Group Case Credits.",
            "Assistant Manager is achieved by generating a total of 75 Open Group Case Credits.",
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_long_wrapped_policy_clause() -> None:
    """A PDF-wrapped clause may place the subject well before its numeric rule."""
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "A Recognized Manager needs 120 Open Group Case Credits.",
            (
                "A Recognized Manager qualifies after meeting the policy requirements and "
                "maintaining the required activity in the applicable Operating Company, with "
                "the relevant qualification period determined under the marketing plan, by "
                "generating a total of 120 Open Group Case Credits."
            ),
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_uses_nearby_previous_sentence_subject() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "For Assistant Manager, the requirement is straightforward. You'll need 75 Open Group Case Credits.",
            "Assistant Manager is achieved by generating a total of 75 Open Group Case Credits.",
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_blocks_percentage_attached_to_wrong_subject() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Active Assistant Manager also receives 8% Volume Bonus.",
            (
                "The Active Assistant Manager also receives 5% Volume Bonus. "
                "The Active Manager also receives 8% Volume Bonus."
            ),
        ),
        result,
    )

    assert result.has_critical()
    assert result.issues[0].code == "NUMERIC_CLAIM_UNGROUNDED"


def test_numeric_grounding_allows_percentage_attached_to_correct_subject() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Active Assistant Manager also receives 5% Volume Bonus.",
            (
                "The Active Assistant Manager also receives 5% Volume Bonus. "
                "The Active Manager also receives 8% Volume Bonus."
            ),
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_answers_without_measurable_claims() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Supervisor is the next level after Assistant Supervisor.",
            "Supervisor is achieved by generating a total of 10 Open Group Case Credits within any Month.",
        ),
        result,
    )

    assert result.valid
    assert result.issues == []


def test_numeric_grounding_allows_exact_directory_phone_across_languages() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Le numéro du bureau est le 52 55 3300 9400.",
            "Office Phone 1 52 55 3300 9400",
            metadata={"directory_section": "office", "access_scope": "global"},
        ),
        result,
    )

    assert not result.has_critical()


def test_numeric_grounding_allows_reformatted_directory_phone_across_languages() -> None:
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "Le numero du bureau est le +52 (55) 3383-6196.",
            "Admin. 2 Cell# 525533836196",
            metadata={"directory_section": "staff", "access_scope": "global"},
        ),
        result,
    )

    assert not result.has_critical()


_MANAGER_SOURCE = (
    "Section 5.01: Recognized Manager: (a) An FBO qualifies as a Recognized Manager when "
    "he/she has generated a total of 120 Case Credits within any 2 consecutive Months, "
    "of which at least 25 Case Credits must be from Personal sales."
)


@pytest.mark.parametrize("answer", [
    "To become a Recognized Manager you must generate 120 Case Credits within any 2 consecutive Months.",
    "How to Become a Recognized Manager\n\nYou must generate a total of 120 Case Credits "
    "within any 2 consecutive Months.",
    "## Recognized Manager Requirements\n\nYou need 120 Case Credits in any 2 consecutive Months.",
    "**Recognized Manager Qualification**\n\nA total of 120 Case Credits is required.",
    "A Recognized Manager requires:\n\n* 120 Case Credits within 2 consecutive Months",
])
def test_headings_do_not_break_numeric_subject_binding(answer) -> None:
    """A heading must not detach a number from the subject that grounds it.

    Observed live 2026-09-07: "how can i become a recognized manager" retrieved
    the right sections at confidence 0.95 and generated a correct answer, which
    then failed output validation with NUMERIC_CLAIM_UNGROUNDED on 120 - a figure
    stated in the cited source - and was replaced by the insufficient-evidence
    fallback.

    Two causes. Phrase extraction discarded line breaks, merging a heading into
    the sentence below it ("Recognized Manager You"). And token spans covered only
    suffixes, so a trailing word ("Recognized Manager Requirements") left no span
    present in the source. Answers of this shape all use headings, which is why a
    retrieval-only canary never saw it.
    """
    result = ValidationResult()
    NumericGroundingValidator().validate(_context(answer, _MANAGER_SOURCE), result)
    assert result.valid


@pytest.mark.parametrize("answer", [
    "How to Become a Recognized Manager\n\nYou must generate 450 Case Credits.",
    "## Recognized Manager Requirements\n\nYou need 999 Case Credits.",
    "A Recognized Manager earns a 35% bonus on all downline sales.",
])
def test_headings_do_not_let_an_invented_number_through(answer) -> None:
    """Wider subject spans must not weaken the grounding check itself."""
    result = ValidationResult()
    NumericGroundingValidator().validate(_context(answer, _MANAGER_SOURCE), result)
    assert result.has_critical()


def test_repair_does_not_orphan_a_bracket_and_break_the_answer() -> None:
    """Removing a sentence must not leave half a parenthetical behind.

    Measured at 1 in 10 on "How can i become a recognized manager?" against the
    deployed build. The model wrote a parenthetical aside containing an
    ungrounded number, repair deleted that sentence, the stray ")" survived, and
    the integrity validator read the unbalanced text as truncated - replacing a
    complete, correct, cited answer with "the approved policy documents do not
    contain enough information".
    """
    source = "A Recognized Manager must generate 120 Open Group Case Credits within 2 consecutive Months."
    answer = (
        "# Becoming a Recognized Manager\n\n"
        "You must generate 120 Open Group Case Credits. "
        "(There is an exception: a Downline FBO earning 999 Case Credits may still qualify. "
        "Contact support for details.)\n\n"
        "Maintain Active status throughout."
    )
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, _context(answer, source).retrieval_result.documents)

    assert removed == ["999"]
    assert repaired.count("(") == repaired.count(")")
    assert not has_incomplete_ending(repaired, "en")
    assert "120" in repaired


def test_repair_leaves_a_matched_pair_untouched() -> None:
    """Only orphaned delimiters are dropped, never a balanced pair."""
    source = (
        "A Recognized Manager must generate 120 Open Group Case Credits within 2 "
        "consecutive Months (see Section 5.01)."
    )
    answer = "You need 120 Open Group Case Credits (see Section 5.01) within 2 consecutive Months."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, _context(answer, source).retrieval_result.documents)

    assert removed == []
    assert repaired == answer


def test_a_heading_does_not_supply_the_numeric_subject() -> None:
    """The subject comes from the claim's sentence, not the heading above it.

    Measured live on rank-qualification questions. "Requirements to Reach
    Supervisor" supplied {reach, supervisor}; every subject token must appear in
    the source window, and the source says "Supervisor is achieved by generating
    a total of 10 Open Group Case Credits", which has no "reach". The 10 was
    reported ungrounded, so the sentence stating the requirement was deleted from
    the answer, or the answer was replaced entirely.
    """
    source = (
        "Section 4.01: (b) Supervisor is achieved by generating a total of 10 Open Group "
        "Case Credits in any single Month."
    )
    answer = (
        "# Requirements to Reach Supervisor\n\n"
        "To achieve the Supervisor rank, you need to generate a total of "
        "**10 Open Group Case Credits within any single month**."
    )
    result = ValidationResult()
    NumericGroundingValidator().validate(_context(answer, source), result)
    assert result.valid


def test_a_colon_does_not_detach_the_subject() -> None:
    """A colon introduces a list inside the sentence and must not bound the subject.

    Without this, "To qualify as Assistant Manager ... two paths: generate 120"
    loses its subject after the colon, and a figure belonging to a different rank
    passes as grounded.
    """
    source = (
        "Assistant Manager is achieved by generating a total of 75 Open Group Case Credits. "
        "Unrecognized Manager can re-qualify by generating a total of 120 Open Group Case "
        "Credits within 1-2 consecutive Months."
    )
    answer = (
        "To qualify as Assistant Manager, you need one of these paths: "
        "generate 120 Open Group Case Credits in 1-2 consecutive months."
    )
    result = ValidationResult()
    NumericGroundingValidator().validate(_context(answer, source), result)
    assert result.has_critical()


class _HoursSource:
    """The directory writes office hours with dots: 09.00-17.00."""

    content = "Office hours: Monday to Friday 09.00-17.00. Telephone +32 2 555 1234."
    title = "International-Sponsoring-Directory.pdf - Forever Belgium"
    metadata: dict = {}


def _hours_flagged(answer: str, source=None) -> list[str]:
    from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims

    return [claim.number for claim in unsupported_numeric_claims(answer, [source or _HoursSource()])]


def test_office_hours_survive_a_notation_difference() -> None:
    """Observed live 2026-09-08 on the Belgium and Germany sponsoring records.

    The source writes 09.00-17.00 and the model writes 09:00-17:00, so every
    component was reported ungrounded and repair deleted the whole sentence.
    A distributor asking about an office silently lost its opening hours -
    among the most common practical uses of the directory.
    """
    assert _hours_flagged("The office is open Monday to Friday, 09:00-17:00.") == []


def test_office_hours_survive_a_twelve_hour_rewrite() -> None:
    """A model given 17.00 frequently writes 5:00 pm."""
    assert _hours_flagged("The office is open from 9:00 am to 5:00 pm.") == []


def test_a_single_grounded_time_survives() -> None:
    """A time at the end of a sentence is the ordinary case."""
    assert _hours_flagged("The office opens at 09:00.") == []


def test_invented_office_hours_are_still_removed() -> None:
    """The check must not become a blanket exemption for anything time-shaped."""
    assert _hours_flagged("The office is open Monday to Friday, 07:00-22:00.")


def test_a_half_invented_range_is_still_removed() -> None:
    """One real opening time must not launder an invented closing time."""
    assert _hours_flagged("The office is open 09:00-22:00.")


def test_an_invented_non_time_figure_is_still_removed() -> None:
    assert _hours_flagged("Every FBO receives 47 percent commission on retail orders.")


def test_the_hours_sentence_survives_repair() -> None:
    from app.validation.validators.numeric_grounding_validator import (
        remove_unsupported_numeric_sentences,
    )

    answer = "The Belgium office is open Monday to Friday, 09:00-17:00."
    repaired, removed = remove_unsupported_numeric_sentences(answer, [_HoursSource()])

    assert repaired == answer
    assert removed == []


class _UKHoursSource:
    """England, Ireland and Scotland write hours without minutes."""

    content = "Business Hours Office Monday - 9am - 6pm, Tuesday - 9am - 8pm"
    title = "International-Sponsoring-Directory.pdf - Forever England"
    metadata: dict = {}


def test_uk_office_hours_survive_a_24_hour_rewrite() -> None:
    """Three of the 113 records with hours use "9am - 6pm" and no minutes.

    The time pattern found nothing in those sources at all, so a model writing
    09:00-18:00 had nothing to match against and lost the hours.
    """
    assert _hours_flagged("The office is open 09:00-18:00 on Monday.", _UKHoursSource()) == []


def test_uk_office_hours_survive_when_echoed_verbatim() -> None:
    assert _hours_flagged("The office is open 9am - 6pm on Monday.", _UKHoursSource()) == []


def test_invented_uk_hours_are_still_removed() -> None:
    assert _hours_flagged("The office is open 05:00-23:00 on Monday.", _UKHoursSource())


class _SwedenSource:
    """The record has no delivery costs; only a lead time."""

    content = "Welcome to Forever Sweden! +46 31 727 8000. Average lead time for orders is 4-7 days."
    title = "International-Sponsoring-Directory.pdf - Forever Sweden"
    metadata: dict = {}


def test_a_lead_in_does_not_survive_the_content_it_promised() -> None:
    """Observed live 2026-09-08 for "what is the delivery cost for sweden?".

    A colon is not a sentence boundary, so the lead-in was kept while every
    figure beneath it was removed. The reader saw a heading over nothing and an
    unrelated fact below, which reads as a rendering fault and quietly loses
    the question that was asked.
    """
    from app.validation.validators.numeric_grounding_validator import (
        remove_unsupported_numeric_sentences,
    )

    answer = (
        "For Sweden, the delivery costs are:\n"
        "- SEK 95.00 for orders below SEK 1,500.00\n"
        "- Free delivery for orders above SEK 1,500.00\n\n"
        "The average lead time for orders to arrive in Sweden is 4-7 days."
    )
    repaired, removed = remove_unsupported_numeric_sentences(answer, [_SwedenSource()])

    assert removed, "the invented costs should still be removed"
    assert "delivery costs are:" not in repaired
    assert repaired == "The average lead time for orders to arrive in Sweden is 4-7 days."


def test_a_lead_in_whose_list_survives_is_kept() -> None:
    """Only a lead-in left with nothing is orphaned; the rest are doing their job."""
    from app.validation.validators.numeric_grounding_validator import (
        remove_unsupported_numeric_sentences,
    )

    class _Source:
        content = "Requirements: generate 120 Case Credits and sponsor 2 Supervisors."
        title = "US-EN-Company-Policy.pdf"
        metadata: dict = {}

    answer = (
        "To qualify you must meet these requirements:\n"
        "- Generate 120 Case Credits\n"
        "- Sponsor 2 Supervisors"
    )
    repaired, removed = remove_unsupported_numeric_sentences(answer, [_Source()])

    assert removed == []
    assert repaired == answer


def test_prose_after_a_colon_line_does_not_keep_an_orphaned_lead_in() -> None:
    """Ordinary prose beneath a lead-in is a new statement, not its content."""
    from app.validation.validators.numeric_grounding_validator import _drop_orphaned_lead_ins

    text = "The costs are:\n\nOur office is open on weekdays."
    assert _drop_orphaned_lead_ins(text) == "Our office is open on weekdays."


class _AlgeriaSource:
    """The directory writes amounts space-grouped and continental."""

    content = (
        "Forever Algeria. Minimum order size FBO: 0,200CC as a first order for "
        "Preferred Customers, 7 800DZD ($60) and the equivalent in local currency."
    )
    title = "International-Sponsoring-Directory.pdf - Forever Algeria"
    metadata: dict = {}


def _algeria_flagged(answer: str) -> list[str]:
    from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims

    return [claim.number for claim in unsupported_numeric_claims(answer, [_AlgeriaSource()])]


@pytest.mark.parametrize(
    "answer",
    [
        "For a new FBO in Algeria, the minimum first order is 7,800 DZD (about $60).",
        "For a new FBO in Algeria, the minimum first order is 7800 DZD (about $60).",
        "For a new FBO in Algeria, the minimum first order is 7 800DZD ($60).",
        "A new FBO in Algeria must place a first order of 0.200 CC.",
        "A new FBO in Algeria must place a first order of 0,200CC.",
    ],
)
def test_algeria_minimum_order_survives_every_notation(answer: str) -> None:
    """Observed live 2026-09-08. Retrieval, ranking and approval all succeeded -
    Forever Algeria scored 9.542 with a margin of 8.44 - and the reader still
    got "the approved policy documents do not contain enough information".

    The record states "0,200CC" and "7 800DZD"; a model asked in English writes
    "0.200" and "7,800". Neither was found, the sentence was deleted, and with
    nothing left the answer fell back. Four of six natural renderings produced
    an empty answer.
    """
    assert _algeria_flagged(answer) == [], answer


@pytest.mark.parametrize(
    "answer",
    [
        "The minimum first order in Algeria is 99,000 DZD.",
        "A new FBO in Algeria must place a first order of 5,000 CC.",
    ],
)
def test_invented_algeria_amounts_are_still_removed(answer: str) -> None:
    """Tolerating notation must not become tolerating a wrong figure."""
    assert _algeria_flagged(answer)


def test_a_leading_zero_makes_a_three_digit_tail_unambiguous() -> None:
    """"0,200" cannot be a thousands group; that would just be "200"."""
    from app.validation.validators.numeric_grounding_validator import _number_variants

    assert "0.200" in _number_variants("0,200")
    assert "0,200" in _number_variants("0.200")


def test_a_grouped_thousand_is_offered_ungrouped_but_never_swapped() -> None:
    """"7,800" must be able to reach a source writing "7 800".

    The ungrouped form is offered as an alternative, never as a replacement, so
    "1.000" still cannot find "1,000" and the thousandfold confusion stays
    caught by the test above.
    """
    from app.validation.validators.numeric_grounding_validator import _number_variants

    assert "7800" in _number_variants("7,800")
    assert "1,000" not in _number_variants("1.000")


class _NewZealandSource:
    """A directory record states the country once, at the top, not per bullet."""

    content = (
        "Forever New Zealand. • Minimum order size: $100 +gst. "
        "• Delivery Cost: $8 +gst ($9,20). "
        "• Local Product Centers available: Yes, 278 Manukau Rd. Epsom."
    )
    title = "International-Sponsoring-Directory.pdf - Forever New Zealand"
    metadata: dict = {}


class _RankSource:
    content = (
        "Supervisor is achieved by generating a total of 10 Open Group Case Credits "
        "within any single Month. Assistant Manager requires 120 Case Credits."
    )
    title = "US-EN-Company-Policy.pdf - Sec 4.01-b: Supervisor"
    metadata: dict = {}


def _flagged(answer: str, source) -> list[str]:
    from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims

    return [claim.number for claim in unsupported_numeric_claims(answer, [source])]


def test_naming_the_market_does_not_make_a_figure_ungroundable() -> None:
    """Observed live 2026-09-08, deleting $8 and $9.20 from a delivery answer.

    The record states "• Delivery Cost: $8 +gst ($9,20)." and the answer said
    "For New Zealand, the delivery cost is $8 +GST ($9.20)." The subject became
    {new, zealand}, every subject token must appear in the local source window,
    and that bullet does not repeat the country - the country is the record's
    identity. Removing the country from the sentence made the same answer
    ground cleanly, which is backwards: naming the market is what a good answer
    does, and the prompt asks for it.
    """
    assert _flagged("For New Zealand, the delivery cost is $8 +GST ($9.20).", _NewZealandSource()) == []


def test_the_same_answer_without_the_market_still_grounds() -> None:
    """The behaviour that used to be the only one that worked."""
    assert _flagged("The delivery cost is $8 +GST ($9.20).", _NewZealandSource()) == []


def test_an_invented_figure_beside_the_market_is_still_removed() -> None:
    """Forgiving the market must not forgive the number."""
    assert _flagged("For New Zealand, the delivery cost is $42 +GST.", _NewZealandSource())


def test_rank_binding_is_not_weakened_by_the_market_exemption() -> None:
    """Only the market is established by the document, never an arbitrary subject.

    A figure belonging to a different rank must still be caught, which is the
    protection several earlier fixes were written to build.
    """
    assert _flagged("Assistant Manager requires 10 Case Credits.", _RankSource())
    assert _flagged("Supervisor requires 999 Open Group Case Credits.", _RankSource())
    assert _flagged("Supervisor requires 10 Open Group Case Credits.", _RankSource()) == []


def test_a_pm_time_is_not_grounded_by_an_am_source() -> None:
    """External review, 2026-09-08. A defect introduced earlier the same day.

    A meridiem yields one value, not two. Keeping the bare hour alongside the
    24-hour form meant "5:00 pm" carried both 0500 and 1700, so a source
    reading "5:00 am" exempted it from deletion.

    Asserted on the exemption itself: the claim may still ground through the
    literal number path, which binds a figure by its presence anywhere in the
    source and is a separate, wider weakness.
    """
    from app.validation.validators.numeric_grounding_validator import (
        _grounded_time_spans,
        _normalize,
    )

    assert _grounded_time_spans("Opens at 5:00 pm.", [_normalize("Opens at 5:00 am.")]) == []
    assert _grounded_time_spans("Opens at 5:00 pm.", [_normalize("Opens at 5:00 pm.")]) != []


def test_a_decimal_is_not_a_clock_without_a_clock_context() -> None:
    """External review, 2026-09-08. The other defect from the same day.

    "9.00" in "the fee is 9.00 dollars" matched the clock pattern and was
    exempted by an unrelated "09:00" in the source, letting an invented amount
    through. A comment in this file called that harmless. It was not.
    """

    class _ClockSource:
        content = "Opens at 09:00."
        title = "Forever Belgium"
        metadata: dict = {}

    assert _hours_flagged("The fee is 9.00 dollars.", _ClockSource())


def test_a_dotted_time_still_counts_inside_a_range() -> None:
    """"09.00-17.00" has no meridiem and is unmistakably a clock range."""

    class _Source:
        content = "Business Hours Office 09.00 am - 17.00 pm (Mon - Fri)."
        title = "Forever Belgium"
        metadata: dict = {}

    assert _hours_flagged("The office is open 09.00-17.00.", _Source()) == []


def test_a_redundant_meridiem_on_a_24_hour_value_is_accepted() -> None:
    """The directory writes "17.00 pm" throughout: 24-hour with a spare marker.

    Refusing it broke every Belgium case when this fix was first written.
    """

    class _Source:
        content = "Business Hours Office 09.00 am - 17.00 pm (Mon - Fri)."
        title = "Forever Belgium"
        metadata: dict = {}

    assert _hours_flagged("The office is open 09:00-17:00.", _Source()) == []


def test_an_impossible_clock_reading_is_not_exempted() -> None:
    class _Source:
        content = "Business Hours Office 09.00 am - 17.00 pm."
        title = "Forever Belgium"
        metadata: dict = {}

    assert _hours_flagged("The office is open at 45:99.", _Source())


def test_short_figure_is_not_grounded_by_digits_inside_a_phone_number() -> None:
    """A directory record must not ground an invented figure by coincidence.

    Stripping every separator and asking whether the digits appear anywhere
    makes a short number trivially groundable: "50" is four digits into
    "+213 21 50 60 70". The digit-substring path exists for phone reformatting,
    so it is limited to runs long enough to be a phone number.
    """
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "The minimum first order is 50 Case Credits.",
            "Forever Algeria Office Phone +213 21 50 60 70 Fax +213 21 50 60 71",
            metadata={"directory_section": "office", "access_scope": "global"},
        ),
        result,
    )

    assert result.has_critical()


def test_directory_phone_reformatting_is_still_accepted() -> None:
    """The tightening must not undo what the digit path was added for."""
    result = ValidationResult()
    NumericGroundingValidator().validate(
        _context(
            "You can reach the office on +52 (55) 3383-6196.",
            "Admin. 2 Cell# 525533836196",
            metadata={"directory_section": "staff", "access_scope": "global"},
        ),
        result,
    )

    assert not result.has_critical()

from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationContext, ValidationResult
from app.validation.validators.numeric_grounding_validator import NumericGroundingValidator


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

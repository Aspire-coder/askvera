from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationContext, ValidationResult
from app.validation.validators.numeric_grounding_validator import NumericGroundingValidator


def _context(answer: str, source_text: str) -> ValidationContext:
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

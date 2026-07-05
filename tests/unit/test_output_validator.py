"""Unit tests for output validation."""

from app.response.models import ChatResponse
from app.validation import OutputValidator, ValidationContext
from app.validation.validators import AnswerValidator, ConfidenceValidator, LengthValidator, MetadataValidator


def _chat_response(answer="Answer", confidence=0.8, metadata=None) -> ChatResponse:
    return ChatResponse(
        answer=answer,
        citations=[],
        suggestions=[],
        cards=[],
        confidence=confidence,
        metadata={} if metadata is None else metadata,
        correlation_id="cid",
    )


def _context(chat_response: ChatResponse) -> ValidationContext:
    return ValidationContext(
        chat_response=chat_response,
        correlation_id="cid",
        country="US",
        language="en",
        role="new_prospect",
    )


def _validator() -> OutputValidator:
    return OutputValidator(
        [
            AnswerValidator(),
            ConfidenceValidator(),
            MetadataValidator(),
            LengthValidator(),
        ]
    )


def test_empty_answer_is_critical() -> None:
    result = _validator().validate(_context(_chat_response(answer="")))

    assert result.valid is False
    assert result.has_critical() is True
    assert result.issues[0].code == "ANSWER_EMPTY"


def test_missing_answer_is_critical() -> None:
    result = _validator().validate(_context(_chat_response(answer=None)))

    assert result.valid is False
    assert result.has_critical() is True
    assert result.issues[0].field == "answer"


def test_whitespace_answer_is_critical() -> None:
    result = _validator().validate(_context(_chat_response(answer="   ")))

    assert result.valid is False
    assert result.has_critical() is True


def test_confidence_above_one_is_error() -> None:
    result = _validator().validate(_context(_chat_response(confidence=1.2)))

    assert result.valid is False
    assert result.has_errors() is True
    assert result.issues[0].code == "CONFIDENCE_OUT_OF_RANGE"


def test_confidence_below_zero_is_error() -> None:
    result = _validator().validate(_context(_chat_response(confidence=-0.1)))

    assert result.valid is False
    assert result.has_errors() is True
    assert result.issues[0].field == "confidence"


def test_missing_metadata_is_error() -> None:
    result = _validator().validate(_context(_chat_response(metadata=None)))

    assert result.valid is True
    assert result.issues == []

    broken_response = _chat_response()
    object.__setattr__(broken_response, "metadata", None)
    result = _validator().validate(_context(broken_response))

    assert result.valid is False
    assert result.issues[0].code == "METADATA_MISSING"


def test_long_response_is_error() -> None:
    result = _validator().validate(_context(_chat_response(answer="x" * 10001)))

    assert result.valid is False
    assert result.issues[0].code == "ANSWER_TOO_LONG"


def test_valid_response_passes() -> None:
    result = _validator().validate(_context(_chat_response()))

    assert result.valid is True
    assert result.issues == []

"""Unit tests for output validation."""

from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation import OutputValidator, ValidationContext
from app.validation.validators import (
    AnswerValidator,
    CitationValidator,
    ConfidenceValidator,
    LanguageValidator,
    LengthValidator,
    MetadataValidator,
)


def _chat_response(answer="Answer", confidence=0.8, metadata=None, citations=None) -> ChatResponse:
    return ChatResponse(
        answer=answer,
        citations=[] if citations is None else citations,
        suggestions=[],
        cards=[],
        confidence=confidence,
        metadata={} if metadata is None else metadata,
        correlation_id="cid",
    )


def _context(chat_response: ChatResponse, retrieval_result=None) -> ValidationContext:
    return ValidationContext(
        chat_response=chat_response,
        correlation_id="cid",
        country="US",
        language="en",
        role="new_prospect",
        retrieval_result=retrieval_result,
    )


def _validator() -> OutputValidator:
    return OutputValidator(
        [
            AnswerValidator(),
            ConfidenceValidator(),
            CitationValidator(),
            LanguageValidator(),
            MetadataValidator(),
            LengthValidator(),
        ]
    )


def _retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        documents=[
            RetrievedDocument(
                id="doc-1",
                title="Policy",
                content="Policy content",
                source="s3://bucket/policy.pdf",
                score=0.9,
            )
        ],
        citations=[],
        confidence=0.9,
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


def test_missing_citations_warns_when_documents_were_retrieved() -> None:
    result = _validator().validate(_context(_chat_response(), _retrieval_result()))

    assert result.valid is True
    assert result.issues[0].code == "CITATIONS_MISSING"


def test_citations_pass_when_documents_were_retrieved() -> None:
    response = _chat_response(citations=[{"title": "Policy", "uri": "s3://bucket/policy.pdf"}])
    result = _validator().validate(_context(response, _retrieval_result()))

    assert result.valid is True
    assert result.issues == []


def test_incomplete_citation_warns_when_documents_were_retrieved() -> None:
    response = _chat_response(citations=[{"title": "Policy"}])
    result = _validator().validate(_context(response, _retrieval_result()))

    assert result.valid is True
    assert result.issues[0].code == "CITATIONS_INCOMPLETE"


def test_citation_source_alias_passes() -> None:
    response = _chat_response(citations=[{"title": "Policy", "source": "s3://bucket/policy.pdf"}])
    result = _validator().validate(_context(response, _retrieval_result()))

    assert result.valid is True
    assert result.issues == []


def test_language_mismatch_warns() -> None:
    response = _chat_response(metadata={"language": "fr"})
    result = _validator().validate(_context(response))

    assert result.valid is True
    assert result.issues[0].code == "LANGUAGE_MISMATCH"


def test_language_locale_match_passes() -> None:
    response = _chat_response(metadata={"language": "en-US"})
    result = _validator().validate(_context(response))

    assert result.valid is True
    assert result.issues == []


def test_missing_language_metadata_passes() -> None:
    result = _validator().validate(_context(_chat_response(metadata={})))

    assert result.valid is True
    assert result.issues == []


def test_valid_response_passes() -> None:
    result = _validator().validate(_context(_chat_response()))

    assert result.valid is True
    assert result.issues == []

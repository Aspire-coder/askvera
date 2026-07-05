"""Unit tests for validation metadata attachment."""

from app.validation import ValidationIssue, ValidationResult, ValidationSeverity, validation_summary


def test_validation_metadata_is_attached_to_chat_response() -> None:
    result = ValidationResult()
    result.add_issue(
        ValidationIssue(
            code="CITATIONS_INCOMPLETE",
            message="Citation missing source fields.",
            severity=ValidationSeverity.WARNING,
            field="citations",
        )
    )

    summary = validation_summary(result)

    assert summary["valid"] is True
    assert summary["highestSeverity"] == "WARNING"
    assert summary["issueCount"] == 1
    assert summary["issues"][0]["code"] == "CITATIONS_INCOMPLETE"


def test_validation_metadata_records_clean_responses() -> None:
    summary = validation_summary(ValidationResult())

    assert summary["valid"] is True
    assert summary["highestSeverity"] == "PASS"
    assert summary["issueCount"] == 0
    assert summary["issues"] == []

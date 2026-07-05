"""Confidence range validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class ConfidenceValidator:
    """Validate confidence is absent or within the normalized range."""

    name = "confidence"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        confidence = context.chat_response.confidence
        if confidence is None:
            return
        if confidence < 0 or confidence > 1:
            result.add_issue(
                ValidationIssue(
                    code="CONFIDENCE_OUT_OF_RANGE",
                    message="Chat response confidence must be between 0 and 1.",
                    severity=ValidationSeverity.ERROR,
                    field="confidence",
                )
            )

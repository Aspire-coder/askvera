"""Answer length validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class LengthValidator:
    """Validate response text is not absurdly long."""

    name = "length"
    max_answer_length = 10000

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        answer = context.chat_response.answer or ""
        if len(answer) > self.max_answer_length:
            result.add_issue(
                ValidationIssue(
                    code="ANSWER_TOO_LONG",
                    message="Chat response answer exceeds maximum length.",
                    severity=ValidationSeverity.ERROR,
                    field="answer",
                )
            )

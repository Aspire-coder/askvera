"""Answer presence validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class AnswerValidator:
    """Validate that a chat response has answer text."""

    name = "answer"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        answer = context.chat_response.answer
        if answer is None or not str(answer).strip():
            result.add_issue(
                ValidationIssue(
                    code="ANSWER_EMPTY",
                    message="Chat response answer is empty.",
                    severity=ValidationSeverity.CRITICAL,
                    field="answer",
                )
            )

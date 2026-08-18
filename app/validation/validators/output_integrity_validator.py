"""Reject broken or placeholder-bearing user-visible answers."""

from app.response.quality import contains_unresolved_placeholder, has_incomplete_ending
from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class OutputIntegrityValidator:
    """Fail closed when final answer formatting is visibly incomplete."""

    name = "output_integrity"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        answer = context.chat_response.answer or ""
        if contains_unresolved_placeholder(answer):
            result.add_issue(
                ValidationIssue(
                    code="UNRESOLVED_OUTPUT_PLACEHOLDER",
                    message="Chat response contains a user-visible placeholder.",
                    severity=ValidationSeverity.CRITICAL,
                    field="answer",
                )
            )
        if has_incomplete_ending(answer, context.language):
            result.add_issue(
                ValidationIssue(
                    code="INCOMPLETE_OUTPUT",
                    message="Chat response appears truncated or structurally incomplete.",
                    severity=ValidationSeverity.CRITICAL,
                    field="answer",
                )
            )

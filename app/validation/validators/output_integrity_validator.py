"""Reject broken or placeholder-bearing user-visible answers."""

from app.response.quality import (
    contains_internal_retrieval_language,
    contains_unresolved_placeholder,
    incomplete_ending_reason,
)
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
        # The message names the rule that fired. Rejecting an answer replaces it
        # with the insufficient-evidence fallback, and the rejected text is
        # never logged, so without the rule name a wrongly discarded answer
        # leaves nothing to diagnose.
        incomplete_reason = incomplete_ending_reason(answer, context.language)
        if incomplete_reason:
            result.add_issue(
                ValidationIssue(
                    code="INCOMPLETE_OUTPUT",
                    message=(
                        "Chat response appears truncated or structurally incomplete "
                        f"({incomplete_reason})."
                    ),
                    severity=ValidationSeverity.CRITICAL,
                    field="answer",
                )
            )
        if contains_internal_retrieval_language(answer):
            result.add_issue(
                ValidationIssue(
                    code="INTERNAL_RETRIEVAL_LANGUAGE",
                    message="Chat response exposes internal retrieval terminology.",
                    severity=ValidationSeverity.CRITICAL,
                    field="answer",
                )
            )

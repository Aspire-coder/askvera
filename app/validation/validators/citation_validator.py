"""Citation consistency validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class CitationValidator:
    """Warn when retrieved documents are not represented in response citations."""

    name = "citation"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return
        if context.chat_response.citations:
            return
        result.add_issue(
            ValidationIssue(
                code="CITATIONS_MISSING",
                message="Retrieved documents were available, but the chat response has no citations.",
                severity=ValidationSeverity.WARNING,
                field="citations",
            )
        )

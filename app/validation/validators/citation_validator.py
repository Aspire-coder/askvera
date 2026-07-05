"""Citation consistency validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class CitationValidator:
    """Warn when citations are missing or too thin for source tracing."""

    name = "citation"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return
        citations = context.chat_response.citations
        if not citations:
            result.add_issue(
                ValidationIssue(
                    code="CITATIONS_MISSING",
                    message="Retrieved documents were available, but the chat response has no citations.",
                    severity=ValidationSeverity.WARNING,
                    field="citations",
                )
            )
            return
        incomplete_count = sum(1 for citation in citations if self._is_incomplete(citation))
        if incomplete_count:
            result.add_issue(
                ValidationIssue(
                    code="CITATIONS_INCOMPLETE",
                    message="One or more citations are missing source tracing fields.",
                    severity=ValidationSeverity.WARNING,
                    field="citations",
                )
            )

    def _is_incomplete(self, citation: dict) -> bool:
        has_title = bool(citation.get("title"))
        has_source = bool(citation.get("uri") or citation.get("source"))
        return not (has_title and has_source)

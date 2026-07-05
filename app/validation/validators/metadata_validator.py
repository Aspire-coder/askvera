"""Metadata validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class MetadataValidator:
    """Validate response metadata exists."""

    name = "metadata"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        if context.chat_response.metadata is None:
            result.add_issue(
                ValidationIssue(
                    code="METADATA_MISSING",
                    message="Chat response metadata is missing.",
                    severity=ValidationSeverity.ERROR,
                    field="metadata",
                )
            )

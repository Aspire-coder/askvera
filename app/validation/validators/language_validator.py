"""Language consistency validator."""

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity


class LanguageValidator:
    """Warn when response metadata language conflicts with the selected language."""

    name = "language"

    metadata_keys = ("language", "response_language", "detected_language")

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        expected = _normalize_language(context.language)
        actual = self._language_from_metadata(context)
        if not expected or not actual:
            return
        if expected == actual:
            return
        result.add_issue(
            ValidationIssue(
                code="LANGUAGE_MISMATCH",
                message="Chat response language metadata does not match the selected language.",
                severity=ValidationSeverity.WARNING,
                field="language",
            )
        )

    def _language_from_metadata(self, context: ValidationContext) -> str:
        for metadata in (context.chat_response.metadata, getattr(context.model_response, "metadata", None)):
            if not metadata:
                continue
            for key in self.metadata_keys:
                value = metadata.get(key)
                if value:
                    return _normalize_language(str(value))
        return ""


def _normalize_language(value: str) -> str:
    """Normalize language metadata to a comparable short code."""
    return value.strip().lower().replace("_", "-").split("-", 1)[0]

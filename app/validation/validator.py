"""Validation engine."""

from .models import ValidationContext, ValidationResult
from .rules import ResponseValidator


class OutputValidator:
    """Execute registered response validators and aggregate their findings."""

    def __init__(self, validators: list[ResponseValidator] | None = None) -> None:
        self.validators = validators or []

    def validate(self, context: ValidationContext) -> ValidationResult:
        """Run all validators against a response context."""
        result = ValidationResult()
        for validator in self.validators:
            validator.validate(context, result)
        return result


output_validator = OutputValidator()

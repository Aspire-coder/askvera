"""Validation engine."""

from .models import ValidationContext, ValidationResult
from .rules import ResponseValidator
from .validators import AnswerValidator, ConfidenceValidator, LengthValidator, MetadataValidator


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


def default_validators() -> list[ResponseValidator]:
    """Return the default response validator sequence."""
    return [
        AnswerValidator(),
        ConfidenceValidator(),
        MetadataValidator(),
        LengthValidator(),
    ]


output_validator = OutputValidator(default_validators())

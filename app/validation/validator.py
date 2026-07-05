"""Validation engine."""

from time import perf_counter

from app.metrics import STAGE_VALIDATION
from app.metrics.pipeline import record_pipeline_metric

from .models import ValidationContext, ValidationResult
from .rules import ResponseValidator
from .validators import (
    AnswerValidator,
    CitationValidator,
    ConfidenceValidator,
    LanguageValidator,
    LengthValidator,
    MetadataValidator,
)


class OutputValidator:
    """Execute registered response validators and aggregate their findings."""

    def __init__(self, validators: list[ResponseValidator] | None = None) -> None:
        self.validators = validators or []

    def validate(self, context: ValidationContext) -> ValidationResult:
        """Run all validators against a response context."""
        started = perf_counter()
        success = False
        try:
            result = ValidationResult()
            for validator in self.validators:
                validator.validate(context, result)
            success = not result.has_critical()
            return result
        finally:
            record_pipeline_metric(
                stage=STAGE_VALIDATION,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=context.correlation_id,
                metadata={"validatorCount": len(self.validators)},
            )


def default_validators() -> list[ResponseValidator]:
    """Return the default response validator sequence."""
    return [
        AnswerValidator(),
        ConfidenceValidator(),
        CitationValidator(),
        LanguageValidator(),
        MetadataValidator(),
        LengthValidator(),
    ]


output_validator = OutputValidator(default_validators())

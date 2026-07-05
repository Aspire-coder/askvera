"""Validation rule interfaces."""

from typing import Protocol

from .models import ValidationContext, ValidationResult


class ResponseValidator(Protocol):
    """Interface implemented by individual response validators."""

    name: str

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        """Add validation issues to the shared result when needed."""
        ...

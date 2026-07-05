"""Validation summary helpers."""

from typing import Any

from .models import ValidationResult


def validation_summary(result: ValidationResult) -> dict[str, Any]:
    """Return audit/cache-safe validation summary metadata."""
    return {
        "valid": result.valid,
        "highestSeverity": result.highest_severity.value,
        "issueCount": len(result.issues),
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "field": issue.field,
            }
            for issue in result.issues
        ],
    }

"""Typed validation framework models."""

from dataclasses import dataclass, field
from enum import Enum

from app.models import ModelResponse
from app.response import ChatResponse
from app.retrieval import RetrievalResult


class ValidationSeverity(str, Enum):
    """Validation issue severity."""

    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ValidationIssue:
    """One validation issue detected by a validator."""

    code: str
    message: str
    severity: ValidationSeverity
    field: str | None = None


@dataclass
class ValidationResult:
    """Aggregated validation result."""

    valid: bool = True
    highest_severity: ValidationSeverity = ValidationSeverity.PASS
    issues: list[ValidationIssue] = field(default_factory=list)

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add one issue and update aggregate status."""
        self.issues.append(issue)
        if issue.severity in {ValidationSeverity.ERROR, ValidationSeverity.CRITICAL}:
            self.valid = False
        if _severity_rank(issue.severity) > _severity_rank(self.highest_severity):
            self.highest_severity = issue.severity

    def has_errors(self) -> bool:
        """Return true when any error or critical issue exists."""
        return any(issue.severity in {ValidationSeverity.ERROR, ValidationSeverity.CRITICAL} for issue in self.issues)

    def has_critical(self) -> bool:
        """Return true when any critical issue exists."""
        return any(issue.severity == ValidationSeverity.CRITICAL for issue in self.issues)


@dataclass(frozen=True)
class ValidationContext:
    """Data available to response validators."""

    chat_response: ChatResponse
    correlation_id: str
    country: str
    language: str
    role: str
    model_response: ModelResponse | None = None
    retrieval_result: RetrievalResult | None = None


def _severity_rank(severity: ValidationSeverity) -> int:
    """Return severity order for aggregate comparisons."""
    return {
        ValidationSeverity.PASS: 0,
        ValidationSeverity.WARNING: 1,
        ValidationSeverity.ERROR: 2,
        ValidationSeverity.CRITICAL: 3,
    }[severity]

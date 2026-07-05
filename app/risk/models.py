"""Typed risk and policy engine models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.response.models import ChatResponse
    from app.validation.models import ValidationResult


class RiskLevel(str, Enum):
    """Risk severity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RiskIssue:
    """One policy issue detected by the risk engine."""

    code: str
    message: str
    level: RiskLevel
    source: str
    policy: str = ""
    policy_version: str = ""


@dataclass
class RiskDecision:
    """Aggregated risk engine decision."""

    allowed: bool = True
    highest_risk: RiskLevel = RiskLevel.LOW
    issues: list[RiskIssue] = field(default_factory=list)
    recommended_action: str = "allow"

    def add_issue(self, issue: RiskIssue) -> None:
        """Add an issue and update aggregate risk fields."""
        self.issues.append(issue)
        if _risk_rank(issue.level) > _risk_rank(self.highest_risk):
            self.highest_risk = issue.level
        if issue.level == RiskLevel.CRITICAL:
            self.allowed = False
            self.recommended_action = "refuse"
        elif issue.level == RiskLevel.HIGH and self.recommended_action == "allow":
            self.recommended_action = "review"
        elif issue.level == RiskLevel.MEDIUM and self.recommended_action == "allow":
            self.recommended_action = "monitor"

    def is_critical(self) -> bool:
        """Return true when critical risk was detected."""
        return self.highest_risk == RiskLevel.CRITICAL


@dataclass(frozen=True)
class RiskContext:
    """Inputs available to risk policies."""

    user_message: str
    country: str
    language: str
    role: str
    correlation_id: str
    chat_response: ChatResponse | None = None
    validation_result: ValidationResult | None = None


def _risk_rank(level: RiskLevel) -> int:
    """Return risk level order for aggregate comparisons."""
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }[level]

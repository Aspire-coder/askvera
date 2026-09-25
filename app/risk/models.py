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


class PolicyAction(str, Enum):
    """Recommended policy actions, separate from risk severity."""

    ALLOW = "ALLOW"
    WARN = "WARN"
    REDACT = "REDACT"
    REFUSE = "REFUSE"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class RiskIssue:
    """One policy issue detected by the risk engine."""

    code: str
    message: str
    level: RiskLevel
    action: PolicyAction
    source: str
    policy: str = ""
    policy_version: str = ""


@dataclass
class RiskDecision:
    """Aggregated risk engine decision."""

    allowed: bool = True
    highest_risk: RiskLevel = RiskLevel.LOW
    action: PolicyAction = PolicyAction.ALLOW
    issues: list[RiskIssue] = field(default_factory=list)
    recommended_action: str = "allow"

    def add_issue(self, issue: RiskIssue) -> None:
        """Add an issue and update aggregate risk/action fields."""
        self.issues.append(issue)
        if _risk_rank(issue.level) > _risk_rank(self.highest_risk):
            self.highest_risk = issue.level
        if _action_rank(issue.action) > _action_rank(self.action):
            self.action = issue.action
            self.recommended_action = issue.action.value.lower()
        if issue.action == PolicyAction.REFUSE:
            self.allowed = False

    def should_refuse(self) -> bool:
        """Return true when policy action requires refusal."""
        return self.action == PolicyAction.REFUSE


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


def _action_rank(action: PolicyAction) -> int:
    """Return action order for aggregate comparisons."""
    return {
        PolicyAction.ALLOW: 0,
        PolicyAction.WARN: 1,
        PolicyAction.REDACT: 2,
        PolicyAction.ESCALATE: 3,
        PolicyAction.REFUSE: 4,
    }[action]

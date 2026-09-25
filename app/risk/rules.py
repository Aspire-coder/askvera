"""Risk policy interfaces."""

from dataclasses import dataclass
from typing import Protocol

from .models import PolicyAction, RiskContext, RiskIssue, RiskLevel


@dataclass(frozen=True)
class RiskPolicyMetadata:
    """Policy metadata for auditability and future admin controls."""

    name: str
    version: str
    description: str
    enabled: bool
    risk_level: RiskLevel
    action: PolicyAction


class RiskPolicy(Protocol):
    """Interface implemented by risk policies."""

    metadata: RiskPolicyMetadata

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        """Return risk issues for the provided context."""
        ...

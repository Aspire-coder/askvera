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
    is_claim_topic: bool = False
    """True for a policy that flags medical/income claim vocabulary.

    Such a policy is suppressed on the answer-side pass when the caller has
    established that the generated answer is explaining a reviewed policy
    (see RiskContext.allow_claim_topics and RiskEngine.evaluate).
    """


class RiskPolicy(Protocol):
    """Interface implemented by risk policies."""

    metadata: RiskPolicyMetadata

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        """Return risk issues for the provided context."""
        ...

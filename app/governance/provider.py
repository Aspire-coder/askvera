"""Governance provider interface."""

from typing import Protocol

from .models import GovernanceDecision


class GovernanceProvider(Protocol):
    """Interface implemented by governance providers."""

    name: str

    def evaluate(
        self,
        *,
        text: str,
        country: str,
        language: str,
        correlation_id: str,
    ) -> GovernanceDecision:
        """Evaluate one text payload and return a governance decision."""
        ...

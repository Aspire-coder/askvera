"""Typed governance decision models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GovernanceAction(str, Enum):
    """Possible governance actions."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class GovernanceDecision:
    """Decision returned by a governance provider."""

    allowed: bool
    action: GovernanceAction
    provider: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

"""Offline-only contracts for the evidence-first V2 experiment.

This package deliberately has no dependency on the existing application
pipeline.  It is not imported by routes or production configuration.
"""

from .contracts import (
    EvidenceFact,
    EvidenceFirstResult,
    EvidenceReference,
    FactQualifiers,
    ResultStatus,
    Turn,
    TurnSpeaker,
    V2Request,
)
from .context import Ambiguity, AmbiguityCode, ContextField, ContextSource, ContextUse, PlaceStatus, StructuredContext
from .scope import EvidenceAccess, ScopeCompatibility, ScopeIntent, ScopeDecision, resolve_scope
from .standalone import InterpreterOutput, StandaloneRequest, StandaloneRequestBuilder, resolve_standalone_scope

__all__ = [
    "Ambiguity",
    "AmbiguityCode",
    "ContextField",
    "ContextSource",
    "ContextUse",
    "EvidenceAccess",
    "EvidenceFact",
    "EvidenceFirstResult",
    "EvidenceReference",
    "FactQualifiers",
    "InterpreterOutput",
    "PlaceStatus",
    "ResultStatus",
    "ScopeCompatibility",
    "ScopeDecision",
    "ScopeIntent",
    "StandaloneRequest",
    "StandaloneRequestBuilder",
    "StructuredContext",
    "Turn",
    "TurnSpeaker",
    "V2Request",
    "resolve_scope",
    "resolve_standalone_scope",
]

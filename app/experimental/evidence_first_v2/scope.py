"""Pure deterministic scope rules for evidence-first V2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import EvidenceAccess, EvidenceReference, V2Request, _enum, _market, _required


class ScopeIntent(str, Enum):
    COMPANY_POLICY = "company_policy"
    INTERNATIONAL_SPONSORING = "international_sponsoring"


@dataclass(frozen=True)
class ScopeCompatibility:
    """Inspectable compatibility between preserved request and evidence context."""

    request_role: str
    evidence_role: str | None
    request_language: str
    evidence_language: str
    request_effective_version: str
    evidence_effective_version: str
    role_compatible: bool
    language_rule: str
    effective_version_compatible: bool

    @property
    def permitted(self) -> bool:
        return self.role_compatible and self.effective_version_compatible


@dataclass(frozen=True)
class ScopeDecision:
    """The sole allowed evidence shape for one interpreted request."""

    intent: ScopeIntent
    user_market: str
    directory_market: str | None
    allowed_access: EvidenceAccess
    role: str
    language: str
    effective_version: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent", _enum(self.intent, ScopeIntent, "intent"))
        object.__setattr__(self, "allowed_access", _enum(self.allowed_access, EvidenceAccess, "allowed_access"))
        object.__setattr__(self, "user_market", _market(self.user_market, "user_market"))
        object.__setattr__(self, "role", _required(self.role, "role"))
        object.__setattr__(self, "language", _required(self.language, "language"))
        object.__setattr__(self, "effective_version", _required(self.effective_version, "effective_version"))
        object.__setattr__(self, "reason", _required(self.reason, "reason"))
        if self.directory_market is not None:
            object.__setattr__(self, "directory_market", _market(self.directory_market, "directory_market"))
        if self.intent is ScopeIntent.COMPANY_POLICY:
            if self.directory_market is not None:
                raise ValueError("company policy scope cannot declare a directory market")
            if self.allowed_access is not EvidenceAccess.LOCAL_POLICY:
                raise ValueError("company policy scope requires LOCAL_POLICY access")
        elif self.intent is ScopeIntent.INTERNATIONAL_SPONSORING:
            if self.directory_market is None:
                raise ValueError("international sponsoring scope requires a directory market")
            if self.allowed_access is not EvidenceAccess.GLOBAL_DIRECTORY:
                raise ValueError("international sponsoring scope requires GLOBAL_DIRECTORY access")
        else:
            raise ValueError("unsupported scope intent")

    def compatibility(self, reference: EvidenceReference) -> ScopeCompatibility:
        """Expose the V2-01 role, language and version compatibility rule.

        A source may use another language because translation behavior is not a
        V2-01 concern. Both languages remain inspectable for the later stage.
        Version is strict, and role-bound evidence must match the user role.
        """
        return ScopeCompatibility(
            request_role=self.role,
            evidence_role=reference.role,
            request_language=self.language,
            evidence_language=reference.language,
            request_effective_version=self.effective_version,
            evidence_effective_version=reference.effective_version,
            role_compatible=reference.role is None or reference.role == self.role,
            language_rule="source_language_retained_translation_not_decided",
            effective_version_compatible=reference.effective_version == self.effective_version,
        )

    def permits(self, reference: EvidenceReference) -> bool:
        """Return whether source shape and preserved context permit evidence."""
        if not isinstance(reference, EvidenceReference):
            return False
        if reference.access is not self.allowed_access or not self.compatibility(reference).permitted:
            return False
        if self.intent is ScopeIntent.COMPANY_POLICY:
            return reference.source_market == self.user_market
        if self.intent is ScopeIntent.INTERNATIONAL_SPONSORING:
            return reference.source_market == "GLOBAL" and reference.directory_market == self.directory_market
        return False


def resolve_scope(request: V2Request, intent: ScopeIntent) -> ScopeDecision:
    """Resolve scope without a model, retrieval provider, cache, or I/O."""
    if not isinstance(request, V2Request):
        raise ValueError("request must be a V2Request")
    if not isinstance(intent, ScopeIntent):
        raise ValueError("intent must be a ScopeIntent")
    common = {
        "intent": intent,
        "user_market": request.user_market,
        "role": request.role,
        "language": request.language,
        "effective_version": request.effective_version,
    }
    if intent is ScopeIntent.COMPANY_POLICY:
        return ScopeDecision(directory_market=None, allowed_access=EvidenceAccess.LOCAL_POLICY, reason="policy_restricted_to_user_market", **common)
    if intent is ScopeIntent.INTERNATIONAL_SPONSORING:
        return ScopeDecision(
            directory_market=request.requested_directory_market or request.user_market,
            allowed_access=EvidenceAccess.GLOBAL_DIRECTORY,
            reason="international_sponsoring_uses_global_directory",
            **common,
        )
    raise ValueError("unsupported scope intent")

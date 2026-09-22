"""Immutable data contracts for the isolated evidence-first V2 runner."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, TypeVar


_MARKET_RE = re.compile(r"[A-Za-z]{2}\Z", re.ASCII)
_EnumT = TypeVar("_EnumT", bound=Enum)
_ValueT = TypeVar("_ValueT")


def _required(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _market(value: str, name: str) -> str:
    value = _required(value, name)
    if not _MARKET_RE.fullmatch(value):
        raise ValueError(f"{name} must be an ASCII two-letter market code")
    return value.upper()


def _source_market(value: str) -> str:
    value = _required(value, "source_market")
    if value == "GLOBAL":
        return value
    return _market(value, "source_market")


def _enum(value: object, enum_type: type[_EnumT], name: str) -> _EnumT:
    if not isinstance(value, enum_type):
        raise ValueError(f"{name} must be a {enum_type.__name__}")
    return value


def _tuple_of(value: Iterable[_ValueT], item_type: type, name: str) -> tuple[_ValueT, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a collection")
    try:
        items = tuple(value)
    except TypeError as error:
        raise ValueError(f"{name} must be a collection") from error
    if any(not isinstance(item, item_type) for item in items):
        raise ValueError(f"{name} must contain only {item_type.__name__} values")
    return items


def _string_tuple(value: Iterable[str], name: str) -> tuple[str, ...]:
    items = _tuple_of(value, str, name)
    return tuple(_required(item, name[:-1] if name.endswith("s") else name) for item in items)


class TurnSpeaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Turn:
    """Conversation context only. It is never an authoritative source."""

    speaker: TurnSpeaker
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "speaker", _enum(self.speaker, TurnSpeaker, "speaker"))
        object.__setattr__(self, "text", _required(self.text, "turn text"))


@dataclass(frozen=True)
class V2Request:
    """A fully structured request entering the standalone V2 pipeline."""

    request_id: str
    message: str
    user_market: str
    language: str
    role: str
    effective_version: str
    turns: tuple[Turn, ...] = ()
    requested_directory_market: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _required(self.request_id, "request_id"))
        object.__setattr__(self, "message", _required(self.message, "message"))
        object.__setattr__(self, "user_market", _market(self.user_market, "user_market"))
        object.__setattr__(self, "language", _required(self.language, "language"))
        object.__setattr__(self, "role", _required(self.role, "role"))
        object.__setattr__(self, "effective_version", _required(self.effective_version, "effective_version"))
        object.__setattr__(self, "turns", _tuple_of(self.turns, Turn, "turns"))
        if self.requested_directory_market is not None:
            object.__setattr__(self, "requested_directory_market", _market(self.requested_directory_market, "requested_directory_market"))


class EvidenceAccess(str, Enum):
    LOCAL_POLICY = "local_policy"
    GLOBAL_DIRECTORY = "global_directory"


@dataclass(frozen=True)
class EvidenceReference:
    """A source-bound quotation eligible to support a fact."""

    source_id: str
    section_id: str
    quote: str
    access: EvidenceAccess
    source_market: str
    language: str
    effective_version: str
    directory_market: str | None = None
    role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "access", _enum(self.access, EvidenceAccess, "access"))
        for name in ("source_id", "section_id", "quote", "language", "effective_version"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        object.__setattr__(self, "source_market", _source_market(self.source_market))
        if self.directory_market is not None:
            object.__setattr__(self, "directory_market", _market(self.directory_market, "directory_market"))
        if self.role is not None:
            object.__setattr__(self, "role", _required(self.role, "role"))
        if self.access is EvidenceAccess.LOCAL_POLICY:
            if self.directory_market is not None:
                raise ValueError("local policy evidence cannot declare a directory market")
            if self.source_market == "GLOBAL":
                raise ValueError("local policy evidence cannot use GLOBAL source_market")
        elif self.access is EvidenceAccess.GLOBAL_DIRECTORY:
            if self.source_market != "GLOBAL":
                raise ValueError("global directory evidence must use GLOBAL source_market")
            if self.directory_market is None:
                raise ValueError("global directory evidence requires a directory market")
        else:
            raise ValueError("unsupported evidence access")


@dataclass(frozen=True)
class FactQualifiers:
    """Conditions that must travel with a source-bound fact when present."""

    role: str | None = None
    unit: str | None = None
    timing: str | None = None
    exceptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("role", "unit", "timing"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _required(value, name))
        object.__setattr__(self, "exceptions", _string_tuple(self.exceptions, "exceptions"))


@dataclass(frozen=True)
class EvidenceFact:
    """A claim with a single, inspectable source binding and qualifiers."""

    text: str
    evidence: EvidenceReference
    qualifiers: FactQualifiers = field(default_factory=FactQualifiers)

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _required(self.text, "fact text"))
        if not isinstance(self.evidence, EvidenceReference):
            raise ValueError("evidence must be an EvidenceReference")
        if not isinstance(self.qualifiers, FactQualifiers):
            raise ValueError("qualifiers must be a FactQualifiers")


class ResultStatus(str, Enum):
    READY = "ready"
    SAFE_PARTIAL = "safe_partial"
    CLARIFICATION = "clarification"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EvidenceFirstResult:
    """Contract shared by future composition and validation stages."""

    status: ResultStatus
    scope_reason: str
    facts: tuple[EvidenceFact, ...] = ()
    answer: str = ""
    failure_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _enum(self.status, ResultStatus, "status"))
        object.__setattr__(self, "scope_reason", _required(self.scope_reason, "scope_reason"))
        object.__setattr__(self, "facts", _tuple_of(self.facts, EvidenceFact, "facts"))
        object.__setattr__(self, "failure_reasons", _string_tuple(self.failure_reasons, "failure_reasons"))
        if self.status is ResultStatus.READY and not self.facts:
            raise ValueError("ready result requires source-bound facts")
        if self.status is ResultStatus.BLOCKED and not self.failure_reasons:
            raise ValueError("blocked result requires failure reasons")

"""Bounded, non-authoritative conversation context for V2-02."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import Turn, TurnSpeaker, _required, _tuple_of


MAX_CONTEXT_TURNS = 32
MAX_CONTEXT_CHARACTERS = 4_000
MAX_AMBIGUITY_DETAIL_CHARACTERS = 256


class ContextSource(str, Enum):
    CURRENT_REQUEST = "current_request"
    HISTORY = "history"


class ContextField(str, Enum):
    INTENT = "intent"
    STANDALONE_MEANING = "standalone_meaning"
    PLACE = "place"
    REQUESTED_DIRECTORY_MARKET = "requested_directory_market"
    REFERENT = "referent"
    NEGATION = "negation"
    NUMBER = "number"
    ROLE = "role"
    LANGUAGE = "language"
    EFFECTIVE_VERSION = "effective_version"
    POLICY = "policy"
    PERMISSION = "permission"


class PlaceStatus(str, Enum):
    NONE = "none"
    IMPLIED_FROM_HISTORY = "implied_from_history"
    EXPLICIT_RESOLVED = "explicit_resolved"
    EXPLICIT_UNKNOWN = "explicit_unknown"


class AmbiguityCode(str, Enum):
    UNKNOWN_EXPLICIT_PLACE = "unknown_explicit_place"
    UNKNOWN_CURRENT_INTENT = "unknown_current_intent"
    COMPOUND_REQUEST = "compound_request"
    MULTIPLE_CURRENT_PLACES = "multiple_current_places"


def _enum(value: object, enum_type: type[Enum], name: str) -> Enum:
    if not isinstance(value, enum_type):
        raise ValueError(f"{name} must be a {enum_type.__name__}")
    return value


@dataclass(frozen=True)
class ContextUse:
    """Value-bound provenance for one current-request or retained history span."""

    field: ContextField
    source: ContextSource
    value: str
    start: int
    end: int
    turn_index: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", _enum(self.field, ContextField, "field"))
        object.__setattr__(self, "source", _enum(self.source, ContextSource, "source"))
        object.__setattr__(self, "value", _required(self.value, "context value"))
        if type(self.start) is not int or type(self.end) is not int or self.start < 0 or self.end <= self.start:
            raise ValueError("context span must use non-negative integer bounds")
        if self.source is ContextSource.HISTORY:
            if type(self.turn_index) is not int or self.turn_index < 0:
                raise ValueError("history context use requires a non-negative integer turn_index")
        elif self.turn_index is not None:
            raise ValueError("current request context use cannot declare a turn_index")


@dataclass(frozen=True)
class Ambiguity:
    code: AmbiguityCode
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _enum(self.code, AmbiguityCode, "code"))
        object.__setattr__(self, "detail", _required(self.detail, "ambiguity detail"))
        if len(self.detail) > MAX_AMBIGUITY_DETAIL_CHARACTERS:
            raise ValueError("ambiguity detail exceeds the V2-02 limit")


@dataclass(frozen=True)
class StructuredContext:
    """Session-bounded context. It is not evidence and cannot authorize facts."""

    session_id: str
    turns: tuple[Turn, ...] = ()
    turn_indices: tuple[int, ...] | None = None
    prior_role: str | None = None
    prior_language: str | None = None
    prior_effective_version: str | None = None
    truncated: bool = False
    history_fallback_blocked: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _required(self.session_id, "session_id"))
        object.__setattr__(self, "turns", _tuple_of(self.turns, Turn, "turns"))
        indices = tuple(range(len(self.turns))) if self.turn_indices is None else tuple(self.turn_indices)
        if len(indices) != len(self.turns) or any(type(index) is not int or index < 0 for index in indices) or len(set(indices)) != len(indices):
            raise ValueError("turn_indices must be unique non-negative integers for every turn")
        object.__setattr__(self, "turn_indices", indices)
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a bool")
        if not isinstance(self.history_fallback_blocked, bool):
            raise ValueError("history_fallback_blocked must be a bool")
        for name in ("prior_role", "prior_language", "prior_effective_version"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _required(value, name))

    def bounded(self) -> StructuredContext:
        """Keep the newest complete turns within fixed limits and original indexes."""
        kept: list[tuple[int, Turn]] = []
        chars = 0
        blocked = self.history_fallback_blocked
        for index, turn in reversed(tuple(zip(self.turn_indices, self.turns))):
            if len(kept) >= MAX_CONTEXT_TURNS or chars + len(turn.text) > MAX_CONTEXT_CHARACTERS:
                if not kept and len(turn.text) > MAX_CONTEXT_CHARACTERS:
                    blocked = True
                break
            kept.append((index, turn))
            chars += len(turn.text)
        kept.reverse()
        indices = tuple(item[0] for item in kept)
        turns = tuple(item[1] for item in kept)
        return StructuredContext(
            session_id=self.session_id,
            turns=turns,
            turn_indices=indices,
            prior_role=self.prior_role,
            prior_language=self.prior_language,
            prior_effective_version=self.prior_effective_version,
            truncated=self.truncated or len(turns) != len(self.turns),
            history_fallback_blocked=blocked,
        )

    def turn_for_original_index(self, index: int) -> Turn | None:
        for stored_index, turn in zip(self.turn_indices, self.turns):
            if stored_index == index:
                return turn
        return None

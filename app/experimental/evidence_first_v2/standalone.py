"""Fail-closed, injected standalone-request interpretation for V2-02."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Callable, Mapping

from .context import Ambiguity, AmbiguityCode, ContextField, ContextSource, ContextUse, PlaceStatus, StructuredContext
from .contracts import TurnSpeaker, V2Request, _enum, _market, _required, _tuple_of
from .scope import ScopeDecision, ScopeIntent, resolve_scope


MAX_REGISTRY_ENTRIES = 128
MAX_ALIAS_CHARACTERS = 96
MAX_REQUEST_CHARACTERS = 4_000
MAX_NUMBER_TOKENS = 32
MAX_CONTEXT_USES = 64
MAX_AMBIGUITIES = 8

_NUMBER_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?", re.ASCII)
_NEGATION_RE = re.compile(r"\b(?:not|no|never)\b|n['’]t", re.IGNORECASE)
_POLICY_RE = re.compile(r"\b(?:polic(?:y|ies)|eligib\w*|(?:can|may)\s+i\s+(?:sponsor|recruit)|(?:may|can)\s+i\s+(?:be\s+)?permitted\s+to\s+(?:sponsor|recruit)|permission\s+to\s+sponsor|(?:sponsor|recruit)\s+in|allowed\s+to\s+recruit|puis-je\s+parrainer\s+au)\b", re.IGNORECASE)
_DIRECTORY_RE = re.compile(r"\b(?:phone|telephone|contact|office(?!\s+policy)|hotline|switchboard|email|e-mail|address|whatsapp|number\s+(?:should|can|do)\s+i\s+call|number\s+to\s+call|call\s+number)\b", re.IGNORECASE)
_CLAUSE_SPLIT_RE = re.compile(r"(?:[;,]|\b(?:and|or)\b)", re.IGNORECASE)
_NEGATED_POLICY_ONLY_RE = re.compile(r"\b(?:do\s+not\s+want|don't\s+want)\s+(?:eligibility|policy|sponsoring|recruiting).*?\bonly\b", re.IGNORECASE)
_FOLLOW_UP_RE = re.compile(r"(?:what\s+about\s+)?(?:the\s+)?(?:telephone|phone|contact)\??", re.IGNORECASE)
_NUMERIC_UNIT_CONTINUATION_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?(?:\s+[A-Za-z]+)?[?.!]*", re.ASCII)

_AMBIGUITY_DETAILS = {
    AmbiguityCode.UNKNOWN_EXPLICIT_PLACE: "current destination requires clarification",
    AmbiguityCode.UNKNOWN_CURRENT_INTENT: "current request requires clarification",
    AmbiguityCode.COMPOUND_REQUEST: "current request has multiple branches",
    AmbiguityCode.MULTIPLE_CURRENT_PLACES: "current request has multiple destinations",
}


def _numbers(text: str) -> tuple[tuple[str, int, int], ...]:
    return tuple((match.group(0), match.start(), match.end()) for match in _NUMBER_RE.finditer(text))


def _span_matches(text: str, use: ContextUse) -> bool:
    return use.end <= len(text) and text[use.start:use.end] == use.value


def _safe_lower(value: str) -> str | None:
    lowered = value.lower()
    return lowered if len(lowered) == len(value) and value.casefold() == lowered else None


def _token_boundary(text: str, start: int, end: int) -> bool:
    def continues(char: str) -> bool:
        category = unicodedata.category(char)
        return char.isalnum() or category.startswith("M") or category == "Pc"
    return (start == 0 or not continues(text[start - 1])) and (end == len(text) or not continues(text[end]))


@dataclass(frozen=True, order=True)
class _RegisteredPlace:
    normalized: str
    alias: str
    market: str | None


@dataclass(frozen=True)
class _PlaceMatch:
    entry: _RegisteredPlace
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class _BuilderProof:
    fingerprint: str


@dataclass(frozen=True)
class InterpreterOutput:
    """Untrusted structured output tied to the exact request and bounded context."""

    request_id: str
    session_id: str
    intent: ScopeIntent
    standalone_message: str
    place_status: PlaceStatus
    explicit_place: str | None = None
    requested_directory_market: str | None = None
    negated: bool = False
    number_tokens: tuple[str, ...] = ()
    context_uses: tuple[ContextUse, ...] = ()
    ambiguities: tuple[Ambiguity, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _required(self.request_id, "request_id"))
        object.__setattr__(self, "session_id", _required(self.session_id, "session_id"))
        object.__setattr__(self, "intent", _enum(self.intent, ScopeIntent, "intent"))
        object.__setattr__(self, "standalone_message", _required(self.standalone_message, "standalone_message"))
        if len(self.standalone_message) > MAX_REQUEST_CHARACTERS:
            raise ValueError("standalone_message exceeds the V2-02 limit")
        object.__setattr__(self, "place_status", _enum(self.place_status, PlaceStatus, "place_status"))
        if self.explicit_place is not None:
            object.__setattr__(self, "explicit_place", _required(self.explicit_place, "explicit_place"))
        if self.requested_directory_market is not None:
            object.__setattr__(self, "requested_directory_market", _market(self.requested_directory_market, "requested_directory_market"))
        if not isinstance(self.negated, bool):
            raise ValueError("negated must be a bool")
        object.__setattr__(self, "number_tokens", _tuple_of(self.number_tokens, str, "number_tokens"))
        object.__setattr__(self, "context_uses", _tuple_of(self.context_uses, ContextUse, "context_uses"))
        object.__setattr__(self, "ambiguities", _tuple_of(self.ambiguities, Ambiguity, "ambiguities"))
        if len(self.number_tokens) > MAX_NUMBER_TOKENS or len(self.context_uses) > MAX_CONTEXT_USES or len(self.ambiguities) > MAX_AMBIGUITIES:
            raise ValueError("interpreter output exceeds a V2-02 collection limit")
        if any(item.detail != _AMBIGUITY_DETAILS[item.code] for item in self.ambiguities):
            raise ValueError("ambiguity detail must use the V2-02 canonical detail")


@dataclass(frozen=True)
class StandaloneRequest:
    request_id: str
    session_id: str
    original_message: str
    standalone_message: str
    intent: ScopeIntent
    user_market: str
    requested_directory_market: str | None
    role: str
    language: str
    effective_version: str
    negated: bool
    number_tokens: tuple[str, ...]
    context_uses: tuple[ContextUse, ...]
    ambiguities: tuple[Ambiguity, ...]
    context_truncated: bool
    requires_clarification: bool
    destination_validated: bool
    _proof: _BuilderProof | None = field(default=None, repr=False, compare=False)


Interpreter = Callable[[V2Request, StructuredContext], InterpreterOutput]


class StandaloneRequestBuilder:
    """Stateless boundary: one fake/replay interpreter call per build."""

    __slots__ = ("_interpreter", "_place_aliases", "registry_identity", "_sealed")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False) and name in {"_interpreter", "_place_aliases", "registry_identity"}:
            raise AttributeError("StandaloneRequestBuilder registry is immutable")
        object.__setattr__(self, name, value)

    def __init__(self, interpreter: Interpreter, place_aliases: Mapping[str, str | None]) -> None:
        if not callable(interpreter) or not isinstance(place_aliases, Mapping):
            raise ValueError("interpreter must be callable and place_aliases must be a mapping")
        self._interpreter = interpreter
        self._place_aliases = self._validated_aliases(place_aliases)
        material = b"".join(self._identity_part(item.normalized) + self._identity_part(item.alias) + self._identity_part(item.market or "") for item in self._place_aliases)
        self.registry_identity = hashlib.sha256(material).hexdigest()
        self._sealed = True

    def build(self, request: V2Request, context: StructuredContext) -> StandaloneRequest:
        if not isinstance(request, V2Request) or not isinstance(context, StructuredContext):
            raise ValueError("request and context must use V2 contracts")
        if len(request.message) > MAX_REQUEST_CHARACTERS:
            raise ValueError("request message exceeds the V2-02 limit")
        bounded = context.bounded()
        candidates = self._current_places(request.message)
        interpreter_request = replace(request, turns=(), requested_directory_market=None)
        output = self._interpreter(interpreter_request, bounded)
        if not isinstance(output, InterpreterOutput):
            raise ValueError("interpreter must return an InterpreterOutput")
        if output.request_id != request.request_id or output.session_id != bounded.session_id:
            raise ValueError("interpreter output request/session identity mismatch")
        self._validate_uses(output, request, bounded)
        self._validate_current_preservation(output, request)
        destination_validated = self._validate_place(output, request, bounded, candidates)
        self._validate_intent(output, request)
        codes = {item.code for item in output.ambiguities}
        result = StandaloneRequest(
            request_id=request.request_id, session_id=bounded.session_id, original_message=request.message,
            standalone_message=output.standalone_message, intent=output.intent, user_market=request.user_market,
            requested_directory_market=output.requested_directory_market, role=request.role, language=request.language,
            effective_version=request.effective_version, negated=output.negated, number_tokens=output.number_tokens,
            context_uses=output.context_uses, ambiguities=output.ambiguities, context_truncated=bounded.truncated,
            requires_clarification=bool(codes & set(_AMBIGUITY_DETAILS)), destination_validated=destination_validated,
        )
        return replace(result, _proof=_BuilderProof(_result_fingerprint(result)))

    @staticmethod
    def _identity_part(value: str) -> bytes:
        encoded = value.encode("utf-8")
        return len(encoded).to_bytes(4, "big") + encoded

    def _validate_uses(self, output: InterpreterOutput, request: V2Request, context: StructuredContext) -> None:
        for use in output.context_uses:
            text = request.message if use.source is ContextSource.CURRENT_REQUEST else ""
            turn = None if use.source is ContextSource.CURRENT_REQUEST else context.turn_for_original_index(use.turn_index)
            if turn is not None:
                text = turn.text
            if not text or not _span_matches(text, use):
                raise ValueError("context use is not bound to its declared source span")
            if use.source is ContextSource.HISTORY and turn.speaker is TurnSpeaker.ASSISTANT:
                raise ValueError("assistant turns cannot supply V2-02 context")

    def _current_use(self, output: InterpreterOutput, field: ContextField, value: str) -> bool:
        return any(use.field is field and use.source is ContextSource.CURRENT_REQUEST and use.value == value for use in output.context_uses)

    def _validate_current_preservation(self, output: InterpreterOutput, request: V2Request) -> None:
        if not self._current_use(output, ContextField.STANDALONE_MEANING, request.message) or output.standalone_message != request.message:
            raise ValueError("standalone message must equal the current request")
        occurrences = _numbers(request.message)
        if output.number_tokens != tuple(item[0] for item in occurrences):
            raise ValueError("interpreter output must retain exactly the current-request numbers")
        supplied = tuple((use.value, use.start, use.end) for use in output.context_uses if use.source is ContextSource.CURRENT_REQUEST and use.field is ContextField.NUMBER)
        if supplied != occurrences:
            raise ValueError("current-request numbers require distinct ordered provenance spans")
        negated = bool(_NEGATION_RE.search(request.message))
        if output.negated is not negated:
            raise ValueError("interpreter output changes current-request negation")
        if negated and not any(use.field is ContextField.NEGATION and use.source is ContextSource.CURRENT_REQUEST for use in output.context_uses):
            raise ValueError("current-request negation lacks provenance")

    @staticmethod
    def _validated_aliases(source: Mapping[str, str | None]) -> tuple[_RegisteredPlace, ...]:
        if not source or len(source) > MAX_REGISTRY_ENTRIES:
            raise ValueError("place_aliases exceeds the V2-02 registry limit")
        aliases: list[_RegisteredPlace] = []
        seen: set[str] = set()
        for alias, market in source.items():
            alias = _required(alias, "place alias")
            normalized = _safe_lower(alias)
            if normalized is None or alias.upper() == "GLOBAL" or len(alias) > MAX_ALIAS_CHARACTERS or not any(char.isalpha() for char in alias) or any(unicodedata.category(char).startswith("C") for char in alias):
                raise ValueError("place alias uses unsupported normalization or shape")
            if normalized in seen:
                raise ValueError("place aliases must be unique")
            seen.add(normalized)
            aliases.append(_RegisteredPlace(normalized, alias, None if market is None else _market(market, "place alias market")))
        return tuple(sorted(aliases))

    def _current_places(self, message: str) -> tuple[_PlaceMatch, ...]:
        matches: list[_PlaceMatch] = []
        for entry in self._place_aliases:
            width = len(entry.alias)
            for start in range(0, len(message) - width + 1):
                end = start + width
                segment = message[start:end]
                if _token_boundary(message, start, end) and _safe_lower(segment) == entry.normalized:
                    matches.append(_PlaceMatch(entry, segment, start, end))
        matches.sort(key=lambda item: (item.start, item.end, item.entry.normalized, item.entry.alias))
        distinct: list[_PlaceMatch] = []
        seen_destinations: set[tuple[str, str]] = set()
        for match in matches:
            key = ("market", match.entry.market) if match.entry.market is not None else ("unknown", match.entry.normalized)
            if key not in seen_destinations:
                seen_destinations.add(key)
                distinct.append(match)
        return tuple(distinct)

    def _registered_market(self, place: str) -> str | None:
        normalized = _safe_lower(place)
        if normalized is None:
            return None
        for entry in self._place_aliases:
            if entry.normalized == normalized:
                return entry.market
        return None

    def _classify_request(self, message: str) -> tuple[frozenset[ScopeIntent], bool]:
        expected: set[ScopeIntent] = set()
        unclassified = False
        suppressed_policy = bool(_NEGATED_POLICY_ONLY_RE.search(message))
        clauses = tuple(part.strip() for part in _CLAUSE_SPLIT_RE.split(message) if part.strip())
        for clause in clauses:
            if suppressed_policy and re.search(r"\b(?:do\s+not\s+want|don't\s+want)\b", clause, re.IGNORECASE):
                continue
            classified: set[ScopeIntent] = set()
            if _POLICY_RE.search(clause):
                classified.add(ScopeIntent.COMPANY_POLICY)
            if _DIRECTORY_RE.search(clause):
                classified.add(ScopeIntent.INTERNATIONAL_SPONSORING)
            expected.update(classified)
            if len(clauses) > 1 and not classified and not self._current_places(clause) and not _NUMERIC_UNIT_CONTINUATION_RE.fullmatch(clause):
                unclassified = True
        return frozenset(expected), unclassified or len(expected) > 1

    def _newest_user_destination(self, context: StructuredContext) -> tuple[int, _PlaceMatch] | None:
        for index, turn in reversed(tuple(zip(context.turn_indices, context.turns))):
            if turn.speaker is not TurnSpeaker.USER:
                continue
            matches = self._current_places(turn.text)
            if len(matches) == 1 and matches[0].entry.market is not None:
                return index, matches[0]
            return None
        return None

    @staticmethod
    def _has_code(output: InterpreterOutput, code: AmbiguityCode) -> bool:
        return any(item.code is code for item in output.ambiguities)

    def _validate_place(self, output: InterpreterOutput, request: V2Request, context: StructuredContext, candidates: tuple[_PlaceMatch, ...]) -> bool:
        history_uses = tuple(use for use in output.context_uses if use.source is ContextSource.HISTORY)
        has_unknown = any(item.entry.market is None for item in candidates)
        if has_unknown and history_uses:
            raise ValueError("explicit unknown place cannot retain history context")
        if has_unknown and output.requested_directory_market is not None:
            raise ValueError("explicit unknown place cannot select a market")
        if len(candidates) > 1:
            if not self._has_code(output, AmbiguityCode.MULTIPLE_CURRENT_PLACES):
                raise ValueError("multiple current places require ambiguity")
            if output.requested_directory_market is not None:
                raise ValueError("multiple current places cannot select a market")
            if has_unknown and not self._has_code(output, AmbiguityCode.UNKNOWN_EXPLICIT_PLACE):
                raise ValueError("unknown current place requires ambiguity")
            return False
        if len(candidates) == 1:
            candidate = candidates[0]
            if candidate.entry.market is None:
                if output.place_status is not PlaceStatus.EXPLICIT_UNKNOWN or output.explicit_place != candidate.value or output.requested_directory_market is not None:
                    raise ValueError("unresolved current place cannot fall back to history")
                if not self._current_use(output, ContextField.PLACE, candidate.value) or not self._has_code(output, AmbiguityCode.UNKNOWN_EXPLICIT_PLACE):
                    raise ValueError("unresolved current place requires provenance and ambiguity")
                return False
            if output.place_status is not PlaceStatus.EXPLICIT_RESOLVED or output.explicit_place != candidate.value or output.requested_directory_market != candidate.entry.market:
                raise ValueError("resolved current place must override history")
            if not self._current_use(output, ContextField.PLACE, candidate.value):
                raise ValueError("resolved current place lacks provenance")
            return True
        expected, _compound = self._classify_request(request.message)
        if output.place_status is PlaceStatus.IMPLIED_FROM_HISTORY:
            if not _FOLLOW_UP_RE.fullmatch(request.message.strip()) or context.history_fallback_blocked:
                raise ValueError("history market fallback requires a bounded positive follow-up")
            if len(history_uses) != 1 or history_uses[0].field is not ContextField.REQUESTED_DIRECTORY_MARKET:
                raise ValueError("history-derived market requires exactly one user-turn provenance")
            turn = context.turn_for_original_index(history_uses[0].turn_index)
            if turn is None or turn.speaker is not TurnSpeaker.USER:
                raise ValueError("history-derived market requires a user turn")
            newest = self._newest_user_destination(context)
            if newest is None or history_uses[0].turn_index != newest[0] or history_uses[0].value != newest[1].value or output.requested_directory_market != newest[1].entry.market:
                raise ValueError("place-to-market resolution conflicts with interpreter output")
            return True
        if output.place_status is not PlaceStatus.NONE or output.requested_directory_market is not None or output.explicit_place is not None:
            raise ValueError("unmatched current place cannot declare a place or market")
        if ScopeIntent.INTERNATIONAL_SPONSORING in expected and not self._has_code(output, AmbiguityCode.UNKNOWN_EXPLICIT_PLACE):
            raise ValueError("directory request without a registered destination requires ambiguity")
        return False

    def _validate_intent(self, output: InterpreterOutput, request: V2Request) -> None:
        expected, compound = self._classify_request(request.message)
        if not self._current_use(output, ContextField.INTENT, request.message):
            raise ValueError("intent lacks current-request provenance")
        if compound:
            if not self._has_code(output, AmbiguityCode.COMPOUND_REQUEST):
                raise ValueError("compound request requires explicit ambiguity")
        elif len(expected) == 1 and output.intent not in expected:
            raise ValueError("interpreter output conflicts with current-request intent")
        elif not expected and not self._has_code(output, AmbiguityCode.UNKNOWN_CURRENT_INTENT):
            raise ValueError("unmarked current intent requires ambiguity")


def resolve_standalone_scope(result: StandaloneRequest) -> ScopeDecision:
    """The only V2-02 handoff to V2-01 scope resolution."""
    if not isinstance(result, StandaloneRequest):
        raise ValueError("result must be a StandaloneRequest")
    if not isinstance(result.requires_clarification, bool) or not isinstance(result.destination_validated, bool):
        raise ValueError("standalone clarification and destination flags must be bools")
    if not isinstance(result._proof, _BuilderProof) or result._proof.fingerprint != _result_fingerprint(replace(result, _proof=None)):
        raise ValueError("standalone result was not produced intact by the V2-02 builder")
    requires_clarification = bool({item.code for item in result.ambiguities} & set(_AMBIGUITY_DETAILS))
    destination_validated = result.requested_directory_market is not None
    if result.requires_clarification is not requires_clarification or result.destination_validated is not destination_validated:
        raise ValueError("standalone result semantic flags are inconsistent")
    if requires_clarification:
        raise ValueError("clarification result cannot resolve scope")
    if result.intent is ScopeIntent.INTERNATIONAL_SPONSORING and (not destination_validated or result.requested_directory_market is None):
        raise ValueError("international scope requires an explicit validated destination")
    request = V2Request(result.request_id, result.original_message, result.user_market, result.language, result.role, result.effective_version, turns=(), requested_directory_market=result.requested_directory_market)
    return resolve_scope(request, result.intent)


def _result_fingerprint(result: StandaloneRequest) -> str:
    material = repr((
        result.request_id, result.session_id, result.original_message, result.standalone_message, result.intent.value,
        result.user_market, result.requested_directory_market, result.role, result.language, result.effective_version,
        result.negated, result.number_tokens,
        tuple((item.field.value, item.source.value, item.value, item.start, item.end, item.turn_index) for item in result.context_uses),
        tuple((item.code.value, item.detail) for item in result.ambiguities), result.context_truncated,
        result.requires_clarification, result.destination_validated,
    )).encode("utf-8")
    return hashlib.sha256(material).hexdigest()

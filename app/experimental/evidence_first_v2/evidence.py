"""Offline V2-03 structural evidence and coverage contracts.

Catalogue/manifest inputs are trusted application configuration.  Documents,
provider candidates, annotations carried by documents, and fact wrappers are
untrusted data.  This binds structure; it does not prove semantic entailment.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .contracts import EvidenceAccess, EvidenceFact, EvidenceReference, FactQualifiers, V2Request, _enum, _required, _tuple_of
from .scope import ScopeDecision, ScopeIntent, resolve_scope


_CATALOG_TOKEN = object()
_QUALIFIERS = frozenset(("role", "unit", "timing", "exceptions"))
_NEGATED_PREFIX_RE = re.compile(r"\b(?:not|no|never)(?:[\s:/\-\u2010-\u2015]*)$", re.IGNORECASE)
_NUMERIC_CONTEXT = frozenset(("+", "-", "\u2212", "/", ":", ".", ",", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015"))


def _canon(value: object) -> bytes:
    """Unambiguous typed encoding for all V2-03 identities."""
    if value is None:
        return b"N"
    if isinstance(value, bool):
        return b"B1" if value else b"B0"
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return b"S" + str(len(raw)).encode("ascii") + b":" + raw
    if isinstance(value, int):
        return b"I" + str(value).encode("ascii") + b";"
    if isinstance(value, Enum):
        return b"E" + _canon(type(value).__qualname__) + _canon(value.value)
    if isinstance(value, tuple):
        return b"T" + str(len(value)).encode("ascii") + b":" + b"".join(_canon(item) for item in value)
    raise ValueError(f"unsupported canonical value type: {type(value).__name__}")


def _identity(value: object) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def canonical_identity(value: object) -> str:
    """Expose the typed canonical identity used by every V2-03 record."""
    return _identity(value)


def _span(start: object, end: object, text: str, value: str, name: str) -> None:
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(end, bool) or not isinstance(end, int):
        raise ValueError(f"{name} coordinates must be integers")
    if start < 0 or end <= start or end > len(text) or text[start:end] != _required(value, f"{name} value"):
        raise ValueError(f"{name} must bind exactly to its text span")


def _continues_token(char: str) -> bool:
    category = unicodedata.category(char)
    return category[0] in {"L", "N", "M"} or category == "Pc"


def _token_boundary(text: str, start: int, end: int) -> bool:
    return (start == 0 or not _continues_token(text[start - 1])) and (end == len(text) or not _continues_token(text[end]))


@dataclass(frozen=True)
class SourceAnnotation:
    """Untrusted document annotation. Governing metadata is never read here."""

    aspect: str
    start: int
    end: int
    value: str
    required_for: tuple[str, ...] = ()
    alternative_group: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "aspect", _required(self.aspect, "annotation aspect"))
        if isinstance(self.start, bool) or not isinstance(self.start, int) or isinstance(self.end, bool) or not isinstance(self.end, int):
            raise ValueError("annotation coordinates must be integers")
        object.__setattr__(self, "value", _required(self.value, "annotation value"))
        object.__setattr__(self, "required_for", _tuple_of(self.required_for, str, "annotation required_for"))
        if self.alternative_group is not None:
            object.__setattr__(self, "alternative_group", _required(self.alternative_group, "annotation alternative_group"))


@dataclass(frozen=True)
class SourceSection:
    source_id: str
    section_id: str
    text: str
    access: EvidenceAccess
    source_market: str
    language: str
    effective_version: str
    annotations: tuple[SourceAnnotation, ...]
    directory_market: str | None = None
    role: str | None = None
    role_neutral: bool = False

    def __post_init__(self) -> None:
        ref = EvidenceReference(self.source_id, self.section_id, "catalogue section", self.access, self.source_market, self.language, self.effective_version, self.directory_market, self.role)
        for name in ("source_id", "section_id", "access", "source_market", "language", "effective_version", "directory_market", "role"):
            object.__setattr__(self, name, getattr(ref, name))
        object.__setattr__(self, "text", _required(self.text, "section text"))
        if not isinstance(self.role_neutral, bool) or (self.role is not None and self.role_neutral) or (self.role is None and not self.role_neutral):
            raise ValueError("section role metadata is contradictory")
        annotations = _tuple_of(self.annotations, SourceAnnotation, "annotations")
        if not annotations:
            raise ValueError("section requires annotations")
        seen: set[tuple[str, int, int, str]] = set()
        for annotation in annotations:
            _span(annotation.start, annotation.end, self.text, annotation.value, "annotation")
            key = (annotation.aspect, annotation.start, annotation.end, annotation.value)
            if key in seen:
                raise ValueError("duplicate source annotation")
            seen.add(key)
        if self.role is not None and not any(item.aspect == "role" and item.value == self.role for item in annotations):
            raise ValueError("role-bound section requires an exact role annotation")
        object.__setattr__(self, "annotations", annotations)

    def reference(self, start: int, end: int) -> EvidenceReference:
        _span(start, end, self.text, self.text[start:end] if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(self.text) else "", "reference")
        return EvidenceReference(self.source_id, self.section_id, self.text[start:end], self.access, self.source_market, self.language, self.effective_version, self.directory_market, self.role)


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    section_id: str
    start: int
    end: int
    quote: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _required(self.source_id, "source_id"))
        object.__setattr__(self, "section_id", _required(self.section_id, "section_id"))
        if isinstance(self.start, bool) or not isinstance(self.start, int) or isinstance(self.end, bool) or not isinstance(self.end, int):
            raise ValueError("reference coordinates must be integers")
        object.__setattr__(self, "quote", _required(self.quote, "reference quote"))
        if self.start < 0 or self.end <= self.start:
            raise ValueError("reference has invalid coordinates")


@dataclass(frozen=True)
class AspectSupport:
    aspect: str
    start: int
    end: int
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "aspect", _required(self.aspect, "support aspect"))
        if isinstance(self.start, bool) or not isinstance(self.start, int) or isinstance(self.end, bool) or not isinstance(self.end, int):
            raise ValueError("support coordinates must be integers")
        object.__setattr__(self, "value", _required(self.value, "support value"))
        if self.start < 0 or self.end <= self.start:
            raise ValueError("support has invalid coordinates")


@dataclass(frozen=True)
class FactCandidate:
    text: str
    source_reference: SourceReference
    qualifiers: FactQualifiers
    supports: tuple[AspectSupport, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _required(self.text, "candidate text"))
        if not isinstance(self.source_reference, SourceReference) or not isinstance(self.qualifiers, FactQualifiers):
            raise ValueError("candidate requires source_reference and qualifiers")
        object.__setattr__(self, "supports", _tuple_of(self.supports, AspectSupport, "supports"))
        if not self.supports:
            raise ValueError("candidate requires supports")


@dataclass(frozen=True)
class GoverningRequirement:
    """Trusted manifest entry; it may add a target or authorize an alternative."""

    source_id: str
    section_id: str
    aspect: str
    start: int
    end: int
    value: str
    target_aspect: str
    alternative_group: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "section_id", "aspect", "value", "target_aspect"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if isinstance(self.start, bool) or not isinstance(self.start, int) or isinstance(self.end, bool) or not isinstance(self.end, int):
            raise ValueError("governing requirement coordinates must be integers")
        if self.alternative_group is not None:
            object.__setattr__(self, "alternative_group", _required(self.alternative_group, "alternative_group"))


@dataclass(frozen=True)
class GoverningManifest:
    """Trusted application configuration, separate from provider annotations."""

    requirements: tuple[GoverningRequirement, ...] = ()
    cross_section_alternatives: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", _tuple_of(self.requirements, GoverningRequirement, "manifest requirements"))
        groups = _tuple_of(self.cross_section_alternatives, str, "cross_section_alternatives")
        object.__setattr__(self, "cross_section_alternatives", frozenset(_required(group, "cross section group") for group in groups))


def _annotation_key(section: SourceSection, annotation: SourceAnnotation) -> tuple[object, ...]:
    return section.source_id, section.section_id, annotation.aspect, annotation.start, annotation.end, annotation.value


def _annotation_identity(section: SourceSection, annotation: SourceAnnotation) -> str:
    return _identity(("annotation",) + _annotation_key(section, annotation))


def _admit_annotation(section: SourceSection, annotation: SourceAnnotation) -> None:
    if annotation.required_for or annotation.alternative_group is not None:
        raise ValueError("document annotation cannot set governing requirements")
    _span(annotation.start, annotation.end, section.text, annotation.value, "annotation")
    if not _token_boundary(section.text, annotation.start, annotation.end):
        raise ValueError("annotation must use complete Unicode token boundaries")
    if any(char.isdecimal() for char in annotation.value):
        before = section.text[annotation.start - 1] if annotation.start else ""
        after = section.text[annotation.end] if annotation.end < len(section.text) else ""
        if (before and (before in _NUMERIC_CONTEXT or _continues_token(before))) or (after and (after in _NUMERIC_CONTEXT or _continues_token(after))):
            raise ValueError("numeric annotation must retain adjacent sign or numeric context")
    if _NEGATED_PREFIX_RE.search(section.text[:annotation.start]) and not annotation.value.casefold().startswith(("not ", "no ", "never ")):
        raise ValueError("affirmative annotation cannot be extracted from explicit negation")


def _section_key(section: SourceSection) -> tuple[str, str]:
    return section.source_id, section.section_id


def _scope_identity(scope: ScopeDecision) -> str:
    return _identity(("scope", scope.intent.value, scope.user_market, scope.directory_market, scope.allowed_access.value, scope.role, scope.language, scope.effective_version, scope.reason))


def _request_identity(request: V2Request) -> str:
    turns = tuple((turn.speaker.value, turn.text) for turn in request.turns)
    return _identity(("request", request.request_id, request.message, request.user_market, request.language, request.role, request.effective_version, turns, request.requested_directory_market))


def _manifest_identity(manifest: GoverningManifest) -> str:
    entries = tuple((item.source_id, item.section_id, item.aspect, item.start, item.end, item.value, item.target_aspect, item.alternative_group) for item in manifest.requirements)
    return _identity(("manifest", entries, tuple(sorted(manifest.cross_section_alternatives))))


def _catalog_identity(sections: tuple[SourceSection, ...], manifest: GoverningManifest) -> str:
    records = tuple((section.source_id, section.section_id, section.text, section.access.value, section.source_market, section.language, section.effective_version, section.directory_market, section.role, section.role_neutral, tuple(_annotation_identity(section, annotation) for annotation in section.annotations)) for section in sections)
    return _identity(("catalog", records, _manifest_identity(manifest)))


class SourceCatalog:
    """Immutable authoritative catalogue plus trusted governing manifest."""

    __slots__ = ("_sections", "_manifest", "identity", "_sealed")

    def __init__(self, sections: Iterable[SourceSection], manifest: GoverningManifest, *, _token: object | None = None) -> None:
        if _token is not _CATALOG_TOKEN:
            raise ValueError("SourceCatalog requires authoritative admission")
        items = tuple(sorted(_tuple_of(sections, SourceSection, "sections"), key=_section_key))
        if not items or len({_section_key(section) for section in items}) != len(items):
            raise ValueError("catalogue requires unique sections")
        object.__setattr__(self, "_sections", items)
        object.__setattr__(self, "_manifest", manifest)
        object.__setattr__(self, "identity", _catalog_identity(items, manifest))
        object.__setattr__(self, "_sealed", True)

    @classmethod
    def admit(cls, sections: Iterable[SourceSection], manifest: GoverningManifest | None = None) -> "SourceCatalog":
        proposals = _tuple_of(sections, SourceSection, "sections")
        manifest = GoverningManifest() if manifest is None else manifest
        if not isinstance(manifest, GoverningManifest):
            raise ValueError("manifest must be a GoverningManifest")
        for section in proposals:
            for annotation in section.annotations:
                _admit_annotation(section, annotation)
        cls._validate_manifest(proposals, manifest)
        return cls(proposals, manifest, _token=_CATALOG_TOKEN)

    @staticmethod
    def _validate_manifest(sections: tuple[SourceSection, ...], manifest: GoverningManifest) -> None:
        locations = {_annotation_key(section, annotation): section for section in sections for annotation in section.annotations}
        primary = {(section.source_id, section.section_id, annotation.aspect) for section in sections for annotation in section.annotations if annotation.aspect != "role"}
        seen_exact: set[tuple[object, ...]] = set()
        seen_authority: set[tuple[object, ...]] = set()
        grouped: dict[str, list[tuple[str, tuple[str, str]]]] = {}
        for item in manifest.requirements:
            key = (item.source_id, item.section_id, item.aspect, item.start, item.end, item.value)
            section = locations.get(key)
            if section is None or (section.source_id, section.section_id, item.target_aspect) not in primary:
                raise ValueError("manifest requirement must reference admitted annotation and governing aspect")
            exact = key + (item.target_aspect, item.alternative_group)
            authority = key + (item.target_aspect,)
            if exact in seen_exact:
                raise ValueError("duplicate governing requirement")
            if authority in seen_authority:
                raise ValueError("governing requirement has conflicting alternative groups")
            seen_exact.add(exact)
            seen_authority.add(authority)
            if item.alternative_group is not None:
                grouped.setdefault(item.alternative_group, []).append((item.target_aspect, (item.source_id, item.section_id)))
        for group, memberships in grouped.items():
            targets = {target for target, _section in memberships}
            sections_for_group = {section for _target, section in memberships}
            if len(targets) != 1:
                raise ValueError("alternative group must have one target aspect")
            if len(sections_for_group) > 1 and group not in manifest.cross_section_alternatives:
                raise ValueError("alternative groups must be section-local unless trusted cross-section")
            if len(sections_for_group) == 1 and group in manifest.cross_section_alternatives:
                raise ValueError("cross-section alternative must span multiple sections")
        if set(manifest.cross_section_alternatives) != {group for group, memberships in grouped.items() if len({section for _target, section in memberships}) > 1}:
            raise ValueError("cross-section alternatives must name exactly known spanning groups")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("SourceCatalog is immutable")
        object.__setattr__(self, name, value)

    @property
    def sections(self) -> tuple[SourceSection, ...]:
        return self._sections

    @property
    def manifest(self) -> GoverningManifest:
        return self._manifest

    def resolve(self, reference: SourceReference) -> SourceSection:
        matches = [section for section in self._sections if _section_key(section) == (reference.source_id, reference.section_id)]
        if len(matches) != 1:
            raise ValueError("reference is missing or ambiguous in current catalogue")
        _span(reference.start, reference.end, matches[0].text, reference.quote, "reference")
        return matches[0]


def _trusted_annotation(section: SourceSection, support: AspectSupport) -> SourceAnnotation:
    for annotation in section.annotations:
        if (annotation.aspect, annotation.start, annotation.end, annotation.value) == (support.aspect, support.start, support.end, support.value):
            return annotation
    raise ValueError("provider support is not a trusted admitted annotation")


def _qualifier_support(section: SourceSection, candidate: FactCandidate, aspect: str, value: str) -> None:
    matches = [item for item in section.annotations if item.aspect == aspect and item.value == value and candidate.source_reference.start <= item.start and item.end <= candidate.source_reference.end]
    if len(matches) != 1 or not any((support.aspect, support.start, support.end, support.value) == (aspect, matches[0].start, matches[0].end, value) for support in candidate.supports):
        raise ValueError(f"{aspect} qualifier lacks trusted annotation and support")


@dataclass(frozen=True)
class ValidatedFact:
    fact: EvidenceFact
    candidate: FactCandidate
    catalog_identity: str
    scope_identity: str
    fact_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.fact, EvidenceFact) or not isinstance(self.candidate, FactCandidate):
            raise ValueError("validated fact requires fact and candidate")
        for name in ("catalog_identity", "scope_identity", "fact_identity"):
            object.__setattr__(self, name, _required(getattr(self, name), name))


def _fact_identity(candidate: FactCandidate, catalog: SourceCatalog, scope: ScopeDecision) -> str:
    ref = candidate.source_reference
    qualifiers = candidate.qualifiers
    supports = tuple((item.aspect, item.start, item.end, item.value) for item in candidate.supports)
    return _identity(("fact", catalog.identity, _scope_identity(scope), candidate.text, (ref.source_id, ref.section_id, ref.start, ref.end, ref.quote), (qualifiers.role, qualifiers.unit, qualifiers.timing, qualifiers.exceptions), supports))


def _validate_candidate(candidate: FactCandidate, catalog: SourceCatalog, scope: ScopeDecision) -> ValidatedFact:
    section = catalog.resolve(candidate.source_reference)
    reference = section.reference(candidate.source_reference.start, candidate.source_reference.end)
    if not scope.permits(reference) or candidate.text != candidate.source_reference.quote:
        raise ValueError("candidate source or text is outside current scope")
    seen: set[tuple[str, int, int, str]] = set()
    for support in candidate.supports:
        if not (candidate.source_reference.start <= support.start and support.end <= candidate.source_reference.end):
            raise ValueError("support is outside candidate source quote")
        annotation = _trusted_annotation(section, support)
        key = (annotation.aspect, annotation.start, annotation.end, annotation.value)
        if key in seen:
            raise ValueError("duplicate candidate support")
        seen.add(key)
    qualifiers = candidate.qualifiers
    if section.role is not None:
        if qualifiers.role != section.role:
            raise ValueError("role-bound source requires its exact role qualifier")
        _qualifier_support(section, candidate, "role", section.role)
    elif qualifiers.role is not None:
        raise ValueError("role-neutral source cannot add a role qualifier")
    for name in ("unit", "timing"):
        contained = [item for item in section.annotations if item.aspect == name and candidate.source_reference.start <= item.start and item.end <= candidate.source_reference.end]
        value = getattr(qualifiers, name)
        if len(contained) > 1 or (contained and value != contained[0].value):
            raise ValueError(f"candidate must retain the exact {name} qualifier")
        if value is not None:
            _qualifier_support(section, candidate, name, value)
    exceptions = [item for item in section.annotations if item.aspect == "exceptions" and candidate.source_reference.start <= item.start and item.end <= candidate.source_reference.end]
    if tuple(item.value for item in exceptions) != qualifiers.exceptions:
        raise ValueError("candidate must retain every exact exception")
    for value in qualifiers.exceptions:
        _qualifier_support(section, candidate, "exceptions", value)
    fact = EvidenceFact(candidate.text, reference, qualifiers)
    return ValidatedFact(fact, candidate, catalog.identity, _scope_identity(scope), _fact_identity(candidate, catalog, scope))


def validate_facts(candidates: Iterable[FactCandidate], catalog: SourceCatalog, scope: ScopeDecision) -> tuple[ValidatedFact, ...]:
    candidates = _tuple_of(candidates, FactCandidate, "candidates")
    facts = tuple(_validate_candidate(item, catalog, scope) for item in candidates)
    keys = tuple((item.candidate.source_reference.source_id, item.candidate.source_reference.section_id, item.candidate.source_reference.start, item.candidate.source_reference.end) for item in facts)
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate fact source references are ambiguous")
    return facts


@dataclass(frozen=True)
class CoverageBranch:
    """Compatibility marker only; assessor derives all obligations afresh."""

    intent: ScopeIntent
    scope: ScopeDecision
    request_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent", _enum(self.intent, ScopeIntent, "intent"))
        if not isinstance(self.scope, ScopeDecision):
            raise ValueError("coverage branch requires scope")
        object.__setattr__(self, "request_identity", _required(self.request_identity, "request_identity"))


def build_coverage_branch(request: V2Request, scope: ScopeDecision, catalog: SourceCatalog) -> CoverageBranch:
    """Convenience only. Assessment never trusts its request-derived content."""
    if not isinstance(request, V2Request) or not isinstance(scope, ScopeDecision) or not isinstance(catalog, SourceCatalog):
        raise ValueError("request, scope, and admitted catalog are required")
    if resolve_scope(request, scope.intent) != scope:
        raise ValueError("scope is not the exact V2-01 scope for request")
    return CoverageBranch(scope.intent, scope, _request_identity(request))


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class CoverageGap:
    intent: ScopeIntent
    aspect: str
    reason: str


@dataclass(frozen=True)
class CoverageAssessment:
    status: CoverageStatus
    gaps: tuple[CoverageGap, ...]


def _aspects(actual_request: V2Request, catalog: SourceCatalog, scope: ScopeDecision) -> tuple[str, ...]:
    labels = sorted({annotation.aspect for section in catalog.sections if scope.permits(section.reference(0, len(section.text))) for annotation in section.annotations if annotation.aspect != "role"})
    found: list[str] = []
    for label in labels:
        start = 0
        while True:
            start = actual_request.message.find(label, start)
            if start < 0:
                break
            end = start + len(label)
            if _token_boundary(actual_request.message, start, end):
                found.append(label)
            start = end
    return tuple(found)


def _governing_sections(catalog: SourceCatalog, scope: ScopeDecision, aspect: str) -> tuple[SourceSection, ...]:
    return tuple(section for section in catalog.sections if scope.permits(section.reference(0, len(section.text))) and any(item.aspect == aspect for item in section.annotations))


def _manifest_rules(catalog: SourceCatalog, target: str) -> dict[tuple[str, str, str, int, int, str], str | None]:
    return {(item.source_id, item.section_id, item.aspect, item.start, item.end, item.value): item.alternative_group for item in catalog.manifest.requirements if item.target_aspect == target}


def _requirements(section: SourceSection, target: str, rules: dict[tuple[str, str, str, int, int, str], str | None]) -> tuple[tuple[SourceAnnotation, str | None], ...]:
    values: list[tuple[SourceAnnotation, str | None]] = []
    for annotation in section.annotations:
        key = _annotation_key(section, annotation)
        if annotation.aspect == target or annotation.aspect in _QUALIFIERS or key in rules:
            values.append((annotation, rules.get(key)))
    return tuple(values)


def _revalidated(item: ValidatedFact, catalog: SourceCatalog, scope: ScopeDecision) -> ValidatedFact | None:
    try:
        fresh = _validate_candidate(item.candidate, catalog, scope)
    except ValueError:
        return None
    if (item.catalog_identity, item.scope_identity, item.fact_identity, item.fact, item.candidate) != (fresh.catalog_identity, fresh.scope_identity, fresh.fact_identity, fresh.fact, fresh.candidate):
        raise ValueError("validated fact does not match current catalog and scope")
    return fresh


def _supports(fact: ValidatedFact, section: SourceSection, annotation: SourceAnnotation) -> bool:
    ref = fact.candidate.source_reference
    return ref.source_id == section.source_id and ref.section_id == section.section_id and any((item.aspect, item.start, item.end, item.value) == (annotation.aspect, annotation.start, annotation.end, annotation.value) for item in fact.candidate.supports)


def assess_coverage(actual_request: V2Request, branches: Iterable[CoverageBranch], catalog: SourceCatalog, facts: Iterable[ValidatedFact]) -> CoverageAssessment:
    """Recompute scopes and obligations from externally held actual request."""
    if not isinstance(actual_request, V2Request) or not isinstance(catalog, SourceCatalog):
        raise ValueError("actual V2 request and admitted catalog are required")
    branches = _tuple_of(branches, CoverageBranch, "coverage branches")
    facts = _tuple_of(facts, ValidatedFact, "validated facts")
    if not branches:
        raise ValueError("coverage requires branches")
    gaps: list[CoverageGap] = []
    for branch in branches:
        expected_scope = resolve_scope(actual_request, branch.intent)
        if branch.request_identity != _request_identity(actual_request) or branch.scope != expected_scope:
            raise ValueError("coverage branch does not match externally held actual request and scope")
        aspects = _aspects(actual_request, catalog, expected_scope)
        if not aspects:
            raise ValueError("actual request has no admitted governing aspect")
        usable = [fresh for item in facts if (fresh := _revalidated(item, catalog, expected_scope)) is not None]
        for aspect in aspects:
            sections = _governing_sections(catalog, expected_scope, aspect)
            if not sections:
                gaps.append(CoverageGap(branch.intent, aspect, "missing_governing_section"))
                continue
            rules = _manifest_rules(catalog, aspect)
            mandatory: list[tuple[SourceSection, SourceAnnotation]] = []
            alternatives: dict[str, list[tuple[SourceSection, SourceAnnotation]]] = {}
            for section in sections:
                for annotation, group in _requirements(section, aspect, rules):
                    (alternatives.setdefault(group, []) if group is not None else mandatory).append((section, annotation))
            requirements = [(item,) for item in mandatory] + [tuple(items) for _, items in sorted(alternatives.items())]
            if not requirements or any(not any(_supports(fact, section, annotation) for fact in usable for section, annotation in requirement) for requirement in requirements):
                gaps.append(CoverageGap(branch.intent, aspect, "missing_validated_evidence"))
    return CoverageAssessment(CoverageStatus.COMPLETE if not gaps else CoverageStatus.UNCERTAIN, tuple(gaps))
